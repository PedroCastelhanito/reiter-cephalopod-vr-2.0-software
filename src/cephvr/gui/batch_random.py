"""Bounded authoring-time samples on an explicit numeric precision grid."""

from collections.abc import Callable
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation, localcontext
from math import isfinite


def random_values(
    minimum: str,
    maximum: str,
    precision: str,
    count: str,
    randbelow: Callable[[int], int],
) -> tuple[str, ...]:
    try:
        if any(len(text) > 64 for text in (minimum, maximum, precision, count)):
            raise ValueError("Random fields are too long")
        low, high, step = (
            Decimal(text.strip()) for text in (minimum, maximum, precision)
        )
        size = int(count.strip())
        if not all(v.is_finite() and isfinite(float(v)) for v in (low, high, step)):
            raise ValueError("Random range and precision must be finite")
        if any(v != 0 and float(v) == 0 for v in (low, high, step)):
            raise ValueError("Random values are below the supported numeric precision")
        if low > high or step <= 0:
            raise ValueError("Random needs min ≤ max and positive precision")
        if not 1 <= size <= 2000:
            raise ValueError("Random supports at most 2000 expanded epochs")
        with localcontext() as context:
            context.prec = max(
                28,
                max(len(v.as_tuple().digits) for v in (low, high, step))
                + max(v.adjusted() if v else 0 for v in (low, high, step))
                - min(v.adjusted() if v else 0 for v in (low, high, step))
                + 8,
            )
            first = int((low / step).to_integral_value(rounding=ROUND_CEILING))
            last = int((high / step).to_integral_value(rounding=ROUND_FLOOR))
            if first > last:
                raise ValueError("Range contains no values at the selected precision")
            return tuple(
                str(Decimal(first + randbelow(last - first + 1)) * step)
                for _ in range(size)
            )
    except (InvalidOperation, OverflowError) as error:
        raise ValueError(
            "Provide numeric min, max, precision and an integer epoch count"
        ) from error
