"""Register a private worker endpoint before enabling camera lifecycle operations."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping

import grpc

from cephvr.acquisition.v1 import services_pb2_grpc as rpc
from cephvr.shared.clock import host_time_ns
from cephvr.shared.transport_deadlines import remaining_seconds

from .owner import SerializedCameraOwner
from .service import AcquisitionWorkerService
from .state import WorkerState

RegisterEndpoint = Callable[[str], Awaitable[None]]


async def serve_registered_worker(
    endpoint: str,
    state: WorkerState,
    owner: SerializedCameraOwner,
    peer_tokens: Mapping[str, tuple[str, str]],
    register_endpoint: RegisterEndpoint,
    *,
    max_message_bytes: int,
    max_concurrent_rpcs: int,
    teardown_budget_ns: int,
    shutdown_requested: asyncio.Event,
    shutdown_deadline_ns: Callable[[], int | None],
) -> None:
    """Listen, register the exact endpoint, then accept work and start the owner."""
    if max_message_bytes <= 0 or max_concurrent_rpcs <= 0 or teardown_budget_ns <= 0:
        raise ValueError("worker gRPC limits must be positive")
    server = grpc.aio.server(
        options=(
            ("grpc.max_send_message_length", max_message_bytes),
            ("grpc.max_receive_message_length", max_message_bytes),
        ),
        maximum_concurrent_rpcs=max_concurrent_rpcs,
    )
    rpc.add_AcquisitionWorkerServiceServicer_to_server(
        AcquisitionWorkerService(state, owner, peer_tokens), server
    )  # type: ignore[no-untyped-call]
    port = server.add_insecure_port(endpoint)
    if port == 0:
        raise RuntimeError("worker gRPC endpoint could not bind")
    host, separator, _requested_port = endpoint.rpartition(":")
    if not separator:
        raise ValueError("worker endpoint must include a TCP port")
    bound_endpoint = f"{host}:{port}"
    await server.start()
    owner_started = False
    owner_stopped = False
    try:
        await register_endpoint(bound_endpoint)
        with state.lock:
            state.registered = True
        owner.start()
        owner_started = True
        server_wait = asyncio.create_task(server.wait_for_termination())
        shutdown_wait = asyncio.create_task(shutdown_requested.wait())
        done, pending = await asyncio.wait(
            (server_wait, shutdown_wait), return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        if shutdown_wait in done and shutdown_wait.result():
            deadline = shutdown_deadline_ns()
            if deadline is None:
                raise RuntimeError("worker shutdown has no retained original deadline")
            stopped = await asyncio.to_thread(owner.stop, remaining_seconds(deadline))
            if not stopped:
                raise RuntimeError("camera owner did not stop within shutdown deadline")
            owner_stopped = True
            await server.stop(grace=remaining_seconds(deadline))
    finally:
        if owner_started and not owner_stopped:
            deadline = shutdown_deadline_ns()
            if deadline is None:
                deadline = host_time_ns() + teardown_budget_ns
            stopped = await asyncio.to_thread(owner.stop, remaining_seconds(deadline))
            if not stopped:
                raise RuntimeError("camera owner remains active after server shutdown")
            owner_stopped = True
        with state.lock:
            state.registered = False
        await server.stop(grace=0)
