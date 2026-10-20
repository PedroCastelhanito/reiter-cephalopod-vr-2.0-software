"""Explicit projector LED adjustment under the existing manual-device gate."""

import asyncio
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
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
from cephvr.platform.windows.projector_brightness import BrightnessPort
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
        native: BrightnessPort | None,
        generation: str,
    ) -> None:
        self.lifecycle = lifecycle
        self.configuration = configuration
        self.device = device
        self.limits = limits
        self.clock = clock
        self.hooks = hooks
        self.native = native
        self.generation = generation

    @property
    def cleanup_complete(self) -> bool:
        operation = self.device.camera_operation
        evidence = self.device.projector_brightness
        pending = (
            operation is not None
            and evidence is not None
            and operation.operator_id == evidence["command_id"]
        )
        return not pending and (self.native is None or self.native.cleanup_complete)

    async def execute(
        self, request: svc.ProjectorBrightnessRequest
    ) -> pb.CommandAdmission:
        command_id = request.command.operator.command_id
        async with self.lifecycle.lock:
            error = self.hooks.authorized(request.command)
            if (
                error
                or self.native is None
                or not self.native.cleanup_complete
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
            self.hooks.operation(
                command_id,
                "AdjustProjectorBrightness",
                progress="Adjusting all USB projectors",
            )
            assert self.native is not None
            self.native.reset_cancel()
            self.device.camera_operation = operation
            self.device.camera_operation_changed.clear()
            self.device.projector_brightness = {
                "schema_version": 1,
                "controller_generation": self.generation,
                "command_id": command_id,
                "configuration_revision": self.configuration.revision,
                "requested_ma": request.current_ma,
                "started_monotonic_ns": self.clock(),
                "started_utc": datetime.now(UTC).isoformat(),
                "outcome": "unconfirmed",
                "native_cleanup_confirmed": False,
                "sdk_result": None,
                "diagnostics": "",
                "error": "adjustment pending",
            }
            self.hooks.spawn(self._perform(request.current_ma, operation))
            self.hooks.publish()
            return self.hooks.admission(command_id)

    async def _perform(self, current_ma: int, operation: CameraOperation) -> None:
        failure = ""
        details = ""
        assert self.native is not None
        native = self.native
        worker = asyncio.create_task(
            asyncio.to_thread(
                native.adjust,
                current_ma,
                pb.OperationContext(command_id=operation.operator_id),
                deadline_ns=operation.deadline_ns,
            )
        )
        try:
            await asyncio.wait_for(
                asyncio.shield(worker),
                remaining_seconds(operation.deadline_ns, clock=self.clock),
            )
            if self.clock() >= operation.deadline_ns:
                raise TimeoutError(
                    "Projector adjustment exceeded its original deadline"
                )
        except (Exception, asyncio.CancelledError) as exc:
            native.cancel()
            failure = str(exc) or (
                "Projector adjustment cancelled; hardware state unconfirmed"
                if isinstance(exc, asyncio.CancelledError)
                else "Projector adjustment timed out; hardware state unconfirmed"
            )
            if not worker.done():
                try:
                    await asyncio.wait_for(
                        asyncio.shield(worker),
                        remaining_seconds(operation.deadline_ns, clock=self.clock),
                    )
                except (Exception, asyncio.CancelledError):
                    pass
        cleanup_complete = worker.done() and native.cleanup_complete
        if not cleanup_complete:
            failure = (
                failure + "; exact native process/job/pipe cleanup unconfirmed"
            ).lstrip("; ")
        details = native.diagnostics
        async with self.lifecycle.lock:
            evidence = self.device.projector_brightness
            assert (
                evidence is not None and evidence["command_id"] == operation.operator_id
            )
            evidence.update(
                {
                    "completed_monotonic_ns": self.clock(),
                    "completed_utc": datetime.now(UTC).isoformat(),
                    "outcome": "unconfirmed"
                    if not cleanup_complete
                    else ("failed" if failure else "succeeded"),
                    "native_cleanup_confirmed": cleanup_complete,
                    "sdk_result": deepcopy(native.result),
                    "diagnostics": details,
                    "error": failure,
                }
            )
            self.hooks.complete_operation(
                operation.operator_id,
                success=not failure,
                progress=details or "Projector adjustment failed",
                error=failure,
            )
            if cleanup_complete and self.device.camera_operation is operation:
                self.device.camera_operation = None
                self.device.camera_operation_changed.set()
            self.hooks.publish()
