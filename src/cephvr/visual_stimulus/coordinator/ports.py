"""Small process communication contracts, independent of gRPC adapters."""

from __future__ import annotations

from typing import Protocol

from google.protobuf.message import Message

from cephvr.control.v1 import types_pb2 as pb


class PeerPort(Protocol):
    async def call(
        self,
        method: str,
        request: Message,
        *,
        deadline_ns: int,
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> Message: ...
    async def command(
        self, method: str, request: Message, *, deadline_ns: int
    ) -> pb.CommandAdmission: ...
    async def receipt(
        self, method: str, request: Message, *, deadline_ns: int
    ) -> pb.ReportReceipt: ...
