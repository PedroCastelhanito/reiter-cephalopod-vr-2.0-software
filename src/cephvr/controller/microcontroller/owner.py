"""Single-threaded typed owner for the bounded A11 serial protocol."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from typing import cast

from cephvr.acquisition.v1 import camera_pb2, microcontroller_pb2, runtime_pb2
from cephvr.shared.clock import host_time_ns

from .channel import (
    ChannelDeadline,
    Exchange,
    SerialChannel,
)
from .protocol import (
    PROTOCOL_VERSION,
    ROLES,
    frequency_text,
    parse_capabilities,
    parse_compact_state,
    parse_diagnostic,
    parse_state,
)
from .pulses import BoundaryReservation, PulseExecutor, normalize_roles
from .serial_port import SerialPort


class SerialOwnerError(RuntimeError):
    """Startup, protocol or readback evidence cannot satisfy the operation."""


class SerialOwner:
    """Own one configured port on exactly one dedicated serial-owner thread."""

    def __init__(
        self,
        port: str,
        policies: runtime_pb2.AcquisitionFilePolicies,
        *,
        clock: Callable[[], int] = host_time_ns,
        serial_port: SerialPort | None = None,
    ) -> None:
        if not port or any(ch.isspace() for ch in port):
            raise ValueError("configured microcontroller port must be a nonempty token")
        self.port_name = port
        self._clock = clock
        self._baud_rate = _required_positive(policies, "serial_baud_rate")
        self._ack_ns = _required_positive(policies, "serial_ack_timeout_ns")
        self._keepalive_ns = _required_positive(
            policies, "serial_keepalive_interval_ns"
        )
        self._communication_ns = _required_positive(
            policies, "serial_communication_timeout_ns"
        )
        self.stop_completion_margin_ns = _required_positive(
            policies, "serial_stop_completion_margin_ns"
        )
        if self._keepalive_ns >= self._communication_ns:
            raise ValueError(
                "keepalive interval must be shorter than communication timeout"
            )
        self._watchdog_ms = _exact_milliseconds(self._communication_ns)
        self._channel = SerialChannel(
            port,
            self._baud_rate,
            self._ack_ns,
            clock=clock,
            serial_port=serial_port,
        )
        self._pulses = PulseExecutor(self._channel, self._ack_ns, clock=clock)
        self._thread_id: int | None = None
        self._connected = False
        self._closed = False
        self._capabilities: microcontroller_pb2.MicrocontrollerCapabilities | None = (
            None
        )
        self._capabilities_time_ns: int | None = None
        self._state: microcontroller_pb2.MicrocontrollerState | None = None
        self._diagnostic: tuple[str, str] | None = None

    @property
    def connection_id(self) -> str:
        return self._channel.connection_id or ""

    @property
    def unmatched_replies(self) -> int:
        return self._channel.unmatched_replies

    @property
    def malformed_replies(self) -> int:
        return self._channel.malformed_replies

    def cancel_active_request(self) -> bool:
        """Request cancellation; the eventual request evidence still controls state."""
        return self._channel.cancel_request()

    def wait_for_active_request(self, timeout_seconds: float) -> bool:
        """Wait for owner-thread I/O to return after a cancellation request."""
        return self._channel.wait_for_request_completion(timeout_seconds)

    @property
    def next_keepalive_deadline_ns(self) -> int | None:
        last = self._channel.last_valid_reply_ns
        if not self._connected or last is None:
            return None
        return last + self._keepalive_ns

    def connect(
        self, deadline_ns: int
    ) -> microcontroller_pb2.MicrocontrollerObservation:
        """Verify protocol, fresh capabilities, status and stopped outputs."""
        self._assert_owner_thread()
        if self._closed or self._connected:
            raise SerialOwnerError("serial owner is closed or already connected")
        try:
            self._channel.open(deadline_ns)
            caps_exchange = self._channel.probe("CAPS", deadline_ns)
            if caps_exchange.reply is None:
                raise SerialOwnerError(
                    "CAPS startup probe did not return a matched reply"
                )
            version, firmware, pins, input_pins, minimum, maximum, wd_min, wd_max = (
                parse_capabilities(caps_exchange.reply)
            )
            if version != PROTOCOL_VERSION:
                raise SerialOwnerError(
                    f"incompatible MCU protocol version {version}; required {PROTOCOL_VERSION}"
                )
            self._capabilities = microcontroller_pb2.MicrocontrollerCapabilities(
                protocol_version=version,
                firmware=firmware,
                pins=pins,
                rising_edge_input_pins=input_pins,
                minimum_requested_hz=minimum,
                maximum_requested_hz=maximum,
                minimum_watchdog_ms=wd_min,
                maximum_watchdog_ms=wd_max,
            )
            self._capabilities_time_ns = caps_exchange.completed_ns
            if not wd_min <= self._watchdog_ms <= wd_max:
                raise SerialOwnerError(
                    "communication timeout is outside MCU watchdog limits"
                )

            status_exchange = self._channel.probe("STATUS", deadline_ns)
            if status_exchange.reply is None:
                raise SerialOwnerError(
                    "STATUS startup probe did not return a matched reply"
                )
            state = _state_from_values(
                parse_state(status_exchange.reply, configured=False)
            )
            running = [role for role in ROLES if getattr(state, role).running]
            if running:
                fields = {
                    "behavioral_selected": "1" if "behavioral" in running else "0",
                    "tracking_selected": "1" if "tracking" in running else "0",
                }
                self._channel.request("OFF", fields, deadline_ns)
                status_exchange = self._channel.probe("STATUS", deadline_ns)
                if status_exchange.reply is None:
                    raise SerialOwnerError("post-OFF STATUS has no matched reply")
                state = _state_from_values(
                    parse_state(status_exchange.reply, configured=False)
                )
            if any(getattr(state, role).running for role in ROLES):
                raise SerialOwnerError(
                    "startup verification found a running pulse output"
                )
            self._state = state
            self._connected = True
            return self._observation(
                status_exchange.request_id,
                state,
                observed_ns=status_exchange.completed_ns or self._clock(),
            )
        except Exception as exc:
            try:
                self._close_after_startup_failure(deadline_ns)
            except SerialOwnerError as cleanup_error:
                raise SerialOwnerError(
                    f"MCU startup failed: {exc}; cleanup: {cleanup_error}"
                ) from exc
            raise

    def configure(
        self,
        requested: camera_pb2.CameraPulseConfiguration,
        deadline_ns: int,
        *,
        active_roles: Iterable[int | str],
    ) -> microcontroller_pb2.MicrocontrollerObservation:
        """Apply both output roles from complete settings plus an explicit active mask."""
        self._require_connected()
        active = normalize_roles(active_roles)
        if requested.HasField("port") and requested.port != self.port_name:
            raise ValueError(
                "pulse configuration port differs from the serialized owner port"
            )
        fields = {"watchdog_ms": str(self._watchdog_ms)}
        caps = self._require_capabilities()
        for role in ROLES:
            enabled = role in active
            fields[f"{role}_enabled"] = "1" if enabled else "0"
            if not enabled:
                continue
            if not requested.HasField(role):
                raise ValueError(f"active {role} role has no requested pulse settings")
            value = getattr(requested, role)
            if not value.HasField("pin") or not value.pin:
                raise ValueError(
                    f"active {role} role requires an explicit firmware pin"
                )
            if not value.HasField("requested_frequency_hz"):
                raise ValueError(
                    f"active {role} role requires an explicit requested frequency"
                )
            pin = _safe_token(value.pin, f"{role} pin")
            if pin not in caps.pins:
                raise ValueError(
                    f"firmware did not advertise configured {role} pin {pin!r}"
                )
            rate = value.requested_frequency_hz
            fields[f"{role}_hz"] = frequency_text(rate)
            if not caps.minimum_requested_hz <= rate <= caps.maximum_requested_hz:
                raise ValueError(
                    f"requested {role} frequency is outside current CAPS range"
                )
            fields[f"{role}_pin"] = pin
        exchange = self._exchange("CONFIGURE", fields, deadline_ns, routine=True)
        assert exchange.reply is not None
        state = _state_from_values(parse_state(exchange.reply, configured=True))
        if not state.HasField("configuration_valid") or not state.configuration_valid:
            raise SerialOwnerError("CONFIGURE readback is not configuration-valid")
        if not state.HasField("watchdog_ms") or state.watchdog_ms != self._watchdog_ms:
            raise SerialOwnerError("CONFIGURE watchdog readback differs from request")
        if state.watchdog_stopped:
            raise SerialOwnerError("successful CONFIGURE left MCU watchdog stopped")
        for role in ROLES:
            output = getattr(state, role)
            if output.running:
                raise SerialOwnerError(f"CONFIGURE unexpectedly resumed {role} output")
            if output.enabled != (role in active):
                raise SerialOwnerError(
                    f"CONFIGURE readback enablement differs for {role}"
                )
            if role in active and output.pin != getattr(requested, role).pin:
                raise SerialOwnerError(f"CONFIGURE readback pin differs for {role}")
        self._state = state
        return self._observation(
            exchange.request_id,
            state,
            observed_ns=exchange.completed_ns or self._clock(),
        )

    def status(
        self, deadline_ns: int
    ) -> microcontroller_pb2.MicrocontrollerObservation:
        """Refresh complete status; STATUS cannot clear a watchdog stop."""
        self._require_connected()
        exchange = self._exchange("STATUS", {}, deadline_ns, routine=True)
        assert exchange.reply is not None
        state = _state_from_values(parse_state(exchange.reply, configured=False))
        self._state = state
        return self._observation(
            exchange.request_id,
            state,
            observed_ns=exchange.completed_ns or self._clock(),
        )

    def keepalive(self, deadline_ns: int) -> microcontroller_pb2.MicrocontrollerState:
        """PING updates compact running evidence, never full status or CAPS time."""
        self._require_connected()
        exchange = self._exchange("PING", {}, deadline_ns, routine=True)
        assert exchange.reply is not None and self._state is not None
        compact = parse_compact_state(exchange.reply)
        state = microcontroller_pb2.MicrocontrollerState()
        state.CopyFrom(self._state)
        state.watchdog_stopped = compact["watchdog_stopped"]
        for role in ROLES:
            getattr(state, role).running = compact[f"{role}_running"]
        if state.watchdog_stopped and any(
            getattr(state, role).running for role in ROLES
        ):
            raise SerialOwnerError("PING state conflicts with watchdog stop")
        self._state = state
        return state

    def diagnostic_start(
        self,
        kind: str,
        pin: str,
        deadline_ns: int,
        *,
        frequency_hz: float | None = None,
    ) -> tuple[bool, str, str, int]:
        """Start one firmware-bounded diagnostic on an otherwise stopped MCU."""
        self._require_connected()
        if self._diagnostic is not None:
            raise SerialOwnerError("another pin diagnostic is active")
        if kind not in {"trial_state", "projector_flip", *ROLES}:
            raise ValueError("unknown pin diagnostic kind")
        if pin not in self._require_capabilities().pins:
            raise ValueError("pin is absent from current firmware capabilities")
        if (
            kind == "projector_flip"
            and pin not in self._require_capabilities().rising_edge_input_pins
        ):
            raise ValueError("pin does not support rising-edge input capture")
        assert self._state is not None
        if any(getattr(self._state, role).running for role in ROLES):
            raise SerialOwnerError("pin diagnostics require stopped camera outputs")
        fields = {"kind": kind, "pin": pin, "duration_ms": "2000"}
        if kind in ROLES:
            if frequency_hz is None:
                raise ValueError("camera pin diagnostic requires its requested rate")
            fields["hz"] = frequency_text(frequency_hz)
        elif frequency_hz is not None:
            raise ValueError("fixed I/O diagnostic does not accept a camera rate")
        exchange = self._exchange("DIAG_START", fields, deadline_ns, routine=True)
        if exchange.reply is None:
            raise SerialOwnerError("diagnostic start has no matched reply")
        result = parse_diagnostic(exchange.reply)
        if result[:3] != (True, kind, pin):
            raise SerialOwnerError("diagnostic start reply differs from request")
        self._diagnostic = (kind, pin)
        return result

    def diagnostic_status(self, deadline_ns: int) -> tuple[bool, str, str, int]:
        self._require_connected()
        if self._diagnostic is None:
            raise SerialOwnerError("no pin diagnostic is active")
        exchange = self._exchange("DIAG_STATUS", {}, deadline_ns, routine=True)
        if exchange.reply is None:
            raise SerialOwnerError("diagnostic status has no matched reply")
        result = parse_diagnostic(exchange.reply)
        if result[1:3] != self._diagnostic:
            raise SerialOwnerError("diagnostic identity changed")
        if not result[0]:
            self._diagnostic = None
        return result

    def diagnostic_stop(self, deadline_ns: int) -> tuple[bool, str, str, int]:
        self._require_connected()
        if self._diagnostic is None:
            raise SerialOwnerError("no pin diagnostic is active")
        exchange = self._exchange("DIAG_STOP", {}, deadline_ns, routine=False)
        if exchange.reply is None:
            raise SerialOwnerError("diagnostic stop has no matched reply")
        result = parse_diagnostic(exchange.reply)
        if result[0] or result[1:3] != self._diagnostic:
            raise SerialOwnerError("diagnostic stop was not confirmed")
        self._diagnostic = None
        return result

    def on(
        self,
        selected_roles: Iterable[int | str],
        deadline_ns: int,
        *,
        scheduled_boundary_ns: int | None = None,
    ) -> microcontroller_pb2.PulseCommandEvidence:
        return self._pulse(
            "ON",
            microcontroller_pb2.PULSE_BOUNDARY_COMMAND_ON,
            selected_roles,
            deadline_ns,
            scheduled_boundary_ns,
            None,
        )

    def off(
        self,
        selected_roles: Iterable[int | str],
        deadline_ns: int,
        *,
        scheduled_boundary_ns: int | None = None,
        stop_issued_ns: int | None = None,
    ) -> microcontroller_pb2.PulseCommandEvidence:
        return self._pulse(
            "OFF",
            microcontroller_pb2.PULSE_BOUNDARY_COMMAND_OFF,
            selected_roles,
            deadline_ns,
            scheduled_boundary_ns,
            stop_issued_ns,
        )

    def reserve_boundary(
        self,
        boundary_ns: int,
        command: microcontroller_pb2.PulseBoundaryCommand,
        *,
        selected_roles: Iterable[int | str],
    ) -> BoundaryReservation:
        self._assert_owner_thread()
        return self._pulses.reserve(boundary_ns, command, selected_roles=selected_roles)

    def cancel_on_reservations(self) -> None:
        """Cancel unsent execution starts while preserving normal end reservations."""
        self._assert_owner_thread()
        self._pulses.cancel_on_reservations()

    def close(self, deadline_ns: int) -> None:
        """Close immediately; an OS close error remains an unresolved owner blocker."""
        self._assert_owner_thread()
        started_ns = self._clock()
        try:
            self._channel.close()
        except Exception as exc:
            raise SerialOwnerError(
                f"microcontroller port close is unconfirmed: {exc}"
            ) from exc
        self._connected = False
        self._state = None
        self._capabilities = None
        self._capabilities_time_ns = None
        self._pulses.clear()
        self._closed = True
        if started_ns >= deadline_ns or self._clock() >= deadline_ns:
            raise SerialOwnerError(
                "port close returned after the original deadline; completion was late"
            )

    def _pulse(
        self,
        verb: str,
        command: microcontroller_pb2.PulseBoundaryCommand,
        selected_roles: Iterable[int | str],
        deadline_ns: int,
        boundary_ns: int | None,
        stop_issued_ns: int | None,
    ) -> microcontroller_pb2.PulseCommandEvidence:
        evidence, state = self._pulses.execute(
            verb,
            command,
            selected_roles,
            deadline_ns,
            connection_id=self.connection_id,
            boundary_ns=boundary_ns,
            stop_issued_ns=stop_issued_ns,
            current_state=self._state,
            require_connected=self._require_connected,
            exchange_command=self._exchange,
        )
        if state is not None:
            self._state = state
        return evidence

    def _exchange(
        self,
        verb: str,
        fields: dict[str, str],
        deadline_ns: int,
        *,
        routine: bool,
        dispatch_before_ns: int | None = None,
    ) -> Exchange:
        self._assert_owner_thread()
        now = self._clock()
        next_boundary = self._pulses.next_boundary_ns
        if (
            routine
            and next_boundary is not None
            and now + self._ack_ns >= next_boundary
        ):
            raise ChannelDeadline(
                "routine command cannot drain before reserved boundary"
            )
        if dispatch_before_ns is not None and now < dispatch_before_ns:
            raise ChannelDeadline("reserved boundary is not due")
        return self._channel.request(
            verb,
            fields,
            deadline_ns,
            dispatch_before_ns=dispatch_before_ns,
        )

    def _observation(
        self,
        request_id: str,
        state: microcontroller_pb2.MicrocontrollerState,
        *,
        observed_ns: int,
    ) -> microcontroller_pb2.MicrocontrollerObservation:
        observation = microcontroller_pb2.MicrocontrollerObservation(
            port=self.port_name,
            connection_id=self.connection_id,
            request_id=request_id,
            observed_monotonic_ns=observed_ns,
        )
        observation.state.CopyFrom(state)
        if self._capabilities is not None:
            observation.capabilities.CopyFrom(self._capabilities)
        if self._capabilities_time_ns is not None:
            observation.capabilities_observed_monotonic_ns = self._capabilities_time_ns
        return observation

    def _require_connected(self) -> None:
        self._assert_owner_thread()
        if not self._connected or self._state is None:
            raise SerialOwnerError("startup verification has not completed")

    def _require_capabilities(
        self,
    ) -> microcontroller_pb2.MicrocontrollerCapabilities:
        if self._capabilities is None or not self._capabilities.HasField(
            "protocol_version"
        ):
            raise SerialOwnerError("fresh matching CAPS evidence is required")
        return self._capabilities

    def _close_after_startup_failure(self, deadline_ns: int) -> None:
        expired = self._clock() >= deadline_ns
        try:
            self._channel.close()
        except Exception as exc:
            self._connected = False
            raise SerialOwnerError(
                f"startup failed and port close is unconfirmed: {exc}"
            ) from exc
        self._connected = False
        self._state = None
        self._capabilities = None
        self._capabilities_time_ns = None
        if expired or self._clock() >= deadline_ns:
            self._closed = True
            raise SerialOwnerError(
                "startup failure cleanup closed the port after its original deadline"
            )

    def _assert_owner_thread(self) -> None:
        current = threading.get_ident()
        if self._thread_id is None:
            self._thread_id = current
        elif current != self._thread_id:
            raise SerialOwnerError(
                "all serial owner calls must stay on its dedicated thread"
            )


def _required_positive(
    policies: runtime_pb2.AcquisitionFilePolicies, field: str
) -> int:
    if not policies.HasField(field):
        raise ValueError(f"acquisition file policy {field} is required")
    value = getattr(policies, field)
    if isinstance(value, bool) or value <= 0:
        raise ValueError(f"acquisition file policy {field} must be positive")
    return cast(int, value)


def _exact_milliseconds(nanoseconds: int) -> int:
    quotient, remainder = divmod(nanoseconds, 1_000_000)
    if remainder or quotient == 0 or quotient >= 1 << 32:
        raise ValueError(
            "communication watchdog must be an exact positive uint32 ms value"
        )
    return quotient


def _safe_token(value: str, field: str) -> str:
    if not value or any(not (33 <= ord(char) <= 126) or char in "=," for char in value):
        raise ValueError(f"{field} must be a printable ASCII firmware token")
    return value


def _state_from_values(
    values: dict[str, object],
) -> microcontroller_pb2.MicrocontrollerState:
    state = microcontroller_pb2.MicrocontrollerState(
        configuration_valid=cast(bool, values["valid"]),
        watchdog_stopped=cast(bool, values["watchdog_stopped"]),
        watchdog_ms=cast(int, values["watchdog_ms"]),
    )
    outputs = values["outputs"]
    assert isinstance(outputs, dict)
    for role in ROLES:
        item = outputs[role]
        assert isinstance(item, dict)
        output = getattr(state, role)
        enabled = cast(bool, item["enabled"])
        output.enabled = enabled
        output.running = cast(bool, item["running"])
        if enabled:
            output.pin = cast(str, item["pin"])
            output.applied_frequency_hz = cast(float, item["frequency"])
    return state
