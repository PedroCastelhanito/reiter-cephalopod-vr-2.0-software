"""Bounded aggregate image-stage timings; no per-frame records or GPU waits."""

import threading
from dataclasses import dataclass, field


@dataclass(slots=True)
class ImageTimings:
    """Loader-thread records and render-thread reads/resets share one lock."""

    stages: dict[str, tuple[int, int, int]] = field(default_factory=dict)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False, compare=False
    )

    def record(self, stage: str, elapsed_ns: int) -> None:
        with self._lock:
            count, total, maximum = self.stages.get(stage, (0, 0, 0))
            self.stages[stage] = (
                count + 1,
                total + elapsed_ns,
                max(maximum, elapsed_ns),
            )

    def clear(self) -> None:
        with self._lock:
            self.stages.clear()

    def snapshot(self) -> dict[str, tuple[int, int, int]]:
        with self._lock:
            return dict(self.stages)

    def summary(self) -> dict[str, dict[str, float | int]]:
        return {
            key: {"count": n, "total_ms": total / 1e6, "max_ms": maximum / 1e6}
            for key, (n, total, maximum) in self.snapshot().items()
        }
