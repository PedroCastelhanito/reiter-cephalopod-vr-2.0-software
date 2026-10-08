"""Session and trial records with bounded cleanup evidence retention."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from uuid import uuid4

from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.commands import CommandLedger


@dataclass
class SessionSlot:
    """Single live Setup/session authority; no duplicate session IDs."""

    current: SessionRecord | None = None
    interrupted: bool = False
    completed: dict[str, SessionRecord] = field(default_factory=dict)

    def prune_completed(self, commands: CommandLedger) -> int:
        if self.current is not None:
            self.current.prune_retained_data(commands, current=True)
        for session in self.completed.values():
            session.prune_retained_data(commands, current=False)
        expired = [
            session_id
            for session_id, session in self.completed.items()
            if not commands.has_retained_work(session_id)
            and not any(
                commands.has_retained_work(command_id)
                for command_id in session.cleanup_report_history
            )
            and not (
                session.pending_cleanup_report is not None
                and commands.has_retained_work(
                    session.pending_cleanup_report.operation.command_id
                )
            )
        ]
        for session_id in expired:
            self.completed.pop(session_id, None)
        return len(expired)

    def retain_completed(self, session: SessionRecord, commands: CommandLedger) -> None:
        if not session.cleanup_complete:
            raise ValueError("only fully cleaned sessions can enter retained history")
        self.prune_completed(commands)
        session_id = session.work.session.session_id
        if session_id in self.completed:
            if self.completed[session_id] is not session:
                raise ValueError(
                    "completed session identity changed and cannot be replaced"
                )
            return
        if len(self.completed) >= commands.max_records:
            raise RuntimeError("completed session retention capacity is exhausted")
        # The current slot remains authoritative until every admission check for
        # the history handoff has succeeded. In particular, never drop the
        # independent local proof reservation on a failed history insertion.
        session.handoff_cleanup_proof(commands)
        self.completed[session_id] = session


@dataclass
class TrialRecord:
    work: control.WorkContext
    plan: control.TrialPlan
    preparation: control.OperationContext
    configuration_revision: int
    schedule: control.OperationContext | None = None
    release: control.OperationContext | None = None
    stop: control.OperationContext | None = None
    start_monotonic_ns: int | None = None
    end_monotonic_ns: int | None = None
    stop_issued_ns: int | None = None
    stop_deadline_ns: int | None = None
    trial_file_prefix: str | None = None
    outputs: list[control.OutputPlan] = field(default_factory=list)
    ready_report: control.ReadyReport | None = None
    ready_reported: bool = False
    started_report: control.StartedReport | None = None
    stopped_report: control.StoppedReport | None = None
    finished_report: control.FinishedReport | None = None
    pending_started_report: control.StartedReport | None = None
    pending_stopped_report: control.StoppedReport | None = None
    pending_finished_report: control.FinishedReport | None = None
    lifecycle_report_attempts: dict[str, int] = field(default_factory=dict)
    ready_deadline_ns: int | None = None
    pending_ready_report: control.ReadyReport | None = None
    pending_ready_attempts: int = 0
    ready_confirmed: asyncio.Event = field(default_factory=asyncio.Event)
    pulse_on_task: asyncio.Task[None] | None = None
    pulse_off_task: asyncio.Task[None] | None = None
    normal_end_task: asyncio.Task[None] | None = None
    pulse_on_ready: asyncio.Event = field(default_factory=asyncio.Event)
    pulse_off_ready: asyncio.Event = field(default_factory=asyncio.Event)
    pulse_on: mcu.PulseCommandEvidence | None = None
    pulse_off: mcu.PulseCommandEvidence | None = None
    pulse_delivery_deadline_ns: int | None = None
    interrupted: bool = False


@dataclass
class SessionRecord:
    work: control.WorkContext
    operation: control.OperationContext
    configuration_revision: int
    required_cameras: set[int]
    reserved_outputs: list[control.OutputPlan] = field(default_factory=list)
    dispatched_output_keys: set[str] = field(default_factory=set)
    output_results: dict[str, control.OutputResult] = field(default_factory=dict)
    requested_configuration_revision: int | None = None
    tracking_required: bool = False
    setup_cancelled: bool = False
    ready_report: control.ReadyReport | None = None
    trial: TrialRecord | None = None
    interrupted: bool = False
    cleanup_complete: bool = False
    cleanup_delivery_complete: bool = False
    camera_resolutions: dict[int, camera_pb2.CameraResolvedState] = field(
        default_factory=dict
    )
    resolution_reported: bool = False
    expected_attachments: dict[int, set[str]] = field(default_factory=dict)
    prepared_functions: dict[int, list[control.PreparedFunctionScope]] = field(
        default_factory=dict
    )
    pending_ready_report: control.ReadyReport | None = None
    pending_ready_deadline_ns: int | None = None
    pending_ready_attempts: int = 0
    pending_resolution_report: wire.AcquisitionResolutionReport | None = None
    pending_resolution_deadline_ns: int | None = None
    pending_resolution_attempts: int = 0
    setup_deadline_ns: int | None = None
    confirmed_settings: control.AcquisitionSettings | None = None
    confirmed_revision: int | None = None
    resolution_confirmed: asyncio.Event = field(default_factory=asyncio.Event)
    ready_confirmed: asyncio.Event = field(default_factory=asyncio.Event)
    resolved_report: wire.AcquisitionResolutionReport | None = None
    pulse_resolution: mcu.PulseConfigurationResolution | None = None
    tracking_input_report: wire.DataPreparationReport | None = None
    tracking_input_confirmation: wire.TrackingInputConfirmation | None = None
    tracking_input_confirmed: asyncio.Event = field(default_factory=asyncio.Event)
    tracking_cleanup_confirmation: wire.TrackingInputConfirmation | None = None
    tracking_cleanup_confirmed: asyncio.Event = field(default_factory=asyncio.Event)
    cleanup_deadline_ns: int | None = None
    cleanup_command_id: str | None = None
    cleanup_attempt_deadline_ns: int | None = None
    pending_cleanup_report: control.CleanupReport | None = None
    cleanup_report_recipients: set[str] = field(default_factory=set)
    cleanup_report_history: dict[str, control.CleanupReport] = field(
        default_factory=dict
    )
    cleanup_reserved_bytes: int = 0
    cleanup_local_scope: str = field(default_factory=lambda: str(uuid4()))
    cleanup_local_payload_key: str | None = None
    serial_owner_released: bool = False
    cleanup_resources: list[control.ResourceObligation] = field(default_factory=list)
    cleanup_resources_revision: int = 0
    cleanup_catalogue_initialized: bool = False
    pending_cleanup_heartbeat: control.HeartbeatReport | None = None
    incident_revisions: dict[str, int] = field(default_factory=dict)
    confirmed_incidents: dict[str, control.RuntimeIncident] = field(
        default_factory=dict
    )
    unavailable_resources: set[str] = field(default_factory=set)

    def retain_output_result(
        self,
        result: control.OutputResult,
        commands: CommandLedger,
    ) -> None:
        """Retain one exact reserved output closure under shared E08 limits."""
        self.preflight_output_results((result,), commands)
        if result.output_key not in {item.output_key for item in self.reserved_outputs}:
            raise ValueError("output result is outside the exact Setup reservation")
        serialized = result.SerializeToString(deterministic=True)
        old = self.output_results.get(result.output_key)
        if old is not None and old.SerializeToString(deterministic=True) != serialized:
            raise ValueError("reserved output result changed after retention")
        retained = control.OutputResult.FromString(serialized)
        candidates = dict(self.output_results)
        candidates[result.output_key] = retained
        self._reserve_session_evidence(commands, output_results=candidates)
        self.output_results[result.output_key] = retained

    def preflight_output_results(
        self,
        results: tuple[control.OutputResult, ...],
        commands: CommandLedger,
    ) -> None:
        """Reserve exact result bytes before confirming any transfer release."""
        expected = {item.output_key for item in self.reserved_outputs}
        candidates = dict(self.output_results)
        for result in results:
            if result.output_key not in expected:
                raise ValueError("output result is outside the exact Setup reservation")
            serialized = result.SerializeToString(deterministic=True)
            old = candidates.get(result.output_key)
            if (
                old is not None
                and old.SerializeToString(deterministic=True) != serialized
            ):
                raise ValueError("reserved output result changed after retention")
            candidates[result.output_key] = control.OutputResult.FromString(serialized)
        self._reserve_session_evidence(commands, output_results=candidates)

    def retain_cleanup_report(
        self,
        report: control.CleanupReport,
        commands: CommandLedger,
    ) -> None:
        """Retain one exact report while its local proof remains authoritative."""
        retained = control.CleanupReport.FromString(
            report.SerializeToString(deterministic=True)
        )
        command_id = retained.operation.command_id
        if not command_id:
            raise ValueError("cleanup report requires its exact terminal command")
        serialized = retained.SerializeToString(deterministic=True)
        if self.pending_cleanup_report is not None:
            pending_bytes = self.pending_cleanup_report.SerializeToString(
                deterministic=True
            )
            if pending_bytes == serialized:
                return
            raise ValueError("pending cleanup report changed after retention")
        if command_id in self.cleanup_report_history:
            raise ValueError("cleanup report command already exists in history")
        key = f"acquisition-cleanup-report:{command_id}"
        size = max(self.cleanup_reserved_bytes, retained.ByteSize() + 128)
        if not commands.has_payload(key):
            raise ValueError("terminal cleanup report was not reserved before effects")
        commands.reserve_payload(key, size, work_key=command_id, priority=True)
        if self.cleanup_local_payload_key is None:
            raise ValueError("cleanup report has no bounded current proof reservation")
        commands.reserve_payload(
            self.cleanup_local_payload_key,
            size,
            work_key=self.cleanup_local_scope,
            priority=True,
        )
        self.pending_cleanup_report = retained

    def archive_cleanup_report(self, commands: CommandLedger) -> None:
        """Keep an older report only while its originating command is retained."""
        if self.pending_cleanup_report is None:
            return
        command_id = self.pending_cleanup_report.operation.command_id
        if not commands.has_retained_work(command_id):
            self.pending_cleanup_report = None
            return
        if command_id in self.cleanup_report_history:
            raise ValueError("cleanup report history repeats an operation")
        if len(self.cleanup_report_history) >= commands.max_records:
            raise RuntimeError("cleanup attempt evidence capacity is exhausted")
        history = dict(self.cleanup_report_history)
        retained = control.CleanupReport.FromString(
            self.pending_cleanup_report.SerializeToString(deterministic=True)
        )
        commands.reserve_payload(
            f"acquisition-cleanup-report:{command_id}",
            max(retained.ByteSize() + 128, self.cleanup_reserved_bytes),
            work_key=command_id,
            priority=True,
        )
        history[command_id] = retained
        self.cleanup_report_history = history
        self.pending_cleanup_report = None

    def prune_retained_data(self, commands: CommandLedger, *, current: bool) -> int:
        """Shed expired operation payloads while preserving current cleanup proof."""
        session_id = self.work.session.session_id
        if not commands.has_retained_work(session_id):
            self.ready_report = None
            self.resolved_report = None
            self.pending_ready_report = None
            self.pending_resolution_report = None
            self.camera_resolutions.clear()
            self.expected_attachments.clear()
            self.prepared_functions.clear()
            self.confirmed_settings = None
            self.pulse_resolution = None
            self.tracking_input_report = None
            self.tracking_input_confirmation = None
            self.tracking_cleanup_confirmation = None
            self.reserved_outputs.clear()
            self.dispatched_output_keys.clear()
            self.output_results.clear()
            self.incident_revisions.clear()
            self.confirmed_incidents.clear()
            self.unavailable_resources.clear()
        if self.trial is not None and not commands.has_retained_work(
            self.trial.work.trial.trial_id
        ):
            self.trial = None
        expired = [
            command_id
            for command_id in self.cleanup_report_history
            if not commands.has_retained_work(command_id)
        ]
        for command_id in expired:
            self.cleanup_report_history.pop(command_id, None)
        pending_id = (
            self.pending_cleanup_report.operation.command_id
            if self.pending_cleanup_report is not None
            else None
        )
        if (
            not current
            and pending_id is not None
            and not commands.has_retained_work(pending_id)
        ):
            self.pending_cleanup_report = None
            self.cleanup_report_recipients.clear()
        return len(expired)

    def prepare_cleanup_command(self, command_id: str, commands: CommandLedger) -> None:
        """Reserve terminal replay evidence before any cleanup effects begin."""
        if self.cleanup_reserved_bytes <= 0 or self.cleanup_local_payload_key is None:
            raise ValueError("Setup did not reserve local cleanup proof capacity")
        commands.reserve_payload(
            f"acquisition-cleanup-report:{command_id}",
            self.cleanup_reserved_bytes,
            work_key=command_id,
            priority=True,
        )

    def handoff_cleanup_proof(self, commands: CommandLedger) -> None:
        """End current-session ownership after terminal report storage exists."""
        key = self.cleanup_local_payload_key
        if key is None:
            return
        self.cleanup_local_payload_key = None
        report = self.pending_cleanup_report
        command_id = report.operation.command_id if report is not None else ""
        retained = commands.get(command_id) if command_id else None
        if (
            retained is not None
            and retained.work_key == command_id
            and commands.has_payload(f"acquisition-cleanup-report:{command_id}")
        ):
            commands.release_payload(key)
            return
        self.pending_cleanup_report = None
        self.cleanup_report_recipients.clear()
        commands.release_payload(key)

    def reserve_cleanup_evidence(self, commands: CommandLedger) -> None:
        """Reserve bounded local cleanup proof before owner effects (E08)."""
        estimate = (
            4096
            + sum(item.ByteSize() + 2048 for item in self.cleanup_resources)
            + sum(item.ByteSize() + 16384 for item in self.reserved_outputs)
        )
        selected = max(self.cleanup_reserved_bytes, estimate)
        key = f"acquisition-cleanup-proof:{self.work.session.session_id}"
        commands.reserve_payload(
            key,
            max(1, selected),
            work_key=self.cleanup_local_scope,
            priority=True,
        )
        self.cleanup_local_payload_key = key
        self.cleanup_reserved_bytes = selected

    def release_cleanup_proof(self, commands: CommandLedger) -> None:
        """Release an unpublished Setup candidate's unused proof reservation."""
        key = self.cleanup_local_payload_key
        if key is None:
            return
        commands.release_payload(key)
        self.cleanup_local_payload_key = None

    def _reserve_session_evidence(
        self,
        commands: CommandLedger,
        *,
        output_results: dict[str, control.OutputResult] | None = None,
    ) -> None:
        outputs = self.output_results if output_results is None else output_results
        total = sum(item.ByteSize() + 128 for item in outputs.values())
        commands.reserve_payload(
            f"acquisition-session-outputs:{self.work.session.session_id}",
            max(1, total),
            work_key=self.work.session.session_id,
            priority=False,
        )
