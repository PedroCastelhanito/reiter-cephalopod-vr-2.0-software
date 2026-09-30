"""Fixed-size private pixel buffers for recording and consumer working copies (A03)."""

from __future__ import annotations

from collections import deque
from threading import Lock


class PixelPoolError(RuntimeError):
    """A pixel buffer is not available or has an invalid ownership transition."""


class PixelBufferPool:
    """Preallocates known-size images and offers capture-thread nonblocking checkout."""

    def __init__(self, payload_bytes: int, capacity: int) -> None:
        if payload_bytes <= 0 or capacity <= 0:
            raise ValueError("pixel payload size and pool capacity must be positive")
        self.payload_bytes = payload_bytes
        self.capacity = capacity
        self._buffers = tuple(bytearray(payload_bytes) for _ in range(capacity))
        self._free: deque[int] = deque(range(capacity))
        self._checked_out: set[int] = set()
        self._lock = Lock()
        self._closed = False

    def acquire_nowait(self) -> memoryview:
        with self._lock:
            if self._closed:
                raise PixelPoolError("pixel pool is closed")
            if not self._free:
                raise PixelPoolError("prepared pixel pool exhausted")
            index = self._free.popleft()
            self._checked_out.add(index)
            return memoryview(self._buffers[index])

    def release(self, pixels: memoryview) -> None:
        if pixels.readonly or pixels.nbytes != self.payload_bytes:
            raise PixelPoolError("released pixel view has incompatible size or access")
        with self._lock:
            if self._closed:
                raise PixelPoolError("cannot release into a closed pixel pool")
            index = next(
                (
                    candidate
                    for candidate in self._checked_out
                    if pixels.obj is self._buffers[candidate]
                ),
                None,
            )
            if index is None:
                raise PixelPoolError("pixel buffer is not checked out from this pool")
            self._checked_out.remove(index)
            self._free.append(index)

    def close(self) -> None:
        with self._lock:
            if self._checked_out:
                raise PixelPoolError("cannot close while pixel buffers remain in use")
            self._closed = True
