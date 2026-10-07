from __future__ import annotations

from collections import deque
from collections.abc import Callable

import pytest

from cephvr.acquisition.v1 import microcontroller_pb2
from cephvr.controller.microcontroller.channel import (
    ChannelCancelled,
    ChannelTimeout,
    ChannelTransportFailure,
    Exchange,
    SerialChannel,
)
from cephvr.controller.microcontroller.protocol import (
    ProtocolError,
    parse_capabilities,
    parse_diagnostic,
    parse_reply,
)
from cephvr.controller.microcontroller.pulses import PulseExecutor


def test_v3_reply_accepts_multiple_spaces_and_caps_pin_list() -> None:
    reply = parse_reply(
        b"OK   id=run-1   protocol=3 firmware=board pins=D2,D3 input_pins=D2,D3 min_hz=0.1 "
        b"max_hz=60.0 watchdog_min_ms=100 watchdog_max_ms=10000\n"
    )

    (
        version,
        firmware,
        pins,
        input_pins,
        minimum,
        maximum,
        watchdog_min,
        watchdog_max,
    ) = parse_capabilities(reply)
    assert (version, firmware, pins) == (3, "board", ("D2", "D3"))
    assert input_pins == ("D2", "D3")
    assert minimum == 0.1
    assert maximum == 60.0
    assert (watchdog_min, watchdog_max) == (100, 10000)


def test_caps_rejects_input_pin_outside_advertised_pins() -> None:
    reply = parse_reply(
        b"OK id=run-1 protocol=3 firmware=board pins=D2,D3 input_pins=D4 "
        b"min_hz=0.1 max_hz=60.0 watchdog_min_ms=100 watchdog_max_ms=10000\n"
    )
    with pytest.raises(ProtocolError, match="input_pins"):
        parse_capabilities(reply)


def test_diagnostic_reply_requires_exact_kind_pin_and_edge_shape() -> None:
    assert parse_diagnostic(
        parse_reply(b"OK id=run-2 active=1 kind=projector_flip pin=D2 edges=3\n")
    ) == (True, "projector_flip", "D2", 3)
    assert parse_diagnostic(
        parse_reply(b"OK id=run-3 active=0 kind=trial_state pin=D9 edges=1\n")
    ) == (False, "trial_state", "D9", 1)
    with pytest.raises(ProtocolError, match="initial HIGH"):
        parse_diagnostic(
            parse_reply(b"OK id=run-4 active=0 kind=trial_state pin=D9 edges=0\n")
        )
    with pytest.raises(ProtocolError, match="single HIGH"):
        parse_diagnostic(
            parse_reply(b"OK id=run-5 active=0 kind=trial_state pin=D9 edges=2\n")
        )


@pytest.mark.parametrize("kind", ["behavioral", "tracking"])
@pytest.mark.parametrize("active,edges", [(1, 1), (1, 17), (0, 59), (0, 2**32 - 1)])
def test_camera_diagnostic_preserves_generated_count(
    kind: str, active: int, edges: int
) -> None:
    reply = parse_reply(
        f"OK id=run-6 active={active} kind={kind} pin=D10 edges={edges}\n".encode()
    )
    assert parse_diagnostic(reply) == (bool(active), kind, "D10", edges)


@pytest.mark.parametrize("edges", ["0", "-1", "4294967296", "1.5"])
def test_camera_diagnostic_rejects_invalid_generated_counts(edges: str) -> None:
    with pytest.raises(ProtocolError):
        parse_diagnostic(
            parse_reply(
                f"OK id=run-7 active=0 kind=behavioral pin=D10 edges={edges}\n".encode()
            )
        )


def test_channel_ignores_stale_ids_and_drains_fragmented_bounded_replies() -> None:
    clock = _StepClock()
    port = _FakePort()

    def write(payload: bytes) -> int:
        request_id = payload.decode("ascii").split("id=", 1)[1].split()[0]
        port.feed(b"x" * 520 + b"\n")
        port.feed(
            b"OK id=stale watchdog_stopped=0 behavioral_running=0 tracking_running=0\n"
        )
        port.feed(
            f"OK id={request_id} watchdog_stopped=0 behavioral_running=0 tracking_running=0\n".encode()
        )
        return len(payload)

    port.on_write = write
    channel = SerialChannel("fake", 115200, 10_000, clock=clock, serial_port=port)
    channel.open(10000)

    result = channel.request("PING", {}, 10000)

    assert result.reply is not None
    assert result.reply.request_id == result.request_id
    assert channel.unmatched_replies == 1
    assert channel.malformed_replies == 1


def test_dispatched_request_without_ack_is_timed_out_with_dispatch_evidence() -> None:
    clock = _StepClock()
    port = _FakePort()
    port.on_write = lambda payload: len(payload)
    channel = SerialChannel("fake", 115200, 30, clock=clock, serial_port=port)
    channel.open(1000)

    with pytest.raises(ChannelTimeout):
        channel.request(
            "ON", {"behavioral_selected": "1", "tracking_selected": "0"}, 1000
        )

    assert channel.last_exchange is not None
    assert channel.last_exchange.dispatched_ns > 0
    assert channel.last_exchange.completed_ns is None


def test_partial_write_fails_after_dispatch_without_acknowledgement() -> None:
    clock = _StepClock()
    port = _FakePort()
    port.on_write = lambda payload: len(payload) - 1
    channel = SerialChannel("fake", 115200, 1000, clock=clock, serial_port=port)
    channel.open(10000)

    with pytest.raises(ChannelTransportFailure):
        channel.request(
            "ON", {"behavioral_selected": "1", "tracking_selected": "0"}, 10000
        )

    assert channel.last_exchange is not None
    assert channel.last_exchange.completed_ns is None


def test_cancellation_waits_for_blocked_call_return_and_is_not_off_evidence() -> None:
    clock = _StepClock()
    port = _FakePort()
    channel = SerialChannel("fake", 115200, 1000, clock=clock, serial_port=port)
    port.cancel_callback = channel.cancel_request
    channel.open(10000)

    with pytest.raises(ChannelCancelled):
        channel.request(
            "ON", {"behavioral_selected": "1", "tracking_selected": "0"}, 10000
        )

    assert channel.wait_for_request_completion(0)
    assert channel.last_exchange is not None
    assert channel.last_exchange.completed_ns is None


def test_malformed_matched_ack_has_no_ack_timestamp_or_fabricated_state() -> None:
    evidence, resulting = _pulse_evidence(
        b"OK id={request_id} watchdog_stopped=0\n",
        verb="ON",
        command=microcontroller_pb2.PULSE_BOUNDARY_COMMAND_ON,
    )

    assert (
        evidence.outcome == microcontroller_pb2.PULSE_COMMAND_OUTCOME_TRANSPORT_FAILED
    )
    assert evidence.HasField("dispatched_monotonic_ns")
    assert not evidence.HasField("acknowledged_monotonic_ns")
    assert not evidence.HasField("resulting_state")
    assert resulting is None


def test_watchdog_stopped_off_retains_stop_state_and_matched_ack() -> None:
    evidence, resulting = _pulse_evidence(
        b"OK id={request_id} watchdog_stopped=1 behavioral_running=0 tracking_running=0\n",
        verb="OFF",
        command=microcontroller_pb2.PULSE_BOUNDARY_COMMAND_OFF,
    )

    assert evidence.outcome == microcontroller_pb2.PULSE_COMMAND_OUTCOME_APPLIED
    assert evidence.applied is True
    assert evidence.error_code == "WATCHDOG_STOPPED"
    assert evidence.HasField("acknowledged_monotonic_ns")
    assert resulting is not None
    assert resulting.watchdog_stopped is True
    assert resulting.behavioral.running is False


def _pulse_evidence(
    response: bytes,
    *,
    verb: str,
    command: microcontroller_pb2.PulseBoundaryCommand,
) -> tuple[
    microcontroller_pb2.PulseCommandEvidence,
    microcontroller_pb2.MicrocontrollerState | None,
]:
    clock = _StepClock()
    port = _FakePort()
    port.on_write = lambda payload: _write_reply(port, payload, response)
    channel = SerialChannel("fake", 115200, 1000, clock=clock, serial_port=port)
    channel.open(10000)
    executor = PulseExecutor(channel, 1000, clock=clock)

    def exchange_command(
        command_text: str,
        fields: dict[str, str],
        deadline_ns: int,
        *,
        routine: bool,
        dispatch_before_ns: int | None,
    ) -> Exchange:
        del routine
        return channel.request(
            command_text,
            fields,
            deadline_ns,
            dispatch_before_ns=dispatch_before_ns,
        )

    return executor.execute(
        verb,
        command,
        ("behavioral",),
        10000,
        connection_id=channel.connection_id or "",
        boundary_ns=None,
        stop_issued_ns=None,
        current_state=None,
        require_connected=lambda: None,
        exchange_command=exchange_command,
    )


def _write_reply(port: _FakePort, payload: bytes, response: bytes) -> int:
    request_id = payload.decode("ascii").split("id=", 1)[1].split()[0]
    port.feed(response.replace(b"{request_id}", request_id.encode("ascii")))
    return len(payload)


class _StepClock:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> int:
        self.value += 1
        return self.value


class _FakePort:
    def __init__(self) -> None:
        self.incoming: deque[int] = deque()
        self.on_write: Callable[[bytes], int] = lambda payload: len(payload)
        self.cancel_callback: Callable[[], bool] | None = None
        self.cancelled_read = False
        self.cancelled_write = False

    def set_timeouts(self, *, read_seconds: float, write_seconds: float) -> None:
        del read_seconds, write_seconds

    def write(self, payload: bytes) -> int:
        return self.on_write(payload)

    def read(self, size: int = 1) -> bytes:
        if self.cancel_callback is not None:
            callback = self.cancel_callback
            self.cancel_callback = None
            callback()
        return bytes(
            self.incoming.popleft() for _ in range(min(size, len(self.incoming)))
        )

    def feed(self, payload: bytes) -> None:
        self.incoming.extend(payload)

    def cancel_read(self) -> None:
        self.cancelled_read = True

    def cancel_write(self) -> None:
        self.cancelled_write = True

    def close(self) -> None:
        pass
