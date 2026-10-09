"""Bounded progress and stdin-stall deadlines for one FFmpeg child."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from cephvr.acquisition.recording.session_contracts import (
    EncoderProcess,
    RecordingFailure,
    RecordingQueue,
)


class EncoderProgressWatchdog:
    """Arm only while an ordered record is pending and retain progress history."""

    def __init__(
        self,
        encoder: EncoderProcess,
        queue: RecordingQueue,
        stall_timeout_ns: int,
        clock_ns: Callable[[], int],
    ) -> None:
        self.encoder = encoder
        self.queue = queue
        self.stall_timeout_ns = stall_timeout_ns
        self.clock_ns = clock_ns
        self._last_progress = -1
        self._last_progress_ns: int | None = None
        self._pending_started_ns: int | None = None
        self._first_input_ns: int | None = None
        self._active_input_work = False

    @contextmanager
    def active_input_work(self) -> Iterator[None]:
        """Keep the stall clock armed for bounded writes outside the source queue."""
        previous = self._active_input_work
        self._active_input_work = True
        failed = False
        try:
            self.check()
            yield
        except BaseException:
            failed = True
            raise
        finally:
            self._active_input_work = previous
            if not previous and not failed:
                self.check()

    def note_input_submitted(self) -> None:
        """Arm one fixed startup deadline after the first complete input packet."""
        if self._first_input_ns is None:
            self._first_input_ns = self.clock_ns()

    def check(self) -> None:
        if self.encoder.reader_error is not None:
            raise RecordingFailure(
                f"FFmpeg pipe reader failed: {self.encoder.reader_error}"
            )
        progress = self.encoder.progress_frame
        if progress is not None and progress > self._last_progress:
            self._last_progress = progress
            self._last_progress_ns = self.clock_ns()
        pending = bool(
            self._active_input_work
            or self.queue.pending_records
            or self.queue.waiting_pixels
        )
        now = self.clock_ns()
        if (
            self._first_input_ns is not None
            and not self.encoder.negotiated
            and now >= self._first_input_ns + self.stall_timeout_ns
        ):
            raise RecordingFailure(
                "FFmpeg did not report the initialized video formats before startup deadline"
            )
        if pending and self._pending_started_ns is None:
            self._pending_started_ns = now
        elif not pending:
            self._pending_started_ns = None
        if not pending or self._pending_started_ns is None:
            return
        base_ns = (
            max(self._pending_started_ns, self._last_progress_ns)
            if self._last_progress_ns is not None
            else self._pending_started_ns
        )
        if now - base_ns > self.stall_timeout_ns:
            raise RecordingFailure(
                "FFmpeg progress watchdog expired with recording work pending"
            )

    def write_deadline(self, finalization_deadline_ns: int) -> int:
        """Bound one frame write by pending-work stall and retained completion budget."""
        now = self.clock_ns()
        if self._pending_started_ns is None:
            self._pending_started_ns = now
        base_ns = max(
            self._pending_started_ns,
            self._last_progress_ns or self._pending_started_ns,
        )
        deadline_ns = min(
            base_ns + self.stall_timeout_ns,
            finalization_deadline_ns,
        )
        if self._first_input_ns is not None and not self.encoder.negotiated:
            deadline_ns = min(deadline_ns, self._first_input_ns + self.stall_timeout_ns)
        if now >= deadline_ns:
            raise RecordingFailure("FFmpeg stdin write budget already expired")
        return deadline_ns
