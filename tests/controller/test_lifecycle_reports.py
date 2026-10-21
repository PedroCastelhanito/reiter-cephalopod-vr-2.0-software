"""Exact lifecycle report admission, recovery and cleanup forwarding."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import grpc
import pytest

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.lifecycle.preparation_context import PreparationContext
from cephvr.controller.lifecycle.trials import TrialExecution
from cephvr.controller.lifecycle_reports import LifecycleReports, ReportHooks
from cephvr.controller.metadata.reservation import OutputReservation
from cephvr.controller.planning import requested_output_identities
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


async def test_setup_failure_accepts_only_its_exact_backend_operation(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    operation = pb.OperationState(
        context=pb.OperationContext(command_id="setup"),
        work=pb.WorkContext(session=fixture.attempt.context),
        complete=True,
        succeeded=False,
        failure=pb.Failure(code="SETUP_REJECTED", message="explicit failure"),
    )
    report = pb.LifecycleReport(
        operation=pb.BackendOperationReport(source=fixture.backend, operation=operation)
    )
    assert (
        await fixture.reports.receive(report, 50)
    ).result == pb.COMMAND_RESULT_ACCEPTED
    assert fixture.attempt.scope_results["setup"] == operation
    report.operation.source.backend_generation = str(uuid4())
    assert (
        await fixture.reports.receive(report, 50)
    ).result == pb.COMMAND_RESULT_REJECTED


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


@pytest.mark.parametrize(
    ("include_expected", "include_unknown", "invalid_result", "accepted"),
    [
        (True, False, "", True),
        (False, False, "", False),
        (True, True, "", False),
        (True, False, "closed", False),
        (True, False, "path", False),
        (True, False, "unknown-presence", False),
        (True, False, "present", False),
    ],
)
async def test_failed_setup_cleanup_matches_registered_output_set_exactly(
    tmp_path: Path,
    include_expected: bool,
    include_unknown: bool,
    invalid_result: str,
    accepted: bool,
) -> None:
    fixture = _fixture(tmp_path)
    attempt, backend = fixture.attempt, fixture.backend
    setting = attempt.prepared.configuration.backends.add(
        backend_name="visual_stimulus", enabled=True
    )
    setting.visual_stimulus.save_visual_stimulus_data = True
    work = pb.WorkContext(session=attempt.context)
    source = pb.ProcessIdentity(
        role=backend.backend_name, generation=backend.backend_generation
    )
    requested = requested_output_identities(
        attempt.prepared,
        {name: participant.context for name, participant in attempt.required.items()},
    )
    output_keys = {output.output_key for output in requested}
    registered = svc.RegisteredContext(work=work)
    operation_id = "cancel-setup"
    registered.cleanup_commands.add(
        target=source,
        work=work,
        operation=pb.OperationContext(command_id=operation_id),
    )
    attempt.registered_context = registered
    assert len(registered.outputs) == 0
    heartbeat = pb.HeartbeatReport(
        source=source, work=work, cleanup_resources_revision=1
    )
    fixture.supervisor.processes[backend.backend_name] = svc.ProcessHealthStatus(
        process=source, last_heartbeat=heartbeat
    )
    cleanup = pb.CleanupReport(
        source=source,
        work=work,
        operation=pb.OperationContext(command_id=operation_id),
        verified_monotonic_ns=1,
        trial_activity_stopped=True,
        cleanup_resources_revision=1,
    )
    if include_expected:
        for output_key in output_keys:
            output = cleanup.outputs.add(
                output_key=output_key,
                closure=(
                    pb.OUTPUT_CLOSURE_CLOSED
                    if invalid_result == "closed"
                    else pb.OUTPUT_CLOSURE_NOT_STARTED
                ),
                path="unexpected.jsonl" if invalid_result == "path" else "",
            )
            if invalid_result != "unknown-presence":
                output.artifact_present = invalid_result == "present"
    if include_unknown:
        cleanup.outputs.add(
            output_key="unregistered-output",
            closure=pb.OUTPUT_CLOSURE_NOT_STARTED,
            artifact_present=False,
        )

    receipt = await fixture.reports.receive(pb.LifecycleReport(cleanup=cleanup), 50)

    assert (receipt.result == pb.COMMAND_RESULT_ACCEPTED) is accepted
    if not accepted:
        assert receipt.failure.code == "EVIDENCE"


@pytest.mark.parametrize(
    "dispatched,heartbeat", ((False, False), (False, True), (True, False), (True, True))
)
async def test_pre_dispatch_stimulus_cleanup_requires_exact_empty_proof(
    tmp_path, dispatched, heartbeat
):
    fixture = _fixture(tmp_path)
    attempt = fixture.attempt
    attempt.visual_stimulus_setup_dispatched = dispatched
    setting = attempt.prepared.configuration.backends.add(
        backend_name="visual_stimulus", enabled=True
    )
    setting.visual_stimulus.save_visual_stimulus_data = True
    source = pb.ProcessIdentity(
        role="visual_stimulus", generation=fixture.backend.backend_generation
    )
    work = pb.WorkContext(session=attempt.context)
    operation = pb.OperationContext(command_id=str(uuid4()))
    attempt.registered_context = svc.RegisteredContext(work=work)
    attempt.registered_context.cleanup_commands.add(
        target=source, work=work, operation=operation
    )
    if heartbeat:
        fixture.supervisor.processes["visual_stimulus"] = svc.ProcessHealthStatus(
            process=source,
            last_heartbeat=pb.HeartbeatReport(
                source=source, work=work, cleanup_resources_revision=0
            ),
        )
    cleanup = pb.CleanupReport(
        source=source,
        work=work,
        operation=operation,
        verified_monotonic_ns=1,
        trial_activity_stopped=True,
        cleanup_resources_revision=0,
    )
    receipt = await fixture.reports.receive(pb.LifecycleReport(cleanup=cleanup), 50)
    assert (receipt.result == pb.COMMAND_RESULT_ACCEPTED) is not dispatched


@pytest.mark.parametrize("path", [None, "wrong.jsonl", "camera.jsonl"])
async def test_cleanup_requires_registered_output_path(
    tmp_path: Path, path: str | None
) -> None:
    fixture = _fixture(tmp_path)
    attempt, backend = fixture.attempt, fixture.backend
    source = pb.ProcessIdentity(
        role=backend.backend_name, generation=backend.backend_generation
    )
    work = pb.WorkContext(session=attempt.context)
    registered = svc.RegisteredContext(work=work)
    registered.outputs.add(output_key="camera", backend=backend)
    attempt.prepared.outputs.add(
        output_key="camera", backend=backend, path="camera.jsonl"
    )
    operation = pb.OperationContext(command_id=_id())
    registered.cleanup_commands.add(target=source, work=work, operation=operation)
    attempt.registered_context = registered
    fixture.supervisor.processes[backend.backend_name] = svc.ProcessHealthStatus(
        process=source,
        last_heartbeat=pb.HeartbeatReport(
            source=source, work=work, cleanup_resources_revision=1
        ),
    )
    cleanup = pb.CleanupReport(
        source=source,
        work=work,
        operation=operation,
        verified_monotonic_ns=1,
        trial_activity_stopped=True,
        cleanup_resources_revision=1,
    )
    result = cleanup.outputs.add(
        output_key="camera", closure=pb.OUTPUT_CLOSURE_CLOSED, artifact_present=True
    )
    if path is not None:
        result.path = path
    receipt = await fixture.reports.receive(pb.LifecycleReport(cleanup=cleanup), 50)
    assert (receipt.result == pb.COMMAND_RESULT_ACCEPTED) == (path == "camera.jsonl")
    assert bool(attempt.cleanup) == (path == "camera.jsonl")


@pytest.mark.parametrize(
    "outcome",
    [
        "scheduled",
        "wrong-path",
        "foreign-trial",
        "missing-plan",
        "duplicate-frozen",
        "registered-wrong-path",
        "unscheduled",
        "unscheduled-closed",
    ],
)
async def test_cleanup_joins_frozen_setup_output_to_scheduled_path(tmp_path, outcome):
    fixture = _fixture(tmp_path)
    attempt, backend = fixture.attempt, fixture.backend
    trial = attempt.prepared.trials[0]
    trial.resolved_duration_ns = 1_000_000_000
    attempt.prepared.anchor_wall_time = datetime.now(UTC).isoformat()
    attempt.prepared.anchor_monotonic_ns = 0
    attempt.prepared.configuration.subject = "DUMMY"
    attempt.prepared.outputs.add(
        output_key="camera",
        backend=backend,
        trial=trial.context,
        output_tag="camera",
        extension="jsonl",
    )
    preparation = PreparationContext(
        configuration=ConfigurationState(
            pb.ExperimentConfiguration(), pb.ControlPolicies()
        ),
        supervisor=fixture.supervisor,
        generation=attempt.context.controller_generation,
        supervisor_generation=_id(),
    )
    registered = preparation.registration(attempt, "setup").context
    assert not registered.outputs[0].HasField("path")
    attempt.registered_context = registered
    if not outcome.startswith("unscheduled"):
        execution = SimpleNamespace(
            clock=lambda: 100,
            limit_state=LimitsState(_limits()),
            lifecycle=fixture.lifecycle,
            publisher=SimpleNamespace(publish=lambda: None),
        )
        await TrialExecution._plan_trial(execution, attempt, trial)
        assert attempt.prepared.outputs[0].path
    assert not registered.outputs[0].HasField("path")
    source = pb.ProcessIdentity(
        role=backend.backend_name, generation=backend.backend_generation
    )
    work = pb.WorkContext(session=attempt.context)
    operation = pb.OperationContext(command_id=_id())
    registered.cleanup_commands.add(target=source, work=work, operation=operation)
    fixture.supervisor.processes[backend.backend_name] = svc.ProcessHealthStatus(
        process=source,
        last_heartbeat=pb.HeartbeatReport(
            source=source, work=work, cleanup_resources_revision=1
        ),
    )
    cleanup = pb.CleanupReport(
        source=source,
        work=work,
        operation=operation,
        verified_monotonic_ns=1,
        trial_activity_stopped=True,
        cleanup_resources_revision=1,
    )
    cleanup.outputs.add(
        output_key="camera",
        path=attempt.prepared.outputs[0].path,
        closure=pb.OUTPUT_CLOSURE_NOT_STARTED
        if outcome == "unscheduled"
        else pb.OUTPUT_CLOSURE_CLOSED,
        artifact_present=outcome != "unscheduled",
    )
    if outcome == "wrong-path":
        cleanup.outputs[0].path = "foreign.jsonl"
    elif outcome == "foreign-trial":
        attempt.prepared.outputs[0].trial.trial_id = _id()
    elif outcome == "missing-plan":
        del attempt.prepared.outputs[:]
    elif outcome == "duplicate-frozen":
        registered.outputs.add().CopyFrom(registered.outputs[0])
    elif outcome == "registered-wrong-path":
        registered.outputs[0].path = "wrong-frozen-path.jsonl"
    receipt = await fixture.reports.receive(pb.LifecycleReport(cleanup=cleanup), 50)
    assert (receipt.result == pb.COMMAND_RESULT_ACCEPTED) == (
        outcome in {"scheduled", "unscheduled"}
    )


async def test_trial_state_only_is_required_activity_and_admits_exact_pulse_reports(
    tmp_path,
):
    from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
    from cephvr.controller.lifecycle.activity import activity_backends

    fixture = _fixture(tmp_path)
    attempt = fixture.attempt
    backend = pb.BackendContext(
        backend_name="acquisition", backend_generation=str(uuid4())
    )
    attempt.required = {"acquisition": cast(BackendPort, _Backend(backend))}
    attempt.trial_participants = dict(attempt.required)
    settings = attempt.prepared.configuration.backends.add(
        backend_name="acquisition", enabled=True
    ).acquisition
    settings.pulses.trial_state_enabled = True
    attempt.ready["acquisition"] = pb.ReadyReport(required_checks_passed=True)
    assert activity_backends(attempt) == {"acquisition"}
    attempt.target_ns, attempt.end_ns = 100, 200
    fixture.lifecycle.session.phase = pb.SESSION_PHASE_RUNNING
    fixture.lifecycle.trial.phase = pb.TRIAL_PHASE_RUNNING
    context = pb.ReportContext(
        backend=backend,
        work=pb.WorkContext(trial=attempt.prepared.trials[0].context),
        operation=pb.OperationContext(command_id=attempt.trial_operation),
    )
    pulse = mcu.PulseCommandEvidence(
        command=mcu.PULSE_BOUNDARY_COMMAND_ON,
        outcome=mcu.PULSE_COMMAND_OUTCOME_APPLIED,
        applied=True,
        behavioral_selected=False,
        tracking_selected=False,
        eye_tracking_selected=False,
        trial_state_selected=True,
        scheduled_boundary_monotonic_ns=100,
        dispatched_monotonic_ns=101,
        acknowledged_monotonic_ns=105,
        resulting_state=mcu.MicrocontrollerState(
            trial_state=mcu.PulseOutputState(enabled=True, running=True)
        ),
    )
    started = pb.LifecycleReport(
        started=pb.StartedReport(
            context=context, actual_start_monotonic_ns=105, acquisition_pulse_on=pulse
        )
    )
    assert (
        await fixture.reports.receive(started, 110)
    ).result == pb.COMMAND_RESULT_ACCEPTED
    assert "acquisition" in attempt.started
    pulse.command = mcu.PULSE_BOUNDARY_COMMAND_OFF
    pulse.scheduled_boundary_monotonic_ns = 200
    pulse.dispatched_monotonic_ns = 201
    pulse.acknowledged_monotonic_ns = 205
    pulse.resulting_state.trial_state.running = False
    fixture.lifecycle.trial.phase = pb.TRIAL_PHASE_FINALIZING
    stopped = pb.LifecycleReport(
        stopped=pb.StoppedReport(
            context=context,
            actual_stop_monotonic_ns=210,
            trial_activity_stopped=True,
            recording_interval_sealed=True,
            acquisition_pulse_off=pulse,
        )
    )
    assert (
        await fixture.reports.receive(stopped, 210)
    ).result == pb.COMMAND_RESULT_ACCEPTED
    assert "acquisition" in attempt.stopped


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


async def test_trial_failure_keeps_participants_separate_and_exact_deadline(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    attempt = fixture.attempt
    acquisition = pb.BackendContext(
        backend_name="acquisition", backend_generation=_id()
    )
    attempt.trial_participants["acquisition"] = cast(BackendPort, _Backend(acquisition))
    for backend in (fixture.backend, acquisition):
        operation = pb.OperationState(
            context=pb.OperationContext(command_id=attempt.trial_operation),
            command="PrepareTrial",
            work=pb.WorkContext(trial=attempt.prepared.trials[0].context),
            complete=True,
            succeeded=False,
            failure=pb.Failure(code="WRITER", message="cannot prepare output"),
        )
        report = pb.LifecycleReport(
            operation=pb.BackendOperationReport(source=backend, operation=operation)
        )
        assert (
            await fixture.reports.receive(report, 101)
        ).result == pb.COMMAND_RESULT_REJECTED
        assert (
            await fixture.reports.receive(report, 50)
        ).result == pb.COMMAND_RESULT_ACCEPTED
        assert (
            await fixture.reports.receive(report, 50)
        ).result == pb.COMMAND_RESULT_ACCEPTED
        report.operation.operation.context.command_id = "stale"
        assert (
            await fixture.reports.receive(report, 50)
        ).result == pb.COMMAND_RESULT_REJECTED
    assert set(attempt.trial_results) == {"acquisition", "visual_stimulus"}
    assert not attempt.scope_results


async def test_successful_prepare_completion_can_follow_accepted_trial_ready(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    attempt = fixture.attempt
    attempt.trial_ready[fixture.backend.backend_name] = pb.ReadyReport()
    fixture.lifecycle.trial.phase = pb.TRIAL_PHASE_STARTING
    report = pb.LifecycleReport(
        operation=pb.BackendOperationReport(
            source=fixture.backend,
            operation=pb.OperationState(
                context=pb.OperationContext(command_id=attempt.trial_operation),
                command="PrepareTrial",
                work=pb.WorkContext(trial=attempt.prepared.trials[0].context),
                complete=True,
                succeeded=True,
            ),
        )
    )
    assert (
        await fixture.reports.receive(report, 50)
    ).result == pb.COMMAND_RESULT_ACCEPTED
    report.operation.operation.succeeded = False
    assert (
        await fixture.reports.receive(report, 50)
    ).result == pb.COMMAND_RESULT_REJECTED


async def test_setup_progress_is_nonterminal_and_rejects_stale_or_invalid_reports(
    tmp_path,
):
    fixture = _fixture(tmp_path)
    operation = pb.OperationState(
        context=pb.OperationContext(command_id="setup"),
        command="SetupSession",
        work=pb.WorkContext(session=fixture.attempt.context),
        progress="Uploading initial textures: 4/20",
    )
    report = pb.LifecycleReport(
        operation=pb.BackendOperationReport(
            source=fixture.backend,
            operation=operation,
        )
    )
    receipt = await fixture.reports.receive(report, 50)
    assert receipt.result == pb.COMMAND_RESULT_ACCEPTED
    assert fixture.attempt.setup_progress == {"visual_stimulus": operation.progress}
    assert not fixture.attempt.scope_results and not fixture.attempt.ready
    assert fixture.attempt.setup_deadline_ns == 100
    assert not fixture.attempt.changed.is_set()
    assert fixture.publications == [1]

    for mutation in (
        lambda r: setattr(r.operation.source, "backend_generation", "stale"),
        lambda r: setattr(r.operation.operation.context, "command_id", "stale"),
        lambda r: setattr(r.operation.operation.work.session, "session_id", "stale"),
        lambda r: setattr(r.operation.operation, "progress", "x" * 2049),
        lambda r: setattr(r.operation.operation, "progress", ""),
        lambda r: setattr(r.operation.operation, "succeeded", True),
    ):
        changed = pb.LifecycleReport.FromString(report.SerializeToString())
        mutation(changed)
        assert (
            await fixture.reports.receive(changed, 50)
        ).result == pb.COMMAND_RESULT_REJECTED
    assert (
        await fixture.reports.receive(report, 101)
    ).result == pb.COMMAND_RESULT_REJECTED
    fixture.attempt.cancel_requested = True
    assert (
        await fixture.reports.receive(report, 50)
    ).result == pb.COMMAND_RESULT_REJECTED
    fixture.attempt.cancel_requested = False
    fixture.lifecycle.session.phase = pb.SESSION_PHASE_READY
    assert (
        await fixture.reports.receive(report, 50)
    ).result == pb.COMMAND_RESULT_REJECTED
    assert fixture.publications == [1]
