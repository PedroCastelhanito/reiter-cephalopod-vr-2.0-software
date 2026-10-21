"""Bounded display-rate measurements; no capture scheduling or health authority."""

from math import isfinite


class PreviewRateMeter:
    def __init__(self) -> None:
        self.started_ns: int | None = None
        self.presented = 0
        self.source: tuple[int, int] | None = None
        self.baseline: tuple[int, int] | None = None

    def received(self, count: int, time_ns: int) -> None:
        current = count, time_ns
        if self.source is not None and (
            count < self.source[0] or time_ns < self.source[1]
        ):
            self.baseline = None
        self.source = current
        if self.baseline is None:
            self.baseline = current

    def sample(self, now_ns: int) -> tuple[float | None, float] | None:
        if self.started_ns is None:
            self.started_ns = now_ns
            self.presented = 0
            return None
        elapsed = now_ns - self.started_ns
        if elapsed < 1_000_000_000:
            return None
        source_fps = None
        if self.source is not None and self.baseline is not None:
            count = self.source[0] - self.baseline[0]
            duration = self.source[1] - self.baseline[1]
            if duration > 0:
                source_fps = count * 1e9 / duration
            elif now_ns - self.source[1] >= 1_000_000_000:
                source_fps = 0.0
        preview_fps = self.presented * 1e9 / elapsed
        self.baseline = self.source
        self.started_ns = now_ns
        self.presented = 0
        return source_fps, preview_fps


def valid_rates(source: float | None, preview: float | None, observed_ns: int) -> bool:
    return observed_ns > 0 and all(
        value is None or (isfinite(value) and value >= 0) for value in (source, preview)
    )
