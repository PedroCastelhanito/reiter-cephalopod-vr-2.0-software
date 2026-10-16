"""Exact GUI replacement ownership after native launch, under E08."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.platform.windows.jobs import SuspendedProcess, WindowsLaunchError


class GuiRelaunch:
    """Serialize replacement plans and retain only an actually launched GUI."""

    def __init__(
        self,
        *,
        owner: pb.ProcessIdentity,
        interpreter: str,
        command_id: str,
        refresh: Callable[[str], wire.LaunchState],
        launch: Callable[
            [wire.PlanLaunchRequest, wire.LaunchState, str, int],
            Awaitable[SuspendedProcess],
        ],
        register: Callable[[pb.ProcessIdentity, str, int, int], Awaitable[None]],
    ) -> None:
        self.owner = owner
        self.interpreter = interpreter
        self.command_id = command_id
        self.refresh = refresh
        self.launch = launch
        self.register = register
        self.lock = asyncio.Lock()

    async def __call__(
        self,
        request: wire.PlanLaunchRequest,
        planned: wire.LaunchState,
        token: str,
        deadline_ns: int,
    ) -> wire.LaunchState:
        async with self.lock:
            if (
                request.owner != self.owner
                or request.child.role != "gui"
                or request.executable != self.interpreter
                or not request.python_worker
                or request.stop_method != "grpc_shutdown"
                or request.HasField("work")
                or request.HasField("parent_operation")
            ):
                raise WindowsLaunchError("GUI relaunch plan is outside launcher policy")
            if request.command_id == self.command_id:
                return self.refresh(request.command_id)
            previous = self.refresh(self.command_id)
            if previous.phase != wire.LAUNCH_PHASE_RELEASED:
                raise WindowsLaunchError("prior GUI launch is not confirmed released")
            child = await self.launch(request, planned, token, deadline_ns)
            # Notification may fail after launch; retain that exact child for cleanup.
            self.command_id = request.command_id
            await self.register(
                request.child, request.command_id, child.pid, child.creation_time_100ns
            )
            return self.refresh(request.command_id)
