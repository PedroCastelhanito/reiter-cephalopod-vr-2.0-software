"""Coordinator artifact ownership, release confirmation and lifecycle deadlines."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.resources import ResourceObligationRegistry
from cephvr.visual_stimulus.compiler import prepared_digest
from cephvr.visual_stimulus.coordinator.commands import bind_command, validate
from cephvr.visual_stimulus.coordinator.obligations import output_plans
from cephvr.visual_stimulus.coordinator.recipes import RecipeOwner
from cephvr.visual_stimulus.coordinator.reports import Reports
from cephvr.visual_stimulus.coordinator.state import (
    CommandLink,
    Identity,
    Prepared,
    State,
)
from cephvr.visual_stimulus.identity import CONTRACT_VERSION
from cephvr.visual_stimulus.main import command_ledger
from cephvr.visual_stimulus.recording.recipe import PreparedRecipe
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus
from cephvr.visual_stimulus.v1 import runtime_pb2 as vp
from cephvr.visual_stimulus.worker.reporting import ReportBridge

from .support import Clock, make_prepared_trial


class Peer:
    def __init__(self):
        self.commands = []
        self.reports = []

    async def command(self, method, request, *, deadline_ns):
        self.commands.append((method, request, deadline_ns))
        return pb.CommandAdmission(
            result=pb.COMMAND_RESULT_ACCEPTED, command_id=request.command.command_id
        )

    async def receipt(self, method, request, *, deadline_ns):
        self.reports.append((method, request, deadline_ns))
        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)


@pytest.mark.asyncio
async def test_idle_renderer_heartbeat_carries_lifecycle_to_supervisor():
    clock = Clock()
    identity = Identity(
        *(
            pb.ProcessIdentity(role=role, generation=str(uuid4()))
            for role in (
                "visual_stimulus",
                "controller",
                "supervisor",
                "visual_stimulus_renderer",
            )
        )
    )
    supervisor = Peer()
    reports = Reports(
        identity,
        State(),
        command_ledger(identity.process.generation, 10**12, 1_000_000),
        Peer(),
        supervisor,
        clock,
    )
    bridge = ReportBridge(
        asyncio.get_running_loop(),
        Peer(),
        supervisor,
        failed=lambda error: pytest.fail(str(error)),
        maximum_bytes=1024,
    )
    assert bridge.catalogue.session_phase == pb.SESSION_PHASE_CONFIGURATION
    heartbeat = pb.HeartbeatReport.FromString(bridge.catalogue.SerializeToString())
    heartbeat.source.CopyFrom(identity.worker)
    heartbeat.sent_monotonic_ns = clock()
    await reports.heartbeat(heartbeat, clock())
    method, accepted, _ = supervisor.reports[-1]
    assert method == "ReportHeartbeat"
    assert accepted.source == identity.process
    assert accepted.sent_monotonic_ns > 0
    assert accepted.session_phase == pb.SESSION_PHASE_CONFIGURATION
    assert not accepted.HasField("cleanup_resources_revision")


@pytest.mark.parametrize(
    "method", ["InitializeDisplay", "PrepareTrial", "SetupSession"]
)
@pytest.mark.parametrize("succeeded", [True, False])
async def test_worker_completion_routes_only_setup_to_controller(method, succeeded):
    clock = Clock()
    identity = Identity(
        *(
            pb.ProcessIdentity(role=role, generation=str(uuid4()))
            for role in (
                "visual_stimulus",
                "controller",
                "supervisor",
                "visual_stimulus_renderer",
            )
        )
    )
    state = State()
    controller, supervisor = Peer(), Peer()
    ledger = command_ledger(identity.process.generation, 10**12, 1_000_000)
    parent = wire.BackendCommand(command_id=str(uuid4()), target=identity.backend)
    if method != "InitializeDisplay":
        parent.work.session.CopyFrom(
            pb.SessionContext(
                controller_generation=identity.controller.generation,
                session_id=str(uuid4()),
            )
        )
    child = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        target=visual_stimulus.WorkerContext(
            worker=identity.worker, owner=identity.process, work=parent.work
        ),
    )
    state.links[child.command_id] = CommandLink(method, parent, child, clock() + 10**9)
    ledger.admit(
        parent.command_id,
        parent.SerializeToString(),
        clock(),
        work_key=parent.work.session.session_id or parent.command_id,
    )
    ledger.complete(
        parent.command_id,
        pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED).SerializeToString(),
        clock(),
    )
    reports = Reports(identity, state, ledger, controller, supervisor, clock)
    await reports.operation(
        visual_stimulus.WorkerOperation(
            source=child.target,
            operation=pb.OperationState(
                context=pb.OperationContext(command_id=child.command_id),
                complete=True,
                succeeded=succeeded,
                failure=pb.Failure(code="TEST_FAILURE") if not succeeded else None,
            ),
        )
    )
    assert len(controller.reports) == int(method == "SetupSession")
    if controller.reports:
        assert (
            controller.reports[0][1].operation.operation.context.command_id
            == parent.command_id
        )
        assert controller.reports[0][1].operation.operation.work == parent.work
    assert len(supervisor.reports) == int(not succeeded)
    assert state.interrupted == (not succeeded)


async def recipe_fixture(tmp_path):
    clock = Clock()
    identity = Identity(
        *(
            pb.ProcessIdentity(role=role, generation=str(uuid4()))
            for role in (
                "visual_stimulus",
                "controller",
                "supervisor",
                "visual_stimulus_renderer",
            )
        )
    )
    trial = pb.TrialContext(
        session=pb.SessionContext(
            controller_generation=identity.controller.generation,
            session_id=str(uuid4()),
        ),
        trial_id=str(uuid4()),
        trial_number=1,
    )
    plan = make_prepared_trial(
        session_id=trial.session.session_id, trial_id=trial.trial_id
    )
    digest, length, data = prepared_digest(plan)
    handle = vp.PreparedHandle(
        plan_sha256=digest, plan_bytes=length, configuration_revision=1
    )
    state = State()
    state.prepared[trial.trial_id] = Prepared(
        trial, data, handle, PreparedRecipe(data, digest), plan
    )
    worker, supervisor = Peer(), Peer()
    ledger = command_ledger(identity.process.generation, 10**12, 1_000_000)
    recipe = RecipeOwner(
        identity, state, worker, supervisor, asyncio.Event(), clock, ledger
    )
    setup = wire.SetupSessionRequest(
        command=wire.BackendCommand(
            command_id=str(uuid4()),
            issuer=identity.controller,
            target=identity.backend,
            work=pb.WorkContext(session=trial.session),
        )
    )
    setup.plan.context.CopyFrom(trial.session)
    setup.plan.trials.add(context=trial)
    state.setup = setup
    await recipe.prepare(setup, clock() + 10**9)
    output = output_plans(identity.backend, list(setup.plan.trials), False)[0]
    output.path = str(tmp_path / "trial_stimulus_LOG.json")
    schedule = wire.ScheduleTrialRequest(
        command=wire.BackendCommand(work=pb.WorkContext(trial=trial)), outputs=[output]
    )
    recipe.scheduled(schedule)
    release = wire.ReleaseTrialRequest(
        command=wire.BackendCommand(
            command_id=str(uuid4()),
            issuer=identity.controller,
            target=identity.backend,
            work=pb.WorkContext(trial=trial),
        ),
        start_monotonic_ns=clock(),
        normal_end_monotonic_ns=clock() + plan.resolved_duration_ns,
    )
    return recipe, state, clock, release, worker, supervisor, ledger


@pytest.mark.asyncio
@pytest.mark.parametrize("attached", [False, True])
async def test_setup_binding_preserves_optional_feedback_presence(tmp_path, attached):
    recipe, state, clock, _, _, _, _ = await recipe_fixture(tmp_path)
    request = state.setup
    if attached:
        request.feedback_attachment.SetInParent()
    forwarded, link = bind_command(
        recipe.identity, state, "SetupSession", request, clock() + 10**9
    )
    assert forwarded.HasField("feedback_attachment") == attached
    assert forwarded.command.target.work == request.command.work
    assert link.parent.command_id == request.command.command_id
    if attached:
        assert forwarded.feedback_attachment == request.feedback_attachment


@pytest.mark.asyncio
async def test_recipe_setup_initializes_exact_empty_catalogue_before_obligations(
    tmp_path,
):
    recipe, state, clock, _, _, supervisor, _ = await recipe_fixture(tmp_path)
    source = recipe.identity.process
    registry = ResourceObligationRegistry(
        source,
        state.setup.command.work,
        allowed_owners=frozenset({(source.role, source.generation)}),
        max_resources=10,
        max_bytes=10_000,
    )
    assert len(supervisor.reports) == 2
    for expected_revision, (method, report, deadline) in enumerate(supervisor.reports):
        assert method == "ReportHeartbeat"
        assert report.work == state.setup.command.work
        assert deadline == clock() + 10**9
        assert registry.accept_heartbeat(report) == expected_revision
    assert registry.obligations == tuple(state.resources)
    # Each new session starts at revision zero even after a completed prior session.
    state.resources.clear()
    state.catalogue_revision = 12
    await recipe.prepare(state.setup, clock() + 10**9)
    assert supervisor.reports[-2][1].cleanup_resources_revision == 0
    assert not supervisor.reports[-2][1].cleanup_resources
    assert state.catalogue_revision == 1


@pytest.mark.asyncio
async def test_save_off_recipe_uses_exact_retained_bytes_and_private_confirmation(
    tmp_path,
):
    recipe, state, clock, release, worker, supervisor, ledger = await recipe_fixture(
        tmp_path
    )
    recipe.start(release, clock() + 10**9, clock() + 100_000_000)
    await asyncio.sleep(0)
    assert not list(tmp_path.iterdir())
    recipe.confirm_release(release.command.work.trial.trial_id)
    await recipe.drain(clock() + 10**9)
    tid = release.command.work.trial.trial_id
    result = state.recipe_results[tid]
    assert result.closure == pb.OUTPUT_CLOSURE_CLOSED and result.artifact_present
    assert (tmp_path / "trial_stimulus_LOG.json").read_bytes() == state.prepared[
        tid
    ].data
    method, publication, _ = worker.commands[0]
    assert method == "ConfirmRecipePublication" and publication.published
    assert publication.command.command_id in state.links
    assert (
        ledger.get(publication.command.command_id).canonical_request
        == publication.SerializeToString()
    )
    assert any(resource.resource == "recipe:" + tid for resource in state.resources)


@pytest.mark.asyncio
async def test_pre_onset_cancellation_discloses_not_started_without_creating_file(
    tmp_path,
):
    recipe, state, clock, release, worker, supervisor, ledger = await recipe_fixture(
        tmp_path
    )
    release.start_monotonic_ns = clock() + 500_000_000
    recipe.start(release, clock() + 10**9, clock() + 100_000_000)
    tid = release.command.work.trial.trial_id
    recipe.confirm_release(tid)
    await asyncio.sleep(0)
    recipe.cancel_trial(tid)
    await recipe.drain(clock() + 10**9)
    assert not list(tmp_path.iterdir())
    assert not worker.commands
    assert state.recipe_results[tid].closure == pb.OUTPUT_CLOSURE_NOT_STARTED
    assert not state.recipe_results[tid].artifact_present


@pytest.mark.asyncio
async def test_interruption_wakes_pending_release_confirmation(tmp_path):
    recipe, state, clock, release, worker, supervisor, ledger = await recipe_fixture(
        tmp_path
    )
    release.start_monotonic_ns = clock() + 500_000_000
    recipe.start(release, clock() + 10**9, clock() + 100_000_000)
    await asyncio.sleep(0)
    recipe.interrupt()
    await recipe.drain(clock() + 10**9)
    assert not list(tmp_path.iterdir())
    assert not worker.commands
    assert state.recipe_results[release.command.work.trial.trial_id].closure == (
        pb.OUTPUT_CLOSURE_NOT_STARTED
    )


def test_post_onset_reports_use_lifecycle_deadlines_not_release_rpc_deadline():
    clock = Clock()
    identity = Identity(
        *(
            pb.ProcessIdentity(role=role, generation=str(uuid4()))
            for role in (
                "visual_stimulus",
                "controller",
                "supervisor",
                "visual_stimulus_renderer",
            )
        )
    )
    state = State(
        setup=wire.SetupSessionRequest(),
        release=wire.ReleaseTrialRequest(
            start_monotonic_ns=1000, normal_end_monotonic_ns=5000
        ),
    )
    state.setup.plan.policies.start_evidence_allowance_ns = 200
    state.setup.plan.policies.stop_evidence_allowance_ns = 300
    state.setup.plan.policies.trial_finished.initial_ns = 400
    reports = Reports(
        identity,
        state,
        command_ledger(identity.process.generation, 10**12, 1_000_000),
        Peer(),
        Peer(),
        clock,
    )
    assert reports.lifecycle_deadline("started", pb.StartedReport(), 900) == 1200
    assert (
        reports.lifecycle_deadline(
            "stopped", pb.StoppedReport(actual_stop_monotonic_ns=4000), 900
        )
        == 4300
    )
    assert reports.lifecycle_deadline("finished", pb.FinishedReport(), 900) == 5400


@pytest.mark.asyncio
async def test_missing_release_execution_receipt_keeps_recipe_outcome_unknown(tmp_path):
    recipe, state, clock, release, worker, supervisor, ledger = await recipe_fixture(
        tmp_path
    )
    recipe.start(release, clock() + 10**9, clock())
    await recipe.drain(clock() + 10**9)
    result = state.recipe_results[release.command.work.trial.trial_id]
    assert result.closure == pb.OUTPUT_CLOSURE_UNCONFIRMED
    assert not result.HasField("artifact_present")
    assert state.interrupted and not list(tmp_path.iterdir())
    assert supervisor.reports[-1][0] == "ReportError"
    assert supervisor.reports[-1][1].failure.code == "RELEASE_UNCONFIRMED"


def _setup_with_policy_version(
    identity: Identity, version: int
) -> wire.SetupSessionRequest:
    session = pb.SessionContext(
        controller_generation=identity.controller.generation, session_id=str(uuid4())
    )
    request = wire.SetupSessionRequest(
        command=wire.BackendCommand(
            command_id=str(uuid4()),
            issuer=identity.controller,
            target=identity.backend,
            work=pb.WorkContext(session=session),
        )
    )
    request.plan.context.CopyFrom(session)
    request.settings.backend_name = "visual_stimulus"
    request.settings.visual_stimulus.SetInParent()
    request.visual_stimulus_policies.contract_version = version
    return request


@pytest.mark.parametrize("version", [0, CONTRACT_VERSION + 1])
def test_setup_with_the_wrong_file_policy_contract_version_is_rejected(
    version: int,
) -> None:
    identity = Identity(
        *(
            pb.ProcessIdentity(role=role, generation=str(uuid4()))
            for role in (
                "visual_stimulus",
                "controller",
                "supervisor",
                "visual_stimulus_renderer",
            )
        )
    )
    validate(
        identity,
        State(),
        "SetupSession",
        _setup_with_policy_version(identity, CONTRACT_VERSION),
    )
    with pytest.raises(ValueError, match="file policy version"):
        validate(
            identity,
            State(),
            "SetupSession",
            _setup_with_policy_version(identity, version),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("succeeded", [False, True])
async def test_release_waits_for_exact_schedule_completion(succeeded):
    from cephvr.visual_stimulus.coordinator.commands import wait_schedule_completion

    ledger = command_ledger(str(uuid4()), 10**12, 1_000_000)
    command_id = str(uuid4())
    work = pb.WorkContext(trial=pb.TrialContext(trial_id=str(uuid4())))
    ledger.admit(command_id, b"schedule", 1, work_key=work.trial.trial_id)
    task = asyncio.create_task(
        wait_schedule_completion(ledger, command_id, work, 1_000_000_000, lambda: 1)
    )
    await asyncio.sleep(0.01)
    assert not task.done()
    result = pb.OperationState(
        context=pb.OperationContext(command_id=command_id),
        command="ScheduleTrial",
        work=work,
        complete=True,
        succeeded=succeeded,
        failure=pb.Failure(message="launch failed") if not succeeded else None,
    )
    ledger.complete_executor(command_id, result.SerializeToString(), 2)
    if succeeded:
        await task
    else:
        with pytest.raises(RuntimeError, match="launch failed"):
            await task


@pytest.mark.asyncio
async def test_started_evidence_preserves_exact_trial_preparation_parent():
    clock = Clock()
    identity = Identity(
        *(
            pb.ProcessIdentity(role=role, generation=str(uuid4()))
            for role in (
                "visual_stimulus",
                "controller",
                "supervisor",
                "visual_stimulus_renderer",
            )
        )
    )
    work = pb.WorkContext(trial=pb.TrialContext(trial_id=str(uuid4())))
    state = State(
        setup=wire.SetupSessionRequest(),
        release=wire.ReleaseTrialRequest(
            start_monotonic_ns=clock(), normal_end_monotonic_ns=clock() + 10**9
        ),
    )
    state.setup.plan.policies.start_evidence_allowance_ns = 10**9
    prepare_id, schedule_id = str(uuid4()), str(uuid4())
    for method, parent in (
        ("PrepareTrial", prepare_id),
        ("ScheduleTrial", schedule_id),
    ):
        child = visual_stimulus.WorkerCommand(
            command_id=str(uuid4()),
            target=visual_stimulus.WorkerContext(
                worker=identity.worker, owner=identity.process, work=work
            ),
        )
        state.links[child.command_id] = CommandLink(
            method,
            wire.BackendCommand(command_id=parent, work=work),
            child,
            clock() + 10**9,
        )
    scheduled = next(
        item for item in state.links.values() if item.method == "ScheduleTrial"
    )
    peer = Peer()
    reports = Reports(
        identity,
        state,
        command_ledger(identity.process.generation, 10**12, 1_000_000),
        peer,
        Peer(),
        clock,
    )
    evidence = visual_stimulus.WorkerLifecycle(
        source=identity.worker,
        report=pb.LifecycleReport(
            started=pb.StartedReport(
                context=pb.ReportContext(
                    backend=identity.backend,
                    work=work,
                    operation=pb.OperationContext(
                        command_id=scheduled.child.command_id
                    ),
                )
            )
        ),
    )
    await reports.lifecycle(evidence)
    assert peer.reports[-1][1].started.context.operation.command_id == prepare_id
    assert ("started", prepare_id) in state.reports
    assert ("started", schedule_id) not in state.reports
