"""Host deadlines and receipt-based Setup inactivity accounting."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

from cephvr.shared.clock import INT64_MAX, host_time_ns

Deadline = int | Callable[[], int]


def resolve_deadline(deadline: Deadline) -> int:
    return deadline() if callable(deadline) else deadline


@dataclass
class SetupInactivity:
    """One Setup operation's receipt-based inactivity, never a health waiver."""

    interval_ns: int
    deadline_ns: int
    sequence: int = 0
    message: str = ""
    last_ingress_ns: int = 0

    def advance(self, sequence: int, message: str, ingress_ns: int) -> bool:
        if (
            ingress_ns > self.deadline_ns
            or ingress_ns < self.last_ingress_ns
            or sequence <= self.sequence
            or not message
        ):
            return False
        self.sequence = sequence
        if message == self.message:
            return False
        self.message = message
        self.last_ingress_ns = ingress_ns
        self.deadline_ns = ingress_ns + self.interval_ns
        return True


def duration_ns(value: int | float | Decimal, unit: Literal["s", "ms", "ns"]) -> int:
    """Convert a TOML duration exactly; reject rounding, negatives and overflow."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("duration must be numeric")
    if unit not in ("s", "ms", "ns"):
        raise ValueError("unsupported duration unit")
    try:
        ns = Decimal(str(value)) * {"s": 1_000_000_000, "ms": 1_000_000, "ns": 1}[unit]
    except InvalidOperation as exc:
        raise ValueError("invalid duration") from exc
    if not ns.is_finite() or ns < 0 or ns != ns.to_integral_value() or ns > INT64_MAX:
        raise ValueError(
            "duration cannot be represented as nonnegative int64 nanoseconds"
        )
    return int(ns)


def remaining_ns(
    deadline_ns: Deadline, *, clock: Callable[[], int] = host_time_ns
) -> int:
    """Return nonnegative time to a deadline in nanoseconds."""
    return max(0, resolve_deadline(deadline_ns) - clock())


def remaining_seconds(
    deadline_ns: Deadline, *, clock: Callable[[], int] = host_time_ns
) -> float:
    """Return nonnegative time to a deadline in seconds."""
    return remaining_ns(deadline_ns, clock=clock) / 1_000_000_000


async def wait_until_ns(
    boundary_ns: int, *, clock: Callable[[], int] = host_time_ns
) -> None:
    """Wait for the original host boundary even if an async timer wakes early."""
    # This is a timer correction, not state polling that an Event could replace.
    while remaining := remaining_seconds(boundary_ns, clock=clock):  # noqa: ASYNC110
        await asyncio.sleep(remaining)
