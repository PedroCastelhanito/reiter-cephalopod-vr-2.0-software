"""Confirm an operational backend endpoint under its existing supervisor launch."""

from __future__ import annotations

from typing import cast
from uuid import uuid4

import grpc

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import services_pb2_grpc as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.auth import Principal
from cephvr.shared.backend_bootstrap import BackendBootstrap
from cephvr.shared.clock import describe_host_clock


async def register_backend_endpoint(bootstrap: BackendBootstrap) -> None:
    """Complete the OS-confirmed launch before any backend-owned child launch."""
    endpoint = f"127.0.0.1:{bootstrap.endpoint_port}"
    clock = describe_host_clock()
    request = wire.ConfirmLaunchRequest(
        command_id=str(uuid4()),
        launch_command_id=bootstrap.launch_command_id,
        owner=bootstrap.supervisor,
        child=bootstrap.identity,
        pid=bootstrap.pid,
        creation_time_100ns=bootstrap.creation_time_100ns,
        endpoint=endpoint,
        host_clock=pb.HostClockDescriptor(
            clock_id=clock.clock_id,
            implementation=clock.implementation,
            monotonic=clock.monotonic,
            adjustable=clock.adjustable,
            resolution_s=clock.resolution_s,
        ),
    )
    principal = Principal(
        bootstrap.identity.role, bootstrap.identity.generation, bootstrap.token
    )
    channel = grpc.aio.insecure_channel(
        f"127.0.0.1:{bootstrap.supervisor_port}",
        options=(
            ("grpc.max_send_message_length", bootstrap.max_message_bytes),
            ("grpc.max_receive_message_length", bootstrap.max_message_bytes),
        ),
    )
    try:
        response = await stub_call(
            channel, request, principal, bootstrap.health_silence_ns
        )
    finally:
        await channel.close()
    if (
        response.admission.result != pb.COMMAND_RESULT_ACCEPTED
        or response.state.phase != wire.LAUNCH_PHASE_OPERATIONAL
        or response.state.endpoint != endpoint
        or response.state.plan.child != bootstrap.identity
    ):
        raise RuntimeError("supervisor did not confirm the exact backend endpoint")


async def stub_call(
    channel: grpc.aio.Channel,
    request: wire.ConfirmLaunchRequest,
    principal: Principal,
    silence_ns: int,
) -> wire.LaunchReceipt:
    stub = rpc.SupervisorServiceStub(channel)  # type: ignore[no-untyped-call]
    return cast(
        wire.LaunchReceipt,
        await stub.ConfirmLaunch(
            request,
            metadata=principal.metadata(),
            timeout=silence_ns / 1e9,
        ),
    )
