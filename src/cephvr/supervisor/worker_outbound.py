"""Direct authenticated RPCs to exact acquisition worker launches (A02/E08)."""

from __future__ import annotations

import asyncio
from typing import cast

import grpc

from cephvr.acquisition.identity import camera_for_process_role
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import services_pb2_grpc as acq_rpc
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.clock import host_time_ns
from cephvr.shared.transport_deadlines import deadline_metadata, remaining_seconds
from cephvr.supervisor.registry import LaunchError, LaunchRegistry


class GrpcWorkerOutbound:
    """One channel per exact registered generation and endpoint."""

    MAX_CHANNELS = 64

    def __init__(
        self,
        *,
        supervisor: types.ProcessIdentity,
        token: str,
        max_message_bytes: int,
    ) -> None:
        self.metadata = (
            ("x-cephvr-role", supervisor.role),
            ("x-cephvr-generation", supervisor.generation),
            ("x-cephvr-token", token),
        )
        self.options = [
            ("grpc.max_send_message_length", max_message_bytes),
            ("grpc.max_receive_message_length", max_message_bytes),
        ]
        self.channels: dict[tuple[str, str, str], grpc.aio.Channel] = {}
        self._registry: LaunchRegistry | None = None

    def bind_registry(self, registry: LaunchRegistry) -> None:
        """Current launch state is re-read from here before any channel use."""
        self._registry = registry

    def _stub(
        self, launch: wire.LaunchState, target: acq.WorkerContext
    ) -> acq_rpc.AcquisitionWorkerServiceStub:
        plan = launch.plan
        try:
            expected_camera = camera_for_process_role(plan.child.role)
        except ValueError:
            expected_camera = None
        if (
            plan.owner.role != "acquisition"
            or launch.phase
            not in (wire.LAUNCH_PHASE_OPERATIONAL, wire.LAUNCH_PHASE_CLEANUP_REQUIRED)
            or not launch.HasField("pid")
            or not launch.HasField("endpoint")
            or expected_camera is None
        ):
            raise RuntimeError("camera worker launch is not registered and reachable")
        if (
            target.worker != plan.child
            or target.owner != plan.owner
            or target.camera != expected_camera
            or not self._work_matches_launch(plan, target)
        ):
            raise RuntimeError("worker context differs from its exact launch")
        if self._registry is None:
            raise RuntimeError("worker outbound has no launch registry")
        try:
            current = self._registry.refresh(plan.command_id)
        except LaunchError as exc:
            raise RuntimeError("camera worker launch is no longer registered") from exc
        if (
            current.phase
            not in (wire.LAUNCH_PHASE_OPERATIONAL, wire.LAUNCH_PHASE_CLEANUP_REQUIRED)
            or current.endpoint != launch.endpoint
        ):
            raise RuntimeError("camera worker launch changed since it was resolved")
        channel_key = (launch.endpoint, plan.child.role, plan.child.generation)
        channel = self.channels.get(channel_key)
        if channel is None:
            if len(self.channels) >= self.MAX_CHANNELS:
                raise RuntimeError("registered worker channel capacity exhausted")
            channel = grpc.aio.insecure_channel(launch.endpoint, options=self.options)
            self.channels[channel_key] = channel
        return acq_rpc.AcquisitionWorkerServiceStub(channel)  # type: ignore[no-untyped-call]

    @staticmethod
    def _work_matches_launch(
        plan: wire.PlanLaunchRequest, target: acq.WorkerContext
    ) -> bool:
        kind = target.work.WhichOneof("work")
        if not plan.HasField("work"):
            return kind is None
        if plan.work.WhichOneof("work") == "session":
            if kind == "session":
                return target.work.session == plan.work.session
            if kind == "trial":
                return target.work.trial.session == plan.work.session
            return False
        return target.work == plan.work

    def _metadata(self, deadline_ns: int) -> tuple[tuple[str, str], ...]:
        if deadline_ns <= host_time_ns():
            raise TimeoutError("registered worker command deadline expired")
        return (*self.metadata, deadline_metadata(deadline_ns))

    @staticmethod
    def _timeout(deadline_ns: int) -> float:
        timeout = remaining_seconds(deadline_ns)
        if timeout <= 0:
            raise TimeoutError("registered worker command deadline expired")
        return timeout

    async def interrupt(
        self,
        launch: wire.LaunchState,
        request: acq.WorkerInterrupt,
        *,
        deadline_ns: int,
    ) -> types.CommandAdmission:
        return cast(
            types.CommandAdmission,
            await self._stub(launch, request.command.target).InterruptSession(
                request,
                metadata=self._metadata(deadline_ns),
                timeout=self._timeout(deadline_ns),
            ),
        )

    async def cleanup(
        self,
        launch: wire.LaunchState,
        request: acq.WorkerCommand,
        *,
        deadline_ns: int,
    ) -> types.CommandAdmission:
        return cast(
            types.CommandAdmission,
            await self._stub(launch, request.target).Cleanup(
                request,
                metadata=self._metadata(deadline_ns),
                timeout=self._timeout(deadline_ns),
            ),
        )

    async def shutdown(
        self,
        launch: wire.LaunchState,
        request: acq.WorkerCommand,
        *,
        deadline_ns: int,
    ) -> types.CommandAdmission:
        return cast(
            types.CommandAdmission,
            await self._stub(launch, request.target).Shutdown(
                request,
                metadata=self._metadata(deadline_ns),
                timeout=self._timeout(deadline_ns),
            ),
        )

    async def get_state(
        self,
        launch: wire.LaunchState,
        request: acq.WorkerQuery,
        *,
        deadline_ns: int,
    ) -> acq.WorkerState:
        return cast(
            acq.WorkerState,
            await self._stub(launch, request.target).GetState(
                request,
                metadata=self._metadata(deadline_ns),
                timeout=self._timeout(deadline_ns),
            ),
        )

    async def get_retained_result(
        self,
        launch: wire.LaunchState,
        request: acq.WorkerRetainedResultQuery,
        *,
        deadline_ns: int,
    ) -> acq.WorkerRetainedResult:
        return cast(
            acq.WorkerRetainedResult,
            await self._stub(launch, request.query.target).GetRetainedResult(
                request,
                metadata=self._metadata(deadline_ns),
                timeout=self._timeout(deadline_ns),
            ),
        )

    async def close(self) -> None:
        channels = tuple(self.channels.values())
        self.channels.clear()
        await asyncio.gather(*(channel.close() for channel in channels))

    async def retire_generation(self, role: str, generation: str) -> None:
        """Close cached channels only after the exact worker launch is released."""
        matches = [key for key in self.channels if key[1:] == (role, generation)]
        channels = [self.channels.pop(key) for key in matches]
        await asyncio.gather(*(channel.close() for channel in channels))
