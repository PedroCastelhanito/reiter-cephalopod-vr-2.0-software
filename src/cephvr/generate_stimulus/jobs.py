"""One bounded CPU worker; newer requests cancel obsolete work without touching Qt."""

from collections.abc import Callable
from queue import Empty, Queue
from threading import Event, Thread
from typing import Any


class Cancelled(Exception):
    pass


class Jobs:
    def __init__(self) -> None:
        self.pending: Queue[Any] = Queue(maxsize=1)
        self.results: Queue[Any] = Queue(maxsize=1)
        self.cancel = Event()
        self.closed = Event()
        self.serial = 0
        Thread(target=self._run, daemon=True, name="stimulus-authoring").start()

    def submit(self, operation: Callable[[Callable[[], None]], Any]) -> int:
        self.cancel.set()
        self.cancel = Event()
        self.serial += 1
        try:
            self.pending.get_nowait()
        except Empty:
            pass
        self.pending.put_nowait((self.serial, self.cancel, operation))
        return self.serial

    def close(self) -> None:
        self.closed.set()
        self.cancel.set()

    def _publish(self, result: Any) -> None:
        try:
            self.results.get_nowait()
        except Empty:
            pass
        self.results.put_nowait(result)

    def _run(self) -> None:
        while not self.closed.is_set():
            try:
                serial, cancel, operation = self.pending.get(timeout=0.1)
            except Empty:
                continue

            def check(cancel: Event = cancel) -> None:
                if cancel.is_set() or self.closed.is_set():
                    raise Cancelled()

            try:
                check()
                value = operation(check)
                check()
                self._publish((serial, value, None))
            except Cancelled:
                continue
            except Exception as error:
                self._publish((serial, None, str(error)))
