"""Bounded immutable report handoff off the GL thread (E08)."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from concurrent.futures import Future

from google.protobuf.message import Message

from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.clock import host_time_ns
from cephvr.shared.deadlines import remaining_seconds
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
        self._optional: Future[None] | None = None
        self.retain_lifecycle: (
            Callable[[visual_stimulus.WorkerLifecycle, int], Awaitable[None]] | None
        ) = None
        self.observe_display: Callable[[pb.VisualStimulusDisplayView], None] | None = (
            None
        )
        self.catalogue = pb.HeartbeatReport(
            cleanup_resources_revision=0,
            session_phase=pb.SESSION_PHASE_CONFIGURATION,
        )

    def retire_session(
        self,
        session: pb.SessionContext,
        cleanup_revision: int,
        released_resources: bool,
    ) -> None:
        """Clear only the acknowledged session's cached heartbeat catalogue."""
        with self.lock:
            work = self.catalogue.work
            kind = work.WhichOneof("work")
            cached_session = (
                work.session
                if kind == "session"
                else work.trial.session
                if kind == "trial"
                else None
            )
            if cached_session != session:
                return
            changed = bool(self.catalogue.cleanup_resources) or released_resources
            revision = cleanup_revision + int(released_resources)
            if changed:
                revision = max(revision, self.catalogue.cleanup_resources_revision + 1)
            else:
                revision = max(revision, self.catalogue.cleanup_resources_revision)
            self.catalogue.cleanup_resources.clear()
            self.catalogue.cleanup_resources_revision = revision
            self.catalogue.ClearField("work")
            self.catalogue.ClearField("trial_phase")
            self.catalogue.session_phase = pb.SESSION_PHASE_CONFIGURATION
            self.catalogue.continuing_functions.clear()

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
            started_ns = host_time_ns()
            try:
                await peer.receipt(method, message, deadline_ns=deadline_ns)
            except Exception as exc:
                raise RuntimeError(
                    f"{method} receipt failed: "
                    f"elapsed_ms={(host_time_ns() - started_ns) / 1e6:.3f}, "
                    f"budget_ms={(deadline_ns - started_ns) / 1e6:.3f}, "
                    f"bytes={message.ByteSize()}: {exc}"
                ) from exc

    def _enqueue(
        self, method: str, message: Message, deadline_ns: int, *, required: bool = True
    ) -> Future[None]:
        data = message.SerializeToString(deterministic=True)
        snapshot = type(message).FromString(data)

        async def deliver() -> None:
            try:
                await self._deliver(method, snapshot, deadline_ns)
            except Exception:
                if required:
                    raise

        with self.lock:
            if not required and (
                (self._optional is not None and not self._optional.done())
                or len(self.pending) >= self.maximum_reports
                or sum(self.pending.values()) + len(data) > self.maximum_bytes
            ):
                dropped: Future[None] = Future()
                dropped.set_result(None)
                return dropped
            if (
                len(self.pending) >= self.maximum_reports
                or sum(self.pending.values()) + len(data) > self.maximum_bytes
            ):
                raise RuntimeError("bounded worker report handoff exhausted")
            future = asyncio.run_coroutine_threadsafe(deliver(), self.loop)
            self.pending[future] = len(data)
            if not required:
                self._optional = future

        def done(result: Future[None]) -> None:
            with self.lock:
                self.pending.pop(result, None)
            try:
                result.result()
            except BaseException as exc:
                self.failed(exc)

        future.add_done_callback(done)
        return future

    def send(
        self, method: str, message: Message, deadline_ns: int, *, required: bool = True
    ) -> None:
        self._enqueue(method, message, deadline_ns, required=required)

    def confirm(self, method: str, message: Message, deadline_ns: int) -> None:
        self._enqueue(method, message, deadline_ns).result(
            remaining_seconds(deadline_ns, clock=host_time_ns)
        )

    async def drain(self, deadline_ns: int) -> None:
        with self.lock:
            pending = tuple(self.pending)
        if pending:
            async with asyncio.timeout(
                remaining_seconds(deadline_ns, clock=host_time_ns)
            ):
                await asyncio.gather(*(asyncio.wrap_future(f) for f in pending))
