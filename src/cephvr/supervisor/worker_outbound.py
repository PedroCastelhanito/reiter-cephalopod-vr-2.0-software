"""Direct authenticated RPCs to exact camera and renderer launches (A02/V01/E08)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import grpc

from cephvr.acquisition.identity import camera_for_process_role
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import services_pb2_grpc as acq_rpc
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.clock import host_time_ns
from cephvr.shared.transport_deadlines import deadline_metadata, remaining_seconds
from cephvr.supervisor.registry import LIVE_PHASES, LaunchError, LaunchRegistry
from cephvr.supervisor.worker_context import launch_work_matches
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus
from cephvr.visual_stimulus.v1 import services_pb2_grpc as visual_stimulus_rpc

_Reply = TypeVar("_Reply")


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

    @staticmethod
    def _reachable(launch: wire.LaunchState) -> bool:
        return (
            launch.phase in LIVE_PHASES
            and launch.HasField("pid")
            and launch.HasField("endpoint")
        )

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
            or not self._reachable(launch)
            or expected_camera is None
        ):
            raise RuntimeError("camera worker launch is not registered and reachable")
        if (
            target.worker != plan.child
            or target.owner != plan.owner
            or target.camera != expected_camera
            or not launch_work_matches(plan, target.work)
        ):
            raise RuntimeError("worker context differs from its exact launch")
        channel = self._channel(launch, "camera worker")
        return acq_rpc.AcquisitionWorkerServiceStub(channel)  # type: ignore[no-untyped-call]

    def _channel(self, launch: wire.LaunchState, label: str) -> grpc.aio.Channel:
        """Revalidate the launch before using even an already cached channel."""
        if self._registry is None:
            raise RuntimeError("worker outbound has no launch registry")
        try:
            current = self._registry.refresh(launch.plan.command_id)
        except LaunchError as exc:
            raise RuntimeError(f"{label} launch is no longer registered") from exc
        if current.phase not in LIVE_PHASES or current.endpoint != launch.endpoint:
            raise RuntimeError(f"{label} launch changed since it was resolved")
        channel_key = (
            launch.endpoint,
            launch.plan.child.role,
            launch.plan.child.generation,
        )
        channel = self.channels.get(channel_key)
        if channel is None:
            if len(self.channels) >= self.MAX_CHANNELS:
                raise RuntimeError("registered worker channel capacity exhausted")
            channel = grpc.aio.insecure_channel(launch.endpoint, options=self.options)
            self.channels[channel_key] = channel
        return channel

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

    async def _call(
        self,
        rpc: Callable[..., Awaitable[_Reply]],
        request: object,
        deadline_ns: int,
    ) -> _Reply:
        return await rpc(
            request,
            metadata=self._metadata(deadline_ns),
            timeout=self._timeout(deadline_ns),
        )

    async def interrupt_worker(
        self,
        launch: wire.LaunchState,
        request: acq.WorkerInterrupt,
        *,
        deadline_ns: int,
    ) -> types.CommandAdmission:
        return await self._call(
            self._stub(launch, request.command.target).InterruptSession,
            request,
            deadline_ns,
        )

    async def cleanup_worker(
        self,
        launch: wire.LaunchState,
        request: acq.WorkerCommand,
        *,
        deadline_ns: int,
    ) -> types.CommandAdmission:
        return await self._call(
            self._stub(launch, request.target).Cleanup, request, deadline_ns
        )

    async def shutdown_worker(
        self,
        launch: wire.LaunchState,
        request: acq.WorkerCommand,
        *,
        deadline_ns: int,
    ) -> types.CommandAdmission:
        return await self._call(
            self._stub(launch, request.target).Shutdown, request, deadline_ns
        )

    async def get_worker_state(
        self,
        launch: wire.LaunchState,
        request: acq.WorkerQuery,
        *,
        deadline_ns: int,
    ) -> acq.WorkerState:
        return await self._call(
            self._stub(launch, request.target).GetState, request, deadline_ns
        )

    async def get_worker_retained_result(
        self,
        launch: wire.LaunchState,
        request: acq.WorkerRetainedResultQuery,
        *,
        deadline_ns: int,
    ) -> acq.WorkerRetainedResult:
        return await self._call(
            self._stub(launch, request.query.target).GetRetainedResult,
            request,
            deadline_ns,
        )

    async def close(self) -> None:
        channels = tuple(self.channels.values())
        self.channels.clear()
        await asyncio.gather(*(channel.close() for channel in channels))

    def _visual_stimulus_stub(
        self, launch: wire.LaunchState, target: visual_stimulus.WorkerContext
    ) -> visual_stimulus_rpc.VisualStimulusWorkerServiceStub:
        plan = launch.plan
        if (
            plan.owner.role != "visual_stimulus"
            or plan.child.role != "visual_stimulus_renderer"
            or not self._reachable(launch)
        ):
            raise RuntimeError(
                "Visual Stimulus renderer launch is not registered and reachable"
            )
        if target.worker != plan.child or target.owner != plan.owner:
            raise RuntimeError(
                "Visual Stimulus worker context differs from its exact launch"
            )
        # V19's persistent renderer has no launch scope; its current work is
        # reconciled by VisualStimulusWorkerControl and validated by the renderer itself.
        if plan.HasField("work") and not launch_work_matches(plan, target.work):
            raise RuntimeError(
                "Visual Stimulus worker work differs from its exact launch"
            )
        channel = self._channel(launch, "Visual Stimulus renderer")
        return visual_stimulus_rpc.VisualStimulusWorkerServiceStub(channel)  # type: ignore[no-untyped-call]

    async def interrupt_visual_stimulus_worker(
        self,
        launch: wire.LaunchState,
        request: visual_stimulus.WorkerStop,
        *,
        deadline_ns: int,
    ) -> types.CommandAdmission:
        return await self._call(
            self._visual_stimulus_stub(launch, request.command.target).InterruptSession,
            request,
            deadline_ns,
        )

    async def cleanup_visual_stimulus_worker(
        self,
        launch: wire.LaunchState,
        request: visual_stimulus.WorkerCommand,
        *,
        deadline_ns: int,
    ) -> types.CommandAdmission:
        return await self._call(
            self._visual_stimulus_stub(launch, request.target).Cleanup,
            request,
            deadline_ns,
        )

    async def shutdown_visual_stimulus_worker(
        self,
        launch: wire.LaunchState,
        request: visual_stimulus.WorkerCommand,
        *,
        deadline_ns: int,
    ) -> types.CommandAdmission:
        return await self._call(
            self._visual_stimulus_stub(launch, request.target).Shutdown,
            request,
            deadline_ns,
        )

    async def get_visual_stimulus_worker_state(
        self,
        launch: wire.LaunchState,
        request: visual_stimulus.WorkerQuery,
        *,
        deadline_ns: int,
    ) -> visual_stimulus.WorkerState:
        return await self._call(
            self._visual_stimulus_stub(launch, request.target).GetState,
            request,
            deadline_ns,
        )

    async def retire_worker_generation(self, role: str, generation: str) -> None:
        """Close cached channels only after the exact worker launch is released."""
        matches = [key for key in self.channels if key[1:] == (role, generation)]
        channels = [self.channels.pop(key) for key in matches]
        await asyncio.gather(*(channel.close() for channel in channels))
