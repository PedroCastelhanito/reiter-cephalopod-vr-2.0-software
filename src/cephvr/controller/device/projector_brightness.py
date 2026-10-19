"""Explicit projector LED adjustment under the existing manual-device gate."""

from collections.abc import Callable
from uuid import uuid4

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.device.ports import DeviceHooks
from cephvr.controller.state import (
    CameraOperation,
    ConfigurationState,
    DeviceState,
    LifecycleState,
    LimitsState,
)
from cephvr.platform.windows.projector_brightness import adjust_brightness
from cephvr.shared.deadlines import remaining_seconds


class ProjectorBrightness:
    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        configuration: ConfigurationState,
        device: DeviceState,
        limits: LimitsState,
        clock: Callable[[], int],
        hooks: DeviceHooks,
    ) -> None:
        self.lifecycle = lifecycle
        self.configuration = configuration
        self.device = device
        self.limits = limits
        self.clock = clock
        self.hooks = hooks

    async def execute(
        self, request: svc.ProjectorBrightnessRequest
    ) -> pb.CommandAdmission:
        command_id = request.command.operator.command_id
        async with self.lifecycle.lock:
            error = self.hooks.authorized(request.command)
            if (
                error
                or self.lifecycle.session.phase != pb.SESSION_PHASE_CONFIGURATION
                or self.lifecycle.startup_blocker
                or self.lifecycle.manual_control_cleanup_pending
                or self.lifecycle.authority_lost
                or self.lifecycle.session.shutdown_requested
                or self.lifecycle.attempt is not None
                or self.device.camera_operation is not None
                or self.device.configuration_edit is not None
                or request.expected_configuration_revision
                != self.configuration.revision
                or not 101 <= request.current_ma <= 2500
            ):
                return self.hooks.admission(
                    command_id,
                    error=error
                    or "Projector brightness unavailable; requires idle Configuration and 101–2500 mA",
                )
            operation = CameraOperation(
                command_id,
                str(uuid4()),
                self.configuration.revision,
                0,
                0,
                pb.WorkContext(),
                self.clock() + self.limits.current.setup_ns,
                False,
                is_projector=True,
            )
            self.device.camera_operation = operation
            self.device.camera_operation_changed.clear()
            self.hooks.operation(
                command_id,
                "AdjustProjectorBrightness",
                progress="Adjusting all USB projectors",
            )
            self.hooks.spawn(self._perform(request.current_ma, operation))
            self.hooks.publish()
            return self.hooks.admission(command_id)

    async def _perform(self, current_ma: int, operation: CameraOperation) -> None:
        failure = ""
        details = ""
        try:
            details = await adjust_brightness(
                current_ma, remaining_seconds(operation.deadline_ns, clock=self.clock)
            )
            if self.clock() >= operation.deadline_ns:
                raise TimeoutError(
                    "Projector adjustment exceeded its original deadline"
                )
        except Exception as exc:
            failure = (
                str(exc) or "Projector adjustment timed out; hardware state unconfirmed"
            )
        async with self.lifecycle.lock:
            self.hooks.complete_operation(
                operation.operator_id,
                success=not failure,
                progress=details or "Projector adjustment failed",
                error=failure,
            )
            if self.device.camera_operation is operation:
                self.device.camera_operation = None
                self.device.camera_operation_changed.set()
            self.hooks.publish()
