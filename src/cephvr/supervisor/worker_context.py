"""Work containment for registered worker discovery and RPC validation (E08)."""

from typing import Any, Protocol

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types


def work_covered_by(scope: types.WorkContext | None, work: types.WorkContext) -> bool:
    """Whether registered/launch ``scope`` covers ``work``.

    An absent or empty scope covers only unscoped work; a session scope covers
    that session and its trials; any other scope must match exactly.
    """
    kind = work.WhichOneof("work")
    if scope is None or scope.WhichOneof("work") is None:
        return kind is None
    if scope.WhichOneof("work") == "session":
        if kind == "session":
            return work.session == scope.session
        return kind == "trial" and work.trial.session == scope.session
    return work == scope


def launch_work_matches(plan: wire.PlanLaunchRequest, work: types.WorkContext) -> bool:
    """Session launches cover their trials; other work must match exactly.

    An absent launch scope covers only unscoped work. Persistent Visual Stimulus renderers
    explicitly bypass this check when launched without a work field (V19).
    """
    return work_covered_by(plan.work if plan.HasField("work") else None, work)


class WorkerControl(Protocol):
    """Per-backend direct worker safety operations used by shutdown (E08)."""

    def registered_workers(
        self, work: types.WorkContext
    ) -> list[tuple[wire.LaunchState, Any]]: ...

    async def interrupt_worker(
        self,
        launch: wire.LaunchState,
        worker: Any,
        report: wire.InterruptionReport,
        deadline_ns: int,
    ) -> None: ...

    async def cleanup_worker(
        self, launch: wire.LaunchState, worker: Any, deadline_ns: int
    ) -> None: ...

    async def shutdown_worker(
        self, launch: wire.LaunchState, worker: Any, deadline_ns: int
    ) -> None: ...
