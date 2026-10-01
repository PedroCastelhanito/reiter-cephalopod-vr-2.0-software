"""Ordered exact-process exit and final absence evidence (E06/E08)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from cephvr.control.v1 import services_pb2 as wire
from cephvr.shared.clock import host_time_ns
from cephvr.supervisor.registry import BACKEND_ROLES, LaunchRegistry, NativeLaunches
from cephvr.supervisor.state import ShutdownState


@dataclass(frozen=True)
class ProcessExitEvidence:
    remaining: tuple[tuple[int, int, str], ...]
    unconfirmed_jobs: frozenset[str]


async def wait_while(
    condition: Callable[[], object], until_ns: int, poll_s: float = 0.05
) -> None:
    """Poll until ``until_ns`` or the condition clears; the deadline is checked first."""
    while host_time_ns() < until_ns and condition():
        await asyncio.sleep(min(poll_s, max(0.0, (until_ns - host_time_ns()) / 1e9)))


async def stop_owned_processes(
    *,
    registry: LaunchRegistry,
    native: NativeLaunches,
    shutdown: ShutdownState,
    graceful_exit_ns: int,
    terminate_exit_ns: int,
) -> ProcessExitEvidence:
    """Stop backend groups before controller/GUI without claiming output closure.

    Read the retained outer deadline at each exit phase; only the coordinator
    records operation outcomes and decides whether shutdown is complete.
    """
    unconfirmed: set[str] = set()

    def inspect(state: wire.LaunchState) -> list[tuple[int, int, str]]:
        # A released launch proved absence and closed its job handle.
        if state.phase == wire.LAUNCH_PHASE_RELEASED:
            return []
        # One unreadable job must not stop shutdown of the other children.
        try:
            return native.inspect_launch_job(state.containment_job_name)
        except Exception:
            unconfirmed.add(state.containment_job_name)
            return []

    for roles in (
        BACKEND_ROLES,
        {"controller", "gui"},
    ):
        candidates = [
            state
            for state in registry.states(tolerant=True)
            if state.plan.child.role in roles
        ]

        def remaining_members(
            states: tuple[wire.LaunchState, ...] = tuple(candidates),
        ) -> list[tuple[int, int, str]]:
            found: dict[tuple[int, int], tuple[int, int, str]] = {}
            for state in states:
                for member in inspect(state):
                    found[member[:2]] = member
            return list(found.values())

        grace_until = min(
            host_time_ns() + graceful_exit_ns,
            shutdown.shutdown_deadline_ns or (host_time_ns() + graceful_exit_ns),
        )
        await wait_while(remaining_members, grace_until)
        for pid, created, _ in remaining_members():
            try:
                if native.process_running(pid, created):
                    native.terminate_exact(pid, created)
            except Exception:
                # Continue with the other members; the final job inspection
                # decides whether this one is still present.
                continue
        terminate_until = min(
            host_time_ns() + terminate_exit_ns,
            shutdown.shutdown_deadline_ns or (host_time_ns() + terminate_exit_ns),
        )
        await wait_while(remaining_members, terminate_until)
    unconfirmed.clear()  # only the final inspection can leave absence unconfirmed
    remaining = [
        member
        for state in registry.states(tolerant=True)
        if state.plan.child.role != "supervisor"
        for member in inspect(state)
    ]
    return ProcessExitEvidence(tuple(remaining), frozenset(unconfirmed))
