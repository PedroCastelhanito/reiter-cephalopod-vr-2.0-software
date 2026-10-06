"""Narrow, typed boundaries used by acquisition coordinator features."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from cephvr.acquisition.buffers.ring import SharedRing
from cephvr.acquisition.v1 import camera_pb2, microcontroller_pb2, runtime_pb2
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as control_svc
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.pixels.types import PixelLayout


class SerialOwnerPort(Protocol):
    """Async facade serializing sync owner operations on one dedicated thread."""

    async def connect(
        self, *, deadline_ns: int
    ) -> microcontroller_pb2.MicrocontrollerObservation: ...
    async def configure(
        self,
        requested: camera_pb2.CameraPulseConfiguration,
        *,
        active_roles: tuple[int | str, ...],
        deadline_ns: int,
    ) -> microcontroller_pb2.MicrocontrollerObservation: ...
    async def status(
        self, *, deadline_ns: int
    ) -> microcontroller_pb2.MicrocontrollerObservation: ...
    async def keepalive(
        self, *, deadline_ns: int
    ) -> microcontroller_pb2.MicrocontrollerState: ...
    async def diagnostic_start(
        self, kind: str, pin: str, *, frequency_hz: float | None, deadline_ns: int
    ) -> tuple[bool, str, str, int]: ...
    async def diagnostic_status(
        self, *, deadline_ns: int
    ) -> tuple[bool, str, str, int]: ...
    async def diagnostic_stop(
        self, *, deadline_ns: int
    ) -> tuple[bool, str, str, int]: ...
    async def on(
        self,
        selected_roles: tuple[int | str, ...],
        *,
        scheduled_boundary_ns: int | None,
        deadline_ns: int,
    ) -> microcontroller_pb2.PulseCommandEvidence: ...
    async def off(
        self,
        selected_roles: tuple[int | str, ...],
        *,
        scheduled_boundary_ns: int | None,
        stop_issued_ns: int | None,
        deadline_ns: int,
    ) -> microcontroller_pb2.PulseCommandEvidence: ...
    async def reserve_boundary(
        self,
        boundary_ns: int,
        command: microcontroller_pb2.PulseBoundaryCommand,
        *,
        selected_roles: tuple[int | str, ...],
        deadline_ns: int,
    ) -> None: ...
    async def cancel_on_reservations(self, *, deadline_ns: int) -> None: ...
    async def cancel_active_request(self) -> bool: ...
    async def close(self, *, deadline_ns: int) -> None: ...


class WorkerPort(Protocol):
    """One authenticated worker endpoint bound to one exact WorkerContext."""

    context: acq.WorkerContext

    async def prepare_preview(
        self, request: acq.WorkerPreparePreview, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def start_preview(
        self, request: acq.WorkerStartPreview, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def stop_preview(
        self, request: acq.WorkerStopPreview, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def edit_camera(
        self, request: acq.WorkerEditCamera, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def resolve_camera_configuration(
        self, request: acq.WorkerResolveCamera, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def get_state(
        self, request: acq.WorkerQuery, *, deadline_ns: int
    ) -> acq.WorkerState: ...
    async def get_retained_result(
        self, request: acq.WorkerRetainedResultQuery, *, deadline_ns: int
    ) -> acq.WorkerRetainedResult: ...
    async def setup_session(
        self, request: acq.WorkerSetupSession, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def cancel_setup(
        self, request: acq.WorkerCommand, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def prepare_trial(
        self, request: acq.WorkerPrepareTrial, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def schedule_trial(
        self, request: acq.WorkerSchedule, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def release_trial(
        self, request: acq.WorkerRelease, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def record_pulse_evidence(
        self, request: acq.WorkerPulseEvidence, *, deadline_ns: int
    ) -> control.ReportReceipt: ...
    async def stop_trial(
        self, request: acq.WorkerStop, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def interrupt_session(
        self, request: acq.WorkerInterrupt, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def cleanup(
        self, request: acq.WorkerCommand, *, deadline_ns: int
    ) -> control.CommandAdmission: ...
    async def shutdown(
        self, request: acq.WorkerCommand, *, deadline_ns: int
    ) -> control.CommandAdmission: ...


class WorkerBootstrapPort(Protocol):
    """Start a planned child and return only after exact endpoint registration."""

    async def launch(
        self,
        spec: WorkerLaunchSpec,
        *,
        deadline_ns: int,
    ) -> WorkerLaunchResult: ...
    async def retire(
        self, worker: control.ProcessIdentity, *, deadline_ns: int
    ) -> None: ...
    async def wait_process_exit(
        self, worker: control.ProcessIdentity, *, deadline_ns: int
    ) -> bool: ...


class SupervisorPort(Protocol):
    """Acquisition's authenticated supervisor RPC boundary."""

    async def plan_launch(
        self,
        request: control_svc.PlanLaunchRequest,
        *,
        deadline_ns: int,
        child_token: str,
    ) -> control_svc.LaunchReceipt: ...
    async def confirm_launch(
        self, request: control_svc.ConfirmLaunchRequest, *, deadline_ns: int
    ) -> control_svc.LaunchReceipt: ...
    async def get_launch_state(
        self, request: control_svc.LaunchQuery, *, deadline_ns: int
    ) -> control_svc.LaunchState: ...
    async def register_context(
        self, request: control_svc.RegisterContextRequest, *, deadline_ns: int
    ) -> control_svc.RegistrationReceipt: ...
    async def report_lifecycle(
        self, request: control.LifecycleReport, *, deadline_ns: int
    ) -> control.ReportReceipt: ...
    async def report_error(
        self, request: control.ErrorReport, *, deadline_ns: int
    ) -> control.ReportReceipt: ...
    async def report_heartbeat(
        self, request: control.HeartbeatReport, *, deadline_ns: int
    ) -> control.ReportReceipt: ...


class ControllerPort(Protocol):
    """Controller reports, resolution adoption and owner lifecycle boundary."""

    async def report_lifecycle(
        self, request: control.LifecycleReport, *, deadline_ns: int
    ) -> control.ReportReceipt: ...
    async def report_acquisition_resolution(
        self, request: control_svc.AcquisitionResolutionReport, *, deadline_ns: int
    ) -> control.ReportReceipt: ...
    async def report_acquisition_device_status(
        self, request: control_svc.AcquisitionDeviceStatusReport, *, deadline_ns: int
    ) -> control.ReportReceipt: ...
    async def report_acquisition_warnings(
        self, request: control_svc.AcquisitionWarningReport, *, deadline_ns: int
    ) -> control.ReportReceipt: ...
    async def report_preview_attachment(
        self, request: control_svc.PreviewAttachmentReport, *, deadline_ns: int
    ) -> control.ReportReceipt: ...
    async def report_data_preparation(
        self, request: control_svc.DataPreparationReport, *, deadline_ns: int
    ) -> control.ReportReceipt: ...


class ResourcePort(Protocol):
    """Create/release only coordinator-owned shared frame-ring obligations."""

    def create_ring(
        self,
        attachment: acq.FrameBufferAttachment,
        layout: PixelLayout,
        owner: control.ProcessIdentity,
    ) -> SharedRing: ...
    def release_ring(self, allocation_id: str) -> None: ...


@dataclass(frozen=True)
class WorkerLaunchSpec:
    """Launch fields are public data; credentials stay inside bootstrap ports."""

    launch_command_id: str
    parent_operation: control.OperationContext
    context: acq.WorkerContext
    file_policy: runtime_pb2.CameraFilePolicy
    control_policies: control.ControlPolicies
    coordinator_endpoint: str
    heartbeat_interval_ns: int
    health_silence_ns: int
    executable: Path
    python_worker: bool
    stop_method: str


@dataclass(frozen=True)
class WorkerLaunchResult:
    context: acq.WorkerContext
    port: WorkerPort
    pid: int
    creation_time_100ns: int
    endpoint: str


class ExecutableResolver(Protocol):
    def resolve_worker(self, role: int) -> tuple[Path, bool, str]: ...
