"""Shared operator-facing value formatting, independent of Qt."""

import re
from decimal import Decimal, InvalidOperation


def parse_clock_duration(value: str) -> str:
    """Convert an epoch clock entry to exact decimal seconds."""
    parts = value.strip().split(":")
    if (
        len(parts) != 3
        or not re.fullmatch(r"[0-9]{2,}", parts[0])
        or not re.fullmatch(r"[0-9]{2}", parts[1])
        or not re.fullmatch(r"[0-9]{2}(?:\.[0-9]{1,9})?", parts[2])
    ):
        raise ValueError("Use duration hh:mm:ss (fractional seconds are allowed)")
    hours, minutes, seconds = parts
    try:
        second = Decimal(seconds)
    except InvalidOperation as error:
        raise ValueError(
            "Use duration hh:mm:ss (fractional seconds are allowed)"
        ) from error
    if not second.is_finite() or not 0 <= int(minutes) < 60 or not 0 <= second < 60:
        raise ValueError("Use duration hh:mm:ss with minutes and seconds below 60")
    return str(Decimal(hours) * 3600 + Decimal(minutes) * 60 + second)


def clock_duration(seconds: str | float) -> str:
    total = Decimal(str(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, second = divmod(remainder, 60)
    second_text = (
        f"{int(second):02d}." + format(second, "f").partition(".")[2]
        if second % 1
        else f"{int(second):02d}"
    )
    return f"{int(hours):02d}:{int(minutes):02d}:{second_text}"


def duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    total = max(0, round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, seconds_part = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds_part:02d}"


def metrics_text(rows: tuple[tuple[str, str], ...]) -> str:
    width = max((len(key) for key, _ in rows), default=0)
    return "\n".join(f"{key:<{width}}  {value}" for key, value in rows)
