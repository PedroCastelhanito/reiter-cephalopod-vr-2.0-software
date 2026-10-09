"""Bounded GL-owner mailbox with independent safety cancellation (V01/E08)."""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from functools import partial
from typing import Protocol

from google.protobuf.message import Message

from cephvr.shared.clock import host_time_ns
from cephvr.shared.deadlines import remaining_seconds


class Driver(Protocol):
    def execute(
        self, method: str, request: Message, deadline_ns: int
    ) -> Future[None] | None: ...
    def advance(self, now_ns: int) -> int | None: ...
    def fail(self, error: BaseException) -> None: ...


@dataclass
class Pending:
    method: str
    request: Message
    deadline_ns: int
    future: Future[None]


class RenderOwner:
    """Construct the graphics driver on its sole owning thread."""

    def __init__(
        self,
        factory: Callable[[threading.Event], Driver],
        *,
        clock: Callable[[], int] = host_time_ns,
        capacity: int = 64,
        safety_capacity: int = 16,
    ) -> None:
        if min(capacity, safety_capacity) <= 0:
            raise ValueError("positive render mailbox capacities required")
        self.factory, self.clock = factory, clock
        self.capacity, self.safety_capacity = capacity, safety_capacity
        self.cancelled = threading.Event()
        self.condition = threading.Condition()
        self.regular: deque[Pending] = deque()
        self.safety: deque[Pending] = deque()
        self.closed = False
        self.failure: BaseException | None = None
        self.last_progress_ns = self.clock()
        self.progress_required = True
        self.thread = threading.Thread(
            target=self._run, name="cephvr-visual-stimulus-gl-owner", daemon=True
        )
        self.thread.start()

    async def submit(self, method: str, request: Message, deadline_ns: int) -> None:
        from cephvr.visual_stimulus.transport.boundary import SAFETY

        future: Future[None] = Future()
        item = Pending(
            method,
            type(request).FromString(request.SerializeToString()),
            deadline_ns,
            future,
        )
        with self.condition:
            if self.closed or self.failure is not None:
                raise RuntimeError("GL owner unavailable") from self.failure
            target = self.safety if method in SAFETY else self.regular
            limit = self.safety_capacity if method in SAFETY else self.capacity
            if len(target) >= limit:
                raise RuntimeError("bounded GL command mailbox exhausted")
            if method in {"InterruptSession", "CancelSetup", "Cleanup", "Shutdown"}:
                self.cancelled.set()
            target.append(item)
            self.condition.notify()
        # Caller cancellation cannot revoke ownership of an admitted native operation.
        await asyncio.shield(asyncio.wrap_future(future))

    def cancel(self) -> None:
        """Wake a future-onset wait as soon as local safety fences activity."""
        self.cancelled.set()
        with self.condition:
            self.condition.notify()

    def _begin_progress(self) -> None:
        # An intentional Idle wait is not a stall. Start its next operation's
        # progress interval on wakeup, before entering any native/GL call.
        if not self.progress_required:
            self.last_progress_ns = self.clock()
        self.progress_required = True

    def _run(self) -> None:
        driver: Driver | None = None
        try:
            driver = self.factory(self.cancelled)
            while True:
                with self.condition:
                    item = (
                        self.safety.popleft()
                        if self.safety
                        else self.regular.popleft()
                        if self.regular
                        else None
                    )
                    if self.closed and item is None:
                        return
                if item is not None:
                    self._begin_progress()
                    try:
                        if self.clock() >= item.deadline_ns:
                            raise TimeoutError(
                                "render command missed its original deadline"
                            )
                        deferred = driver.execute(
                            item.method, item.request, item.deadline_ns
                        )
                        if deferred is None:
                            item.future.set_result(None)
                        else:
                            deferred.add_done_callback(
                                partial(_complete, target=item.future)
                            )
                    except BaseException as exc:
                        item.future.set_exception(exc)
                        driver.fail(exc)
                self._begin_progress()
                try:
                    due = driver.advance(self.clock())
                except Exception as exc:
                    self.cancelled.set()
                    driver.fail(exc)
                    # Give the same GL owner one immediate chance to establish Idle
                    # and start output finalization before declaring it unavailable.
                    due = driver.advance(self.clock())
                self.last_progress_ns = self.clock()
                self.progress_required = (
                    due is not None and due <= self.last_progress_ns
                )
                with self.condition:
                    if not self.regular and not self.safety and not self.closed:
                        timeout = (
                            None
                            if due is None
                            else remaining_seconds(due, clock=self.clock)
                        )
                        self.condition.wait(timeout)
        except BaseException as exc:
            self.failure = exc
            self.cancelled.set()
            if driver is not None:
                driver.fail(exc)
            with self.condition:
                for item in (*self.regular, *self.safety):
                    item.future.set_exception(exc)
                self.regular.clear()
                self.safety.clear()

    async def close(self, deadline_ns: int) -> None:
        with self.condition:
            self.closed = True
            self.condition.notify()
        await asyncio.to_thread(
            self.thread.join, remaining_seconds(deadline_ns, clock=self.clock)
        )
        if self.thread.is_alive():
            raise TimeoutError("GL owner has not released its thread/resources")


def _complete(source: Future[None], target: Future[None]) -> None:
    try:
        source.result()
        target.set_result(None)
    except BaseException as exc:
        target.set_exception(exc)
