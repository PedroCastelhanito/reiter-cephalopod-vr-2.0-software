"""Typed unary Visual Stimulus peers; preserve the original absolute operation deadline."""

from __future__ import annotations

from typing import cast

import grpc
from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2_grpc as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.auth import Principal
from cephvr.shared.transport_deadlines import deadline_metadata, remaining_seconds
from cephvr.visual_stimulus.v1 import services_pb2_grpc as visual_stimulus_rpc


class Peer:
    def __init__(
        self, endpoint: str, principal: Principal, maximum: int, *, kind: str
    ) -> None:
        if not endpoint.startswith("127.0.0.1:") or maximum <= 0:
            raise ValueError("registered loopback endpoint and message bound required")
        self.channel = grpc.aio.insecure_channel(
            endpoint,
            options=(
                ("grpc.max_receive_message_length", maximum),
                ("grpc.max_send_message_length", maximum),
            ),
        )
        self.principal = principal
        self.stub = {
            "worker": visual_stimulus_rpc.VisualStimulusWorkerServiceStub,
            "coordinator": visual_stimulus_rpc.VisualStimulusCoordinatorServiceStub,
            "controller": rpc.ExperimentControllerServiceStub,
            "supervisor": rpc.SupervisorServiceStub,
        }[kind](self.channel)  # type: ignore[no-untyped-call]

    async def call(
        self,
        method: str,
        request: Message,
        *,
        deadline_ns: int,
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> Message:
        timeout = remaining_seconds(deadline_ns)
        if timeout <= 0:
            raise TimeoutError("original Visual Stimulus peer deadline expired")
        return cast(
            Message,
            await getattr(self.stub, method)(
                request,
                metadata=(
                    *self.principal.metadata(),
                    *metadata,
                    deadline_metadata(deadline_ns),
                ),
                timeout=timeout,
            ),
        )

    async def command(
        self, method: str, request: Message, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        result = await self.call(method, request, deadline_ns=deadline_ns)
        if not isinstance(result, pb.CommandAdmission):
            raise TypeError("Visual Stimulus peer returned no command admission")
        return result

    async def receipt(
        self, method: str, request: Message, *, deadline_ns: int
    ) -> pb.ReportReceipt:
        result = await self.call(method, request, deadline_ns=deadline_ns)
        if not isinstance(result, pb.ReportReceipt):
            raise TypeError("Visual Stimulus peer returned no report receipt")
        if result.result != pb.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError(
                f"{method}: {result.failure.code}: {result.failure.message}"
            )
        return result

    async def close(self) -> None:
        await self.channel.close()
