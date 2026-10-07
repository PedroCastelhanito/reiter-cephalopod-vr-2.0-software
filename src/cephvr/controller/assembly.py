"""Application assembly for controller components and their explicit dependencies."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google.protobuf.message import Message

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.configuration import ControllerConfiguration
from cephvr.controller.control.configuration import ConfigurationCommands
from cephvr.controller.control.leases import ControlLeases
from cephvr.controller.control.operations import ControlOperations
from cephvr.controller.control.prompts import OperatorPrompts
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.device.camera import CameraCommands
from cephvr.controller.device.display import DisplayInitialization
from cephvr.controller.device.display_calibration import DisplayCalibrationController
from cephvr.controller.device.microcontroller import MicrocontrollerCommands
from cephvr.controller.device.owner_cleanup import ManualControlCleanup
from cephvr.controller.device.ports import DeviceHooks
from cephvr.controller.device.preview import PreviewHandling
from cephvr.controller.device.readback import CameraReadback
from cephvr.controller.device.spikeglx_inventory import SpikeGLXInventory
from cephvr.controller.device.spikeglx_monitor import SpikeGLXProgressMonitor
from cephvr.controller.device.status_retention import CameraStatusRetention
from cephvr.controller.device.tracking_diagnostic import TrackingDiagnosticController
from cephvr.controller.device.views import DeviceViews
from cephvr.controller.incident.coordination import IncidentCoordinator
from cephvr.controller.lifecycle.acquisition_resolution import AcquisitionResolution
from cephvr.controller.lifecycle.activity import activity_requirements, source_producers
from cephvr.controller.lifecycle.cleanup import CleanupWorkflow
from cephvr.controller.lifecycle.commands import SessionCommands
from cephvr.controller.lifecycle.evidence_wait import EvidenceWaiter
from cephvr.controller.lifecycle.handoffs import PreparationHandoffs
from cephvr.controller.lifecycle.interruption import InterruptionWorkflow
from cephvr.controller.lifecycle.preparation_context import PreparationContext
from cephvr.controller.lifecycle.setup_admission import SetupAdmission
from cephvr.controller.lifecycle.setup_execution import SetupExecution
from cephvr.controller.lifecycle.start import StartActivation
from cephvr.controller.lifecycle.trials import TrialExecution
from cephvr.controller.lifecycle_reports import LifecycleReports, ReportHooks
from cephvr.controller.metadata.coordination import MetadataCoordinator
from cephvr.controller.metadata.trial_logs import TrialLogs
from cephvr.controller.microcontroller.device import MicrocontrollerDevice
from cephvr.controller.ports import BackendPort, SpikeGLXPort, SupervisorPort
from cephvr.controller.projections import ProjectionStore
from cephvr.controller.state import (
    Attempt,
    ConfigurationState,
    ControlState,
    DeviceState,
    IncidentState,
    LifecycleState,
    LimitsState,
    MetadataState,
    SupervisorState,
)
from cephvr.controller.supervision import SupervisorObservations


@dataclass(frozen=True)
class AssemblyInputs:
    generation: str
    supervisor_generation: str
    configuration_state: ConfigurationState
    lifecycle: LifecycleState
    control: ControlState
    metadata_state: MetadataState
    supervisor_state: SupervisorState
    incident_state: IncidentState
    device_state: DeviceState
    limit_state: LimitsState
    projections: ProjectionStore
    backends: Mapping[str, BackendPort]
    supervisor: SupervisorPort | None
    spikeglx: SpikeGLXPort | None
    validators: Mapping[
        str, Callable[[pb.ExperimentConfiguration], pb.ValidationResult]
    ]
    file_policy_loader: Callable[[frozenset[str]], Mapping[str, Message]] | None
    display_validator: Callable[[str], frozenset[str]] | None
    output_planner: (
        Callable[
            [pb.PreparedSession, Mapping[str, pb.ReadyReport]], list[pb.OutputPlan]
        ]
        | None
    )
    schema_factory: Callable[[pb.PreparedSession], dict[str, object]] | None
    settings_loader: Callable[[], ControllerConfiguration] | None
    startup_settings: ControllerConfiguration | None
    configuration_history_path: Path | None
    reservation_started: Callable[[Attempt], Awaitable[None]] | None
    reservation_released: Callable[[Attempt], Awaitable[None]] | None
    max_preparation_bytes: int
    max_incident_bytes: int
    max_operation_records: int
    health_silence_ns: int
    clock: Callable[[], int]
    spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]]
    display_pacing_resolver: Callable[[str, Message], str] | None = None
    software_root: Path | None = None
    microcontroller_device: MicrocontrollerDevice | None = None


@dataclass(frozen=True)
class ControllerComponents:
    control_operations: ControlOperations
    preparation_context: PreparationContext
    publisher: SnapshotPublisher
    leases: ControlLeases
    metadata: MetadataCoordinator
    display: DisplayInitialization
    display_calibration: DisplayCalibrationController
    camera: CameraCommands
    microcontroller: MicrocontrollerCommands
    camera_readback: CameraReadback
    device_views: DeviceViews
    camera_status_retention: CameraStatusRetention
    preview: PreviewHandling
    cleanup: CleanupWorkflow
    configuration_commands: ConfigurationCommands
    lifecycle_reports: LifecycleReports
    evidence_waiter: EvidenceWaiter
    trial_logs: TrialLogs
    interruption: InterruptionWorkflow
    session_commands: SessionCommands
    supervision: SupervisorObservations
    prompts: OperatorPrompts
    trials: TrialExecution
    start: StartActivation
    handoffs: PreparationHandoffs
    setup_execution: SetupExecution
    setup_admission: SetupAdmission
    acquisition_resolution: AcquisitionResolution
    tracking_diagnostic: TrackingDiagnosticController
    spikeglx_monitor: SpikeGLXProgressMonitor | None
    spikeglx_inventory: SpikeGLXInventory | None


def assemble_controller(i: AssemblyInputs) -> ControllerComponents:
    camera_status_retention = CameraStatusRetention(i.device_state, i.clock)
    control_operations = ControlOperations(
        lifecycle=i.lifecycle,
        configuration=i.configuration_state,
        control=i.control,
        generation=i.generation,
        max_operation_records=i.max_operation_records,
        clock=i.clock,
    )
    preparation_context = PreparationContext(
        configuration=i.configuration_state,
        supervisor=i.supervisor_state,
        generation=i.generation,
        supervisor_generation=i.supervisor_generation,
    )
    publisher = SnapshotPublisher(
        generation=i.generation,
        clock=i.clock,
        configuration=i.configuration_state,
        lifecycle=i.lifecycle,
        control=i.control,
        metadata=i.metadata_state,
        supervisor=i.supervisor_state,
        incidents=i.incident_state,
        projections=i.projections,
        limits=i.limit_state,
    )
    leases = ControlLeases(
        lifecycle=i.lifecycle,
        control=i.control,
        operations=control_operations,
        publisher=publisher,
        generation=i.generation,
    )
    metadata = MetadataCoordinator(
        lifecycle=i.lifecycle,
        control=i.control,
        metadata_state=i.metadata_state,
        limits=i.limit_state,
        clock=i.clock,
        publish=publisher.publish,
        spawn=i.spawn,
    )
    device_hooks = DeviceHooks(
        admission=control_operations.admission,
        authorized=control_operations.authorized,
        operation=control_operations.operation,
        complete_operation=control_operations.complete_operation,
        prune_operations=control_operations.prune_operations,
        publish=publisher.publish,
        spawn=i.spawn,
    )
    display = DisplayInitialization(
        lifecycle=i.lifecycle,
        configuration=i.configuration_state,
        control=i.control,
        device=i.device_state,
        backends=i.backends,
        projections=i.projections,
        file_policy_loader=i.file_policy_loader,
        display_validator=i.display_validator,
        display_pacing_resolver=i.display_pacing_resolver,
        generation=i.generation,
        limits=i.limit_state,
        max_operation_records=i.max_operation_records,
        clock=i.clock,
        hooks=device_hooks,
    )
    display_calibration = DisplayCalibrationController(
        lifecycle=i.lifecycle,
        configuration=i.configuration_state,
        control=i.control,
        device=i.device_state,
        backends=i.backends,
        projections=i.projections,
        file_policy_loader=i.file_policy_loader,
        display_validator=i.display_validator,
        display_pacing_resolver=i.display_pacing_resolver,
        generation=i.generation,
        limits=i.limit_state,
        hooks=device_hooks,
        maximum_asset_bytes=i.max_preparation_bytes,
        clock=i.clock,
    )
    camera = CameraCommands(
        lifecycle=i.lifecycle,
        configuration=i.configuration_state,
        device=i.device_state,
        backends=i.backends,
        projections=i.projections,
        file_policy_loader=i.file_policy_loader,
        generation=i.generation,
        limits=i.limit_state,
        clock=i.clock,
        hooks=device_hooks,
        status_retention=camera_status_retention,
    )
    acquisition_views = i.projections
    microcontroller = MicrocontrollerCommands(
        lifecycle=i.lifecycle,
        configuration=i.configuration_state,
        device=i.device_state,
        owner=i.microcontroller_device,
        limits=i.limit_state,
        clock=i.clock,
        hooks=device_hooks,
        device_views=lambda: acquisition_views.devices,
    )

    owner_cleanup = ManualControlCleanup(
        lifecycle=i.lifecycle,
        configuration=i.configuration_state,
        device=i.device_state,
        backends=i.backends,
        projections=i.projections,
        file_policy_loader=i.file_policy_loader,
        generation=i.generation,
        limits=i.limit_state,
        clock=i.clock,
        hooks=device_hooks,
        status_retention=camera_status_retention,
    )
    leases.bind_owner_loss(owner_cleanup.request)
    publisher.bind_owner_loss(owner_cleanup.request)
    camera_readback = CameraReadback(
        lifecycle=i.lifecycle,
        configuration=i.configuration_state,
        device=i.device_state,
        backends=i.backends,
        projections=i.projections,
        validators=i.validators,
        generation=i.generation,
        clock=i.clock,
        hooks=device_hooks,
        status_retention=camera_status_retention,
    )
    device_views = DeviceViews(
        lifecycle=i.lifecycle,
        configuration=i.configuration_state,
        device=i.device_state,
        projections=i.projections,
        clock=i.clock,
        hooks=device_hooks,
        finish_camera_operation=camera_readback.finish_camera_operation,
        status_retention=camera_status_retention,
    )
    preview = PreviewHandling(
        lifecycle=i.lifecycle,
        device=i.device_state,
        backends=i.backends,
        supervisor=i.supervisor,
        projections=i.projections,
        limits=i.limit_state,
        hooks=device_hooks,
        finish_camera_operation=camera_readback.finish_camera_operation,
    )
    cleanup = CleanupWorkflow(
        lifecycle=i.lifecycle,
        control=i.control,
        incidents=i.incident_state,
        limit_state=i.limit_state,
        clock=i.clock,
        publisher=publisher,
        control_operations=control_operations,
        supervisor=i.supervisor,
        max_incident_bytes=i.max_incident_bytes,
        reservation_released=i.reservation_released,
        generation=i.generation,
        spawn=i.spawn,
        configuration=i.configuration_state,
        projections=i.projections,
    )
    configuration_commands = ConfigurationCommands(
        lifecycle=i.lifecycle,
        configuration=i.configuration_state,
        control=i.control,
        device=i.device_state,
        limits=i.limit_state,
        validators=i.validators,
        cleanup=cleanup,
        projections=i.projections,
        publisher=publisher,
        operations=control_operations,
        configuration_history_path=i.configuration_history_path,
        clock=i.clock,
        spawn=i.spawn,
        microcontroller_active=lambda: (
            i.microcontroller_device is not None
            and (
                i.microcontroller_device.view.diagnostic.active
                or i.microcontroller_device.closing
            )
        ),
    )

    def warn_controller(message: str) -> None:
        i.control.add_warning("controller", message)
        publisher.publish()

    camera.bind_recovery(device_views.report_projection, warn_controller)

    lifecycle_reports = LifecycleReports(
        lifecycle=i.lifecycle,
        configuration=i.configuration_state,
        supervisor=i.supervisor_state,
        limits=i.limit_state,
        hooks=ReportHooks(
            publish=publisher.publish,
            spawn=i.spawn,
            late_cleanup=cleanup.late_cleanup,
            log_event=metadata.log_event,
            activity_requirements=activity_requirements,
            source_producers=source_producers,
            clock=i.clock,
            warn=warn_controller,
        ),
    )
    cleanup.bind_report(lifecycle_reports.receive)
    evidence_waiter = EvidenceWaiter(
        lifecycle=i.lifecycle,
        control=i.control,
        limits=i.limit_state,
        clock=i.clock,
        publisher=publisher,
        report=lifecycle_reports.receive,
    )
    trial_logs = TrialLogs(
        lifecycle=i.lifecycle,
        control=i.control,
        limits=i.limit_state,
        metadata=metadata,
        evidence_waiter=evidence_waiter,
        clock=i.clock,
        spawn=i.spawn,
        publish=publisher.publish,
    )
    interruption = InterruptionWorkflow(
        lifecycle=i.lifecycle,
        control=i.control,
        incidents=i.incident_state,
        supervisor_state=i.supervisor_state,
        limit_state=i.limit_state,
        cleanup=cleanup,
        metadata=metadata,
        trial_logs=trial_logs,
        spikeglx=i.spikeglx,
        publisher=publisher,
        generation=i.generation,
        supervisor_generation=i.supervisor_generation,
        clock=i.clock,
        spawn=i.spawn,
    )
    session_commands = SessionCommands(
        lifecycle=i.lifecycle,
        configuration=i.configuration_state,
        control=i.control,
        metadata_state=i.metadata_state,
        limit_state=i.limit_state,
        cleanup=cleanup,
        interruption=interruption,
        publisher=publisher,
        operations=control_operations,
        projections=i.projections,
        supervisor=i.supervisor,
        generation=i.generation,
        supervisor_generation=i.supervisor_generation,
        clock=i.clock,
        spawn=i.spawn,
    )
    incidents = IncidentCoordinator(
        lifecycle=i.lifecycle,
        incidents=i.incident_state,
        supervisor_state=i.supervisor_state,
        limits=i.limit_state,
        health_silence_ns=i.health_silence_ns,
        clock=i.clock,
        publisher=publisher,
        metadata=metadata,
        evidence_waiter=evidence_waiter,
        preparation_context=preparation_context,
        lifecycle_reports=lifecycle_reports,
        supervisor=i.supervisor,
        interrupt=interruption.interrupt,
        spawn=i.spawn,
    )
    supervision = SupervisorObservations(
        lifecycle=i.lifecycle,
        supervisor_state=i.supervisor_state,
        publisher=publisher,
        incidents=incidents,
        generation=i.generation,
        supervisor_generation=i.supervisor_generation,
    )
    spikeglx_monitor = (
        SpikeGLXProgressMonitor(
            lifecycle=i.lifecycle,
            spikeglx=i.spikeglx,
            incidents=incidents,
            publisher=publisher,
            generation=i.generation,
            clock=i.clock,
        )
        if i.spikeglx is not None
        else None
    )
    spikeglx_inventory = (
        SpikeGLXInventory(
            software_root=i.software_root,
            lifecycle=i.lifecycle,
            configuration=i.configuration_state,
            operations=control_operations,
            limits=i.limit_state,
            publish=publisher.publish,
            clock=i.clock,
        )
        if i.software_root is not None
        else None
    )
    prompts = OperatorPrompts(
        lifecycle=i.lifecycle,
        incidents=i.incident_state,
        control=i.control,
        limit_state=i.limit_state,
        control_operations=control_operations,
        incident_coordinator=incidents,
        interruption=interruption,
        publisher=publisher,
        spawn=i.spawn,
    )
    trials = TrialExecution(
        lifecycle=i.lifecycle,
        limit_state=i.limit_state,
        clock=i.clock,
        projections=i.projections,
        publisher=publisher,
        evidence_waiter=evidence_waiter,
        cleanup=cleanup,
        trial_logs=trial_logs,
        interruption=interruption,
        spawn=i.spawn,
    )
    start = StartActivation(
        lifecycle=i.lifecycle,
        control=i.control,
        limit_state=i.limit_state,
        clock=i.clock,
        publisher=publisher,
        control_operations=control_operations,
        metadata=metadata,
        preparation_context=preparation_context,
        trials=trials,
        interruption=interruption,
        supervisor=i.supervisor,
        spikeglx=i.spikeglx,
        spikeglx_monitor=spikeglx_monitor,
        schema_factory=i.schema_factory,
        output_planner=i.output_planner,
        generation=i.generation,
        spawn=i.spawn,
    )
    handoffs = PreparationHandoffs(
        lifecycle=i.lifecycle,
        preparation_context=preparation_context,
        evidence_waiter=evidence_waiter,
        clock=i.clock,
    )
    setup_execution = SetupExecution(
        lifecycle=i.lifecycle,
        control=i.control,
        supervisor_state=i.supervisor_state,
        incident_state=i.incident_state,
        limits=i.limit_state,
        clock=i.clock,
        control_operations=control_operations,
        publisher=publisher,
        reservation_started=i.reservation_started,
        spikeglx=i.spikeglx,
        supervisor=i.supervisor,
        preparation_context=preparation_context,
        evidence_waiter=evidence_waiter,
        handoffs=handoffs,
        validators=i.validators,
        display_validator=i.display_validator,
        output_planner=i.output_planner,
        max_incident_bytes=i.max_incident_bytes,
        cancel_attempt=cleanup.cancel_attempt,
    )
    setup_admission = SetupAdmission(
        lifecycle=i.lifecycle,
        configuration=i.configuration_state,
        control=i.control,
        device=i.device_state,
        supervisor_state=i.supervisor_state,
        limit_state=i.limit_state,
        backends=i.backends,
        spikeglx=i.spikeglx,
        file_policy_loader=i.file_policy_loader,
        settings_loader=i.settings_loader,
        startup_settings=i.startup_settings,
        validators=i.validators,
        generation=i.generation,
        clock=i.clock,
        max_preparation_bytes=i.max_preparation_bytes,
        projections=i.projections,
        publisher=publisher,
        control_operations=control_operations,
        setup_execution=setup_execution,
        spawn=i.spawn,
    )
    acquisition_resolution = AcquisitionResolution(
        lifecycle=i.lifecycle,
        configuration=i.configuration_state,
        device=i.device_state,
        backends=i.backends,
        camera_readback=camera_readback,
        projections=i.projections,
        preparation_context=preparation_context,
        setup_execution=setup_execution,
        publisher=publisher,
        validators=i.validators,
        clock=i.clock,
        spawn=i.spawn,
    )
    tracking_diagnostic = TrackingDiagnosticController(
        generation=i.generation,
        lifecycle=i.lifecycle,
        configuration=i.configuration_state,
        control=i.control,
        device=i.device_state,
        supervisor=i.supervisor_state,
        limits=i.limit_state,
        backends=i.backends,
        supervisor_peer=i.supervisor,
        projections=i.projections,
        file_policy_loader=i.file_policy_loader,
        publish=publisher.publish,
        clock=i.clock,
        maximum_frame_bytes=i.max_preparation_bytes,
    )
    return ControllerComponents(
        control_operations=control_operations,
        preparation_context=preparation_context,
        publisher=publisher,
        leases=leases,
        metadata=metadata,
        display=display,
        display_calibration=display_calibration,
        camera=camera,
        microcontroller=microcontroller,
        camera_readback=camera_readback,
        device_views=device_views,
        camera_status_retention=camera_status_retention,
        preview=preview,
        cleanup=cleanup,
        configuration_commands=configuration_commands,
        lifecycle_reports=lifecycle_reports,
        evidence_waiter=evidence_waiter,
        trial_logs=trial_logs,
        interruption=interruption,
        session_commands=session_commands,
        supervision=supervision,
        prompts=prompts,
        trials=trials,
        start=start,
        handoffs=handoffs,
        setup_execution=setup_execution,
        setup_admission=setup_admission,
        acquisition_resolution=acquisition_resolution,
        tracking_diagnostic=tracking_diagnostic,
        spikeglx_monitor=spikeglx_monitor,
        spikeglx_inventory=spikeglx_inventory,
    )
