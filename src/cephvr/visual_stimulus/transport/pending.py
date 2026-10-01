"""One renderer endpoint becomes available only after registered native launch."""

from __future__ import annotations

import asyncio

from google.protobuf.message import Message

from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.transport_deadlines import remaining_seconds

from .peers import Peer


class PendingPeer:
    def __init__(self) -> None:
        self.peer: Peer | None = None
        self.ready = asyncio.Event()

    def attach(self, peer: Peer) -> None:
        if self.peer is not None:
            raise RuntimeError("renderer endpoint already attached")
        self.peer = peer
        self.ready.set()

    async def call(
        self,
        method: str,
        request: Message,
        *,
        deadline_ns: int,
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> Message:
        async with asyncio.timeout(remaining_seconds(deadline_ns)):
            await self.ready.wait()
        if self.peer is None:
            raise RuntimeError("renderer endpoint missing")
        return await self.peer.call(
            method, request, deadline_ns=deadline_ns, metadata=metadata
        )

    async def command(
        self, method: str, request: Message, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        result = await self.call(method, request, deadline_ns=deadline_ns)
        if not isinstance(result, pb.CommandAdmission):
            raise TypeError("renderer command returned no admission")
        return result

    async def receipt(
        self, method: str, request: Message, *, deadline_ns: int
    ) -> pb.ReportReceipt:
        result = await self.call(method, request, deadline_ns=deadline_ns)
        if not isinstance(result, pb.ReportReceipt):
            raise TypeError("renderer returned no receipt")
        return result
