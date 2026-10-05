"""Lazy serial-owner construction for roles that actually use external triggers."""

from __future__ import annotations

from collections.abc import Callable

from cephvr.acquisition.microcontroller.bridge import SerialOwnerBridge
from cephvr.acquisition.microcontroller.owner import SerialOwner
from cephvr.acquisition.microcontroller.serial_port import PySerialPort
from cephvr.acquisition.ports import SerialOwnerPort
from cephvr.acquisition.v1 import camera_pb2, runtime_pb2
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import types_pb2 as control


class LazySerialOwner(SerialOwnerPort):
    """Construct MCU protocol only when an active role needs a serial port."""

    def __init__(
        self,
        settings: control.AcquisitionSettings,
        policies: runtime_pb2.AcquisitionFilePolicies,
        on_create: Callable[[SerialOwnerBridge], None],
    ) -> None:
        self.settings = settings
        self.policies = policies
        self.on_create = on_create
        self.bridge: SerialOwnerBridge | None = None
        self.port: str | None = None
        self.connected = False

    def _ensure(self, requested_port: str | None = None) -> SerialOwnerBridge:
        if self.bridge is not None:
            return self.bridge
        pulses = self.settings.pulses
        port = requested_port or (pulses.port if pulses.HasField("port") else "")
        if not port:
            raise ValueError(
                "active external-trigger cameras require a configured MCU port"
            )
        baud_rate = self.policies.serial_baud_rate

        def create_owner() -> SerialOwner:
            return SerialOwner(
                port,
                self.policies,
                serial_port=PySerialPort(port, baud_rate),
            )

        self.bridge = SerialOwnerBridge(create_owner)
        self.port = port
        self.on_create(self.bridge)
        return self.bridge

    async def connect(self, *, deadline_ns: int) -> mcu.MicrocontrollerObservation:
        bridge = self._ensure()
        if self.connected:
            return await bridge.status(deadline_ns=deadline_ns)
        observation = await bridge.connect(deadline_ns=deadline_ns)
        self.connected = True
        return observation

    async def configure(
        self,
        requested: camera_pb2.CameraPulseConfiguration,
        *,
        active_roles: tuple[int | str, ...],
        deadline_ns: int,
    ) -> mcu.MicrocontrollerObservation:
        selected_port = requested.port if requested.HasField("port") else None
        if self.bridge is not None and selected_port and selected_port != self.port:
            await self.bridge.close(deadline_ns=deadline_ns)
            self.bridge = None
            self.port = None
            self.connected = False
        return await self._ensure(selected_port).configure(
            requested, active_roles=active_roles, deadline_ns=deadline_ns
        )

    async def status(self, *, deadline_ns: int) -> mcu.MicrocontrollerObservation:
        return await self._ensure().status(deadline_ns=deadline_ns)

    async def keepalive(self, *, deadline_ns: int) -> mcu.MicrocontrollerState:
        return await self._ensure().keepalive(deadline_ns=deadline_ns)

    async def diagnostic_start(
        self, kind: str, pin: str, *, frequency_hz: float | None, deadline_ns: int
    ) -> tuple[bool, str, str, int]:
        return await self._ensure().diagnostic_start(
            kind, pin, frequency_hz=frequency_hz, deadline_ns=deadline_ns
        )

    async def diagnostic_status(
        self, *, deadline_ns: int
    ) -> tuple[bool, str, str, int]:
        return await self._ensure().diagnostic_status(deadline_ns=deadline_ns)

    async def diagnostic_stop(self, *, deadline_ns: int) -> tuple[bool, str, str, int]:
        return await self._ensure().diagnostic_stop(deadline_ns=deadline_ns)

    async def on(
        self,
        selected_roles: tuple[int | str, ...],
        *,
        scheduled_boundary_ns: int | None,
        deadline_ns: int,
    ) -> mcu.PulseCommandEvidence:
        return await self._ensure().on(
            selected_roles,
            scheduled_boundary_ns=scheduled_boundary_ns,
            deadline_ns=deadline_ns,
        )

    async def off(
        self,
        selected_roles: tuple[int | str, ...],
        *,
        scheduled_boundary_ns: int | None,
        stop_issued_ns: int | None,
        deadline_ns: int,
    ) -> mcu.PulseCommandEvidence:
        return await self._ensure().off(
            selected_roles,
            scheduled_boundary_ns=scheduled_boundary_ns,
            stop_issued_ns=stop_issued_ns,
            deadline_ns=deadline_ns,
        )

    async def reserve_boundary(
        self,
        boundary_ns: int,
        command: mcu.PulseBoundaryCommand,
        *,
        selected_roles: tuple[int | str, ...],
        deadline_ns: int,
    ) -> None:
        await self._ensure().reserve_boundary(
            boundary_ns,
            command,
            selected_roles=selected_roles,
            deadline_ns=deadline_ns,
        )

    async def cancel_on_reservations(self, *, deadline_ns: int) -> None:
        if self.bridge is not None:
            await self.bridge.cancel_on_reservations(deadline_ns=deadline_ns)

    async def cancel_active_request(self) -> bool:
        return (
            False if self.bridge is None else await self.bridge.cancel_active_request()
        )

    async def close(self, *, deadline_ns: int) -> None:
        if self.bridge is not None:
            await self.bridge.close(deadline_ns=deadline_ns)
            self.bridge = None
            self.port = None
            self.connected = False
