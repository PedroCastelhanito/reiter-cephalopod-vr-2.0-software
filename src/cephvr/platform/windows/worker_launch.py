"""Shared registered Python-worker launch sequence under E08."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from cephvr.control.v1 import services_pb2 as wire
from cephvr.platform.windows.bootstrap import BootstrapPipeWrite, close_handle
from cephvr.platform.windows.jobs import WindowsLaunchError
from cephvr.shared.clock import host_time_ns
from cephvr.shared.deadlines import remaining_seconds

_Child = TypeVar("_Child")


@dataclass
class BootstrapPipeHandles:
    """Parent-side pipe handles until read closure and writer-thread transfer."""

    read_handle: int
    write_handle: int

    def close_read(self) -> None:
        if self.read_handle >= 0:
            close_handle(self.read_handle)
            self.read_handle = -1

    def close_untransferred(self) -> None:
        self.close_read()
        if self.write_handle >= 0:
            close_handle(self.write_handle)
            self.write_handle = -1


async def launch_registered_worker(
    *,
    request: wire.PlanLaunchRequest,
    create_pipes: Callable[[], BootstrapPipeHandles],
    plan: Callable[[wire.PlanLaunchRequest], Awaitable[wire.LaunchState]],
    create_suspended: Callable[[wire.LaunchState, BootstrapPipeHandles], _Child],
    process_identity: Callable[[_Child], tuple[int, int]],
    confirm: Callable[[_Child], Awaitable[wire.LaunchState]],
    descriptor: Callable[[_Child], dict[str, object]],
    register_peer: Callable[[_Child, dict[str, object]], None],
    resume: Callable[[_Child], None],
    retain_writer: Callable[[BootstrapPipeWrite], None],
    finish_writer: Callable[[BootstrapPipeWrite], None],
    get_state: Callable[[], Awaitable[wire.LaunchState]],
    deadline_ns: int,
    clock: Callable[[], int] = host_time_ns,
) -> tuple[_Child, wire.LaunchState]:
    """Run Plan -> suspended child -> OS confirmation -> bootstrap -> Operational.

    Native process/job ownership and transport authentication stay with the caller.
    This helper owns only the shared launch ordering and the two parent pipe handles.
    """
    pipes: BootstrapPipeHandles | None = None
    try:
        if clock() >= deadline_ns:
            raise TimeoutError("worker launch deadline expired before PlanLaunch")
        planned = await plan(request)
        if (
            planned.phase != wire.LAUNCH_PHASE_PLANNED
            or not planned.containment_job_name
            or planned.plan.SerializeToString(deterministic=True)
            != request.SerializeToString(deterministic=True)
        ):
            raise WindowsLaunchError("supervisor did not retain the exact launch plan")

        pipes = create_pipes()
        child = create_suspended(planned, pipes)
        pid, creation_time = process_identity(child)
        confirmed = await confirm(child)
        if (
            confirmed.phase != wire.LAUNCH_PHASE_OS_CONFIRMED
            or confirmed.pid != pid
            or confirmed.creation_time_100ns != creation_time
            or confirmed.plan.SerializeToString(deterministic=True)
            != request.SerializeToString(deterministic=True)
        ):
            raise WindowsLaunchError("supervisor did not confirm the exact worker")

        document = descriptor(child)
        register_peer(child, document)
        resume(child)

        attempt = BootstrapPipeWrite(pipes.write_handle, document)
        retain_writer(attempt)
        try:
            attempt.start()
        except BaseException:
            finish_writer(attempt)
            raise
        pipes.write_handle = -1
        try:
            await attempt.wait(deadline_ns)
        except BaseException:
            if attempt.completed.is_set():
                finish_writer(attempt)
            raise
        finish_writer(attempt)
        pipes.close_read()

        last = wire.LaunchState()
        while clock() < deadline_ns:
            last = await get_state()
            if not isinstance(last, wire.LaunchState):
                raise TypeError("supervisor returned an invalid launch state")
            if last.plan.SerializeToString(
                deterministic=True
            ) != request.SerializeToString(deterministic=True):
                raise WindowsLaunchError("launch state differs from the exact plan")
            if (last.pid, last.creation_time_100ns) != (pid, creation_time):
                raise WindowsLaunchError(
                    "launch state differs from the confirmed worker"
                )
            if last.phase == wire.LAUNCH_PHASE_OPERATIONAL:
                if not last.endpoint:
                    raise WindowsLaunchError("operational worker has no endpoint")
                return child, last
            if last.phase in {
                wire.LAUNCH_PHASE_CLEANUP_REQUIRED,
                wire.LAUNCH_PHASE_RELEASED,
            }:
                raise WindowsLaunchError(
                    "worker launch entered a terminal failure phase"
                )
            await asyncio.sleep(min(0.01, remaining_seconds(deadline_ns, clock=clock)))
        raise TimeoutError(
            f"worker endpoint registration missed deadline; last phase={last.phase}"
        )
    finally:
        if pipes is not None:
            pipes.close_untransferred()
