"""Original absolute host deadlines; retries and nested work cannot renew them."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Literal

from cephvr.shared.clock import INT64_MAX, host_time_ns


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


def remaining_ns(deadline_ns: int, *, clock: Callable[[], int] = host_time_ns) -> int:
    """Return nonnegative time to a deadline in nanoseconds."""
    return max(0, deadline_ns - clock())


def remaining_seconds(
    deadline_ns: int, *, clock: Callable[[], int] = host_time_ns
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
