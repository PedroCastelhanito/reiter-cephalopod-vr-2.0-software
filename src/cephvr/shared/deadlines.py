"""Original absolute host deadlines; retries and nested work cannot renew them."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

from cephvr.shared.clock import INT64_MAX, host_time_ns, require_int64_ns


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


def earliest_deadline(*values: int) -> int:
    """Carry the earliest applicable absolute cutoff through nested work."""
    if not values:
        raise ValueError("at least one deadline is required")
    for value in values:
        require_int64_ns(value)
    return min(values)


@dataclass(frozen=True)
class Deadline:
    absolute_ns: int

    def __post_init__(self) -> None:
        require_int64_ns(self.absolute_ns)

    @classmethod
    def after(cls, duration: int, *, now_ns: int | None = None) -> Deadline:
        require_int64_ns(duration)
        start = host_time_ns() if now_ns is None else require_int64_ns(now_ns)
        return cls(require_int64_ns(start + duration))

    def constrain(self, other: Deadline) -> Deadline:
        return Deadline(min(self.absolute_ns, other.absolute_ns))

    def remaining_ns(self, *, now_ns: int | None = None) -> int:
        now = host_time_ns() if now_ns is None else require_int64_ns(now_ns)
        return max(0, self.absolute_ns - now)

    def expired_at(self, ingress_ns: int) -> bool:
        """The cutoff is inclusive: ingress at the deadline still qualifies."""
        return require_int64_ns(ingress_ns) > self.absolute_ns
