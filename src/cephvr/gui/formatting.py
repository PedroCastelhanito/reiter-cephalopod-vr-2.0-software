"""Shared operator-facing value formatting, independent of Qt."""


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
