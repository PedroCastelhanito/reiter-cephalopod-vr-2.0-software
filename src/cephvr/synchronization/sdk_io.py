"""One serialized worker for every controller-owned SpikeGLX SDK call."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")


class SpikeGLXIOBusy(RuntimeError):
    """The previous native call is still running or its outcome is unobserved."""


class SpikeGLXIOOwner:
    """Serialize diagnostic and lifecycle calls; a timeout never frees ownership."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="cephvr-spikeglx-sdk"
        )
        self._lock = threading.Lock()
        self._pending: Future[Any] | None = None
        self._closed = False

    async def run(self, operation: Callable[[], T], timeout_s: float) -> T:
        if timeout_s <= 0:
            raise TimeoutError("SpikeGLX native-call deadline elapsed")
        with self._lock:
            if self._closed:
                raise RuntimeError("SpikeGLX SDK owner is closed")
            if self._pending is not None:
                if not self._pending.done():
                    raise SpikeGLXIOBusy("previous SpikeGLX SDK call remains in flight")
                self._pending = None
            future = self._executor.submit(operation)
            self._pending = future

        def release(completed: Future[Any]) -> None:
            with self._lock:
                if self._pending is completed:
                    self._pending = None

        future.add_done_callback(release)
        wrapped = asyncio.wrap_future(future)
        try:
            return await asyncio.wait_for(asyncio.shield(wrapped), timeout_s)
        except TimeoutError:
            # Keep _pending until the native invocation actually returns.
            raise

    def close(self, wait: bool = False) -> None:
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=False)
