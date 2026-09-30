"""Pulse boundaries, reservation ownership and command evidence."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from cephvr.acquisition.v1 import camera_pb2, microcontroller_pb2
from cephvr.shared.clock import host_time_ns

from .channel import (
    ChannelCancelled,
    ChannelDeadline,
    ChannelTimeout,
    ChannelTransportFailure,
    Exchange,
    SerialChannel,
)
from .protocol import (
    ROLES,
    FirmwareRejected,
    ProtocolError,
    parse_compact_state,
)


@dataclass(frozen=True)
class BoundaryReservation:
    boundary_ns: int
    command: microcontroller_pb2.PulseBoundaryCommand
    behavioral_selected: bool
    tracking_selected: bool


class PulseExecutor:
    """Serialize pulse masks and preserve dispatched, ACK and state evidence."""

    def __init__(
        self,
        channel: SerialChannel,
        ack_timeout_ns: int,
        *,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self._channel = channel
        self._ack_timeout_ns = ack_timeout_ns
        self._clock = clock
        self._reservations: dict[int, BoundaryReservation] = {}

    def reserve(
        self,
        boundary_ns: int,
        command: microcontroller_pb2.PulseBoundaryCommand,
        *,
        selected_roles: Iterable[int | str],
    ) -> BoundaryReservation:
        if command not in (
            microcontroller_pb2.PULSE_BOUNDARY_COMMAND_ON,
            microcontroller_pb2.PULSE_BOUNDARY_COMMAND_OFF,
        ):
            raise ValueError("boundary reservation requires ON or OFF")
        if boundary_ns <= self._clock():
            raise ValueError("boundary must be in the future when reserved")
        roles = normalize_roles(selected_roles)
        if not roles:
            raise ValueError("empty pulse masks do not create a reservation")
        if self._reservations:
            existing = next(iter(self._reservations.values()))
            if existing.behavioral_selected != ("behavioral" in roles) or (
                existing.tracking_selected != ("tracking" in roles)
            ):
                raise ValueError("current-trial ON and OFF masks must match")
        if boundary_ns in self._reservations:
            raise ValueError("a pulse boundary already owns this serial slot")
        if any(item.command == command for item in self._reservations.values()):
            name = (
                "ON"
                if command == microcontroller_pb2.PULSE_BOUNDARY_COMMAND_ON
                else "OFF"
            )
            raise ValueError(f"current-trial {name} slot is already reserved")
        if len(self._reservations) >= 2:
            raise ValueError("only current-trial ON and OFF boundaries may be reserved")
        on_boundary = next(
            (
                item.boundary_ns
                for item in self._reservations.values()
                if item.command == microcontroller_pb2.PULSE_BOUNDARY_COMMAND_ON
            ),
            None,
        )
        if (
            command == microcontroller_pb2.PULSE_BOUNDARY_COMMAND_OFF
            and on_boundary is not None
            and boundary_ns <= on_boundary
        ):
            raise ValueError("current-trial OFF boundary must follow its ON boundary")
        off_boundary = next(
            (
                item.boundary_ns
                for item in self._reservations.values()
                if item.command == microcontroller_pb2.PULSE_BOUNDARY_COMMAND_OFF
            ),
            None,
        )
        if (
            command == microcontroller_pb2.PULSE_BOUNDARY_COMMAND_ON
            and off_boundary is not None
            and boundary_ns >= off_boundary
        ):
            raise ValueError("current-trial ON boundary must precede its OFF boundary")
        if any(
            abs(other - boundary_ns) <= self._ack_timeout_ns
            for other in self._reservations
        ):
            raise ValueError(
                "pulse boundary reservations overlap an acknowledgement budget"
            )
        reservation = BoundaryReservation(
            boundary_ns,
            command,
            "behavioral" in roles,
            "tracking" in roles,
        )
        self._reservations[boundary_ns] = reservation
        return reservation

    def cancel_on_reservations(self) -> None:
        """Cancel unsent starts while preserving normal end reservations."""
        self._reservations = {
            time_ns: item
            for time_ns, item in self._reservations.items()
            if item.command != microcontroller_pb2.PULSE_BOUNDARY_COMMAND_ON
        }

    def clear(self) -> None:
        self._reservations.clear()

    @property
    def next_boundary_ns(self) -> int | None:
        return min(self._reservations, default=None)

    def execute(
        self,
        verb: str,
        command: microcontroller_pb2.PulseBoundaryCommand,
        selected_roles: Iterable[int | str],
        deadline_ns: int,
        *,
        connection_id: str,
        boundary_ns: int | None,
        stop_issued_ns: int | None,
        current_state: microcontroller_pb2.MicrocontrollerState | None,
        require_connected: Callable[[], None],
        exchange_command: Callable[..., Exchange],
    ) -> tuple[
        microcontroller_pb2.PulseCommandEvidence,
        microcontroller_pb2.MicrocontrollerState | None,
    ]:
        roles = normalize_roles(selected_roles)
        evidence = microcontroller_pb2.PulseCommandEvidence(
            connection_id=connection_id,
            command=command,
            behavioral_selected="behavioral" in roles,
            tracking_selected="tracking" in roles,
            outcome=microcontroller_pb2.PULSE_COMMAND_OUTCOME_NOT_DISPATCHED,
        )
        if boundary_ns is not None:
            evidence.scheduled_boundary_monotonic_ns = boundary_ns
        if stop_issued_ns is not None:
            evidence.stop_issued_monotonic_ns = stop_issued_ns
        if not roles:
            evidence.error_code = "EMPTY_SELECTION"
            return evidence, current_state
        if self._clock() >= deadline_ns:
            evidence.error_code = "DEADLINE_EXPIRED"
            if boundary_ns is not None:
                self._reservations.pop(boundary_ns, None)
            return evidence, current_state
        if boundary_ns is not None:
            reservation = self._reservations.get(boundary_ns)
            if not _matches_reservation(reservation, command, roles):
                evidence.error_code = "BOUNDARY_NOT_RESERVED"
                return evidence, current_state
            if self._clock() < boundary_ns:
                evidence.error_code = "BOUNDARY_NOT_DUE"
                return evidence, current_state
        fields = {
            "behavioral_selected": "1" if "behavioral" in roles else "0",
            "tracking_selected": "1" if "tracking" in roles else "0",
        }
        before_exchange = self._channel.last_exchange
        next_state = current_state
        try:
            require_connected()
            exchange = exchange_command(
                verb,
                fields,
                deadline_ns,
                routine=False,
                dispatch_before_ns=boundary_ns,
            )
            evidence.request_id = exchange.request_id
            evidence.dispatched_monotonic_ns = exchange.dispatched_ns
            if exchange.reply is None:
                evidence.outcome = microcontroller_pb2.PULSE_COMMAND_OUTCOME_TIMED_OUT
                evidence.error_code = "ACK_TIMEOUT"
                return evidence, current_state
            compact = parse_compact_state(exchange.reply)
            state = microcontroller_pb2.MicrocontrollerState()
            if current_state is not None:
                state.CopyFrom(current_state)
            state.watchdog_stopped = compact["watchdog_stopped"]
            for role in ROLES:
                getattr(state, role).running = compact[f"{role}_running"]
            evidence.resulting_state.CopyFrom(state)
            next_state = state
            if compact["watchdog_stopped"] and verb != "OFF":
                raise ProtocolError("matched pulse reply reports watchdog stopped")
            expected_running = verb == "ON"
            if any(compact[f"{role}_running"] != expected_running for role in roles):
                raise ProtocolError(
                    "matched pulse reply lacks the selected output transition"
                )
            if exchange.completed_ns is not None:
                evidence.acknowledged_monotonic_ns = exchange.completed_ns
            evidence.applied = True
            evidence.outcome = microcontroller_pb2.PULSE_COMMAND_OUTCOME_APPLIED
            if compact["watchdog_stopped"]:
                evidence.error_code = "WATCHDOG_STOPPED"
        except ChannelTimeout:
            self._record_dispatch(evidence, before_exchange)
            evidence.outcome = microcontroller_pb2.PULSE_COMMAND_OUTCOME_TIMED_OUT
            evidence.error_code = "ACK_TIMEOUT"
        except FirmwareRejected as exc:
            self._record_dispatch(evidence, before_exchange)
            rejected = self._channel.last_exchange
            if (
                rejected is not None
                and rejected is not before_exchange
                and rejected.reply is not None
                and not rejected.reply.ok
                and rejected.completed_ns is not None
            ):
                evidence.acknowledged_monotonic_ns = rejected.completed_ns
            evidence.applied = False
            evidence.outcome = microcontroller_pb2.PULSE_COMMAND_OUTCOME_REJECTED
            evidence.error_code = exc.code
        except (
            ChannelCancelled,
            ChannelDeadline,
            ChannelTransportFailure,
            ProtocolError,
            RuntimeError,
            ValueError,
        ) as exc:
            self._record_dispatch(evidence, before_exchange)
            evidence.error_code = _error_code(exc)
            if evidence.HasField("dispatched_monotonic_ns"):
                evidence.outcome = (
                    microcontroller_pb2.PULSE_COMMAND_OUTCOME_TRANSPORT_FAILED
                )
        finally:
            if boundary_ns is not None:
                self._reservations.pop(boundary_ns, None)
        return evidence, next_state

    def _record_dispatch(
        self,
        evidence: microcontroller_pb2.PulseCommandEvidence,
        before_exchange: Exchange | None,
    ) -> None:
        exchange = self._channel.last_exchange
        if exchange is not None and exchange is not before_exchange:
            evidence.request_id = exchange.request_id
            evidence.dispatched_monotonic_ns = exchange.dispatched_ns


def normalize_roles(values: Iterable[int | str]) -> set[str]:
    names: set[str] = set()
    for value in values:
        if type(value) is str and value in ROLES:
            name = value
        elif type(value) is int and value == camera_pb2.CAMERA_ROLE_BEHAVIORAL:
            name = "behavioral"
        elif type(value) is int and value == camera_pb2.CAMERA_ROLE_TRACKING:
            name = "tracking"
        else:
            raise ValueError(f"unknown or unspecified camera role {value!r}")
        if name in names:
            raise ValueError(f"duplicate camera role {name}")
        names.add(name)
    return names


def _matches_reservation(
    item: BoundaryReservation | None,
    command: microcontroller_pb2.PulseBoundaryCommand,
    roles: set[str],
) -> bool:
    return bool(
        item is not None
        and item.command == command
        and item.behavioral_selected == ("behavioral" in roles)
        and item.tracking_selected == ("tracking" in roles)
    )


def _error_code(error: BaseException) -> str:
    if isinstance(error, ChannelCancelled):
        return "REQUEST_CANCELLED"
    message = str(error).upper()
    for code in (
        "ACK_TIMEOUT",
        "DEADLINE_EXPIRED",
        "SERIAL",
        "PROTOCOL",
        "CONFIGURATION",
    ):
        if code in message:
            return code
    return "SERIAL_FAILURE"
