"""Exact lifecycle report admission, recovery and cleanup forwarding."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import grpc

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.lifecycle_reports import LifecycleReports, ReportHooks
from cephvr.controller.metadata.reservation import OutputReservation
from cephvr.controller.ports import BackendPort
from cephvr.controller.state import (
    Attempt,
    ConfigurationState,
    ControllerLimits,
    LifecycleState,
    LimitsState,
    SupervisorState,
)
from tests.controller.support_components import _id


class _Acquisition:
    def __init__(self, outcomes: list[object]) -> None:
        self.context = pb.BackendContext(
            backend_name="acquisition", backend_generation=_id()
        )
        self.outcomes = outcomes
        self.calls = 0

    async def confirm_tracking_input(self, request: object, *, deadline_ns: int) -> Any:
        self.calls += 1
        outcome = self.outcomes[min(self.calls, len(self.outcomes)) - 1]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _rpc_error() -> grpc.aio.AioRpcError:
    return grpc.aio.AioRpcError(
        grpc.StatusCode.UNAVAILABLE, grpc.aio.Metadata(), grpc.aio.Metadata(), "down"
    )


async def _forward(
    tmp_path: Path, outcomes: list[object], clock_ticks: int
) -> tuple[_Acquisition, list[str]]:
    fixture = _fixture(tmp_path)
    acquisition = _Acquisition(outcomes)
    fixture.attempt.required["acquisition"] = cast(Any, acquisition)
    warnings: list[str] = []
    hooks = fixture.reports.hooks
    object.__setattr__(hooks, "warn", warnings.append)
    ticks = iter(range(clock_ticks))
    object.__setattr__(hooks, "clock", lambda: next(ticks, 10**9))
    cleanup = pb.CleanupReport()
    cleanup.operation.command_id = _id()
    await fixture.reports._forward_tracking_cleanup(
        fixture.attempt, cleanup, deadline_ns=clock_ticks
    )
    return acquisition, warnings


async def test_transport_error_is_retried_then_warns_at_deadline(
    tmp_path: Path,
) -> None:
    acquisition, warnings = await _forward(tmp_path, [_rpc_error()], 6)
    assert acquisition.calls >= 2
    assert len(warnings) == 1 and "unconfirmed" in warnings[0]


async def test_transport_error_then_accept_does_not_warn(tmp_path: Path) -> None:
    accepted = pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED)
    acquisition, warnings = await _forward(tmp_path, [_rpc_error(), accepted], 50)
    assert acquisition.calls == 2 and warnings == []


async def test_non_retryable_rejection_warns(tmp_path: Path) -> None:
    rejected = pb.CommandAdmission(
        result=pb.COMMAND_RESULT_REJECTED, failure=pb.Failure(code="EVIDENCE")
    )
    acquisition, warnings = await _forward(tmp_path, [rejected], 50)
    assert acquisition.calls == 1
    assert len(warnings) == 1 and "tracking cleanup forwarding" in warnings[0]


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


async def test_operation_completion_retains_exact_duplicate_without_publishing(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    reports, attempt, backend = fixture.reports, fixture.attempt, fixture.backend
    operation = pb.OperationState(
        context=pb.OperationContext(command_id="scope"),
        work=pb.WorkContext(session=attempt.context),
        complete=True,
    )
    report = pb.LifecycleReport(
        operation=pb.BackendOperationReport(source=backend, operation=operation)
    )
    first = await reports.receive(report, 50)
    assert first.result == pb.COMMAND_RESULT_ACCEPTED
    assert attempt.changed.is_set()
    assert fixture.publications[0] == 0
    assert (await reports.receive(report, 50)).result == pb.COMMAND_RESULT_ACCEPTED
    changed = pb.LifecycleReport()
    changed.CopyFrom(report)
    changed.operation.operation.succeeded = True
    rejected = await reports.receive(changed, 50)
    assert rejected.result == pb.COMMAND_RESULT_REJECTED
    assert rejected.failure.code == "CONFLICT"
    assert len(attempt.scope_results) == 1


async def test_setup_ready_keeps_original_deadline_and_exact_duplicate_rule(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    reports, attempt, backend = fixture.reports, fixture.attempt, fixture.backend
    context = pb.ReportContext(
        backend=backend,
        work=pb.WorkContext(session=attempt.context),
        operation=pb.OperationContext(command_id="setup"),
    )
    report = pb.LifecycleReport(
        ready=pb.ReadyReport(
            context=context,
            configuration_revision=1,
            required_checks_passed=True,
        )
    )
    late = await reports.receive(report, 101)
    assert late.result == pb.COMMAND_RESULT_REJECTED
    assert late.failure.code == "EVIDENCE"
    assert not attempt.ready
    assert fixture.publications[0] == 0
    accepted = await reports.receive(report, 100)
    assert accepted.result == pb.COMMAND_RESULT_ACCEPTED
    assert fixture.publications[0] == 1
    changed = pb.LifecycleReport()
    changed.CopyFrom(report)
    changed.ready.asset_filenames.append("new-file.ext")
    rejected = await reports.receive(changed, 100)
    assert rejected.failure.code == "CONFLICT"
    assert fixture.publications[0] == 1


async def test_trial_ready_requires_exact_trial_and_active_participant(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    reports, attempt, backend = fixture.reports, fixture.attempt, fixture.backend
    fixture.lifecycle.session.phase = pb.SESSION_PHASE_RUNNING
    trial = attempt.prepared.trials[0].context
    report = pb.LifecycleReport(
        ready=pb.ReadyReport(
            context=pb.ReportContext(
                backend=backend,
                work=pb.WorkContext(trial=trial),
                operation=pb.OperationContext(command_id="trial-command"),
            ),
            configuration_revision=1,
            required_checks_passed=True,
        )
    )
    attempt.trial_participants.clear()
    absent = await reports.receive(report, 50)
    assert absent.failure.code == "EVIDENCE"
    attempt.trial_participants["visual_stimulus"] = attempt.required["visual_stimulus"]
    accepted = await reports.receive(report, 50)
    assert accepted.result == pb.COMMAND_RESULT_ACCEPTED
    assert "visual_stimulus" in attempt.trial_ready
    assert fixture.publications[0] == 1


async def test_late_finished_retains_one_exact_recovery_without_changing_duplicate(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    reports, attempt, backend = fixture.reports, fixture.attempt, fixture.backend
    fixture.lifecycle.session.phase = pb.SESSION_PHASE_RUNNING
    fixture.lifecycle.trial.phase = pb.TRIAL_PHASE_RUNNING
    attempt.target_ns = 10
    attempt.end_ns = 20
    attempt.finished_deadline_ns = 100
    attempt.finalization_deadline_ns = 200
    attempt.recovering_evidence = "finished"
    attempt.recovery_deadline_ns = 180
    attempt.confirmed_incidents = {}
    attempt.finished = {}
    attempt.recovered_finished = {}
    attempt.writer = None
    attempt.writer_closed = False
    attempt.recovery_log_closed = False
    trial = attempt.prepared.trials[0].context
    output = attempt.prepared.outputs.add(
        backend=backend,
        trial=trial,
        output_key="stimulus_LOG",
        output_tag="stimulus_LOG",
        extension="json",
        path="/reserved/stimulus_LOG.json",
    )
    report = pb.LifecycleReport(
        finished=pb.FinishedReport(
            context=pb.ReportContext(
                backend=backend,
                work=pb.WorkContext(trial=trial),
                operation=pb.OperationContext(command_id="trial-command"),
            ),
            trial_activity_stopped=True,
            outputs=[
                pb.OutputResult(
                    output_key=output.output_key,
                    path=output.path,
                    artifact_present=True,
                    closure=pb.OUTPUT_CLOSURE_CLOSED,
                )
            ],
        )
    )
    first = await reports.receive(report, 150)
    assert first.result == pb.COMMAND_RESULT_ACCEPTED
    assert len(fixture.supervisor.controller_recoveries) == 1
    assert (
        fixture.supervisor.controller_recoveries[0].outcome
        == pb.RECOVERY_OUTCOME_COMPLETED
    )
    assert (trial.trial_id, "visual_stimulus") in attempt.recovered_finished
    duplicate = await reports.receive(report, 150)
    assert duplicate.result == pb.COMMAND_RESULT_ACCEPTED
    assert len(fixture.supervisor.controller_recoveries) == 1
    changed = pb.LifecycleReport()
    changed.CopyFrom(report)
    changed.finished.visual_stimulus_review_summary.trial_id = trial.trial_id
    changed.finished.visual_stimulus_review_summary.render_groups = 1
    rejected = await reports.receive(changed, 150)
    assert rejected.result == pb.COMMAND_RESULT_REJECTED
    assert rejected.failure.code == "CONFLICT"
    assert len(fixture.supervisor.controller_recoveries) == 1
