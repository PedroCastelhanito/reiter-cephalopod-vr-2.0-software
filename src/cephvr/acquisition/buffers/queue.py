"""Bounded ordered capture-to-recording handoff (A03/A04/A07)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Condition
from time import monotonic
from typing import TypeAlias

from cephvr.acquisition.buffers.records import FrameRecord


class PendingRecordCapacityError(RuntimeError):
    """The writer cannot preserve complete ordered frame accounting."""


@dataclass(slots=True)
class _Entry:
    record: FrameRecord
    pixels: memoryview | None
    dropped: bool


@dataclass(frozen=True, slots=True)
class RecordingEntry:
    record: FrameRecord
    pixels: memoryview | None
    dropped: bool


@dataclass(frozen=True, slots=True)
class QueueAdmission:
    dropped_record: FrameRecord | None
    dropped_pixels: memoryview | None


QueueResult: TypeAlias = RecordingEntry | None


class RecordingQueue:
    """Single-producer/single-consumer ordered queue with oldest-waiting drops.

    Entries remain in source order so invalid and overloaded frames can each get one
    frame-log line. Queue capacity bounds waiting pixel payloads; pending capacity
    bounds all not-yet-accounted records.
    """

    def __init__(self, capacity_frames: int, pending_records_capacity: int) -> None:
        if capacity_frames <= 0 or pending_records_capacity <= 0:
            raise ValueError("queue and pending-record capacities must be positive")
        self.capacity_frames = capacity_frames
        self.pending_records_capacity = pending_records_capacity
        self._entries: deque[_Entry] = deque()
        self._inflight: FrameRecord | None = None
        self._waiting_pixels = 0
        self._inflight_pixels: memoryview | None = None
        self._closed = False
        self._condition = Condition()

    def enqueue(self, record: FrameRecord, pixels: memoryview | None) -> QueueAdmission:
        if record.valid_image != (pixels is not None):
            raise ValueError(
                "valid frames require pixels; invalid frames must omit them"
            )
        with self._condition:
            if self._closed:
                raise RuntimeError("recording queue is closed")
            if (
                len(self._entries) + (self._inflight is not None)
                >= self.pending_records_capacity
            ):
                raise PendingRecordCapacityError(
                    "pending frame-record capacity exhausted"
                )
            dropped: FrameRecord | None = None
            dropped_pixels: memoryview | None = None
            if pixels is not None and self._waiting_pixels >= self.capacity_frames:
                for previous in self._entries:
                    if previous.pixels is not None:
                        dropped_pixels = memoryview(previous.pixels)
                        previous.pixels = None
                        previous.dropped = True
                        self._waiting_pixels -= 1
                        dropped = previous.record
                        break
            self._entries.append(_Entry(record, pixels, False))
            if pixels is not None:
                self._waiting_pixels += 1
            self._condition.notify()
            return QueueAdmission(dropped, dropped_pixels)

    def dequeue(self, timeout: float | None = None) -> QueueResult:
        """Return the oldest entry; None means timed out or drained closed."""
        with self._condition:
            if self._inflight is not None:
                raise RuntimeError(
                    "complete the in-flight record before dequeuing again"
                )
            deadline = None if timeout is None else monotonic() + timeout
            while not self._entries and not self._closed:
                remaining = None if deadline is None else deadline - monotonic()
                if remaining is not None and remaining <= 0:
                    return None
                self._condition.wait(remaining)
            if not self._entries:
                return None
            entry = self._entries.popleft()
            if entry.pixels is not None:
                self._waiting_pixels -= 1
            self._inflight = entry.record
            self._inflight_pixels = entry.pixels
            return RecordingEntry(entry.record, entry.pixels, entry.dropped)

    def complete(self, record: FrameRecord) -> memoryview | None:
        """Release pending accounting and return its payload slot to the pool.

        Appending the row is the caller's responsibility; queue completion does not
        claim an OS durability sync.
        """
        with self._condition:
            if self._inflight != record:
                raise RuntimeError(
                    "completed frame does not match the in-flight record"
                )
            completed_pixels = self._inflight_pixels
            self._inflight = None
            self._inflight_pixels = None
            self._condition.notify_all()
            return completed_pixels

    def close(self) -> None:
        """Reject new items and wake the consumer after already admitted items drain."""
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    @property
    def pending_records(self) -> int:
        with self._condition:
            return len(self._entries) + (self._inflight is not None)

    @property
    def waiting_pixels(self) -> int:
        with self._condition:
            return self._waiting_pixels
