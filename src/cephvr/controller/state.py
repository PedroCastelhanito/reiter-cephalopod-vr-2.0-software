"""Controller-owned in-memory state and limits, shared by its concrete handlers."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path

from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.incident.registry import IncidentRegistry
from cephvr.controller.metadata.reservation import OutputReservation
from cephvr.controller.metadata.types import MetadataCompletion
from cephvr.controller.metadata.writer import MetadataWriter
from cephvr.controller.ports import BackendPort
from cephvr.controller.preparation import PreparationHandoff
from cephvr.shared.incidents import IncidentTopology
from cephvr.synchronization.v1 import spikeglx_pb2 as spikeglx_pb

# Retained display/report lists (warnings, errors, recoveries) keep this many newest items.
RETAINED_LIMIT = 256


@dataclass(frozen=True)
class ControllerLimits:
    setup_ns: int
    setup_cancel_ns: int
    ready_ns: int
    finished_ns: int
    registration_ns: int
    recovery_ns: int
    metadata_ns: int
    validation_ns: int
    lead_ns: int
    controller_release_ns: int
    backend_release_ns: int
    start_evidence_ns: int
    stop_evidence_ns: int
    max_metadata_operations: int
    max_metadata_bytes: int
    history_ns: int
    space_query_ns: int
    low_space_bytes: int
    max_retained_incidents: int = 64
    max_watchers: int = 64

    def __post_init__(self) -> None:
        values = vars(self)
        if any(
            not isinstance(v, int) or v <= 0
            for k, v in values.items()
            if k != "max_watchers"
        ):
            raise ValueError("controller limits require positive exact integer values")
        if not self.lead_ns > self.controller_release_ns > self.backend_release_ns:
            raise ValueError("release offsets must be strictly ordered within lead")
        if self.max_metadata_operations < 4:
            raise ValueError(
                "metadata retention requires the three central files and one active trial file"
            )


@dataclass
class LimitsState:
    """The active immutable limit set; Setup may atomically replace it."""

    current: ControllerLimits


@dataclass
class Watch:
    client_id: str
    watch_id: str
    queue: asyncio.Queue[pb.Snapshot]
    installed_revision: int


@dataclass
class CameraOperation:
    operator_id: str
    child_id: str
    revision: int
    camera: int
    kind: int
    work: pb.WorkContext
    deadline_ns: int
    readback_required: bool
    path: str = ""
    preview_run_id: str = ""
    resolution: svc.AcquisitionResolutionReport | None = None
    confirmed: bool = False
    final_status: svc.AcquisitionDeviceStatusReport | None = None
    timed_out: bool = False
    admission_rejected: bool = False
    admission_unconfirmed: bool = False
    manual_effects_before: bool = False
    status_reservation_key: str = ""
    status_work_key: str = ""
    internal_retention: bool = False
    is_microcontroller: bool = False


@dataclass
class ConfigurationState:
    """One effective configuration and its accepted revision."""

    current: pb.ExperimentConfiguration
    policies: pb.ControlPolicies
    revision: int = 1
    validation: tuple[pb.ValidationResult, ...] = ()

    def retain_validation(
        self, results: list[pb.ValidationResult] | tuple[pb.ValidationResult, ...]
    ) -> None:
        self.validation = tuple(
            pb.ValidationResult.FromString(result.SerializeToString())
            for result in results
        )
        for result in self.validation:
            result.configuration_revision = self.revision


@dataclass
class ConfigurationEdit:
    """One E07 acquisition edit awaiting exact device readback/adoption."""

    command: svc.OperatorCommand
    command_id: str
    operation_id: str
    revision: int
    deadline_ns: int
    expected_cameras: frozenset[int]
    expect_pulses: bool
    proposed: pb.ExperimentConfiguration
    validation: tuple[pb.ValidationResult, ...] = ()
    adopted: pb.ExperimentConfiguration | None = None
    adopted_revision: int | None = None
    report: svc.AcquisitionResolutionReport | None = None
    device_status: svc.AcquisitionDeviceStatusReport | None = None
    operation_result: pb.OperationState | None = None
    confirmed: asyncio.Event = field(default_factory=asyncio.Event)
    failure: str = ""


@dataclass
class ConfigurationEditTerminal:
    """Bounded exact edit identity and device outcome, including late delivery."""

    operation_id: str
    source: pb.BackendContext
    deadline_ns: int
    device_status: svc.AcquisitionDeviceStatusReport | None = None
    device_status_late: bool = False
    operation_result: pb.OperationState | None = None
    operation_result_late: bool = False


@dataclass
class LifecycleState:
    """Authoritative session, trial, and attempt on the controller event loop."""

    session: pb.SessionState = field(
        default_factory=lambda: pb.SessionState(phase=pb.SESSION_PHASE_CONFIGURATION)
    )
    trial: pb.TrialState = field(
        default_factory=lambda: pb.TrialState(phase=pb.TRIAL_PHASE_PENDING)
    )
    attempt: Attempt | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    changed: asyncio.Condition = field(default_factory=asyncio.Condition)
    authority_lost: bool = False
    shutdown_intent_ns: int = 0
    startup_blocker: str = ""
    startup_prompt: pb.Prompt | None = None
    startup_recovery_handler: Callable[[], Awaitable[None]] | None = None
    startup_recovery_running: bool = False
    startup_warning_id: str = ""
    startup_completion_warning: str | None = None
    manual_control_cleanup_pending: bool = False
    manual_control_cleanup_task: asyncio.Task[None] | None = None
    # Set by runtime shutdown: the cleanup retry chain must not respawn.
    manual_control_cleanup_stopping: bool = False
    # A file-backed inventory replace may outlive its RPC bound. Safety and
    # health handlers remain live while Setup/config edits wait for settlement.
    inventory_update_pending: bool = False


@dataclass
class ControlState:
    """Lease, watches, and retained command outcomes."""

    revision: int = 1
    owner: tuple[str, str, str] | None = None
    watches: dict[tuple[str, str], Watch] = field(default_factory=dict)
    operations: dict[str, pb.OperationState] = field(default_factory=dict)
    operation_finished_ns: dict[str, int] = field(default_factory=dict)
    errors: list[pb.ErrorReport] = field(default_factory=list)
    warnings: list[pb.Warning] = field(default_factory=list)
    tracking_diagnostic: pb.TrackingDiagnosticState = field(
        default_factory=lambda: pb.TrackingDiagnosticState(closed=True)
    )

    def add_warning(self, component: str, message: str) -> None:
        """Retain a fresh warning; the caller publishes under its own lock."""
        self.warnings.append(
            pb.Warning(
                warning_id=str(uuid.uuid4()), component=component, message=message
            )
        )
        self.warnings = self.warnings[-RETAINED_LIMIT:]


@dataclass
class MetadataState:
    """Bounded local metadata completion and published write results."""

    max_operations: int
    results: dict[str, pb.MetadataResult] = field(default_factory=dict)
    latest_synced: dict[str, str] = field(default_factory=dict)
    completion_queue: asyncio.Queue[
        tuple[Future[MetadataCompletion], MetadataWriter, str, Path]
    ] = field(init=False)
    drain_task: asyncio.Task[object] | None = None

    def __post_init__(self) -> None:
        self.completion_queue = asyncio.Queue(maxsize=self.max_operations)


@dataclass
class SupervisorState:
    """Latest supervision observations and retained recovery evidence."""

    last_seen_ns: int
    status_revision: int = 0
    status_bytes: bytes = b""
    processes: dict[str, svc.ProcessHealthStatus] = field(default_factory=dict)
    all_processes: list[svc.ProcessHealthStatus] = field(default_factory=list)
    recoveries: list[pb.RecoveryState] = field(default_factory=list)
    controller_recoveries: list[pb.RecoveryState] = field(default_factory=list)
    operations: dict[str, pb.OperationState] = field(default_factory=dict)
    interruption_ids: dict[str, bytes] = field(default_factory=dict)
    errors: list[pb.ErrorReport] = field(default_factory=list)
    warnings: list[pb.Warning] = field(default_factory=list)


@dataclass
class IncidentState:
    """Pending operator and incident choices."""

    prompts: dict[str, tuple[pb.Prompt, asyncio.Future[str], Attempt]] = field(
        default_factory=dict
    )
    incident_prompts: dict[str, tuple[pb.Prompt, Attempt]] = field(default_factory=dict)


@dataclass
class DeviceState:
    """Pending display and camera commands."""

    display_pending: tuple[str, int, int, frozenset[str]] | None = None
    calibration_pending: tuple[str, int, int, str, int, frozenset[str]] | None = None
    calibration_blocked: bool = False
    camera_operation: CameraOperation | None = None
    camera_operations: dict[str, CameraOperation] = field(default_factory=dict)
    camera_operation_changed: asyncio.Event = field(default_factory=asyncio.Event)
    configuration_edit: ConfigurationEdit | None = None
    configuration_edit_terminals: dict[str, ConfigurationEditTerminal] = field(
        default_factory=dict
    )
    manual_effects_admitted: bool = False


@dataclass(frozen=True)
class AuthorityStatus:
    shutdown_intent_ns: int
    supervisor_last_seen_ns: int
    session_phase: pb.SessionPhase
    cleanup_confirmed: bool
    handoff_complete: bool
    work: pb.WorkContext
    activated: bool
    spikeglx_stop_unconfirmed: bool

    @classmethod
    def capture(
        cls,
        lifecycle: LifecycleState,
        control: ControlState,
        supervisor_state: SupervisorState,
    ) -> AuthorityStatus:
        attempt = lifecycle.attempt
        work = pb.WorkContext()
        if attempt is not None:
            work.session.CopyFrom(attempt.context)
        return cls(
            shutdown_intent_ns=lifecycle.shutdown_intent_ns,
            supervisor_last_seen_ns=supervisor_state.last_seen_ns,
            session_phase=lifecycle.session.phase,
            cleanup_confirmed=lifecycle.session.cleanup_confirmed,
            handoff_complete=all(
                operation.complete
                for operation in control.operations.values()
                if operation.command == "ShutdownApplication"
            ),
            work=work,
            activated=bool(attempt and attempt.activated),
            spikeglx_stop_unconfirmed=bool(
                attempt and attempt.paired and not attempt.spikeglx_stopped
            ),
        )


@dataclass
class ClosureState:
    """One attempt-owned closure (E06): finalize task and command-outcome bookkeeping."""

    task: asyncio.Task[None] | None = None
    reason: str = ""
    done: bool = False
    clean: bool = False
    start_command_id: str = ""
    metadata_written: bool = False
    # Shutdown commands whose supervisor handoff result is not yet known, and
    # the handoff failure recorded for each command that failed.
    handoff_pending: set[str] = field(default_factory=set)
    handoff_failures: dict[str, str] = field(default_factory=dict)


@dataclass
class TrialClosureState:
    """Release and normal-closure facts interruption needs for the current trial."""

    released: frozenset[str] = frozenset()
    finish_append_issued: bool = False


@dataclass
class Attempt:
    context: pb.SessionContext
    prepared: pb.PreparedSession
    reservation: OutputReservation
    required: dict[str, BackendPort]
    setup_operations: dict[str, str]
    ready: dict[str, pb.ReadyReport] = field(default_factory=dict)
    trial_ready: dict[str, pb.ReadyReport] = field(default_factory=dict)
    trial_results: dict[str, pb.OperationState] = field(default_factory=dict)
    started: dict[str, pb.StartedReport] = field(default_factory=dict)
    stopped: dict[str, pb.StoppedReport] = field(default_factory=dict)
    finished: dict[str, pb.FinishedReport] = field(default_factory=dict)
    recovered_finished: dict[tuple[str, str], pb.FinishedReport] = field(
        default_factory=dict
    )
    recovery_log_tasks: set[asyncio.Task[object]] = field(default_factory=set)
    recovery_log_failed: bool = False
    recovery_log_closed: bool = False
    writer: MetadataWriter | None = None
    trial_index: int = -1
    trial_operation: str = ""
    schedule_operations: dict[str, str] = field(default_factory=dict)
    target_ns: int = 0
    end_ns: int = 0
    activated: bool = False
    paired: bool = False
    cancel_requested: bool = False
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    cleanup: dict[str, pb.CleanupReport] = field(default_factory=dict)
    setup_deadline_ns: int = 0
    ready_deadline_ns: int = 0
    finished_deadline_ns: int = 0
    finalization_deadline_ns: int = 0
    interrupted: bool = False
    trial_task: asyncio.Task[object] | None = None
    trial_log_name: str = ""
    trial_log_finished: bool = False
    trial_log_start_task: asyncio.Task[object] | None = None
    trial_log_finish_task: asyncio.Task[object] | None = None
    start_task: asyncio.Task[object] | None = None
    interruption_issued_ns: int = 0
    overrides: list[dict[str, object]] = field(default_factory=list)
    cancelling: bool = False
    writer_closed: bool = False
    spikeglx_stopped: bool = False
    spikeglx_stop_task: asyncio.Task[bool] | None = None
    spikeglx_stop_due_ns: int = 0
    spikeglx_stop_started: bool = False
    spikeglx_stop_trial_operation: str = ""
    spikeglx_stop_trial_index: int = -1
    spikeglx_stop_trial_end_ns: int = 0
    spikeglx_stop_final_trial: bool = False
    spikeglx_recording: spikeglx_pb.SpikeGLXRecordingView = field(
        default_factory=lambda: spikeglx_pb.SpikeGLXRecordingView(
            phase=spikeglx_pb.SPIKEGLX_RECORDING_PHASE_NOT_STARTED
        )
    )
    spikeglx_monitor_stop: asyncio.Event = field(default_factory=asyncio.Event)
    handoff: PreparationHandoff | None = None
    file_policies: dict[str, Message] = field(default_factory=dict)
    registered_context: svc.RegisteredContext | None = None
    incident_topology: IncidentTopology | None = None
    incidents: IncidentRegistry | None = None
    incident_errors: dict[str, pb.ErrorReport] = field(default_factory=dict)
    incident_deadlines: dict[str, int] = field(default_factory=dict)
    incident_id_by_error: dict[str, str] = field(default_factory=dict)
    episode_deadlines: dict[tuple[str, str, str], int] = field(default_factory=dict)
    confirmed_incidents: dict[str, pb.RuntimeIncident] = field(default_factory=dict)
    scope_commands: dict[str, tuple[str, str, int]] = field(default_factory=dict)
    scope_results: dict[str, pb.OperationState] = field(default_factory=dict)
    scope_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    scope_inflight: dict[str, frozenset[str]] = field(default_factory=dict)
    cleanup_commands: dict[str, str] = field(default_factory=dict)
    cleanup_catalogue_revisions: dict[str, int] = field(default_factory=dict)
    resolution_received: svc.AcquisitionResolutionReport | None = None
    # Revision the accepted resolution was requested at; adoption bumps prepared's.
    resolution_requested_revision: int = 0
    resolution_confirmed: bool = False
    setup_command_id: str = ""
    visual_stimulus_output_ids: frozenset[str] = frozenset()
    trial_participants: dict[str, BackendPort] = field(default_factory=dict)
    unavailable_outputs: list[pb.OutputResult] = field(default_factory=list)
    recovering_evidence: str = ""
    recovery_deadline_ns: int = 0
    cancel_command_ids: list[str] = field(default_factory=list)
    abort_command_ids: list[str] = field(default_factory=list)
    shutdown_command_ids: list[str] = field(default_factory=list)
    reservation_registration_started: bool = False
    reservation_registered: bool = True
    closure: ClosureState = field(default_factory=ClosureState)
    trial_closure: TrialClosureState = field(default_factory=TrialClosureState)

    @property
    def reservation_unconfirmed(self) -> bool:
        return self.reservation_registration_started and not self.reservation_registered

    def unavailable_resources(self) -> frozenset[str]:
        return frozenset(
            key
            for incident in self.confirmed_incidents.values()
            for key in incident.affected_resources
        )

    def recovery_log_finished(self, task: asyncio.Task[object]) -> None:
        self.recovery_log_tasks.discard(task)
        if task.cancelled() or task.exception() is not None:
            self.recovery_log_failed = True
