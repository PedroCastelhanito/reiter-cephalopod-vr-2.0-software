"""Public and private acquisition RPC endpoint lifecycle."""

from __future__ import annotations

from collections.abc import MutableMapping

import grpc

from cephvr.acquisition.coordinator.operations import CoordinatorOperations
from cephvr.acquisition.transport.admission import CommandAdmissionTransport
from cephvr.acquisition.transport.services import (
    AcquisitionBackendService,
    AcquisitionConfigurationService,
    AcquisitionCoordinatorService,
)
from cephvr.acquisition.v1 import services_pb2_grpc as acquisition_rpc
from cephvr.control.v1 import services_pb2_grpc as control_rpc
from cephvr.shared.commands import CommandLedger
from cephvr.shared.transport_deadlines import remaining_seconds


class AcquisitionServer:
    """Own one coordinator listener and its admitted command drain."""

    def __init__(
        self, server: grpc.aio.Server, admission: CommandAdmissionTransport
    ) -> None:
        self.server = server
        self.admission = admission
        self._closed = False

    async def close(self, *, deadline_ns: int) -> None:
        if self._closed:
            return
        try:
            await self.admission.close(deadline_ns)
        finally:
            await self.server.stop(grace=remaining_seconds(deadline_ns))
        self._closed = True


async def start_acquisition_server(
    operations: CoordinatorOperations,
    credentials: MutableMapping[tuple[str, str], str],
    ledger: CommandLedger,
    *,
    port: int,
    max_message_bytes: int,
    max_concurrent_rpcs: int,
) -> AcquisitionServer:
    """Bind only explicit IPv4 loopback and serve every existing acquisition RPC."""
    if not 0 < port <= 65535 or max_message_bytes <= 0:
        raise ValueError("invalid acquisition endpoint limits")
    if max_concurrent_rpcs <= 0:
        raise ValueError("acquisition RPC concurrency must be positive")
    server = grpc.aio.server(
        options=(
            ("grpc.max_receive_message_length", max_message_bytes),
            ("grpc.max_send_message_length", max_message_bytes),
        ),
        maximum_concurrent_rpcs=max_concurrent_rpcs,
    )
    admission = CommandAdmissionTransport(
        ledger, terminal_failure=operations.report_dispatch_failure
    )
    control_rpc.add_BackendServiceServicer_to_server(
        AcquisitionBackendService(operations, credentials, admission), server
    )  # type: ignore[no-untyped-call]
    control_rpc.add_AcquisitionConfigurationServiceServicer_to_server(
        AcquisitionConfigurationService(operations, credentials, admission), server
    )  # type: ignore[no-untyped-call]
    acquisition_rpc.add_AcquisitionCoordinatorServiceServicer_to_server(
        AcquisitionCoordinatorService(operations, credentials, admission), server
    )  # type: ignore[no-untyped-call]
    bound = server.add_insecure_port(f"127.0.0.1:{port}")
    if bound != port:
        raise RuntimeError("configured acquisition loopback port unavailable")
    try:
        await server.start()
    except BaseException:
        await server.stop(grace=0)
        raise
    return AcquisitionServer(server, admission)
