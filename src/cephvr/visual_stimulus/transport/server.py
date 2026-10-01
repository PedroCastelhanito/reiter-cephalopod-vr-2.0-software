"""Bounded loopback listeners for the two Visual Stimulus processes (V01/E08)."""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass

import grpc

from cephvr.control.v1 import services_pb2_grpc as rpc
from cephvr.shared.admission import CommandAdmissionTransport
from cephvr.shared.commands import CommandLedger
from cephvr.shared.transport_deadlines import remaining_seconds
from cephvr.visual_stimulus.v1 import services_pb2_grpc as visual_stimulus_rpc

from .boundary import Boundary, Operations
from .services import (
    BackendService,
    ConfigurationService,
    CoordinatorService,
    WorkerService,
)


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
    port: int,
    max_message_bytes: int,
    worker: bool = False,
    testing: bool = False,
) -> Listener:
    if (
        not 0 <= port <= 65535
        or (port == 0 and not (worker or testing))
        or max_message_bytes <= 0
    ):
        raise ValueError(
            "Visual Stimulus listener requires its configured port and positive message bound"
        )
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
    boundary = Boundary(operations, credentials, admission, worker=worker)
    if worker:
        visual_stimulus_rpc.add_VisualStimulusWorkerServiceServicer_to_server(
            WorkerService(boundary), server
        )  # type: ignore[no-untyped-call]
    else:
        rpc.add_BackendServiceServicer_to_server(BackendService(boundary), server)  # type: ignore[no-untyped-call]
        rpc.add_VisualStimulusConfigurationServiceServicer_to_server(
            ConfigurationService(boundary), server
        )  # type: ignore[no-untyped-call]
        visual_stimulus_rpc.add_VisualStimulusCoordinatorServiceServicer_to_server(
            CoordinatorService(boundary), server
        )  # type: ignore[no-untyped-call]
    bound = server.add_insecure_port(f"127.0.0.1:{port}")
    if not bound or (port and bound != port):
        raise RuntimeError("configured Visual Stimulus port unavailable")
    await server.start()
    return Listener(server, admission, bound)
