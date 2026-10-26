"""Coordinator artifact ownership, release confirmation and lifecycle deadlines."""

from __future__ import annotations

import asyncio
import hashlib
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
from cephvr.visual_stimulus.runtime import VisualStimulusCoordinatorRuntime
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus
from cephvr.visual_stimulus.v1 import runtime_pb2 as vp
from cephvr.visual_stimulus.worker.reporting import ReportBridge

from .support import Clock, make_prepared_trial, valid_display_json


@pytest.mark.parametrize("scope", ("session", "trial", "none"))
def test_unprepared_cancel_accepts_only_session_cleanup(scope):
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
    request = wire.BackendCommand(
        command_id=str(uuid4()), issuer=identity.controller, target=identity.backend
    )
    if scope == "session":
        request.work.session.session_id = str(uuid4())
    elif scope == "trial":
        request.work.trial.trial_id = str(uuid4())
    if scope == "session":
        validate(identity, State(), "CancelSetup", request)
    else:
        with pytest.raises(ValueError, match="no open calibration"):
            validate(identity, State(), "CancelSetup", request)


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


async def test_renderer_report_failure_identifies_rpc_and_retains_deadline():
    class FailingPeer(Peer):
        async def receipt(self, method, request, *, deadline_ns):
            assert deadline_ns == 123456789
            raise TimeoutError("deadline exceeded")

    bridge = ReportBridge(
        asyncio.get_running_loop(),
        FailingPeer(),
        Peer(),
        failed=lambda error: None,
        maximum_bytes=1024,
    )
    with pytest.raises(
        RuntimeError, match="ReportWorkerHeartbeat receipt failed"
    ) as error:
        await bridge._deliver("ReportWorkerHeartbeat", pb.HeartbeatReport(), 123456789)
    assert isinstance(error.value.__cause__, TimeoutError)
    assert "budget_ms=" in str(error.value)
    assert "elapsed_ms=" in str(error.value)


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
@pytest.mark.parametrize(
    "display_rejection", [None, "confirmed", "unreleased", "stale"]
)
async def test_worker_completion_routes_only_setup_to_controller(
    method, succeeded, display_rejection
):
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
    if display_rejection is not None:
        state.display = pb.VisualStimulusDisplayView(
            command_id=str(uuid4())
            if display_rejection == "stale"
            else parent.command_id,
            complete=True,
            issues=[
                pb.FieldIssue(failure=pb.Failure(code="DISPLAY_OUTPUT_UNAVAILABLE"))
            ],
            resources=[
                pb.ResourceRelease(
                    resource="display:main", released=display_rejection != "unreleased"
                )
            ],
        )
    await reports.operation(
        visual_stimulus.WorkerOperation(
            source=child.target,
            operation=pb.OperationState(
                context=pb.OperationContext(command_id=child.command_id),
                complete=True,
                succeeded=succeeded,
                failure=pb.Failure(
                    code="DISPLAY_OUTPUT_UNAVAILABLE"
                    if display_rejection
                    else "TEST_FAILURE"
                )
                if not succeeded
                else None,
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
    recovered_display = (
        method == "InitializeDisplay" and display_rejection == "confirmed"
    )
    setup_rejection = method == "SetupSession"
    assert len(supervisor.reports) == int(
        not succeeded and not recovered_display and not setup_rejection
    )
    assert state.interrupted is (
        not succeeded and not recovered_display and not setup_rejection
    )


@pytest.mark.parametrize(
    "mismatch",
    [
        None,
        "missing",
        "command",
        "unknown",
        "not_presented",
        "sequence",
        "diagnostic",
        "revision",
        "renderer",
        "controller",
        "incomplete",
        "generic_failure",
        "wrong_method",
        "session_work",
        "setup",
    ],
)
async def test_rejected_update_requires_exact_retained_active_display_proof(mismatch):
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
    parent = wire.BackendCommand(
        command_id=str(uuid4()), issuer=identity.controller, target=identity.backend
    )
    child = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        target=visual_stimulus.WorkerContext(
            worker=identity.worker, owner=identity.process, configuration_revision=4
        ),
    )
    diagnostic = str(uuid4())
    link = CommandLink(
        "UpdateDisplayCalibration",
        parent,
        child,
        clock() + 10**9,
        diagnostic_id=diagnostic,
        output_ids=frozenset({"projector/main"}),
        adjustment_sequence=2,
    )
    state.links[child.command_id] = link
    ledger.admit(
        parent.command_id,
        parent.SerializeToString(),
        clock(),
        work_key=parent.command_id,
    )
    ledger.complete(
        parent.command_id,
        pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED).SerializeToString(),
        clock(),
    )
    reports = Reports(identity, state, ledger, controller, supervisor, clock)
    prior = pb.VisualStimulusDisplayView()
    prior.calibration.diagnostic_id = diagnostic
    prior.calibration.adjustment_sequence = 1
    state.display = prior
    report = pb.VisualStimulusDisplayView(
        command_id=child.command_id,
        source=identity.worker,
        backend=identity.backend,
        controller=identity.controller,
        requested_revision=4,
        complete=True,
    )
    report.outputs.add(output_id="projector/main")
    report.calibration.CopyFrom(
        vp.DisplayCalibrationEvidence(
            diagnostic_id=diagnostic,
            configuration_revision=4,
            controller_generation=identity.controller.generation,
            renderer_generation=identity.worker.generation,
            state=vp.DISPLAY_CALIBRATION_STATE_ACTIVE,
            presented=True,
            adjustment_sequence=1,
            failure_code="CALIBRATION_ADJUSTMENT_REJECTED",
        )
    )
    await reports.display(report)
    saved = state.display
    if mismatch == "missing":
        state.display = None
    elif mismatch == "command":
        saved.command_id = str(uuid4())
    elif mismatch == "unknown":
        saved.calibration.state = vp.DISPLAY_CALIBRATION_STATE_UNKNOWN
    elif mismatch == "not_presented":
        saved.calibration.presented = False
    elif mismatch == "sequence":
        saved.calibration.adjustment_sequence = 2
    elif mismatch == "diagnostic":
        saved.calibration.diagnostic_id = str(uuid4())
    elif mismatch == "revision":
        saved.calibration.configuration_revision = 5
    elif mismatch == "renderer":
        saved.calibration.renderer_generation = str(uuid4())
    elif mismatch == "controller":
        saved.calibration.controller_generation = str(uuid4())
    elif mismatch == "incomplete":
        saved.complete = False
    elif mismatch == "wrong_method":
        link.method = "OpenDisplayCalibration"
    elif mismatch == "session_work":
        parent.work.session.session_id = str(uuid4())
    elif mismatch == "setup":
        state.setup = wire.SetupSessionRequest()
    operation = pb.OperationState(
        context=pb.OperationContext(command_id=child.command_id),
        command=link.method,
        complete=True,
        succeeded=False,
        failure=pb.Failure(
            code="VISUAL_STIMULUS_OPERATION"
            if mismatch == "generic_failure"
            else "CALIBRATION_ADJUSTMENT_REJECTED"
        ),
    )
    await reports.operation(
        visual_stimulus.WorkerOperation(source=child.target, operation=operation)
    )
    assert state.interrupted is (mismatch is not None)
    assert len(supervisor.reports) == int(mismatch is not None)
    terminal = pb.OperationState.FromString(
        ledger.get(parent.command_id).executor_result
    )
    assert terminal.complete and not terminal.succeeded
    assert terminal.context.command_id == parent.command_id


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


def _cleanup_evidence(recipe, state, clock):
    identity = recipe.identity
    session = state.setup.plan.context
    work = pb.WorkContext(session=session)
    child = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        target=visual_stimulus.WorkerContext(
            worker=identity.worker, owner=identity.process, work=work
        ),
    )
    parent = wire.BackendCommand(
        command_id=str(uuid4()),
        issuer=identity.supervisor,
        target=identity.backend,
        work=work,
    )
    link = CommandLink("Cleanup", parent, child, clock() + 10**9)
    state.links[child.command_id] = link
    report = pb.LifecycleReport(
        cleanup=pb.CleanupReport(
            source=identity.worker,
            work=work,
            operation=pb.OperationContext(command_id=child.command_id),
            trial_activity_stopped=True,
        )
    )
    return visual_stimulus.WorkerLifecycle(source=identity.worker, report=report), link


def _open_calibration_request(identity, diagnostic_id):
    profile_json = valid_display_json()
    policies = vp.VisualStimulusFilePolicies(contract_version=CONTRACT_VERSION)
    policies.limits.max_document_bytes = 1_000_000
    return wire.VisualStimulusDisplayCalibrationOpenRequest(
        command_id=str(uuid4()),
        issuer=identity.controller,
        target=identity.backend,
        configuration_revision=1,
        diagnostic_id=diagnostic_id,
        profile_json=profile_json,
        profile_sha256=hashlib.sha256(profile_json.encode()).hexdigest(),
        policies=policies,
    )


def _fresh_setup_request(identity, previous):
    request = wire.SetupSessionRequest.FromString(previous.SerializeToString())
    request.command.command_id = str(uuid4())
    request.plan.context.session_id = str(uuid4())
    request.command.work.session.CopyFrom(request.plan.context)
    request.settings.backend_name = "visual_stimulus"
    request.settings.visual_stimulus.SetInParent()
    request.visual_stimulus_policies.contract_version = CONTRACT_VERSION
    return request


def _same_session_setup_request(previous):
    request = wire.SetupSessionRequest.FromString(previous.SerializeToString())
    request.command.command_id = str(uuid4())
    return request


def _confirm_recipe_outputs(recipe, state):
    for trial_id, plan in recipe.plans.items():
        state.recipe_results[trial_id] = pb.OutputResult(
            output_key=plan.output_key,
            path=plan.path,
            closure=pb.OUTPUT_CLOSURE_CLOSED,
            artifact_present=True,
        )
    assert recipe.cleanup_results()


def _retained_display_scope(identity, state, ledger, clock, diagnostic_id):
    command_id = str(uuid4())
    child = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        target=visual_stimulus.WorkerContext(
            worker=identity.worker, owner=identity.process
        ),
    )
    parent = wire.BackendCommand(
        command_id=command_id,
        issuer=identity.controller,
        target=identity.backend,
    )
    state.links[child.command_id] = CommandLink(
        "OpenDisplayCalibration",
        parent,
        child,
        clock() + 10**9,
        diagnostic_id=diagnostic_id,
        output_ids=frozenset({"projector/main"}),
    )
    ledger.admit(command_id, b"open-calibration", clock(), work_key=diagnostic_id)
    ledger.complete(command_id, b"accepted", clock())
    return command_id


@pytest.mark.asyncio
async def test_cleanup_retry_gates_new_setup_until_both_receipts_accept(tmp_path):
    class ControllerPeer(Peer):
        accept_cleanup = False

        async def receipt(self, method, request, *, deadline_ns):
            self.reports.append((method, request, deadline_ns))
            return pb.ReportReceipt(
                result=(
                    pb.COMMAND_RESULT_ACCEPTED
                    if self.accept_cleanup
                    else pb.COMMAND_RESULT_REJECTED
                )
            )

    recipe, state, clock, _, _, supervisor, ledger = await recipe_fixture(tmp_path)
    identity = recipe.identity
    controller = ControllerPeer()
    reports = Reports(identity, state, ledger, controller, supervisor, clock)
    old_setup = wire.SetupSessionRequest.FromString(state.setup.SerializeToString())
    _confirm_recipe_outputs(recipe, state)
    evidence, cleanup_link = _cleanup_evidence(recipe, state, clock)
    old_diagnostic = str(uuid4())
    old_scope_command = _retained_display_scope(
        identity, state, ledger, clock, old_diagnostic
    )

    with pytest.raises(ValueError, match="was not accepted"):
        await reports.lifecycle(evidence)
    assert state.setup is not None
    assert ("cleanup", cleanup_link.parent.command_id) in state.worker_reports
    fresh_setup = _fresh_setup_request(identity, old_setup)
    with pytest.raises(ValueError, match="previous Visual Stimulus session"):
        validate(identity, state, "SetupSession", fresh_setup)
    blocked_open = _open_calibration_request(identity, str(uuid4()))
    with pytest.raises(ValueError, match="unavailable during a session"):
        validate(identity, state, "OpenDisplayCalibration", blocked_open)

    controller.accept_cleanup = True
    await reports.lifecycle(evidence)
    assert state.setup is None
    old_session = cleanup_link.parent.work.session
    assert old_session.SerializeToString(deterministic=True) in state.retired_sessions
    with pytest.raises(ValueError, match="retired Visual Stimulus session"):
        validate(
            identity, state, "SetupSession", _same_session_setup_request(old_setup)
        )
    assert ledger.get(old_scope_command).completed_ns > 0
    assert ledger.get(old_scope_command).finalized_ns is not None
    clock.value += ledger.retention_ns + 1
    ledger.prune(clock())
    assert ledger.get(old_scope_command) is None

    validate(identity, state, "SetupSession", fresh_setup)
    fresh_diagnostic = _open_calibration_request(identity, str(uuid4()))
    validate(identity, state, "OpenDisplayCalibration", fresh_diagnostic)
    _, fresh_link = bind_command(
        identity, state, "OpenDisplayCalibration", fresh_diagnostic, clock() + 10**9
    )
    assert fresh_link.output_ids
    ledger.admit(
        fresh_diagnostic.command_id,
        fresh_diagnostic.SerializeToString(deterministic=True),
        clock(),
        work_key=fresh_diagnostic.diagnostic_id,
    )
    assert ledger.get(fresh_diagnostic.command_id).finalized_ns is None


@pytest.mark.asyncio
async def test_retired_cleanup_replay_preserves_fresh_state_and_ignores_old_heartbeat(
    tmp_path,
):
    recipe, state, clock, _, worker, supervisor, ledger = await recipe_fixture(tmp_path)
    identity = recipe.identity
    old_setup = wire.SetupSessionRequest.FromString(state.setup.SerializeToString())
    _confirm_recipe_outputs(recipe, state)
    cleanup_evidence, cleanup_link = _cleanup_evidence(recipe, state, clock)
    controller = Peer()
    reports = Reports(identity, state, ledger, controller, supervisor, clock)
    await reports.lifecycle(cleanup_evidence)
    assert state.setup is None

    fresh_diagnostic = _open_calibration_request(identity, str(uuid4()))
    runtime = VisualStimulusCoordinatorRuntime(
        identity=identity,
        worker=worker,
        controller=controller,
        supervisor=supervisor,
        ledger=ledger,
        clock=clock,
    )
    runtime.state = state
    runtime.reports = reports
    runtime.recipes = recipe

    async def unexpected_drain(*_args, **_kwargs):
        raise AssertionError("retained Cleanup replay must not drain new recipe work")

    def unexpected_cleanup_results():
        raise AssertionError("retained Cleanup replay must not clear recipe results")

    recipe.drain = unexpected_drain
    recipe.cleanup_results = unexpected_cleanup_results
    runtime.recovery_deadline_ns = clock() + 10**9
    opened = await runtime.execute(
        "OpenDisplayCalibration", fresh_diagnostic, deadline_ns=clock() + 10**9
    )
    assert opened.result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime.recovery_deadline_ns is None
    ledger.admit(
        fresh_diagnostic.command_id,
        fresh_diagnostic.SerializeToString(deterministic=True),
        clock(),
        work_key=fresh_diagnostic.diagnostic_id,
    )
    fresh_scope = ledger.get(fresh_diagnostic.command_id)
    assert fresh_scope is not None and fresh_scope.finalized_ns is None
    assert fresh_scope.completed_ns is None

    state.display = pb.VisualStimulusDisplayView(
        command_id=fresh_diagnostic.command_id,
        source=identity.worker,
        backend=identity.backend,
        complete=True,
    )
    state.display.calibration.diagnostic_id = fresh_diagnostic.diagnostic_id
    state.display.calibration.state = vp.DISPLAY_CALIBRATION_STATE_ACTIVE
    display_before = pb.VisualStimulusDisplayView.FromString(
        state.display.SerializeToString()
    )
    runtime.recovery_deadline_ns = clock() + 10**9
    close_request = wire.VisualStimulusDisplayCalibrationCloseRequest(
        command_id=str(uuid4()),
        issuer=identity.controller,
        target=identity.backend,
        diagnostic_id=fresh_diagnostic.diagnostic_id,
    )
    await runtime.execute(
        "CloseDisplayCalibration", close_request, deadline_ns=clock() + 10**9
    )
    assert runtime.recovery_deadline_ns == clock() + 10**9
    state.display.calibration.state = vp.DISPLAY_CALIBRATION_STATE_IDLE
    display_before = pb.VisualStimulusDisplayView.FromString(
        state.display.SerializeToString()
    )

    state.setup = _fresh_setup_request(identity, old_setup)
    fresh_context = pb.SessionContext.FromString(
        state.setup.plan.context.SerializeToString()
    )
    state.cleanup = None
    fresh_trial_id = str(uuid4())
    state.recipe_results[fresh_trial_id] = pb.OutputResult(
        output_key="fresh-output",
        closure=pb.OUTPUT_CLOSURE_CLOSED,
        artifact_present=True,
    )
    state.active_trial = fresh_trial_id
    fresh_result = pb.OutputResult.FromString(
        state.recipe_results[fresh_trial_id].SerializeToString()
    )

    await runtime.report("ReportWorkerLifecycle", cleanup_evidence, ingress_ns=clock())
    assert state.setup.plan.context == fresh_context
    assert state.display == display_before
    assert state.recipe_results[fresh_trial_id] == fresh_result
    assert state.active_trial == fresh_trial_id
    assert ledger.get(fresh_diagnostic.command_id).finalized_ns is None
    assert runtime.recovery_deadline_ns == clock() + 10**9

    old_session = cleanup_link.parent.work.session
    prior_heartbeat = pb.HeartbeatReport(
        source=identity.worker,
        work=pb.WorkContext(session=old_session),
        sent_monotonic_ns=clock(),
        session_phase=pb.SESSION_PHASE_CONFIGURATION,
        cleanup_resources_revision=state.retired_sessions[
            old_session.SerializeToString(deterministic=True)
        ],
    )
    state.worker_heartbeat = prior_heartbeat
    stale_empty = pb.HeartbeatReport(
        source=identity.worker,
        sent_monotonic_ns=clock(),
        session_phase=pb.SESSION_PHASE_CONFIGURATION,
        cleanup_resources_revision=prior_heartbeat.cleanup_resources_revision,
    )
    supervisor_count = len(supervisor.reports)
    await reports.heartbeat(stale_empty, clock() + 1)
    assert state.worker_heartbeat == prior_heartbeat
    assert state.worker_ingress_ns == clock() + 1
    assert len(supervisor.reports) == supervisor_count


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
@pytest.mark.parametrize("recording", [False, True])
async def test_recipe_setup_and_worker_growth_pass_real_catalogue_validation(
    tmp_path, recording
):
    recipe, state, clock, _, _, supervisor, ledger = await recipe_fixture(tmp_path)
    identity, setup = recipe.identity, state.setup
    state.resources.clear()
    state.catalogue_revision = 12
    supervisor.reports.clear()
    setup.plan.configuration.backends.add(
        backend_name="visual_stimulus",
        enabled=True,
        visual_stimulus=pb.VisualStimulusSettings(save_visual_stimulus_data=recording),
    )
    registry = ResourceObligationRegistry(
        identity.process,
        setup.command.work,
        allowed_owners=frozenset(
            (owner.role, owner.generation)
            for owner in (identity.process, identity.worker)
        ),
        max_resources=10,
        max_bytes=10_000,
    )
    receipt = supervisor.receipt

    async def validate_catalogue(method, request, *, deadline_ns):
        assert method == "ReportHeartbeat"
        registry.accept_heartbeat(request)
        return await receipt(method, request, deadline_ns=deadline_ns)

    supervisor.receipt = validate_catalogue
    await recipe.prepare(setup, clock() + 10**9)
    assert state.catalogue_revision == int(recording)
    assert len(supervisor.reports) == 1 + int(recording)
    assert bool(recipe.plans) is recording
    reports = Reports(identity, state, ledger, Peer(), supervisor, clock)
    heartbeat = pb.HeartbeatReport(
        source=identity.worker,
        work=setup.command.work,
        sent_monotonic_ns=clock(),
        session_phase=pb.SESSION_PHASE_SETTING_UP,
        cleanup_resources_revision=1,
        cleanup_resources=[
            pb.ResourceObligation(
                owner=identity.worker, resource="visual_stimulus:renderer"
            )
        ],
    )
    await reports.heartbeat(heartbeat, clock())
    assert registry.revision == 1 + int(recording)
    assert registry.obligations == tuple(state.resources)
    # Identical worker heartbeats must not manufacture another catalogue revision.
    await reports.heartbeat(heartbeat, clock())
    assert registry.revision == 1 + int(recording)
    assert not list(tmp_path.iterdir())


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


@pytest.mark.parametrize(
    "calibration_view", ["frame_grid", "photodiode_placement", "blackout_placement"]
)
def test_live_calibration_bind_preserves_identity_and_rejects_stale_updates(
    calibration_view,
):
    from cephvr.visual_stimulus.transport.messages import worker_command

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
    state.display = pb.VisualStimulusDisplayView()
    state.display.outputs.add(output_id="projector/main")
    evidence = state.display.calibration
    evidence.diagnostic_id = str(uuid4())
    evidence.configuration_revision = 4
    evidence.state = vp.DISPLAY_CALIBRATION_STATE_ACTIVE
    evidence.calibration_view = calibration_view
    request = wire.VisualStimulusDisplayCalibrationUpdateRequest(
        command_id=str(uuid4()),
        issuer=identity.controller,
        target=identity.backend,
        configuration_revision=4,
        diagnostic_id=evidence.diagnostic_id,
        adjustment_sequence=1,
    )
    request.adjustments.add(
        mapping_id="diagnostic_front",
        destination_xy=[0.1, 0.1, 0.9, 0.1, 0.1, 0.9, 0.9, 0.9],
    )
    import json

    if calibration_view != "frame_grid":
        request.ClearField("adjustments")
        request.placement_json = json.dumps(
            dict(
                outputs=[dict(output_id="projector/main", blackout_zones=[])],
                **(
                    dict(
                        photodiode_output_id="projector/main",
                        photodiode_patch=dict(
                            rect=dict(x=1, y=1, width=2, height=2),
                            high_linear_rgb=[1, 1, 1],
                            low_linear_rgb=[0, 0, 0],
                        ),
                    )
                    if calibration_view == "photodiode_placement"
                    else {}
                ),
            )
        )
    validate(identity, state, "UpdateDisplayCalibration", request)
    child, link = bind_command(
        identity, state, "UpdateDisplayCalibration", request, 123456
    )
    assert isinstance(child, visual_stimulus.UpdateDisplayCalibrationCommand)
    assert child.diagnostic_id == evidence.diagnostic_id
    assert child.placement_json == request.placement_json
    assert worker_command(child).target.configuration_revision == 4
    assert link.deadline_ns == 123456 and link.adjustment_sequence == 1
    assert link.output_ids == frozenset({"projector/main"})
    evidence.adjustment_sequence = 1
    with pytest.raises(ValueError, match="stale"):
        bind_command(identity, state, "UpdateDisplayCalibration", request, 123456)
    request.adjustment_sequence = 2
    request.issuer.CopyFrom(identity.supervisor)
    with pytest.raises(ValueError, match="authority"):
        validate(identity, state, "UpdateDisplayCalibration", request)
    request.issuer.CopyFrom(identity.controller)
    evidence.calibration_view = "reference_bars"
    with pytest.raises(ValueError, match="inactive"):
        bind_command(identity, state, "UpdateDisplayCalibration", request, 123456)
    evidence.calibration_view = calibration_view
    state.interrupted = True
    with pytest.raises(ValueError, match="fenced"):
        validate(identity, state, "UpdateDisplayCalibration", request)


async def test_setup_progress_maps_worker_command_without_completing_it():
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
    parent = wire.BackendCommand(
        command_id=str(uuid4()),
        target=identity.backend,
        work=pb.WorkContext(session=pb.SessionContext(session_id=str(uuid4()))),
    )
    child = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        target=visual_stimulus.WorkerContext(
            worker=identity.worker,
            owner=identity.process,
            work=parent.work,
        ),
    )
    state = State(
        links={child.command_id: CommandLink("SetupSession", parent, child, 1234)}
    )
    controller, supervisor = Peer(), Peer()
    reports = Reports(
        identity,
        state,
        command_ledger(identity.process.generation, 10**12, 1_000_000),
        controller,
        supervisor,
        Clock(),
    )
    report = visual_stimulus.WorkerOperation(
        source=child.target,
        operation=pb.OperationState(
            context=pb.OperationContext(command_id=child.command_id),
            command="SetupSession",
            work=child.target.work,
            progress="Decoding textures: 50/500",
        ),
    )
    await reports.operation(report)
    method, forwarded, deadline = controller.reports[-1]
    assert method == "ReportLifecycle" and deadline == 1234
    assert forwarded.operation.source == identity.backend
    assert forwarded.operation.operation.context.command_id == parent.command_id
    assert forwarded.operation.operation.work == parent.work
    assert forwarded.operation.operation.progress == report.operation.progress
    assert not forwarded.operation.operation.complete
    assert not state.prepared and not supervisor.reports
    report.source.worker.generation = "foreign"
    with pytest.raises(ValueError, match="retained command"):
        await reports.operation(report)


async def test_optional_progress_handoff_is_bounded_and_delivery_failure_is_nonfatal():
    gate = asyncio.Event()
    entered = asyncio.Event()
    failures = []

    class SlowPeer(Peer):
        async def receipt(self, method, request, *, deadline_ns):
            self.reports.append((method, request, deadline_ns))
            entered.set()
            await gate.wait()
            raise TimeoutError("progress unavailable")

    peer = SlowPeer()
    bridge = ReportBridge(
        asyncio.get_running_loop(),
        peer,
        Peer(),
        failed=failures.append,
        maximum_bytes=1024,
        maximum_reports=2,
    )
    bridge.send(
        "ReportWorkerOperation", visual_stimulus.WorkerOperation(), 1234, required=False
    )
    await entered.wait()
    for _ in range(100):
        bridge.send(
            "ReportWorkerOperation",
            visual_stimulus.WorkerOperation(),
            1234,
            required=False,
        )
    assert len(bridge.pending) == 1
    assert len(peer.reports) == 1
    gate.set()
    from cephvr.shared.clock import host_time_ns

    await bridge.drain(host_time_ns() + 1_000_000_000)
    assert not failures and not bridge.pending
