"""Authenticated outbound reports to the acquisition coordinator."""

from __future__ import annotations

from typing import Any, cast

import grpc

from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import services_pb2_grpc as rpc
from cephvr.control.v1 import services_pb2_grpc as control_rpc
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.auth import Principal
from cephvr.shared.transport_deadlines import deadline_metadata, remaining_seconds


class CoordinatorReportClient:
    """One worker-generation principal and existing unary report service."""

    def __init__(
        self,
        endpoint: str,
        principal: Principal,
        max_message_bytes: int,
        channel: grpc.aio.Channel | None = None,
    ) -> None:
        if max_message_bytes <= 0:
            raise ValueError("coordinator message limit must be positive")
        self._channel = channel or grpc.aio.insecure_channel(
            endpoint,
            options=(
                ("grpc.max_send_message_length", max_message_bytes),
                ("grpc.max_receive_message_length", max_message_bytes),
            ),
        )
        self._stub = rpc.AcquisitionCoordinatorServiceStub(self._channel)  # type: ignore[no-untyped-call]
        self._principal = principal

    async def report_operation(
        self, request: acq.WorkerOperationReport, *, deadline_ns: int
    ) -> control.ReportReceipt:
        return cast(
            control.ReportReceipt,
            await cast(Any, self._stub).ReportWorkerOperation(
                request,
                metadata=(*self._principal.metadata(), deadline_metadata(deadline_ns)),
                timeout=remaining_seconds(deadline_ns),
            ),
        )

    async def report_lifecycle(
        self, request: acq.WorkerLifecycleEvidence, *, deadline_ns: int
    ) -> control.ReportReceipt:
        return cast(
            control.ReportReceipt,
            await cast(Any, self._stub).ReportWorkerLifecycle(
                request,
                metadata=(*self._principal.metadata(), deadline_metadata(deadline_ns)),
                timeout=remaining_seconds(deadline_ns),
            ),
        )

    async def report_warnings(
        self, request: acq.WorkerWarningReport, *, deadline_ns: int
    ) -> control.ReportReceipt:
        return cast(
            control.ReportReceipt,
            await cast(Any, self._stub).ReportWorkerWarnings(
                request,
                metadata=(*self._principal.metadata(), deadline_metadata(deadline_ns)),
                timeout=remaining_seconds(deadline_ns),
            ),
        )

    async def report_heartbeat(
        self, request: control.HeartbeatReport, *, deadline_ns: int
    ) -> control.ReportReceipt:
        return cast(
            control.ReportReceipt,
            await cast(Any, self._stub).ReportWorkerHeartbeat(
                request,
                metadata=(*self._principal.metadata(), deadline_metadata(deadline_ns)),
                timeout=remaining_seconds(deadline_ns),
            ),
        )

    async def close(self) -> None:
        await self._channel.close()


class SupervisorErrorClient:
    """Direct worker-to-supervisor ErrorReport path required by E08."""

    def __init__(
        self,
        endpoint: str,
        principal: Principal,
        max_message_bytes: int,
        channel: grpc.aio.Channel | None = None,
    ) -> None:
        if max_message_bytes <= 0:
            raise ValueError("supervisor message limit must be positive")
        self._channel = channel or grpc.aio.insecure_channel(
            endpoint,
            options=(
                ("grpc.max_send_message_length", max_message_bytes),
                ("grpc.max_receive_message_length", max_message_bytes),
            ),
        )
        self._stub = control_rpc.SupervisorServiceStub(self._channel)  # type: ignore[no-untyped-call]
        self._principal = principal

    async def report_error(
        self, request: control.ErrorReport, *, deadline_ns: int
    ) -> control.ReportReceipt:
        return cast(
            control.ReportReceipt,
            await cast(Any, self._stub).ReportError(
                request,
                metadata=(*self._principal.metadata(), deadline_metadata(deadline_ns)),
                timeout=remaining_seconds(deadline_ns),
            ),
        )

    async def close(self) -> None:
        await self._channel.close()
