"""Controller-owned operator MCU diagnostics through acquisition (A11/E08)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Mapping

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.device.ports import DeviceHooks
from cephvr.controller.device.status_retention import CameraStatusRetention
from cephvr.controller.ports import BackendPort
from cephvr.controller.state import (
    CameraOperation,
    ConfigurationState,
    DeviceState,
    LifecycleState,
    LimitsState,
)


class MicrocontrollerCommands:
    """Admit one bounded device operation with retained exact status evidence."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        configuration: ConfigurationState,
        device: DeviceState,
        backends: Mapping[str, BackendPort],
        generation: str,
        limits: LimitsState,
        clock: Callable[[], int],
        hooks: DeviceHooks,
        status_retention: CameraStatusRetention,
    ) -> None:
        self.lifecycle = lifecycle
        self.configuration = configuration
        self.device = device
        self.backends = backends
        self.generation = generation
        self.limits = limits
        self.clock = clock
        self.hooks = hooks
        self.status_retention = status_retention

    async def execute(
        self, request: svc.MicrocontrollerCommandRequest
    ) -> pb.CommandAdmission:
        operator_id = request.command.operator.command_id
        async with self.lifecycle.lock:
            error = self.hooks.authorized(request.command)
            backend = self.backends.get("acquisition")
            if (
                error
                or backend is None
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
                }
            ):
                return self.hooks.admission(
                    operator_id, error=error or "microcontroller command unavailable"
                )
            if (request.kind == svc.MICROCONTROLLER_COMMAND_KIND_START) != (
                request.signal != pb.MICROCONTROLLER_SIGNAL_KIND_UNSPECIFIED
            ):
                return self.hooks.admission(
                    operator_id, error="invalid MCU signal selection"
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
            child_id = str(uuid.uuid4())
            deadline_ns = (
                self.clock()
                + self.limits.current.setup_ns
                + self.limits.current.recovery_ns
            )
            child = svc.AcquisitionMicrocontrollerCommand(
                configuration_revision=self.configuration.revision,
                kind=request.kind,
                signal=request.signal,
                requested=settings.pulses,
            )
            child.command.command_id = child_id
            child.command.issuer.CopyFrom(
                pb.ProcessIdentity(role="controller", generation=self.generation)
            )
            child.command.target.CopyFrom(backend.context)
            child.command.parent_operation.command_id = operator_id
            operation = CameraOperation(
                operator_id,
                child_id,
                self.configuration.revision,
                0,
                request.kind,
                pb.WorkContext(),
                deadline_ns,
                False,
                is_microcontroller=True,
            )
            try:
                self.status_retention.reserve(operation)
            except (RuntimeError, ValueError) as exc:
                return self.hooks.admission(operator_id, error=str(exc))
            self.device.camera_operation = operation
            self.device.camera_operation_changed.clear()
            self.device.manual_effects_admitted = True
            self.hooks.operation(
                operator_id,
                "ExecuteMicrocontrollerCommand",
                progress="acquisition MCU command pending",
            )
            self.hooks.publish()
        try:
            response = await asyncio.wait_for(
                backend.execute_microcontroller_command(child, deadline_ns=deadline_ns),
                max(0, (deadline_ns - self.clock()) / 1e9),
            )
        except Exception as exc:
            self.hooks.spawn(self._timeout(child_id, deadline_ns))
            return self.hooks.admission(operator_id, error=str(exc))
        if response.result != pb.COMMAND_RESULT_ACCEPTED:
            async with self.lifecycle.lock:
                if self.device.camera_operation is operation:
                    self.hooks.complete_operation(
                        operator_id,
                        success=False,
                        progress="MCU command rejected",
                        error=response.failure.message,
                    )
                    self.status_retention.release_unstarted(operation)
                    self.device.camera_operation = None
                    self.device.camera_operation_changed.set()
                    self.hooks.publish()
            return self.hooks.admission(operator_id, error=response.failure.message)
        self.hooks.spawn(self._timeout(child_id, deadline_ns))
        return self.hooks.admission(operator_id)

    async def _timeout(self, child_id: str, deadline_ns: int) -> None:
        await asyncio.sleep(max(0, (deadline_ns - self.clock()) / 1e9))
        async with self.lifecycle.lock:
            operation = self.device.camera_operation
            if operation is None or operation.child_id != child_id:
                return
            operation.timed_out = True
            self.hooks.complete_operation(
                operation.operator_id,
                success=False,
                progress="MCU command evidence timed out",
                error="exact completion missing",
            )
            self.status_retention.retire_operation(operation)
            self.hooks.publish()
