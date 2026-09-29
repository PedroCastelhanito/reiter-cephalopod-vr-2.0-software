"""E02/E05 controller authority and experiment lifecycle.

Backends are injected registered peers. Their command admissions are never treated
as Ready, Started, Stopped or Finished evidence.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Literal, Protocol, TypeVar, cast
from zoneinfo import ZoneInfo

import grpc
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message

from cephvr.acquisition.v1 import camera_pb2 as camera_pb
from cephvr.acquisition.v1 import runtime_pb2 as acquisition_pb
from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.configuration import ControllerConfiguration
from cephvr.controller.evidence import (
    outputs_satisfied,
    started_satisfied,
    stopped_satisfied,
)
from cephvr.controller.preparation import PreparationError, PreparationHandoff
from cephvr.controller.projections import ProjectionError, ProjectionStore
from cephvr.controller.resolution import resolved_configuration
from cephvr.controller.storage import (
    MetadataCompletion,
    MetadataWrite,
    MetadataWriter,
    OutputReservation,
    StorageError,
    _atomic_json,
    _safe_component,
)
from cephvr.shared.clock import host_time_ns
from cephvr.shared.identity import require_uuid4
from cephvr.shared.incidents import (
    IncidentCapacityError,
    IncidentEvidenceError,
    IncidentRegistry,
    IncidentTopology,
    IsolationProof,
    StaleIncidentChoice,
    classify_incident,
    validate_registered_cleanup,
)
from cephvr.shared.resources import (
    ResourceCatalogueError,
    cleanup_command_fenced,
    validate_cleanup_fence_update,
)
from cephvr.synchronization.v1 import spikeglx_pb2
from cephvr.tracking.v1 import services_pb2 as tracking_svc
from cephvr.vr.v1 import runtime_pb2 as vr_pb


def _id() -> str:
    return str(uuid.uuid4())


M = TypeVar("M", bound=Message)


def _copy(message: M) -> M:
    duplicate = type(message)()
    duplicate.CopyFrom(message)
    return duplicate


def _json(message: Message) -> dict[str, object]:
    return MessageToDict(message, preserving_proto_field_name=True)


def _active_configuration_document(
    configuration: pb.ExperimentConfiguration,
) -> dict[str, object]:
    """Persist effective active settings without reusable PFS payloads or dormant values."""
    public = _copy(configuration)
    selected = [_copy(item) for item in public.backends if item.enabled]
    public.ClearField("backends")
    for setting in selected:
        if setting.backend_name == "acquisition":
            for camera in (
                setting.acquisition.behavioral,
                setting.acquisition.tracking,
            ):
                if not camera.HasField("enabled") or not camera.enabled:
                    camera.ClearField("device")
                    camera.ClearField("ffmpeg_args")
                    camera.ClearField("sdk_buffer_count")
                    camera.ClearField("recording_bit_depth")
                    camera.ClearField("save_video")
                else:
                    camera.device.ClearField("pfs_baseline")
        public.backends.add().CopyFrom(setting)
    return _json(public)


class BackendPort(Protocol):
    context: pb.BackendContext

    async def setup_session(
        self, request: svc.SetupSessionRequest
    ) -> pb.CommandAdmission: ...
    async def cancel_setup(
        self, request: svc.BackendCommand
    ) -> pb.CommandAdmission: ...
    async def prepare_trial(
        self, request: svc.PrepareTrialRequest
    ) -> pb.CommandAdmission: ...
    async def schedule_trial(
        self, request: svc.ScheduleTrialRequest
    ) -> pb.CommandAdmission: ...
    async def release_trial(
        self, request: svc.ReleaseTrialRequest
    ) -> pb.CommandAdmission: ...
    async def interrupt_session(
        self, request: svc.InterruptSessionRequest
    ) -> pb.CommandAdmission: ...
    async def cleanup(self, request: svc.BackendCommand) -> pb.CommandAdmission: ...
    async def get_state(self, request: svc.BackendQuery) -> pb.ParticipantState: ...
    async def bind_tracking_data(
        self, request: tracking_svc.TrackingDataBinding
    ) -> pb.CommandAdmission: ...
    async def confirm_tracking_input(
        self, request: svc.TrackingInputConfirmation
    ) -> pb.CommandAdmission: ...
    async def report_preview_consumer_state(
        self, request: svc.PreviewConsumerReport
    ) -> pb.ReportReceipt: ...
    async def apply_incident_scope(
        self, request: svc.IncidentScopeRequest
    ) -> pb.CommandAdmission: ...
    async def get_retained_result(
        self, request: svc.RetainedResultQuery
    ) -> svc.RetainedResult: ...
    async def confirm_configuration(
        self, request: svc.AcquisitionConfigurationConfirmation
    ) -> pb.CommandAdmission: ...
    async def initialize_display(
        self, request: svc.VRDisplayInitializationRequest
    ) -> pb.CommandAdmission: ...
    async def execute_camera_command(
        self, request: svc.AcquisitionCameraCommand
    ) -> pb.CommandAdmission: ...


class SupervisorPort(Protocol):
    async def register_context(
        self, request: svc.RegisterContextRequest
    ) -> svc.RegistrationReceipt: ...
    async def request_shutdown(
        self, request: svc.ApplicationShutdownRequest
    ) -> pb.CommandAdmission: ...
    async def report_preview_consumer_state(
        self, request: svc.PreviewConsumerReport
    ) -> pb.ReportReceipt: ...


class SpikeGLXPort(Protocol):
    async def prepare(
        self, configuration: pb.ExperimentConfiguration, session: pb.SessionContext
    ) -> spikeglx_pb2.SpikeGLXPreparation: ...
    async def verify_before_start(self) -> bool: ...
    async def start_and_verify_writing(self) -> bool: ...
    async def stop_expected_run(self) -> bool: ...


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


@dataclass
class Attempt:
    context: pb.SessionContext
    prepared: pb.PreparedSession
    reservation: OutputReservation
    required: dict[str, BackendPort]
    setup_operations: dict[str, str]
    ready: dict[str, pb.ReadyReport] = field(default_factory=dict)
    trial_ready: dict[str, pb.ReadyReport] = field(default_factory=dict)
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
    trial_log_started: bool = False
    trial_log_finished: bool = False
    trial_log_start_task: asyncio.Task[object] | None = None
    trial_log_finish_task: asyncio.Task[object] | None = None
    start_task: asyncio.Task[object] | None = None
    finalizing: bool = False
    interruption_issued_ns: int = 0
    overrides: list[dict[str, object]] = field(default_factory=list)
    cancelling: bool = False
    writer_closed: bool = False
    spikeglx_stopped: bool = False
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
    resolution_confirmed: bool = False
    setup_command_id: str = ""
    vr_output_ids: frozenset[str] = frozenset()
    trial_participants: dict[str, BackendPort] = field(default_factory=dict)
    unavailable_outputs: list[pb.OutputResult] = field(default_factory=list)
    recovering_evidence: str = ""
    recovery_deadline_ns: int = 0
    cancel_command_ids: list[str] = field(default_factory=list)
    abort_command_ids: list[str] = field(default_factory=list)
    shutdown_command_ids: list[str] = field(default_factory=list)
    reservation_registration_started: bool = False
    reservation_registered: bool = True


class ControllerRuntime:
    """One asyncio loop serializes state transitions; I/O uses bounded workers."""

    def __init__(
        self,
        *,
        generation: str,
        configuration: pb.ExperimentConfiguration,
        policies: pb.ControlPolicies | None = None,
        recording_root: Path,
        configuration_history_path: Path | None = None,
        history_warning: str | None = None,
        limits: ControllerLimits,
        validators: Mapping[
            str, Callable[[pb.ExperimentConfiguration], pb.ValidationResult]
        ],
        backends: Mapping[str, BackendPort],
        supervisor: SupervisorPort | None = None,
        supervisor_generation: str = "",
        spikeglx: SpikeGLXPort | None = None,
        output_planner: Callable[
            [pb.PreparedSession, Mapping[str, pb.ReadyReport]], list[pb.OutputPlan]
        ]
        | None = None,
        schema_factory: Callable[[pb.PreparedSession], dict[str, object]] | None = None,
        file_policies: Mapping[str, Message] | None = None,
        file_policy_loader: Callable[[frozenset[str]], Mapping[str, Message]]
        | None = None,
        settings_loader: Callable[[], ControllerConfiguration] | None = None,
        startup_settings: ControllerConfiguration | None = None,
        reservation_started: Callable[[Attempt], Awaitable[None]] | None = None,
        reservation_released: Callable[[Attempt], Awaitable[None]] | None = None,
        initial_startup_blocker: str | None = None,
        display_validator: Callable[[str], frozenset[str]] | None = None,
        max_preparation_bytes: int = 16_777_216,
        max_incident_bytes: int = 1_048_576,
        max_operation_records: int = 1024,
        health_silence_ns: int = 15_000_000_000,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.generation = generation
        self.configuration = pb.ExperimentConfiguration()
        self.configuration.CopyFrom(configuration)
        self.policies = pb.ControlPolicies()
        if policies is not None:
            self.policies.CopyFrom(policies)
        self.recording_root = recording_root
        self.configuration_history_path = configuration_history_path
        self.limits = limits
        self.validators = dict(validators)
        self.backends = dict(backends)
        self.supervisor = supervisor
        self.supervisor_generation = supervisor_generation
        self.spikeglx = spikeglx
        self.output_planner = output_planner
        self.schema_factory = schema_factory
        self.file_policies = dict(file_policies or {})
        self.file_policy_loader = file_policy_loader
        if (settings_loader is None) != (startup_settings is None):
            raise ValueError(
                "Setup settings loader requires its startup-fixed baseline"
            )
        self.settings_loader = settings_loader
        self.startup_settings = startup_settings
        self.reservation_started = reservation_started
        self.reservation_released = reservation_released
        self.display_validator = display_validator
        if max_preparation_bytes <= 0:
            raise ValueError("preparation descriptor budget must be positive")
        self.max_preparation_bytes = max_preparation_bytes
        if (
            max_incident_bytes <= 0
            or health_silence_ns <= 0
            or max_operation_records < 3
        ):
            raise ValueError("incident and health budgets must be positive")
        self.max_incident_bytes = max_incident_bytes
        self.max_operation_records = max_operation_records
        self.health_silence_ns = health_silence_ns
        self.projections = ProjectionStore(
            generation,
            {name: backend.context for name, backend in backends.items()},
            max_entries=limits.max_retained_incidents,
            max_payload_bytes=max_preparation_bytes,
        )
        self.clock = clock
        self.revision = 1
        self.configuration_revision = 1
        self.session = pb.SessionState(phase=pb.SESSION_PHASE_CONFIGURATION)
        self.trial = pb.TrialState(phase=pb.TRIAL_PHASE_PENDING)
        self.attempt: Attempt | None = None
        self._owner: tuple[str, str, str] | None = None
        self._watches: dict[tuple[str, str], Watch] = {}
        self._lock = asyncio.Lock()
        self._changed = asyncio.Condition()
        self._operations: dict[str, pb.OperationState] = {}
        self._operation_finished_ns: dict[str, int] = {}
        self._errors: list[pb.ErrorReport] = []
        self._warnings: list[pb.Warning] = []
        self._supervisor_errors: list[pb.ErrorReport] = []
        self._supervisor_warnings: list[pb.Warning] = []
        if history_warning:
            self._warnings.append(
                pb.Warning(
                    warning_id=_id(),
                    component="configuration_history",
                    message=history_warning,
                )
            )
        self._metadata: dict[str, pb.MetadataResult] = {}
        self._metadata_latest_synced: dict[str, str] = {}
        self._metadata_completion_queue: asyncio.Queue[
            tuple[Any, MetadataWriter, str, Path]
        ] = asyncio.Queue(maxsize=limits.max_metadata_operations)
        self._metadata_drain_task: asyncio.Task[object] | None = None
        self._supervisor_status_revision = 0
        self._supervisor_status_bytes = b""
        self._supervisor_last_seen_ns = self.clock()
        self._supervisor_processes: dict[str, svc.ProcessHealthStatus] = {}
        self._supervisor_all_processes: list[svc.ProcessHealthStatus] = []
        self._supervisor_recoveries: list[pb.RecoveryState] = []
        self._controller_recoveries: list[pb.RecoveryState] = []
        self._supervisor_operations: dict[str, pb.OperationState] = {}
        self._interruption_ids: dict[str, bytes] = {}
        self._prompts: dict[str, tuple[pb.Prompt, asyncio.Future[str], Attempt]] = {}
        self._incident_prompts: dict[str, tuple[pb.Prompt, Attempt]] = {}
        self._tasks: set[asyncio.Task[object]] = set()
        self._shutdown_intent_ns = 0
        self._authority_lost = False
        self._display_pending: tuple[str, int, int, frozenset[str]] | None = None
        self._camera_operation: CameraOperation | None = None
        self._startup_blocker = initial_startup_blocker or ""
        self._startup_prompt: pb.Prompt | None = None
        self._startup_recovery_handler: Callable[[], Awaitable[None]] | None = None
        self._startup_recovery_running = False
        self._startup_warning_id = _id() if initial_startup_blocker else ""
        self._startup_completion_warning: str | None = None

    def _spawn(self, coroutine: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)
        return task

    def _task_done(self, task: asyncio.Task[object]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is None:
            return
        self._warnings.append(
            pb.Warning(
                warning_id=_id(),
                component="controller",
                message=f"background operation failed: {error}",
            )
        )
        self._warnings = self._warnings[-256:]
        self._publish()
        attempt = self.attempt
        if attempt is not None and not attempt.interrupted and not self._authority_lost:
            self._spawn(
                self._interrupt(
                    attempt, f"controller background operation failed: {error}"
                )
            )

    @staticmethod
    def _recovery_log_done(attempt: Attempt, task: asyncio.Task[object]) -> None:
        attempt.recovery_log_tasks.discard(task)
        if task.cancelled() or task.exception() is not None:
            attempt.recovery_log_failed = True

    def _operation(
        self,
        command_id: str,
        name: str,
        *,
        attempt: Attempt | None = None,
        progress: str = "accepted",
        complete: bool = False,
        succeeded: bool | None = None,
        safety: Literal["ordinary", "abort", "shutdown"] = "ordinary",
    ) -> pb.OperationState:
        self._prune_operations()
        reserved = 2 if safety == "ordinary" else 1 if safety == "abort" else 0
        if len(self._operations) >= self.max_operation_records - reserved:
            raise RuntimeError("retained operation capacity exhausted")
        if command_id in self._operations:
            raise RuntimeError("operator operation ID was already retained")
        operation = pb.OperationState(
            context=pb.OperationContext(command_id=command_id),
            command=name,
            progress=progress,
            complete=complete,
        )
        if attempt is not None:
            operation.work.session.CopyFrom(attempt.context)
        if succeeded is not None:
            operation.succeeded = succeeded
        self._operations[command_id] = operation
        if complete:
            self._operation_finished_ns[command_id] = self.clock()
        return operation

    def _complete_operation(
        self, command_id: str, *, success: bool, progress: str, error: str = ""
    ) -> None:
        operation = self._operations.get(command_id)
        if operation is None or operation.complete:
            return
        operation.complete = True
        self._operation_finished_ns[command_id] = self.clock()
        operation.succeeded = success
        operation.progress = progress
        if error:
            operation.failure.CopyFrom(
                pb.Failure(code="OPERATION_FAILED", message=error)
            )

    def _prune_operations(self) -> None:
        now = self.clock()
        retention = self.policies.command_retention_after_finalization_ns
        if retention <= 0:
            return
        active_session = (
            self.attempt.context.session_id
            if self.attempt is not None and not self.session.cleanup_confirmed
            else None
        )
        for command_id, finished_ns in tuple(self._operation_finished_ns.items()):
            operation = self._operations.get(command_id)
            if operation is None:
                self._operation_finished_ns.pop(command_id, None)
            elif now - finished_ns >= retention and (
                operation.work.WhichOneof("work") != "session"
                or operation.work.session.session_id != active_session
            ):
                self._operations.pop(command_id, None)
                self._operation_finished_ns.pop(command_id, None)

    def _snapshot(self, *, include_configuration: bool = True) -> pb.Snapshot:
        view = pb.Snapshot(
            controller_generation=self.generation,
            captured_monotonic_ns=self.clock(),
            state_revision=self.revision,
        )
        view.configuration.revision = self.configuration_revision
        view.configuration.locked = self.session.phase in (
            pb.SESSION_PHASE_STARTING,
            pb.SESSION_PHASE_RUNNING,
            pb.SESSION_PHASE_FINALIZING,
            pb.SESSION_PHASE_ENDED,
        )
        if include_configuration:
            view.configuration_values.current.CopyFrom(self.configuration)
            view.configuration_values.revision = self.configuration_revision
        view.session.CopyFrom(self.session)
        view.trial.CopyFrom(self.trial)
        if self._owner is not None:
            view.control.holder_client_id = self._owner[0]
            view.control.control_generation = self._owner[2]
        view.operations.extend(self._operations.values())
        view.errors.extend((self._errors + self._supervisor_errors)[-256:])
        view.warnings.extend((self._warnings + self._supervisor_warnings)[-256:])
        if self._startup_blocker:
            view.warnings.add(
                warning_id=self._startup_warning_id,
                component="startup_recovery",
                message=self._startup_blocker,
            )
        view.recoveries.extend(
            (self._supervisor_recoveries + self._controller_recoveries)[-256:]
        )
        view.metadata.extend(self._metadata.values())
        view.prompts.extend(item[0] for item in self._prompts.values())
        view.prompts.extend(item[0] for item in self._incident_prompts.values())
        if self._startup_prompt is not None:
            view.prompts.add().CopyFrom(self._startup_prompt)
        if self.attempt is not None and self.attempt.incidents is not None:
            view.runtime_incidents.extend(self.attempt.incidents.snapshot())
        self.projections.install_public(view)
        if self.attempt is not None:
            view.reservation.session.CopyFrom(self.attempt.context)
            view.reservation.session_directory = str(
                self.attempt.reservation.session_directory
            )
            view.reservation.lock_held = self.attempt.reservation._lock_fd is not None
            view.reservation.ready_for_outputs = self.session.phase in (
                pb.SESSION_PHASE_READY,
                pb.SESSION_PHASE_STARTING,
                pb.SESSION_PHASE_RUNNING,
                pb.SESSION_PHASE_FINALIZING,
            )
            for name, backend in self.attempt.required.items():
                participant = view.participants.add()
                participant.process.role = name
                participant.process.generation = backend.context.backend_generation
                participant.enabled = True
                participant.required = True
                health = self._supervisor_processes.get(name)
                if health is not None:
                    participant.process_running = health.process_running
                    participant.connected = health.connected
                    participant.health = health.health
                    participant.software_version = health.software_version
                    participant.capabilities.extend(health.capabilities)
                    participant.protocol_package = health.protocol_package
                if name in self.attempt.ready:
                    report = self.attempt.ready[name]
                    participant.ready.context.CopyFrom(report.context)
                    participant.ready.configuration_revision = (
                        report.configuration_revision
                    )
                    participant.ready.required_checks_passed = (
                        report.required_checks_passed
                    )
        return view

    async def install_startup_recovery(
        self,
        prompt: pb.Prompt | None,
        handler: Callable[[], Awaitable[None]] | None,
        blocker: str | None,
        completion_warning: str | None = None,
    ) -> None:
        if (prompt is None) != (handler is None):
            raise ValueError(
                "startup recovery prompt and handler must be installed together"
            )
        if prompt is not None:
            if (
                not blocker
                or set(prompt.permitted_choices) != {"continue", "cancel"}
                or not prompt.HasField("setup")
                or not prompt.HasField("operation")
            ):
                raise ValueError(
                    "startup recovery requires a concrete bounded prompt and blocker"
                )
            for identity in (
                prompt.prompt_id,
                prompt.setup.controller_generation,
                prompt.setup.session_id,
                prompt.operation.command_id,
            ):
                require_uuid4(identity)
        async with self._lock:
            if (
                self._authority_lost
                or self.session.shutdown_requested
                or self._startup_recovery_running
            ):
                raise RuntimeError("startup recovery authority unavailable")
            self._startup_prompt = _copy(prompt) if prompt is not None else None
            self._startup_recovery_handler = handler
            self._startup_blocker = blocker or ""
            self._startup_warning_id = _id() if blocker else ""
            self._startup_completion_warning = completion_warning
            self._publish()

    async def snapshot(self) -> pb.Snapshot:
        async with self._lock:
            return self._snapshot()

    async def open_watch(self, client_id: str, watch_id: str) -> Watch:
        async with self._lock:
            key = (client_id, watch_id)
            if (
                not client_id
                or not watch_id
                or key in self._watches
                or len(self._watches) >= self.limits.max_watchers
            ):
                raise ValueError("watch identity unavailable")
            queue: asyncio.Queue[pb.Snapshot] = asyncio.Queue(maxsize=1)
            watch = Watch(client_id, watch_id, queue, 0)
            self._watches[key] = watch
            queue.put_nowait(self._snapshot())
            return watch

    async def delivered_watch_view(self, watch: Watch, revision: int) -> None:
        async with self._lock:
            if self._watches.get((watch.client_id, watch.watch_id)) is watch:
                watch.installed_revision = revision

    async def close_watch(self, watch: Watch) -> None:
        async with self._lock:
            self._watches.pop((watch.client_id, watch.watch_id), None)
            if self._owner is not None and self._owner[:2] == (
                watch.client_id,
                watch.watch_id,
            ):
                self._owner = None
                self._publish()

    def _publish(self) -> None:
        self.revision += 1
        for watch in self._watches.values():
            if watch.queue.full():
                watch.queue.get_nowait()
            watch.queue.put_nowait(self._snapshot())

    def _admission(
        self, command_id: str, *, error: str = "", code: str = "REJECTED"
    ) -> pb.CommandAdmission:
        if error:
            return pb.CommandAdmission(
                result=pb.COMMAND_RESULT_REJECTED,
                command_id=command_id,
                failure=pb.Failure(code=code, message=error),
            )
        return pb.CommandAdmission(
            result=pb.COMMAND_RESULT_ACCEPTED, command_id=command_id
        )

    async def claim(
        self, claim: svc.ControlClaim, *, takeover: bool = False
    ) -> pb.CommandAdmission:
        async with self._lock:
            if self._authority_lost:
                return self._admission(
                    claim.command_id, error="controller authority permanently lost"
                )
            key = (claim.client_id, claim.watch_id)
            watch = self._watches.get(key)
            if (
                claim.controller_generation != self.generation
                or watch is None
                or claim.synchronized_state_revision != watch.installed_revision
            ):
                return self._admission(
                    claim.command_id,
                    error="claim requires this client's synchronized live WatchState",
                )
            if self._owner is not None and not takeover:
                return self._admission(claim.command_id, error="control is held")
            if claim.HasField("session_id") and (
                self.attempt is None
                or claim.session_id != self.attempt.context.session_id
            ):
                return self._admission(
                    claim.command_id, error="session identity mismatch"
                )
            self._owner = (claim.client_id, claim.watch_id, _id())
            self._publish()
            return self._admission(claim.command_id)

    def _authorized(
        self,
        command: svc.OperatorCommand,
        *,
        safety: Literal["ordinary", "abort", "shutdown"] = "ordinary",
    ) -> str:
        if self._authority_lost:
            return "controller authority permanently lost"
        self._prune_operations()
        reserved = 2 if safety == "ordinary" else 1 if safety == "abort" else 0
        if len(self._operations) >= self.max_operation_records - reserved:
            return "retained operation capacity exhausted"
        if command.controller_generation != self.generation or self._owner is None:
            return "controller generation or control lease mismatch"
        if (command.operator.client_id, command.operator.control_generation) != (
            self._owner[0],
            self._owner[2],
        ):
            return "control lease mismatch"
        if (self._owner[0], self._owner[1]) not in self._watches:
            return "control subscription closed"
        if self.attempt is not None and command.HasField("expected_work"):
            work = command.expected_work
            session = (
                work.session
                if work.WhichOneof("work") == "session"
                else work.trial.session
            )
            if session != self.attempt.context:
                return "work identity mismatch"
        return ""

    async def release_control(
        self, command: svc.OperatorCommand
    ) -> pb.CommandAdmission:
        async with self._lock:
            error = self._authorized(command)
            if error:
                return self._admission(command.operator.command_id, error=error)
            self._owner = None
            self._publish()
            return self._admission(command.operator.command_id)

    async def update_configuration(
        self, request: svc.UpdateConfigurationRequest
    ) -> pb.CommandAdmission:
        command_id = request.command.operator.command_id
        async with self._lock:
            error = self._authorized(request.command)
            if (
                error
                or request.expected_revision != self.configuration_revision
                or self.session.phase
                not in (pb.SESSION_PHASE_CONFIGURATION, pb.SESSION_PHASE_READY)
            ):
                return self._admission(
                    command_id,
                    error=error or "configuration revision or phase mismatch",
                )
            revision = self.revision
            validators = tuple(self.validators.values())
            if not validators:
                return self._admission(
                    command_id, error="configuration validator unavailable"
                )
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        asyncio.to_thread(validator, request.proposed)
                        for validator in validators
                    )
                ),
                self.limits.validation_ns / 1e9,
            )
        except (TimeoutError, Exception) as exc:
            return self._admission(
                command_id, error=f"configuration validation unavailable: {exc}"
            )
        if any(not result.completed or not result.valid for result in results):
            return self._admission(command_id, error="configuration validation failed")
        async with self._lock:
            error = self._authorized(request.command)
            if (
                error
                or request.expected_revision != self.configuration_revision
                or self.revision != revision
            ):
                return self._admission(
                    command_id, error=error or "configuration changed during validation"
                )
            if request.proposed == self.configuration:
                self._operation(
                    command_id,
                    "UpdateConfiguration",
                    progress="configuration already current",
                    complete=True,
                    succeeded=True,
                )
                self._publish()
                return self._admission(command_id)
            if (
                self.session.phase == pb.SESSION_PHASE_READY
                and self.attempt is not None
            ):
                attempt = self.attempt
                attempt.cancel_requested = True
                if attempt.handoff is not None:
                    attempt.handoff.retire()
                self.session.phase = pb.SESSION_PHASE_SETTING_UP
                self._spawn(self._cancel_attempt(attempt))
            self.configuration.CopyFrom(request.proposed)
            self.configuration_revision += 1
            self._operation(
                command_id,
                "UpdateConfiguration",
                progress="configuration revision committed",
                complete=True,
                succeeded=True,
            )
            if self._display_pending is not None:
                self._complete_operation(
                    self._display_pending[0],
                    success=False,
                    progress="display initialization superseded",
                    error="configuration revision changed",
                )
                self._display_pending = None
                self.projections.expected_display = None
            self._publish()
            return self._admission(command_id)

    async def initialize_display(self) -> pb.CommandAdmission:
        """One startup V19 preparation against the adopted revision, never Setup."""
        command_id = _id()
        async with self._lock:
            backend = self.backends.get("vr")
            setting = next(
                (
                    item
                    for item in self.configuration.backends
                    if item.backend_name == "vr" and item.enabled
                ),
                None,
            )
            self._prune_operations()
            if len(self._operations) >= self.max_operation_records:
                return self._admission(
                    command_id, error="retained operation capacity exhausted"
                )
            if (
                self._authority_lost
                or self.session.shutdown_requested
                or self.session.phase != pb.SESSION_PHASE_CONFIGURATION
                or self._display_pending is not None
            ):
                return self._admission(
                    command_id,
                    error="display initialization unavailable in current phase",
                )
            if (
                backend is None
                or setting is None
                or setting.WhichOneof("settings") != "vr"
                or not setting.vr.display.profile_json
            ):
                self._warnings.append(
                    pb.Warning(
                        warning_id=_id(),
                        component="vr_display",
                        message="VR display settings or registered coordinator unavailable",
                    )
                )
                self._publish()
                return self._admission(
                    command_id, error="VR display settings or coordinator unavailable"
                )
            if self.display_validator is None or self.file_policy_loader is None:
                self._warnings.append(
                    pb.Warning(
                        warning_id=_id(),
                        component="vr_display",
                        message="display validator or file policy loader unavailable",
                    )
                )
                self._publish()
                return self._admission(
                    command_id,
                    error="display validator or file policy loader unavailable",
                )
            revision = self.configuration_revision
            display = _copy(setting.vr.display)
        try:
            output_ids, loaded = await asyncio.wait_for(
                asyncio.gather(
                    asyncio.to_thread(self.display_validator, display.profile_json),
                    asyncio.to_thread(self.file_policy_loader, frozenset({"vr"})),
                ),
                self.limits.validation_ns / 1e9,
            )
            if not output_ids or len(output_ids) > 64:
                raise ValueError(
                    "display validator returned no bounded required output identities"
                )
            policy = loaded.get("vr")
            if policy is None or policy.DESCRIPTOR != vr_pb.VRFilePolicies.DESCRIPTOR:
                raise ValueError("VR file policies unavailable")
            vr_policy = vr_pb.VRFilePolicies.FromString(policy.SerializeToString())
            if not vr_policy.HasField("limits") or not vr_policy.limits.ListFields():
                raise ValueError("VR resource limits unresolved")
        except (TimeoutError, ValueError, Exception) as exc:
            async with self._lock:
                self._warnings.append(
                    pb.Warning(
                        warning_id=_id(),
                        component="vr_display",
                        message=f"display settings unavailable: {exc}",
                    )
                )
                self._publish()
            return self._admission(
                command_id, error=f"display settings unavailable: {exc}"
            )
        async with self._lock:
            if (
                self.configuration_revision != revision
                or self.session.phase != pb.SESSION_PHASE_CONFIGURATION
                or self._authority_lost
                or self.session.shutdown_requested
            ):
                return self._admission(
                    command_id, error="display settings changed before dispatch"
                )
            deadline_ns = self.clock() + self.limits.setup_ns + self.limits.recovery_ns
            request = svc.VRDisplayInitializationRequest(
                command_id=command_id,
                issuer=pb.ProcessIdentity(
                    role="controller", generation=self.generation
                ),
                target=backend.context,
                configuration_revision=revision,
                display=display,
                limits=vr_policy.limits,
                policies=self.policies,
                deadline_monotonic_ns=deadline_ns,
            )
            self._display_pending = command_id, revision, deadline_ns, output_ids
            self.projections.expect_display(command_id, revision)
            self._operation(
                command_id, "InitializeDisplay", progress="renderer preparation pending"
            )
            self._publish()
        try:
            reply = await asyncio.wait_for(
                backend.initialize_display(request),
                max(0, (deadline_ns - self.clock()) / 1e9),
            )
            if reply.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(
                    reply.failure.message or "renderer rejected display initialization"
                )
        except Exception as exc:
            async with self._lock:
                if (
                    self._display_pending is not None
                    and self._display_pending[0] == command_id
                ):
                    self._complete_operation(
                        command_id,
                        success=False,
                        progress="display initialization admission failed",
                        error=str(exc),
                    )
                    self._display_pending = None
                    self.projections.expected_display = None
                    self._publish()
            return self._admission(command_id, error=str(exc))
        self._spawn(self._display_timeout(command_id, deadline_ns))
        return self._admission(command_id)

    async def _display_timeout(self, command_id: str, deadline_ns: int) -> None:
        await asyncio.sleep(max(0, (deadline_ns - self.clock()) / 1e9))
        async with self._lock:
            if (
                self._display_pending is not None
                and self._display_pending[0] == command_id
            ):
                self._complete_operation(
                    command_id,
                    success=False,
                    progress="display initialization evidence timed out",
                    error="exact renderer completion missing",
                )
                self._display_pending = None
                self.projections.expected_display = None
                self._publish()

    async def execute_camera_command(
        self, request: svc.CameraCommandRequest
    ) -> pb.CommandAdmission:
        operator_id = request.command.operator.command_id
        no_path = {
            svc.CAMERA_COMMAND_KIND_START_PREVIEW,
            svc.CAMERA_COMMAND_KIND_STOP_PREVIEW,
            svc.CAMERA_COMMAND_KIND_FINISH_EDITING,
            svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER,
        }
        requires_run = {
            svc.CAMERA_COMMAND_KIND_STOP_PREVIEW,
            svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER,
        }
        requires_readback = {
            svc.CAMERA_COMMAND_KIND_START_PREVIEW,
            svc.CAMERA_COMMAND_KIND_IMPORT_PFS,
            svc.CAMERA_COMMAND_KIND_EXPORT_PFS,
        }
        async with self._lock:
            error = self._authorized(request.command)
            backend = self.backends.get("acquisition")
            attached_session = (
                request.kind == svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER
                and self.session.phase == pb.SESSION_PHASE_RUNNING
            )
            if (
                error
                or self._startup_blocker
                or backend is None
                or self._camera_operation is not None
                or self.session.cleanup_blockers
                or self._authority_lost
                or self.session.shutdown_requested
                or (
                    self.session.phase != pb.SESSION_PHASE_CONFIGURATION
                    and not attached_session
                )
            ):
                return self._admission(
                    operator_id,
                    error=error
                    or self._startup_blocker
                    or "camera operation unavailable or another operation pending",
                )
            if (
                not request.HasField("expected_configuration_revision")
                or request.expected_configuration_revision
                != self.configuration_revision
                or request.camera
                not in (
                    camera_pb.CAMERA_ROLE_BEHAVIORAL,
                    camera_pb.CAMERA_ROLE_TRACKING,
                )
                or request.kind not in no_path | requires_readback
            ):
                return self._admission(
                    operator_id, error="camera command shape or revision invalid"
                )
            if (
                request.kind in no_path
                and request.HasField("path")
                or request.kind not in no_path
                and (not request.HasField("path") or not request.path)
            ):
                return self._admission(
                    operator_id, error="camera path does not match command kind"
                )
            if (
                request.kind in requires_run
                and not request.HasField("preview_run_id")
                or request.kind not in requires_run
                and request.HasField("preview_run_id")
            ):
                return self._admission(
                    operator_id,
                    error="preview run identity does not match command kind",
                )
            if request.kind == svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER:
                consumer = request.preview_consumer
                if (
                    consumer.role not in {"gui", "cli"}
                    or consumer.generation != request.command.operator.client_id
                ):
                    return self._admission(
                        operator_id,
                        error="preview consumer is not the authenticated operator client",
                    )
            elif request.HasField("preview_consumer"):
                return self._admission(
                    operator_id, error="preview consumer is only valid for attachment"
                )
            settings = next(
                (
                    item.acquisition
                    for item in self.configuration.backends
                    if item.backend_name == "acquisition" and item.enabled
                ),
                None,
            )
            if settings is None:
                return self._admission(
                    operator_id, error="acquisition settings unavailable"
                )
            camera = (
                settings.behavioral
                if request.camera == camera_pb.CAMERA_ROLE_BEHAVIORAL
                else settings.tracking
            )
            if not camera.device.device_id:
                return self._admission(
                    operator_id, error="assigned camera device ID unresolved"
                )
            current_view = (
                self.projections.devices.behavioral
                if self.projections.devices
                and request.camera == camera_pb.CAMERA_ROLE_BEHAVIORAL
                else self.projections.devices.tracking
                if self.projections.devices
                else None
            )
            if request.kind in requires_run and (
                current_view is None
                or not current_view.preview_running
                or current_view.preview_run_id != request.preview_run_id
            ):
                return self._admission(
                    operator_id, error="current preview run does not match"
                )
            if (
                request.kind == svc.CAMERA_COMMAND_KIND_START_PREVIEW
                and current_view is not None
                and current_view.preview_running
            ):
                return self._admission(operator_id, error="preview already running")
            revision = self.configuration_revision
            work = _copy(self.projections.work)
            selected = _copy(camera)
            bit_depth = (
                settings.preview_output_bit_depth
                if settings.HasField("preview_output_bit_depth")
                else None
            )
        policy: acquisition_pb.AcquisitionFilePolicies | None = None
        if request.kind != svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER:
            if self.file_policy_loader is None:
                return self._admission(
                    operator_id, error="acquisition file policies unavailable"
                )
            try:
                loaded = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.file_policy_loader, frozenset({"acquisition"})
                    ),
                    self.limits.validation_ns / 1e9,
                )
                raw = loaded.get("acquisition")
                if (
                    raw is None
                    or raw.DESCRIPTOR
                    != acquisition_pb.AcquisitionFilePolicies.DESCRIPTOR
                ):
                    raise ValueError("acquisition file policies unavailable")
                policy = acquisition_pb.AcquisitionFilePolicies.FromString(
                    raw.SerializeToString()
                )
                if (
                    len(
                        [
                            item
                            for item in policy.cameras
                            if item.camera == request.camera
                        ]
                    )
                    != 1
                ):
                    raise ValueError("camera transport policy is not unique")
            except Exception as exc:
                return self._admission(
                    operator_id, error=f"acquisition file policy unavailable: {exc}"
                )
        async with self._lock:
            error = self._authorized(request.command)
            if (
                error
                or self.configuration_revision != revision
                or self._camera_operation is not None
                or self._authority_lost
                or self.session.shutdown_requested
            ):
                return self._admission(
                    operator_id,
                    error=error or "camera operation retired before dispatch",
                )
            child_id = _id()
            deadline_ns = self.clock() + self.limits.setup_ns + self.limits.recovery_ns
            command = svc.AcquisitionCameraCommand(
                camera=request.camera,
                kind=request.kind,
                configuration_revision=revision,
            )
            command.command.command_id = child_id
            command.command.issuer.CopyFrom(
                pb.ProcessIdentity(role="controller", generation=self.generation)
            )
            command.command.target.CopyFrom(backend.context)
            command.command.work.CopyFrom(work)
            command.command.parent_operation.command_id = operator_id
            if request.HasField("path"):
                command.path = request.path
            if request.HasField("preview_run_id"):
                command.preview_run_id = request.preview_run_id
            if request.kind == svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER:
                command.preview_consumer.CopyFrom(request.preview_consumer)
                try:
                    self.projections.expect_preview(
                        child_id,
                        request.preview_consumer,
                        request.preview_run_id,
                        request.camera,
                    )
                except (ProjectionError, ValueError) as exc:
                    return self._admission(operator_id, error=str(exc))
            else:
                assert policy is not None
                command.file_policies.CopyFrom(policy)
                command.requested.CopyFrom(selected.device)
                command.transport.CopyFrom(
                    next(
                        item.transport
                        for item in policy.cameras
                        if item.camera == request.camera
                    )
                )
                if bit_depth is not None:
                    command.preview_output_bit_depth = bit_depth
            self._camera_operation = CameraOperation(
                operator_id,
                child_id,
                revision,
                request.camera,
                request.kind,
                work,
                deadline_ns,
                request.kind in requires_readback,
                request.path if request.HasField("path") else "",
                request.preview_run_id if request.HasField("preview_run_id") else "",
            )
            self._operation(
                operator_id,
                "ExecuteCameraCommand",
                attempt=self.attempt,
                progress="acquisition command pending",
            )
            self._publish()
        try:
            reply = await asyncio.wait_for(
                backend.execute_camera_command(command),
                max(0, (deadline_ns - self.clock()) / 1e9),
            )
        except Exception as exc:
            async with self._lock:
                if (
                    self._camera_operation is not None
                    and self._camera_operation.child_id == child_id
                ):
                    self._camera_operation.timed_out = True
                    self._complete_operation(
                        operator_id,
                        success=False,
                        progress="camera command admission unconfirmed",
                        error=str(exc),
                    )
                    self._publish()
            return self._admission(operator_id, error=str(exc))
        if reply.result != pb.COMMAND_RESULT_ACCEPTED:
            async with self._lock:
                if (
                    self._camera_operation is not None
                    and self._camera_operation.child_id == child_id
                ):
                    self._complete_operation(
                        operator_id,
                        success=False,
                        progress="camera command rejected",
                        error=reply.failure.message,
                    )
                    self._camera_operation = None
                    self._publish()
            return self._admission(
                operator_id,
                error=reply.failure.message or "acquisition rejected camera command",
            )
        if request.kind == svc.CAMERA_COMMAND_KIND_STOP_PREVIEW:
            self.projections.retire_preview(request.preview_run_id)
        self._spawn(self._camera_timeout(child_id, deadline_ns))
        return self._admission(operator_id)

    async def _camera_timeout(self, child_id: str, deadline_ns: int) -> None:
        await asyncio.sleep(max(0, (deadline_ns - self.clock()) / 1e9))
        async with self._lock:
            operation = self._camera_operation
            if operation is not None and operation.child_id == child_id:
                operation.timed_out = True
                self._complete_operation(
                    operation.operator_id,
                    success=False,
                    progress="camera command evidence timed out",
                    error="exact completion missing",
                )
                self._publish()

    def _required_backends(self) -> dict[str, BackendPort]:
        configured = {
            setting.backend_name
            for setting in self.configuration.backends
            if setting.enabled
        }
        if "vr" not in configured:
            raise ValueError("VR participant is required in both modes")
        local = configured - {"synchronization"}
        if (
            self.configuration.mode == pb.SESSION_MODE_CLOSED_LOOP
            and "tracking" not in local
        ):
            raise ValueError("closed-loop VR requires tracking feedback")
        if "tracking" in local and "acquisition" not in local:
            raise ValueError("tracking requires acquisition camera input")
        missing = local - self.backends.keys()
        if missing:
            raise ValueError(
                f"required backend is not registered: {', '.join(sorted(missing))}"
            )
        for name in local:
            status = self._supervisor_processes.get(name)
            backend = self.backends[name]
            if (
                status is None
                or status.process.generation != backend.context.backend_generation
                or not status.process_running
                or not status.connected
            ):
                raise ValueError(f"required backend is not operational: {name}")
        if "synchronization" in configured and self.spikeglx is None:
            raise ValueError("paired SpikeGLX adapter is unavailable")
        return {name: self.backends[name] for name in local}

    async def setup(self, command: svc.OperatorCommand) -> pb.CommandAdmission:
        command_id = command.operator.command_id
        if not self.validators:
            return self._admission(
                command_id, error="configuration validators unavailable"
            )
        async with self._lock:
            if self._startup_blocker:
                return self._admission(command_id, error=self._startup_blocker)
            proposal = _copy(self.configuration)
            expected_revision = self.configuration_revision
        active_names = frozenset(
            item.backend_name for item in proposal.backends if item.enabled
        )
        loaded_settings: ControllerConfiguration | None = None
        candidate_limits = self.limits
        if self.settings_loader is not None:
            try:
                loaded_settings = await asyncio.wait_for(
                    asyncio.to_thread(self.settings_loader),
                    self.limits.validation_ns / 1e9,
                )
                baseline = self.startup_settings
                assert baseline is not None
                if (
                    loaded_settings.controller_port != baseline.controller_port
                    or loaded_settings.supervisor_startup != baseline.supervisor_startup
                    or loaded_settings.max_message_bytes != baseline.max_message_bytes
                    or loaded_settings.max_pending_events != baseline.max_pending_events
                    or loaded_settings.max_pending_payload_bytes
                    != baseline.max_pending_payload_bytes
                    or loaded_settings.max_retained_incidents
                    != baseline.max_retained_incidents
                    or loaded_settings.limits_kwargs["max_metadata_operations"]
                    != baseline.limits_kwargs["max_metadata_operations"]
                    or loaded_settings.limits_kwargs["max_metadata_bytes"]
                    != baseline.limits_kwargs["max_metadata_bytes"]
                ):
                    return self._admission(
                        command_id,
                        error="startup-only controller settings changed; restart required",
                    )
                candidate_limits = ControllerLimits(**loaded_settings.limits_kwargs)
            except Exception as exc:
                return self._admission(
                    command_id, error=f"controller settings unavailable: {exc}"
                )
        try:
            validation = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        asyncio.to_thread(validator, proposal)
                        for validator in self.validators.values()
                    )
                ),
                self.limits.validation_ns / 1e9,
            )
        except Exception as exc:
            return self._admission(
                command_id, error=f"configuration validation unavailable: {exc}"
            )
        if any(not result.completed or not result.valid for result in validation):
            reason = next(
                (
                    result.unavailable_reason.message
                    for result in validation
                    if not result.completed and result.unavailable_reason.message
                ),
                "configuration invalid",
            )
            return self._admission(command_id, error=reason)
        try:
            file_policies = (
                dict(
                    await asyncio.wait_for(
                        asyncio.to_thread(self.file_policy_loader, active_names),
                        self.limits.validation_ns / 1e9,
                    )
                )
                if self.file_policy_loader is not None
                else dict(self.file_policies)
            )
        except Exception as exc:
            return self._admission(
                command_id, error=f"backend file policies unavailable: {exc}"
            )
        async with self._lock:
            error = self._authorized(command)
            if (
                error
                or self._startup_blocker
                or self.configuration_revision != expected_revision
                or self.session.phase != pb.SESSION_PHASE_CONFIGURATION
                or not self.session.cleanup_confirmed
                and self.attempt is not None
            ):
                return self._admission(
                    command_id,
                    error=error
                    or self._startup_blocker
                    or "Setup unavailable in current phase or blocked cleanup",
                )
            if (
                not self.configuration.HasField("mode")
                or self.configuration.mode == pb.SESSION_MODE_UNSPECIFIED
                or not self.configuration.trials
            ):
                return self._admission(
                    command_id, error="explicit mode and trial protocol required"
                )
            try:
                required = self._required_backends()
            except ValueError as exc:
                return self._admission(command_id, error=str(exc))
            if (
                not self.configuration.recording_root
                or not self.recording_root.is_dir()
            ):
                return self._admission(command_id, error="recording root unavailable")
            now = self.clock()
            try:
                from tzlocal import get_localzone_name

                zone_name = get_localzone_name()
                anchor = datetime.now(ZoneInfo(zone_name))
            except (ImportError, KeyError, ValueError) as exc:
                return self._admission(
                    command_id, error=f"IANA local timezone unavailable: {exc}"
                )
            if loaded_settings is not None:
                self.policies.CopyFrom(loaded_settings.policies)
                self.limits = candidate_limits
            context = pb.SessionContext(
                controller_generation=self.generation, session_id=_id()
            )
            prepared = pb.PreparedSession(
                context=context,
                configuration_revision=self.configuration_revision,
                configuration=self.configuration,
                policies=self.policies,
                anchor_monotonic_ns=now,
                anchor_wall_time=anchor.isoformat(),
                local_timezone=zone_name,
            )
            for index, definition in enumerate(self.configuration.trials, 1):
                if definition.trial_number != index:
                    return self._admission(
                        command_id, error="trial numbers must be ordered and one-based"
                    )
                trial_context = pb.TrialContext(
                    session=context, trial_id=_id(), trial_number=index
                )
                prepared.trials.add(context=trial_context, definition=definition)
            reservation = OutputReservation(
                self.recording_root,
                self.configuration.experiment,
                self.configuration.subject,
                context.session_id,
                self.generation,
                anchor,
            )
            prepared.session_directory = str(reservation.session_directory)
            attempt = Attempt(context, prepared, reservation, required, {})
            attempt.setup_command_id = command_id
            attempt.file_policies = file_policies
            if "tracking" in required:
                tracking_settings = next(
                    (
                        setting.tracking
                        for setting in self.configuration.backends
                        if setting.backend_name == "tracking" and setting.enabled
                    ),
                    None,
                )
                if tracking_settings is None or not tracking_settings.HasField(
                    "input_camera_role"
                ):
                    return self._admission(
                        command_id, error="tracking input camera role unresolved"
                    )
                attempt.setup_operations.update({name: _id() for name in required})
                attempt.handoff = PreparationHandoff(
                    context,
                    self.configuration_revision,
                    {name: backend.context for name, backend in required.items()},
                    attempt.setup_operations,
                    camera=tracking_settings.input_camera_role,
                    closed_loop=self.configuration.mode == pb.SESSION_MODE_CLOSED_LOOP,
                    max_payload_bytes=self.max_preparation_bytes,
                )
            attempt.setup_deadline_ns = now + self.limits.setup_ns
            attempt.paired = any(
                setting.backend_name == "synchronization" and setting.enabled
                for setting in self.configuration.backends
            )
            self.attempt = attempt
            self.session = pb.SessionState(
                phase=pb.SESSION_PHASE_SETTING_UP,
                context=context,
                directory=str(reservation.session_directory),
                trial_count=len(prepared.trials),
            )
            self.trial = pb.TrialState(phase=pb.TRIAL_PHASE_PENDING)
            self.projections.set_scope(
                pb.WorkContext(session=context), self.configuration_revision
            )
            self._operations[command_id] = pb.OperationState(
                context=pb.OperationContext(command_id=command_id),
                command="Setup",
                work=pb.WorkContext(session=context),
                progress="reserving output namespace",
            )
            self._publish()
            self._spawn(self._run_setup(attempt, command_id, attempt.setup_deadline_ns))
            return self._admission(command_id)

    async def _run_setup(
        self, attempt: Attempt, command_id: str, deadline: int
    ) -> None:
        try:
            try:
                free = await asyncio.wait_for(
                    asyncio.to_thread(
                        lambda: shutil.disk_usage(self.recording_root).free
                    ),
                    self.limits.space_query_ns / 1e9,
                )
                reason = f"recording destination has {free} free bytes"
            except (TimeoutError, OSError) as exc:
                free = None
                reason = f"recording space unknown: {exc}"
            if free is None or free < self.limits.low_space_bytes:
                choice, wait_ns = await self._setup_prompt(
                    attempt, command_id, f"{reason}; Continue or Cancel Setup"
                )
                deadline += wait_ns
                attempt.setup_deadline_ns += wait_ns
                if choice == "cancel":
                    await self._cancel_attempt(attempt)
                    return
                attempt.overrides.append(
                    {"check": "recording_space", "free_bytes": free, "reason": reason}
                )
            conflicts = await asyncio.wait_for(
                asyncio.to_thread(attempt.reservation.acquire),
                max(0, (deadline - self.clock()) / 1e9),
            )
            if conflicts:
                listed = [str(path) for path in conflicts]
                choice, wait_ns = await self._setup_prompt(
                    attempt,
                    command_id,
                    "Existing output files: "
                    + ", ".join(listed)
                    + "; Continue deletes exactly these files or Cancel preserves them",
                )
                deadline += wait_ns
                attempt.setup_deadline_ns += wait_ns
                if choice == "cancel":
                    await self._cancel_attempt(attempt)
                    return
                await asyncio.wait_for(
                    asyncio.to_thread(
                        attempt.reservation.resolve_collisions, conflicts
                    ),
                    max(0, (deadline - self.clock()) / 1e9),
                )
                attempt.overrides.append({"check": "output_conflict", "paths": listed})
            if self.reservation_started is not None:
                async with self._lock:
                    if (
                        self.attempt is not attempt
                        or attempt.cancel_requested
                        or self._authority_lost
                    ):
                        raise RuntimeError(
                            "reservation registration lost Setup authority"
                        )
                    attempt.reservation_registration_started = True
                    attempt.reservation_registered = False
                await asyncio.wait_for(
                    self.reservation_started(attempt),
                    max(0, (deadline - self.clock()) / 1e9),
                )
                async with self._lock:
                    attempt.reservation_registered = True
                    if (
                        self.attempt is not attempt
                        or attempt.cancel_requested
                        or self._authority_lost
                    ):
                        raise RuntimeError(
                            "Setup retired after reservation registration"
                        )
            if attempt.paired:
                assert self.spikeglx is not None
                preparation = await asyncio.wait_for(
                    self.spikeglx.prepare(
                        attempt.prepared.configuration, attempt.context
                    ),
                    max(0, (deadline - self.clock()) / 1e9),
                )
                anchor = datetime.fromisoformat(attempt.prepared.anchor_wall_time)
                expected_run = f"{_safe_component(attempt.prepared.configuration.experiment)}_{_safe_component(attempt.prepared.configuration.subject)}_{anchor.strftime('%Y%m%d')}_{anchor.strftime('%H%M%S')}"
                if (
                    not preparation.address.strip()
                    or not 1 <= preparation.port <= 65535
                    or preparation.run_name != expected_run
                    or not preparation.spikeglx_version
                    or not preparation.sdk_version
                    or not preparation.mapping_id
                    or not preparation.data_directory
                    or not preparation.streams
                ):
                    raise RuntimeError(
                        "SpikeGLX preparation endpoint, run identity or required readback missing"
                    )
                attempt.prepared.spikeglx.CopyFrom(preparation)
            if self.supervisor is None:
                raise RuntimeError("supervisor registration unavailable")
            initial_registration = await asyncio.wait_for(
                self.supervisor.register_context(
                    self._registration(attempt, command_id)
                ),
                max(0, (deadline - self.clock()) / 1e9),
            )
            if (
                initial_registration.admission.result != pb.COMMAND_RESULT_ACCEPTED
                or initial_registration.registered.work.session != attempt.context
            ):
                raise RuntimeError("supervisor did not register Setup work identity")
            attempt.registered_context = _copy(initial_registration.registered)
            closed_loop_handoff = (
                attempt.handoff is not None and attempt.handoff.closed_loop
            )
            for name in attempt.required:
                attempt.setup_operations.setdefault(name, _id())
            acquisition = attempt.required.get("acquisition")
            if acquisition is not None:
                response = await asyncio.wait_for(
                    acquisition.setup_session(
                        self._setup_request(
                            attempt,
                            acquisition,
                            attempt.setup_operations["acquisition"],
                        )
                    ),
                    max(0, (deadline - self.clock()) / 1e9),
                )
                if response.result != pb.COMMAND_RESULT_ACCEPTED:
                    raise RuntimeError(
                        f"acquisition rejected Setup: {response.failure.message}"
                    )
                await self._wait_evidence(
                    lambda: attempt.resolution_confirmed, deadline, attempt
                )
            initial = {
                name: backend
                for name, backend in attempt.required.items()
                if name != "acquisition" and (name != "vr" or not closed_loop_handoff)
            }
            responses = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        backend.setup_session(
                            self._setup_request(
                                attempt, backend, attempt.setup_operations[name]
                            )
                        )
                        for name, backend in initial.items()
                    )
                ),
                max(0, (deadline - self.clock()) / 1e9),
            )
            for name, response in zip(initial, responses, strict=True):
                if response.result != pb.COMMAND_RESULT_ACCEPTED:
                    raise RuntimeError(
                        f"{name} rejected Setup: {response.failure.message}"
                    )
            if attempt.handoff is not None:
                await self._complete_preparation_handoff(attempt, deadline)
            if await self._wait_lifecycle_with_recovery(
                attempt, "setup_ready", frozenset(attempt.required), deadline
            ):
                deadline += self.limits.recovery_ns
            effective = _copy(attempt.prepared.configuration)
            for name in attempt.required:
                ready = attempt.ready[name]
                current = next(
                    (item for item in effective.backends if item.backend_name == name),
                    None,
                )
                resolved = ready.resolved_settings
                if (
                    current is None
                    or not current.enabled
                    or resolved.backend_name != name
                    or not resolved.enabled
                    or resolved.WhichOneof("settings") != current.WhichOneof("settings")
                ):
                    raise RuntimeError(f"{name} Ready lacks exact resolved settings")
                current.CopyFrom(resolved)
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        asyncio.to_thread(validator, effective)
                        for validator in self.validators.values()
                    )
                ),
                max(0, (deadline - self.clock()) / 1e9),
            )
            if not results or any(
                not result.completed or not result.valid for result in results
            ):
                raise RuntimeError("resolved effective settings failed pure validation")
            attempt.prepared.configuration.CopyFrom(effective)
            vr = attempt.ready.get("vr")
            if vr is None or len(vr.resolved_trials) != len(attempt.prepared.trials):
                raise RuntimeError("VR did not provide every resolved trial")
            if self.display_validator is None:
                raise RuntimeError("display output validator unavailable")
            vr_settings = next(
                item.vr
                for item in effective.backends
                if item.backend_name == "vr" and item.enabled
            )
            attempt.vr_output_ids = await asyncio.wait_for(
                asyncio.to_thread(
                    self.display_validator, vr_settings.display.profile_json
                ),
                max(0, (deadline - self.clock()) / 1e9),
            )
            if not attempt.vr_output_ids:
                raise RuntimeError("VR resolved display has no required outputs")
            for index, resolved_trial in enumerate(vr.resolved_trials):
                if (
                    resolved_trial.context != attempt.prepared.trials[index].context
                    or resolved_trial.definition
                    != attempt.prepared.trials[index].definition
                    or not resolved_trial.HasField("resolved_duration_ns")
                    or resolved_trial.resolved_duration_ns < 60_000_000_000
                ):
                    raise RuntimeError("VR resolved duration or trial identity invalid")
                attempt.prepared.trials[index].CopyFrom(resolved_trial)
            if self.output_planner is None:
                raise RuntimeError("output reservation planner unavailable")
            outputs = self.output_planner(attempt.prepared, attempt.ready)
            if not outputs:
                raise RuntimeError("required output plan unavailable")
            for name in attempt.required:
                self._activity_requirements(attempt, name)
            seen: set[str] = set()
            for output in outputs:
                if (
                    not output.output_key
                    or output.output_key in seen
                    or output.trial.session != attempt.context
                ):
                    raise RuntimeError("output plan identity or key invalid")
                seen.add(output.output_key)
                attempt.prepared.outputs.add().CopyFrom(output)
            await self._wait_evidence(
                lambda: self._catalogues_match_ready(attempt), deadline, attempt
            )
            context_request = self._registration(attempt, command_id)
            try:
                worker_owners = self._worker_owners(attempt)
                registered_workers = frozenset(
                    worker for workers in worker_owners.values() for worker in workers
                )
                topology = IncidentTopology.from_registered(
                    context_request.context,
                    registered_workers=registered_workers,
                    worker_backend={
                        worker: name
                        for name, workers in worker_owners.items()
                        for worker in workers
                    },
                )
                zero_resources = frozenset(
                    name
                    for name in attempt.required
                    if not self._supervisor_processes[
                        name
                    ].last_heartbeat.cleanup_resources
                )
                validate_registered_cleanup(
                    context_request.context,
                    attempt.ready,
                    registered_workers=registered_workers,
                    zero_resource_backends=zero_resources,
                )
            except IncidentEvidenceError as exc:
                raise RuntimeError(f"prepared incident closure invalid: {exc}") from exc
            registration = await asyncio.wait_for(
                self.supervisor.register_context(context_request),
                max(0, (deadline - self.clock()) / 1e9),
            )
            if (
                registration.admission.result != pb.COMMAND_RESULT_ACCEPTED
                or registration.registered.work.session != attempt.context
            ):
                raise RuntimeError(
                    "supervisor did not acknowledge exact session context"
                )
            attempt.registered_context = _copy(context_request.context)
            attempt.incident_topology = topology
            attempt.incidents = IncidentRegistry(
                attempt.context,
                max_incidents=self.limits.max_retained_incidents,
                max_error_ids=256,
                max_bytes=self.max_incident_bytes,
            )
            attempt.cleanup_catalogue_revisions = {
                name: self._supervisor_processes[
                    name
                ].last_heartbeat.cleanup_resources_revision
                for name in attempt.required
            }
            async with self._lock:
                if self.attempt is not attempt or attempt.cancel_requested:
                    return
                self.session.phase = pb.SESSION_PHASE_READY
                operation = self._operations[command_id]
                operation.complete = True
                operation.succeeded = True
                operation.progress = "Ready"
                self._publish()
        except Exception as exc:
            await self._fail_setup(attempt, command_id, str(exc))

    def _setup_request(
        self, attempt: Attempt, backend: BackendPort, operation_id: str
    ) -> svc.SetupSessionRequest:
        request = svc.SetupSessionRequest()
        request.command.command_id = operation_id
        request.command.issuer.role = "controller"
        request.command.issuer.generation = self.generation
        request.command.target.CopyFrom(backend.context)
        request.command.work.session.CopyFrom(attempt.context)
        request.command.parent_operation.command_id = operation_id
        request.plan.CopyFrom(attempt.prepared)
        for setting in self.configuration.backends:
            if setting.backend_name == backend.context.backend_name:
                request.settings.CopyFrom(setting)
                break
        name = backend.context.backend_name
        if name == "acquisition":
            policy = attempt.file_policies.get(name)
            if (
                policy is None
                or policy.DESCRIPTOR != request.acquisition_policies.DESCRIPTOR
            ):
                raise RuntimeError("acquisition file policies unavailable")
            request.acquisition_policies.ParseFromString(policy.SerializeToString())
        elif name == "tracking":
            policy = attempt.file_policies.get(name)
            if (
                policy is None
                or policy.DESCRIPTOR != request.tracking_policies.DESCRIPTOR
            ):
                raise RuntimeError("tracking file policies unavailable")
            request.tracking_policies.ParseFromString(policy.SerializeToString())
        elif name == "vr":
            policy = attempt.file_policies.get(name)
            if policy is None or policy.DESCRIPTOR != request.vr_policies.DESCRIPTOR:
                raise RuntimeError("VR file policies unavailable")
            request.vr_policies.ParseFromString(policy.SerializeToString())
            if attempt.handoff is not None and attempt.handoff.closed_loop:
                tracking = attempt.handoff.tracking
                if tracking is None or not tracking.HasField("feedback"):
                    raise RuntimeError("closed-loop VR feedback descriptor unavailable")
                request.feedback_attachment.CopyFrom(tracking.feedback)
        return request

    def _catalogues_match_ready(self, attempt: Attempt) -> bool:
        for name, backend in attempt.required.items():
            health = self._supervisor_processes.get(name)
            ready = attempt.ready.get(name)
            if health is None or ready is None or not health.HasField("last_heartbeat"):
                return False
            heartbeat = health.last_heartbeat
            if (
                heartbeat.source.role != name
                or heartbeat.source.generation != backend.context.backend_generation
                or heartbeat.work.WhichOneof("work") != "session"
                or heartbeat.work.session != attempt.context
                or not heartbeat.HasField("cleanup_resources_revision")
                or tuple(
                    item.SerializeToString(deterministic=True)
                    for item in heartbeat.cleanup_resources
                )
                != tuple(
                    item.SerializeToString(deterministic=True)
                    for item in ready.cleanup_resources
                )
            ):
                return False
        return True

    def _handoff_command(
        self, attempt: Attempt, name: str, command_id: str
    ) -> svc.BackendCommand:
        request = svc.BackendCommand(command_id=command_id)
        request.issuer.role = "controller"
        request.issuer.generation = self.generation
        request.target.CopyFrom(attempt.required[name].context)
        request.work.session.CopyFrom(attempt.context)
        request.parent_operation.command_id = attempt.setup_operations[name]
        return request

    async def _complete_preparation_handoff(
        self, attempt: Attempt, deadline_ns: int
    ) -> None:
        handoff = attempt.handoff
        assert handoff is not None
        vr_sent = not handoff.closed_loop
        while True:
            async with self._lock:
                if (
                    self.attempt is not attempt
                    or attempt.cancel_requested
                    or self.session.phase != pb.SESSION_PHASE_SETTING_UP
                ):
                    raise RuntimeError("Setup handoff retired")
                action: str | None = None
                request: object | None = None
                if handoff.can_bind_input:
                    frames, tracking = handoff.frames, handoff.tracking
                    assert frames is not None and tracking is not None
                    command_id = _id()
                    handoff.input_binding_command = command_id
                    request = tracking_svc.TrackingDataBinding(
                        command=self._handoff_command(attempt, "tracking", command_id),
                        configuration_revision=attempt.prepared.configuration_revision,
                        preparation_generation=tracking.preparation_generation,
                        frames=frames,
                    )
                    action = "bind"
                elif handoff.can_confirm_input:
                    evidence = handoff.reports["tracking"]
                    command_id = _id()
                    handoff.input_confirmation_command = command_id
                    request = svc.TrackingInputConfirmation(
                        command=self._handoff_command(
                            attempt, "acquisition", command_id
                        ),
                        configuration_revision=attempt.prepared.configuration_revision,
                        tracking_evidence=evidence,
                    )
                    action = "confirm"
                elif not vr_sent and handoff.can_prepare_vr:
                    request = self._setup_request(
                        attempt, attempt.required["vr"], attempt.setup_operations["vr"]
                    )
                    vr_sent = True
                    action = "vr"
                elif (
                    handoff.input_binding_command
                    and handoff.input_confirmation_command
                    and vr_sent
                ):
                    return
            if action is None:
                vr_pending = not vr_sent

                def actionable(pending: bool = vr_pending) -> bool:
                    return (
                        handoff.can_bind_input
                        or handoff.can_confirm_input
                        or (pending and handoff.can_prepare_vr)
                    )

                await self._wait_evidence(
                    actionable,
                    deadline_ns,
                    attempt,
                )
                continue
            remaining = max(0, (deadline_ns - self.clock()) / 1e9)
            if action == "bind":
                assert isinstance(request, tracking_svc.TrackingDataBinding)
                response = await asyncio.wait_for(
                    attempt.required["tracking"].bind_tracking_data(request), remaining
                )
            elif action == "confirm":
                assert isinstance(request, svc.TrackingInputConfirmation)
                response = await asyncio.wait_for(
                    attempt.required["acquisition"].confirm_tracking_input(request),
                    remaining,
                )
            else:
                assert isinstance(request, svc.SetupSessionRequest)
                response = await asyncio.wait_for(
                    attempt.required["vr"].setup_session(request), remaining
                )
            if response.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(
                    f"{action} handoff rejected: {response.failure.message}"
                )

    async def report_data_preparation(
        self, report: svc.DataPreparationReport, ingress_ns: int
    ) -> pb.ReportReceipt:
        async with self._lock:
            attempt = self.attempt
            if (
                attempt is None
                or attempt.handoff is None
                or attempt.cancel_requested
                or self.session.phase != pb.SESSION_PHASE_SETTING_UP
                or ingress_ns > attempt.setup_deadline_ns
            ):
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(
                        code="STALE", message="no matching live Setup handoff"
                    ),
                )
            if "acquisition" in attempt.required and not attempt.resolution_confirmed:
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(
                        code="ORDER",
                        message="acquisition readback was not adopted before resource allocation",
                    ),
                )
            try:
                changed = attempt.handoff.accept(report)
            except (PreparationError, ValueError) as exc:
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(code="EVIDENCE", message=str(exc)),
                )
            if changed:
                attempt.changed.set()
            return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    async def report_acquisition_resolution(
        self, report: svc.AcquisitionResolutionReport, ingress_ns: int
    ) -> pb.ReportReceipt:
        async with self._lock:
            camera_op = self._camera_operation
            if (
                camera_op is not None
                and report.operation.command_id == camera_op.child_id
            ):
                backend = self.backends.get("acquisition")
                if (
                    not camera_op.readback_required
                    or backend is None
                    or report.source != backend.context
                    or report.work != camera_op.work
                    or ingress_ns > camera_op.deadline_ns
                    or not report.HasField("requested_configuration_revision")
                    or report.requested_configuration_revision != camera_op.revision
                ):
                    return pb.ReportReceipt(
                        result=pb.COMMAND_RESULT_REJECTED,
                        failure=pb.Failure(
                            code="EVIDENCE",
                            message="camera readback operation or deadline mismatch",
                        ),
                    )
                if camera_op.resolution is not None:
                    if camera_op.resolution.SerializeToString(
                        deterministic=True
                    ) != report.SerializeToString(deterministic=True):
                        return pb.ReportReceipt(
                            result=pb.COMMAND_RESULT_REJECTED,
                            failure=pb.Failure(
                                code="CONFLICT", message="changed camera readback"
                            ),
                        )
                    return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
                camera_op.resolution = _copy(report)
                self._spawn(self._adopt_camera_resolution(camera_op, _copy(report)))
                return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
            attempt = self.attempt
            if (
                attempt is None
                or attempt.cancel_requested
                or self.session.phase != pb.SESSION_PHASE_SETTING_UP
                or ingress_ns > attempt.setup_deadline_ns
            ):
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(
                        code="STALE", message="no live acquisition Setup resolution"
                    ),
                )
            backend = attempt.required.get("acquisition")
            if (
                backend is None
                or report.source != backend.context
                or report.work.WhichOneof("work") != "session"
                or report.work.session != attempt.context
                or report.operation.command_id
                != attempt.setup_operations.get("acquisition")
                or not report.HasField("requested_configuration_revision")
                or report.requested_configuration_revision
                != attempt.prepared.configuration_revision
            ):
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(
                        code="IDENTITY",
                        message="acquisition resolution source/work/revision mismatch",
                    ),
                )
            old = attempt.resolution_received
            if old is not None:
                if old.SerializeToString(
                    deterministic=True
                ) != report.SerializeToString(deterministic=True):
                    return pb.ReportReceipt(
                        result=pb.COMMAND_RESULT_REJECTED,
                        failure=pb.Failure(
                            code="CONFLICT", message="changed acquisition resolution"
                        ),
                    )
                return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
            attempt.resolution_received = _copy(report)
            self._spawn(self._adopt_acquisition_resolution(attempt, _copy(report)))
            return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    async def _adopt_camera_resolution(
        self, operation: CameraOperation, report: svc.AcquisitionResolutionReport
    ) -> None:
        try:
            setting = next(
                item.acquisition
                for item in self.configuration.backends
                if item.backend_name == "acquisition" and item.enabled
            )
            expected_pulses = (
                operation.kind == svc.CAMERA_COMMAND_KIND_START_PREVIEW
                and bool(setting.pulses.port)
            )
            backend = self.backends["acquisition"]
            candidate = resolved_configuration(
                self.configuration,
                report,
                source=backend.context,
                work=operation.work,
                operation_id=operation.child_id,
                revision=operation.revision,
                expected_cameras=frozenset({operation.camera}),
                expect_pulses=expected_pulses,
            )
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        asyncio.to_thread(validator, candidate)
                        for validator in self.validators.values()
                    )
                ),
                max(0, (operation.deadline_ns - self.clock()) / 1e9),
            )
            if not results or any(
                not result.completed or not result.valid for result in results
            ):
                raise RuntimeError(
                    "camera readback failed pure configuration validation"
                )
            async with self._lock:
                if (
                    self._camera_operation is not operation
                    or self.configuration_revision != operation.revision
                    or self.clock() > operation.deadline_ns
                    or self._authority_lost
                ):
                    raise RuntimeError("camera readback retired before adoption")
                if candidate != self.configuration:
                    self.configuration.CopyFrom(candidate)
                    self.configuration_revision += 1
                    self.projections.set_scope(
                        self.projections.work, self.configuration_revision
                    )
                confirmed = next(
                    item.acquisition
                    for item in candidate.backends
                    if item.backend_name == "acquisition" and item.enabled
                )
                confirmation = svc.AcquisitionConfigurationConfirmation(
                    resolution_operation=report.operation,
                    requested_configuration_revision=operation.revision,
                    confirmed_configuration_revision=self.configuration_revision,
                    confirmed=confirmed,
                )
                confirmation.command.command_id = _id()
                confirmation.command.issuer.CopyFrom(
                    pb.ProcessIdentity(role="controller", generation=self.generation)
                )
                confirmation.command.target.CopyFrom(backend.context)
                confirmation.command.work.CopyFrom(operation.work)
                confirmation.command.parent_operation.command_id = operation.child_id
                if report.HasField("pulses"):
                    confirmation.confirmed_pulses.CopyFrom(report.pulses)
                self._publish()
            reply = await asyncio.wait_for(
                backend.confirm_configuration(confirmation),
                max(0, (operation.deadline_ns - self.clock()) / 1e9),
            )
            if reply.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(
                    reply.failure.message
                    or "acquisition rejected readback confirmation"
                )
            async with self._lock:
                if (
                    self._camera_operation is operation
                    and self.clock() <= operation.deadline_ns
                ):
                    operation.confirmed = True
                    self._finish_camera_operation(operation)
                    self._publish()
        except Exception as exc:
            async with self._lock:
                if self._camera_operation is operation:
                    self._complete_operation(
                        operation.operator_id,
                        success=False,
                        progress="camera readback or confirmation failed",
                        error=str(exc),
                    )
                    self._camera_operation = None
                    self._publish()

    async def _adopt_acquisition_resolution(
        self, attempt: Attempt, report: svc.AcquisitionResolutionReport
    ) -> None:
        try:
            setting = next(
                (
                    item.acquisition
                    for item in attempt.prepared.configuration.backends
                    if item.backend_name == "acquisition" and item.enabled
                ),
                None,
            )
            if setting is None:
                raise RuntimeError("enabled acquisition settings unavailable")
            expected_cameras = frozenset(
                role
                for role, camera_settings in (
                    (camera_pb.CAMERA_ROLE_BEHAVIORAL, setting.behavioral),
                    (camera_pb.CAMERA_ROLE_TRACKING, setting.tracking),
                )
                if camera_settings.HasField("enabled") and camera_settings.enabled
            )
            if not expected_cameras:
                raise RuntimeError(
                    "acquisition Setup requires an explicit enabled camera"
                )
            requested_revision = attempt.prepared.configuration_revision
            candidate = resolved_configuration(
                attempt.prepared.configuration,
                report,
                source=attempt.required["acquisition"].context,
                work=pb.WorkContext(session=attempt.context),
                operation_id=attempt.setup_operations["acquisition"],
                revision=requested_revision,
                expected_cameras=expected_cameras,
                expect_pulses=setting.pulses.HasField("port")
                and bool(setting.pulses.port),
            )
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        asyncio.to_thread(validator, candidate)
                        for validator in self.validators.values()
                    )
                ),
                max(0, (attempt.setup_deadline_ns - self.clock()) / 1e9),
            )
            if any(not result.completed or not result.valid for result in results):
                raise RuntimeError(
                    "acquisition readback failed pure configuration validation"
                )
            async with self._lock:
                if (
                    self.attempt is not attempt
                    or attempt.cancel_requested
                    or self.configuration_revision != requested_revision
                    or self.clock() > attempt.setup_deadline_ns
                ):
                    raise RuntimeError(
                        "acquisition readback arrived after Setup or revision changed"
                    )
                if candidate != self.configuration:
                    self.configuration.CopyFrom(candidate)
                    self.configuration_revision += 1
                attempt.prepared.configuration.CopyFrom(candidate)
                attempt.prepared.configuration_revision = self.configuration_revision
                if attempt.handoff is not None:
                    attempt.handoff.revision = self.configuration_revision
                self._publish()
                confirmed = next(
                    item.acquisition
                    for item in candidate.backends
                    if item.backend_name == "acquisition" and item.enabled
                )
                confirmation = svc.AcquisitionConfigurationConfirmation(
                    command=self._handoff_command(attempt, "acquisition", _id()),
                    resolution_operation=report.operation,
                    requested_configuration_revision=requested_revision,
                    confirmed_configuration_revision=self.configuration_revision,
                    confirmed=confirmed,
                )
                if report.HasField("pulses"):
                    confirmation.confirmed_pulses.CopyFrom(report.pulses)
            reply = await asyncio.wait_for(
                attempt.required["acquisition"].confirm_configuration(confirmation),
                max(0, (attempt.setup_deadline_ns - self.clock()) / 1e9),
            )
            if reply.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(
                    f"acquisition rejected readback confirmation: {reply.failure.message}"
                )
            async with self._lock:
                if self.attempt is not attempt or attempt.cancel_requested:
                    return
                attempt.resolution_confirmed = True
                attempt.changed.set()
        except Exception as exc:
            await self._fail_setup(
                attempt, attempt.setup_command_id, f"acquisition readback: {exc}"
            )

    async def report_projection(
        self, kind: str, report: Message, ingress_ns: int | None = None
    ) -> pb.ReportReceipt:
        observed_ingress = self.clock() if ingress_ns is None else ingress_ns
        async with self._lock:
            try:
                if kind == "devices":
                    status = cast(svc.AcquisitionDeviceStatusReport, report)
                    operation = self._camera_operation
                    if (
                        operation is not None
                        and status.operation.command_id == operation.child_id
                    ):
                        if (
                            status.work != operation.work
                            or status.result.context.command_id != operation.child_id
                            or status.result.work != operation.work
                        ):
                            raise ProjectionError(
                                "camera operation result work or deadline mismatch"
                            )
                        if status.result.complete:
                            if (
                                operation.final_status is not None
                                and operation.final_status.SerializeToString(
                                    deterministic=True
                                )
                                != status.SerializeToString(deterministic=True)
                            ):
                                raise ProjectionError(
                                    "changed camera operation completion"
                                )
                    changed = self.projections.accept_devices(status)
                    if (
                        operation is not None
                        and status.operation.command_id == operation.child_id
                        and status.result.complete
                    ):
                        operation.final_status = _copy(status)
                        self._finish_camera_operation(operation)
                elif kind == "warnings":
                    changed = self.projections.accept_warnings(
                        cast(svc.AcquisitionWarningReport, report)
                    )
                elif kind == "display":
                    display_view = cast(pb.VRDisplayView, report)
                    pending = self._display_pending
                    if (
                        pending is None
                        or display_view.command_id != pending[0]
                        or observed_ingress > pending[2]
                        or self.configuration_revision != pending[1]
                    ):
                        raise ProjectionError(
                            "display result is stale or its original deadline elapsed"
                        )
                    changed = self.projections.accept_display(display_view)
                    if display_view.complete:
                        actual = {item.output_id for item in display_view.outputs}
                        successful = (
                            display_view.HasField("applied_revision")
                            and display_view.applied_revision == pending[1]
                            and actual == pending[3]
                            and len(display_view.outputs) == len(pending[3])
                            and not display_view.issues
                            and all(
                                item.HasField("resources_ready")
                                and item.resources_ready
                                and item.idle_submission
                                == vr_pb.SUBMISSION_OUTCOME_RETURNED
                                and item.HasField("idle_swap_return_ns")
                                for item in display_view.outputs
                            )
                        )
                        self._complete_operation(
                            pending[0],
                            success=successful,
                            progress="Idle output confirmed"
                            if successful
                            else "display initialization failed",
                            error="required Idle output evidence incomplete"
                            if not successful
                            else "",
                        )
                        self._display_pending = None
                elif kind == "preview":
                    changed = self.projections.accept_preview(
                        cast(svc.PreviewAttachmentReport, report)
                    )
                else:
                    raise ProjectionError("unknown projection report")
            except (ProjectionError, ValueError) as exc:
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(code="EVIDENCE", message=str(exc)),
                )
            if changed and kind != "preview":
                self._publish()
            return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    def _finish_camera_operation(self, operation: CameraOperation) -> None:
        status = operation.final_status
        if status is None or self._camera_operation is not operation:
            return
        if operation.timed_out:
            self._camera_operation = None
            return
        if not status.result.HasField("succeeded"):
            return
        if (
            status.result.succeeded
            and operation.readback_required
            and not operation.confirmed
        ):
            return
        view = (
            status.views.behavioral
            if operation.camera == camera_pb.CAMERA_ROLE_BEHAVIORAL
            else status.views.tracking
        )
        success = bool(status.result.succeeded)
        if operation.kind == svc.CAMERA_COMMAND_KIND_START_PREVIEW:
            success = (
                success
                and view.HasField("preview_running")
                and view.preview_running
                and view.HasField("preview_run_id")
                and bool(view.preview_run_id)
                and not view.cleanup_pending
            )
        elif operation.kind == svc.CAMERA_COMMAND_KIND_STOP_PREVIEW:
            success = (
                success
                and view.HasField("preview_running")
                and not view.preview_running
                and view.HasField("cleanup_pending")
                and not view.cleanup_pending
                and view.preview_run_id != operation.preview_run_id
            )
        elif operation.kind == svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER:
            transfer = self.projections.transfers.get(operation.child_id)
            if transfer is None or transfer.result is None:
                return
            success = (
                success
                and transfer.result.result == svc.PREVIEW_CONSUMER_RESULT_ATTACHED
            )
        elif operation.kind == svc.CAMERA_COMMAND_KIND_EXPORT_PFS:
            success = (
                success
                and status.HasField("exported_pfs_path")
                and status.exported_pfs_path == operation.path
            )
        elif operation.kind == svc.CAMERA_COMMAND_KIND_FINISH_EDITING:
            success = (
                success
                and view.HasField("cleanup_pending")
                and not view.cleanup_pending
                and (view.preview_running or not view.device_open)
            )
        self._complete_operation(
            operation.operator_id,
            success=success,
            progress="camera command confirmed" if success else "camera command failed",
            error="required camera result evidence incomplete" if not success else "",
        )
        self._camera_operation = None

    async def get_preview_attachment(
        self, query: svc.PreviewAttachmentQuery
    ) -> svc.PreviewAttachmentResult:
        async with self._lock:
            try:
                return self.projections.preview(query)
            except (ProjectionError, ValueError) as exc:
                return svc.PreviewAttachmentResult(
                    available=False,
                    failure=pb.Failure(code="EVIDENCE", message=str(exc)),
                )

    async def report_preview_consumer_state(
        self, report: svc.PreviewConsumerReport
    ) -> pb.ReportReceipt:
        async with self._lock:
            try:
                self.projections.preview_result(report)
            except (ProjectionError, ValueError) as exc:
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(code="EVIDENCE", message=str(exc)),
                )
        acquisition = self.backends.get("acquisition")
        if acquisition is None or self.supervisor is None:
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="UNAVAILABLE", message="preview release recipients unavailable"
                ),
            )
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    acquisition.report_preview_consumer_state(report),
                    self.supervisor.report_preview_consumer_state(report),
                ),
                self.limits.registration_ns / 1e9,
            )
        except Exception as exc:
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(code="HANDOFF", message=str(exc)),
            )
        if any(item.result != pb.COMMAND_RESULT_ACCEPTED for item in results):
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="HANDOFF",
                    message="preview consumer result was not retained by every owner",
                ),
            )
        async with self._lock:
            operation = self._camera_operation
            if (
                operation is not None
                and operation.kind == svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER
                and operation.preview_run_id == report.preview_run_id
            ):
                self._finish_camera_operation(operation)
                self._publish()
        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    def _registration(
        self, attempt: Attempt, command_id: str
    ) -> svc.RegisterContextRequest:
        request = svc.RegisterContextRequest(command_id=_id())
        request.context.controller.role = "controller"
        request.context.controller.generation = self.generation
        request.context.supervisor.role = "supervisor"
        request.context.supervisor.generation = self.supervisor_generation
        request.context.work.session.CopyFrom(attempt.context)
        request.context.operation.command_id = command_id
        request.context.required_participants.extend(
            backend.context for backend in attempt.required.values()
        )
        request.context.session_directory = str(attempt.reservation.session_directory)
        request.context.paired_spikeglx = attempt.paired
        request.context.outputs.extend(attempt.prepared.outputs)
        request.context.policies.CopyFrom(self.policies)
        worker_owners = self._worker_owners(attempt)
        for name, report in attempt.ready.items():
            owner = attempt.required[name].context
            allowed = {(name, owner.backend_generation)} | worker_owners[name]
            for function in report.prepared_functions:
                if (function.owner.role, function.owner.generation) not in allowed:
                    raise RuntimeError(
                        "Ready prepared function owner differs from registered backend"
                    )
                request.context.prepared_functions.add().CopyFrom(function)
            for resource in report.cleanup_resources:
                if (resource.owner.role, resource.owner.generation) not in allowed:
                    raise RuntimeError(
                        "Ready cleanup resource owner differs from registered backend"
                    )
                request.context.cleanup_resources.add().CopyFrom(resource)
        return request

    def _worker_owners(self, attempt: Attempt) -> dict[str, frozenset[tuple[str, str]]]:
        top_level = {
            (name, backend.context.backend_generation): name
            for name, backend in attempt.required.items()
        }
        statuses = {
            (status.process.role, status.process.generation): status
            for status in self._supervisor_all_processes
            if status.process.role
            and status.process.generation
            and status.process_running
            and status.connected
        }
        connected = [
            status
            for status in self._supervisor_all_processes
            if status.process.role
            and status.process.generation
            and status.process_running
            and status.connected
        ]
        if len(statuses) != len(connected):
            raise RuntimeError(
                "supervisor status repeats an operational process identity"
            )
        result: dict[str, set[tuple[str, str]]] = {
            name: set() for name in attempt.required
        }
        for identity, status in statuses.items():
            if identity in top_level:
                continue
            visited = {identity}
            current = status
            while current.HasField("launch_owner"):
                parent = (current.launch_owner.role, current.launch_owner.generation)
                if parent in visited:
                    raise RuntimeError("supervisor worker ancestry contains a cycle")
                if parent in top_level:
                    result[top_level[parent]].add(identity)
                    break
                visited.add(parent)
                next_status = statuses.get(parent)
                if next_status is None:
                    break
                current = next_status
        return {name: frozenset(workers) for name, workers in result.items()}

    def _registered_workers(self, attempt: Attempt) -> frozenset[tuple[str, str]]:
        return frozenset(
            worker
            for workers in self._worker_owners(attempt).values()
            for worker in workers
        )

    async def _wait_evidence(
        self, predicate: Callable[[], bool], deadline_ns: int, attempt: Attempt
    ) -> None:
        while True:
            async with self._lock:
                if self.attempt is not attempt or attempt.cancel_requested:
                    raise RuntimeError("attempt retired")
                remaining = (deadline_ns - self.clock()) / 1e9
                if remaining < 0:
                    break
                if predicate():
                    return
                attempt.changed.clear()
                if remaining <= 0:
                    break
            try:
                await asyncio.wait_for(attempt.changed.wait(), remaining)
            except TimeoutError:
                break
        raise TimeoutError("required lifecycle evidence missing by deadline")

    async def _wait_lifecycle_with_recovery(
        self,
        attempt: Attempt,
        kind: Literal["setup_ready", "trial_ready", "finished"],
        expected: frozenset[str],
        initial_deadline_ns: int,
        *,
        closure_only: bool = False,
    ) -> bool:
        def received_names() -> set[str]:
            if kind == "setup_ready":
                return set(attempt.ready)
            if kind == "trial_ready":
                return set(attempt.trial_ready)
            return set(attempt.finished)

        def predicate() -> bool:
            return expected <= received_names()

        try:
            await self._wait_evidence(predicate, initial_deadline_ns, attempt)
            return False
        except TimeoutError as exc:
            initial_error = exc
        recovery_deadline_ns = initial_deadline_ns + self.limits.recovery_ns
        if closure_only:
            if (
                kind != "finished"
                or not attempt.interrupted
                or not attempt.finalization_deadline_ns
            ):
                raise initial_error
            recovery_deadline_ns = min(
                recovery_deadline_ns, attempt.finalization_deadline_ns
            )
        async with self._lock:
            if (
                self.attempt is not attempt
                or attempt.interrupted
                and not closure_only
                or attempt.cancel_requested
                or self.clock() >= recovery_deadline_ns
                or kind == "setup_ready"
                and self.session.phase != pb.SESSION_PHASE_SETTING_UP
                or kind == "trial_ready"
                and self.trial.phase != pb.TRIAL_PHASE_PREPARING
                or kind == "finished"
                and self.trial.phase != pb.TRIAL_PHASE_FINALIZING
            ):
                raise initial_error
            missing = frozenset(expected - received_names())
            attempt.recovering_evidence = kind
            attempt.recovery_deadline_ns = recovery_deadline_ns
            self._warnings.append(
                pb.Warning(
                    warning_id=_id(),
                    component="lifecycle_recovery",
                    message=f"{kind} initial evidence deadline expired; querying the frozen missing set",
                )
            )
            self._warnings = self._warnings[-256:]
            self._publish()

        async def query(name: str) -> None:
            backend = attempt.required[name]
            work = (
                pb.WorkContext(session=attempt.context)
                if kind == "setup_ready"
                else pb.WorkContext(
                    trial=attempt.prepared.trials[attempt.trial_index].context
                )
            )
            command_id = (
                attempt.setup_operations[name]
                if kind == "setup_ready"
                else attempt.trial_operation
            )
            request = svc.RetainedResultQuery(
                query=svc.BackendQuery(target=backend.context, work=work),
                command_id=command_id,
            )
            try:
                retained = await asyncio.wait_for(
                    backend.get_retained_result(request),
                    max(0, (recovery_deadline_ns - self.clock()) / 1e9),
                )
                if (
                    not retained.found
                    or retained.backend != backend.context
                    or retained.work != work
                ):
                    return
                if kind == "finished":
                    if retained.finished.context.operation.command_id != command_id:
                        return
                    lifecycle = pb.LifecycleReport(finished=retained.finished)
                else:
                    if retained.ready.context.operation.command_id != command_id:
                        return
                    lifecycle = pb.LifecycleReport(ready=retained.ready)
                await self.report_lifecycle(lifecycle, self.clock())
            except (TimeoutError, Exception):
                return

        try:
            await asyncio.gather(*(query(name) for name in missing))
            await self._wait_evidence(predicate, recovery_deadline_ns, attempt)
            return True
        except TimeoutError as exc:
            raise TimeoutError(
                f"{kind} missing after one bounded recovery query"
            ) from exc
        finally:
            async with self._lock:
                if self.attempt is attempt and attempt.recovering_evidence == kind:
                    attempt.recovering_evidence = ""
                    attempt.recovery_deadline_ns = 0

    async def _fail_setup(self, attempt: Attempt, command_id: str, error: str) -> None:
        async with self._lock:
            if self.attempt is not attempt:
                return
            attempt.cancel_requested = True
            if attempt.handoff is not None:
                attempt.handoff.retire()
            operation = self._operations[command_id]
            operation.complete = True
            operation.succeeded = False
            operation.failure.CopyFrom(pb.Failure(code="SETUP_FAILED", message=error))
            self._warnings.append(
                pb.Warning(warning_id=_id(), component="controller", message=error)
            )
            self._publish()
        await self._cancel_attempt(attempt)

    async def _setup_prompt(
        self, attempt: Attempt, command_id: str, explanation: str
    ) -> tuple[str, int]:
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        prompt = pb.Prompt(
            prompt_id=_id(),
            setup=attempt.context,
            operation=pb.OperationContext(command_id=command_id),
            explanation=explanation,
            permitted_choices=["continue", "cancel"],
        )
        async with self._lock:
            if self.attempt is not attempt or attempt.cancel_requested:
                raise RuntimeError("Setup attempt retired")
            self._prompts[prompt.prompt_id] = (prompt, future, attempt)
            self._publish()
        since = self.clock()
        try:
            choice = await future
        finally:
            async with self._lock:
                self._prompts.pop(prompt.prompt_id, None)
                self._publish()
        return choice, self.clock() - since

    async def respond_to_prompt(
        self, request: svc.PromptResponse
    ) -> pb.CommandAdmission:
        command_id = request.command.operator.command_id
        async with self._lock:
            error = self._authorized(request.command)
            startup_prompt = self._startup_prompt
            if (
                startup_prompt is not None
                and request.prompt_id == startup_prompt.prompt_id
            ):
                if (
                    error
                    or self.session.shutdown_requested
                    or self._startup_recovery_running
                    or self._startup_recovery_handler is None
                    or request.setup != startup_prompt.setup
                    or request.setup_operation != startup_prompt.operation
                    or request.HasField("expected_incident_revision")
                    or request.choice not in startup_prompt.permitted_choices
                ):
                    return self._admission(
                        command_id,
                        error=error
                        or "startup recovery prompt identity, state or choice mismatch",
                    )
                operation = self._operation(
                    command_id,
                    "StartupRecovery",
                    progress="reservation recovery accepted",
                    complete=request.choice == "cancel",
                    succeeded=True if request.choice == "cancel" else None,
                )
                operation.work.session.CopyFrom(startup_prompt.setup)
                if request.choice == "cancel":
                    operation.progress = (
                        "recovery deferred; reservation and blocker preserved"
                    )
                else:
                    self._startup_recovery_running = True
                    self._spawn(
                        self._run_startup_recovery(
                            command_id, self._startup_recovery_handler
                        )
                    )
                self._publish()
                return self._admission(command_id)
            incident_item = self._incident_prompts.get(request.prompt_id)
            if incident_item is not None:
                prompt, owner = incident_item
                if (
                    error
                    or owner is not self.attempt
                    or owner.incidents is None
                    or request.setup != owner.context
                    or request.setup_operation != prompt.operation
                    or not request.HasField("expected_incident_revision")
                    or request.choice not in prompt.permitted_choices
                ):
                    return self._admission(
                        command_id,
                        error=error
                        or "runtime incident prompt identity or choice mismatch",
                    )
                try:
                    updated = owner.incidents.choose(
                        prompt.runtime_incident.incident_id,
                        request.expected_incident_revision,
                        cast(
                            Literal["continue_session", "abort_session", "acknowledge"],
                            request.choice,
                        ),
                        session_active=self.session.phase
                        in (pb.SESSION_PHASE_STARTING, pb.SESSION_PHASE_RUNNING),
                    )
                except (StaleIncidentChoice, IncidentCapacityError) as exc:
                    return self._admission(command_id, error=str(exc))
                self._incident_prompts.pop(request.prompt_id, None)
                owner.changed.set()
                self._publish()
                if owner.writer is not None:
                    self._spawn(
                        self._incident_log(
                            owner,
                            "incident_decision",
                            {
                                "incident_id": updated.incident_id,
                                "incident_revision": updated.revision,
                                "choice": request.choice,
                                "client_id": request.command.operator.client_id,
                                "affected_resources": list(updated.affected_resources),
                            },
                        )
                    )
                if request.choice == "abort_session":
                    self._spawn(
                        self._interrupt(
                            owner, f"operator aborted incident {updated.incident_id}"
                        )
                    )
                self._operation(
                    command_id,
                    "RespondToPrompt",
                    attempt=owner,
                    progress="runtime incident choice retained",
                    complete=True,
                    succeeded=True,
                )
                self._publish()
                return self._admission(command_id)
            item = self._prompts.get(request.prompt_id)
            if error or item is None:
                return self._admission(command_id, error=error or "prompt unavailable")
            prompt, future, attempt = item
            if (
                attempt is not self.attempt
                or request.setup != attempt.context
                or request.setup_operation != prompt.operation
                or request.choice not in prompt.permitted_choices
                or future.done()
            ):
                return self._admission(
                    command_id, error="prompt choice or Setup identity mismatch"
                )
            future.set_result(request.choice)
            self._operation(
                command_id,
                "RespondToPrompt",
                attempt=attempt,
                progress="Setup prompt choice retained",
                complete=True,
                succeeded=True,
            )
            self._publish()
            return self._admission(command_id)

    async def _run_startup_recovery(
        self, command_id: str, handler: Callable[[], Awaitable[None]]
    ) -> None:
        error = ""
        try:
            await asyncio.wait_for(
                handler(), (self.limits.setup_cancel_ns + self.limits.recovery_ns) / 1e9
            )
        except Exception as exc:
            error = str(exc)
        async with self._lock:
            self._startup_recovery_running = False
            if self._authority_lost or self.session.shutdown_requested:
                error = (
                    error
                    or "controller authority or shutdown changed during startup recovery"
                )
            if error:
                self._complete_operation(
                    command_id,
                    success=False,
                    progress="startup recovery remains blocked",
                    error=error,
                )
                self._warnings.append(
                    pb.Warning(
                        warning_id=_id(), component="startup_recovery", message=error
                    )
                )
            else:
                self._complete_operation(
                    command_id,
                    success=True,
                    progress="startup reservation recovery confirmed",
                )
                self._startup_blocker = ""
                self._startup_prompt = None
                self._startup_recovery_handler = None
                self._startup_warning_id = ""
                if self._startup_completion_warning:
                    self._warnings.append(
                        pb.Warning(
                            warning_id=_id(),
                            component="startup_recovery",
                            message=self._startup_completion_warning,
                        )
                    )
                self._startup_completion_warning = None
                if self.attempt is None:
                    self.session.cleanup_confirmed = True
            self._warnings = self._warnings[-256:]
            self._publish()

    async def _release_reservation_pointer(
        self, attempt: Attempt, deadline_ns: int
    ) -> bool:
        if (
            self._authority_lost
            or attempt.reservation_registration_started
            and not attempt.reservation_registered
        ):
            return False
        if (
            not attempt.reservation_registration_started
            or self.reservation_released is None
        ):
            return True
        try:
            await asyncio.wait_for(
                self.reservation_released(attempt),
                max(0, (deadline_ns - self.clock()) / 1e9),
            )
            return True
        except Exception as exc:
            async with self._lock:
                self._warnings.append(
                    pb.Warning(
                        warning_id=_id(),
                        component="reservation",
                        message=f"durable reservation release unconfirmed: {exc}",
                    )
                )
                self._warnings = self._warnings[-256:]
                self._publish()
            return False

    async def _cancel_attempt(self, attempt: Attempt) -> None:
        async with self._lock:
            if attempt.cancelling:
                return
            attempt.cancelling = True
        deadline = self.clock() + self.limits.setup_cancel_ns
        clean = True
        try:
            requests = {
                name: self._backend_command(attempt, backend)
                for name, backend in attempt.required.items()
            }
            attempt.cleanup_commands.update(
                {name: request.command_id for name, request in requests.items()}
            )
            clean = (
                await self._register_cleanup_fences(attempt, requests, deadline)
                if not self._authority_lost
                else False
            )
            if clean or self._authority_lost:
                results = await asyncio.wait_for(
                    asyncio.gather(
                        *(
                            backend.cancel_setup(requests[name])
                            for name, backend in attempt.required.items()
                        ),
                        return_exceptions=True,
                    ),
                    max(0, (deadline - self.clock()) / 1e9),
                )
                clean = (
                    all(
                        isinstance(result, pb.CommandAdmission)
                        and result.result == pb.COMMAND_RESULT_ACCEPTED
                        for result in results
                    )
                    and clean
                )
        except TimeoutError:
            clean = False
        if attempt.setup_operations:
            clean = await self._await_cleanups(attempt, deadline) and clean
        if (
            attempt.reservation_registration_started
            and not attempt.reservation_registered
        ):
            clean = False
        if (
            clean
            and not self._authority_lost
            and attempt.reservation._lock_fd is not None
        ):
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(attempt.reservation.cancel),
                    max(0, (deadline + self.limits.recovery_ns - self.clock()) / 1e9),
                )
                clean = await self._release_reservation_pointer(
                    attempt, deadline + self.limits.recovery_ns
                )
            except (StorageError, OSError) as exc:
                clean = False
                self._warnings.append(
                    pb.Warning(
                        warning_id=_id(), component="reservation", message=str(exc)
                    )
                )
            except TimeoutError:
                clean = False
        async with self._lock:
            if self.attempt is attempt:
                self.session = pb.SessionState(
                    phase=pb.SESSION_PHASE_CONFIGURATION,
                    cleanup_confirmed=clean and not self._authority_lost,
                    shutdown_requested=bool(self._shutdown_intent_ns),
                )
                self.trial = pb.TrialState(phase=pb.TRIAL_PHASE_PENDING)
                for command_id in (
                    attempt.cancel_command_ids
                    + attempt.abort_command_ids
                    + attempt.shutdown_command_ids
                ):
                    self._complete_operation(
                        command_id,
                        success=clean and not self._authority_lost,
                        progress="cleanup confirmed"
                        if clean and not self._authority_lost
                        else "cleanup evidence blocked",
                        error="cleanup could not be confirmed"
                        if not clean or self._authority_lost
                        else "",
                    )
                if clean:
                    self.attempt = None
                self._publish()

    async def _await_cleanups(self, attempt: Attempt, initial_deadline_ns: int) -> bool:
        expected = set(attempt.setup_operations)
        while self.clock() < initial_deadline_ns:
            async with self._lock:
                if expected <= attempt.cleanup.keys():
                    return True
                attempt.changed.clear()
            try:
                await asyncio.wait_for(
                    attempt.changed.wait(),
                    max(0, (initial_deadline_ns - self.clock()) / 1e9),
                )
            except TimeoutError:
                break
        missing = expected - attempt.cleanup.keys()
        recovery_deadline = initial_deadline_ns + self.limits.recovery_ns

        async def query(name: str) -> None:
            backend = attempt.required[name]
            request = svc.BackendQuery(
                target=backend.context, work=pb.WorkContext(session=attempt.context)
            )
            try:
                state = await asyncio.wait_for(
                    backend.get_state(request),
                    max(0, (recovery_deadline - self.clock()) / 1e9),
                )
                if state.HasField("cleanup"):
                    await self.report_lifecycle(
                        pb.LifecycleReport(cleanup=state.cleanup), self.clock()
                    )
            except (TimeoutError, Exception):
                return

        await asyncio.gather(*(query(name) for name in missing))
        return expected <= attempt.cleanup.keys()

    def _backend_command(
        self, attempt: Attempt, backend: BackendPort
    ) -> svc.BackendCommand:
        request = svc.BackendCommand(command_id=_id())
        request.issuer.role = "controller"
        request.issuer.generation = self.generation
        request.target.CopyFrom(backend.context)
        request.work.session.CopyFrom(attempt.context)
        return request

    async def _register_cleanup_fences(
        self,
        attempt: Attempt,
        requests: Mapping[str, svc.BackendCommand],
        deadline_ns: int,
    ) -> bool:
        previous = attempt.registered_context
        if previous is None or self.supervisor is None:
            return False
        updated = _copy(previous)
        for name, request in requests.items():
            updated.cleanup_commands.add(
                target=pb.ProcessIdentity(
                    role=name,
                    generation=attempt.required[name].context.backend_generation,
                ),
                work=request.work,
                operation=pb.OperationContext(command_id=request.command_id),
            )
        try:
            validate_cleanup_fence_update(
                previous, updated, max_fences=256, max_bytes=self.max_incident_bytes
            )
            receipt = await asyncio.wait_for(
                self.supervisor.register_context(
                    svc.RegisterContextRequest(command_id=_id(), context=updated)
                ),
                max(0, (deadline_ns - self.clock()) / 1e9),
            )
            if (
                receipt.admission.result != pb.COMMAND_RESULT_ACCEPTED
                or receipt.registered != updated
            ):
                return False
            attempt.registered_context = _copy(updated)
            return True
        except (ResourceCatalogueError, TimeoutError, Exception):
            return False

    async def cancel_setup(self, command: svc.OperatorCommand) -> pb.CommandAdmission:
        async with self._lock:
            error = self._authorized(command)
            attempt = self.attempt
            if (
                error
                or attempt is None
                or self.session.phase
                not in (pb.SESSION_PHASE_SETTING_UP, pb.SESSION_PHASE_READY)
            ):
                return self._admission(
                    command.operator.command_id,
                    error=error or "Cancel Setup unavailable",
                )
            attempt.cancel_requested = True
            attempt.cancel_command_ids.append(command.operator.command_id)
            self._operation(
                command.operator.command_id,
                "CancelSetup",
                attempt=attempt,
                progress="bounded cleanup in progress",
            )
            if attempt.handoff is not None:
                attempt.handoff.retire()
            for _prompt, future, owner in self._prompts.values():
                if owner is attempt and not future.done():
                    future.cancel()
            self._spawn(self._cancel_attempt(attempt))
            return self._admission(command.operator.command_id)

    def _activity_requirements(
        self, attempt: Attempt, name: str
    ) -> tuple[
        frozenset[int],
        frozenset[int],
        frozenset[str],
        frozenset[str],
        frozenset[tuple[str, str]],
    ]:
        ready = attempt.ready.get(name)
        if ready is None:
            raise RuntimeError("required backend lacks frozen Setup Ready evidence")
        affected = {
            key
            for incident in attempt.confirmed_incidents.values()
            for key in incident.affected_resources
        }
        declared = {
            source
            for item in ready.prepared_functions
            for source in item.lifecycle_sources
        }
        active = {
            source
            for item in ready.prepared_functions
            if item.resource_id not in affected
            for source in item.lifecycle_sources
        }
        producers = {
            (reporter.role, reporter.generation)
            for item in ready.prepared_functions
            if item.resource_id not in affected and item.lifecycle_sources
            for reporter in item.authorized_reporters
        }
        if name == "acquisition":
            settings = next(
                (
                    item.acquisition
                    for item in attempt.prepared.configuration.backends
                    if item.backend_name == name and item.enabled
                ),
                None,
            )
            if settings is None:
                raise RuntimeError("acquisition resolved settings missing")
            selected = {
                camera_pb.CAMERA_ROLE_BEHAVIORAL: settings.behavioral,
                camera_pb.CAMERA_ROLE_TRACKING: settings.tracking,
            }
            configured = {
                "behavioral" if role == camera_pb.CAMERA_ROLE_BEHAVIORAL else "tracking"
                for role, camera in selected.items()
                if camera.HasField("enabled") and camera.enabled
            }
            if declared != configured:
                raise RuntimeError(
                    "acquisition lifecycle source declaration differs from enabled cameras"
                )
            roles = frozenset(
                role
                for role, camera in selected.items()
                if camera.HasField("enabled")
                and camera.enabled
                and (
                    "behavioral"
                    if role == camera_pb.CAMERA_ROLE_BEHAVIORAL
                    else "tracking"
                )
                in active
            )
            external = frozenset(
                role
                for role in roles
                if selected[role].device.frame_timing
                == camera_pb.FRAME_TIMING_EXTERNAL_TRIGGER
            )
            sources = frozenset(
                "behavioral" if role == camera_pb.CAMERA_ROLE_BEHAVIORAL else "tracking"
                for role in roles
            )
            return roles, external, frozenset(), sources, frozenset(producers)
        if name == "vr":
            if declared != {"renderer"} or "renderer" not in active:
                raise RuntimeError("essential VR renderer lifecycle source unavailable")
            return (
                frozenset(),
                frozenset(),
                attempt.vr_output_ids,
                frozenset(active),
                frozenset(producers),
            )
        if name == "tracking":
            if declared != {"tracking"}:
                raise RuntimeError("tracking lifecycle source declaration missing")
            return (
                frozenset(),
                frozenset(),
                frozenset(),
                frozenset(active),
                frozenset(producers),
            )
        raise RuntimeError("backend has no declared activity evidence semantics")

    def _activity_backends(self, attempt: Attempt) -> frozenset[str]:
        return frozenset(
            name
            for name in attempt.trial_participants
            if bool(self._activity_requirements(attempt, name)[3])
        )

    def _source_producers(
        self, attempt: Attempt, name: str
    ) -> dict[str, tuple[str, str]]:
        ready = attempt.ready[name]
        affected = {
            key
            for incident in attempt.confirmed_incidents.values()
            for key in incident.affected_resources
        }
        sources: dict[str, tuple[str, str]] = {}
        for function in ready.prepared_functions:
            if function.resource_id in affected:
                continue
            for source in function.lifecycle_sources:
                if (
                    source in sources
                    or len(function.authorized_reporters) > 1
                    or name == "acquisition"
                    and len(function.authorized_reporters) != 1
                ):
                    raise RuntimeError(
                        "lifecycle source lacks one exact registered producer"
                    )
                reporter = (
                    function.authorized_reporters[0]
                    if function.authorized_reporters
                    else function.owner
                )
                sources[source] = (reporter.role, reporter.generation)
        return sources

    def _select_trial_participants(
        self, attempt: Attempt, plan: pb.TrialPlan
    ) -> dict[str, BackendPort]:
        affected = {
            key
            for incident in attempt.confirmed_incidents.values()
            for key in incident.affected_resources
        }
        participants: dict[str, BackendPort] = {}
        for name, backend in attempt.required.items():
            declared = {
                item.resource_id for item in attempt.ready[name].prepared_functions
            }
            expected_outputs = {
                item.output_key
                for item in attempt.prepared.outputs
                if item.trial == plan.context and item.backend.backend_name == name
            }
            if not declared or declared - affected:
                participants[name] = backend
                continue
            if name == "vr" or not expected_outputs <= affected:
                raise RuntimeError(
                    f"{name} has unavailable functions without a safe trial omission"
                )
        return participants

    async def report_lifecycle(
        self, report: pb.LifecycleReport, ingress_ns: int
    ) -> pb.ReportReceipt:
        kind = report.WhichOneof("report")
        if kind is None:
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(code="INVALID", message="empty lifecycle report"),
            )
        payload = getattr(report, kind)
        context = payload.context if kind not in {"cleanup", "operation"} else None
        async with self._lock:
            attempt = self.attempt
            if attempt is None:
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(code="STALE", message="no matching live work"),
                )
            if kind == "operation":
                operation = payload.operation
                expected_scope = attempt.scope_commands.get(
                    operation.context.command_id
                )
                backend = attempt.required.get(payload.source.backend_name)
                if (
                    expected_scope is None
                    or backend is None
                    or payload.source != backend.context
                    or expected_scope[0] != payload.source.backend_name
                    or operation.work.WhichOneof("work") != "session"
                    or operation.work.session != attempt.context
                    or not operation.complete
                ):
                    return pb.ReportReceipt(
                        result=pb.COMMAND_RESULT_REJECTED,
                        failure=pb.Failure(
                            code="EVIDENCE",
                            message="unexpected backend operation result",
                        ),
                    )
                prior = attempt.scope_results.get(operation.context.command_id)
                if prior is not None and prior.SerializeToString(
                    deterministic=True
                ) != operation.SerializeToString(deterministic=True):
                    return pb.ReportReceipt(
                        result=pb.COMMAND_RESULT_REJECTED,
                        failure=pb.Failure(
                            code="CONFLICT",
                            message="changed backend operation completion",
                        ),
                    )
                attempt.scope_results[operation.context.command_id] = _copy(operation)
                attempt.changed.set()
                return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
            if kind == "cleanup":
                name = payload.source.role
                backend = attempt.required.get(name)
                registered = attempt.registered_context
                health = self._supervisor_processes.get(name)
                heartbeat = (
                    health.last_heartbeat
                    if health is not None and health.HasField("last_heartbeat")
                    else None
                )
                catalogued = (
                    heartbeat is not None
                    and heartbeat.source == payload.source
                    and heartbeat.work.WhichOneof("work") == "session"
                    and heartbeat.work.session == attempt.context
                    and heartbeat.HasField("cleanup_resources_revision")
                )
                obligations = {
                    resource.resource: resource
                    for resource in (
                        attempt.ready[name].cleanup_resources
                        if attempt.incident_topology is not None
                        and name in attempt.ready
                        else heartbeat.cleanup_resources
                        if catalogued and heartbeat is not None
                        else ()
                    )
                }
                source_obligations = (
                    attempt.ready[name].cleanup_resources
                    if attempt.incident_topology is not None and name in attempt.ready
                    else heartbeat.cleanup_resources
                    if catalogued and heartbeat is not None
                    else ()
                )
                revision = (
                    attempt.cleanup_catalogue_revisions.get(name)
                    if attempt.incident_topology is not None
                    else heartbeat.cleanup_resources_revision
                    if catalogued and heartbeat is not None
                    else None
                )
                releases = {
                    resource.resource: resource for resource in payload.resources
                }
                expected_outputs = (
                    {
                        output.output_key
                        for output in registered.outputs
                        if output.backend.backend_name == name
                    }
                    if attempt.incident_topology is not None and registered is not None
                    else set()
                )
                actual_outputs = {
                    output.output_key: output for output in payload.outputs
                }
                if (
                    backend is None
                    or payload.source.generation != backend.context.backend_generation
                    or payload.work.WhichOneof("work") != "session"
                    or payload.work.session != attempt.context
                    or not payload.trial_activity_stopped
                    or registered is None
                    or not cleanup_command_fenced(payload, registered)
                    or revision is None
                    or not payload.HasField("cleanup_resources_revision")
                    or payload.cleanup_resources_revision != revision
                    or payload.verified_monotonic_ns <= 0
                    or set(releases) != set(obligations)
                    or len(obligations) != len(source_obligations)
                    or len(releases) != len(payload.resources)
                    or any(
                        not release.released
                        or release.failure.code
                        or release.failure.message
                        or release.HasField("path") != obligations[key].HasField("path")
                        or release.HasField("path")
                        and release.path != obligations[key].path
                        for key, release in releases.items()
                    )
                    or set(actual_outputs) != expected_outputs
                    or len(actual_outputs) != len(payload.outputs)
                    or any(
                        output.closure
                        not in (pb.OUTPUT_CLOSURE_CLOSED, pb.OUTPUT_CLOSURE_FAILED)
                        for output in actual_outputs.values()
                    )
                ):
                    return pb.ReportReceipt(
                        result=pb.COMMAND_RESULT_REJECTED,
                        failure=pb.Failure(
                            code="EVIDENCE",
                            message="cleanup identity or release proof missing",
                        ),
                    )
                previous_cleanup = attempt.cleanup.get(name)
                if previous_cleanup is not None and previous_cleanup.SerializeToString(
                    deterministic=True
                ) != payload.SerializeToString(deterministic=True):
                    return pb.ReportReceipt(
                        result=pb.COMMAND_RESULT_REJECTED,
                        failure=pb.Failure(
                            code="CONFLICT", message="changed duplicate Cleanup"
                        ),
                    )
                attempt.cleanup[name] = _copy(payload)
                attempt.changed.set()
                self._publish()
                if (
                    self.session.phase
                    in (pb.SESSION_PHASE_CONFIGURATION, pb.SESSION_PHASE_ENDED)
                    and not self.session.cleanup_confirmed
                ):
                    self._spawn(self._late_cleanup(attempt))
                return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
            if attempt.cancel_requested or context is None:
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(code="STALE", message="attempt retired"),
                )
            name = context.backend.backend_name
            backend = attempt.required.get(name)
            if backend is None or context.backend != backend.context:
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(
                        code="IDENTITY", message="unregistered backend generation"
                    ),
                )
            work_kind = context.work.WhichOneof("work")
            if kind == "ready" and self.session.phase == pb.SESSION_PHASE_SETTING_UP:
                within_ready_gate = (
                    ingress_ns <= attempt.setup_deadline_ns
                    or attempt.recovering_evidence == "setup_ready"
                    and ingress_ns <= attempt.recovery_deadline_ns
                )
                if (
                    attempt.interrupted
                    or not within_ready_gate
                    or work_kind != "session"
                    or context.work.session != attempt.context
                    or context.operation.command_id
                    != attempt.setup_operations.get(name)
                    or payload.configuration_revision != self.configuration_revision
                    or not payload.required_checks_passed
                ):
                    return pb.ReportReceipt(
                        result=pb.COMMAND_RESULT_REJECTED,
                        failure=pb.Failure(
                            code="EVIDENCE",
                            message="Setup Ready identity/check mismatch",
                        ),
                    )
                old = attempt.ready.get(name)
                if old is not None and old.SerializeToString(
                    deterministic=True
                ) != payload.SerializeToString(deterministic=True):
                    return pb.ReportReceipt(
                        result=pb.COMMAND_RESULT_REJECTED,
                        failure=pb.Failure(
                            code="CONFLICT", message="changed duplicate Setup Ready"
                        ),
                    )
                attempt.ready[name] = _copy(payload)
            elif kind in {"ready", "started", "stopped", "finished"}:
                if (
                    attempt.trial_index < 0
                    or work_kind != "trial"
                    or context.work.trial
                    != attempt.prepared.trials[attempt.trial_index].context
                    or context.operation.command_id != attempt.trial_operation
                ):
                    return pb.ReportReceipt(
                        result=pb.COMMAND_RESULT_REJECTED,
                        failure=pb.Failure(
                            code="EVIDENCE", message="trial report identity mismatch"
                        ),
                    )
                if name not in attempt.trial_participants:
                    return pb.ReportReceipt(
                        result=pb.COMMAND_RESULT_REJECTED,
                        failure=pb.Failure(
                            code="EVIDENCE",
                            message="backend is not an active trial participant",
                        ),
                    )
                if kind == "ready":
                    within_ready_gate = (
                        ingress_ns <= attempt.ready_deadline_ns
                        or attempt.recovering_evidence == "trial_ready"
                        and ingress_ns <= attempt.recovery_deadline_ns
                    )
                    if (
                        attempt.interrupted
                        or self.trial.phase != pb.TRIAL_PHASE_PREPARING
                        or not within_ready_gate
                        or payload.configuration_revision != self.configuration_revision
                        or not payload.required_checks_passed
                    ):
                        return pb.ReportReceipt(
                            result=pb.COMMAND_RESULT_REJECTED,
                            failure=pb.Failure(
                                code="EVIDENCE", message="trial readiness failed"
                            ),
                        )
                    old = attempt.trial_ready.get(name)
                    if old is not None and old.SerializeToString(
                        deterministic=True
                    ) != payload.SerializeToString(deterministic=True):
                        return pb.ReportReceipt(
                            result=pb.COMMAND_RESULT_REJECTED,
                            failure=pb.Failure(
                                code="CONFLICT", message="changed duplicate trial Ready"
                            ),
                        )
                    attempt.trial_ready[name] = _copy(payload)
                elif kind == "started":
                    camera_roles, external_roles, vr_outputs, sources, producers = (
                        self._activity_requirements(attempt, name)
                    )
                    if (
                        not sources
                        or self.trial.phase
                        not in (pb.TRIAL_PHASE_STARTING, pb.TRIAL_PHASE_RUNNING)
                        or not started_satisfied(
                            payload,
                            target_ns=attempt.target_ns,
                            ingress_ns=ingress_ns,
                            allowance_ns=self.limits.start_evidence_ns,
                            camera_roles=camera_roles,
                            external_camera_roles=external_roles,
                            allowed_producers=producers,
                            source_producers=self._source_producers(attempt, name),
                            vr_outputs=vr_outputs,
                        )
                    ):
                        return pb.ReportReceipt(
                            result=pb.COMMAND_RESULT_REJECTED,
                            failure=pb.Failure(
                                code="LATE",
                                message="Started evidence late or incomplete",
                            ),
                        )
                    old_started = attempt.started.get(name)
                    if old_started is not None and old_started.SerializeToString(
                        deterministic=True
                    ) != payload.SerializeToString(deterministic=True):
                        return pb.ReportReceipt(
                            result=pb.COMMAND_RESULT_REJECTED,
                            failure=pb.Failure(
                                code="CONFLICT", message="changed duplicate Started"
                            ),
                        )
                    attempt.started[name] = _copy(payload)
                elif kind == "stopped":
                    _camera_roles, external_roles, _vr_outputs, sources, producers = (
                        self._activity_requirements(attempt, name)
                    )
                    if (
                        not sources
                        or self.trial.phase
                        not in (
                            pb.TRIAL_PHASE_STARTING,
                            pb.TRIAL_PHASE_RUNNING,
                            pb.TRIAL_PHASE_FINALIZING,
                        )
                        or not stopped_satisfied(
                            payload,
                            target_ns=attempt.target_ns,
                            end_ns=attempt.end_ns,
                            ingress_ns=ingress_ns,
                            allowance_ns=self.limits.stop_evidence_ns,
                            interruption_issued_ns=attempt.interruption_issued_ns,
                            expected_sources=sources,
                            allowed_producers=producers,
                            source_producers=self._source_producers(attempt, name),
                            external_camera_roles=external_roles,
                        )
                    ):
                        return pb.ReportReceipt(
                            result=pb.COMMAND_RESULT_REJECTED,
                            failure=pb.Failure(
                                code="EVIDENCE", message="Stopped conditions missing"
                            ),
                        )
                    old_stopped = attempt.stopped.get(name)
                    if old_stopped is not None and old_stopped.SerializeToString(
                        deterministic=True
                    ) != payload.SerializeToString(deterministic=True):
                        return pb.ReportReceipt(
                            result=pb.COMMAND_RESULT_REJECTED,
                            failure=pb.Failure(
                                code="CONFLICT", message="changed duplicate Stopped"
                            ),
                        )
                    attempt.stopped[name] = _copy(payload)
                else:
                    trial_expected_outputs = [
                        output
                        for output in attempt.prepared.outputs
                        if output.trial
                        == attempt.prepared.trials[attempt.trial_index].context
                        and output.backend.backend_name == name
                    ]
                    unavailable = {
                        key
                        for incident in attempt.confirmed_incidents.values()
                        for key in incident.affected_resources
                    }
                    interrupted_recovery_deadline = (
                        min(
                            attempt.finished_deadline_ns + self.limits.recovery_ns,
                            attempt.finalization_deadline_ns,
                        )
                        if attempt.finalization_deadline_ns
                        else 0
                    )
                    within_finished_gate = (
                        ingress_ns <= attempt.finished_deadline_ns
                        or attempt.recovering_evidence == "finished"
                        and ingress_ns <= attempt.recovery_deadline_ns
                        or attempt.interrupted
                        and ingress_ns <= interrupted_recovery_deadline
                        and not attempt.recovery_log_closed
                    )
                    earliest_finished_ns = (
                        attempt.target_ns
                        if attempt.interruption_issued_ns
                        else attempt.end_ns
                    )
                    if (
                        self.trial.phase
                        not in (pb.TRIAL_PHASE_RUNNING, pb.TRIAL_PHASE_FINALIZING)
                        or ingress_ns < earliest_finished_ns
                        or not within_finished_gate
                        or not payload.trial_activity_stopped
                        or not outputs_satisfied(
                            trial_expected_outputs,
                            payload.outputs,
                            unavailable=unavailable,
                        )
                    ):
                        return pb.ReportReceipt(
                            result=pb.COMMAND_RESULT_REJECTED,
                            failure=pb.Failure(
                                code="EVIDENCE", message="Finished closure incomplete"
                            ),
                        )
                    old_finished = attempt.finished.get(name)
                    if old_finished is not None and old_finished.SerializeToString(
                        deterministic=True
                    ) != payload.SerializeToString(deterministic=True):
                        return pb.ReportReceipt(
                            result=pb.COMMAND_RESULT_REJECTED,
                            failure=pb.Failure(
                                code="CONFLICT", message="changed duplicate Finished"
                            ),
                        )
                    if (
                        old_finished is None
                        and ingress_ns > attempt.finished_deadline_ns
                    ):
                        trial_id = payload.context.work.trial.trial_id
                        recovered_key = (trial_id, name)
                        if (
                            len(attempt.recovered_finished)
                            >= len(attempt.prepared.trials) * len(attempt.required)
                            and recovered_key not in attempt.recovered_finished
                        ):
                            return pb.ReportReceipt(
                                result=pb.COMMAND_RESULT_REJECTED,
                                failure=pb.Failure(
                                    code="CAPACITY",
                                    message="late Finished retention exhausted",
                                ),
                            )
                        attempt.recovered_finished[recovered_key] = _copy(payload)
                        closure = [
                            {
                                "output_key": item.output_key,
                                "closure": pb.OutputClosure.Name(item.closure),
                            }
                            for item in payload.outputs
                        ]
                        recovered = pb.RecoveryState(
                            attempt_id=_id(),
                            affected=pb.ProcessIdentity(
                                role=name, generation=backend.context.backend_generation
                            ),
                            work=pb.WorkContext(trial=payload.context.work.trial),
                            trigger=pb.Failure(
                                code="FINISHED_TIMEOUT",
                                message="initial Finished evidence deadline expired",
                            ),
                            action="reconcile exact Finished output closure",
                            start_monotonic_ns=attempt.finished_deadline_ns,
                            deadline_monotonic_ns=attempt.finished_deadline_ns
                            + self.limits.recovery_ns,
                            completion_monotonic_ns=ingress_ns,
                            progress="exact late Finished accepted; original trial outcome unchanged",
                            outcome=pb.RECOVERY_OUTCOME_COMPLETED,
                            evidence=f"{len(payload.outputs)} exact output closure result(s) retained",
                        )
                        self._controller_recoveries.append(recovered)
                        self._controller_recoveries = self._controller_recoveries[-256:]
                        if (
                            attempt.writer is not None
                            and not attempt.writer_closed
                            and not attempt.recovery_log_closed
                        ):
                            recovery_task = self._spawn(
                                self._log_event(
                                    attempt,
                                    "recovery",
                                    details={
                                        "component": "Finished",
                                        "action": "reconcile exact output closure",
                                        "trial_id": trial_id,
                                        "backend": name,
                                        "outputs": closure,
                                        "initial_deadline_ns": attempt.finished_deadline_ns,
                                    },
                                    at_ns=ingress_ns,
                                    trial_number=payload.context.work.trial.trial_number,
                                    outcome="completed",
                                )
                            )
                            attempt.recovery_log_tasks.add(recovery_task)
                            recovery_task.add_done_callback(
                                partial(self._recovery_log_done, attempt)
                            )
                    attempt.finished[name] = _copy(payload)
            else:
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(code="PHASE", message="report not applicable"),
                )
            self._publish()
            attempt.changed.set()
        async with self._changed:
            self._changed.notify_all()
        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    async def start_session(self, command: svc.OperatorCommand) -> pb.CommandAdmission:
        command_id = command.operator.command_id
        async with self._lock:
            error = self._authorized(command)
            attempt = self.attempt
            if (
                error
                or self._startup_blocker
                or attempt is None
                or self.session.phase != pb.SESSION_PHASE_READY
            ):
                return self._admission(
                    command_id,
                    error=error
                    or self._startup_blocker
                    or "Start requires this attempt's Ready state",
                )
            if self.schema_factory is None or self.output_planner is None:
                return self._admission(
                    command_id, error="writer schema or output contract unavailable"
                )
            self.session.phase = pb.SESSION_PHASE_STARTING
            self._operations[command_id] = pb.OperationState(
                context=pb.OperationContext(command_id=command_id),
                command="StartSession",
                work=pb.WorkContext(session=attempt.context),
                progress="freezing configuration and metadata",
            )
            self._publish()
            attempt.start_task = self._spawn(self._run_start(attempt, command_id))
            return self._admission(command_id)

    async def _persist(
        self,
        attempt: Attempt,
        name: str,
        action: Literal["create_json", "replace_json", "append_jsonl_record"],
        document: dict[str, object],
    ) -> MetadataCompletion:
        writer = attempt.writer
        if writer is None:
            raise StorageError("metadata writer unavailable")
        payload = json.dumps(
            document, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        now = self.clock()
        command_id = _id()
        path = writer.root / name
        work = pb.WorkContext(session=attempt.context)
        if name.endswith("_LOG.json") and attempt.trial_index >= 0:
            work.trial.CopyFrom(attempt.prepared.trials[attempt.trial_index].context)
        request = MetadataWrite(
            command_id,
            work,
            pb.OperationContext(command_id=command_id),
            path,
            action,
            payload,
            now,
            now + self.limits.metadata_ns,
        )
        async with self._lock:
            if len(self._metadata) >= self.limits.max_metadata_operations:
                raise StorageError("metadata result retention capacity exhausted")
            future = writer.submit(request)
            self._metadata[command_id] = pb.MetadataResult(
                operation=pb.OperationContext(command_id=command_id),
                state=pb.METADATA_PERSISTENCE_PENDING,
                path=str(path),
            )
            self._publish()
        try:
            completion = await asyncio.wait_for(
                asyncio.shield(asyncio.wrap_future(future)),
                max(0, (request.deadline_ns - self.clock()) / 1e9),
            )
            terminal = True
        except TimeoutError:
            completion = MetadataCompletion(
                command_id,
                path,
                "unconfirmed",
                self.clock(),
                "metadata deadline expired",
                False,
            )
            terminal = False
            loop = asyncio.get_running_loop()
            future.add_done_callback(
                lambda f: loop.call_soon_threadsafe(
                    self._enqueue_late_metadata, f, writer, command_id, path
                )
            )
        except Exception as exc:
            completion = MetadataCompletion(
                command_id, path, "failed", self.clock(), str(exc), False
            )
            terminal = True
        await self._record_metadata(completion, writer, terminal=terminal)
        if completion.state != "synced" or not completion.deadline_met:
            raise StorageError(
                f"metadata {name} {completion.state}: {completion.error}"
            )
        return completion

    def _enqueue_late_metadata(
        self, future: Any, writer: MetadataWriter, command_id: str, path: Path
    ) -> None:
        try:
            self._metadata_completion_queue.put_nowait(
                (future, writer, command_id, path)
            )
        except asyncio.QueueFull as exc:
            raise RuntimeError(
                "accepted metadata completion exceeded its reserved queue capacity"
            ) from exc
        if self._metadata_drain_task is None or self._metadata_drain_task.done():
            self._metadata_drain_task = self._spawn(self._drain_metadata_completions())

    async def _drain_metadata_completions(self) -> None:
        while True:
            try:
                future, writer, command_id, path = (
                    self._metadata_completion_queue.get_nowait()
                )
            except asyncio.QueueEmpty:
                return
            try:
                completion = cast(MetadataCompletion, future.result())
            except Exception as exc:
                completion = MetadataCompletion(
                    command_id, path, "failed", self.clock(), str(exc), False
                )
            await self._record_metadata(completion, writer, terminal=True)

    async def _record_metadata(
        self, completion: MetadataCompletion, writer: MetadataWriter, *, terminal: bool
    ) -> None:
        enum = {
            "synced": pb.METADATA_PERSISTENCE_SYNCED,
            "failed": pb.METADATA_PERSISTENCE_FAILED,
            "unconfirmed": pb.METADATA_PERSISTENCE_UNCONFIRMED,
        }[completion.state]
        async with self._lock:
            result = self._metadata.get(completion.command_id)
            if result is None:
                if terminal:
                    writer.retire(completion.command_id)
                return
            if not terminal and result.state != pb.METADATA_PERSISTENCE_PENDING:
                return
            if (
                result.state == pb.METADATA_PERSISTENCE_UNCONFIRMED
                and enum == pb.METADATA_PERSISTENCE_UNCONFIRMED
            ):
                if terminal:
                    writer.retire(completion.command_id)
                return
            prior_unconfirmed = result.state == pb.METADATA_PERSISTENCE_UNCONFIRMED
            prior_failure = result.failure.message if result.HasField("failure") else ""
            result.state = enum
            if enum == pb.METADATA_PERSISTENCE_SYNCED:
                result.ClearField("failure")
                if prior_unconfirmed or not completion.deadline_met:
                    reason = (
                        prior_failure
                        or "metadata completion missed its original deadline"
                    )
                    self._warnings.append(
                        pb.Warning(
                            warning_id=_id(),
                            component="metadata",
                            message=f"{completion.path.name}: late verified sync; original timeout retained: {reason}",
                        )
                    )
                    self._warnings = self._warnings[-256:]
            elif completion.error:
                result.failure.CopyFrom(
                    pb.Failure(code="METADATA_WRITE", message=completion.error)
                )
            if terminal and enum == pb.METADATA_PERSISTENCE_SYNCED:
                path_key = str(completion.path)
                previous = self._metadata_latest_synced.get(path_key)
                if previous is not None and previous != completion.command_id:
                    prior = self._metadata.get(previous)
                    if (
                        prior is not None
                        and prior.state == pb.METADATA_PERSISTENCE_SYNCED
                    ):
                        self._metadata.pop(previous)
                self._metadata_latest_synced[path_key] = completion.command_id
            self._publish()
            if terminal:
                writer.retire(completion.command_id)

    async def _retire_completed_trial_metadata(
        self, attempt: Attempt, trial_log: str
    ) -> None:
        async with self._lock:
            if self.attempt is not attempt:
                return
            path_key = str(attempt.reservation.protocol_directory / trial_log)
            command_id = self._metadata_latest_synced.get(path_key)
            if command_id is None:
                return
            result = self._metadata.get(command_id)
            if result is not None and result.state == pb.METADATA_PERSISTENCE_SYNCED:
                self._metadata.pop(command_id)
                self._metadata_latest_synced.pop(path_key, None)
                self._publish()

    def _event(
        self,
        attempt: Attempt,
        event_type: str,
        *,
        at_ns: int | None = None,
        trial_number: int | None = None,
        outcome: str | None = None,
        details: dict[str, object] | None = None,
    ) -> dict[str, object]:
        event_ns = self.clock() if at_ns is None else at_ns
        anchor = datetime.fromisoformat(attempt.prepared.anchor_wall_time)
        from datetime import timedelta

        wall = anchor + timedelta(
            microseconds=(event_ns - attempt.prepared.anchor_monotonic_ns) / 1000
        )
        event: dict[str, object] = {
            "monotonic_ns": event_ns,
            "wall_time": wall.isoformat(),
            "event_type": event_type,
            "source": "controller",
        }
        if trial_number is not None:
            event["trial_number"] = trial_number
        if outcome is not None:
            event["outcome"] = outcome
        if details is not None:
            event["details"] = details
        return event

    async def _log_event(
        self,
        attempt: Attempt,
        event_type: str,
        *,
        at_ns: int | None = None,
        trial_number: int | None = None,
        outcome: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        await self._persist(
            attempt,
            "SESSION_LOG.jsonl",
            "append_jsonl_record",
            self._event(
                attempt,
                event_type,
                at_ns=at_ns,
                trial_number=trial_number,
                outcome=outcome,
                details=details,
            ),
        )

    async def _incident_log(
        self,
        attempt: Attempt,
        event_type: str,
        details: dict[str, object],
        *,
        at_ns: int | None = None,
        trial_number: int | None = None,
        outcome: str | None = None,
    ) -> None:
        try:
            await self._log_event(
                attempt,
                event_type,
                at_ns=at_ns,
                trial_number=trial_number,
                outcome=outcome,
                details=details,
            )
        except StorageError as exc:
            await self._interrupt(
                attempt, f"incident bookkeeping persistence failed: {exc}"
            )

    async def _run_start(self, attempt: Attempt, command_id: str) -> None:
        try:
            start_deadline_ns = self.clock() + self.limits.setup_ns
            if attempt.cancel_requested:
                raise RuntimeError("attempt cancelled")
            schema = (
                self.schema_factory(attempt.prepared) if self.schema_factory else None
            )
            if not isinstance(schema, dict) or schema.get("schema_version") != 1:
                raise RuntimeError("versioned writer schema unavailable")
            writer = MetadataWriter(
                attempt.reservation.protocol_directory,
                max_operations=self.limits.max_metadata_operations,
                max_bytes=self.limits.max_metadata_bytes,
                clock=self.clock,
                session_id=attempt.context.session_id,
            )
            attempt.writer = writer
            session_document: dict[str, object] = {
                "schema_version": 1,
                "session_id": attempt.context.session_id,
                "controller_generation": self.generation,
                "session_setup_wall_time": attempt.prepared.anchor_wall_time,
                "session_setup_monotonic_ns": attempt.prepared.anchor_monotonic_ns,
                "local_timezone": attempt.prepared.local_timezone,
                "configuration_revision": attempt.prepared.configuration_revision,
                "configuration": _active_configuration_document(
                    attempt.prepared.configuration
                ),
                "trials": [_json(plan) for plan in attempt.prepared.trials],
                "outputs": [_json(plan) for plan in attempt.prepared.outputs],
            }
            if attempt.paired:
                session_document["spikeglx"] = _json(attempt.prepared.spikeglx)
            await self._persist(
                attempt, "SESSION_CONFIG.json", "create_json", session_document
            )
            await self._persist(attempt, "SCHEMA.json", "create_json", schema)
            if self.clock() >= start_deadline_ns:
                raise TimeoutError(
                    "Start preparation deadline elapsed before registration"
                )
            if self.supervisor is None:
                raise RuntimeError("supervisor unavailable")
            registration = await asyncio.wait_for(
                self.supervisor.register_context(
                    self._registration(attempt, command_id)
                ),
                max(
                    0,
                    min(start_deadline_ns - self.clock(), self.limits.registration_ns)
                    / 1e9,
                ),
            )
            if (
                registration.admission.result != pb.COMMAND_RESULT_ACCEPTED
                or registration.registered.work.session != attempt.context
            ):
                raise RuntimeError("Start registration unconfirmed")
            async with self._lock:
                if self.attempt is not attempt or attempt.cancel_requested:
                    raise RuntimeError("attempt retired before activation")
                attempt.activated = True
                self.session.activated = True
                self._publish()
            await self._log_event(attempt, "session_started")
            if attempt.paired:
                if self.clock() >= start_deadline_ns:
                    raise TimeoutError("Start writing gate deadline elapsed")
                if (
                    self.spikeglx is None
                    or not await asyncio.wait_for(
                        self.spikeglx.verify_before_start(),
                        max(0, (start_deadline_ns - self.clock()) / 1e9),
                    )
                    or not await asyncio.wait_for(
                        self.spikeglx.start_and_verify_writing(),
                        max(0, (start_deadline_ns - self.clock()) / 1e9),
                    )
                ):
                    raise RuntimeError("SpikeGLX writing gate failed")
                await self._log_event(
                    attempt,
                    "spikeglx_started",
                    details={"run_name": attempt.prepared.spikeglx.run_name},
                )
            async with self._lock:
                if (
                    self.attempt is not attempt
                    or attempt.interrupted
                    or self.session.phase != pb.SESSION_PHASE_STARTING
                ):
                    raise RuntimeError("Start retired before Running transition")
                self.session.phase = pb.SESSION_PHASE_RUNNING
                operation = self._operations[command_id]
                operation.complete = True
                operation.succeeded = True
                operation.progress = "session activated"
                self._publish()
            attempt.trial_task = self._spawn(self._run_trials(attempt))
        except Exception as exc:
            async with self._lock:
                self._complete_operation(
                    command_id, success=False, progress="Start failed", error=str(exc)
                )
                self._publish()
            await self._interrupt(attempt, f"Start failed: {exc}")

    async def _run_trials(self, attempt: Attempt) -> None:
        for index, plan in enumerate(attempt.prepared.trials):
            async with self._lock:
                if (
                    self.attempt is not attempt
                    or self.session.phase != pb.SESSION_PHASE_RUNNING
                ):
                    return
                if (
                    set(attempt.incident_id_by_error.values())
                    - attempt.confirmed_incidents.keys()
                ):
                    pending = (
                        set(attempt.incident_id_by_error.values())
                        - attempt.confirmed_incidents.keys()
                    )
                    expired = [
                        error_id
                        for error_id, incident_id in attempt.incident_id_by_error.items()
                        if incident_id in pending
                        and self.clock() >= attempt.incident_deadlines.get(error_id, 0)
                    ]
                    if expired:
                        raise RuntimeError(
                            "incident isolation remained unconfirmed after its original recovery deadline"
                        )
                attempt.trial_index = index
                attempt.trial_operation = _id()
                attempt.trial_ready.clear()
                attempt.started.clear()
                attempt.stopped.clear()
                attempt.finished.clear()
                attempt.unavailable_outputs.clear()
                attempt.trial_participants = self._select_trial_participants(
                    attempt, plan
                )
                self.trial = pb.TrialState(
                    context=plan.context, phase=pb.TRIAL_PHASE_PREPARING
                )
                self.projections.set_scope(
                    pb.WorkContext(trial=plan.context), self.configuration_revision
                )
                self._publish()
            try:
                await self._prepare_and_run_trial(attempt, plan)
            except Exception as exc:
                await self._interrupt(attempt, f"trial {index + 1}: {exc}")
                return
            async with self._lock:
                if self.session.stop_after_trial:
                    self.session.phase = pb.SESSION_PHASE_FINALIZING
                    self.session.outcome = pb.SESSION_OUTCOME_STOPPED
                    self._publish()
                    break
        await self._finalize(attempt)

    async def _prepare_and_run_trial(
        self, attempt: Attempt, plan: pb.TrialPlan
    ) -> None:
        deadline = self.clock() + self.limits.ready_ns
        attempt.ready_deadline_ns = deadline
        request_by_name: dict[str, svc.PrepareTrialRequest] = {}
        for name, backend in attempt.trial_participants.items():
            request = svc.PrepareTrialRequest(
                configuration_revision=self.configuration_revision, plan=plan
            )
            request.command.CopyFrom(self._backend_command(attempt, backend))
            request.command.command_id = attempt.trial_operation
            request.command.work.trial.CopyFrom(plan.context)
            request.outputs.extend(
                output
                for output in attempt.prepared.outputs
                if output.trial == plan.context and output.backend.backend_name == name
            )
            request_by_name[name] = request
        replies = await asyncio.wait_for(
            asyncio.gather(
                *(
                    attempt.trial_participants[name].prepare_trial(request)
                    for name, request in request_by_name.items()
                )
            ),
            max(0, (deadline - self.clock()) / 1e9),
        )
        if any(reply.result != pb.COMMAND_RESULT_ACCEPTED for reply in replies):
            raise RuntimeError("trial preparation rejected")
        await self._wait_lifecycle_with_recovery(
            attempt, "trial_ready", frozenset(attempt.trial_participants), deadline
        )
        async with self._lock:
            self.trial.phase = pb.TRIAL_PHASE_READY
            self._publish()
        target = self.clock() + self.limits.lead_ns
        end = target + plan.resolved_duration_ns
        attempt.target_ns = target
        attempt.end_ns = end
        attempt.finished_deadline_ns = end + self.limits.finished_ns
        schedule_deadline = target - self.limits.controller_release_ns
        release_deadline = target - self.limits.backend_release_ns
        anchor = datetime.fromisoformat(attempt.prepared.anchor_wall_time)
        from datetime import timedelta

        trial_wall = anchor + timedelta(
            microseconds=(target - attempt.prepared.anchor_monotonic_ns) / 1000
        )
        prefix = f"{self.configuration.subject}_{trial_wall.strftime('%H%M%S')}"
        attempt.trial_log_name = f"{prefix}_LOG.json"
        attempt.trial_log_started = False
        attempt.trial_log_finished = False
        attempt.trial_log_start_task = None
        attempt.trial_log_finish_task = None
        for output in attempt.prepared.outputs:
            if output.trial == plan.context:
                if (
                    not output.output_tag
                    or not output.extension
                    or "/" in output.output_tag
                    or "/" in output.extension
                    or "\\" in output.output_tag
                    or "\\" in output.extension
                ):
                    raise RuntimeError("unsafe output reservation name")
                output.path = str(
                    attempt.reservation.protocol_directory
                    / f"{prefix}_{output.output_tag}.{output.extension}"
                )
                if output.backend.backend_name not in attempt.trial_participants:
                    if output.output_key not in {
                        key
                        for incident in attempt.confirmed_incidents.values()
                        for key in incident.affected_resources
                    }:
                        raise RuntimeError(
                            "omitted backend has an unproven output obligation"
                        )
                    attempt.unavailable_outputs.append(
                        pb.OutputResult(
                            output_key=output.output_key,
                            path=output.path,
                            closure=pb.OUTPUT_CLOSURE_FAILED,
                            failure=pb.Failure(
                                code="INCIDENT_UNAVAILABLE",
                                message="owning function unavailable under confirmed E06 scope",
                            ),
                        )
                    )
        async with self._lock:
            self.trial.phase = pb.TRIAL_PHASE_STARTING
            self.trial.start_monotonic_ns = target
            self.trial.scheduled_end_monotonic_ns = end
            self._publish()
        for name, backend in attempt.trial_participants.items():
            schedule_request = svc.ScheduleTrialRequest(
                start_monotonic_ns=target,
                normal_end_monotonic_ns=end,
                trial_file_prefix=prefix,
            )
            schedule_request.command.CopyFrom(self._backend_command(attempt, backend))
            schedule_request.command.command_id = _id()
            schedule_request.command.work.trial.CopyFrom(plan.context)
            schedule_request.outputs.extend(
                output
                for output in attempt.prepared.outputs
                if output.trial == plan.context and output.backend.backend_name == name
            )
            attempt.schedule_operations[name] = schedule_request.command.command_id
            reply = await self._trial_command_with_retry(
                backend.schedule_trial,
                schedule_request,
                schedule_deadline,
                schedule_deadline,
            )
            if reply.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(f"{name} schedule rejected")
        if self.clock() > schedule_deadline:
            raise TimeoutError(
                "schedule acknowledgements missed controller release cutoff"
            )
        releases: dict[str, tuple[BackendPort, svc.ReleaseTrialRequest]] = {}
        for name, backend in attempt.trial_participants.items():
            release_request = svc.ReleaseTrialRequest(
                start_monotonic_ns=target, normal_end_monotonic_ns=end
            )
            release_request.command.CopyFrom(self._backend_command(attempt, backend))
            release_request.command.command_id = _id()
            release_request.command.work.trial.CopyFrom(plan.context)
            release_request.schedule_operation.command_id = attempt.schedule_operations[
                name
            ]
            releases[name] = backend, release_request
        if self.clock() > schedule_deadline:
            raise TimeoutError("release dispatch missed controller cutoff")
        release_results = await asyncio.wait_for(
            asyncio.gather(
                *(
                    self._trial_command_with_retry(
                        backend.release_trial,
                        request,
                        schedule_deadline,
                        release_deadline,
                    )
                    for backend, request in releases.values()
                )
            ),
            max(0, (release_deadline - self.clock()) / 1e9),
        )
        for name, reply in zip(releases, release_results, strict=True):
            if reply.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(f"{name} release rejected")
        if self.clock() > release_deadline:
            raise TimeoutError("release acknowledgement missed backend cutoff")
        await asyncio.sleep(max(0, (target - self.clock()) / 1e9))
        async with self._lock:
            self.trial.phase = pb.TRIAL_PHASE_RUNNING
            self._publish()
        await self._wait_evidence(
            lambda: bool(attempt.started),
            target + self.limits.start_evidence_ns,
            attempt,
        )
        attempt.trial_log_start_task = self._spawn(self._start_trial_log(attempt, plan))
        await asyncio.shield(attempt.trial_log_start_task)
        activity_backends = self._activity_backends(attempt)
        await self._wait_evidence(
            lambda: activity_backends <= attempt.started.keys(),
            target + self.limits.start_evidence_ns,
            attempt,
        )
        await asyncio.sleep(max(0, (end - self.clock()) / 1e9))
        async with self._lock:
            self.trial.phase = pb.TRIAL_PHASE_FINALIZING
            attempt.finished_deadline_ns = end + self.limits.finished_ns
            self._publish()
        await self._wait_evidence(
            lambda: activity_backends <= attempt.stopped.keys(),
            end + self.limits.stop_evidence_ns,
            attempt,
        )
        await self._wait_lifecycle_with_recovery(
            attempt,
            "finished",
            frozenset(attempt.trial_participants),
            end + self.limits.finished_ns,
        )
        attempt.trial_log_finish_task = self._spawn(
            self._finish_normal_trial_log(attempt, plan)
        )
        await asyncio.shield(attempt.trial_log_finish_task)
        async with self._lock:
            self.trial.phase = pb.TRIAL_PHASE_ENDED
            self.trial.outcome = pb.TRIAL_OUTCOME_COMPLETED
            self.trial.actual_end_monotonic_ns = end
            self._publish()
        gap = next(
            (
                item.minimum_duration_ns
                for item in self.configuration.gaps
                if item.after_trial_number == plan.context.trial_number
            ),
            0,
        )
        await asyncio.sleep(max(0, (end + gap - self.clock()) / 1e9))

    async def _start_trial_log(self, attempt: Attempt, plan: pb.TrialPlan) -> None:
        if attempt.writer is None or not attempt.trial_log_name:
            raise StorageError("trial metadata writer unavailable")
        attempt.writer.reserve_trial_log(attempt.trial_log_name)
        await self._persist(
            attempt,
            attempt.trial_log_name,
            "create_json",
            {
                "schema_version": 1,
                "session_id": attempt.context.session_id,
                "trial_id": plan.context.trial_id,
                "trial_number": plan.context.trial_number,
                "session_config": "SESSION_CONFIG.json",
                "complete": False,
                "plan": _json(plan),
            },
        )
        await self._log_event(
            attempt,
            "trial_started",
            at_ns=attempt.target_ns,
            trial_number=plan.context.trial_number,
        )
        attempt.trial_log_started = True

    async def _finish_normal_trial_log(
        self, attempt: Attempt, plan: pb.TrialPlan
    ) -> None:
        if attempt.interrupted:
            raise RuntimeError("normal trial closure superseded by interruption")
        outputs = [
            _json(result)
            for finished in attempt.finished.values()
            for result in finished.outputs
        ]
        outputs.extend(_json(result) for result in attempt.unavailable_outputs)
        await self._persist(
            attempt,
            attempt.trial_log_name,
            "replace_json",
            {
                "schema_version": 1,
                "session_id": attempt.context.session_id,
                "trial_id": plan.context.trial_id,
                "trial_number": plan.context.trial_number,
                "session_config": "SESSION_CONFIG.json",
                "complete": True,
                "outcome": "completed",
                "plan": _json(plan),
                "outputs": outputs,
            },
        )
        if attempt.interrupted:
            raise RuntimeError("normal trial event superseded by interruption")
        await self._log_event(
            attempt,
            "trial_finished",
            at_ns=attempt.end_ns,
            trial_number=plan.context.trial_number,
            outcome="completed",
        )
        attempt.trial_log_finished = True
        await self._retire_completed_trial_metadata(attempt, attempt.trial_log_name)

    async def _finish_interrupted_trial(self, attempt: Attempt) -> bool:
        if attempt.trial_index < 0 or not attempt.started or attempt.trial_log_finished:
            return True
        plan = attempt.prepared.trials[attempt.trial_index]
        deadline_ns = attempt.finalization_deadline_ns
        try:
            start_task = attempt.trial_log_start_task
            if start_task is None:
                start_task = self._spawn(self._start_trial_log(attempt, plan))
                attempt.trial_log_start_task = start_task
            await asyncio.wait_for(
                asyncio.shield(start_task), max(0, (deadline_ns - self.clock()) / 1e9)
            )
            normal_finish = attempt.trial_log_finish_task
            if normal_finish is not None:
                await asyncio.wait_for(
                    asyncio.gather(normal_finish, return_exceptions=True),
                    max(0, (deadline_ns - self.clock()) / 1e9),
                )
                if attempt.trial_log_finished:
                    async with self._lock:
                        if self.attempt is attempt:
                            self.trial.phase = pb.TRIAL_PHASE_ENDED
                            self.trial.outcome = pb.TRIAL_OUTCOME_COMPLETED
                            self._publish()
                    return True
            activity_backends = self._activity_backends(attempt)
            try:
                await self._wait_evidence(
                    lambda: activity_backends <= attempt.stopped.keys(),
                    attempt.interruption_issued_ns + self.limits.stop_evidence_ns,
                    attempt,
                )
            except TimeoutError:
                pass
            try:
                await self._wait_lifecycle_with_recovery(
                    attempt,
                    "finished",
                    frozenset(attempt.trial_participants),
                    attempt.finished_deadline_ns,
                    closure_only=True,
                )
            except TimeoutError:
                pass
            # A missing Finished report leaves every corresponding reserved output
            # explicitly unknown. A reported closure is retained exactly as sent.
            reported = {
                result.output_key: result
                for finished in attempt.finished.values()
                for result in finished.outputs
            }
            reported.update(
                {result.output_key: result for result in attempt.unavailable_outputs}
            )
            output_results: list[dict[str, object]] = []
            for output in attempt.prepared.outputs:
                if output.trial != plan.context:
                    continue
                result = reported.get(output.output_key)
                if result is None:
                    result = pb.OutputResult(
                        output_key=output.output_key,
                        path=output.path,
                        closure=pb.OUTPUT_CLOSURE_UNCONFIRMED,
                        failure=pb.Failure(
                            code="OUTPUT_CLOSURE_UNCONFIRMED",
                            message="no exact Finished closure by original interruption deadline",
                        ),
                    )
                output_results.append(_json(result))
            await asyncio.wait_for(
                self._persist(
                    attempt,
                    attempt.trial_log_name,
                    "replace_json",
                    {
                        "schema_version": 1,
                        "session_id": attempt.context.session_id,
                        "trial_id": plan.context.trial_id,
                        "trial_number": plan.context.trial_number,
                        "session_config": "SESSION_CONFIG.json",
                        "complete": True,
                        "outcome": "interrupted",
                        "plan": _json(plan),
                        "outputs": output_results,
                    },
                ),
                max(0, (deadline_ns - self.clock()) / 1e9),
            )
            if not attempt.trial_log_finished:
                actual_end_ns = (
                    max(
                        report.actual_stop_monotonic_ns
                        for report in attempt.stopped.values()
                    )
                    if activity_backends <= attempt.stopped.keys() and attempt.stopped
                    else None
                )
                await asyncio.wait_for(
                    self._log_event(
                        attempt,
                        "trial_finished",
                        trial_number=plan.context.trial_number,
                        outcome="interrupted",
                        details={
                            "output_closure_confirmed": frozenset(
                                attempt.trial_participants
                            )
                            <= attempt.finished.keys(),
                            "actual_end_monotonic_ns": actual_end_ns,
                            "interruption_issued_monotonic_ns": attempt.interruption_issued_ns,
                        },
                    ),
                    max(0, (deadline_ns - self.clock()) / 1e9),
                )
                attempt.trial_log_finished = True
            async with self._lock:
                if self.attempt is attempt:
                    self.trial.phase = pb.TRIAL_PHASE_ENDED
                    self.trial.outcome = pb.TRIAL_OUTCOME_INTERRUPTED
                    if activity_backends <= attempt.stopped.keys() and attempt.stopped:
                        self.trial.actual_end_monotonic_ns = max(
                            report.actual_stop_monotonic_ns
                            for report in attempt.stopped.values()
                        )
                    self._publish()
            await self._retire_completed_trial_metadata(attempt, attempt.trial_log_name)
            return True
        except (StorageError, TimeoutError, RuntimeError) as exc:
            async with self._lock:
                self._warnings.append(
                    pb.Warning(
                        warning_id=_id(),
                        component="interrupted_trial",
                        message=f"interrupted trial log or closure unconfirmed: {exc}",
                    )
                )
                self._warnings = self._warnings[-256:]
                self._publish()
            return False

    async def _trial_command_with_retry(
        self,
        send: Callable[[Any], Coroutine[Any, Any, pb.CommandAdmission]],
        request: Message,
        dispatch_deadline_ns: int,
        receipt_deadline_ns: int,
    ) -> pb.CommandAdmission:
        for retry in range(2):
            if self.clock() > dispatch_deadline_ns:
                raise TimeoutError("trial command dispatch cutoff elapsed")
            try:
                return await asyncio.wait_for(
                    send(request), max(0, (receipt_deadline_ns - self.clock()) / 1e9)
                )
            except grpc.RpcError:
                if retry or self.clock() >= receipt_deadline_ns:
                    raise
        raise RuntimeError("trial command retry exhausted")

    async def _interrupt(
        self, attempt: Attempt, reason: str, *, issued_ns: int | None = None
    ) -> None:
        async with self._lock:
            if self.attempt is not attempt:
                return
            if attempt.interrupted:
                return
            attempt.interrupted = True
            attempt.interruption_issued_ns = (
                self.clock() if issued_ns is None else issued_ns
            )
            activated = attempt.activated
            if not activated:
                attempt.cancel_requested = True
                self._publish()
        if (
            attempt.start_task is not None
            and attempt.start_task is not asyncio.current_task()
        ):
            attempt.start_task.cancel()
            await asyncio.gather(attempt.start_task, return_exceptions=True)
        if not activated:
            await self._cancel_attempt(attempt)
            return
        async with self._lock:
            self.session.phase = pb.SESSION_PHASE_FINALIZING
            self.session.outcome = pb.SESSION_OUTCOME_INTERRUPTED
            self.session.interruption_reason.CopyFrom(
                pb.Failure(code="INTERRUPTED", message=reason)
            )
            if not attempt.finalization_deadline_ns:
                attempt.finalization_deadline_ns = (
                    attempt.interruption_issued_ns
                    + self.limits.stop_evidence_ns
                    + self.limits.finished_ns
                    + self.limits.setup_cancel_ns
                )
            if (
                self.trial.phase
                in (
                    pb.TRIAL_PHASE_RUNNING,
                    pb.TRIAL_PHASE_STARTING,
                    pb.TRIAL_PHASE_FINALIZING,
                )
                and attempt.started
                and not attempt.trial_log_finished
            ):
                self.trial.phase = pb.TRIAL_PHASE_FINALIZING
                self.trial.outcome = pb.TRIAL_OUTCOME_INTERRUPTED
                self.trial.interruption_issued_monotonic_ns = (
                    attempt.interruption_issued_ns
                )
                attempt.finished_deadline_ns = (
                    attempt.interruption_issued_ns + self.limits.finished_ns
                )
            self._publish()
        if (
            attempt.trial_task is not None
            and attempt.trial_task is not asyncio.current_task()
        ):
            attempt.trial_task.cancel()
            await asyncio.gather(attempt.trial_task, return_exceptions=True)
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    *(
                        backend.interrupt_session(
                            self._interrupt_request(attempt, backend, reason)
                        )
                        for backend in attempt.required.values()
                    ),
                    return_exceptions=True,
                ),
                self.limits.stop_evidence_ns / 1e9,
            )
        except TimeoutError:
            pass
        trial_metadata_clean = await self._finish_interrupted_trial(attempt)
        await self._finalize(attempt, metadata_clean=trial_metadata_clean)

    async def authority_loss(self, reason: str, issued_ns: int) -> None:
        async with self._lock:
            if self._authority_lost:
                return
            self._authority_lost = True
            self._shutdown_intent_ns = (
                min(self._shutdown_intent_ns, issued_ns)
                if self._shutdown_intent_ns
                else issued_ns
            )
            self.session.shutdown_requested = True
            attempt = self.attempt
            if attempt is not None and not attempt.interruption_issued_ns:
                attempt.interruption_issued_ns = issued_ns
            self._owner = None
            self._publish()
        if attempt is not None:
            # This dispatch is independent of an older CancelSetup/cleanup task that
            # may be waiting on the now-lost supervisor. Admission is not stop proof.
            emergency = self._spawn(
                self._authority_emergency_interrupt(attempt, reason)
            )
            await self._interrupt(attempt, reason, issued_ns=issued_ns)
            await asyncio.gather(emergency, return_exceptions=True)

    async def _authority_emergency_interrupt(
        self, attempt: Attempt, reason: str
    ) -> None:
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    *(
                        backend.interrupt_session(
                            self._interrupt_request(attempt, backend, reason)
                        )
                        for backend in attempt.required.values()
                    ),
                    return_exceptions=True,
                ),
                self.limits.stop_evidence_ns / 1e9,
            )
        except TimeoutError:
            pass

    async def report_interruption(
        self, report: svc.InterruptionReport
    ) -> pb.ReportReceipt:
        async with self._lock:
            attempt = self.attempt
            if (
                attempt is None
                or report.controller_generation != self.generation
                or report.supervisor.role != "supervisor"
                or report.supervisor.generation != self.supervisor_generation
                or not report.interruption_id
            ):
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(
                        code="IDENTITY", message="interruption identity mismatch"
                    ),
                )
            work_kind = report.work.WhichOneof("work")
            if work_kind == "session":
                valid_work = report.work.session == attempt.context
            elif work_kind == "trial" and attempt.trial_index >= 0:
                valid_work = (
                    report.work.trial
                    == attempt.prepared.trials[attempt.trial_index].context
                )
            else:
                valid_work = False
            if not valid_work:
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(
                        code="STALE", message="interruption work mismatch"
                    ),
                )
            canonical = report.SerializeToString(deterministic=True)
            old = self._interruption_ids.get(report.interruption_id)
            if old is not None:
                if old != canonical:
                    return pb.ReportReceipt(
                        result=pb.COMMAND_RESULT_REJECTED,
                        failure=pb.Failure(
                            code="CONFLICT", message="interruption ID changed payload"
                        ),
                    )
                return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
            if len(self._interruption_ids) >= 256:
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(
                        code="CAPACITY", message="interruption accounting exhausted"
                    ),
                )
            self._interruption_ids[report.interruption_id] = canonical
            self._errors.append(
                pb.ErrorReport(
                    error_id=report.interruption_id,
                    source=report.supervisor,
                    work=report.work,
                    occurred_monotonic_ns=report.issued_monotonic_ns,
                    failure=report.reason,
                )
            )
            if len(self._errors) > 256:
                self._errors = self._errors[-256:]
            self._publish()
        self._spawn(
            self._interrupt(
                attempt, report.reason.message, issued_ns=report.issued_monotonic_ns
            )
        )
        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    def _interrupt_request(
        self, attempt: Attempt, backend: BackendPort, reason: str
    ) -> svc.InterruptSessionRequest:
        request = svc.InterruptSessionRequest(
            issued_monotonic_ns=attempt.interruption_issued_ns,
            reason=pb.Failure(code="INTERRUPTED", message=reason),
        )
        request.command.CopyFrom(self._backend_command(attempt, backend))
        return request

    async def _finalize(self, attempt: Attempt, *, metadata_clean: bool = True) -> None:
        async with self._lock:
            if self.attempt is not attempt or attempt.finalizing:
                return
            attempt.finalizing = True
            if self.session.phase != pb.SESSION_PHASE_FINALIZING:
                self.session.phase = pb.SESSION_PHASE_FINALIZING
                self.session.outcome = pb.SESSION_OUTCOME_COMPLETED
                self._publish()
            outcome = (
                pb.SessionOutcome.Name(self.session.outcome)
                .removeprefix("SESSION_OUTCOME_")
                .lower()
            )
            if not attempt.finalization_deadline_ns:
                attempt.finalization_deadline_ns = (
                    self.clock() + self.limits.setup_cancel_ns
                )
            cleanup_deadline = attempt.finalization_deadline_ns
        clean = metadata_clean
        if attempt.paired:
            try:
                if self.spikeglx is None or not await asyncio.wait_for(
                    self.spikeglx.stop_expected_run(),
                    max(0, (cleanup_deadline - self.clock()) / 1e9),
                ):
                    clean = False
                else:
                    attempt.spikeglx_stopped = True
                    await self._log_event(
                        attempt,
                        "spikeglx_stopped",
                        details={"run_name": attempt.prepared.spikeglx.run_name},
                    )
            except Exception:
                clean = False
        if attempt.writer is not None:
            # The receipt for every accepted late Finished is paired with an owned
            # recovery event task before releasing the state lock. Close that
            # admission gate and join those writes before sealing the writer.
            async with self._lock:
                attempt.recovery_log_closed = True
                recovery_logs = tuple(attempt.recovery_log_tasks)
            if recovery_logs:
                try:
                    recovery_results = await asyncio.wait_for(
                        asyncio.gather(*recovery_logs, return_exceptions=True),
                        max(0, (cleanup_deadline - self.clock()) / 1e9),
                    )
                    if any(
                        isinstance(result, BaseException) for result in recovery_results
                    ):
                        clean = False
                except TimeoutError:
                    clean = False
            if attempt.recovery_log_failed or any(
                result.state
                in (pb.METADATA_PERSISTENCE_FAILED, pb.METADATA_PERSISTENCE_UNCONFIRMED)
                for result in self._metadata.values()
            ):
                clean = False
            try:
                await asyncio.wait_for(
                    self._log_event(attempt, "session_ended", outcome=outcome),
                    max(0, (cleanup_deadline - self.clock()) / 1e9),
                )
            except (StorageError, TimeoutError):
                clean = False
            try:
                sealed = await asyncio.wait_for(
                    asyncio.to_thread(
                        attempt.writer.seal,
                        max(0, (cleanup_deadline - self.clock()) / 1e9),
                    ),
                    max(0, (cleanup_deadline - self.clock()) / 1e9),
                )
            except (TimeoutError, StorageError, OSError):
                sealed = False
            if not sealed:
                clean = False
            else:
                attempt.writer_closed = True
        else:
            attempt.writer_closed = True
        try:
            requests = {
                name: self._backend_command(attempt, backend)
                for name, backend in attempt.required.items()
            }
            attempt.cleanup_commands.update(
                {name: request.command_id for name, request in requests.items()}
            )
            fenced = (
                await self._register_cleanup_fences(attempt, requests, cleanup_deadline)
                if not self._authority_lost
                else False
            )
            clean = clean and fenced
            if fenced or self._authority_lost:
                results = await asyncio.wait_for(
                    asyncio.gather(
                        *(
                            backend.cleanup(requests[name])
                            for name, backend in attempt.required.items()
                        ),
                        return_exceptions=True,
                    ),
                    max(0, (cleanup_deadline - self.clock()) / 1e9),
                )
                if not all(
                    isinstance(result, pb.CommandAdmission)
                    and result.result == pb.COMMAND_RESULT_ACCEPTED
                    for result in results
                ):
                    clean = False
        except TimeoutError:
            clean = False
        clean = await self._await_cleanups(attempt, cleanup_deadline) and clean
        if (
            attempt.reservation_registration_started
            and not attempt.reservation_registered
        ):
            clean = False
        if clean and not self._authority_lost:
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(attempt.reservation.complete),
                    max(0, (cleanup_deadline - self.clock()) / 1e9),
                )
                clean = await self._release_reservation_pointer(
                    attempt, cleanup_deadline
                )
            except (StorageError, OSError, TimeoutError):
                clean = False
        async with self._lock:
            self.session.phase = pb.SESSION_PHASE_ENDED
            self.session.cleanup_confirmed = clean and not self._authority_lost
            if not clean:
                self.session.outcome = pb.SESSION_OUTCOME_INTERRUPTED
            if attempt.incidents is not None:
                try:
                    attempt.incidents.end_session()
                except IncidentCapacityError:
                    self.session.outcome = pb.SESSION_OUTCOME_INTERRUPTED
                    self._warnings.append(
                        pb.Warning(
                            warning_id=_id(),
                            component="incidents",
                            message="terminal incident accounting capacity exhausted",
                        )
                    )
            for prompt_id, (prompt, owner) in list(self._incident_prompts.items()):
                if owner is attempt and "acknowledge" not in prompt.permitted_choices:
                    self._incident_prompts.pop(prompt_id)
            for command_id in attempt.abort_command_ids + attempt.shutdown_command_ids:
                self._complete_operation(
                    command_id,
                    success=clean and not self._authority_lost,
                    progress="interruption and cleanup confirmed"
                    if clean and not self._authority_lost
                    else "cleanup evidence blocked",
                    error="cleanup could not be confirmed"
                    if not clean or self._authority_lost
                    else "",
                )
            self._publish()

    async def _late_cleanup(self, attempt: Attempt) -> None:
        async with self._lock:
            if (
                self._authority_lost
                or attempt.reservation_registration_started
                and not attempt.reservation_registered
                or self.attempt is not attempt
                or self.session.cleanup_confirmed
                or len(attempt.cleanup) != len(attempt.required)
            ):
                return
            if self.session.phase == pb.SESSION_PHASE_ENDED:
                if (
                    not attempt.writer_closed
                    or attempt.paired
                    and not attempt.spikeglx_stopped
                ):
                    return
                complete = True
            elif (
                self.session.phase == pb.SESSION_PHASE_CONFIGURATION
                and attempt.cancel_requested
            ):
                complete = False
            else:
                return
        deadline_ns = self.clock() + self.limits.metadata_ns
        try:
            if complete:
                await asyncio.wait_for(
                    asyncio.to_thread(attempt.reservation.complete),
                    max(0, (deadline_ns - self.clock()) / 1e9),
                )
            else:
                await asyncio.wait_for(
                    asyncio.to_thread(attempt.reservation.cancel),
                    max(0, (deadline_ns - self.clock()) / 1e9),
                )
            if not await self._release_reservation_pointer(attempt, deadline_ns):
                return
        except (StorageError, OSError, TimeoutError):
            return
        async with self._lock:
            if self.attempt is attempt:
                self.session.cleanup_confirmed = True
                if not complete:
                    self.attempt = None
                self._publish()

    async def stop_after_trial(
        self, command: svc.OperatorCommand, *, cancel: bool = False
    ) -> pb.CommandAdmission:
        async with self._lock:
            error = self._authorized(command)
            if error or self.session.phase != pb.SESSION_PHASE_RUNNING:
                return self._admission(
                    command.operator.command_id, error=error or "no running session"
                )
            if (
                cancel
                and self.trial.HasField("scheduled_end_monotonic_ns")
                and self.clock() > self.trial.scheduled_end_monotonic_ns
            ):
                return self._admission(
                    command.operator.command_id,
                    error="stop withdrawal is past trial boundary",
                )
            self.session.stop_after_trial = not cancel
            self._operation(
                command.operator.command_id,
                "CancelStopAfterTrial" if cancel else "StopAfterTrial",
                attempt=self.attempt,
                progress="stop preference updated",
                complete=True,
                succeeded=True,
            )
            self._publish()
            return self._admission(command.operator.command_id)

    async def abort_now(self, command: svc.OperatorCommand) -> pb.CommandAdmission:
        async with self._lock:
            error = self._authorized(command, safety="abort")
            attempt = self.attempt
            if (
                error
                or attempt is None
                or self.session.phase
                not in (pb.SESSION_PHASE_STARTING, pb.SESSION_PHASE_RUNNING)
            ):
                return self._admission(
                    command.operator.command_id, error=error or "Abort unavailable"
                )
            attempt.abort_command_ids.append(command.operator.command_id)
            self._operation(
                command.operator.command_id,
                "AbortNow",
                attempt=attempt,
                progress="interruption in progress",
                safety="abort",
            )
            self._spawn(self._interrupt(attempt, "operator Abort now"))
            return self._admission(command.operator.command_id)

    async def new_session(self, command: svc.OperatorCommand) -> pb.CommandAdmission:
        async with self._lock:
            error = self._authorized(command)
            if (
                error
                or self.session.phase != pb.SESSION_PHASE_ENDED
                or not self.session.cleanup_confirmed
            ):
                return self._admission(
                    command.operator.command_id,
                    error=error or "New session requires confirmed cleanup",
                )
            self.attempt = None
            self.session = pb.SessionState(
                phase=pb.SESSION_PHASE_CONFIGURATION, cleanup_confirmed=True
            )
            self.trial = pb.TrialState(phase=pb.TRIAL_PHASE_PENDING)
            self.projections.set_scope(pb.WorkContext(), self.configuration_revision)
            self._metadata.clear()
            self._metadata_latest_synced.clear()
            self._operation(
                command.operator.command_id,
                "NewSession",
                progress="new configuration session created",
                complete=True,
                succeeded=True,
            )
            self._publish()
            return self._admission(command.operator.command_id)

    async def shutdown_application(
        self, command: svc.OperatorCommand
    ) -> pb.CommandAdmission:
        async with self._lock:
            error = self._authorized(command, safety="shutdown")
            if error or self.session.shutdown_requested:
                return self._admission(
                    command.operator.command_id,
                    error=error or "shutdown already requested",
                )
            attempt = self.attempt
            issued_ns = self.clock()
            self._shutdown_intent_ns = issued_ns
            self.session.shutdown_requested = True
            self._operation(
                command.operator.command_id,
                "ShutdownApplication",
                attempt=attempt,
                progress="shutdown intent retained",
                safety="shutdown",
            )
            if attempt is not None:
                attempt.shutdown_command_ids.append(command.operator.command_id)
            self._publish()
            request = svc.ApplicationShutdownRequest(
                command_id=command.operator.command_id,
                controller=pb.ProcessIdentity(
                    role="controller", generation=self.generation
                ),
                supervisor=pb.ProcessIdentity(
                    role="supervisor", generation=self.supervisor_generation
                ),
                operator=command.operator,
                controller_operation=pb.OperationContext(
                    command_id=command.operator.command_id
                ),
                issued_monotonic_ns=issued_ns,
            )
            if attempt is not None:
                request.work.session.CopyFrom(attempt.context)
        if self.supervisor is not None:
            try:
                receipt = await asyncio.wait_for(
                    self.supervisor.request_shutdown(request),
                    self.limits.registration_ns / 1e9,
                )
                if receipt.result != pb.COMMAND_RESULT_ACCEPTED:
                    raise RuntimeError(
                        receipt.failure.message or "supervisor rejected shutdown"
                    )
            except Exception as exc:
                async with self._lock:
                    self._warnings.append(
                        pb.Warning(
                            warning_id=_id(),
                            component="shutdown",
                            message=f"supervisor handoff unconfirmed: {exc}",
                        )
                    )
                    self._publish()
        if attempt is not None:
            if attempt.activated:
                self._spawn(self._interrupt(attempt, "application shutdown"))
            else:
                attempt.cancel_requested = True
                if attempt.handoff is not None:
                    attempt.handoff.retire()
                self._spawn(self._cancel_attempt(attempt))
        else:
            async with self._lock:
                self._complete_operation(
                    command.operator.command_id,
                    success=True,
                    progress="shutdown handoff attempted",
                )
                self._publish()
        return self._admission(command.operator.command_id)

    async def save_configuration_history(
        self, command: svc.OperatorCommand
    ) -> pb.CommandAdmission:
        async with self._lock:
            error = self._authorized(command)
            if error or self.configuration_history_path is None:
                return self._admission(
                    command.operator.command_id,
                    error=error or "configuration history path unavailable",
                )
            path = self.configuration_history_path
            document = {"format_version": 1, "configuration": _json(self.configuration)}
            deadline_ns = self.clock() + self.limits.history_ns
            self._operation(
                command.operator.command_id,
                "SaveConfigurationHistory",
                progress="writing reusable configuration history",
            )
            self._publish()
        payload = json.dumps(
            document, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        try:
            await asyncio.wait_for(
                asyncio.to_thread(_atomic_json, path, payload, replace=True),
                max(0, (deadline_ns - self.clock()) / 1e9),
            )
        except Exception as exc:
            async with self._lock:
                self._warnings.append(
                    pb.Warning(
                        warning_id=_id(),
                        component="configuration_history",
                        message=f"save unconfirmed or failed: {exc}",
                    )
                )
                self._complete_operation(
                    command.operator.command_id,
                    success=False,
                    progress="history save unconfirmed or failed",
                    error=str(exc),
                )
                self._publish()
            return self._admission(
                command.operator.command_id,
                error=f"configuration history save unconfirmed or failed: {exc}",
            )
        async with self._lock:
            self._complete_operation(
                command.operator.command_id,
                success=True,
                progress="reusable configuration history saved",
            )
            self._publish()
        return self._admission(command.operator.command_id)

    async def supervisor_heartbeat(
        self, report: pb.HeartbeatReport, ingress_ns: int
    ) -> pb.ReportReceipt:
        if (
            report.source.role != "supervisor"
            or report.source.generation != self.supervisor_generation
        ):
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="IDENTITY", message="supervisor identity mismatch"
                ),
            )
        async with self._lock:
            self._supervisor_last_seen_ns = ingress_ns
        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    async def supervisor_status(
        self, report: svc.SupervisorStatusReport, ingress_ns: int
    ) -> pb.ReportReceipt:
        if (
            report.supervisor.role != "supervisor"
            or report.supervisor.generation != self.supervisor_generation
            or report.controller_generation != self.generation
        ):
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(code="IDENTITY", message="status identity mismatch"),
            )
        if len(report.processes) > 256:
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="CAPACITY",
                    message="supervisor process projection exceeds controller limit",
                ),
            )
        serialized = report.SerializeToString(deterministic=True)
        new_errors: list[pb.ErrorReport] = []
        async with self._lock:
            if report.status_revision < self._supervisor_status_revision:
                return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
            if report.status_revision == self._supervisor_status_revision:
                if serialized != self._supervisor_status_bytes:
                    return pb.ReportReceipt(
                        result=pb.COMMAND_RESULT_REJECTED,
                        failure=pb.Failure(
                            code="CONFLICT",
                            message="changed duplicate supervisor status",
                        ),
                    )
                self._supervisor_last_seen_ns = ingress_ns
                return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
            self._supervisor_status_revision = report.status_revision
            self._supervisor_status_bytes = serialized
            self._supervisor_last_seen_ns = ingress_ns
            self._supervisor_processes = {
                item.process.role: _copy(item) for item in report.processes
            }
            self._supervisor_all_processes = [_copy(item) for item in report.processes]
            self._supervisor_errors = [_copy(item) for item in report.errors[-256:]]
            self._supervisor_warnings = [_copy(item) for item in report.warnings[-256:]]
            self._supervisor_recoveries = [
                _copy(item) for item in report.recoveries[-256:]
            ]
            self._supervisor_operations = {
                item.context.command_id: _copy(item)
                for item in report.operations[-1024:]
            }
            attempt = self.attempt
            if attempt is not None:
                attempt.changed.set()
            if (
                attempt is not None
                and attempt.incidents is not None
                and self.session.phase
                in (pb.SESSION_PHASE_STARTING, pb.SESSION_PHASE_RUNNING)
            ):
                new_errors = [
                    _copy(item)
                    for item in report.errors
                    if item.error_id not in attempt.incident_errors
                    or item.SerializeToString(deterministic=True)
                    != attempt.incident_errors[item.error_id].SerializeToString(
                        deterministic=True
                    )
                ]
            self._publish()
        for error in new_errors:
            await self._observe_runtime_error(error)
        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    async def _observe_runtime_error(self, error: pb.ErrorReport) -> None:
        async with self._lock:
            attempt = self.attempt
            if (
                attempt is None
                or attempt.incidents is None
                or attempt.incident_topology is None
                or self.session.phase
                not in (pb.SESSION_PHASE_STARTING, pb.SESSION_PHASE_RUNNING)
            ):
                return
            now = self.clock()
            episode_id = (
                error.incident_episode_id
                if error.HasField("incident_episode_id")
                else error.error_id
            )
            episode_key = (error.source.role, error.source.generation, episode_id)
            deadline = attempt.episode_deadlines.get(
                episode_key, error.occurred_monotonic_ns + self.limits.recovery_ns
            )
            heartbeats = {
                (
                    status.last_heartbeat.source.role,
                    status.last_heartbeat.source.generation,
                ): _copy(status.last_heartbeat)
                for status in self._supervisor_all_processes
                if status.HasField("last_heartbeat")
            }
            proof = IsolationProof(
                continuing_heartbeats=heartbeats,
                controller_authority_valid=True,
                supervisor_authority_valid=now - self._supervisor_last_seen_ns
                <= self.health_silence_ns,
                bounded_accounting=True,
            )
            try:
                classification = classify_incident(
                    error,
                    attempt.incident_topology,
                    proof,
                    now_ns=now,
                    original_deadline_ns=deadline,
                    max_evidence_age_ns=self.health_silence_ns,
                )
                verified_scope = (
                    classification if classification.status == "continuable" else None
                )
                if classification.status == "continuable":
                    classification = type(classification)(
                        "pending",
                        "isolation proven; incident scope acknowledgements pending",
                        classification.affected_resources,
                        deadline,
                    )
                incident = attempt.incidents.observe(
                    error, classification, consequence=classification.reason
                )
            except (IncidentEvidenceError, IncidentCapacityError, ValueError) as exc:
                self._spawn(
                    self._interrupt(attempt, f"incident accounting invalid: {exc}")
                )
                return
            attempt.incident_errors[error.error_id] = _copy(error)
            attempt.episode_deadlines[episode_key] = deadline
            attempt.incident_deadlines[error.error_id] = deadline
            attempt.incident_id_by_error[error.error_id] = incident.incident_id
            existing_prompt_id = next(
                (
                    key
                    for key, (prompt, owner) in self._incident_prompts.items()
                    if owner is attempt
                    and prompt.runtime_incident.incident_id == incident.incident_id
                ),
                None,
            )
            prompt_id = existing_prompt_id or _id()
            if classification.status == "blocking":
                prompt = pb.Prompt(
                    prompt_id=prompt_id,
                    setup=attempt.context,
                    operation=error.operation,
                    explanation=classification.reason,
                    permitted_choices=["acknowledge"],
                    runtime_incident=incident,
                )
                self._incident_prompts[prompt.prompt_id] = (prompt, attempt)
                self._spawn(
                    self._interrupt(
                        attempt,
                        f"blocking incident: {classification.reason}",
                        issued_ns=error.occurred_monotonic_ns,
                    )
                )
            else:
                prompt = pb.Prompt(
                    prompt_id=prompt_id,
                    setup=attempt.context,
                    operation=error.operation,
                    explanation=classification.reason,
                    permitted_choices=["abort_session"],
                    runtime_incident=incident,
                )
                self._incident_prompts[prompt.prompt_id] = (prompt, attempt)
                self._spawn(self._incident_deadline(attempt, error.error_id, deadline))
                if verified_scope is not None:
                    affected = frozenset(verified_scope.affected_resources)
                    in_flight = attempt.scope_inflight.get(incident.incident_id)
                    if in_flight is None:
                        attempt.scope_inflight[incident.incident_id] = affected
                        self._spawn(
                            self._confirm_incident_scope(
                                attempt, error, incident, verified_scope, deadline
                            )
                        )
                    elif in_flight != affected:
                        self._spawn(
                            self._interrupt(
                                attempt,
                                "incident scope changed while confirmation was in flight",
                            )
                        )
            self._publish()
            if attempt.writer is not None:
                self._spawn(
                    self._incident_log(
                        attempt,
                        "error",
                        {
                            "error_id": error.error_id,
                            "incident_id": incident.incident_id,
                            "source_role": error.source.role,
                            "failure_code": error.failure.code,
                            "affected_resources": list(incident.affected_resources),
                            "classification": classification.status,
                        },
                    )
                )

    async def _confirm_incident_scope(
        self,
        attempt: Attempt,
        error: pb.ErrorReport,
        pending: pb.RuntimeIncident,
        classification: Any,
        deadline_ns: int,
    ) -> None:
        try:
            async with attempt.scope_lock:
                await self._confirm_incident_scope_serial(
                    attempt, error, pending, classification, deadline_ns
                )
        finally:
            attempt.scope_inflight.pop(pending.incident_id, None)

    async def _confirm_incident_scope_serial(
        self,
        attempt: Attempt,
        error: pb.ErrorReport,
        pending: pb.RuntimeIncident,
        classification: Any,
        deadline_ns: int,
    ) -> None:
        topology = attempt.incident_topology
        registered = attempt.registered_context
        if topology is None or registered is None or self.supervisor is None:
            await self._interrupt(attempt, "incident scope authority unavailable")
            return
        candidate = _copy(pending)
        candidate.revision += 1
        candidate.continuation_available = True
        candidate.consequence = classification.reason
        scope = _copy(registered)
        scope.ClearField("continuation_incidents")
        scope.continuation_incidents.extend(attempt.confirmed_incidents.values())
        scope.continuation_incidents.add().CopyFrom(candidate)
        registration = svc.RegisterContextRequest(command_id=_id(), context=scope)
        try:
            acknowledgement = await asyncio.wait_for(
                self.supervisor.register_context(registration),
                max(0, (deadline_ns - self.clock()) / 1e9),
            )
            if (
                acknowledgement.admission.result != pb.COMMAND_RESULT_ACCEPTED
                or acknowledgement.registered != scope
            ):
                raise RuntimeError("supervisor did not retain exact incident scope")
            affected = set(classification.affected_resources)
            healthy_names = {
                name
                for name in attempt.required
                if any(
                    function.resource_id not in affected
                    for function in attempt.ready[name].prepared_functions
                )
            }
            commands: dict[str, str] = {}
            requests: dict[str, svc.IncidentScopeRequest] = {}
            for name in healthy_names:
                command_id = _id()
                commands[name] = command_id
                requests[name] = svc.IncidentScopeRequest(
                    command=self._handoff_command(attempt, name, command_id),
                    incident=candidate,
                )
            async with self._lock:
                if self.attempt is not attempt or attempt.interrupted:
                    return
                for name, command_id in commands.items():
                    attempt.scope_commands[command_id] = (
                        name,
                        candidate.incident_id,
                        candidate.revision,
                    )
            replies = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        attempt.required[name].apply_incident_scope(requests[name])
                        for name in commands
                    )
                ),
                max(0, (deadline_ns - self.clock()) / 1e9),
            )
            if any(reply.result != pb.COMMAND_RESULT_ACCEPTED for reply in replies):
                raise RuntimeError("healthy coordinator rejected incident scope")
            if commands:
                initial_scope_deadline = min(
                    deadline_ns, self.clock() + self.limits.registration_ns
                )
                try:
                    await self._wait_evidence(
                        lambda: all(
                            command_id in attempt.scope_results
                            for command_id in commands.values()
                        ),
                        initial_scope_deadline,
                        attempt,
                    )
                except TimeoutError as exc:
                    for name, command_id in commands.items():
                        state = attempt.scope_results.get(command_id)
                        if state is not None:
                            continue
                        retained = await asyncio.wait_for(
                            attempt.required[name].get_retained_result(
                                svc.RetainedResultQuery(
                                    query=svc.BackendQuery(
                                        target=attempt.required[name].context,
                                        work=pb.WorkContext(session=attempt.context),
                                    ),
                                    command_id=command_id,
                                )
                            ),
                            max(0, (deadline_ns - self.clock()) / 1e9),
                        )
                        if (
                            not retained.found
                            or not retained.operation.complete
                            or not retained.operation.succeeded
                            or retained.operation.context.command_id != command_id
                        ):
                            raise RuntimeError(
                                f"{name} incident scope completion unconfirmed"
                            ) from exc
                        receipt = await self.report_lifecycle(
                            pb.LifecycleReport(
                                operation=pb.BackendOperationReport(
                                    source=attempt.required[name].context,
                                    operation=retained.operation,
                                )
                            ),
                            self.clock(),
                        )
                        if receipt.result != pb.COMMAND_RESULT_ACCEPTED:
                            raise RuntimeError(
                                f"{name} retained scope result was rejected"
                            ) from exc
            if any(
                not attempt.scope_results[command_id].succeeded
                for command_id in commands.values()
            ):
                raise RuntimeError("backend incident scope completed unsuccessfully")
            async with self._lock:
                if (
                    self.attempt is not attempt
                    or attempt.interrupted
                    or attempt.incidents is None
                    or self.clock() > deadline_ns
                ):
                    return
                confirmed = attempt.incidents.observe(
                    error, classification, consequence=classification.reason
                )
                if (
                    confirmed.incident_id != candidate.incident_id
                    or confirmed.revision != candidate.revision
                ):
                    raise RuntimeError("incident scope changed during registration")
                attempt.confirmed_incidents[confirmed.incident_id] = _copy(confirmed)
                attempt.registered_context = _copy(scope)
                for plan in attempt.prepared.trials:
                    plan.continuation_incidents.add().CopyFrom(confirmed)
                for prompt_id, (prompt, owner) in list(self._incident_prompts.items()):
                    if (
                        owner is attempt
                        and prompt.runtime_incident.incident_id == confirmed.incident_id
                    ):
                        prompt.runtime_incident.CopyFrom(confirmed)
                        prompt.explanation = classification.reason
                        prompt.permitted_choices[:] = [
                            "continue_session",
                            "abort_session",
                        ]
                        self._incident_prompts[prompt_id] = (prompt, owner)
                self._publish()
                if attempt.writer is not None:
                    self._spawn(
                        self._incident_log(
                            attempt,
                            "incident_scope",
                            {
                                "incident_id": confirmed.incident_id,
                                "incident_revision": confirmed.revision,
                                "affected_resources": list(
                                    confirmed.affected_resources
                                ),
                            },
                        )
                    )
        except Exception as exc:
            await self._interrupt(
                attempt, f"incident scope could not be confirmed: {exc}"
            )

    async def _incident_deadline(
        self, attempt: Attempt, error_id: str, deadline_ns: int
    ) -> None:
        await asyncio.sleep(max(0, (deadline_ns - self.clock()) / 1e9))
        async with self._lock:
            if (
                self.attempt is not attempt
                or attempt.interrupted
                or self.session.phase
                not in (pb.SESSION_PHASE_STARTING, pb.SESSION_PHASE_RUNNING)
                or error_id not in attempt.incident_errors
                or attempt.incident_id_by_error.get(error_id)
                in attempt.confirmed_incidents
            ):
                return
        await self._interrupt(
            attempt,
            f"incident {error_id} unresolved at original recovery deadline",
            issued_ns=deadline_ns,
        )
