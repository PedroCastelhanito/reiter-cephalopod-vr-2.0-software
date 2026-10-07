"""Controller keepalive scheduling preserves A11 reservation and watchdog budgets."""

import asyncio
from collections.abc import Awaitable, Callable

from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import types_pb2 as control
from cephvr.controller.microcontroller.channel import ChannelDeadline
from cephvr.shared.microcontroller import SerialOwnerPort


class MicrocontrollerHealth:
    def __init__(
        self,
        *,
        observation: Callable[[], mcu.MicrocontrollerObservation | None],
        serial: SerialOwnerPort,
        serial_keepalive_interval_ns: int,
        serial_communication_timeout_ns: int,
        serial_ack_timeout_ns: int,
        serial_handoff_active: Callable[[], bool],
        next_boundary: Callable[[int], int | None],
        failure_handler: Callable[[control.Failure], Awaitable[None]],
        clock: Callable[[], int],
        policy_values: Callable[[], tuple[int, int, int]] | None = None,
        changed: Callable[[], None] = lambda: None,
    ) -> None:
        self.observation = observation
        self.serial = serial
        self.serial_keepalive_interval_ns = serial_keepalive_interval_ns
        self.serial_communication_timeout_ns = serial_communication_timeout_ns
        self.serial_ack_timeout_ns = serial_ack_timeout_ns
        self.serial_handoff_active = serial_handoff_active
        self.next_boundary = next_boundary
        self.failure_handler = failure_handler
        self.clock = clock
        self.policy_values = policy_values
        self.changed = changed

    async def run(self, shutdown: asyncio.Event) -> None:
        while not shutdown.is_set():
            await self._keepalive_loop(shutdown)
            await _wait(shutdown, 100_000_000)

    async def _keepalive_loop(self, shutdown: asyncio.Event) -> None:
        due_ns: int | None = None
        connection_id: str | None = None
        last_valid_ns: int | None = None
        last_observation_ns: int | None = None
        while not shutdown.is_set():
            if self.policy_values is not None:
                (
                    self.serial_keepalive_interval_ns,
                    self.serial_communication_timeout_ns,
                    self.serial_ack_timeout_ns,
                ) = self.policy_values()
            observation = self.observation()
            if (
                self.serial_handoff_active()
                or observation is None
                or not observation.connection_id
                or (
                    observation.state.HasField("configuration_valid")
                    and not observation.state.configuration_valid
                    and observation.state.HasField("watchdog_ms")
                    and observation.state.watchdog_ms == 0
                    and all(
                        observation.state.HasField(role)
                        and getattr(observation.state, role).HasField("running")
                        and not getattr(observation.state, role).running
                        for role in ("behavioral", "tracking")
                    )
                )
            ):
                # A connection-only probe leaves the firmware watchdog unarmed.
                due_ns = None
                connection_id = None
                last_valid_ns = None
                last_observation_ns = None
                await _wait(
                    shutdown, min(self.serial_keepalive_interval_ns, 100_000_000)
                )
                continue
            now = self.clock()
            if connection_id != observation.connection_id:
                connection_id = observation.connection_id
                observed_ns = (
                    observation.observed_monotonic_ns
                    if observation.HasField("observed_monotonic_ns")
                    else now
                )
                last_observation_ns = observed_ns
                last_valid_ns = observed_ns
                due_ns = observed_ns + self.serial_keepalive_interval_ns
            elif (
                observation.HasField("observed_monotonic_ns")
                and observation.observed_monotonic_ns > (last_observation_ns or 0)
                and observation.state.HasField("configuration_valid")
                and observation.state.configuration_valid
                and observation.state.HasField("watchdog_stopped")
                and not observation.state.watchdog_stopped
                and observation.state.HasField("watchdog_ms")
                and observation.state.watchdog_ms > 0
            ):
                last_observation_ns = observation.observed_monotonic_ns
                last_valid_ns = observation.observed_monotonic_ns
                due_ns = (
                    observation.observed_monotonic_ns
                    + self.serial_keepalive_interval_ns
                )
            if due_ns is None:
                last_valid_ns = now
                due_ns = now + self.serial_keepalive_interval_ns
            if now < due_ns:
                await _wait(shutdown, due_ns - now)
                continue
            watchdog_ms = (
                observation.state.watchdog_ms
                if observation.state.HasField("watchdog_ms")
                else 0
            )
            watchdog_deadline = (
                (last_valid_ns or now)
                + watchdog_ms * 1_000_000
                - self.serial_ack_timeout_ns
            )
            if watchdog_ms <= 0 or now >= watchdog_deadline:
                await self.failure_handler(
                    control.Failure(
                        code="MICROCONTROLLER_KEEPALIVE_WINDOW_EXHAUSTED",
                        message="no bounded keepalive window remains before the configured watchdog expires",
                    ),
                )
                return
            boundary = self.next_boundary(now)
            if boundary is not None and now + self.serial_ack_timeout_ns >= boundary:
                due_ns = boundary + self.serial_ack_timeout_ns
                continue
            deadline = min(
                now + self.serial_communication_timeout_ns,
                watchdog_deadline,
            )
            observed_before = observation.observed_monotonic_ns
            connection_before = observation.connection_id
            try:
                state = await self.serial.keepalive(deadline_ns=deadline)
            except ChannelDeadline:
                # The owner deferred routine traffic to protect a reserved ON/OFF.
                retry_at = (
                    boundary + self.serial_ack_timeout_ns
                    if boundary is not None
                    else now + self.serial_ack_timeout_ns
                )
                due_ns = min(retry_at, watchdog_deadline)
                continue
            except Exception as exc:
                if self.serial_handoff_active():
                    continue
                await self.failure_handler(
                    control.Failure(
                        code="MICROCONTROLLER_KEEPALIVE_FAILED",
                        message=f"serial watchdog keepalive failed: {exc}"[:2048],
                    ),
                )
                return
            if (
                self.serial_handoff_active()
                or self.observation() is not observation
                or observation.connection_id != connection_before
                or observation.observed_monotonic_ns != observed_before
            ):
                continue
            if not state.HasField("watchdog_stopped") or state.watchdog_stopped:
                await self.failure_handler(
                    control.Failure(
                        code="MICROCONTROLLER_WATCHDOG_STOPPED",
                        message="MCU keepalive did not prove a running watchdog state",
                    ),
                )
                return
            observation.state.CopyFrom(state)
            last_valid_ns = self.clock()
            observation.observed_monotonic_ns = last_valid_ns
            self.changed()
            due_ns = last_valid_ns + self.serial_keepalive_interval_ns


async def _wait(shutdown: asyncio.Event, delay_ns: int) -> None:
    try:
        await asyncio.wait_for(shutdown.wait(), max(0, delay_ns) / 1_000_000_000)
    except TimeoutError:
        pass
