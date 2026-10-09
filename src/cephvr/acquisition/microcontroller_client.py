"""Authenticated camera-trigger client of the controller's sole serial owner."""

from collections.abc import Callable
from typing import Any, cast
from uuid import uuid4

from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.auth import Principal
from cephvr.shared.clock import host_time_ns
from cephvr.shared.microcontroller import SerialOwnerPort
from cephvr.shared.transport_deadlines import deadline_metadata

_ROLES = {
    "behavioral": camera.CAMERA_ROLE_BEHAVIORAL,
    "tracking": camera.CAMERA_ROLE_TRACKING,
}


class ControllerMicrocontrollerClient(SerialOwnerPort):
    def __init__(
        self,
        stub: Any,
        principal: Principal,
        controller_generation: str,
        requested: Callable[[], camera.CameraPulseConfiguration],
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.stub = stub
        self.principal = principal
        self.controller_generation = controller_generation
        self.requested = requested
        self.clock = clock
        self.claim_id = ""

    async def _call(
        self, kind: int, deadline_ns: int, **fields: Any
    ) -> wire.MicrocontrollerIoResult:
        if self.clock() >= deadline_ns:
            raise TimeoutError(
                "Microcontroller request deadline expired before transport"
            )
        command_id = str(uuid4())
        claim_id = (
            command_id
            if kind == wire.MICROCONTROLLER_IO_KIND_CONNECT
            else self.claim_id
        )
        request = wire.MicrocontrollerIoRequest(
            command_id=command_id,
            claim_id=claim_id,
            requester=pb.ProcessIdentity(
                role=self.principal.role, generation=self.principal.generation
            ),
            controller_generation=self.controller_generation,
            deadline_monotonic_ns=deadline_ns,
            kind=cast(wire.MicrocontrollerIoKind, kind),
            **fields,
        )
        if kind == wire.MICROCONTROLLER_IO_KIND_CONNECT:
            self.claim_id = claim_id
        result = cast(
            wire.MicrocontrollerIoResult,
            await self.stub.ExecuteMicrocontrollerIo(
                request,
                metadata=(*self.principal.metadata(), deadline_metadata(deadline_ns)),
                timeout=(deadline_ns - self.clock()) / 1e9,
            ),
        )
        if result.command_id != request.command_id:
            raise RuntimeError(
                "Microcontroller response identifies a different command"
            )
        if not result.succeeded:
            raise RuntimeError(result.failure)
        expected = (
            "observation"
            if kind
            in {
                wire.MICROCONTROLLER_IO_KIND_CONNECT,
                wire.MICROCONTROLLER_IO_KIND_CONFIGURE,
                wire.MICROCONTROLLER_IO_KIND_STATUS,
            }
            else "evidence"
            if kind
            in {wire.MICROCONTROLLER_IO_KIND_ON, wire.MICROCONTROLLER_IO_KIND_OFF}
            else "cancelled"
            if kind == wire.MICROCONTROLLER_IO_KIND_CANCEL_ACTIVE
            else None
        )
        if expected is not None and result.WhichOneof("result") != expected:
            raise RuntimeError(
                "Microcontroller response omitted required typed evidence"
            )
        return result

    async def connect(self, *, deadline_ns: int) -> mcu.MicrocontrollerObservation:
        # Remember the claim even if transport fails; cleanup must address any admitted CONNECT.
        if self.claim_id:
            return await self.status(deadline_ns=deadline_ns)
        result = await self._call(
            wire.MICROCONTROLLER_IO_KIND_CONNECT,
            deadline_ns,
            requested=self.requested(),
        )
        return result.observation

    async def configure(
        self,
        requested: camera.CameraPulseConfiguration,
        *,
        active_roles: tuple[int | str, ...],
        deadline_ns: int,
        resolution_operation: pb.OperationContext | None = None,
        requested_configuration_revision: int | None = None,
    ) -> mcu.MicrocontrollerObservation:
        if (resolution_operation is None) != (requested_configuration_revision is None):
            raise ValueError("configuration edit scope is incomplete")
        scope = {}
        if resolution_operation is not None:
            if (
                not resolution_operation.command_id
                or not requested_configuration_revision
            ):
                raise ValueError("configuration edit scope is invalid")
            scope = {
                "resolution_operation": resolution_operation,
                "requested_configuration_revision": requested_configuration_revision,
            }
        return (
            await self._call(
                wire.MICROCONTROLLER_IO_KIND_CONFIGURE,
                deadline_ns,
                requested=requested,
                roles=_roles(active_roles, allow_empty=True),
                **scope,
            )
        ).observation

    async def status(self, *, deadline_ns: int) -> mcu.MicrocontrollerObservation:
        return (
            await self._call(wire.MICROCONTROLLER_IO_KIND_STATUS, deadline_ns)
        ).observation

    async def keepalive(self, *, deadline_ns: int) -> mcu.MicrocontrollerState:
        # Keepalive scheduling belongs to the owner; consumers read its current state.
        return (await self.status(deadline_ns=deadline_ns)).state

    async def on(
        self,
        selected_roles: tuple[int | str, ...],
        *,
        scheduled_boundary_ns: int | None,
        deadline_ns: int,
    ) -> mcu.PulseCommandEvidence:
        fields = (
            {}
            if scheduled_boundary_ns is None
            else {"boundary_monotonic_ns": scheduled_boundary_ns}
        )
        return (
            await self._call(
                wire.MICROCONTROLLER_IO_KIND_ON,
                deadline_ns,
                roles=_roles(selected_roles),
                **fields,
            )
        ).evidence

    async def off(
        self,
        selected_roles: tuple[int | str, ...],
        *,
        scheduled_boundary_ns: int | None,
        stop_issued_ns: int | None,
        deadline_ns: int,
    ) -> mcu.PulseCommandEvidence:
        fields = {}
        if scheduled_boundary_ns is not None:
            fields["boundary_monotonic_ns"] = scheduled_boundary_ns
        if stop_issued_ns is not None:
            fields["stop_issued_monotonic_ns"] = stop_issued_ns
        return (
            await self._call(
                wire.MICROCONTROLLER_IO_KIND_OFF,
                deadline_ns,
                roles=_roles(selected_roles),
                **fields,
            )
        ).evidence

    async def reserve_boundary(
        self,
        boundary_ns: int,
        command: mcu.PulseBoundaryCommand,
        *,
        selected_roles: tuple[int | str, ...],
        deadline_ns: int,
    ) -> None:
        await self._call(
            wire.MICROCONTROLLER_IO_KIND_RESERVE,
            deadline_ns,
            roles=_roles(selected_roles),
            boundary_monotonic_ns=boundary_ns,
            boundary_command=command,
        )

    async def cancel_on_reservations(self, *, deadline_ns: int) -> None:
        await self._call(wire.MICROCONTROLLER_IO_KIND_CANCEL_ON, deadline_ns)

    async def cancel_active_request(self, *, deadline_ns: int) -> bool:
        return (
            await self._call(wire.MICROCONTROLLER_IO_KIND_CANCEL_ACTIVE, deadline_ns)
        ).cancelled

    async def close(self, *, deadline_ns: int) -> None:
        await self._call(wire.MICROCONTROLLER_IO_KIND_CLOSE, deadline_ns)
        self.claim_id = ""

    async def diagnostic_start(
        self, kind: str, pin: str, *, frequency_hz: float | None, deadline_ns: int
    ) -> tuple[bool, str, str, int]:
        raise RuntimeError("Microcontroller diagnostics are controller-owned")

    async def diagnostic_status(
        self, *, deadline_ns: int
    ) -> tuple[bool, str, str, int]:
        raise RuntimeError("Microcontroller diagnostics are controller-owned")

    async def diagnostic_stop(self, *, deadline_ns: int) -> tuple[bool, str, str, int]:
        raise RuntimeError("Microcontroller diagnostics are controller-owned")


def _roles(selected: tuple[int | str, ...], *, allow_empty: bool = False) -> list[int]:
    result = [_ROLES[role] if isinstance(role, str) else role for role in selected]
    if (
        (not result and not allow_empty)
        or len(set(result)) != len(result)
        or any(role not in _ROLES.values() for role in result)
    ):
        raise ValueError("Select distinct supported camera trigger roles")
    return result
