"""Coordinator artifact ownership, release confirmation and lifecycle deadlines."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.visual_stimulus.compiler import prepared_digest
from cephvr.visual_stimulus.coordinator.commands import validate
from cephvr.visual_stimulus.coordinator.obligations import output_plans
from cephvr.visual_stimulus.coordinator.recipes import RecipeOwner
from cephvr.visual_stimulus.coordinator.reports import Reports
from cephvr.visual_stimulus.coordinator.state import Identity, Prepared, State
from cephvr.visual_stimulus.identity import CONTRACT_VERSION
from cephvr.visual_stimulus.main import command_ledger
from cephvr.visual_stimulus.recording.recipe import PreparedRecipe
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
