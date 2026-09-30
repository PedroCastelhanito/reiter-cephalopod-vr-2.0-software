"""Exact state and retained-result reads over focused coordinator records (E08)."""

from __future__ import annotations

from collections.abc import Callable

from cephvr.acquisition.coordinator.manual_device_status import (
    ManualDeviceStatusReporter,
)
from cephvr.acquisition.state import (
    CoordinatorIdentity,
    SessionRecord,
    SessionSlot,
    WorkerRecord,
)
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger


class CoordinatorQueries:
    """Answer reads from the same authoritative records that own each fact."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        session_slot: SessionSlot,
        workers: dict[int, WorkerRecord],
        commands: CommandLedger,
        device_status: ManualDeviceStatusReporter,
        current_error: Callable[[], control.ErrorReport | None],
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.session_slot = session_slot
        self.workers = workers
        self.commands = commands
        self.device_status = device_status
        self.current_error = current_error
        self.clock = clock

    async def get_state(
        self, request: wire.BackendQuery, *, deadline_ns: int
    ) -> control.ParticipantState:
        if (
            request.target != self.identity.backend
            or self.clock() >= deadline_ns
            or not self._query_work_matches(request.work)
        ):
            raise ValueError(
                "backend state query is stale or targets another work scope"
            )
        session = self._session_for_work(request.work)
        participant = control.ParticipantState(
            process=self.identity.process,
            enabled=bool(session and session.required_cameras),
            required=True,
            process_running=True,
            connected=bool(self.workers),
            health="interrupted" if session and session.interrupted else "healthy",
        )
        if session is None:
            participant.session_phase = control.SESSION_PHASE_CONFIGURATION
        elif session.cleanup_complete:
            participant.session_phase = control.SESSION_PHASE_CONFIGURATION
        elif session.interrupted or session.setup_cancelled:
            participant.session_phase = control.SESSION_PHASE_FINALIZING
        elif session.ready_report is not None:
            participant.session_phase = control.SESSION_PHASE_READY
            participant.ready.context.CopyFrom(session.ready_report.context)
            participant.ready.configuration_revision = (
                session.ready_report.configuration_revision
            )
            participant.ready.required_checks_passed = (
                session.ready_report.required_checks_passed
            )
        else:
            participant.session_phase = control.SESSION_PHASE_SETTING_UP
        if session is not None:
            cleanup = self._latest_cleanup_report(session, request.target, request.work)
            if cleanup is not None:
                participant.cleanup.CopyFrom(cleanup)
        if session is not None and session.trial is not None:
            trial = session.trial
            if trial.finished_report is not None:
                participant.trial_phase = control.TRIAL_PHASE_ENDED
                participant.finished.CopyFrom(trial.finished_report)
            elif trial.stopped_report is not None:
                participant.trial_phase = control.TRIAL_PHASE_FINALIZING
                participant.stopped.CopyFrom(trial.stopped_report)
            elif trial.started_report is not None:
                participant.trial_phase = control.TRIAL_PHASE_RUNNING
                participant.started.CopyFrom(trial.started_report)
            elif trial.ready_report is not None:
                participant.trial_phase = control.TRIAL_PHASE_READY
                participant.ready.context.CopyFrom(trial.ready_report.context)
                participant.ready.configuration_revision = (
                    trial.ready_report.configuration_revision
                )
                participant.ready.required_checks_passed = (
                    trial.ready_report.required_checks_passed
                )
            else:
                participant.trial_phase = control.TRIAL_PHASE_PREPARING
        for worker in self.workers.values():
            if worker.heartbeat is not None:
                observed = worker.heartbeat.sent_monotonic_ns
                participant.last_evidence_monotonic_ns = max(
                    participant.last_evidence_monotonic_ns, observed
                )
            participant.acquisition_warnings.extend(worker.warning_views.values())
        error = self.current_error()
        if error is not None:
            participant.errors.add().CopyFrom(error)
        return participant

    async def get_retained_result(
        self, request: wire.RetainedResultQuery, *, deadline_ns: int
    ) -> wire.RetainedResult:
        if (
            request.query.target != self.identity.backend
            or self.clock() >= deadline_ns
            or not request.command_id
            or not self._query_work_matches(request.query.work)
        ):
            raise ValueError("retained-result query is invalid or expired")
        item = wire.RetainedResult(
            backend=self.identity.backend,
            work=request.query.work,
        )
        retained = self.commands.get(request.command_id)
        terminal_command = retained is not None and _is_terminal_command(
            retained.canonical_request
        )
        if retained is not None and terminal_command:
            work_matches = _terminal_scope_matches(
                retained.canonical_request,
                retained.work_key,
                request.command_id,
                request.query.target,
                request.query.work,
            )
        else:
            work_matches = (
                retained is not None
                and retained.work_key
                == _query_work_key(request.query.work, request.command_id)
            )
        if retained is not None and work_matches:
            item.found = True
            if retained.result is not None:
                item.admission.CopyFrom(
                    control.CommandAdmission.FromString(retained.result)
                )
            if retained.executor_result is not None:
                item.operation.CopyFrom(
                    control.OperationState.FromString(retained.executor_result)
                )
            status = self.device_status.get_report(request.command_id)
            if (
                status is not None
                and status.work == request.query.work
                and status.operation.command_id == request.command_id
            ):
                item.acquisition_device_result.CopyFrom(status)
        session = self._session_for_work(request.query.work)
        if session is not None and request.query.work == session.work:
            command = self.commands.get(request.command_id)
            if (
                session.operation.command_id == request.command_id
                and command is not None
                and command.work_key == session.work.session.session_id
            ):
                item.found = True
                if command.result:
                    item.admission.CopyFrom(
                        control.CommandAdmission.FromString(command.result)
                    )
                if session.ready_report is not None:
                    item.ready.CopyFrom(session.ready_report)
                if session.resolved_report is not None:
                    item.acquisition_resolution.CopyFrom(session.resolved_report)
        if (
            session is not None
            and session.trial is not None
            and request.query.work == session.trial.work
            and request.command_id == session.trial.preparation.command_id
        ):
            trial = session.trial
            command = self.commands.get(request.command_id)
            if command is not None and command.work_key == trial.work.trial.trial_id:
                item.found = True
                if command.result:
                    item.admission.CopyFrom(
                        control.CommandAdmission.FromString(command.result)
                    )
                if trial.ready_report is not None:
                    item.ready.CopyFrom(trial.ready_report)
                if trial.started_report is not None:
                    item.started.CopyFrom(trial.started_report)
                if trial.stopped_report is not None:
                    item.stopped.CopyFrom(trial.stopped_report)
                if trial.finished_report is not None:
                    item.finished.CopyFrom(trial.finished_report)
                    item.outputs.extend(trial.finished_report.outputs)
        return item

    def _query_work_matches(self, requested: control.WorkContext) -> bool:
        if requested.WhichOneof("work") is None:
            current = self.session_slot.current
            return current is None or current.cleanup_complete
        return self._session_for_work(requested) is not None

    def _session_for_work(self, requested: control.WorkContext) -> SessionRecord | None:
        selected = requested.WhichOneof("work")
        if selected is None:
            return None
        self.commands.prune(self.clock())
        self.session_slot.prune_completed(self.commands)
        current = self.session_slot.current
        candidates = [*self.session_slot.completed.values()]
        if current is not None:
            candidates.append(current)
        for session in candidates:
            if selected == "session" and requested == session.work:
                return session
            if (
                selected == "trial"
                and requested.trial.session == session.work.session
                and session.trial is not None
                and requested == session.trial.work
            ):
                return session
        return None

    def _latest_cleanup_report(
        self,
        session: SessionRecord,
        target: control.BackendContext,
        work: control.WorkContext,
    ) -> control.CleanupReport | None:
        pending = session.pending_cleanup_report
        if pending is not None and self._cleanup_report_is_live(pending, target, work):
            return pending
        for command_id in reversed(tuple(session.cleanup_report_history)):
            report = session.cleanup_report_history[command_id]
            if not self._cleanup_report_is_live(report, target, work):
                continue
            return report
        return None

    def _cleanup_report_is_live(
        self,
        report: control.CleanupReport,
        target: control.BackendContext,
        work: control.WorkContext,
    ) -> bool:
        command_id = report.operation.command_id
        retained = self.commands.get(command_id)
        return (
            retained is not None
            and retained.work_key == command_id
            and _is_terminal_command(retained.canonical_request)
            and _terminal_scope_matches(
                retained.canonical_request,
                retained.work_key,
                command_id,
                target,
                work,
            )
            and report.work == work
        )


def _query_work_key(work: control.WorkContext, command_id: str) -> str:
    selected = work.WhichOneof("work")
    if selected == "session":
        return work.session.session_id
    if selected == "trial":
        return work.trial.trial_id
    return command_id


def _terminal_scope_matches(
    canonical: bytes,
    work_key: str,
    command_id: str,
    target: control.BackendContext,
    work: control.WorkContext,
) -> bool:
    """Bind command-local terminal retention back to its exact original scope."""
    if work_key != command_id:
        return False
    try:
        method, encoded = canonical.split(b"\0", 1)
        command = wire.BackendCommand.FromString(encoded)
    except (ValueError, TypeError):
        return False
    return (
        command.command_id == command_id
        and command.target == target
        and command.work == work
    )


def _is_terminal_command(canonical: bytes) -> bool:
    try:
        method, _encoded = canonical.split(b"\0", 1)
    except ValueError:
        return False
    return method in {b"Cleanup", b"Shutdown"}
