"""Bounded per-trial recording diagnostics; durations never control deadlines."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable


class RecordingMetrics:
    """Aggregate fixed stages and retain timestamps only for admitted slots."""

    def __init__(self, clock_ns: Callable[[], int]) -> None:
        self.clock_ns = clock_ns
        self._lock = threading.Lock()
        self._stages = {
            name: [0, 0, 0]
            for name in (
                "readback_poll_ready",
                "readback_poll_pending",
                "capture_ready",
                "queue_wait",
                "normalization",
                "pipe_write",
                "slot_hold",
            )
        }
        self._admitted: dict[int, int] = {}
        self._ready: dict[int, int] = {}
        self._peak_slots = 0
        self._zero_writes = 0
        self._written_bytes = 0
        self._cancelled = 0

    def _observe(self, name: str, elapsed_ns: int) -> None:
        item = self._stages[name]
        elapsed_ns = max(0, elapsed_ns)
        item[0] += 1
        item[1] += elapsed_ns
        item[2] = max(item[2], elapsed_ns)

    def observe(self, name: str, elapsed_ns: int) -> None:
        with self._lock:
            self._observe(name, elapsed_ns)

    def reserve(self, group: int, occupied_slots: int) -> None:
        with self._lock:
            self._admitted[group] = self.clock_ns()
            self._peak_slots = max(self._peak_slots, occupied_slots)

    def ready(self, group: int) -> None:
        with self._lock:
            now = self.clock_ns()
            self._observe("capture_ready", now - self._admitted[group])
            self._ready[group] = now

    def dequeue(self, group: int) -> None:
        with self._lock:
            self._observe("queue_wait", self.clock_ns() - self._ready.pop(group))

    def release(self, group: int, *, cancelled: bool = False) -> None:
        with self._lock:
            self._observe("slot_hold", self.clock_ns() - self._admitted.pop(group))
            self._ready.pop(group, None)
            self._cancelled += int(cancelled)

    def write(self, elapsed_ns: int, consumed: int) -> None:
        with self._lock:
            self._observe("pipe_write", elapsed_ns)
            self._zero_writes += int(consumed == 0)
            self._written_bytes += max(0, consumed)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "stages_ns": {
                    name: dict(zip(("count", "total", "max"), values, strict=True))
                    for name, values in self._stages.items()
                },
                "peak_capture_slots": self._peak_slots,
                "active_capture_slots": len(self._admitted),
                "queued_captures": len(self._ready),
                "zero_progress_writes": self._zero_writes,
                "submitted_bytes": self._written_bytes,
                "cancelled_captures": self._cancelled,
            }


def configure_recording_logger() -> None:
    """Enable JSON summary output in the renderer without changing root logging."""
    logger = logging.getLogger("cephvr.visual_stimulus.recording.session")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
