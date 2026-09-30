"""Confirm the worker's resolved loopback endpoint under its original launch."""

from __future__ import annotations

from uuid import uuid4

import grpc

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import services_pb2_grpc as rpc
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.auth import Principal
from cephvr.shared.clock import describe_host_clock
from cephvr.shared.transport_deadlines import deadline_metadata, remaining_seconds

from .state import WorkerBootstrap


class SupervisorEndpointRegistration:
    """One-use registration callback passed to `serve_registered_worker`."""

    def __init__(self, bootstrap: WorkerBootstrap) -> None:
        self._bootstrap = bootstrap
        self._channel: grpc.aio.Channel | None = None
        self._confirmed = False

    async def __call__(self, endpoint: str) -> None:
        if self._confirmed:
            raise RuntimeError("worker endpoint was already registered")
        if not endpoint or not _loopback_endpoint(endpoint):
            raise ValueError("worker endpoint must be a concrete loopback address")
        bootstrap = self._bootstrap
        self._channel = grpc.aio.insecure_channel(bootstrap.supervisor_endpoint)
        stub = rpc.SupervisorServiceStub(self._channel)  # type: ignore[no-untyped-call]
        request = wire.ConfirmLaunchRequest(
            command_id=str(uuid4()),
            launch_command_id=bootstrap.launch_command_id,
            owner=bootstrap.context.owner,
            child=bootstrap.context.worker,
            pid=bootstrap.pid,
            creation_time_100ns=bootstrap.creation_time_100ns,
            endpoint=endpoint,
        )
        clock = describe_host_clock()
        request.host_clock.CopyFrom(
            control.HostClockDescriptor(
                clock_id=clock.clock_id,
                implementation=clock.implementation,
                monotonic=clock.monotonic,
                adjustable=clock.adjustable,
                resolution_s=clock.resolution_s,
            )
        )
        principal = Principal(
            bootstrap.context.worker.role,
            bootstrap.context.worker.generation,
            bootstrap.worker_credential,
        )
        response = await stub.ConfirmLaunch(
            request,
            metadata=(
                *principal.metadata(),
                deadline_metadata(bootstrap.registration_deadline_ns),
            ),
            timeout=remaining_seconds(bootstrap.registration_deadline_ns),
        )
        if response.admission.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError(
                response.admission.failure.message
                if response.admission.HasField("failure")
                else "supervisor rejected worker endpoint registration"
            )
        if (
            not response.HasField("state")
            or response.state.endpoint != endpoint
            or response.state.plan.child != bootstrap.context.worker
            or response.state.phase != wire.LAUNCH_PHASE_OPERATIONAL
        ):
            raise RuntimeError(
                "supervisor did not retain the exact operational endpoint"
            )
        self._confirmed = True

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None


def _loopback_endpoint(endpoint: str) -> bool:
    host, separator, port = endpoint.rpartition(":")
    if not separator or not port.isdecimal() or not 0 < int(port) <= 65535:
        return False
    if host in {"127.0.0.1", "localhost", "[::1]"}:
        return True
    return False
