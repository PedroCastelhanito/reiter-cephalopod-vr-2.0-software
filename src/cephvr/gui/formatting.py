"""Shared operator-facing value formatting, independent of Qt."""

import re
from decimal import Decimal, InvalidOperation


def caption_caps(text: str) -> str:
    """Uppercase a caption but keep parenthesised units such as (mA) or (hh:mm:ss)."""
    return re.sub(r"[^()]+(?![^(]*\))", lambda part: part[0].upper(), text)


def card_caption(text: str, *, retro: bool, phosphor: bool, nested: bool) -> str:
    """Shared card heading treatment for runtime and offline windows."""
    if phosphor:
        return f"| {text.upper()} |" if nested else f"< {text.upper()} >"
    return text.upper() if retro else text


def parse_clock_duration(value: str) -> str:
    """Convert an epoch clock entry to exact decimal seconds."""
    parts = value.strip().split(":")
    if (
        len(parts) != 3
        or not re.fullmatch(r"[0-9]{2,}", parts[0])
        or not re.fullmatch(r"[0-9]{2}", parts[1])
        or not re.fullmatch(r"[0-9]{2}(?:\.[0-9]{1,9})?", parts[2])
    ):
        raise ValueError(
            "Use duration hh:mm:ss.mmm (milliseconds; finer precision is allowed)"
        )
    hours, minutes, seconds = parts
    try:
        second = Decimal(seconds)
    except InvalidOperation as error:
        raise ValueError(
            "Use duration hh:mm:ss.mmm (milliseconds; finer precision is allowed)"
        ) from error
    if not second.is_finite() or not 0 <= int(minutes) < 60 or not 0 <= second < 60:
        raise ValueError("Use duration hh:mm:ss.mmm with minutes and seconds below 60")
    result = format(Decimal(hours) * 3600 + Decimal(minutes) * 60 + second, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def clock_duration(seconds: str | float) -> str:
    total = Decimal(str(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, second = divmod(remainder, 60)
    fraction = format(second, "f").partition(".")[2].ljust(3, "0")
    second_text = f"{int(second):02d}.{fraction}"
    return f"{int(hours):02d}:{int(minutes):02d}:{second_text}"


def duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    total = max(0, round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, seconds_part = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds_part:02d}"


HudRows = tuple[tuple[str, str] | None, ...]


def hud_grid(lines: tuple[tuple[tuple[str, str], ...], ...], *, retro: bool) -> str:
    """Align HUD pairs into label/value columns shared by every line."""
    separator = " : " if retro else "  "
    columns = max((len(line) for line in lines), default=0)
    keys = [
        max(len(line[i][0]) for line in lines if i < len(line)) for i in range(columns)
    ]
    values = [
        max(len(line[i][1]) for line in lines if i < len(line)) for i in range(columns)
    ]
    return "\n".join(
        "    ".join(
            ("> " if retro and i else "")
            + f"{key.upper():<{keys[i]}}{separator}{value:<{values[i]}}"
            for i, (key, value) in enumerate(line)
        ).rstrip()
        for line in lines
    )


def hud_text(rows: HudRows, *, retro: bool) -> str:
    """Align HUD labels across sections; None separates groups, empty labels are notes."""
    width = max((len(row[0]) for row in rows if row is not None), default=0)
    separator = " : " if retro else "  "
    return "\n".join(
        ""
        if row is None
        else f"{row[0].upper():<{width}}{separator}{row[1]}"
        if row[0]
        else row[1]
        for row in rows
    )
