"""Serial owner exclusivity, cancellation and reserved-off scheduling."""

from __future__ import annotations

import asyncio
import sys
import threading
from collections import deque
from types import SimpleNamespace
from typing import cast

import pytest

from cephvr.acquisition.microcontroller import SerialOwner, SerialOwnerBridge
from cephvr.acquisition.microcontroller.channel import ChannelDeadline
from cephvr.acquisition.microcontroller.owner import SerialOwnerError
from cephvr.acquisition.microcontroller.serial_port import PySerialPort
from cephvr.acquisition.v1 import microcontroller_pb2, runtime_pb2
from cephvr.shared.clock import host_time_ns


def test_native_serial_write_uses_remaining_command_budget_without_read_reconfiguration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes: list[bytes] = []
    budgets: list[tuple[int, float]] = []

    class NativeSerial:
        def __init__(self, **kwargs: object) -> None:
            self._port_handle = 1234
            self.timeout = kwargs["timeout"]
            self.write_timeout = kwargs["write_timeout"]

        def write(self, payload: bytes) -> int:
            writes.append(payload)
            assert self.write_timeout == 0.01
            return len(payload)

    monkeypatch.setitem(
        sys.modules,
        "serial",
        SimpleNamespace(Serial=NativeSerial, SerialException=OSError),
    )
    monkeypatch.setattr(
        "cephvr.acquisition.microcontroller.serial_port.set_write_timeout",
        lambda handle, seconds: budgets.append((handle, seconds)),
    )
    now = 1_000_000_000
    monkeypatch.setattr(
        "cephvr.acquisition.microcontroller.serial_port.host_time_ns", lambda: now
    )
    port = PySerialPort("COM8", 115200)
    port.set_timeouts(read_seconds=0.1, write_seconds=0.1)
    assert port._serial.timeout == 0.01
    assert port._serial.write_timeout == 0.01
    now += 20_000_000
    payload = b"CONFIGURE " + b"x" * 300 + b"\n"
    assert port.write(payload) == len(payload)
    assert writes == [payload]
    assert budgets == [(1234, pytest.approx(0.08))]
    port.set_timeouts(read_seconds=0.01, write_seconds=0.01)
    assert port._serial.write_timeout == 0.01
    now += 11_000_000
    with pytest.raises(TimeoutError, match="before dispatch"):
        port.write(payload)
    assert writes == [payload]


def test_expired_owner_call_keeps_serial_gate_until_blocked_call_returns() -> None:
    async def scenario() -> None:
        fake = _BlockingOwner()
        bridge = SerialOwnerBridge(lambda: cast(SerialOwner, fake))
        with pytest.raises(TimeoutError):
            await bridge.connect(deadline_ns=host_time_ns() + 20_000_000)
        assert await asyncio.to_thread(fake.finished.wait, 1.0)
        await bridge.status(deadline_ns=host_time_ns() + 1_000_000_000)
        await bridge.close(deadline_ns=host_time_ns() + 1_000_000_000)
        assert fake.maximum_active == 1
        assert fake.thread_ids[0] == fake.thread_ids[1] == fake.thread_ids[2]

    asyncio.run(scenario())


def test_waiting_owner_calls_cannot_overwrite_or_steal_the_exclusive_gate() -> None:
    async def scenario() -> None:
        fake = _StubbornOwner()
        bridge = SerialOwnerBridge(lambda: cast(SerialOwner, fake))
        with pytest.raises(TimeoutError):
            await bridge.connect(deadline_ns=host_time_ns() + 20_000_000)
        assert fake.started.wait(0.2)
        with pytest.raises(TimeoutError):
            await bridge.status(deadline_ns=host_time_ns() + 10_000_000)
        with pytest.raises(TimeoutError):
            await bridge.status(deadline_ns=host_time_ns() + 10_000_000)
        assert fake.thread_ids == [fake.owner_thread]
        fake.release.set()
        assert await asyncio.to_thread(fake.finished.wait, 1.0)
        await bridge.status(deadline_ns=host_time_ns() + 1_000_000_000)
        await bridge.close(deadline_ns=host_time_ns() + 1_000_000_000)
        assert fake.maximum_active == 1

    asyncio.run(scenario())


class _BlockingOwner:
    def __init__(self) -> None:
        self.finished = threading.Event()
        self.release = threading.Event()
        self.active = 0
        self.maximum_active = 0
        self.thread_ids: list[int] = []

    def connect(self, deadline_ns: int) -> None:
        del deadline_ns
        self._block()

    def status(self, deadline_ns: int) -> None:
        del deadline_ns
        self._block()

    def close(self, deadline_ns: int) -> None:
        del deadline_ns
        self._block()

    def cancel_active_request(self) -> bool:
        self.release.set()
        return True

    def _block(self) -> None:
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        self.thread_ids.append(threading.get_ident())
        if len(self.thread_ids) == 1:
            self.release.wait()
        self.active -= 1
        if len(self.thread_ids) == 1:
            self.finished.set()


class _StubbornOwner:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.finished = threading.Event()
        self.release = threading.Event()
        self.owner_thread = -1
        self.thread_ids: list[int] = []
        self.active = 0
        self.maximum_active = 0

    def connect(self, deadline_ns: int) -> None:
        del deadline_ns
        self._block(block=True)

    def status(self, deadline_ns: int) -> None:
        del deadline_ns
        self._block(block=False)

    def close(self, deadline_ns: int) -> None:
        del deadline_ns
        self._block(block=False)

    def cancel_active_request(self) -> bool:
        return True

    def _block(self, *, block: bool) -> None:
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        self.owner_thread = threading.get_ident()
        self.thread_ids.append(self.owner_thread)
        self.started.set()
        if block:
            self.release.wait()
            self.finished.set()
        self.active -= 1


def test_reconnect_explicitly_stops_running_outputs_and_reads_back_status() -> None:
    clock = _Clock(10)
    port = _ScriptedPort(statuses=[_status(behavioral_running=True), _status()])
    owner = SerialOwner("COM7", _policies(), clock=clock, serial_port=port)

    observation = owner.connect(deadline_ns=10_000)

    assert port.verbs == ["CAPS", "STATUS", "OFF", "STATUS"]
    assert port.fields[2] == {
        "behavioral_selected": "1",
        "tracking_selected": "0",
    }
    assert observation.state.behavioral.running is False
    assert observation.state.tracking.running is False


def test_expired_close_still_releases_serial_handle_without_claiming_timely_stop() -> (
    None
):
    clock = _Clock(10)
    port = _ScriptedPort(statuses=[_status()])
    owner = SerialOwner("COM7", _policies(), clock=clock, serial_port=port)
    owner.connect(deadline_ns=10_000)

    with pytest.raises(SerialOwnerError, match="completion was late"):
        owner.close(deadline_ns=9)

    assert port.closed


def test_expired_startup_failure_still_releases_serial_handle() -> None:
    clock = _Clock(10)
    port = _ScriptedPort(statuses=[])
    owner = SerialOwner("COM7", _policies(), clock=clock, serial_port=port)
    owner._channel.open(10_000)

    with pytest.raises(SerialOwnerError, match="closed the port after"):
        owner._close_after_startup_failure(deadline_ns=9)

    assert port.closed


def test_bounded_trial_output_diagnostic_uses_one_serial_owner() -> None:
    clock = _Clock(10)
    port = _ScriptedPort(statuses=[_status()])
    owner = SerialOwner("COM7", _policies(), clock=clock, serial_port=port)
    owner.connect(deadline_ns=10_000)

    assert owner.diagnostic_start("trial_state", "D2", 10_000) == (
        True,
        "trial_state",
        "D2",
        0,
    )
    assert owner.diagnostic_status(10_000)[0]
    assert owner.diagnostic_stop(10_000) == (False, "trial_state", "D2", 0)
    assert port.verbs == ["CAPS", "STATUS", "DIAG_START", "DIAG_STATUS", "DIAG_STOP"]
    assert port.fields[2] == {"kind": "trial_state", "pin": "D2", "duration_ms": "2000"}


def test_flip_input_requires_firmware_advertised_interrupt_pin() -> None:
    clock = _Clock(10)
    port = _ScriptedPort(statuses=[_status()])
    owner = SerialOwner("COM7", _policies(), clock=clock, serial_port=port)
    owner.connect(deadline_ns=10_000)

    with pytest.raises(ValueError, match="rising-edge input"):
        owner.diagnostic_start("projector_flip", "D4", 10_000)

    assert port.verbs == ["CAPS", "STATUS"]


def test_reserved_off_blocks_routine_status_and_dispatches_with_original_deadline() -> (
    None
):
    clock = _Clock(10)
    port = _ScriptedPort(statuses=[_status()])
    owner = SerialOwner("COM7", _policies(ack_ns=20), clock=clock, serial_port=port)
    owner.connect(deadline_ns=10_000)
    boundary_ns = 100
    owner.reserve_boundary(
        boundary_ns,
        microcontroller_pb2.PULSE_BOUNDARY_COMMAND_OFF,
        selected_roles=("behavioral",),
    )

    clock.value = 80
    before = len(port.verbs)
    with pytest.raises(ChannelDeadline, match="cannot drain before reserved boundary"):
        owner.status(deadline_ns=1_000)
    assert len(port.verbs) == before

    clock.value = boundary_ns
    original_deadline_ns = boundary_ns + 20
    evidence = owner.off(
        ("behavioral",),
        original_deadline_ns,
        scheduled_boundary_ns=boundary_ns,
    )

    assert evidence.outcome == microcontroller_pb2.PULSE_COMMAND_OUTCOME_APPLIED
    assert evidence.scheduled_boundary_monotonic_ns == boundary_ns
    assert evidence.dispatched_monotonic_ns == boundary_ns
    assert evidence.acknowledged_monotonic_ns == boundary_ns
    assert evidence.acknowledged_monotonic_ns < original_deadline_ns
    assert port.verbs[-1] == "OFF"


def _policies(*, ack_ns: int = 20) -> runtime_pb2.AcquisitionFilePolicies:
    return runtime_pb2.AcquisitionFilePolicies(
        serial_baud_rate=115_200,
        serial_ack_timeout_ns=ack_ns,
        serial_keepalive_interval_ns=100_000_000,
        serial_communication_timeout_ns=1_000_000_000,
        serial_stop_completion_margin_ns=10_000,
    )


def _status(*, behavioral_running: bool = False) -> bytes:
    running = "1" if behavioral_running else "0"
    enabled = "1" if behavioral_running else "0"
    role_fields = (
        f"behavioral_enabled={enabled} behavioral_running={running}"
        + (
            " behavioral_pin=D2 behavioral_applied_hz=10.0"
            if behavioral_running
            else ""
        )
        + " tracking_enabled=0 tracking_running=0"
    )
    return ("valid=0 watchdog_stopped=0 watchdog_ms=1000 " + role_fields).encode(
        "ascii"
    )


class _Clock:
    def __init__(self, value: int) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value


class _ScriptedPort:
    def __init__(self, *, statuses: list[bytes]) -> None:
        self._statuses = deque(statuses)
        self._incoming: deque[int] = deque()
        self.verbs: list[str] = []
        self.fields: list[dict[str, str]] = []
        self.closed = False

    def set_timeouts(self, *, read_seconds: float, write_seconds: float) -> None:
        del read_seconds, write_seconds

    def write(self, payload: bytes) -> int:
        parts = payload.decode("ascii").strip().split()
        verb = parts[0]
        request_id = parts[1].split("=", 1)[1]
        fields = dict(part.split("=", 1) for part in parts[2:])
        self.verbs.append(verb)
        self.fields.append(fields)
        if verb == "CAPS":
            body = (
                "protocol=2 firmware=board pins=D2,D4 input_pins=D2 min_hz=0.1 max_hz=60.0 "
                "watchdog_min_ms=100 watchdog_max_ms=10000"
            )
        elif verb == "STATUS":
            body = self._statuses.popleft().decode("ascii")
        elif verb == "OFF":
            body = "watchdog_stopped=0 behavioral_running=0 tracking_running=0"
        elif verb.startswith("DIAG_"):
            body = (
                "active=0" if verb == "DIAG_STOP" else "active=1"
            ) + " kind=trial_state pin=D2 edges=0"
        else:
            raise AssertionError(f"unexpected command {verb}")
        line = f"OK id={request_id} {body}\n".encode("ascii")
        self._incoming.extend(line)
        return len(payload)

    def read(self, size: int = 1) -> bytes:
        del size
        if not self._incoming:
            return b""
        return bytes((self._incoming.popleft(),))

    def cancel_read(self) -> None:
        return None

    def cancel_write(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


async def test_lazy_connection_closes_previous_com_before_opening_new_selection(
    monkeypatch,
) -> None:
    from cephvr.acquisition.microcontroller import lazy_owner as module
    from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
    from cephvr.acquisition.v1 import runtime_pb2
    from cephvr.control.v1 import types_pb2 as pb

    events = []

    class Bridge:
        def __init__(self, name):
            self.name = name

        async def close(self, *, deadline_ns):
            events.append(("close", self.name, deadline_ns))

        async def connect(self, *, deadline_ns):
            events.append(("connect", self.name, deadline_ns))
            return mcu.MicrocontrollerObservation(port=self.name)

    settings = pb.AcquisitionSettings()
    settings.pulses.port = "COM9"
    owner = module.LazySerialOwner(
        settings, runtime_pb2.AcquisitionFilePolicies(), lambda _: None
    )
    owner.bridge, owner.port, owner.connected = Bridge("COM8"), "COM8", True
    monkeypatch.setattr(module, "SerialOwnerBridge", lambda _: Bridge("COM9"))
    observed = await owner.connect(deadline_ns=123)
    assert observed.port == "COM9"
    assert events == [("close", "COM8", 123), ("connect", "COM9", 123)]
