"""Typed Microcontroller operations shared by its controller owner and clients."""

from typing import Protocol

from cephvr.acquisition.v1 import camera_pb2, microcontroller_pb2


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
    async def cancel_active_request(self, *, deadline_ns: int) -> bool: ...
    async def close(self, *, deadline_ns: int) -> None: ...
