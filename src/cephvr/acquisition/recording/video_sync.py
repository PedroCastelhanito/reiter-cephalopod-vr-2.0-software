"""Bounded single-flight video flush ownership, independent of encoder feeding."""

from __future__ import annotations

import threading
from collections.abc import Callable

from cephvr.acquisition.recording.session_contracts import VideoSync


class VideoSyncFailure(RuntimeError):
    """A completed flush failed; its handle may close, durability is unconfirmed."""


class PeriodicVideoSync:
    """Retain one exact handle and at most one flush until observed completion."""

    def __init__(self, native: VideoSync, clock_ns: Callable[[], int]) -> None:
        self.native = native
        self.clock_ns = clock_ns
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None
        self._fenced = False
        self._final_started = False
        self._closed = False
        self._original_deadline_ns: int | None = None
        self.late = False

    @property
    def file_identity(self) -> object:
        return self.native.file_identity

    def poll(self) -> bool:
        if self._error is not None:
            raise VideoSyncFailure("video synchronization failed") from self._error
        return self._thread is None or not self._thread.is_alive()

    def request(self) -> bool:
        """Submit one due flush; overdue demand stays with the caller, not a queue."""
        if self._fenced or self._closed:
            raise RuntimeError("video synchronization is fenced")
        if not self.poll():
            return False
        self._start()
        return True

    def _start(self) -> None:
        def flush() -> None:
            try:
                self.native.sync()
            except BaseException as exc:
                self._error = exc

        self._thread = threading.Thread(
            target=flush, name="recording-video-sync", daemon=True
        )
        try:
            self._thread.start()
        except BaseException as exc:
            self._thread = None
            self._error = exc
            raise VideoSyncFailure("video synchronization could not start") from exc

    def sync(self) -> None:
        raise RuntimeError("owned video synchronization requires an absolute deadline")

    def sync_until(self, deadline_ns: int) -> None:
        """Fence periodic work, join it, then flush final encoder bytes exactly once."""
        self._fenced = True
        if self._original_deadline_ns is None:
            self._original_deadline_ns = deadline_ns
        self._join(deadline_ns)
        self.poll()
        if not self._final_started:
            if self.clock_ns() >= deadline_ns:
                self.late = True
                raise TimeoutError("final video synchronization deadline expired")
            self._final_started = True
            self._start()
        self._join(deadline_ns)
        self.poll()
        self.late |= self.clock_ns() > self._original_deadline_ns

    def _join(self, deadline_ns: int) -> None:
        if self._thread is None:
            return
        self._thread.join(max(0, deadline_ns - self.clock_ns()) / 1e9)
        if self._thread.is_alive():
            self.late = True
            raise TimeoutError("video synchronization remains pending at deadline")

    def close(self) -> None:
        self._fenced = True
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("pending video synchronization retains its handle")
        if not self._closed:
            self.native.close()
            self._closed = True


def sync_video_until(sync: VideoSync, deadline_ns: int) -> bool:
    """Use bounded production ownership; primitive injection stays test-compatible."""
    if isinstance(sync, PeriodicVideoSync):
        sync.sync_until(deadline_ns)
        return sync.late
    sync.sync()
    return False
