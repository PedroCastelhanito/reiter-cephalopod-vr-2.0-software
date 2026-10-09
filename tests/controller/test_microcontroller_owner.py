"""Serial owner exclusivity, cancellation and reserved-off scheduling."""

from __future__ import annotations

import asyncio
import sys
import threading
from collections import deque
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import microcontroller_pb2, runtime_pb2
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.controller.microcontroller import SerialOwner, SerialOwnerBridge
from cephvr.controller.microcontroller.channel import ChannelDeadline
from cephvr.controller.microcontroller.device import MicrocontrollerDevice
from cephvr.controller.microcontroller.lifecycle import MicrocontrollerLifecycle
from cephvr.controller.microcontroller.owner import SerialOwnerError
from cephvr.controller.microcontroller.serial_port import PySerialPort
from cephvr.controller.state import (
    ConfigurationEdit,
    ConfigurationEditTerminal,
    ConfigurationState,
    DeviceState,
    LifecycleState,
)
from cephvr.shared.clock import host_time_ns
from cephvr.shared.microcontroller import SerialOwnerPort


def test_owned_configuration_edit_scopes_candidate_microcontroller_write() -> None:
    async def scenario() -> None:
        now = 100
        acquisition_generation = str(uuid4())
        calls: list[camera.CameraPulseConfiguration] = []
        serial_effects: list[str] = []

        class Serial:
            async def configure(self, requested, *, active_roles, deadline_ns):
                assert active_roles == (camera.CAMERA_ROLE_BEHAVIORAL,)
                assert deadline_ns == 200
                calls.append(
                    camera.CameraPulseConfiguration.FromString(
                        requested.SerializeToString(deterministic=True)
                    )
                )
                return mcu.MicrocontrollerObservation(port="COM8")

            async def status(self, *, deadline_ns):
                serial_effects.append("status")
                return mcu.MicrocontrollerObservation(port="COM8")

            async def on(self, *args, **kwargs):
                serial_effects.append("on")
                return mcu.PulseCommandEvidence()

            async def off(self, *args, **kwargs):
                serial_effects.append("off")
                return mcu.PulseCommandEvidence()

            async def close(self, *, deadline_ns):
                serial_effects.append("close")

            async def reserve_boundary(self, *args, **kwargs):
                serial_effects.append("reserve")

            async def cancel_on_reservations(self, *, deadline_ns):
                serial_effects.append("cancel_on")

            async def cancel_active_request(self, *, deadline_ns):
                serial_effects.append("cancel_active")
                return True

        current_pulses = camera.CameraPulseConfiguration(port="COM8")
        candidate_pulses = camera.CameraPulseConfiguration(port="COM8")
        candidate_pulses.behavioral.requested_frequency_hz = 20.0
        settings = control.AcquisitionSettings(pulses=current_pulses)
        owner = MicrocontrollerDevice(
            Serial(),
            settings,
            runtime_pb2.AcquisitionFilePolicies(),
            lambda: now,
        )
        owner.acquisition_claimed = True
        owner.claim_id = "claim"
        candidate = control.ExperimentConfiguration()
        acquisition = candidate.backends.add(backend_name="acquisition").acquisition
        acquisition.pulses.CopyFrom(candidate_pulses)
        edit = ConfigurationEdit(
            command=wire.OperatorCommand(),
            command_id="operator-edit",
            operation_id="edit-op",
            revision=7,
            deadline_ns=200,
            expected_cameras=frozenset(),
            expect_pulses=True,
            proposed=candidate,
        )
        device = DeviceState(configuration_edit=edit)
        device.configuration_edit_terminals[edit.operation_id] = (
            ConfigurationEditTerminal(
                operation_id=edit.operation_id,
                source=control.BackendContext(
                    backend_name="acquisition",
                    backend_generation=acquisition_generation,
                ),
                deadline_ns=200,
            )
        )
        lifecycle = LifecycleState()
        configuration = ConfigurationState(
            current=control.ExperimentConfiguration.FromString(
                candidate.SerializeToString(deterministic=True)
            ),
            policies=control.ControlPolicies(),
            revision=7,
        )
        # The accepted controller configuration still has the old pulse timing.
        configuration.current.backends[0].acquisition.pulses.CopyFrom(current_pulses)
        configuration.current.backends[
            0
        ].acquisition.pulses.behavioral.requested_frequency_hz = 10.0
        owner.settings.pulses.CopyFrom(
            configuration.current.backends[0].acquisition.pulses
        )
        controller = MicrocontrollerLifecycle(
            owner,
            generation="controller-gen",
            lifecycle=lifecycle,
            configuration=configuration,
            device=device,
            limits=SimpleNamespace(current=SimpleNamespace(setup_ns=100)),
            clock=lambda: now,
            publish=lambda: None,
            warning=_noop_warning,
            interrupt=_noop_interrupt,
            spawn=lambda coroutine: asyncio.create_task(coroutine),
        )
        from cephvr.acquisition.microcontroller_client import (
            ControllerMicrocontrollerClient,
        )
        from cephvr.shared.auth import Principal

        received = []

        class Stub:
            async def ExecuteMicrocontrollerIo(self, request, **_kwargs):
                received.append(request)
                return await controller.execute(request)

        client = ControllerMicrocontrollerClient(
            Stub(),
            Principal("acquisition", acquisition_generation, "token"),
            "controller-gen",
            lambda: current_pulses,
            clock=lambda: now,
        )
        client.claim_id = "claim"
        observation = await client.configure(
            candidate_pulses,
            active_roles=("behavioral",),
            deadline_ns=200,
            resolution_operation=control.OperationContext(command_id="edit-op"),
            requested_configuration_revision=7,
        )
        assert observation.port == "COM8"
        request = received[0]
        assert calls == [candidate_pulses]
        assert request.resolution_operation.command_id == "edit-op"
        assert request.requested_configuration_revision == 7
        assert request.claim_id == "claim"
        assert configuration.revision == 7
        assert (
            configuration.current.backends[
                0
            ].acquisition.pulses.behavioral.requested_frequency_hz
            == 10.0
        )
        assert device.camera_operation is None

        stale = wire.MicrocontrollerIoRequest.FromString(
            request.SerializeToString(deterministic=True)
        )
        stale.requested_configuration_revision = 6
        with pytest.raises(ValueError, match="not authorized"):
            await controller.execute(stale)
        assert len(calls) == 1

        partial_scope = wire.MicrocontrollerIoRequest.FromString(
            request.SerializeToString(deterministic=True)
        )
        partial_scope.ClearField("requested_configuration_revision")
        with pytest.raises(ValueError, match="not authorized"):
            await controller.execute(partial_scope)
        assert len(calls) == 1

        wrong_generation = wire.MicrocontrollerIoRequest.FromString(
            request.SerializeToString(deterministic=True)
        )
        wrong_generation.requester.generation = "stale-generation"
        with pytest.raises(ValueError, match="not authorized"):
            await controller.execute(wrong_generation)

        wrong_candidate = wire.MicrocontrollerIoRequest.FromString(
            request.SerializeToString(deterministic=True)
        )
        wrong_candidate.requested.behavioral.requested_frequency_hz = 30.0
        with pytest.raises(ValueError, match="not authorized"):
            await controller.execute(wrong_candidate)
        assert len(calls) == 1

        for kind in (
            wire.MICROCONTROLLER_IO_KIND_STATUS,
            wire.MICROCONTROLLER_IO_KIND_ON,
            wire.MICROCONTROLLER_IO_KIND_OFF,
            wire.MICROCONTROLLER_IO_KIND_RESERVE,
            wire.MICROCONTROLLER_IO_KIND_CANCEL_ON,
            wire.MICROCONTROLLER_IO_KIND_CANCEL_ACTIVE,
            wire.MICROCONTROLLER_IO_KIND_CLOSE,
        ):
            for scope in ("both", "operation", "revision"):
                scoped_non_configure = wire.MicrocontrollerIoRequest.FromString(
                    request.SerializeToString(deterministic=True)
                )
                scoped_non_configure.kind = kind
                if scope == "operation":
                    scoped_non_configure.ClearField("requested_configuration_revision")
                elif scope == "revision":
                    scoped_non_configure.ClearField("resolution_operation")
                if kind == wire.MICROCONTROLLER_IO_KIND_RESERVE:
                    scoped_non_configure.boundary_monotonic_ns = 150
                    scoped_non_configure.boundary_command = (
                        mcu.PULSE_BOUNDARY_COMMAND_ON
                    )
                with pytest.raises(ValueError, match="only valid for Configure"):
                    await controller.execute(scoped_non_configure)
                assert owner.acquisition_claimed
                assert owner.claim_id == "claim"
                assert owner.boundaries == {}
                assert not serial_effects

    async def _noop_warning(_warning) -> None:
        return None

    async def _noop_interrupt(_attempt, _message, _deadline) -> None:
        return None

    asyncio.run(scenario())


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
        "cephvr.controller.microcontroller.serial_port.set_write_timeout",
        lambda handle, seconds: budgets.append((handle, seconds)),
    )
    now = 1_000_000_000
    monkeypatch.setattr(
        "cephvr.controller.microcontroller.serial_port.host_time_ns", lambda: now
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
        1,
    )
    assert owner.diagnostic_status(10_000)[0]
    assert owner.diagnostic_stop(10_000) == (False, "trial_state", "D2", 1)
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


def test_old_firmware_is_rejected_before_output_diagnostics() -> None:
    clock = _Clock(10)
    port = _ScriptedPort(statuses=[_status()], protocol_version=2)
    owner = SerialOwner("COM7", _policies(), clock=clock, serial_port=port)
    with pytest.raises(SerialOwnerError, match="incompatible MCU protocol version 2"):
        owner.connect(deadline_ns=10_000)
    assert port.verbs == ["CAPS"]
    assert port.closed


def test_legacy_firmware_caps_rejection_stops_probe_and_closes_port() -> None:
    from cephvr.controller.microcontroller.channel import ChannelIncompatibleFirmware

    class LegacyPort(_ScriptedPort):
        def write(self, payload: bytes) -> int:
            self.verbs.append(payload.decode("ascii").split()[0])
            self._incoming.extend(b"ERR Unknown command: CAPS\r\n")
            return len(payload)

    clock = _Clock(10)
    port = LegacyPort(statuses=[])
    owner = SerialOwner("COM7", _policies(), clock=clock, serial_port=port)
    with pytest.raises(ChannelIncompatibleFirmware, match="required protocol 3"):
        owner.connect(deadline_ns=10_000)
    assert port.verbs == ["CAPS"]
    assert port.closed
    assert clock.value < 10_000


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
    def __init__(self, *, statuses: list[bytes], protocol_version: int = 3) -> None:
        self._statuses = deque(statuses)
        self._protocol_version = protocol_version
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
                f"protocol={self._protocol_version} firmware=board pins=D2,D4 input_pins=D2 min_hz=0.1 max_hz=60.0 "
                "watchdog_min_ms=100 watchdog_max_ms=10000"
            )
        elif verb == "STATUS":
            body = self._statuses.popleft().decode("ascii")
        elif verb == "OFF":
            body = "watchdog_stopped=0 behavioral_running=0 tracking_running=0"
        elif verb.startswith("DIAG_"):
            body = (
                "active=0" if verb == "DIAG_STOP" else "active=1"
            ) + " kind=trial_state pin=D2 edges=1"
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
    from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
    from cephvr.acquisition.v1 import runtime_pb2
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.controller.microcontroller import lazy_owner as module

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


def test_uno_image_validation_pins_bytes_and_rejects_bad_records(tmp_path) -> None:
    from cephvr.controller.microcontroller.firmware import read_uno_image

    path = tmp_path / "firmware.hex"
    valid = b":0400000001020304F2\n:00000001FF\n"
    path.write_bytes(valid)
    image = read_uno_image(str(path))
    assert image.payload == valid
    assert read_uno_image(str(path), image.digest) == image
    with pytest.raises(ValueError, match="absolute"):
        read_uno_image("firmware.hex")
    for invalid, message in (
        (valid.replace(b"F2", b"F3"), "checksum"),
        (valid.splitlines()[0] + b"\n", "terminal EOF"),
        (valid + valid, "after EOF"),
        (b":017E00000081\n:00000001FF\n", "application flash"),
        (valid.splitlines()[0] + b"\n" + valid, "overlapping"),
    ):
        path.write_bytes(invalid)
        with pytest.raises(ValueError, match=message):
            read_uno_image(str(path))
    path.write_bytes(valid + b"\n")
    with pytest.raises(ValueError, match="changed"):
        read_uno_image(str(path), image.digest)


@pytest.mark.parametrize(
    "source_kind,release_fails,build_failure",
    [(kind, blocked, "") for kind in ("hex", "ino") for blocked in (False, True)]
    + [("ino", False, failure) for failure in ("compiler", "checksum", "cancel")],
)
def test_firmware_native_helper_pins_image_and_retains_cleanup_until_receipt(
    tmp_path, monkeypatch, release_fails, source_kind, build_failure
):
    from pathlib import Path

    from cephvr.control.v1 import services_pb2 as wire
    from cephvr.control.v1 import types_pb2 as control
    from cephvr.controller.microcontroller import firmware_upload as upload
    from cephvr.controller.microcontroller.firmware import read_uno_image
    from cephvr.controller.microcontroller.firmware_source import read_uno_sketch
    from cephvr.controller.microcontroller.identity import FIRMWARE_UPLOAD_ROLE
    from cephvr.shared.auth import Principal

    source = tmp_path / "selected.hex"
    source.write_bytes(b":0400000001020304F2\n:00000001FF\n")
    image = read_uno_image(str(source))
    sketch_path = tmp_path / "selected.ino"
    sketch_path.write_bytes(b"void setup() {}\nvoid loop() {}\n")
    sketch = read_uno_sketch(str(sketch_path))
    cli = tmp_path / "arduino-cli.exe"
    cli.touch()
    monkeypatch.setattr(upload, "arduino_cli", lambda: cli)
    monkeypatch.setattr(upload.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(
        upload, "create_owner_only_directory", lambda path: path.mkdir()
    )
    monkeypatch.setattr(
        upload, "create_owner_only", lambda path, payload: path.write_bytes(payload)
    )
    commands = []
    owner = control.ProcessIdentity(
        role="controller", generation="00000000-0000-4000-8000-000000000001"
    )
    plan = wire.PlanLaunchRequest(
        command_id="launch",
        owner=owner,
        child=control.ProcessIdentity(role=FIRMWARE_UPLOAD_ROLE, generation="child"),
        executable=str(cli),
    )
    state = wire.LaunchState(
        plan=plan, pid=42, creation_time_100ns=142, phase=wire.LAUNCH_PHASE_OPERATIONAL
    )

    class Supervisor:
        fail = release_fails

        def GetLaunchState(self, request, **kwargs):
            assert (
                request.requester == owner
                and request.launch_command_id == state.plan.command_id
            )
            return state

        def ConfirmLaunch(self, request, **kwargs):
            assert not list(tmp_path.glob("cephvr-firmware-*"))
            assert (
                request.native_cleanup_complete
                and request.pid == state.pid
                and request.creation_time_100ns == state.creation_time_100ns
            )
            commands.append(request.command_id)
            if self.fail:
                return wire.LaunchReceipt(
                    admission=control.CommandAdmission(
                        result=control.COMMAND_RESULT_REJECTED
                    )
                )
            state.phase = wire.LAUNCH_PHASE_RELEASED
            return wire.LaunchReceipt(
                admission=control.CommandAdmission(
                    result=control.COMMAND_RESULT_ACCEPTED
                ),
                state=state,
            )

    class Process:
        child = SimpleNamespace(pid=42, creation_time_100ns=142)
        launch_id = "launch"
        cleanup_complete = False
        diagnostic_tail = ("bad sketch diagnostic",)
        stdout_text = ""
        job_name = "exact-job"

        def close_stdin(self, **kwargs):
            pass

        def wait(self, **kwargs):
            self.cleanup_complete = True
            return 1 if build_failure == "compiler" else 0

    class Launcher:
        launches = []
        pending_plans = ()
        registered_plan = None
        supervisor = Supervisor()
        owner_identity = owner
        clock_ns = staticmethod(lambda: 100)
        windows_jobs = SimpleNamespace(
            process_running=lambda pid, created: (
                (tool.cancel() or True) if build_failure == "cancel" else False
            ),
            terminate_job=lambda job: None,
        )

        def bind_operation(self, work, operation):
            assert (
                work.WhichOneof("work") is None and operation.command_id == "operation"
            )

        def launch(self, argv, **kwargs):
            assert kwargs["role"] == FIRMWARE_UPLOAD_ROLE and kwargs["capture_stdout"]
            assert argv[argv.index("--fqbn") + 1] == "arduino:avr:uno"
            self.launches.append(argv[1])
            assert kwargs["deadline_ns"] == 3_000_000_000
            if argv[1] == "compile":
                assert (
                    argv[1] == "compile"
                    and "--upload" not in argv
                    and "--port" not in argv
                )
                staged = Path(argv[-1])
                assert (staged / sketch.path.name).read_bytes() == sketch.files[0][1]
                assert sketch_path.read_bytes() != sketch.files[0][1]
                output = Path(argv[argv.index("--output-dir") + 1])
                (output / "selected.ino.hex").write_bytes(
                    image.payload.replace(b"F2", b"F3")
                    if build_failure == "checksum"
                    else image.payload
                )
                (output / "selected.ino.with_bootloader.hex").write_bytes(
                    b"never select this"
                )
            else:
                assert "--verify" in argv
                staged = Path(argv[argv.index("--input-file") + 1])
                assert staged != source and staged.read_bytes() == image.payload
                assert source.read_bytes() != image.payload
            planned = wire.PlanLaunchRequest.FromString(plan.SerializeToString())
            planned.command_id = f"launch-{len(self.launches)}"
            state.plan.CopyFrom(planned)
            state.pid = 41 + len(self.launches)
            state.creation_time_100ns = 141 + len(self.launches)
            state.phase = wire.LAUNCH_PHASE_OPERATIONAL
            process = Process()
            process.child = SimpleNamespace(
                pid=state.pid, creation_time_100ns=state.creation_time_100ns
            )
            process.launch_id = planned.command_id
            self.registered_plan(planned)
            return process

        def terminate_unconfirmed(self, **kwargs):
            pass

    launcher = Launcher()
    launcher.owner = Principal("controller", owner.generation, "token")
    tool = upload.WindowsFirmwareUpload(launcher)
    if source_kind == "hex":
        tool.prepare(image)
    source.write_bytes(image.payload + b"\n")
    sketch_path.write_bytes(b"changed since selection")

    def perform():
        if source_kind == "ino":
            result = tool.compile(
                sketch,
                control.OperationContext(command_id="operation"),
                deadline_ns=3_000_000_000,
            )
            assert result.payload == image.payload and result.digest == image.digest
            assert (
                tool.cleanup_complete
            )  # Compiler job/pipe/source cleanup precedes flash.
            tool.prepare(result)
            tool.upload(
                "COM8",
                control.OperationContext(command_id="operation"),
                deadline_ns=3_000_000_000,
            )
            assert launcher.launches == ["compile", "upload"]
        else:
            tool.upload(
                "COM8",
                control.OperationContext(command_id="operation"),
                deadline_ns=3_000_000_000,
            )

    if release_fails:
        with pytest.raises(RuntimeError, match="not confirmed"):
            perform()
        assert not tool.cleanup_complete
        launcher.supervisor.fail = False
        tool.close(deadline_ns=3_000_000_000)
        assert commands[0] == commands[1]
    elif build_failure:
        with pytest.raises(
            (RuntimeError, ValueError),
            match={
                "compiler": "bad sketch diagnostic",
                "checksum": "checksum",
                "cancel": "cancelled",
            }[build_failure],
        ):
            perform()
    else:
        perform()
    assert tool.cleanup_complete
    assert not list(tmp_path.glob("cephvr-firmware-*"))


def test_uno_sketch_digest_pins_companions_and_rejects_links(tmp_path):
    from cephvr.controller.microcontroller.firmware_source import (
        read_firmware,
        read_uno_sketch,
    )

    root = tmp_path / "sketch"
    root.mkdir()
    source = root / "sketch.ino"
    source.write_bytes(b'#include "pin.h"\nvoid setup() {}\nvoid loop() {}\n')
    header = root / "pin.h"
    header.write_bytes(b"#define PIN 9\n")
    (root / "README.md").write_text("ignored")
    (root / "src").mkdir()
    (root / "src" / "helper.cpp").write_bytes(b"void helper() {}\n")
    selected = read_firmware(str(source))
    assert [path.as_posix() for path, _ in selected.files] == [
        "pin.h",
        "sketch.ino",
        "src/helper.cpp",
    ]
    assert read_uno_sketch(str(source), selected.digest) == selected
    header.write_bytes(b"#define PIN 10\n")
    with pytest.raises(ValueError, match="changed"):
        read_uno_sketch(str(source), selected.digest)
    source.unlink()
    try:
        source.symlink_to(header)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows symlink privilege or Developer Mode is unavailable")
        raise
    with pytest.raises(ValueError, match="regular file"):
        read_uno_sketch(str(source))


@pytest.mark.parametrize("directory", [False, True])
def test_uno_sketch_reports_missing_or_nonfile_path(tmp_path, directory):
    from cephvr.controller.microcontroller.firmware_source import read_uno_sketch

    source = tmp_path / "moved.ino"
    if directory:
        source.mkdir()
    with pytest.raises(
        ValueError, match="not a regular file" if directory else "not found"
    ) as error:
        read_uno_sketch(str(source))
    assert str(source) in str(error.value)


@pytest.mark.parametrize("limit", ["bytes", "entries"])
def test_uno_sketch_is_bounded_before_compilation(tmp_path, monkeypatch, limit):
    from cephvr.controller.microcontroller import firmware_source as source

    sketch = tmp_path / "main.ino"
    sketch.write_text("void setup() {}\nvoid loop() {}\n")
    monkeypatch.setattr(
        source, "MAX_SOURCE_BYTES" if limit == "bytes" else "MAX_SOURCE_ENTRIES", 1
    )
    if limit == "entries":
        (tmp_path / "helper.h").write_text("#define PIN 9")
    with pytest.raises(ValueError, match="exceeds"):
        source.read_uno_sketch(str(sketch))


def test_firmware_source_bounds_match_fixed_microcontroller_policy():
    from pathlib import Path

    from cephvr.controller.microcontroller.config import load_microcontroller_pair
    from cephvr.controller.microcontroller.firmware_source import (
        MAX_SOURCE_BYTES,
        MAX_SOURCE_ENTRIES,
    )

    pair = load_microcontroller_pair(Path(__file__).resolve().parents[2])
    assert (
        pair.policy["microcontroller"]["firmware_source_max_bytes"] == MAX_SOURCE_BYTES
    )
    assert (
        pair.policy["microcontroller"]["firmware_source_max_entries"]
        == MAX_SOURCE_ENTRIES
    )


@pytest.mark.parametrize(
    "source_kind,failure",
    [
        (kind, failure)
        for kind in ("hex", "ino")
        for failure in ("", "upload", "reconnect", "digest", "active")
    ]
    + [("ino", "compile")],
)
async def test_firmware_upload_hands_off_serial_without_resuming_outputs(
    tmp_path, source_kind, failure
) -> None:
    from cephvr.controller.microcontroller.device import MicrocontrollerDevice
    from cephvr.controller.microcontroller.firmware import read_uno_image
    from cephvr.controller.microcontroller.firmware_source import read_firmware
    from cephvr.shared.clock import host_time_ns

    events = []
    binary = tmp_path / "compiled.hex"
    binary.write_bytes(b":0400000001020304F2\n:00000001FF\n")
    image = read_uno_image(str(binary))
    path = tmp_path / f"firmware.{source_kind}"
    path.write_bytes(
        b"void setup() {}\nvoid loop() {}\n" if source_kind == "ino" else image.payload
    )
    selected = read_firmware(str(path))

    class Uploader:
        cleanup_complete = True

        def reset_cancel(self):
            pass

        def compile(self, sketch, operation, *, deadline_ns):
            events.append("compile")
            assert sketch == selected and operation.command_id == "child"
            assert deadline_ns > 0
            if failure == "compile":
                raise RuntimeError("compilation failed")
            return image

        def prepare(self, selected):
            assert selected.payload == image.payload
            events.append("prepare")
            self.cleanup_complete = False

        def upload(self, port, operation, *, deadline_ns):
            assert port == "COM8" and operation.command_id == "child"
            events.append("upload")
            if failure == "upload":
                raise RuntimeError("verification failed")

        def close(self, *, deadline_ns):
            events.append("cleanup")
            self.cleanup_complete = True

        def cancel(self):
            events.append("cancel")

    class Serial:
        async def close(self, *, deadline_ns):
            events.append("release serial")

        async def connect(self, *, deadline_ns):
            events.append("fresh connect")
            if failure == "reconnect":
                raise RuntimeError("protocol mismatch")

        async def diagnostic_stop(self, *, deadline_ns):
            raise RuntimeError("no pin diagnostic is active")

        async def status(self, *, deadline_ns):
            events.append("fresh status")
            result = mcu.MicrocontrollerObservation(connection_id="new")
            result.state.behavioral.running = False
            result.state.tracking.running = False
            return result

    settings = control.AcquisitionSettings()
    settings.pulses.port = "COM8"
    owner = MicrocontrollerDevice(
        Serial(),
        settings,
        runtime_pb2.AcquisitionFilePolicies(),
        host_time_ns,
        Uploader(),
    )
    owner.view.observation.connection_id = "old"
    owner.failure = "MCU firmware does not support CAPS"
    owner.view.diagnostic.active = failure == "active"
    request = wire.MicrocontrollerCommandRequest(
        kind=wire.MICROCONTROLLER_COMMAND_KIND_UPLOAD_FIRMWARE,
        firmware_path=str(path),
        firmware_sha256=selected.digest,
    )
    request.command.operator.command_id = "child"
    if failure == "digest":
        path.write_bytes(image.payload + b"\n")
    deadline = host_time_ns() + 2_000_000_000
    if failure:
        with pytest.raises((RuntimeError, ValueError)):
            await owner.execute(request, settings.pulses, deadline)
    else:
        await owner.execute(request, settings.pulses, deadline)
    assert not owner.busy
    if not failure:
        assert events == (["compile"] if source_kind == "ino" else []) + [
            "prepare",
            "release serial",
            "upload",
            "fresh connect",
            "fresh status",
            "cleanup",
        ]
        assert owner.view.observation.connection_id == "new"
        assert not owner.failure
    elif failure in {"digest", "active", "compile"}:
        assert "release serial" not in events and "upload" not in events
        assert owner.view.observation.connection_id == "old"
    else:
        assert not owner.view.HasField("observation")
        assert "fresh status" not in events
        if failure == "upload":
            assert "fresh connect" not in events


@pytest.mark.parametrize("role", ["behavioral", "tracking", "eye_tracking"])
@pytest.mark.parametrize("owned", ["device_open", "preview_running", "cleanup_pending"])
async def test_microcontroller_upload_requires_every_camera_released(role, owned):
    from unittest.mock import AsyncMock, Mock

    from cephvr.controller.device.microcontroller import MicrocontrollerCommands
    from cephvr.controller.device.ports import DeviceHooks
    from cephvr.controller.state import LimitsState
    from tests.controller.support_components import default_limits

    views = control.AcquisitionDeviceViews()
    setattr(getattr(views, role), owned, True)
    owner = MicrocontrollerDevice(
        AsyncMock(),
        control.AcquisitionSettings(),
        runtime_pb2.AcquisitionFilePolicies(),
        lambda: 1,
    )
    device = DeviceState()
    hooks = DeviceHooks(
        admission=Mock(),
        authorized=Mock(return_value=""),
        operation=Mock(),
        complete_operation=Mock(),
        prune_operations=Mock(),
        publish=Mock(),
        spawn=Mock(),
    )
    commands = MicrocontrollerCommands(
        lifecycle=LifecycleState(),
        configuration=ConfigurationState(
            control.ExperimentConfiguration(), control.ControlPolicies(), revision=7
        ),
        device=device,
        owner=owner,
        limits=LimitsState(default_limits()),
        clock=lambda: 1,
        hooks=hooks,
        device_views=lambda: views,
    )
    request = wire.MicrocontrollerCommandRequest(
        kind=wire.MICROCONTROLLER_COMMAND_KIND_UPLOAD_FIRMWARE,
        expected_configuration_revision=7,
        firmware_path="firmware.ino",
        firmware_sha256="a" * 64,
    )
    request.command.operator.command_id = "upload"
    await commands.execute(request)
    hooks.admission.assert_called_once_with(
        "upload",
        error="Stop capture and release cameras before Microcontroller diagnostics or Upload",
    )
    hooks.spawn.assert_not_called()
    assert device.camera_operation is None


@pytest.mark.parametrize("phase", ["upload", "compile"])
async def test_firmware_cancellation_waits_for_tool_and_preserves_serial_handoff(
    tmp_path,
    phase,
) -> None:
    import threading

    from cephvr.controller.microcontroller.firmware import read_uno_image
    from cephvr.controller.microcontroller.firmware_operation import FirmwareUpdate
    from cephvr.controller.microcontroller.firmware_source import read_firmware
    from cephvr.shared.clock import host_time_ns

    path = tmp_path / "firmware.hex"
    path.write_bytes(b":0400000001020304F2\n:00000001FF\n")
    image = read_uno_image(str(path))
    if phase == "compile":
        path = tmp_path / "firmware.ino"
        path.write_text("void setup() {}\nvoid loop() {}\n")
    events = []
    started = threading.Event()
    cancelled = threading.Event()

    class Uploader:
        cleanup_complete = True

        def reset_cancel(self):
            pass

        def prepare(self, image):
            self.cleanup_complete = False

        def compile(self, sketch, operation, *, deadline_ns):
            started.set()
            assert cancelled.wait(2)
            return image

        def upload(self, port, operation, *, deadline_ns):
            started.set()
            assert cancelled.wait(2)

        def cancel(self):
            cancelled.set()

        def close(self, *, deadline_ns):
            self.cleanup_complete = True

    class Serial:
        async def close(self, *, deadline_ns):
            events.append("closed")

        async def connect(self, *, deadline_ns):
            events.append("reconnected")

    owner = FirmwareUpdate(
        Uploader(), Serial(), control.MicrocontrollerDeviceView(), host_time_ns
    )
    request = wire.AcquisitionMicrocontrollerCommand(
        firmware_path=str(path), firmware_sha256=read_firmware(str(path)).digest
    )
    request.requested.port = "COM8"
    deadline = host_time_ns() + 3_000_000_000
    task = asyncio.create_task(
        owner.execute(
            request.firmware_path,
            request.firmware_sha256,
            "COM8",
            control.OperationContext(command_id="child"),
            deadline,
        )
    )
    assert await asyncio.to_thread(started.wait, 1)
    with pytest.raises(RuntimeError, match="pending"):
        owner.ensure_idle()
    await owner.close(deadline_ns=deadline)
    with pytest.raises(RuntimeError, match="cancelled"):
        await task
    assert "reconnected" not in events
    if phase == "compile":
        assert "closed" not in events
    assert not owner.busy


@pytest.mark.parametrize(
    "signal,kind,pin,frequency,configure_fails",
    [
        (
            control.MICROCONTROLLER_SIGNAL_KIND_TRIAL_STATE,
            "trial_state",
            "D9",
            None,
            False,
        ),
        (
            control.MICROCONTROLLER_SIGNAL_KIND_BEHAVIORAL,
            "behavioral",
            "D10",
            30.0,
            False,
        ),
        (control.MICROCONTROLLER_SIGNAL_KIND_TRACKING, "tracking", "D11", 60.0, False),
        (
            control.MICROCONTROLLER_SIGNAL_KIND_BEHAVIORAL,
            "behavioral",
            "D10",
            30.0,
            True,
        ),
    ],
)
async def test_manual_mcu_connect_then_start_uses_controller_selected_pin(
    signal: int, kind: str, pin: str, frequency: float | None, configure_fails: bool
) -> None:
    from cephvr.controller.microcontroller.device import MicrocontrollerDevice

    settings = control.AcquisitionSettings()
    settings.pulses.port = "COM8"
    settings.pulses.trial_state_pin = "D9"
    settings.pulses.trial_state_enabled = True
    if frequency is not None:
        output = getattr(settings.pulses, kind)
        output.pin = pin
        output.requested_frequency_hz = frequency
    calls: list[object] = []
    configured: set[str] = set()

    class Serial:
        async def connect(self, *, deadline_ns: int) -> mcu.MicrocontrollerObservation:
            calls.append(("connect", deadline_ns))
            return mcu.MicrocontrollerObservation(port="COM8")

        async def diagnostic_start(
            self, kind: str, pin: str, *, frequency_hz: float | None, deadline_ns: int
        ) -> tuple[bool, str, str, int]:
            if frequency_hz is not None and kind not in configured:
                raise RuntimeError(
                    "camera diagnostic requires applied output configuration"
                )
            calls.append((kind, pin, frequency_hz, deadline_ns))
            return True, kind, pin, 1

        async def configure(
            self,
            requested: camera.CameraPulseConfiguration,
            *,
            active_roles: tuple[int | str, ...],
            deadline_ns: int,
        ) -> mcu.MicrocontrollerObservation:
            calls.append(("configure", tuple(active_roles), deadline_ns))
            assert requested == settings.pulses
            assert active_roles == (kind,)
            if configure_fails:
                raise RuntimeError("MCU rejected CONFIGURE: UNSUPPORTED_FREQUENCY")
            configured.add(kind)
            return mcu.MicrocontrollerObservation(port="COM8", request_id="configured")

    owner = MicrocontrollerDevice(
        Serial(), settings, runtime_pb2.AcquisitionFilePolicies(), lambda: 100
    )
    connect = wire.MicrocontrollerCommandRequest(
        kind=wire.MICROCONTROLLER_COMMAND_KIND_CONNECT
    )
    start = wire.MicrocontrollerCommandRequest(
        kind=wire.MICROCONTROLLER_COMMAND_KIND_START, signal=signal
    )
    await owner.execute(connect, settings.pulses, 1000)
    if configure_fails:
        with pytest.raises(RuntimeError, match="UNSUPPORTED_FREQUENCY"):
            await owner.execute(start, settings.pulses, 1000)
        assert not any(isinstance(item, tuple) and item[0] == kind for item in calls)
        return
    await owner.execute(start, settings.pulses, 1000)
    assert ("connect", 1000) in calls
    assert (kind, pin, frequency, 1000) in calls
    assert owner.view.diagnostic.active and owner.view.diagnostic.rising_edges == 1
    assert owner.view.diagnostic.observed_monotonic_ns == 100
    if frequency is not None:
        assert calls.index(("configure", (kind,), 1000)) < calls.index(
            (kind, pin, frequency, 1000)
        )
        assert owner.view.observation.request_id == "configured"
    else:
        assert not configured


@pytest.mark.asyncio
@pytest.mark.parametrize("running", [False, True, None])
async def test_connection_only_keepalive_requires_proven_stopped_outputs(
    monkeypatch: pytest.MonkeyPatch, running: bool | None
) -> None:
    shutdown = asyncio.Event()
    observation = microcontroller_pb2.MicrocontrollerObservation(
        connection_id=str(uuid4()), observed_monotonic_ns=1
    )
    observation.state.configuration_valid = False
    observation.state.watchdog_ms = 0
    if running is not None:
        observation.state.behavioral.running = running
        observation.state.tracking.running = False
    failures = []
    waits = []

    async def wait(_shutdown: asyncio.Event, delay: int) -> None:
        waits.append(delay)
        shutdown.set()

    async def fail(failure) -> None:
        failures.append(failure.code)
        shutdown.set()

    monkeypatch.setattr("cephvr.controller.microcontroller.health._wait", wait)
    from cephvr.controller.microcontroller.health import MicrocontrollerHealth

    health = MicrocontrollerHealth(
        observation=lambda: observation,
        serial=cast(SerialOwnerPort, object()),
        serial_keepalive_interval_ns=10,
        serial_communication_timeout_ns=20,
        serial_ack_timeout_ns=1,
        serial_handoff_active=lambda: False,
        next_boundary=lambda now: None,
        failure_handler=fail,
        clock=lambda: 100,
    )

    await health._keepalive_loop(shutdown)

    assert failures == (
        [] if running is False else ["MICROCONTROLLER_KEEPALIVE_WINDOW_EXHAUSTED"]
    )
    assert bool(waits) is (running is False)


@pytest.mark.parametrize("handoff", [True, False])
async def test_keepalive_does_not_cross_firmware_serial_handoff(monkeypatch, handoff):
    shutdown = asyncio.Event()
    observation = microcontroller_pb2.MicrocontrollerObservation(
        connection_id=str(uuid4()), observed_monotonic_ns=1
    )
    observation.state.configuration_valid = True
    observation.state.watchdog_ms = 3000
    failures, waits = [], []

    async def wait(_shutdown, delay):
        waits.append(delay)
        shutdown.set()

    async def fail(failure):
        failures.append(failure.code)
        shutdown.set()

    monkeypatch.setattr("cephvr.controller.microcontroller.health._wait", wait)
    from cephvr.controller.microcontroller.health import MicrocontrollerHealth

    health = MicrocontrollerHealth(
        observation=lambda: observation,
        serial=cast(SerialOwnerPort, object()),
        serial_keepalive_interval_ns=10,
        serial_communication_timeout_ns=20,
        serial_ack_timeout_ns=1,
        serial_handoff_active=lambda: handoff,
        next_boundary=lambda now: None,
        failure_handler=fail,
        clock=lambda: 100,
    )

    await health._keepalive_loop(shutdown)
    assert bool(waits) == handoff
    assert failures == ([] if handoff else ["MICROCONTROLLER_KEEPALIVE_FAILED"])


async def test_unconfirmed_firmware_helper_blocks_camera_trigger_access() -> None:
    from unittest.mock import AsyncMock

    from cephvr.controller.microcontroller.device import MicrocontrollerDevice
    from cephvr.shared.clock import host_time_ns

    serial = AsyncMock()

    class Uploader:
        cleanup_complete = False

    owner = MicrocontrollerDevice(
        serial,
        control.AcquisitionSettings(),
        runtime_pb2.AcquisitionFilePolicies(),
        host_time_ns,
        Uploader(),
    )
    with pytest.raises(RuntimeError, match="cleanup"):
        await owner.io(
            wire.MicrocontrollerIoRequest(
                kind=wire.MICROCONTROLLER_IO_KIND_CONNECT,
                deadline_monotonic_ns=host_time_ns() + 100_000_000,
            )
        )
    serial.connect.assert_not_awaited()


async def test_camera_claim_is_exact_and_cleanup_leaves_general_diagnostics_alone():
    from unittest.mock import AsyncMock

    from cephvr.controller.microcontroller.device import MicrocontrollerDevice

    serial = AsyncMock()
    serial.connect.return_value = mcu.MicrocontrollerObservation(port="COM8")
    settings = control.AcquisitionSettings()
    settings.pulses.port = "COM8"
    owner = MicrocontrollerDevice(
        serial, settings, runtime_pb2.AcquisitionFilePolicies(), lambda: 1
    )
    owner.view.diagnostic.active = True
    # A coordinator without a claim cannot close this general-purpose pin test.
    await owner.io(
        wire.MicrocontrollerIoRequest(kind=wire.MICROCONTROLLER_IO_KIND_CLOSE)
    )
    serial.close.assert_not_awaited()
    assert owner.view.diagnostic.active
    with pytest.raises(RuntimeError, match="pin test"):
        await owner.io(
            wire.MicrocontrollerIoRequest(
                kind=wire.MICROCONTROLLER_IO_KIND_CONNECT, deadline_monotonic_ns=1000
            )
        )
    owner.view.diagnostic.active = False
    first = str(uuid4())
    await owner.io(
        wire.MicrocontrollerIoRequest(
            command_id=first,
            claim_id=first,
            kind=wire.MICROCONTROLLER_IO_KIND_CONNECT,
            requested=settings.pulses,
            deadline_monotonic_ns=1000,
        )
    )
    with pytest.raises(RuntimeError, match="claim"):
        await owner.io(
            wire.MicrocontrollerIoRequest(
                kind=wire.MICROCONTROLLER_IO_KIND_STATUS,
                claim_id=str(uuid4()),
                deadline_monotonic_ns=1000,
            )
        )
    with pytest.raises(RuntimeError, match="Release camera"):
        await owner.execute(
            wire.MicrocontrollerCommandRequest(
                kind=wire.MICROCONTROLLER_COMMAND_KIND_CONNECT
            ),
            settings.pulses,
            1000,
        )
    await owner.io(
        wire.MicrocontrollerIoRequest(
            kind=wire.MICROCONTROLLER_IO_KIND_CLOSE,
            claim_id=first,
            deadline_monotonic_ns=1000,
        )
    )
    second = str(uuid4())
    await owner.io(
        wire.MicrocontrollerIoRequest(
            command_id=second,
            claim_id=second,
            kind=wire.MICROCONTROLLER_IO_KIND_CONNECT,
            requested=settings.pulses,
            deadline_monotonic_ns=1000,
        )
    )
    with pytest.raises(RuntimeError, match="claim"):
        await owner.io(
            wire.MicrocontrollerIoRequest(
                kind=wire.MICROCONTROLLER_IO_KIND_CLOSE,
                claim_id=first,
                deadline_monotonic_ns=1000,
            )
        )
    assert owner.claim_id == second and owner.acquisition_claimed
    assert serial.close.await_count == 1


@pytest.mark.parametrize("diagnostic_active", [False, True])
async def test_failed_controller_close_stays_fenced_until_exact_release(
    diagnostic_active,
):
    from unittest.mock import AsyncMock

    from cephvr.controller.microcontroller.device import MicrocontrollerDevice
    from cephvr.shared.clock import host_time_ns

    serial = AsyncMock()
    serial.close.side_effect = RuntimeError("serial release unconfirmed")
    owner = MicrocontrollerDevice(
        serial,
        control.AcquisitionSettings(),
        runtime_pb2.AcquisitionFilePolicies(),
        host_time_ns,
    )
    owner.port_owned = True
    owner.view.observation.port = "COM8"
    owner.view.diagnostic.active = diagnostic_active
    if diagnostic_active:
        serial.diagnostic_stop.return_value = (False, "trial_state", "D9", 1)
    else:
        serial.diagnostic_stop.side_effect = RuntimeError("no pin diagnostic is active")
    stopped = mcu.MicrocontrollerState()
    stopped.behavioral.running = False
    stopped.tracking.running = False
    serial.off.return_value = mcu.PulseCommandEvidence(
        outcome=mcu.PULSE_COMMAND_OUTCOME_APPLIED, resulting_state=stopped
    )
    deadline = host_time_ns() + 1_000_000_000
    with pytest.raises(RuntimeError, match="unconfirmed"):
        await owner.close(deadline_ns=deadline, permanent=False)
    assert owner.snapshot_view().cleanup_pending and not owner.cleanup_complete
    with pytest.raises(RuntimeError, match="pending"):
        owner.ensure_idle()
    serial.close.side_effect = None
    await owner.close(deadline_ns=deadline, permanent=False)
    assert serial.off.await_count == 1
    assert serial.diagnostic_stop.await_count == int(diagnostic_active)
    assert owner.cleanup_complete and not owner.snapshot_view().cleanup_pending
    assert [call.kwargs["deadline_ns"] for call in serial.close.await_args_list] == [
        deadline,
        deadline,
    ]
    owner.ensure_idle()


async def test_uncertain_diagnostic_start_remains_fenced_for_cleanup():
    from unittest.mock import AsyncMock

    from cephvr.controller.microcontroller.device import MicrocontrollerDevice
    from cephvr.shared.clock import host_time_ns

    serial = AsyncMock()
    serial.diagnostic_start.side_effect = RuntimeError(
        "start acknowledgement unconfirmed"
    )
    serial.diagnostic_stop.side_effect = RuntimeError("no pin diagnostic is active")
    owner = MicrocontrollerDevice(
        serial,
        control.AcquisitionSettings(),
        runtime_pb2.AcquisitionFilePolicies(),
        host_time_ns,
    )
    owner.port_owned = True
    owner.view.observation.port = "COM8"
    pulses = camera.CameraPulseConfiguration(
        port="COM8", trial_state_pin="D9", trial_state_enabled=True
    )
    request = wire.MicrocontrollerCommandRequest(
        kind=wire.MICROCONTROLLER_COMMAND_KIND_START,
        signal=control.MICROCONTROLLER_SIGNAL_KIND_TRIAL_STATE,
    )
    deadline = host_time_ns() + 1_000_000_000
    with pytest.raises(RuntimeError, match="unconfirmed"):
        await owner.execute(request, pulses, deadline)
    with pytest.raises(RuntimeError, match="pending"):
        owner.ensure_idle()
    with pytest.raises(RuntimeError, match="no pin diagnostic"):
        await owner.close(deadline_ns=deadline, permanent=False)
    assert not owner.cleanup_complete and owner.snapshot_view().cleanup_pending
    serial.close.assert_not_awaited()
    serial.off.assert_not_awaited()


async def test_cancel_on_retains_off_boundary_for_watchdog_arbitration():
    from unittest.mock import AsyncMock

    from cephvr.controller.microcontroller.device import MicrocontrollerDevice

    owner = MicrocontrollerDevice(
        AsyncMock(),
        control.AcquisitionSettings(),
        runtime_pb2.AcquisitionFilePolicies(),
        lambda: 1,
    )
    owner.acquisition_claimed = True
    owner.claim_id = "claim"
    owner.boundaries = {
        10: mcu.PULSE_BOUNDARY_COMMAND_ON,
        20: mcu.PULSE_BOUNDARY_COMMAND_OFF,
    }
    await owner.io(
        wire.MicrocontrollerIoRequest(
            kind=wire.MICROCONTROLLER_IO_KIND_CANCEL_ON,
            claim_id="claim",
            deadline_monotonic_ns=1000,
        )
    )
    assert owner.next_boundary(1) == 20


async def test_microcontroller_replay_joins_one_executor_and_retains_original_budget():
    from cephvr.controller.microcontroller.admission import MicrocontrollerIoAdmission
    from cephvr.shared.commands import CommandLedger

    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    clock = [1]

    async def operation(request):
        calls.append(request.deadline_monotonic_ns)
        entered.set()
        await release.wait()
        return wire.MicrocontrollerIoResult(
            command_id=request.command_id, succeeded=True
        )

    admission = MicrocontrollerIoAdmission(
        CommandLedger(
            str(uuid4()),
            300_000_000_000,
            max_records=32,
            max_bytes=2 * 1024 * 1024,
            result_reservation_bytes=65536,
        ),
        lambda: clock[0],
        operation,
    )
    request = wire.MicrocontrollerIoRequest(
        command_id=str(uuid4()),
        deadline_monotonic_ns=100,
        kind=wire.MICROCONTROLLER_IO_KIND_CLOSE,
    )
    first = asyncio.create_task(admission.execute(request))
    await entered.wait()
    duplicate = asyncio.create_task(admission.execute(request))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    result = await duplicate
    assert result.succeeded and calls == [100]
    assert await admission.execute(request) == result
    changed = wire.MicrocontrollerIoRequest.FromString(request.SerializeToString())
    changed.deadline_monotonic_ns = 200
    assert not (await admission.execute(changed)).succeeded
    expired = wire.MicrocontrollerIoRequest(
        command_id=str(uuid4()), deadline_monotonic_ns=1
    )
    assert not (await admission.execute(expired)).succeeded
    assert calls == [100]
    await admission.close()


def test_serial_policy_reload_requires_an_idle_released_owner():
    from unittest.mock import AsyncMock

    from cephvr.controller.microcontroller.device import MicrocontrollerDevice

    policies = runtime_pb2.AcquisitionFilePolicies(serial_ack_timeout_ns=100)
    latest = runtime_pb2.AcquisitionFilePolicies(serial_ack_timeout_ns=200)
    owner = MicrocontrollerDevice(
        AsyncMock(),
        control.AcquisitionSettings(),
        policies,
        lambda: 1,
        policy_loader=lambda: latest,
    )
    owner.port_owned = True
    with pytest.raises(RuntimeError, match="Release"):
        owner.reload_idle_policy()
    assert policies.serial_ack_timeout_ns == 100
    owner.port_owned = False
    owner.reload_idle_policy()
    assert policies.serial_ack_timeout_ns == 200


@pytest.mark.parametrize(
    "reply", ["confirmed_false", "missing_evidence", "wrong_command", "expired"]
)
async def test_camera_client_cancellation_retains_deadline_and_requires_typed_reply(
    reply,
):
    from cephvr.acquisition.microcontroller_client import (
        ControllerMicrocontrollerClient,
    )
    from cephvr.shared.auth import Principal
    from cephvr.shared.transport_deadlines import deadline_metadata

    calls = []

    class Stub:
        async def ExecuteMicrocontrollerIo(self, request, **kwargs):
            calls.append((request, kwargs))
            result = wire.MicrocontrollerIoResult(
                command_id=request.command_id, succeeded=True
            )
            if reply != "missing_evidence":
                result.cancelled = False
            if reply == "wrong_command":
                result.command_id = str(uuid4())
            return result

    principal = Principal("acquisition", str(uuid4()), "token")
    client = ControllerMicrocontrollerClient(
        Stub(),
        principal,
        str(uuid4()),
        lambda: camera.CameraPulseConfiguration(),
        clock=lambda: 1000 if reply == "expired" else 10,
    )
    client.claim_id = str(uuid4())
    if reply == "confirmed_false":
        assert not await client.cancel_active_request(deadline_ns=1000)
    else:
        message = {
            "missing_evidence": "typed evidence",
            "wrong_command": "different command",
            "expired": "expired",
        }[reply]
        with pytest.raises((RuntimeError, TimeoutError), match=message):
            await client.cancel_active_request(deadline_ns=1000)
    if reply == "expired":
        assert not calls
    else:
        request, kwargs = calls[0]
        assert len(calls) == 1 and request.claim_id == client.claim_id
        assert request.deadline_monotonic_ns == 1000
        assert kwargs == {
            "metadata": (*principal.metadata(), deadline_metadata(1000)),
            "timeout": 990 / 1e9,
        }


def test_camera_client_allows_empty_roles_only_for_configuration() -> None:
    from cephvr.acquisition.microcontroller_client import (
        ControllerMicrocontrollerClient,
    )
    from cephvr.shared.auth import Principal

    async def scenario() -> None:
        calls = []
        acquisition_generation = str(uuid4())

        class Stub:
            async def ExecuteMicrocontrollerIo(self, request, **kwargs):
                calls.append(request)
                result = wire.MicrocontrollerIoResult(
                    command_id=request.command_id, succeeded=True
                )
                if request.kind == wire.MICROCONTROLLER_IO_KIND_CONFIGURE:
                    result.observation.port = "COM8"
                else:
                    result.evidence.outcome = mcu.PULSE_COMMAND_OUTCOME_APPLIED
                return result

        client = ControllerMicrocontrollerClient(
            Stub(),
            Principal("acquisition", acquisition_generation, "token"),
            "controller-gen",
            lambda: camera.CameraPulseConfiguration(port="COM8"),
            clock=lambda: 10,
        )
        client.claim_id = "claim"
        requested = camera.CameraPulseConfiguration(port="COM8")
        scope = control.OperationContext(command_id="edit-op")
        await client.configure(
            requested,
            active_roles=(),
            deadline_ns=100,
            resolution_operation=scope,
            requested_configuration_revision=7,
        )
        assert calls[0].roles == []
        with pytest.raises(ValueError, match="distinct supported"):
            await client.on((), scheduled_boundary_ns=None, deadline_ns=100)
        assert len(calls) == 1

    asyncio.run(scenario())
