"""One bounded CPU worker; newer requests cancel obsolete work without touching Qt."""

from collections.abc import Callable
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Any

from .errors import describe_error


class Cancelled(Exception):
    pass


class Jobs:
    def __init__(self) -> None:
        self.pending: Queue[Any] = Queue(maxsize=1)
        self.results: Queue[Any] = Queue(maxsize=1)
        self.cancel = Event()
        self.closed = Event()
        self.serial = 0
        # True from submission until the worker is idle and its result is queued.
        self.working = False
        self.lock = Lock()
        Thread(target=self._run, daemon=True, name="stimulus-authoring").start()

    def submit(self, operation: Callable[[Callable[[], None]], Any]) -> int:
        with self.lock:
            self.cancel.set()
            self.cancel = Event()
            self.serial += 1
            try:
                self.pending.get_nowait()
            except Empty:
                pass
            self.pending.put_nowait((self.serial, self.cancel, operation))
            self.working = True
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
                # A finished value is always queued: a cancelled export may have
                # published already, and the consumer discards obsolete serials.
                self._publish((serial, operation(check), None))
            except Cancelled:
                pass
            except Exception as error:
                self._publish((serial, None, describe_error(error)))
            with self.lock:
                if self.pending.empty():
                    self.working = False
