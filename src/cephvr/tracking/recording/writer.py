"""T19 bounded record admission; one file-owning writer thread and truthful closure."""

from __future__ import annotations

import os
import sys
import threading
from collections import deque
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import BinaryIO, Literal

from pydantic import BaseModel

from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.clock import host_time_ns
from cephvr.tracking.config.models.records import Completion, Header, TrackingRecord
from cephvr.tracking.recording.codec import encode_line
from cephvr.tracking.v1.recording_pb2 import TrackingRecordingSettings


class TrackingWriter:
    def __init__(
        self,
        path: Path,
        output_key: str,
        settings: TrackingRecordingSettings,
        *,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.path, self.output_key, self.settings, self.clock = (
            path,
            output_key,
            settings,
            clock,
        )
        self.condition = threading.Condition()
        self.queue: deque[tuple[TrackingRecord, int]] = deque()
        self.pending_count = 0
        self.pending_bytes = 0
        self.pending_since_ns: int | None = None
        self.last_append_ns: int | None = None
        self.last_sync_ns: int | None = None
        self.cutoff: int | None = None
        self.outcome: Literal["completed", "interrupted"] = "completed"
        self.failure: BaseException | None = None
        self.thread: threading.Thread | None = None
        self.closed = False
        self.handle: BinaryIO | None = None
        self.present = False
        self.sealed = False
        self.counts = {"pose": 0, "result": 0, "reset": 0, "discard": 0}
        self.sync_ns = int(Decimal(str(settings.sync_interval_s)) * 1_000_000_000)
        self.progress_ns = int(
            Decimal(str(settings.write_progress_timeout_s)) * 1_000_000_000
        )
        self.reserved = 4 * (settings.max_record_bytes + 1) * 2
        if (
            settings.max_pending_records < 5
            or settings.max_pending_bytes <= self.reserved
        ):
            raise ValueError(
                "writer needs producer capacity beyond four reserved bookkeeping lines"
            )

    def start(self, header: Header) -> None:
        if self.thread is not None or self.clock() < header.trial_start_host_ns:
            raise ValueError("writer start requires released onset and a fresh owner")
        if not self.try_admit(TrackingRecord(record=header), bookkeeping=True):
            raise RuntimeError("cannot admit tracking header")
        self.thread = threading.Thread(
            target=self._run, name="tracking-recording", daemon=False
        )
        self.thread.start()

    def try_admit(self, record: TrackingRecord, *, bookkeeping: bool = False) -> bool:
        # Reserve both immutable Python payload and the maximum serialization copy.
        size = _retained_bytes(record, self.settings.max_pending_bytes) + 2 * (
            self.settings.max_record_bytes + 1
        )
        with self.condition:
            count_limit = self.settings.max_pending_records - (0 if bookkeeping else 4)
            byte_limit = self.settings.max_pending_bytes - (
                0 if bookkeeping else self.reserved
            )
            if (
                self.sealed
                or self.failure is not None
                or self.pending_count >= count_limit
                or self.pending_bytes + size > byte_limit
            ):
                return False
            self.pending_count += 1
            self.pending_bytes += size
            if self.pending_since_ns is None:
                self.pending_since_ns = self.clock()
            self.queue.append((record, size))
            self.condition.notify()
            return True

    def seal(self, cutoff_host_ns: int, *, interrupted: bool = False) -> None:
        with self.condition:
            if self.cutoff is not None and self.cutoff != cutoff_host_ns:
                raise ValueError("writer cutoff cannot change")
            self.cutoff = cutoff_host_ns
            self.outcome = "interrupted" if interrupted else "completed"
            self.sealed = True
            self.condition.notify()

    def stalled(self, now: int) -> bool:
        with self.condition:
            return (
                self.pending_since_ns is not None
                and now - self.pending_since_ns >= self.progress_ns
            )

    def finalize(self, deadline_host_ns: int) -> pb.OutputResult:
        if self.thread is not None:
            self.thread.join(max(0, (deadline_host_ns - self.clock()) / 1e9))
        success = self.closed and self.failure is None
        return pb.OutputResult(
            output_key=self.output_key,
            path=str(self.path),
            artifact_present=self.present,
            closure=pb.OUTPUT_CLOSURE_CLOSED
            if success
            else pb.OUTPUT_CLOSURE_FAILED
            if self.closed
            else pb.OUTPUT_CLOSURE_UNCONFIRMED,
            failure=None
            if success
            else pb.Failure(
                code="TRACKING_WRITER",
                message=str(self.failure or "writer ownership remains active"),
            ),
        )

    def _run(self) -> None:
        handle: BinaryIO | None = None
        dirty = False
        try:
            handle = self.path.open("xb", buffering=0)
            self.handle = handle
            self.present = True
            self.last_sync_ns = self.clock()
            while True:
                with self.condition:
                    while not self.queue and not self.sealed:
                        remaining = (
                            (self.last_sync_ns + self.sync_ns - self.clock()) / 1e9
                            if dirty
                            else None
                        )
                        if remaining is not None and remaining <= 0:
                            break
                        self.condition.wait(remaining)
                    item = self.queue.popleft() if self.queue else None
                    finish = self.sealed and item is None
                if item is not None:
                    record, size = item
                    self._append(
                        handle,
                        encode_line(record, max_bytes=self.settings.max_record_bytes),
                    )
                    dirty = True
                    if record.record.kind in self.counts:
                        self.counts[record.record.kind] += 1
                    with self.condition:
                        self.pending_count -= 1
                        self.pending_bytes -= size
                        self.last_append_ns = self.clock()
                        self.pending_since_ns = self.last_append_ns
                if finish:
                    assert self.cutoff is not None
                    completion = Completion(
                        kind="completion",
                        cutoff_host_ns=self.cutoff,
                        outcome=self.outcome,
                        pose_records=self.counts["pose"],
                        result_records=self.counts["result"],
                        reset_records=self.counts["reset"],
                        discard_records=self.counts["discard"],
                    )
                    self._append(
                        handle,
                        encode_line(
                            TrackingRecord(record=completion),
                            max_bytes=self.settings.max_record_bytes,
                        ),
                    )
                    dirty = True
                if dirty and (
                    finish or self.clock() - self.last_sync_ns >= self.sync_ns
                ):
                    os.fsync(handle.fileno())
                    with self.condition:
                        self.last_sync_ns = self.clock()
                        self.pending_since_ns = (
                            self.last_sync_ns if self.pending_count else None
                        )
                    dirty = False
                if finish:
                    break
        except BaseException as exc:
            self.failure = exc
        finally:
            if handle is not None:
                try:
                    handle.close()
                    self.handle = None
                    self.closed = True
                except BaseException as exc:
                    self.failure = exc
            elif not self.present:
                self.closed = True

    @staticmethod
    def _append(handle: BinaryIO, data: bytes) -> None:
        view = memoryview(data)
        while view:
            count = handle.write(view)
            if count is None or count <= 0:
                raise OSError("tracking append made no progress")
            view = view[count:]


def _retained_bytes(value: object, limit: int) -> int:
    total = sys.getsizeof(value)
    children = (
        tuple(value.__dict__.values())
        if isinstance(value, BaseModel)
        else value
        if isinstance(value, tuple)
        else ()
    )
    for child in children:
        total += _retained_bytes(child, limit - total)
        if total > limit:
            break
    return total
