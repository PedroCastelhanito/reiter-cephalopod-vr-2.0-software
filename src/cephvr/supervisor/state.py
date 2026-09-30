"""Authoritative supervisor state records shared by focused operations (E06/E08)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.incidents import IncidentTopology
from cephvr.shared.resources import ResourceObligationRegistry

ProcessKey = tuple[str, str]


class SupervisorTasks:
    """Retain fire-and-forget tasks and surface their failures (E08).

    A task's exception becomes a supervisor status warning, never a lost result.
    """

    def __init__(self, on_failure: Callable[[str, str], None]) -> None:
        self._on_failure = on_failure
        self._tasks: set[asyncio.Task[Any]] = set()
        self._closed = False

    def spawn(
        self, name: str, coroutine: Coroutine[Any, Any, Any]
    ) -> asyncio.Task[Any]:
        task = asyncio.create_task(coroutine, name=name)
        if self._closed:
            task.cancel()  # stopped: nothing new may outlive cancel_all()
            return task
        self._tasks.add(task)
        task.add_done_callback(lambda done: self._finished(name, done))
        return task

    def _finished(self, name: str, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        failure = task.exception()
        if failure is not None:
            self.report_failure(name, failure)

    def report_failure(self, name: str, failure: BaseException) -> None:
        self._on_failure(name, f"{name} unconfirmed: {failure!r}")

    def cancel_all(self) -> None:
        self._closed = True
        for task in list(self._tasks):
            task.cancel()


@dataclass
class RegistrationState:
    context: wire.RegisteredContext | None = None
    topology: IncidentTopology | None = None
    prepared_worker_backend: dict[ProcessKey, str] = field(default_factory=dict)
    catalogues: dict[ProcessKey, ResourceObligationRegistry] = field(
        default_factory=dict
    )


@dataclass
class HealthState:
    last_heartbeat: dict[ProcessKey, int] = field(default_factory=dict)
    heartbeat_reports: dict[ProcessKey, types.HeartbeatReport] = field(
        default_factory=dict
    )
    errors: dict[str, types.ErrorReport] = field(default_factory=dict)
    pending_error_deadlines: dict[str, int] = field(default_factory=dict)
    pending_backend_exits: dict[ProcessKey, tuple[int, int, types.Failure]] = field(
        default_factory=dict
    )
    isolated_backend_exits: set[ProcessKey] = field(default_factory=set)
    monitor_task: asyncio.Task[None] | None = None
    heartbeater_task: asyncio.Task[None] | None = None


@dataclass
class RecoveryState:
    cleanup: dict[ProcessKey, types.CleanupReport] = field(default_factory=dict)
    recoveries: dict[str, types.RecoveryState] = field(default_factory=dict)
    operations: dict[str, types.OperationState] = field(default_factory=dict)
    issued_cleanup_commands: dict[str, wire.BackendCommand] = field(
        default_factory=dict
    )
    cleanup_events: dict[str, asyncio.Event] = field(default_factory=dict)


@dataclass
class ShutdownState:
    shutdown_deadline_ns: int | None = None
    cleanup_deadline_ns: int | None = None
    shutdown_request: bytes | None = None
    interruption: wire.InterruptionReport | None = None
    safety_task: asyncio.Task[None] | None = None
    shutdown_task: asyncio.Task[None] | None = None
    shutdown_interrupted: bool = False
    shutdown_complete: asyncio.Event = field(default_factory=asyncio.Event)
    controller_ack: asyncio.Event = field(default_factory=asyncio.Event)
    worker_interrupt_commands: dict[ProcessKey, str] = field(default_factory=dict)
    worker_cleanup_commands: dict[ProcessKey, str] = field(default_factory=dict)


@dataclass
class StatusState:
    revision: int = 0
    acknowledged_revision: int = 0  # last revision the controller accepted
    warnings: dict[str, types.Warning] = field(default_factory=dict)
    pending_status: wire.SupervisorStatusReport | None = None
    status_task: asyncio.Task[None] | None = None
