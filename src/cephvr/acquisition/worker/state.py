"""Authoritative, generation-local worker state and retained command records."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock

from google.protobuf.message import Message

from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import runtime_pb2
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.commands import CommandLedger

from .limits import AcquisitionControlLimits
from .terminal_scope import terminal_evidence_scope, terminal_target
from .warnings import WorkerWarningLedger


@dataclass(frozen=True)
class WorkerBootstrap:
    """Protected startup inputs; camera settings are delivered after registration."""

    context: acq.WorkerContext
    supervisor: control.ProcessIdentity
    coordinator_endpoint: str
    coordinator_credential: bytes = field(repr=False)
    control_policies: control.ControlPolicies
    file_policy: runtime_pb2.CameraFilePolicy
    worker_credential: str = field(repr=False)
    owner_credential: str = field(repr=False)
    supervisor_credential: str = field(repr=False)
    supervisor_endpoint: str
    launch_command_id: str
    pid: int
    creation_time_100ns: int
    registration_deadline_ns: int
    max_message_bytes: int
    heartbeat_interval_ns: int
    health_silence_ns: int


@dataclass
class WorkerState:
    context: acq.WorkerContext
    supervisor: control.ProcessIdentity
    commands: CommandLedger
    lock: RLock = field(default_factory=RLock)
    state_revision: int = 0
    confirmed_configuration_revision: int = 0
    lifecycle: dict[tuple[str, str], acq.WorkerLifecycleEvidence] = field(
        default_factory=dict
    )
    operations: dict[str, control.OperationState] = field(default_factory=dict)
    supervisor_command_ids: set[str] = field(default_factory=set)
    warnings: WorkerWarningLedger | None = None
    interrupted: bool = False
    shutdown_requested: bool = False
    max_retained_views: int = 0
    limits: AcquisitionControlLimits | None = None
    registered: bool = False
    health_work: control.WorkContext | None = None
    health_session_phase: control.SessionPhase = control.SESSION_PHASE_CONFIGURATION
    health_trial_phase: control.TrialPhase | None = None
    health_progress_required: bool = False
    health_last_progress_ns: int | None = None
    health_owner_observed_ns: int | None = None
    health_active_error: control.ErrorReport | None = None
    health_continuing_functions: tuple[control.ContinuingFunctionEvidence, ...] = ()
    prepared_functions: tuple[control.PreparedFunctionScope, ...] = ()

    @classmethod
    def create(
        cls,
        bootstrap: WorkerBootstrap,
        *,
        retention_ns: int,
        limits: AcquisitionControlLimits,
    ) -> WorkerState:
        if limits.max_message_bytes != bootstrap.max_message_bytes:
            raise ValueError(
                "worker limits differ from protected startup message limit"
            )
        state = cls(
            bootstrap.context,
            bootstrap.supervisor,
            CommandLedger(
                bootstrap.context.worker.generation,
                retention_ns,
                max_records=limits.max_records,
                max_bytes=limits.max_bytes,
                result_reservation_bytes=limits.normal_result_reservation_bytes,
                safety_reserve_records=limits.safety_reserve_records,
                safety_reserve_bytes=limits.safety_reserve_bytes,
            ),
            max_retained_views=limits.max_records,
            limits=limits,
        )
        state.warnings = WorkerWarningLedger(bootstrap.context)
        return state

    def changed(self) -> int:
        with self.lock:
            self.state_revision += 1
            return self.state_revision

    def update_health_snapshot(
        self,
        *,
        work: control.WorkContext | None,
        session_phase: control.SessionPhase,
        trial_phase: control.TrialPhase | None,
        progress_required: bool,
        last_progress_ns: int | None,
        observed_ns: int,
    ) -> None:
        """Publish a bounded owner snapshot for the independent health loop."""
        with self.lock:
            self.health_work = _copy_work(work) if work is not None else None
            self.health_session_phase = session_phase
            self.health_trial_phase = trial_phase
            self.health_progress_required = progress_required
            self.health_last_progress_ns = last_progress_ns
            self.health_owner_observed_ns = observed_ns

    def update_fault_snapshot(
        self,
        error: control.ErrorReport,
        continuing: tuple[control.ContinuingFunctionEvidence, ...],
    ) -> None:
        """Retain exact typed isolation and healthy-function observations."""
        with self.lock:
            saved = control.ErrorReport()
            saved.CopyFrom(error)
            self.health_active_error = saved
            copied: list[control.ContinuingFunctionEvidence] = []
            for item in continuing:
                snapshot = control.ContinuingFunctionEvidence()
                snapshot.CopyFrom(item)
                copied.append(snapshot)
            self.health_continuing_functions = tuple(copied)

    def update_continuing_snapshot(
        self, continuing: tuple[control.ContinuingFunctionEvidence, ...]
    ) -> None:
        with self.lock:
            copied: list[control.ContinuingFunctionEvidence] = []
            for item in continuing:
                snapshot = control.ContinuingFunctionEvidence()
                snapshot.CopyFrom(item)
                copied.append(snapshot)
            self.health_continuing_functions = tuple(copied)

    def install_prepared_functions(
        self, scopes: tuple[control.PreparedFunctionScope, ...]
    ) -> None:
        with self.lock:
            if self.prepared_functions:
                prior = tuple(
                    item.SerializeToString(deterministic=True)
                    for item in self.prepared_functions
                )
                current = tuple(
                    item.SerializeToString(deterministic=True) for item in scopes
                )
                if prior != current:
                    raise ValueError(
                        "worker function catalogue changed in one generation"
                    )
                return
            copied: list[control.PreparedFunctionScope] = []
            for scope in scopes:
                item = control.PreparedFunctionScope()
                item.CopyFrom(scope)
                copied.append(item)
            self.prepared_functions = tuple(copied)

    def recording_fault_resources(self) -> tuple[str, ...]:
        from cephvr.acquisition.worker.function_scopes import recording_scope_resources

        with self.lock:
            return recording_scope_resources(
                self.prepared_functions, self.context.camera
            )

    def heartbeat_report(
        self, sent_ns: int, *, health_silence_ns: int
    ) -> control.HeartbeatReport:
        """Copy the current scope and data-progress evidence under one lock."""
        with self.lock:
            report = control.HeartbeatReport(
                source=self.context.worker,
                sent_monotonic_ns=sent_ns,
                health_summary="interrupted" if self.interrupted else "healthy",
            )
            if self.health_work is not None:
                report.work.CopyFrom(self.health_work)
            if self.health_active_error is not None:
                report.active_error.CopyFrom(self.health_active_error)
            owner_fresh = (
                self.health_owner_observed_ns is not None
                and sent_ns >= self.health_owner_observed_ns
                and sent_ns - self.health_owner_observed_ns < health_silence_ns
            )
            for function in self.health_continuing_functions:
                current = control.ContinuingFunctionEvidence()
                current.CopyFrom(function)
                if not owner_fresh:
                    current.functioning = False
                    current.control_path_valid = False
                elif (
                    self.health_progress_required
                    and self.health_last_progress_ns is not None
                    and (
                        sent_ns < self.health_last_progress_ns
                        or sent_ns - self.health_last_progress_ns >= health_silence_ns
                    )
                ):
                    # The control loop ages only the immutable owner snapshot. It
                    # never reads mutable camera/capture objects across threads.
                    if current.resource_id.endswith(".capture"):
                        current.functioning = False
                report.continuing_functions.add().CopyFrom(current)
            if self.health_trial_phase is not None:
                report.trial_phase = self.health_trial_phase
                progress = report.workers.add(
                    worker=self.context.worker.role,
                    progress_required=self.health_progress_required,
                )
                if self.health_last_progress_ns is not None:
                    progress.last_progress_monotonic_ns = self.health_last_progress_ns
                progress.evidence.camera = self.context.camera
                progress.evidence.producer.CopyFrom(self.context.worker)
            else:
                report.session_phase = self.health_session_phase
            return report

    def complete_operation(
        self,
        command_id: str,
        *,
        succeeded: bool,
        progress: str,
        now_ns: int,
        failure: control.Failure | None = None,
        retained_result: Message | None = None,
    ) -> control.OperationState:
        with self.lock:
            prior = self.operations.get(command_id)
            if prior is None:
                raise ValueError("worker operation is not retained")
            if prior.complete:
                if prior.succeeded != succeeded:
                    raise ValueError("worker operation terminal result changed")
                return prior
            updated = control.OperationState()
            updated.CopyFrom(prior)
            updated.complete = True
            updated.succeeded = succeeded
            updated.progress = progress
            if failure is not None:
                updated.failure.CopyFrom(failure)
            if retained_result is None:
                source = acq.WorkerContext.FromString(self.context.SerializeToString())
                if updated.HasField("work"):
                    source.work.CopyFrom(updated.work)
                retained_result = acq.WorkerOperationReport(source=source)
            if isinstance(retained_result, acq.WorkerOperationReport):
                retained_result.operation.CopyFrom(updated)
                retained_result.state_revision = self.state_revision + 1
            result = retained_result.SerializeToString(deterministic=True)
            self.commands.complete(command_id, result, now_ns)
            self.operations[command_id] = updated
            self.state_revision += 1
            return _copy_operation(updated)

    def retain_lifecycle(self, evidence: acq.WorkerLifecycleEvidence) -> None:
        if (
            not evidence.HasField("source")
            or not evidence.HasField("operation")
            or not evidence.HasField("state_revision")
        ):
            raise ValueError(
                "worker lifecycle evidence lacks exact source or operation"
            )
        if evidence.source.worker != self.context.worker:
            raise ValueError("worker lifecycle evidence has another generation")
        if (
            evidence.source.owner != self.context.owner
            or evidence.source.camera != self.context.camera
        ):
            raise ValueError("worker lifecycle evidence has another registered context")
        if self.context.HasField("work") and evidence.source.HasField("work"):
            if not _same_session(evidence.source.work, self.context.work):
                raise ValueError("worker lifecycle evidence has another session")
        kind = evidence.WhichOneof("evidence")
        if kind is None:
            raise ValueError("worker lifecycle evidence has no evidence kind")
        key = (evidence.operation.command_id, kind)
        with self.lock:
            prior = self.lifecycle.get(key)
            if prior is not None:
                if prior.state_revision > evidence.state_revision:
                    return
                if prior.state_revision == evidence.state_revision:
                    if prior.SerializeToString(
                        deterministic=True
                    ) != evidence.SerializeToString(deterministic=True):
                        raise ValueError(
                            "same worker lifecycle revision changed evidence"
                        )
                    return
            saved = acq.WorkerLifecycleEvidence()
            saved.CopyFrom(evidence)
            payload_key = f"worker-lifecycle:{key[0]}:{key[1]}"
            retained_command = self.commands.get(key[0])
            retention_work_key = (
                terminal_evidence_scope(retained_command, evidence.source)
                if retained_command is not None
                else None
            ) or _work_key(evidence.source)
            self.commands.reserve_payload(
                payload_key,
                saved.ByteSize(),
                work_key=retention_work_key,
                priority=bool(retained_command and retained_command.priority),
            )
            self.lifecycle[key] = saved
            self.state_revision += 1

    def finalize_work(self, work_key: str, now_ns: int) -> None:
        with self.lock:
            self.commands.finalize_work(work_key, now_ns)

    def finalize_terminal_command(self, command_id: str, now_ns: int) -> bool:
        """Finalize only a completed Cleanup/Shutdown command-local receipt."""
        with self.lock:
            record = self.commands.get(command_id)
            target = None if record is None else terminal_target(record)
            if record is None or target is None:
                return False
            if terminal_evidence_scope(record, target) is None:
                return False
            if record.result is None:
                raise ValueError("terminal command cannot finalize before completion")
            self.commands.finalize_work(command_id, now_ns)
            self.prune(now_ns)
        return True

    def finalize_scope(self, work: control.WorkContext, now_ns: int) -> bool:
        """Finalize and prune one exact closed session or trial retention scope."""
        kind = work.WhichOneof("work")
        work_key = (
            work.trial.trial_id
            if kind == "trial"
            else work.session.session_id
            if kind == "session"
            else None
        )
        if work_key is None:
            return False
        with self.lock:
            self.commands.finalize_work(work_key, now_ns)
            self.prune(now_ns)
        return True

    def prune(self, now_ns: int) -> int:
        with self.lock:
            removed = self.commands.prune(now_ns)
            for command_id in tuple(self.operations):
                if self.commands.get(command_id) is None:
                    del self.operations[command_id]
                    self.supervisor_command_ids.discard(command_id)
            for key in tuple(self.lifecycle):
                if self.commands.get(key[0]) is None:
                    del self.lifecycle[key]
            return removed


def _copy_operation(value: control.OperationState) -> control.OperationState:
    result = control.OperationState()
    result.CopyFrom(value)
    return result


def _copy_work(value: control.WorkContext | None) -> control.WorkContext:
    result = control.WorkContext()
    if value is not None:
        result.CopyFrom(value)
    return result


def _work_key(context: acq.WorkerContext) -> str:
    if not context.HasField("work"):
        return context.worker.generation
    kind = context.work.WhichOneof("work")
    if kind == "trial":
        return context.work.trial.trial_id
    if kind == "session":
        return context.work.session.session_id
    return context.worker.generation


def _same_session(left: control.WorkContext, right: control.WorkContext) -> bool:
    left_kind, right_kind = left.WhichOneof("work"), right.WhichOneof("work")
    if left_kind == "session" and right_kind == "session":
        return left.session == right.session
    if left_kind == "trial" and right_kind == "trial":
        return left.trial.session == right.trial.session
    if left_kind == "trial" and right_kind == "session":
        return left.trial.session == right.session
    if left_kind == "session" and right_kind == "trial":
        return left.session == right.trial.session
    return False
