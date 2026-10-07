"""Authenticated direct transport for one bounded Tracking diagnostic frame."""

from __future__ import annotations

from typing import Any, cast

import grpc

from cephvr.client.session import ClientError, HeadlessClient
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.auth import Principal
from cephvr.tracking.v1 import services_pb2_grpc as tracking_transport


async def fetch_tracking_diagnostic_frame(
    client: HeadlessClient,
    principal: Principal,
    options: dict[str, Any],
    *,
    connection_epoch: int,
    max_message_bytes: int,
) -> tuple[int, str, bytes]:
    """Fetch a frame only for the exact active controller-registered diagnostic."""
    state = client.snapshot
    if not state.HasField("tracking_diagnostic"):
        raise ClientError("Tracking diagnostic state is unavailable.")
    diagnostic = state.tracking_diagnostic
    expected = (
        int(options["expected_revision"]),
        str(options["diagnostic_id"]),
        str(options["preview_run_id"]),
        str(options["tracking_endpoint"]),
        str(options["tracking_generation"]),
    )
    actual = (
        diagnostic.configuration_revision,
        diagnostic.diagnostic_id,
        diagnostic.preview_run_id,
        diagnostic.tracking_endpoint,
        diagnostic.tracking_process.generation
        if diagnostic.HasField("tracking_process")
        else "",
    )
    if (
        expected != actual
        or expected[0] != state.configuration.revision
        or not diagnostic.active
        or not diagnostic.HasField("tracking_process")
        or diagnostic.tracking_process.role != "tracking"
    ):
        raise ClientError("Tracking diagnostic viewer request is stale.")
    query = rpc.TrackingDiagnosticQuery(
        client_id=principal.generation,
        controller_generation=state.controller_generation,
        configuration_revision=expected[0],
        diagnostic_id=expected[1],
        preview_run_id=expected[2],
        viewer=pb.ProcessIdentity(role="gui", generation=principal.generation),
    )
    identity = (connection_epoch, state.controller_generation)
    async with grpc.aio.insecure_channel(
        expected[3],
        options=(
            ("grpc.max_receive_message_length", max_message_bytes),
            ("grpc.max_send_message_length", max_message_bytes),
        ),
    ) as channel:
        stub_constructor = cast(Any, tracking_transport.TrackingDiagnosticServiceStub)
        stub = stub_constructor(channel)
        frame = await stub.GetLatestDiagnosticFrame(
            query,
            metadata=principal.metadata(),
            timeout=min(2.0, client.rpc_timeout_s),
        )
    if (
        frame.diagnostic_id != expected[1]
        or frame.configuration_revision != expected[0]
        or frame.preview_run_id != expected[2]
    ):
        raise ClientError("Tracking diagnostic returned a mismatched frame.")
    return identity[0], identity[1], frame.SerializeToString()
