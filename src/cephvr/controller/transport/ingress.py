"""Bounded report admission and single-loop delivery (E05/E08)."""

from __future__ import annotations

import asyncio
from typing import Protocol, TypeAlias, cast

from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.receipts import rejected_receipt
from cephvr.shared.ingress import BoundedEventIngress, IngressOverload


class ReportSink(Protocol):
    async def report_lifecycle(
        self, request: pb.LifecycleReport, ingress_ns: int
    ) -> pb.ReportReceipt: ...

    async def report_data_preparation(
        self, request: svc.DataPreparationReport, ingress_ns: int
    ) -> pb.ReportReceipt: ...

    async def report_acquisition_resolution(
        self, request: svc.AcquisitionResolutionReport, ingress_ns: int
    ) -> pb.ReportReceipt: ...

    async def report_projection(
        self, kind: str, request: Message, ingress_ns: int
    ) -> pb.ReportReceipt: ...

    async def report_interruption(
        self, request: svc.InterruptionReport
    ) -> pb.ReportReceipt: ...

    def ingress_exhausted(self, reason: str) -> None: ...


ReportEvent: TypeAlias = tuple[str, Message, int, asyncio.Future[pb.ReportReceipt]]


class BoundedReportIngress:
    """Admit reports with interruption priority and retain observed arrival times."""

    def __init__(
        self,
        sink: ReportSink,
        *,
        max_pending_events: int,
        max_pending_payload_bytes: int,
        max_message_bytes: int,
    ) -> None:
        self._sink = sink
        self._queue: BoundedEventIngress[ReportEvent] = BoundedEventIngress(
            max_pending_events,
            max_pending_payload_bytes,
            max_interruption_payload_bytes=max_message_bytes,
        )
        self._ready = asyncio.Event()
        self._active: asyncio.Future[pb.ReportReceipt] | None = None
        self._closed = False
        self._disposed = False
        self._task = asyncio.create_task(self._drain())

    def stop_accepting(self) -> None:
        self._closed = True

    async def _drain(self) -> None:
        while True:
            await self._ready.wait()
            while (item := self._queue.take()) is not None:
                kind, request, ingress_ns, future = item.event
                self._active = future
                try:
                    if kind == "lifecycle":
                        result = await self._sink.report_lifecycle(
                            cast(pb.LifecycleReport, request), ingress_ns
                        )
                    elif kind == "preparation":
                        result = await self._sink.report_data_preparation(
                            cast(svc.DataPreparationReport, request), ingress_ns
                        )
                    elif kind == "resolution":
                        result = await self._sink.report_acquisition_resolution(
                            cast(svc.AcquisitionResolutionReport, request), ingress_ns
                        )
                    elif kind.startswith("projection:"):
                        result = await self._sink.report_projection(
                            kind.removeprefix("projection:"), request, ingress_ns
                        )
                    else:
                        result = await self._sink.report_interruption(
                            cast(svc.InterruptionReport, request)
                        )
                except Exception as exc:
                    result = rejected_receipt("INTERNAL", str(exc))
                if not future.done():
                    future.set_result(result)
                self._active = None
            self._ready.clear()

    async def enqueue(
        self, kind: str, request: Message, ingress_ns: int
    ) -> pb.ReportReceipt:
        if self._closed:
            return rejected_receipt("SHUTDOWN", "controller service is closing")
        future: asyncio.Future[pb.ReportReceipt] = (
            asyncio.get_running_loop().create_future()
        )
        serialized = request.SerializeToString(deterministic=True)
        try:
            event = (kind, request, ingress_ns, future)
            if kind == "interruption":
                fresh = self._queue.put_interruption(serialized, event)
                if not fresh:
                    return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
            else:
                accepted = self._queue.put(
                    serialized,
                    event,
                    essential=kind in {"lifecycle", "preparation", "resolution"},
                    ingress_ns=ingress_ns,
                )
                if not accepted:
                    return rejected_receipt(
                        "OVERLOAD", "controller report ingress full"
                    )
        except IngressOverload as exc:
            self._sink.ingress_exhausted(
                f"essential controller ingress exhausted: {exc}"
            )
            return rejected_receipt("OVERLOAD", str(exc))
        self._ready.set()
        return await future

    async def aclose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        self._closed = True
        closing = rejected_receipt(
            "SHUTDOWN", "controller service closed before report processing"
        )
        while (item := self._queue.take()) is not None:
            future = item.event[3]
            if not future.done():
                future.set_result(closing)
        if self._active is not None and not self._active.done():
            self._active.set_result(closing)
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
