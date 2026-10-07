"""E02/E05 controller authority and experiment lifecycle.

Backends are injected registered peers. Their command admissions are never treated
as Ready, Started, Stopped or Finished evidence.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.assembly import AssemblyInputs, assemble_controller
from cephvr.controller.configuration import ControllerConfiguration
from cephvr.controller.device.owner_cleanup import (
    MANUAL_CLEANUP_TASK_NAME,
    record_manual_cleanup_warning,
)
from cephvr.controller.device.spikeglx_inventory import SpikeGLXInventory
from cephvr.controller.microcontroller.device import MicrocontrollerDevice
from cephvr.controller.microcontroller.lifecycle import MicrocontrollerLifecycle
from cephvr.controller.ports import BackendPort, SpikeGLXPort, SupervisorPort
from cephvr.controller.projections import ProjectionStore
from cephvr.controller.state import (
    Attempt,
    AuthorityStatus,
    ConfigurationState,
    ControllerLimits,
    ControlState,
    DeviceState,
    IncidentState,
    LifecycleState,
    LimitsState,
    MetadataState,
    SupervisorState,
    Watch,
)
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger


def _id() -> str:
    return str(uuid.uuid4())


class ControllerRuntime:
    """One asyncio loop serializes state transitions; I/O uses bounded workers."""

    def __init__(
        self,
        *,
        generation: str,
        configuration: pb.ExperimentConfiguration,
        policies: pb.ControlPolicies | None = None,
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
        file_policy_loader: Callable[[frozenset[str]], Mapping[str, Message]]
        | None = None,
        settings_loader: Callable[[], ControllerConfiguration] | None = None,
        startup_settings: ControllerConfiguration | None = None,
        reservation_started: Callable[[Attempt], Awaitable[None]] | None = None,
        reservation_released: Callable[[Attempt], Awaitable[None]] | None = None,
        initial_startup_blocker: str | None = None,
        display_validator: Callable[[str], frozenset[str]] | None = None,
        display_pacing_resolver: Callable[[str, Message], str] | None = None,
        software_root: Path | None = None,
        max_preparation_bytes: int = 16_777_216,
        max_incident_bytes: int = 1_048_576,
        max_operation_records: int = 1024,
        health_silence_ns: int = 15_000_000_000,
        clock: Callable[[], int] = host_time_ns,
        microcontroller_device: MicrocontrollerDevice | None = None,
    ) -> None:
        self.microcontroller_device = microcontroller_device
        self.generation = generation
        effective = pb.ExperimentConfiguration()
        effective.CopyFrom(configuration)
        effective_policies = pb.ControlPolicies()
        if policies is not None:
            effective_policies.CopyFrom(policies)
        self.configuration_state = ConfigurationState(effective, effective_policies)
        self.limit_state = LimitsState(limits)
        registered_backends = dict(backends)
        validation_ports = dict(validators)
        self.supervisor_generation = supervisor_generation
        if (settings_loader is None) != (startup_settings is None):
            raise ValueError(
                "Setup settings loader requires its startup-fixed baseline"
            )
        if max_preparation_bytes <= 0:
            raise ValueError("preparation descriptor budget must be positive")
        if (
            max_incident_bytes <= 0
            or health_silence_ns <= 0
            or max_operation_records < 3
        ):
            raise ValueError("incident and health budgets must be positive")
        self.projections = ProjectionStore(
            generation,
            {name: backend.context for name, backend in backends.items()},
            max_entries=limits.max_retained_incidents,
            max_payload_bytes=max_preparation_bytes,
        )
        self.projections.set_scope(pb.WorkContext(), self.configuration_state.revision)
        self.clock = clock
        self.lifecycle = LifecycleState(startup_blocker=initial_startup_blocker or "")
        self.control = ControlState()
        self.metadata_state = MetadataState(limits.max_metadata_operations)
        self.supervisor_state = SupervisorState(last_seen_ns=self.clock())
        self.incident_state = IncidentState()
        self.device_state = DeviceState()
        if history_warning:
            self.control.add_warning("configuration_history", history_warning)
        self._tasks: set[asyncio.Task[object]] = set()
        self.lifecycle.startup_warning_id = _id() if initial_startup_blocker else ""
        components = assemble_controller(
            AssemblyInputs(
                generation=self.generation,
                microcontroller_device=microcontroller_device,
                supervisor_generation=self.supervisor_generation,
                configuration_state=self.configuration_state,
                lifecycle=self.lifecycle,
                control=self.control,
                metadata_state=self.metadata_state,
                supervisor_state=self.supervisor_state,
                incident_state=self.incident_state,
                device_state=self.device_state,
                limit_state=self.limit_state,
                projections=self.projections,
                backends=registered_backends,
                supervisor=supervisor,
                spikeglx=spikeglx,
                validators=validation_ports,
                file_policy_loader=file_policy_loader,
                display_validator=display_validator,
                display_pacing_resolver=display_pacing_resolver,
                software_root=software_root,
                output_planner=output_planner,
                schema_factory=schema_factory,
                settings_loader=settings_loader,
                startup_settings=startup_settings,
                configuration_history_path=configuration_history_path,
                reservation_started=reservation_started,
                reservation_released=reservation_released,
                max_preparation_bytes=max_preparation_bytes,
                max_incident_bytes=max_incident_bytes,
                max_operation_records=max_operation_records,
                health_silence_ns=health_silence_ns,
                clock=self.clock,
                spawn=self._spawn,
            )
        )
        self.control_operations = components.control_operations
        self.preparation_context = components.preparation_context
        self.publisher = components.publisher
        self.leases = components.leases
        self.metadata = components.metadata
        self.display = components.display
        self.display_calibration = components.display_calibration
        self.camera = components.camera
        self.microcontroller = components.microcontroller
        self.camera_readback = components.camera_readback
        self.device_views = components.device_views
        self.camera_status_retention = components.camera_status_retention
        self.preview = components.preview
        self.cleanup = components.cleanup
        self.configuration_commands = components.configuration_commands
        self.lifecycle_reports = components.lifecycle_reports
        self.evidence_waiter = components.evidence_waiter
        self.trial_logs = components.trial_logs
        self.interruption = components.interruption
        self.session_commands = components.session_commands
        self.supervision = components.supervision
        self.prompts = components.prompts
        self.trials = components.trials
        self.start = components.start
        self.handoffs = components.handoffs
        self.setup_execution = components.setup_execution
        self.setup_admission = components.setup_admission
        self.acquisition_resolution = components.acquisition_resolution
        self.tracking_diagnostic = components.tracking_diagnostic
        self.spikeglx_inventory: SpikeGLXInventory | None = (
            components.spikeglx_inventory
        )
        self.leases.observe_owner_loss(self.tracking_diagnostic.owner_lost)
        self.publisher.observe_owner_loss(self.tracking_diagnostic.owner_lost)
        self.leases.observe_owner_loss(self.display_calibration.owner_lost)
        self.publisher.observe_owner_loss(self.display_calibration.owner_lost)
        self.microcontroller_lifecycle = None
        if microcontroller_device is not None:
            microcontroller_device.changed = self.publisher.publish
            self.publisher.microcontroller_view = microcontroller_device.snapshot_view
            self.microcontroller_lifecycle = MicrocontrollerLifecycle(
                microcontroller_device,
                generation=self.generation,
                lifecycle=self.lifecycle,
                configuration=self.configuration_state,
                device=self.device_state,
                limits=self.limit_state,
                clock=self.clock,
                publish=self.publisher.publish,
                warning=self.record_warning,
                spawn=self._spawn,
                interrupt=lambda attempt, reason, issued: self.interruption.interrupt(
                    attempt, reason, issued_ns=issued
                ),
            )
            self.leases.observe_owner_loss(self.microcontroller_lifecycle.owner_lost)
            self.publisher.observe_owner_loss(self.microcontroller_lifecycle.owner_lost)

    def start_microcontroller_health(self) -> asyncio.Task[Any] | None:
        if self.microcontroller_lifecycle is None:
            return None
        return self._spawn(self.microcontroller_lifecycle.health().run(asyncio.Event()))

    async def execute_microcontroller_io(
        self, request: svc.MicrocontrollerIoRequest
    ) -> svc.MicrocontrollerIoResult:
        if self.microcontroller_lifecycle is None:
            raise RuntimeError("Controller Microcontroller owner is unavailable")
        return await self.microcontroller_lifecycle.execute(request)

    def bind_microcontroller_shutdown_deadline(self, deadline_ns: int) -> None:
        if self.microcontroller_lifecycle is not None:
            self.microcontroller_lifecycle.bind_shutdown_deadline(deadline_ns)

    def current_work_key(self) -> str | None:
        attempt = self.lifecycle.attempt
        return attempt.context.session_id if attempt is not None else None

    @property
    def limits(self) -> ControllerLimits:
        return self.limit_state.current

    def bind_camera_status_retention(self, ledger: CommandLedger) -> None:
        """Bind the public admission ledger before camera RPCs are served."""
        self.camera_status_retention.bind_ledger(ledger)

    def command_work_complete(self, key: str) -> bool:
        operation = self.control.operations.get(key)
        return operation is not None and operation.complete

    def clean_work_retired(self) -> bool:
        return (
            self.lifecycle.session.cleanup_confirmed
            and self.lifecycle.session.phase
            in (
                pb.SESSION_PHASE_CONFIGURATION,
                pb.SESSION_PHASE_ENDED,
            )
        )

    def ingress_exhausted(self, reason: str) -> None:
        attempt = self.lifecycle.attempt
        if attempt is not None:
            self._spawn(self.interruption.interrupt(attempt, reason))

    async def safety_command_precondition(
        self, request: svc.OperatorCommand, kind: Literal["abort", "shutdown"]
    ) -> str | None:
        if kind not in {"abort", "shutdown"}:
            raise ValueError("unknown safety command")
        return await self.session_commands.safety_precondition(request, kind)

    def authority_status(self) -> AuthorityStatus:
        status = AuthorityStatus.capture(
            self.lifecycle, self.control, self.supervisor_state
        )
        if (
            self.microcontroller_device is not None
            and not self.microcontroller_device.cleanup_complete
        ):
            status = replace(status, cleanup_confirmed=False)
        return status

    async def record_warning(self, warning: pb.Warning) -> None:
        async with self.lifecycle.lock:
            self.control.warnings.append(deepcopy(warning))
            self.publisher.publish()

    async def cancel_background_tasks(self) -> None:
        self.lifecycle.manual_control_cleanup_stopping = True
        manual_cleanup = self.lifecycle.manual_control_cleanup_task
        pending = tuple(task for task in self._tasks if task is not manual_cleanup)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if manual_cleanup is not None and not manual_cleanup.done():
            try:
                # Retries are unbounded while pending; shutdown waits one Setup budget.
                await asyncio.wait_for(
                    asyncio.shield(manual_cleanup), self.limits.setup_ns / 1e9
                )
            except Exception:
                # The task's retained cleanup failure is already published by
                # its normal completion callback; the barrier remains in state.
                pass
            # The chain may have advanced to a later task before stopping.
            current = self.lifecycle.manual_control_cleanup_task or manual_cleanup
            if not current.done():
                current.cancel()
                await asyncio.gather(current, return_exceptions=True)

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
        if task.get_name() == MANUAL_CLEANUP_TASK_NAME:
            # A device-cleanup blocker, not an experiment fault: the pending
            # barrier stays and the task retries itself, so never interrupt.
            record_manual_cleanup_warning(self.control, self.publisher.publish, error)
            return
        if error is None:
            return
        self.control.add_warning("controller", f"background operation failed: {error}")
        self.publisher.publish()
        attempt = self.lifecycle.attempt
        if (
            attempt is not None
            and not attempt.interrupted
            and not self.lifecycle.authority_lost
        ):
            self._spawn(
                self.interruption.interrupt(
                    attempt, f"controller background operation failed: {error}"
                )
            )

    async def install_startup_recovery(
        self,
        prompt: pb.Prompt | None,
        handler: Callable[[], Awaitable[None]] | None,
        blocker: str | None,
        completion_warning: str | None = None,
        notice: str | None = None,
    ) -> None:
        await self.prompts.install_startup_recovery(
            prompt, handler, blocker, completion_warning, notice
        )

    async def snapshot(self) -> pb.Snapshot:
        return await self.publisher.snapshot()

    async def open_watch(self, client_id: str, watch_id: str) -> Watch:
        return await self.publisher.open_watch(client_id, watch_id)

    async def delivered_watch_view(self, watch: Watch, revision: int) -> None:
        await self.publisher.delivered_watch_view(watch, revision)

    async def close_watch(self, watch: Watch) -> None:
        await self.publisher.close_watch(watch)

    async def claim(
        self, claim: svc.ControlClaim, *, takeover: bool = False
    ) -> pb.CommandAdmission:
        return await self.leases.claim(claim, takeover=takeover)

    async def release_control(
        self, command: svc.OperatorCommand
    ) -> pb.CommandAdmission:
        return await self.leases.release_control(command)

    async def update_configuration(
        self, request: svc.UpdateConfigurationRequest
    ) -> pb.CommandAdmission:
        return await self.configuration_commands.update_configuration(request)

    async def get_spikeglx_inventory(
        self, request: svc.SpikeGLXInventoryRequest
    ) -> tuple[svc.SpikeGLXInventorySnapshot | None, str]:
        if self.spikeglx_inventory is None:
            return None, "SpikeGLX inventory service unavailable"
        return await self.spikeglx_inventory.read(request)

    async def update_spikeglx_inventory(
        self, request: svc.SpikeGLXInventoryUpdateRequest
    ) -> pb.CommandAdmission:
        if self.spikeglx_inventory is None:
            return pb.CommandAdmission(
                result=pb.COMMAND_RESULT_REJECTED,
                command_id=request.command.operator.command_id,
                failure=pb.Failure(
                    code="UNAVAILABLE", message="SpikeGLX inventory service unavailable"
                ),
            )
        return await self.spikeglx_inventory.update(request)

    async def save_configuration_history(
        self, command: svc.OperatorCommand
    ) -> pb.CommandAdmission:
        return await self.configuration_commands.save_configuration_history(command)

    async def initialize_display(self) -> pb.CommandAdmission:
        return await self.display.initialize_display()

    async def open_display_calibration(
        self, request: svc.OpenDisplayCalibrationRequest
    ) -> pb.CommandAdmission:
        return await self.display_calibration.open(request)

    async def close_display_calibration(
        self, request: svc.CloseDisplayCalibrationRequest
    ) -> pb.CommandAdmission:
        return await self.display_calibration.close(request)

    async def execute_camera_command(
        self, request: svc.CameraCommandRequest
    ) -> pb.CommandAdmission:
        return await self.camera.execute_camera_command(request)

    async def execute_microcontroller_command(
        self, request: svc.MicrocontrollerCommandRequest
    ) -> pb.CommandAdmission:
        return await self.microcontroller.execute(request)

    async def setup(self, command: svc.OperatorCommand) -> pb.CommandAdmission:
        owner = self.microcontroller_device
        if owner is not None and (
            owner.busy
            or owner.releasing
            or owner.closing
            or owner.closed
            or owner.view.diagnostic.active
            or owner.failure
        ):
            return self.control_operations.admission(
                command.operator.command_id,
                error="Stop Microcontroller diagnostics and confirm device/native cleanup before Setup",
            )
        return await self.setup_admission.setup(command)

    async def begin_tracking_diagnostic(
        self, request: svc.BeginTrackingDiagnosticRequest
    ) -> pb.CommandAdmission:
        return await self.tracking_diagnostic.begin(request)

    async def close_tracking_diagnostic(
        self, request: svc.CloseTrackingDiagnosticRequest
    ) -> pb.CommandAdmission:
        return await self.tracking_diagnostic.close(request)

    async def get_tracking_diagnostic_state(
        self, request: svc.TrackingDiagnosticQuery
    ) -> pb.TrackingDiagnosticState:
        return await self.tracking_diagnostic.query(request)

    async def cancel_setup(self, command: svc.OperatorCommand) -> pb.CommandAdmission:
        return await self.cleanup.cancel_setup(command)

    async def report_data_preparation(
        self, report: svc.DataPreparationReport, ingress_ns: int
    ) -> pb.ReportReceipt:
        return await self.handoffs.report_data_preparation(report, ingress_ns)

    async def report_acquisition_resolution(
        self, report: svc.AcquisitionResolutionReport, ingress_ns: int
    ) -> pb.ReportReceipt:
        return await self.acquisition_resolution.report_acquisition_resolution(
            report, ingress_ns
        )

    async def report_projection(
        self, kind: str, report: Message, ingress_ns: int | None = None
    ) -> pb.ReportReceipt:
        return await self.device_views.report_projection(kind, report, ingress_ns)

    async def get_preview_attachment(
        self, query: svc.PreviewAttachmentQuery
    ) -> svc.PreviewAttachmentResult:
        return await self.preview.get_preview_attachment(query)

    async def report_preview_consumer_state(
        self, report: svc.PreviewConsumerReport
    ) -> pb.ReportReceipt:
        return await self.preview.report_preview_consumer_state(report)

    async def respond_to_prompt(
        self, request: svc.PromptResponse
    ) -> pb.CommandAdmission:
        return await self.prompts.respond_to_prompt(request)

    async def report_lifecycle(
        self, report: pb.LifecycleReport, ingress_ns: int
    ) -> pb.ReportReceipt:
        return await self.lifecycle_reports.receive(report, ingress_ns)

    async def authority_loss(self, reason: str, issued_ns: int) -> None:
        if self.microcontroller_lifecycle is not None:
            self.microcontroller_lifecycle.prepare_authority_close(issued_ns)
        await self.interruption.authority_loss(reason, issued_ns)
        if self.microcontroller_lifecycle is not None:
            await self.microcontroller_lifecycle.close_authority(issued_ns)

    async def report_interruption(
        self, report: svc.InterruptionReport
    ) -> pb.ReportReceipt:
        return await self.interruption.report_interruption(report)

    async def start_session(self, command: svc.OperatorCommand) -> pb.CommandAdmission:
        return await self.start.start_session(command)

    async def stop_after_trial(
        self, command: svc.OperatorCommand, *, cancel: bool = False
    ) -> pb.CommandAdmission:
        return await self.session_commands.stop_after_trial(command, cancel=cancel)

    async def abort_now(self, command: svc.OperatorCommand) -> pb.CommandAdmission:
        return await self.session_commands.abort_now(command)

    async def new_session(self, command: svc.OperatorCommand) -> pb.CommandAdmission:
        return await self.session_commands.new_session(command)

    async def shutdown_application(
        self, command: svc.OperatorCommand
    ) -> pb.CommandAdmission:
        admission = await self.session_commands.shutdown_application(command)
        if (
            admission.result == pb.COMMAND_RESULT_ACCEPTED
            and self.microcontroller_lifecycle is not None
        ):
            self._spawn(
                self.microcontroller_lifecycle.shutdown(
                    self.lifecycle.shutdown_intent_ns
                )
            )
        return admission

    async def supervisor_heartbeat(
        self, heartbeat: pb.HeartbeatReport, ingress_ns: int
    ) -> pb.ReportReceipt:
        return await self.supervision.supervisor_heartbeat(heartbeat, ingress_ns)

    async def supervisor_status(
        self, report: svc.SupervisorStatusReport, ingress_ns: int
    ) -> pb.ReportReceipt:
        return await self.supervision.supervisor_status(report, ingress_ns)
