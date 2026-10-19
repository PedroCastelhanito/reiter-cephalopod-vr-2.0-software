"""Serialize HighGUI and native window operations on one process-local UI thread."""

import queue
import threading
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any, TypeVar

from cephvr.platform.windows.window_coordinates import physical_coordinates

_T = TypeVar("_T")


class WindowThread:
    def __init__(self) -> None:
        self._calls: queue.Queue[tuple[Callable[[], Any], Future[Any]]] = queue.Queue()
        self._start_lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def call(self, operation: Callable[[], _T]) -> _T:
        with self._start_lock:
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._run, name="preview-windows", daemon=True
                )
                self._thread.start()
        future: Future[_T] = Future()
        self._calls.put((operation, future))
        return future.result()

    def _run(self) -> None:
        while True:
            operation, future = self._calls.get()
            try:
                with physical_coordinates():
                    result = operation()
                future.set_result(result)
            except BaseException as exc:
                future.set_exception(exc)


window_thread = WindowThread()
