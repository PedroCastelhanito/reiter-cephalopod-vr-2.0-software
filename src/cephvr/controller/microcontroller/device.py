"""Single controller device owner; camera clients never open serial or run tools."""

import asyncio
from collections.abc import Callable
from typing import cast

from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.acquisition.v1 import runtime_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.microcontroller.firmware import FirmwareUploadPort
from cephvr.controller.microcontroller.firmware_operation import FirmwareUpdate
from cephvr.shared.microcontroller import SerialOwnerPort

_SAFETY_IO = frozenset(
    {
        wire.MICROCONTROLLER_IO_KIND_OFF,
        wire.MICROCONTROLLER_IO_KIND_CLOSE,
        wire.MICROCONTROLLER_IO_KIND_CANCEL_ON,
        wire.MICROCONTROLLER_IO_KIND_CANCEL_ACTIVE,
    }
)

_SIGNAL_KINDS: dict[int, str] = {
    pb.MICROCONTROLLER_SIGNAL_KIND_BEHAVIORAL: "behavioral",
    pb.MICROCONTROLLER_SIGNAL_KIND_TRACKING: "tracking",
    pb.MICROCONTROLLER_SIGNAL_KIND_TRIAL_STATE: "trial_state",
    pb.MICROCONTROLLER_SIGNAL_KIND_PROJECTOR_FLIP: "projector_flip",
}


class MicrocontrollerDevice:
    def __init__(
        self,
        serial: SerialOwnerPort,
        settings: pb.AcquisitionSettings,
        policies: acq.AcquisitionFilePolicies,
        clock: Callable[[], int],
        uploader: FirmwareUploadPort | None = None,
        policy_loader: Callable[[], acq.AcquisitionFilePolicies] | None = None,
    ) -> None:
        self.serial = serial
        self.settings = settings
        self.policies = policies
        self.clock = clock
        self.view = pb.MicrocontrollerDeviceView()
        self.firmware = FirmwareUpdate(uploader, serial, self.view, clock)
        self.manual_active = False
        self.acquisition_claimed = False
        self.claim_id = ""
        self.claim_released = asyncio.Event()
        self.claim_released.set()
        self.io_active = 0
        self.boundaries: dict[int, int] = {}
        self.port_owned = False
        self.shutdown_deadline_ns: int | None = None
        self.closed = False
        self.policy_loader = policy_loader
        self.closing = False
        self.releasing = False
        self._close_lock = asyncio.Lock()
        self._close_stopped = False
        self.changed: Callable[[], None] = lambda: None

    @property
    def busy(self) -> bool:
        return self.manual_active or self.firmware.busy or self.io_active > 0

    @property
    def cleanup_complete(self) -> bool:
        return not (
            self.port_owned
            or self.busy
            or self.acquisition_claimed
            or self.closing
            or self.releasing
        )

    def ensure_idle(self, *, allow_release: bool = False) -> None:
        self.firmware.ensure_idle()
        if (
            self.manual_active
            or self.closed
            or self.closing
            or (self.releasing and not allow_release)
        ):
            raise RuntimeError("Microcontroller operation is unavailable or pending")

    @property
    def failure(self) -> str:
        return self.view.failure

    @failure.setter
    def failure(self, value: str) -> None:
        self.view.failure = value

    def snapshot_view(self) -> pb.MicrocontrollerDeviceView:
        self.view.cleanup_pending = (
            self.closing or self.releasing or self.manual_active or self.firmware.busy
        )
        return self.view

    def reload_idle_policy(self) -> None:
        if self.policy_loader is None:
            return
        latest = self.policy_loader()
        if self.port_owned:
            if latest != self.policies:
                raise RuntimeError(
                    "Release the Microcontroller before changing serial policy"
                )
        else:
            self.policies.CopyFrom(latest)

    async def execute(
        self,
        request: wire.MicrocontrollerCommandRequest,
        pulses: camera.CameraPulseConfiguration,
        deadline_ns: int,
    ) -> None:
        self.ensure_idle()
        if self.acquisition_claimed or self.io_active:
            raise RuntimeError(
                "Release camera triggering before Microcontroller diagnostics or Upload"
            )
        if (
            request.kind == wire.MICROCONTROLLER_COMMAND_KIND_CONNECT
            and self.view.diagnostic.active
        ):
            raise RuntimeError(
                "Stop diagnostics before reconnecting the Microcontroller"
            )
        self.reload_idle_policy()
        self.manual_active = True
        self.changed()
        self.settings.pulses.CopyFrom(pulses)
        try:
            if request.kind == wire.MICROCONTROLLER_COMMAND_KIND_UPLOAD_FIRMWARE:
                if self.view.diagnostic.active:
                    raise RuntimeError("Stop diagnostics before firmware upload")
                await self.firmware.execute(
                    request.firmware_path,
                    request.firmware_sha256,
                    pulses.port,
                    pb.OperationContext(command_id=request.command.operator.command_id),
                    deadline_ns,
                )
                self.port_owned = self.view.HasField("observation")
                self.failure = ""
                return
            if (
                request.kind == wire.MICROCONTROLLER_COMMAND_KIND_CONNECT
                or not self.view.HasField("observation")
            ):
                self.port_owned = True
                self.view.observation.CopyFrom(
                    await self.serial.connect(deadline_ns=deadline_ns)
                )
                self.failure = ""
            if request.kind == wire.MICROCONTROLLER_COMMAND_KIND_CONNECT:
                self.view.ClearField("diagnostic")
            elif request.kind == wire.MICROCONTROLLER_COMMAND_KIND_START:
                if self.view.diagnostic.active:
                    raise RuntimeError(
                        "Stop the active pin test before starting another"
                    )
                kind, pin, frequency = diagnostic_selection(request.signal, pulses)
                if frequency is not None:
                    self.view.observation.CopyFrom(
                        await self.serial.configure(
                            pulses, active_roles=(kind,), deadline_ns=deadline_ns
                        )
                    )
                active, _, _, edges = await self.serial.diagnostic_start(
                    kind, pin, frequency_hz=frequency, deadline_ns=deadline_ns
                )
                self.view.diagnostic.CopyFrom(
                    pb.MicrocontrollerDiagnosticView(
                        signal=request.signal,
                        observed_monotonic_ns=self.clock(),
                        pin=pin,
                        active=active,
                        rising_edges=edges,
                    )
                )
            else:
                active, kind, pin, edges = (
                    await self.serial.diagnostic_status(deadline_ns=deadline_ns)
                    if request.kind == wire.MICROCONTROLLER_COMMAND_KIND_STATUS
                    else await self.serial.diagnostic_stop(deadline_ns=deadline_ns)
                )
                signal = next(
                    (
                        signal
                        for signal, value in _SIGNAL_KINDS.items()
                        if value == kind
                    ),
                    0,
                )
                self.view.diagnostic.CopyFrom(
                    pb.MicrocontrollerDiagnosticView(
                        signal=cast(pb.MicrocontrollerSignalKind, signal),
                        observed_monotonic_ns=self.clock(),
                        pin=pin,
                        active=active,
                        rising_edges=edges,
                    )
                )
        except Exception as exc:
            if request.kind == wire.MICROCONTROLLER_COMMAND_KIND_CONNECT:
                self.failure = str(exc)[:2048]
            raise
        finally:
            self.manual_active = False
            self.changed()

    async def io(
        self, request: wire.MicrocontrollerIoRequest
    ) -> wire.MicrocontrollerIoResult:
        if (
            request.kind == wire.MICROCONTROLLER_IO_KIND_CLOSE
            and not self.acquisition_claimed
            and not self.io_active
        ):
            return wire.MicrocontrollerIoResult(
                command_id=request.command_id, succeeded=True
            )
        self.ensure_idle(allow_release=request.kind in _SAFETY_IO)
        self.io_active += 1
        try:
            return await self._io(request)
        except Exception as exc:
            if (
                request.kind == wire.MICROCONTROLLER_IO_KIND_CONNECT
                and self.acquisition_claimed
            ):
                self.failure = str(exc)[:2048]
            raise
        finally:
            self.io_active -= 1
            self.changed()

    def next_boundary(self, now_ns: int) -> int | None:
        return min((value for value in self.boundaries if value > now_ns), default=None)

    def observation(self) -> mcu.MicrocontrollerObservation | None:
        return self.view.observation if self.view.HasField("observation") else None

    async def _io(
        self, request: wire.MicrocontrollerIoRequest
    ) -> wire.MicrocontrollerIoResult:
        self.ensure_idle(allow_release=request.kind in _SAFETY_IO)
        if self.view.diagnostic.active:
            raise RuntimeError(
                "Stop the controller pin test before acquiring camera triggers"
            )
        deadline_ns = request.deadline_monotonic_ns
        if self.clock() >= deadline_ns:
            raise TimeoutError("Original Microcontroller deadline expired")
        kind = request.kind
        if self.failure and kind in {
            wire.MICROCONTROLLER_IO_KIND_CONNECT,
            wire.MICROCONTROLLER_IO_KIND_CONFIGURE,
            wire.MICROCONTROLLER_IO_KIND_ON,
            wire.MICROCONTROLLER_IO_KIND_RESERVE,
        }:
            raise RuntimeError(
                "Reconnect the Microcontroller explicitly after its failure: "
                + self.failure
            )
        result = wire.MicrocontrollerIoResult(
            command_id=request.command_id, succeeded=True
        )
        roles = tuple(request.roles)
        if kind == wire.MICROCONTROLLER_IO_KIND_CONNECT:
            if self.acquisition_claimed:
                raise RuntimeError("A camera-trigger claim is already active")
            if not request.claim_id or request.claim_id != request.command_id:
                raise ValueError(
                    "CONNECT must establish its exact command as the device claim"
                )
            self.reload_idle_policy()
            if request.requested.port != self.settings.pulses.port:
                raise ValueError(
                    "Camera trigger request targets a different configured port"
                )
            self.acquisition_claimed = True
            self.claim_id = request.claim_id
            self.claim_released.clear()
            self.port_owned = True
            self.view.observation.CopyFrom(
                await self.serial.connect(deadline_ns=deadline_ns)
            )
            result.observation.CopyFrom(self.view.observation)
        elif (
            kind == wire.MICROCONTROLLER_IO_KIND_CLOSE and not self.acquisition_claimed
        ):
            return result
        elif not self.acquisition_claimed or request.claim_id != self.claim_id:
            raise RuntimeError("Camera trigger client has no active device claim")
        elif kind == wire.MICROCONTROLLER_IO_KIND_CONFIGURE:
            if request.requested.port != self.settings.pulses.port:
                raise ValueError(
                    "Camera trigger request targets a different configured port"
                )
            self.view.observation.CopyFrom(
                await self.serial.configure(
                    request.requested, active_roles=roles, deadline_ns=deadline_ns
                )
            )
            result.observation.CopyFrom(self.view.observation)
        elif kind == wire.MICROCONTROLLER_IO_KIND_STATUS:
            self.view.observation.CopyFrom(
                await self.serial.status(deadline_ns=deadline_ns)
            )
            result.observation.CopyFrom(self.view.observation)
        elif kind in (
            wire.MICROCONTROLLER_IO_KIND_ON,
            wire.MICROCONTROLLER_IO_KIND_OFF,
        ):
            boundary = (
                request.boundary_monotonic_ns
                if request.HasField("boundary_monotonic_ns")
                else None
            )
            if kind == wire.MICROCONTROLLER_IO_KIND_ON:
                evidence = await self.serial.on(
                    roles, scheduled_boundary_ns=boundary, deadline_ns=deadline_ns
                )
            else:
                issued = (
                    request.stop_issued_monotonic_ns
                    if request.HasField("stop_issued_monotonic_ns")
                    else None
                )
                evidence = await self.serial.off(
                    roles,
                    scheduled_boundary_ns=boundary,
                    stop_issued_ns=issued,
                    deadline_ns=deadline_ns,
                )
            if boundary is not None and evidence.error_code != "BOUNDARY_NOT_DUE":
                self.boundaries.pop(boundary, None)
            result.evidence.CopyFrom(evidence)
            if evidence.HasField("resulting_state"):
                self.view.observation.state.CopyFrom(evidence.resulting_state)
                self.view.observation.observed_monotonic_ns = self.clock()
        elif kind == wire.MICROCONTROLLER_IO_KIND_RESERVE:
            if not request.HasField("boundary_monotonic_ns"):
                raise ValueError("Boundary reservation requires an original target")
            await self.serial.reserve_boundary(
                request.boundary_monotonic_ns,
                request.boundary_command,
                selected_roles=roles,
                deadline_ns=deadline_ns,
            )
            self.boundaries[request.boundary_monotonic_ns] = request.boundary_command
        elif kind == wire.MICROCONTROLLER_IO_KIND_CANCEL_ON:
            await self.serial.cancel_on_reservations(deadline_ns=deadline_ns)
            self.boundaries = {
                boundary: command
                for boundary, command in self.boundaries.items()
                if command != mcu.PULSE_BOUNDARY_COMMAND_ON
            }
        elif kind == wire.MICROCONTROLLER_IO_KIND_CANCEL_ACTIVE:
            result.cancelled = await self.serial.cancel_active_request(
                deadline_ns=deadline_ns
            )
        elif kind == wire.MICROCONTROLLER_IO_KIND_CLOSE:
            await self.serial.close(deadline_ns=deadline_ns)
            self.acquisition_claimed = False
            self.claim_id = ""
            self.claim_released.set()
            self.port_owned = False
            self.boundaries.clear()
            self.view.ClearField("observation")
        else:
            raise ValueError("Unsupported Microcontroller camera operation")
        self.changed()
        return result

    async def close(self, *, deadline_ns: int, permanent: bool = True) -> None:
        # Fence before awaiting active tools or serial work. A failed close stays fenced.
        self.closing = True
        self.closed = self.closed or permanent
        self.changed()
        try:
            async with asyncio.timeout(max(0, (deadline_ns - self.clock()) / 1e9)):
                async with self._close_lock:
                    await self.firmware.close(deadline_ns=deadline_ns)
                    if self.view.HasField("observation") and not self._close_stopped:
                        await self.serial.cancel_on_reservations(
                            deadline_ns=deadline_ns
                        )
                        active, _, _, _ = await self.serial.diagnostic_stop(
                            deadline_ns=deadline_ns
                        )
                        evidence = await self.serial.off(
                            (
                                camera.CAMERA_ROLE_BEHAVIORAL,
                                camera.CAMERA_ROLE_TRACKING,
                            ),
                            scheduled_boundary_ns=None,
                            stop_issued_ns=self.clock(),
                            deadline_ns=deadline_ns,
                        )
                        if (
                            active
                            or evidence.outcome != mcu.PULSE_COMMAND_OUTCOME_APPLIED
                            or not all(
                                evidence.resulting_state.HasField(role)
                                and getattr(evidence.resulting_state, role).HasField(
                                    "running"
                                )
                                and not getattr(evidence.resulting_state, role).running
                                for role in ("behavioral", "tracking")
                            )
                        ):
                            raise RuntimeError(
                                "Microcontroller stopped outputs remain unconfirmed"
                            )
                        self._close_stopped = True
                        self.view.observation.state.CopyFrom(evidence.resulting_state)
                        self.view.diagnostic.active = False
                    await self.serial.close(deadline_ns=deadline_ns)
                    self._close_stopped = False
                    self.acquisition_claimed = False
                    self.claim_id = ""
                    self.claim_released.set()
                    self.port_owned = False
                    self.boundaries.clear()
                    self.view.ClearField("observation")
                    self.view.ClearField("diagnostic")
                    self.closing = False
                    self.releasing = False
        finally:
            self.changed()


def diagnostic_selection(
    signal: int, pulses: camera.CameraPulseConfiguration
) -> tuple[str, str, float | None]:
    kind = _SIGNAL_KINDS.get(signal)
    if kind is None:
        raise ValueError("Select a supported Microcontroller signal")
    if kind in ("trial_state", "projector_flip"):
        if not getattr(pulses, f"{kind}_enabled") or not pulses.HasField(f"{kind}_pin"):
            raise ValueError("Signal has no enabled pin assignment")
        return kind, getattr(pulses, f"{kind}_pin"), None
    pulse = getattr(pulses, kind)
    if not pulse.HasField("pin") or not pulse.HasField("requested_frequency_hz"):
        raise ValueError("Camera signal has no pin/frequency assignment")
    return kind, pulse.pin, pulse.requested_frequency_hz
