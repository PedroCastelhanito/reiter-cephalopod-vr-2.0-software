"""One recording-thread owner for evidence-first capture, stdin, and closure."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cephvr.shared.encoder_io import WindowsEncoderInputAdapter  # noqa: F401
from cephvr.visual_stimulus.config.models.evidence_model import (
    ArtifactRef,
    EvidenceRecord,
    Header,
    Record,
)

from .capture import (
    CaptureReservation,
    RecordingCounts,
    RecordingWorker,
)
from .evidence import EvidenceWriter

__all__ = ["RecordingSession", "WindowsEncoderInputAdapter"]


@dataclass(frozen=True)
class RecordingCloseResult:
    counts: RecordingCounts
    evidence_closed: bool


class RecordingSession:
    """Own one writer thread; rendering callers only submit bounded immutable data.

    The supplied finalizer runs on this same recording thread after admitted frame
    input drains. It closes/waits/synchronizes the registered FFmpeg process and
    returns the already-serialized EncoderOutcome and Completion JSON lines.
    """

    def __init__(
        self,
        *,
        worker: RecordingWorker,
        evidence: EvidenceWriter,
        evidence_path: Path,
        recipe_path: Path,
        max_queued_evidence_bytes: int,
        finalizer: Callable[[RecordingCounts], tuple[bytes, bytes]],
        startup: Callable[[], None] | None = None,
        sync_interval_ns: int = 0,
        periodic_sync: Callable[[], None] | None = None,
        failure_cleanup: Callable[[], None] | None = None,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        if max_queued_evidence_bytes <= 0:
            raise ValueError("queued evidence byte limit must be positive")
        self.worker = worker
        self.evidence = evidence
        self.evidence_path = evidence_path
        self.recipe_path = recipe_path
        self.max_queued_evidence_bytes = max_queued_evidence_bytes
        self.finalizer = finalizer
        self.startup = startup
        if sync_interval_ns < 0:
            raise ValueError("record sync interval cannot be negative")
        self.sync_interval_ns = sync_interval_ns
        self.periodic_sync = periodic_sync
        self.failure_cleanup = failure_cleanup
        self.clock_ns = clock_ns
        self._condition = threading.Condition()
        self._lines: deque[tuple[bytes | Callable[[], Record], int]] = deque()
        self._line_bytes = 0
        self._header_factory: Callable[[], tuple[Header, ArtifactRef]] | None = None
        self._closing = False
        self._done = False
        self._error: BaseException | None = None
        self._result: RecordingCloseResult | None = None
        self._thread = threading.Thread(
            target=self._run, name="visual-stimulus-recording", daemon=True
        )
        self._thread.start()

    def publish_header(self, header: Header, published_recipe: ArtifactRef) -> None:
        self.publish_header_factory(lambda: (header, published_recipe))

    def publish_header_factory(
        self, factory: Callable[[], tuple[Header, ArtifactRef]]
    ) -> None:
        with self._condition:
            if self._header_factory is not None:
                raise RuntimeError("recording trial Header is already published")
            if self._closing:
                raise RuntimeError("recording session is closing")
            self._header_factory = factory
            self._condition.notify_all()

    def enqueue_evidence_json(self, line: bytes) -> None:
        if not line.endswith(b"\n") or b"\n" in line[:-1]:
            raise ValueError("evidence must be one newline-terminated JSON record")
        with self._condition:
            if self._closing:
                raise RuntimeError("recording evidence is sealed at cutoff")
            pending_total = self._line_bytes + self.evidence.pending_bytes
            if len(line) > self.max_queued_evidence_bytes - pending_total:
                raise BufferError(
                    "required Visual Stimulus evidence exceeded its bounded queue"
                )
            owned = bytes(line)
            self._lines.append((owned, len(owned)))
            self._line_bytes += len(line)
            self._condition.notify_all()

    def enqueue_evidence_factory(
        self,
        factory: Callable[[], Record],
        *,
        reserved_bytes: int,
    ) -> None:
        """Defer model creation and JSON serialization to the recording thread."""
        if reserved_bytes <= 0:
            raise ValueError("evidence line reservation must be positive")
        with self._condition:
            if self._closing:
                raise RuntimeError("evidence cutoff is sealed")
            pending_total = self._line_bytes + self.evidence.pending_bytes
            if reserved_bytes > self.max_queued_evidence_bytes - pending_total:
                raise BufferError(
                    "required Visual Stimulus evidence exceeded evidence_pending_bytes"
                )
            self._lines.append((factory, reserved_bytes))
            self._line_bytes += reserved_bytes
            self._condition.notify_all()

    def enqueue_terminal_evidence_factory(
        self,
        factory: Callable[[], Record],
        *,
        reserved_bytes: int,
    ) -> None:
        """Allow the recording owner to report an admitted write after cutoff seal."""
        if threading.current_thread() is not self._thread:
            raise RuntimeError(
                "terminal evidence may only be appended by its recording owner"
            )
        if reserved_bytes <= 0:
            raise ValueError("evidence line reservation must be positive")
        with self._condition:
            pending_total = self._line_bytes + self.evidence.pending_bytes
            if reserved_bytes > self.max_queued_evidence_bytes - pending_total:
                raise BufferError(
                    "required Visual Stimulus evidence exceeded evidence_pending_bytes"
                )
            self._lines.append((factory, reserved_bytes))
            self._line_bytes += reserved_bytes
            self._condition.notify_all()

    def try_reserve_capture(self, group_id: int) -> CaptureReservation | None:
        with self._condition:
            if self._closing:
                raise RuntimeError("capture admission is sealed at cutoff")
        return self.worker.try_reserve(group_id)

    def complete_capture(
        self,
        reservation: CaptureReservation,
        *,
        width: int,
        height: int,
        pixel_format: str,
        pixels: bytes | bytearray | memoryview,
    ) -> None:
        self.worker.complete_capture(
            reservation,
            width=width,
            height=height,
            pixel_format=pixel_format,
            pixels=pixels,
        )
        with self._condition:
            self._condition.notify_all()

    def cancel_capture(self, reservation: CaptureReservation) -> None:
        self.worker.cancel_reservation(reservation)
        with self._condition:
            self._condition.notify_all()

    def seal_at_cutoff(self) -> None:
        with self._condition:
            self._closing = True
            self._condition.notify_all()

    def begin_finish(self, *, cutoff_ns: int, deadline_ns: int) -> None:
        """Seal admissions without joining the recording thread on the GL owner."""
        if cutoff_ns < 0 or deadline_ns < cutoff_ns:
            raise ValueError("recording cutoff/deadline are invalid")
        self.seal_at_cutoff()

    def begin_cancel(self, *, deadline_ns: int) -> None:
        """Seal admissions for interruption; bounded closure continues in background."""
        if deadline_ns < 0:
            raise ValueError("recording cancellation deadline is invalid")
        self.seal_at_cutoff()

    def poll_finished(self) -> RecordingCloseResult | None:
        """Return closure only after the recorder has finalized all owned outputs."""
        with self._condition:
            if not self._done:
                return None
            error, result = self._error, self._result
        if self._thread.is_alive():
            return None
        if error is not None:
            raise RuntimeError(
                f"Visual Stimulus recording thread failed: {error}"
            ) from error
        if result is None:
            raise RuntimeError(
                "Visual Stimulus recording thread exited without a closure report"
            )
        return result

    def finish(self, *, deadline_ns: int) -> RecordingCloseResult:
        self.seal_at_cutoff()
        while self._thread.is_alive():
            remaining = deadline_ns - self.clock_ns()
            if remaining <= 0:
                raise TimeoutError(
                    "Visual Stimulus recording did not close before its original deadline"
                )
            self._thread.join(min(remaining / 1_000_000_000, 0.05))
        if self._error is not None:
            raise RuntimeError(
                f"Visual Stimulus recording thread failed: {self._error}"
            ) from self._error
        if self._result is None:
            raise RuntimeError(
                "Visual Stimulus recording thread exited without a closure report"
            )
        return self._result

    def _run(self) -> None:
        try:
            if self.startup is not None:
                self.startup()
            header_factory: Callable[[], tuple[Header, ArtifactRef]] | None = None
            while header_factory is None:
                with self._condition:
                    self._condition.wait_for(
                        lambda: self._header_factory is not None or self._closing,
                        timeout=0.05,
                    )
                    header_factory = self._header_factory
                    if header_factory is None and self._closing:
                        if self.failure_cleanup is not None:
                            self.failure_cleanup()
                        self._result = RecordingCloseResult(
                            self.worker.counts(), evidence_closed=False
                        )
                        self._done = True
                        return
            header, receipt = header_factory()
            if header.recipe != receipt:
                raise ValueError(
                    "Header does not match the coordinator recipe publication receipt"
                )
            self.evidence.open_after_recipe(self.evidence_path, header, receipt)
            last_sync_ns = self.clock_ns()
            while True:
                queued: tuple[bytes | Callable[[], Record], int] | None = None
                with self._condition:
                    if self._lines:
                        queued = self._lines.popleft()
                if queued is not None:
                    source, reservation = queued
                    line = (
                        source
                        if isinstance(source, bytes)
                        else EvidenceWriter._encode(EvidenceRecord(payload=source()))
                    )
                    if len(line) > reservation:
                        raise BufferError(
                            "evidence record exceeded its reserved line size"
                        )
                    with self._condition:
                        self.evidence.enqueue_json(line)
                        self._line_bytes -= reservation
                    self.evidence.write_pending()
                    continue
                if self.worker.drain_once():
                    continue
                now_ns = self.clock_ns()
                if (
                    self.sync_interval_ns
                    and now_ns - last_sync_ns >= self.sync_interval_ns
                ):
                    self.evidence.write_pending(sync=True)
                    if self.periodic_sync is not None:
                        self.periodic_sync()
                    last_sync_ns = now_ns
                with self._condition:
                    closing = self._closing
                if closing:
                    counts = self.worker.counts()
                    if counts.unresolved_capture_count:
                        # A nonblocking stdin write may still be owned by Windows.
                        # Keep polling it until it completes or its original deadline
                        # makes the adapter fail and E06 can reconcile the resource.
                        with self._condition:
                            self._condition.wait(timeout=0.005)
                        continue
                    self.worker.finish_input()
                    encoder_line, completion_line = self.finalizer(counts)
                    self.evidence.enqueue_json(encoder_line)
                    self.evidence.enqueue_json(completion_line)
                    self.evidence.write_pending(sync=True)
                    self.evidence.close(sync=True)
                    self._result = RecordingCloseResult(counts, True)
                    self._done = True
                    return
                with self._condition:
                    self._condition.wait(timeout=0.005)
        except BaseException as exc:
            if self.failure_cleanup is not None:
                try:
                    self.failure_cleanup()
                except BaseException:
                    pass
            try:
                self.evidence.close(sync=True)
            except BaseException:
                pass
            self._error = exc
            self._done = True
