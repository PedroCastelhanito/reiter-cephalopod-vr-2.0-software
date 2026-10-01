"""Bounded immutable report handoff off the GL thread (E08)."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from concurrent.futures import Future

from google.protobuf.message import Message

from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.clock import host_time_ns
from cephvr.visual_stimulus.coordinator.ports import PeerPort
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus


class ReportBridge:
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        coordinator: PeerPort,
        supervisor: PeerPort,
        *,
        failed: Callable[[BaseException], None],
        maximum_bytes: int,
        maximum_reports: int = 128,
    ) -> None:
        self.loop, self.coordinator, self.supervisor = loop, coordinator, supervisor
        self.failed = failed
        self.maximum_bytes, self.maximum_reports = maximum_bytes, maximum_reports
        self.pending: dict[Future[None], int] = {}
        self.lock = threading.Lock()
        self.retain_lifecycle: (
            Callable[[visual_stimulus.WorkerLifecycle, int], Awaitable[None]] | None
        ) = None
        self.observe_display: Callable[[pb.VisualStimulusDisplayView], None] | None = (
            None
        )
        self.catalogue = pb.HeartbeatReport(cleanup_resources_revision=0)

    async def _deliver(self, method: str, message: Message, deadline_ns: int) -> None:
        if (
            method == "ReportWorkerLifecycle"
            and isinstance(message, visual_stimulus.WorkerLifecycle)
            and self.retain_lifecycle is not None
        ):
            await self.retain_lifecycle(message, deadline_ns)
        else:
            if (
                isinstance(message, pb.VisualStimulusDisplayView)
                and self.observe_display is not None
            ):
                self.observe_display(message)
            if isinstance(message, pb.HeartbeatReport):
                self.catalogue.CopyFrom(message)
            peer = self.supervisor if method == "ReportError" else self.coordinator
            await peer.receipt(method, message, deadline_ns=deadline_ns)

    def _enqueue(self, method: str, message: Message, deadline_ns: int) -> Future[None]:
        data = message.SerializeToString(deterministic=True)
        snapshot = type(message).FromString(data)
        with self.lock:
            if (
                len(self.pending) >= self.maximum_reports
                or sum(self.pending.values()) + len(data) > self.maximum_bytes
            ):
                raise RuntimeError("bounded worker report handoff exhausted")
            future = asyncio.run_coroutine_threadsafe(
                self._deliver(method, snapshot, deadline_ns), self.loop
            )
            self.pending[future] = len(data)

        def done(result: Future[None]) -> None:
            with self.lock:
                self.pending.pop(result, None)
            try:
                result.result()
            except BaseException as exc:
                self.failed(exc)

        future.add_done_callback(done)
        return future

    def send(self, method: str, message: Message, deadline_ns: int) -> None:
        self._enqueue(method, message, deadline_ns)

    def confirm(self, method: str, message: Message, deadline_ns: int) -> None:
        self._enqueue(method, message, deadline_ns).result(
            max(0, (deadline_ns - host_time_ns()) / 1e9)
        )

    async def drain(self, deadline_ns: int) -> None:
        with self.lock:
            pending = tuple(self.pending)
        if pending:
            async with asyncio.timeout(max(0, (deadline_ns - host_time_ns()) / 1e9)):
                await asyncio.gather(*(asyncio.wrap_future(f) for f in pending))
