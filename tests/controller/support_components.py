"""Shared controller fixtures for state, task ownership and peer evidence."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.lifecycle_reports import LifecycleReports, ReportHooks
from cephvr.controller.metadata.reservation import OutputReservation
from cephvr.controller.ports import BackendPort
from cephvr.controller.runtime import ControllerRuntime
from cephvr.controller.state import (
    Attempt,
    ConfigurationState,
    ControllerLimits,
    LifecycleState,
    LimitsState,
    SupervisorState,
)
from cephvr.shared.commands import CommandLedger


@dataclass
class _Backend:
    context: pb.BackendContext


@dataclass
class _Fixture:
    reports: LifecycleReports
    lifecycle: LifecycleState
    supervisor: SupervisorState
    attempt: Attempt
    backend: pb.BackendContext
    publications: list[int]


def _limits() -> ControllerLimits:
    return ControllerLimits(
        setup_ns=100,
        setup_cancel_ns=100,
        ready_ns=100,
        finished_ns=100,
        registration_ns=100,
        recovery_ns=100,
        metadata_ns=100,
        validation_ns=100,
        lead_ns=3,
        controller_release_ns=2,
        backend_release_ns=1,
        start_evidence_ns=100,
        stop_evidence_ns=100,
        max_metadata_operations=4,
        max_metadata_bytes=100_000,
        history_ns=100,
        space_query_ns=100,
        low_space_bytes=1,
    )


def _fixture(root: Path) -> _Fixture:
    session_id = str(uuid4())
    generation = str(uuid4())
    session = pb.SessionContext(controller_generation=generation, session_id=session_id)
    backend = pb.BackendContext(
        backend_name="visual_stimulus", backend_generation=str(uuid4())
    )
    trial = pb.TrialContext(session=session, trial_id=str(uuid4()), trial_number=1)
    prepared = pb.PreparedSession(context=session)
    prepared.trials.add(context=trial)
    reservation = OutputReservation(
        root, "experiment", "subject", session_id, generation, datetime.now(UTC)
    )
    participant = cast(BackendPort, _Backend(backend))
    attempt = Attempt(
        context=session,
        prepared=prepared,
        reservation=reservation,
        required={"visual_stimulus": participant},
        setup_operations={"visual_stimulus": "setup"},
        visual_stimulus_setup_dispatched=True,
    )
    attempt.scope_commands["scope"] = ("visual_stimulus", "incident", 1)
    attempt.setup_deadline_ns = 100
    attempt.ready_deadline_ns = 100
    attempt.trial_index = 0
    attempt.trial_operation = "trial-command"
    attempt.trial_participants["visual_stimulus"] = participant
    lifecycle = LifecycleState(
        session=pb.SessionState(phase=pb.SESSION_PHASE_SETTING_UP),
        trial=pb.TrialState(phase=pb.TRIAL_PHASE_PREPARING),
        attempt=attempt,
    )
    configuration = ConfigurationState(
        pb.ExperimentConfiguration(), pb.ControlPolicies()
    )
    supervisor = SupervisorState(last_seen_ns=0)
    publications = [0]

    def publish() -> None:
        publications[0] += 1

    def spawn(coroutine: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        return asyncio.create_task(coroutine)

    async def late_cleanup(_attempt: Attempt) -> None:
        pass

    async def log_event(*_args: object, **_kwargs: object) -> None:
        pass

    hooks = ReportHooks(
        publish=publish,
        spawn=spawn,
        late_cleanup=late_cleanup,
        log_event=log_event,
        clock=lambda: 0,
        activity_requirements=lambda _attempt, _name: (
            frozenset(),
            frozenset(),
            frozenset(),
            frozenset(),
            frozenset(),
        ),
        source_producers=lambda _attempt, _name: {},
    )
    reports = LifecycleReports(
        lifecycle=lifecycle,
        configuration=configuration,
        supervisor=supervisor,
        limits=LimitsState(_limits()),
        hooks=hooks,
    )
    return _Fixture(reports, lifecycle, supervisor, attempt, backend, publications)


def _id() -> str:
    return str(uuid.uuid4())


def default_limits() -> ControllerLimits:
    return ControllerLimits(
        setup_ns=1_000_000_000,
        setup_cancel_ns=1_000_000_000,
        ready_ns=1_000_000_000,
        finished_ns=1_000_000_000,
        registration_ns=1_000_000_000,
        recovery_ns=1_000_000_000,
        metadata_ns=1_000_000_000,
        validation_ns=1_000_000_000,
        lead_ns=500_000_000,
        controller_release_ns=100_000_000,
        backend_release_ns=50_000_000,
        start_evidence_ns=250_000_000,
        stop_evidence_ns=250_000_000,
        max_metadata_operations=8,
        max_metadata_bytes=4096,
        history_ns=1_000_000_000,
        space_query_ns=1_000_000_000,
        low_space_bytes=1,
    )


def _runtime(path: Path, backend: pb.BackendContext) -> ControllerRuntime:
    limits = default_limits()
    peer = cast(BackendPort, type("Peer", (), {"context": backend})())
    return ControllerRuntime(
        generation=_id(),
        configuration=pb.ExperimentConfiguration(recording_root=str(path)),
        limits=limits,
        validators={},
        backends={backend.backend_name: peer},
        clock=lambda: 1_000,
    )


def _reservation(root: Path) -> OutputReservation:
    return OutputReservation(
        root,
        "experiment",
        "subject",
        "81d85f03-ac85-4d5e-885c-4754ee594540",
        "470b220b-6272-4fa3-8677-3957c29eea5f",
        datetime(2026, 9, 29, 13, 14, 15, tzinfo=UTC),
    )


def _attempt(
    runtime: ControllerRuntime, path: Path, required: dict[str, BackendPort]
) -> Attempt:
    context = pb.SessionContext(
        controller_generation=runtime.generation, session_id=_id()
    )
    prepared = pb.PreparedSession(
        context=context, configuration_revision=runtime.configuration_state.revision
    )
    reservation = OutputReservation(
        path,
        "experiment",
        "subject",
        context.session_id,
        runtime.generation,
        datetime.now(UTC),
    )
    return Attempt(context, prepared, reservation, required, {})


class _RetainedPeer:
    def __init__(
        self, context: pb.BackendContext, retained: svc.RetainedResult
    ) -> None:
        self.context = context
        self.retained = retained
        self.queries: list[svc.RetainedResultQuery] = []

    async def get_retained_result(
        self, request: svc.RetainedResultQuery, *, deadline_ns: int
    ) -> svc.RetainedResult:
        self.queries.append(request)
        return self.retained


class TaskCapture:
    """Observe component-owned work through its injected spawn port."""

    def __init__(
        self, spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]]
    ) -> None:
        self._spawn = spawn
        self.tasks: list[asyncio.Task[Any]] = []

    def spawn(self, coroutine: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        task = self._spawn(coroutine)
        self.tasks.append(task)
        return task

    async def drain(self) -> None:
        await asyncio.gather(*self.tasks)


def operator_command(runtime: ControllerRuntime) -> svc.OperatorCommand:
    return svc.OperatorCommand(
        controller_generation=runtime.generation,
        operator=pb.OperatorContext(command_id=_id()),
    )


async def drain_runtime_tasks(runtime: ControllerRuntime) -> None:
    while runtime._tasks:
        await asyncio.gather(*list(runtime._tasks), return_exceptions=True)


def bind_ledger(runtime: Any) -> None:
    runtime.bind_camera_status_retention(
        CommandLedger(
            runtime.generation,
            10**15,
            max_records=32,
            max_bytes=10_000_000,
            result_reservation_bytes=4096,
        )
    )
