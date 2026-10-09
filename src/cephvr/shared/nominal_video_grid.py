"""Exact host-time mapping between source samples and nominal video slots."""

from __future__ import annotations

from fractions import Fraction


class NominalVideoGrid:
    """Map half-open source intervals to CFR slots without storing trial slots."""

    def __init__(self, start_ns: int, rate_hz: float | Fraction) -> None:
        if start_ns < 0:
            raise ValueError("video start must be nonnegative")
        try:
            rate = Fraction(str(rate_hz))
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError("video rate must be finite and positive") from exc
        if rate <= 0:
            raise ValueError("video rate must be finite and positive")
        self.start_ns = start_ns
        self.rate = rate

    def slot_for(self, source_ns: int) -> int:
        """Return n for [T+n/R,T+(n+1)/R), using exact rational arithmetic."""
        if source_ns < self.start_ns:
            raise ValueError("source time precedes video start")
        return ((source_ns - self.start_ns) * self.rate.numerator) // (
            1_000_000_000 * self.rate.denominator
        )

    def slots_before(self, cutoff_ns: int) -> int:
        """Count slots with starts strictly before cutoff (ceil(duration * rate))."""
        if cutoff_ns < self.start_ns:
            raise ValueError("video cutoff precedes video start")
        numerator = (cutoff_ns - self.start_ns) * self.rate.numerator
        denominator = 1_000_000_000 * self.rate.denominator
        return (numerator + denominator - 1) // denominator
