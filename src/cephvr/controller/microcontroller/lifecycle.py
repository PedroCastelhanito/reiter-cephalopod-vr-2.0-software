"""Focused controller lifecycle integration for its Microcontroller owner."""

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any
from uuid import uuid4

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.microcontroller.device import MicrocontrollerDevice
from cephvr.controller.microcontroller.health import MicrocontrollerHealth
from cephvr.controller.state import (
    Attempt,
    CameraOperation,
    ConfigurationState,
    DeviceState,
    LifecycleState,
    LimitsState,
)
from cephvr.shared.deadlines import remaining_seconds


class MicrocontrollerLifecycle:
    def __init__(
        self,
        owner: MicrocontrollerDevice,
        *,
        generation: str,
        lifecycle: LifecycleState,
        configuration: ConfigurationState,
        device: DeviceState,
        limits: LimitsState,
        clock: Callable[[], int],
        publish: Callable[[], None],
        warning: Callable[[pb.Warning], Awaitable[None]],
        interrupt: Callable[[Attempt, str, int], Awaitable[None]],
        spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]],
    ) -> None:
        self.owner = owner
        self.generation = generation
        self.lifecycle = lifecycle
        self.configuration = configuration
        self.device = device
        self.limits = limits
        self.clock = clock
        self.publish = publish
        self.warning = warning
        self.interrupt = interrupt
        self.spawn = spawn

    async def owner_lost(self) -> None:
        if self.lifecycle.session.phase != pb.SESSION_PHASE_CONFIGURATION:
            return
        deadline_ns = self.clock() + self.limits.current.setup_ns
        self.owner.releasing = True
        self.publish()
        if self.owner.acquisition_claimed:
            # The existing camera cleanup callback starts after observers return.
            self.spawn(self._finish_owner_loss(deadline_ns))
        else:
            await self._finish_owner_loss(deadline_ns)

    async def _finish_owner_loss(self, deadline_ns: int) -> None:
        try:
            if self.owner.acquisition_claimed:
                wait_until = deadline_ns - self.limits.current.recovery_ns
                try:
                    await asyncio.wait_for(
                        self.owner.claim_released.wait(),
                        remaining_seconds(wait_until, clock=self.clock),
                    )
                except TimeoutError:
                    pass
            await self.owner.close(deadline_ns=deadline_ns, permanent=False)
        except Exception as exc:
            await self.warning(
                pb.Warning(
                    warning_id=str(uuid4()),
                    component="microcontroller",
                    message=f"Microcontroller cleanup remains unconfirmed: {exc}"[
                        :2048
                    ],
                )
            )
            return
        async with self.lifecycle.lock:
            operation = self.device.camera_operation
            if operation is not None and operation.is_microcontroller:
                self.device.camera_operation = None
                self.device.camera_operation_changed.set()
            self.publish()

    def health(self) -> MicrocontrollerHealth:
        owner = self.owner
        return MicrocontrollerHealth(
            observation=owner.observation,
            serial=owner.serial,
            serial_keepalive_interval_ns=owner.policies.serial_keepalive_interval_ns,
            serial_communication_timeout_ns=owner.policies.serial_communication_timeout_ns,
            serial_ack_timeout_ns=owner.policies.serial_ack_timeout_ns,
            policy_values=lambda: (
                owner.policies.serial_keepalive_interval_ns,
                owner.policies.serial_communication_timeout_ns,
                owner.policies.serial_ack_timeout_ns,
            ),
            serial_handoff_active=lambda: (
                owner.firmware.busy or owner.closed or owner.closing
            ),
            next_boundary=owner.next_boundary,
            failure_handler=self.failed,
            clock=self.clock,
            changed=self.publish,
        )

    async def failed(self, failure: pb.Failure) -> None:
        self.owner.failure = failure.message
        await self.warning(
            pb.Warning(
                warning_id=str(uuid4()),
                component="microcontroller",
                message=failure.message,
            )
        )
        attempt = self.lifecycle.attempt
        if attempt is not None:
            await self.interrupt(attempt, failure.message, self.clock())
        else:
            await self.owner.close(
                deadline_ns=self.clock() + self.limits.current.recovery_ns,
                permanent=False,
            )

    async def execute(
        self, request: wire.MicrocontrollerIoRequest
    ) -> wire.MicrocontrollerIoResult:
        if (
            request.controller_generation != self.generation
            or request.requester.role != "acquisition"
        ):
            raise ValueError("Microcontroller peer targets a different owner")
        safety = request.kind in {
            wire.MICROCONTROLLER_IO_KIND_OFF,
            wire.MICROCONTROLLER_IO_KIND_CLOSE,
            wire.MICROCONTROLLER_IO_KIND_CANCEL_ON,
            wire.MICROCONTROLLER_IO_KIND_CANCEL_ACTIVE,
        }
        scoped_edit = request.HasField("resolution_operation") or request.HasField(
            "requested_configuration_revision"
        )
        if scoped_edit and request.kind != wire.MICROCONTROLLER_IO_KIND_CONFIGURE:
            raise ValueError("Microcontroller edit scope is only valid for Configure")
        admitted_operation: CameraOperation | None = None
        async with self.lifecycle.lock:
            if not safety and (
                self.lifecycle.authority_lost
                or self.lifecycle.session.shutdown_requested
            ):
                raise RuntimeError(
                    "Controller authority cannot admit new Microcontroller execution"
                )
            operation = self.device.camera_operation
            if not safety and operation is not None and operation.is_microcontroller:
                raise RuntimeError(
                    "Controller Microcontroller command is already admitted"
                )
            if not safety:
                settings = next(
                    (
                        item.acquisition
                        for item in self.configuration.current.backends
                        if item.backend_name == "acquisition"
                        and item.HasField("acquisition")
                    ),
                    None,
                )
                if settings is None:
                    raise ValueError("Microcontroller configuration is unavailable")
                if request.kind in {
                    wire.MICROCONTROLLER_IO_KIND_CONNECT,
                    wire.MICROCONTROLLER_IO_KIND_CONFIGURE,
                }:
                    if scoped_edit:
                        edit = self.device.configuration_edit
                        terminal = (
                            self.device.configuration_edit_terminals.get(
                                request.resolution_operation.command_id
                            )
                            if request.HasField("resolution_operation")
                            else None
                        )
                        proposed = (
                            next(
                                (
                                    item.acquisition
                                    for item in edit.proposed.backends
                                    if item.backend_name == "acquisition"
                                    and item.WhichOneof("settings") == "acquisition"
                                ),
                                None,
                            )
                            if edit is not None
                            else None
                        )
                        if (
                            request.kind != wire.MICROCONTROLLER_IO_KIND_CONFIGURE
                            or not request.HasField("resolution_operation")
                            or not request.HasField("requested_configuration_revision")
                            or edit is None
                            or terminal is None
                            or not request.resolution_operation.command_id
                            or edit.operation_id
                            != request.resolution_operation.command_id
                            or request.requested_configuration_revision != edit.revision
                            or self.configuration.revision != edit.revision
                            or not edit.expect_pulses
                            or edit.failure
                            or edit.report is not None
                            or edit.confirmed.is_set()
                            or edit.adopted is not None
                            or terminal.source.backend_name != "acquisition"
                            or request.requester.generation
                            != terminal.source.backend_generation
                            or proposed is None
                            or request.requested.SerializeToString(deterministic=True)
                            != proposed.pulses.SerializeToString(deterministic=True)
                            or request.deadline_monotonic_ns > edit.deadline_ns
                            or self.clock() >= edit.deadline_ns
                            or self.lifecycle.session.phase
                            not in {
                                pb.SESSION_PHASE_CONFIGURATION,
                                pb.SESSION_PHASE_READY,
                            }
                        ):
                            raise ValueError(
                                "Microcontroller candidate is not authorized by the live configuration edit"
                            )
                    elif request.requested != settings.pulses:
                        raise ValueError(
                            "Camera trigger configuration differs from the controller revision"
                        )
                    if (
                        request.kind == wire.MICROCONTROLLER_IO_KIND_CONNECT
                        and self.lifecycle.session.phase
                        in {
                            pb.SESSION_PHASE_STARTING,
                            pb.SESSION_PHASE_RUNNING,
                            pb.SESSION_PHASE_FINALIZING,
                            pb.SESSION_PHASE_ENDED,
                        }
                    ):
                        raise RuntimeError(
                            "A camera trigger claim must be established during Configuration or Setup"
                        )
                    self.owner.settings.pulses.CopyFrom(settings.pulses)
                    if scoped_edit:
                        admitted_operation = CameraOperation(
                            operator_id=request.requester.generation,
                            child_id=request.command_id,
                            revision=request.requested_configuration_revision,
                            camera=0,
                            kind=request.kind,
                            work=pb.WorkContext(),
                            deadline_ns=request.deadline_monotonic_ns,
                            readback_required=False,
                            is_microcontroller=True,
                        )
                        self.device.camera_operation = admitted_operation
                        self.device.camera_operation_changed.clear()
        try:
            return await self.owner.io(request)
        finally:
            if admitted_operation is not None:
                async with self.lifecycle.lock:
                    if self.device.camera_operation is admitted_operation:
                        self.device.camera_operation = None
                        self.device.camera_operation_changed.set()
                        self.publish()

    def bind_shutdown_deadline(self, deadline_ns: int) -> None:
        current = self.owner.shutdown_deadline_ns
        self.owner.shutdown_deadline_ns = (
            deadline_ns if current is None else min(current, deadline_ns)
        )

    def prepare_authority_close(self, issued_ns: int) -> None:
        if self.owner.shutdown_deadline_ns is None:
            attempt = self.lifecycle.attempt
            allowance = (
                self.limits.current.finished_ns
                if attempt is not None and attempt.activated
                else self.limits.current.setup_cancel_ns
            )
            self.bind_shutdown_deadline(
                issued_ns + allowance + self.limits.current.recovery_ns
            )

    async def close_authority(self, issued_ns: int) -> None:
        self.prepare_authority_close(issued_ns)
        assert self.owner.shutdown_deadline_ns is not None
        await self.owner.close(deadline_ns=self.owner.shutdown_deadline_ns)

    async def shutdown(self, issued_ns: int) -> None:
        self.prepare_authority_close(issued_ns)
        assert self.owner.shutdown_deadline_ns is not None
        # Let acquisition send its original OFF/cutoff evidence before releasing its claim.
        if self.owner.acquisition_claimed:
            wait_until = (
                self.owner.shutdown_deadline_ns - self.limits.current.recovery_ns
            )
            try:
                await asyncio.wait_for(
                    self.owner.claim_released.wait(),
                    remaining_seconds(wait_until, clock=self.clock),
                )
            except TimeoutError:
                pass
        await self.owner.close(deadline_ns=self.owner.shutdown_deadline_ns)
