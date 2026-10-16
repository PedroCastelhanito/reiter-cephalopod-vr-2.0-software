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
                "frame_input",
                "slot_hold",
            )
        }
        self._worst_samples: dict[str, dict[str, int]] = {}
        self._frame_input: dict[str, int] | None = None
        self._admitted: dict[int, int] = {}
        self._ready: dict[int, int] = {}
        self._peak_slots = 0
        self._zero_writes = 0
        self._written_bytes = 0
        self._cancelled = 0

    def _observe(
        self, name: str, elapsed_ns: int, sample: dict[str, int] | None = None
    ) -> None:
        item = self._stages[name]
        elapsed_ns = max(0, elapsed_ns)
        item[0] += 1
        item[1] += elapsed_ns
        if elapsed_ns > item[2]:
            self._worst_samples.pop(name, None)
        if sample is not None and (
            elapsed_ns > item[2]
            or (elapsed_ns == item[2] and name not in self._worst_samples)
        ):
            self._worst_samples[name] = {**sample, "elapsed_ns": elapsed_ns}
        item[2] = max(item[2], elapsed_ns)

    def observe(
        self, name: str, elapsed_ns: int, *, sample: dict[str, int] | None = None
    ) -> None:
        with self._lock:
            self._observe(name, elapsed_ns, sample)

    def reserve(self, group: int, occupied_slots: int) -> None:
        with self._lock:
            self._admitted[group] = self.clock_ns()
            self._peak_slots = max(self._peak_slots, occupied_slots)

    def ready(self, group: int) -> None:
        with self._lock:
            now = self.clock_ns()
            self._observe(
                "capture_ready",
                now - self._admitted[group],
                self._sample(group, self._admitted[group], now),
            )
            self._ready[group] = now

    def dequeue(self, group: int) -> None:
        with self._lock:
            started, ended = self._ready.pop(group), self.clock_ns()
            self._observe(
                "queue_wait", ended - started, self._sample(group, started, ended)
            )

    def release(self, group: int, *, cancelled: bool = False) -> None:
        with self._lock:
            started, ended = self._admitted.pop(group), self.clock_ns()
            self._observe(
                "slot_hold", ended - started, self._sample(group, started, ended)
            )
            self._ready.pop(group, None)
            self._cancelled += int(cancelled)

    @staticmethod
    def _sample(group: int, started: int, ended: int) -> dict[str, int]:
        return {
            "group_id": group,
            "start_monotonic_ns": started,
            "end_monotonic_ns": ended,
        }

    def write(
        self,
        elapsed_ns: int,
        consumed: int,
        *,
        group_id: int,
        video_frame_index: int,
        started_ns: int,
        completed_ns: int,
        frame_complete: bool,
    ) -> None:
        """Observe one write attempt for a serialized encoder input frame.

        pipe_write measures this call only. frame_input spans the first attempt
        through complete consumption, including gaps between zero-progress calls.
        Keep at most one unfinished frame; the caller serializes frames by group
        and video index. Consumption proves pipe acceptance, not encoding or sync.
        """
        with self._lock:
            sample = {
                **self._sample(group_id, started_ns, completed_ns),
                "video_frame_index": video_frame_index,
            }
            self._observe("pipe_write", elapsed_ns, sample)
            self._zero_writes += int(consumed == 0)
            self._written_bytes += max(0, consumed)
            current = self._frame_input
            if current is None or (
                current["group_id"],
                current["video_frame_index"],
            ) != (group_id, video_frame_index):
                current = {
                    "group_id": group_id,
                    "video_frame_index": video_frame_index,
                    "start_monotonic_ns": started_ns,
                    "write_attempts": 0,
                    "zero_progress_writes": 0,
                }
                self._frame_input = current
            current["write_attempts"] += 1
            current["zero_progress_writes"] += int(consumed == 0)
            if frame_complete:
                self._observe(
                    "frame_input",
                    completed_ns - current["start_monotonic_ns"],
                    {**current, "end_monotonic_ns": completed_ns},
                )
                self._frame_input = None

    def snapshot(self) -> dict[str, object]:
        """Copy aggregates, per-stage maximum examples and the unfinished input.

        Stage maxima may describe different frames; they are not a correlated
        trace. No returned diagnostic mapping aliases mutable metric state.
        """
        with self._lock:
            return {
                "stages_ns": {
                    name: dict(zip(("count", "total", "max"), values, strict=True))
                    for name, values in self._stages.items()
                },
                "worst_stage_samples": {
                    name: dict(sample) for name, sample in self._worst_samples.items()
                },
                "unfinished_frame_input": dict(self._frame_input)
                if self._frame_input is not None
                else None,
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
