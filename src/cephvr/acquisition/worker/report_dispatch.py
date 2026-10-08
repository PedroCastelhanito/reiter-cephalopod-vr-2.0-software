"""Bounded thread-to-async report handoff for acquisition workers (A02)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from concurrent.futures import Future
from threading import BoundedSemaphore, RLock
from typing import Any

from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.transport_deadlines import remaining_seconds

from .reports import CoordinatorReportClient
from .state import WorkerState


class WorkerReportDispatcher:
    """Bound pending RPCs; completion updates only the authoritative worker flag."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        state: WorkerState,
        reports: CoordinatorReportClient,
        capacity: int,
        failure: Callable[[str], None],
    ) -> None:
        if capacity <= 0:
            raise ValueError("worker report dispatch capacity must be positive")
        self.loop = loop
        self.state = state
        self.reports = reports
        self.failure = failure
        self._slots = BoundedSemaphore(capacity)
        self._lock = RLock()
        self._accepting = True
        self._pending: set[Future[control.ReportReceipt]] = set()

    def dispatch(self, awaitable: Coroutine[Any, Any, control.ReportReceipt]) -> None:
        with self._lock:
            if not self._accepting:
                awaitable.close()
                with self.state.lock:
                    self.state.interrupted = True
                self.failure("worker report dispatcher is draining")
                raise RuntimeError("worker report dispatcher is draining")
            if not self._slots.acquire(blocking=False):
                awaitable.close()
                with self.state.lock:
                    self.state.interrupted = True
                self.failure("bounded worker report queue is full")
                raise RuntimeError("bounded worker report queue is full")
            try:
                future: Future[control.ReportReceipt] = (
                    asyncio.run_coroutine_threadsafe(
                        awaitable,
                        self.loop,
                    )
                )
            except BaseException:
                self._slots.release()
                raise
            self._pending.add(future)
            future.add_done_callback(self._completed)

    async def drain(self, deadline_ns: int) -> bool:
        """Stop admission and await every accepted report through its retained bound."""
        with self._lock:
            self._accepting = False
            pending = tuple(self._pending)
        if not pending:
            return True
        wrapped = tuple(asyncio.wrap_future(future) for future in pending)
        _done, unfinished = await asyncio.wait(
            wrapped, timeout=remaining_seconds(deadline_ns)
        )
        if _done:
            await asyncio.gather(*_done, return_exceptions=True)
        if unfinished:
            with self.state.lock:
                self.state.interrupted = True
            return False
        return True

    def operation(self, report: acq.WorkerOperationReport, deadline_ns: int) -> None:
        self.dispatch(self.reports.report_operation(report, deadline_ns=deadline_ns))

    def lifecycle(
        self, evidence: acq.WorkerLifecycleEvidence, deadline_ns: int
    ) -> None:
        self.dispatch(self.reports.report_lifecycle(evidence, deadline_ns=deadline_ns))

    def _completed(self, future: Future[control.ReportReceipt]) -> None:
        try:
            receipt = future.result()
            if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                with self.state.lock:
                    self.state.interrupted = True
                self.failure(
                    f"worker report rejected: {receipt.failure.code}: "
                    f"{receipt.failure.message}"
                )
        except BaseException as exc:
            with self.state.lock:
                self.state.interrupted = True
            self.failure(f"worker report failed: {exc}")
        finally:
            with self._lock:
                self._pending.discard(future)
            self._slots.release()
