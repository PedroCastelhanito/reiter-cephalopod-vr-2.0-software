"""Bounded loopback Tracking listener with independently admitted safety commands."""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass

import grpc

from cephvr.control.v1 import services_pb2_grpc as rpc
from cephvr.shared.admission import CommandAdmissionTransport
from cephvr.shared.commands import CommandLedger
from cephvr.shared.credentials import CredentialStore
from cephvr.shared.transport_deadlines import remaining_seconds
from cephvr.tracking.diagnostic import TrackingDiagnostic
from cephvr.tracking.v1 import services_pb2_grpc as tracking_rpc

from .boundary import Boundary, Operations
from .services import BackendService, DiagnosticService, PreparationService


@dataclass
class Listener:
    server: grpc.aio.Server
    admission: CommandAdmissionTransport
    port: int

    async def close(self, deadline_ns: int) -> None:
        try:
            await self.admission.close(deadline_ns)
        finally:
            await self.server.stop(remaining_seconds(deadline_ns))


async def serve(
    operations: Operations,
    credentials: MutableMapping[tuple[str, str], str],
    ledger: CommandLedger,
    *,
    diagnostic: TrackingDiagnostic,
    port: int,
    max_message_bytes: int,
    viewer_credentials: CredentialStore,
    testing: bool = False,
) -> Listener:
    if not 0 <= port <= 65535 or port == 0 and not testing or max_message_bytes <= 0:
        raise ValueError("Tracking requires configured port and positive message limit")
    server = grpc.aio.server(
        options=(
            ("grpc.max_receive_message_length", max_message_bytes),
            ("grpc.max_send_message_length", max_message_bytes),
        ),
        maximum_concurrent_rpcs=128,
    )
    admission = CommandAdmissionTransport(
        ledger, terminal_failure=operations.failed_command
    )
    boundary = Boundary(operations, credentials, admission)
    rpc.add_BackendServiceServicer_to_server(BackendService(boundary), server)  # type: ignore[no-untyped-call]
    tracking_rpc.add_TrackingPreparationServiceServicer_to_server(
        PreparationService(boundary), server
    )  # type: ignore[no-untyped-call]
    tracking_rpc.add_TrackingDiagnosticServiceServicer_to_server(
        DiagnosticService(boundary, diagnostic, viewer_credentials), server
    )  # type: ignore[no-untyped-call]
    bound = server.add_insecure_port(f"127.0.0.1:{port}")
    if not bound or port and bound != port:
        raise RuntimeError("configured Tracking endpoint unavailable")
    await server.start()
    return Listener(server, admission, bound)
