"""Controller admission and retained completion for general-purpose MCU commands."""

from collections.abc import Callable
from uuid import uuid4

from cephvr.acquisition.v1 import camera_pb2
from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.device.ports import DeviceHooks
from cephvr.controller.microcontroller.device import MicrocontrollerDevice
from cephvr.controller.state import (
    CameraOperation,
    ConfigurationState,
    DeviceState,
    LifecycleState,
    LimitsState,
)


class MicrocontrollerCommands:
    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        configuration: ConfigurationState,
        device: DeviceState,
        owner: MicrocontrollerDevice | None,
        limits: LimitsState,
        clock: Callable[[], int],
        hooks: DeviceHooks,
        device_views: Callable[[], pb.AcquisitionDeviceViews | None],
    ) -> None:
        self.lifecycle = lifecycle
        self.configuration = configuration
        self.device = device
        self.owner = owner
        self.limits = limits
        self.clock = clock
        self.hooks = hooks
        self.device_views = device_views

    async def execute(
        self, request: svc.MicrocontrollerCommandRequest
    ) -> pb.CommandAdmission:
        operator_id = request.command.operator.command_id
        async with self.lifecycle.lock:
            error = self.hooks.authorized(request.command)
            if (
                error
                or self.owner is None
                or self.lifecycle.session.phase != pb.SESSION_PHASE_CONFIGURATION
                or self.lifecycle.startup_blocker
                or self.lifecycle.manual_control_cleanup_pending
                or self.lifecycle.authority_lost
                or self.lifecycle.session.shutdown_requested
                or self.device.camera_operation is not None
                or not request.HasField("expected_configuration_revision")
                or request.expected_configuration_revision
                != self.configuration.revision
                or request.kind
                not in {
                    svc.MICROCONTROLLER_COMMAND_KIND_CONNECT,
                    svc.MICROCONTROLLER_COMMAND_KIND_START,
                    svc.MICROCONTROLLER_COMMAND_KIND_STATUS,
                    svc.MICROCONTROLLER_COMMAND_KIND_STOP,
                    svc.MICROCONTROLLER_COMMAND_KIND_UPLOAD_FIRMWARE,
                }
            ):
                return self.hooks.admission(
                    operator_id, error=error or "microcontroller command unavailable"
                )
            if (request.kind == svc.MICROCONTROLLER_COMMAND_KIND_START) != (
                request.signal != 0
            ):
                return self.hooks.admission(
                    operator_id, error="invalid MCU signal selection"
                )
            upload = request.kind == svc.MICROCONTROLLER_COMMAND_KIND_UPLOAD_FIRMWARE
            if upload != bool(request.firmware_path and request.firmware_sha256) or (
                not upload and (request.firmware_path or request.firmware_sha256)
            ):
                return self.hooks.admission(
                    operator_id, error="invalid firmware source/image selection"
                )
            views = self.device_views()
            if views is not None and any(
                camera.device_open or camera.preview_running or camera.cleanup_pending
                for camera in (views.behavioral, views.tracking)
            ):
                return self.hooks.admission(
                    operator_id,
                    error="Stop capture and release cameras before Microcontroller diagnostics or Upload",
                )
            settings = next(
                (
                    item.acquisition
                    for item in self.configuration.current.backends
                    if item.backend_name == "acquisition"
                    and item.HasField("acquisition")
                ),
                None,
            )
            if settings is None or not settings.pulses.HasField("port"):
                return self.hooks.admission(
                    operator_id, error="MCU port is not configured"
                )
            try:
                self.owner.ensure_idle()
                if self.owner.acquisition_claimed or (
                    upload and self.owner.view.diagnostic.active
                ):
                    raise RuntimeError(
                        "Release camera triggers and stop diagnostics before firmware upload"
                    )
            except RuntimeError as exc:
                return self.hooks.admission(operator_id, error=str(exc))
            deadline_ns = (
                self.clock()
                + self.limits.current.setup_ns
                + self.limits.current.recovery_ns
            )
            operation = CameraOperation(
                operator_id,
                str(uuid4()),
                self.configuration.revision,
                0,
                request.kind,
                pb.WorkContext(),
                deadline_ns,
                False,
                is_microcontroller=True,
            )
            self.device.camera_operation = operation
            self.device.camera_operation_changed.clear()
            self.hooks.operation(
                operator_id,
                "ExecuteMicrocontrollerCommand",
                progress="controller Microcontroller command pending",
            )
            frozen = type(request).FromString(request.SerializeToString())
            pulses = type(settings.pulses).FromString(
                settings.pulses.SerializeToString()
            )
            self.hooks.spawn(self._perform(frozen, pulses, operation))
            self.hooks.publish()
        return self.hooks.admission(operator_id)

    async def _perform(
        self,
        request: svc.MicrocontrollerCommandRequest,
        pulses: camera_pb2.CameraPulseConfiguration,
        operation: CameraOperation,
    ) -> None:
        assert self.owner is not None
        failure = ""
        try:
            await self.owner.execute(request, pulses, operation.deadline_ns)
            if self.clock() >= operation.deadline_ns:
                raise TimeoutError(
                    "Microcontroller completion missed its original deadline"
                )
        except Exception as exc:
            failure = str(exc)
        async with self.lifecycle.lock:
            self.hooks.complete_operation(
                operation.operator_id,
                success=not failure,
                progress="Microcontroller command failed"
                if failure
                else "Microcontroller command completed",
                error=failure,
            )
            if self.owner.firmware.busy:
                operation.timed_out = True
            elif self.device.camera_operation is operation:
                self.device.camera_operation = None
                self.device.camera_operation_changed.set()
            self.hooks.publish()
