"""Backend-neutral nonblocking writer over a supervised process stdin pipe."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class OverlappedEncoderProcess(Protocol):
    def begin_write(self, data: memoryview, *, deadline_ns: int) -> None: ...
    def poll_write(self) -> int | None: ...
    def close_stdin(self, *, deadline_ns: int) -> None: ...


class WindowsEncoderInputAdapter:
    """Poll one overlapped write at a time without blocking the owning thread."""

    def __init__(
        self,
        process: OverlappedEncoderProcess | None = None,
        *,
        write_deadline_ns: Callable[[], int],
        close_deadline_ns: Callable[[], int],
    ) -> None:
        self.process = process
        self.write_deadline_ns = write_deadline_ns
        self.close_deadline_ns = close_deadline_ns
        self._pending = False

    def bind_process(self, process: OverlappedEncoderProcess) -> None:
        if self.process is not None or self._pending:
            raise RuntimeError("encoder process binding is immutable")
        self.process = process

    def write_chunk(self, data: memoryview) -> int:
        if self.process is None:
            raise RuntimeError("registered FFmpeg child is not ready")
        if self._pending:
            transferred = self.process.poll_write()
            if transferred is None:
                return 0
            self._pending = False
            return transferred
        self.process.begin_write(data, deadline_ns=self.write_deadline_ns())
        self._pending = True
        return 0

    def close_input(self) -> None:
        if self.process is None:
            raise RuntimeError("registered FFmpeg child is not ready")
        if self._pending:
            raise RuntimeError(
                "cannot close FFmpeg stdin with a pending overlapped write"
            )
        self.process.close_stdin(deadline_ns=self.close_deadline_ns())
