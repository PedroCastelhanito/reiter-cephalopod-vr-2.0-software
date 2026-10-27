"""Scheduled graphics-owner lifecycle with controlled time and native-only adapters."""

from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from cephvr.control.v1 import types_pb2 as pb
from cephvr.visual_stimulus.configuration import load_file_policies
from cephvr.visual_stimulus.rendering.types import (
    ResourceReleaseReport,
    SubmissionSnapshot,
)
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus
from cephvr.visual_stimulus.worker.lifecycle import LifecycleDriver
from cephvr.visual_stimulus.worker.timing import OutputTiming

from .support import (
    Clock,
    Graphics,
    Preparation,
    Recorder,
    Reports,
    _geometric_profiles,
    make_prepared_trial,
    valid_display_json,
)


def prepared_driver(
    saving=False,
    *,
    display_json=None,
    pacing_refresh_hz=None,
    pacing_output_id=None,
):
    clock, reports, recorder = Clock(), Reports(), Recorder()
    owner, worker, controller = (
        pb.ProcessIdentity(role=role, generation=str(uuid4()))
        for role in ("visual_stimulus", "visual_stimulus_renderer", "controller")
    )
    session = pb.SessionContext(session_id=str(uuid4()))
    trial = pb.TrialContext(session=session, trial_id=str(uuid4()))
    artifact = make_prepared_trial(
        session_id=session.session_id, trial_id=trial.trial_id
    )
    graphics = Graphics(clock, artifact)
    policies = pb.ControlPolicies(
        backend_release_offset_ns=10,
        start_evidence_allowance_ns=1_000_000,
        stop_evidence_allowance_ns=1_000_000,
        recovery_ns=10_000_000,
    )
    policies.trial_finished.initial_ns = 10_000_000
    stopped = []
    driver = LifecycleDriver(
        worker=worker,
        owner=owner,
        controller=controller,
        policies=policies,
        engine=graphics,
        preparation=Preparation(artifact),
        recording=recorder,
        reports=reports,
        cancelled=threading.Event(),
        clock=clock,
        shutdown=lambda: stopped.append(True),
    )

    def command(trial_work=False):
        return visual_stimulus.WorkerCommand(
            command_id=str(uuid4()),
            issuer=owner,
            target=visual_stimulus.WorkerContext(
                worker=worker,
                owner=owner,
                configuration_revision=1,
                work=pb.WorkContext(trial=trial)
                if trial_work
                else pb.WorkContext(session=session),
            ),
            deadline_monotonic_ns=clock() + 100_000_000,
        )

    setup = visual_stimulus.WorkerSetup(command=command())
    setup.session.context.CopyFrom(session)
    setup.session.trials.add(context=trial)
    setup.settings.save_visual_stimulus_data = saving
    setup.settings.display.profile_json = display_json or valid_display_json()
    setup.policies.projection.CopyFrom(
        load_file_policies(Path(__file__).resolve().parents[2]).projection
    )
    setup.policies.limits.max_document_bytes = 1_000_000
    if pacing_refresh_hz is not None:
        setup.policies.pacing_refresh_hz = pacing_refresh_hz
    if pacing_output_id is not None:
        setup.policies.pacing_output_id = pacing_output_id
    setup_completion = driver.execute("SetupSession", setup, clock() + 100_000_000)
    assert setup_completion is not None
    for _ in range(100):
        driver.advance(clock())
        if setup_completion.done():
            break
        threading.Event().wait(0.001)
    setup_completion.result(timeout=1)
    handle = driver.state.artifacts[trial.trial_id].handle
    prepare = visual_stimulus.WorkerPrepareTrial(command=command(True), prepared=handle)
    prepare.trial.context.CopyFrom(trial)
    prepare.trial.resolved_duration_ns = artifact.resolved_duration_ns
    driver.execute("PrepareTrial", prepare, clock() + 100_000_000)
    schedule = visual_stimulus.WorkerSchedule(
        command=command(True),
        prepared=handle,
        start_monotonic_ns=clock() + 1_000_000,
        normal_end_monotonic_ns=clock() + 1_000_000 + artifact.resolved_duration_ns,
    )
    driver.execute("ScheduleTrial", schedule, clock() + 100_000_000)
    release = visual_stimulus.WorkerRelease(
        command=command(True),
        schedule_operation=pb.OperationContext(command_id=schedule.command.command_id),
        start_monotonic_ns=schedule.start_monotonic_ns,
        normal_end_monotonic_ns=schedule.normal_end_monotonic_ns,
    )
    return driver, clock, reports, recorder, graphics, command, release


def test_asset_catalogue_batch_uses_one_receipt_and_exact_identities():
    driver, clock, reports, _, _, command, _ = prepared_driver()
    driver.state.ready = False
    reports.records.clear()
    revision = driver.state.catalogue_revision
    resources = tuple(
        (f"asset:{index}", f"images/{index}.png") for index in range(1920)
    )
    driver.announce_batch_for(command(), clock() + 10**9, resources)
    assert driver.state.catalogue_revision == revision + 1
    assert len(reports.records) == 1
    assert reports.records[0][0] == "ReportWorkerHeartbeat"
    for key, path in resources:
        driver.announce_for(command(), clock() + 10**9, key, path)
        assert driver.state.resources[key].path == path
    assert len(reports.records) == 1
    with pytest.raises(ValueError, match="identity changed"):
        driver.announce_batch_for(
            command(), clock() + 10**9, (("asset:0", "other.png"),)
        )
    assert driver.state.catalogue_revision == revision + 1


def test_native_cpu_preparation_reaches_program_validation_without_gl_calls(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from cephvr.visual_stimulus.resources.session import NativePreparation
    from cephvr.visual_stimulus.v1 import runtime_pb2 as vp

    clock = Clock()
    preparation = NativePreparation(
        object(), renderer_generation=str(uuid4()), clock_ns=clock
    )
    preparation._registered_announce(lambda *_: None, "prior")("asset", None)
    assert preparation.cleanup().released == ("prior:asset",)
    assert preparation.cleanup().released == ("prior:asset",)
    preparation.retire_released_resources()
    setup = visual_stimulus.WorkerSetup()
    setup.session.configuration.asset_root = str(tmp_path)
    setup.session.trials.add().definition.stimulus.SetInParent()
    setup.settings.display.profile_json = valid_display_json()
    setup.policies.limits.CopyFrom(
        vp.ResourceLimits(
            max_document_bytes=1_000_000,
            max_asset_cpu_bytes=2_000_000,
            max_asset_gpu_bytes=2_000_000,
            decoder_threads=1,
            decoder_contexts=1,
            codec_threads_per_context=1,
            codec_threads_total=1,
            decoded_frames_per_instance=1,
            decoded_bytes_total=1_000_000,
            decoder_working_bytes_total=1_000_000,
        )
    )
    with ThreadPoolExecutor(max_workers=1) as cpu:
        outcome = cpu.submit(
            preparation.prepare_trials, setup, lambda *_: None, clock() + 10**9
        )
        with pytest.raises(ValueError, match="canonical stimulus program"):
            outcome.result(timeout=2)
    assert preparation.video_session is not None
    assert preparation.engine._video_provider is None
    assert preparation.engine._video_reset is None
    preparation._registered_announce(lambda *_: None, "current")("asset", None)
    assert preparation.cleanup(clock() + 10**9).released == ("current:asset",)


def test_file_pacing_identity_reaches_both_startup_preparation_owners():
    import json

    from cephvr.visual_stimulus.config.models.display_profile import parse_display_json
    from cephvr.visual_stimulus.v1 import runtime_pb2 as vp

    class CapturingPreparation(Preparation):
        cpu_display = None
        gl_display = None

        def prepare_display(self, request, announce, deadline_ns):
            self.cpu_display = parse_display_json(
                request.display.profile_json,
                max_bytes=request.limits.max_document_bytes,
            )
            return super().prepare_display(request, announce, deadline_ns)

        def initialize_display(self, display, calibration):
            self.gl_display = display
            return super().initialize_display(display, calibration)

    clock, reports, recorder = Clock(), Reports(), Recorder()
    owner, worker, controller = (
        pb.ProcessIdentity(role=role, generation=str(uuid4()))
        for role in ("visual_stimulus", "visual_stimulus_renderer", "controller")
    )
    session = pb.SessionContext(session_id=str(uuid4()))
    artifact = make_prepared_trial(session_id=session.session_id)
    engine = Graphics(clock, artifact)
    preparation = CapturingPreparation(artifact)
    policies = pb.ControlPolicies()
    driver = LifecycleDriver(
        worker=worker,
        owner=owner,
        controller=controller,
        policies=policies,
        engine=engine,
        preparation=preparation,
        recording=recorder,
        reports=reports,
        cancelled=threading.Event(),
        clock=clock,
        shutdown=lambda: None,
    )
    source = json.loads(valid_display_json())
    source["presentation_mode"] = "photodiode_only_vsync"
    source["photodiode_enabled"] = False
    source["photodiode_output_id"] = None
    source.pop("pacing_output_id", None)
    request = visual_stimulus.InitializeDisplay(
        command=visual_stimulus.WorkerCommand(
            command_id=str(uuid4()),
            issuer=owner,
            target=visual_stimulus.WorkerContext(
                worker=worker,
                owner=owner,
                work=pb.WorkContext(session=session),
                configuration_revision=1,
            ),
            deadline_monotonic_ns=clock() + 100_000_000,
        ),
        display=vp.DisplayConfiguration(profile_json=json.dumps(source)),
        limits=vp.ResourceLimits(
            max_document_bytes=1_000_000,
            max_asset_cpu_bytes=2_000_000,
            max_asset_gpu_bytes=1_000_000,
        ),
        pacing_refresh_hz=60.0,
        pacing_output_id="projector/main",
    )
    completion = driver.execute("InitializeDisplay", request, clock() + 100_000_000)
    assert completion is not None
    for _ in range(100):
        driver.advance(clock())
        if completion.done():
            break
        threading.Event().wait(0.001)
    completion.result(timeout=1)
    assert preparation.cpu_display is not None
    assert preparation.gl_display == preparation.cpu_display
    assert preparation.cpu_display.selected_pacing_output_id == "projector/main"
    assert preparation.cpu_display.marker_output_id is None


@pytest.mark.parametrize(
    "failure", ["missing", "cleanup", "gpu", "deadline", "cancelled"]
)
@pytest.mark.parametrize("wrong_adapter", [False, True])
def test_startup_missing_output_is_recoverable_only_after_exact_cleanup(
    failure, wrong_adapter
):
    from cephvr.visual_stimulus.rendering.native_display import (
        DisplayGpuUnavailableError,
        DisplayUnavailableError,
        NativeRenderingError,
    )
    from cephvr.visual_stimulus.v1 import runtime_pb2 as vp

    clock, reports = Clock(), Reports()
    owner, worker, controller = (
        pb.ProcessIdentity(role=role, generation=str(uuid4()))
        for role in ("visual_stimulus", "visual_stimulus_renderer", "controller")
    )
    session = pb.SessionContext(
        controller_generation=controller.generation, session_id=str(uuid4())
    )
    trial = pb.TrialContext(session=session, trial_id=str(uuid4()))
    artifact = make_prepared_trial(
        session_id=session.session_id, trial_id=trial.trial_id
    )
    cleanup_deadlines = []

    class MissingOutput(Preparation):
        def prepare_display(self, request, announce, deadline_ns):
            announce("previous-profile:asset", None)
            return super().prepare_display(request, announce, deadline_ns)

        def initialize_display(self, display, calibration):
            if failure == "gpu":
                raise NativeRenderingError("GPU operation failed")
            if failure == "cancelled":
                driver.cancelled.set()
            if wrong_adapter:
                raise DisplayGpuUnavailableError("OpenGL context uses AMD Radeon")
            raise DisplayUnavailableError("saved projector matched 0 active monitors")

        def cleanup(self, deadline_ns):
            cleanup_deadlines.append(deadline_ns)
            if failure == "deadline":
                clock.value = deadline_ns
            return ResourceReleaseReport(
                ("previous-profile:asset",),
                ("protected source",) if failure == "cleanup" else (),
            )

    driver = LifecycleDriver(
        worker=worker,
        owner=owner,
        controller=controller,
        policies=pb.ControlPolicies(recovery_ns=10_000_000),
        engine=Graphics(clock, artifact),
        preparation=MissingOutput(artifact),
        recording=Recorder(),
        reports=reports,
        cancelled=threading.Event(),
        clock=clock,
        shutdown=lambda: pytest.fail("configuration rejection must not shut down"),
    )
    deadline = clock() + 100_000_000
    command = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        issuer=owner,
        target=visual_stimulus.WorkerContext(
            worker=worker, owner=owner, configuration_revision=1
        ),
        deadline_monotonic_ns=deadline,
    )
    request = visual_stimulus.InitializeDisplay(
        command=command,
        display=vp.DisplayConfiguration(profile_json=valid_display_json()),
        limits=vp.ResourceLimits(max_document_bytes=1_000_000),
    )
    completion = driver.execute("InitializeDisplay", request, deadline)
    for _ in range(100):
        driver.advance(clock())
        if completion.done():
            break
        threading.Event().wait(0.001)
    expected = DisplayUnavailableError if failure == "missing" else Exception
    with pytest.raises(expected):
        completion.result(timeout=1)
    errors = [
        message for method, message, _ in reports.records if method == "ReportError"
    ]
    views = [
        message for method, message, _ in reports.records if method == "ReportDisplay"
    ]
    if failure != "missing":
        assert errors and not views and driver.cancelled.is_set()
        if failure == "cleanup":
            assert driver.state.pending_resources
        if failure == "cancelled":
            assert not cleanup_deadlines
        return
    assert cleanup_deadlines == [deadline]
    assert not errors and not driver.cancelled.is_set()
    assert not driver.display_owner.ready and driver.display_owner.profile is None
    assert driver.state.pending_resources.keys() == driver.state.resources.keys()
    view = views[0]
    assert view.command_id == command.command_id and view.requested_revision == 1
    assert view.complete and not view.HasField("applied_revision")
    assert view.issues[0].failure.code == DisplayUnavailableError.code
    if wrong_adapter:
        assert "cephvr-renderer.exe" in view.issues[0].failure.message
        assert "RTX 5060 Ti" in view.issues[0].failure.message
    assert {item.resource for item in view.resources} == {
        "display:projector/main",
        "display:preparation",
        "previous-profile:asset",
    }
    assert all(item.released for item in view.resources)
    # A fresh explicit Setup can reuse the resident owner after correction.
    setup = visual_stimulus.WorkerSetup(command=command)
    setup.command.command_id = str(uuid4())
    setup.command.target.work.session.CopyFrom(session)
    setup.command.target.configuration_revision = 2
    setup.session.context.CopyFrom(session)
    setup.session.trials.add(context=trial)
    setup.settings.display.profile_json = valid_display_json()
    setup.policies.projection.CopyFrom(
        load_file_policies(Path(__file__).resolve().parents[2]).projection
    )
    setup.policies.limits.max_document_bytes = 1_000_000
    fresh = driver.execute("SetupSession", setup, deadline)
    for _ in range(100):
        driver.advance(clock())
        if fresh.done():
            break
        threading.Event().wait(0.001)
    fresh.result(timeout=1)
    assert not driver.state.interrupted
    driver.cleanup(setup.command)
    assert driver.state.cleaned


def test_pre_setup_display_resources_are_local_then_promoted_by_setup():
    clock, reports, recorder = Clock(), Reports(), Recorder()
    owner, worker, controller = (
        pb.ProcessIdentity(role=role, generation=str(uuid4()))
        for role in ("visual_stimulus", "visual_stimulus_renderer", "controller")
    )
    session = pb.SessionContext(session_id=str(uuid4()))
    trial = pb.TrialContext(session=session, trial_id=str(uuid4()))
    artifact = make_prepared_trial(
        session_id=session.session_id, trial_id=trial.trial_id
    )
    graphics = Graphics(clock, artifact)
    driver = LifecycleDriver(
        worker=worker,
        owner=owner,
        controller=controller,
        policies=pb.ControlPolicies(recovery_ns=10_000_000),
        engine=graphics,
        preparation=Preparation(artifact),
        recording=recorder,
        reports=reports,
        cancelled=threading.Event(),
        clock=clock,
        shutdown=lambda: None,
    )
    setup_command = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        issuer=owner,
        target=visual_stimulus.WorkerContext(
            worker=worker,
            owner=owner,
            configuration_revision=9,
            work=pb.WorkContext(session=session),
        ),
        deadline_monotonic_ns=clock() + 100_000_000,
    )
    driver.announce_for(None, clock() + 100_000_000, "display:projector/main", None)
    assert not reports.records
    assert "display:projector/main" in driver.state.pending_resources
    setup = visual_stimulus.WorkerSetup(command=setup_command)
    setup.session.context.CopyFrom(session)
    setup.session.trials.add(context=trial)
    setup.settings.display.profile_json = valid_display_json()
    setup.policies.projection.CopyFrom(
        load_file_policies(Path(__file__).resolve().parents[2]).projection
    )
    setup.policies.limits.max_document_bytes = 1_000_000
    driver.deadline_ns = clock() + 100_000_000
    completion = driver.setup(setup)
    assert driver.state.setup is setup
    assert not driver.state.pending_resources
    heartbeats = [
        message
        for method, message, _ in reports.records
        if method == "ReportWorkerHeartbeat"
    ]
    assert len(heartbeats) >= 1
    assert "display:projector/main" in {
        item.resource for item in heartbeats[0].cleanup_resources
    }
    for _ in range(100):
        driver.advance(clock())
        if completion.done():
            break
        threading.Event().wait(0.001)
    completion.result(timeout=1)


def test_pre_setup_display_cleanup_requires_exact_local_release_without_session_report():
    clock, reports, recorder = Clock(), Reports(), Recorder()
    owner, worker, controller = (
        pb.ProcessIdentity(role=role, generation=str(uuid4()))
        for role in ("visual_stimulus", "visual_stimulus_renderer", "controller")
    )
    artifact = make_prepared_trial()
    graphics = Graphics(clock, artifact)
    preparation = Preparation(artifact)
    driver = LifecycleDriver(
        worker=worker,
        owner=owner,
        controller=controller,
        policies=pb.ControlPolicies(recovery_ns=10_000_000),
        engine=graphics,
        preparation=preparation,
        recording=recorder,
        reports=reports,
        cancelled=threading.Event(),
        clock=clock,
        shutdown=lambda: None,
    )
    command = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        issuer=owner,
        target=visual_stimulus.WorkerContext(worker=worker, owner=owner),
        deadline_monotonic_ns=clock() + 100_000_000,
    )
    driver.announce_for(command, clock() + 100_000_000, "display:projector/main", None)
    driver.deadline_ns = clock() + 100_000_000
    driver.cleanup(command)
    assert driver.state.cleaned
    assert not driver.state.pending_resources
    assert not driver.state.resources
    assert preparation.retired_resource_catalogues == 1
    assert not any(
        method == "ReportWorkerLifecycle" for method, _, _ in reports.records
    )


def test_pre_setup_display_cleanup_retains_resources_when_release_is_unknown():
    clock, reports, recorder = Clock(), Reports(), Recorder()
    owner, worker, controller = (
        pb.ProcessIdentity(role=role, generation=str(uuid4()))
        for role in ("visual_stimulus", "visual_stimulus_renderer", "controller")
    )
    artifact = make_prepared_trial()
    graphics = Graphics(clock, artifact)
    graphics.cleanup = lambda deadline_ns=None: ResourceReleaseReport(
        (), ("display:unknown",)
    )
    driver = LifecycleDriver(
        worker=worker,
        owner=owner,
        controller=controller,
        policies=pb.ControlPolicies(recovery_ns=10_000_000),
        engine=graphics,
        preparation=Preparation(artifact),
        recording=recorder,
        reports=reports,
        cancelled=threading.Event(),
        clock=clock,
        shutdown=lambda: None,
    )
    command = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        issuer=owner,
        target=visual_stimulus.WorkerContext(worker=worker, owner=owner),
        deadline_monotonic_ns=clock() + 100_000_000,
    )
    driver.announce_for(command, clock() + 100_000_000, "display:projector/main", None)
    driver.deadline_ns = clock() + 100_000_000
    with pytest.raises(RuntimeError, match="cleanup remains unconfirmed"):
        driver.cleanup(command)
    assert driver.state.resources["display:projector/main"].resource
    assert "display:projector/main" in driver.state.pending_resources
    assert not driver.state.cleaned
    assert graphics.retired_resource_catalogues == 0
    assert recorder.retired_resource_catalogues == 0
    assert driver.preparation.retired_resource_catalogues == 0


def test_failed_setup_cleanup_waits_for_terminal_report_acceptance():
    driver, clock, reports, _, _, command, _ = prepared_driver()
    driver.cleanup(command())
    reports.records.clear()
    session = pb.SessionContext(session_id=str(uuid4()))
    setup_context = visual_stimulus.WorkerContext(
        worker=driver.worker,
        owner=driver.owner,
        configuration_revision=1,
        work=pb.WorkContext(session=session),
    )
    setup = visual_stimulus.WorkerSetup(
        command=visual_stimulus.WorkerCommand(
            command_id=str(uuid4()),
            issuer=driver.owner,
            target=setup_context,
            deadline_monotonic_ns=clock() + 100_000_000,
        )
    )
    setup.session.context.CopyFrom(session)
    setup.session.trials.add(
        context=pb.TrialContext(session=session, trial_id=str(uuid4()))
    )
    setup.settings.display.profile_json = "not-json"
    setup.policies.limits.max_document_bytes = 1_000_000
    setup.policies.projection.CopyFrom(
        load_file_policies(Path(__file__).resolve().parents[2]).projection
    )
    with pytest.raises(ValueError) as setup_error:
        driver.execute("SetupSession", setup, setup.command.deadline_monotonic_ns)
    driver.fail(setup_error.value)
    driver.engine.cleanup = lambda deadline_ns=None: ResourceReleaseReport(())
    assert not driver.state.ready
    assert any(
        method == "ReportError" and message.failure.message == str(setup_error.value)
        for method, message, _ in reports.records
    )

    confirmed = []
    original_confirm = reports.confirm
    original_send = reports.send

    def confirm(method, message, deadline_ns):
        if message.report.WhichOneof("report") == "cleanup":
            assert driver.state.setup is not None
            confirmed.append((method, deadline_ns))
        original_confirm(method, message, deadline_ns)

    def send(method, message, deadline_ns, *, required=True):
        if (
            method == "ReportWorkerLifecycle"
            and message.report.WhichOneof("report") == "cleanup"
        ):
            raise AssertionError("terminal cleanup must use confirmed delivery")
        original_send(method, message, deadline_ns)

    reports.confirm = confirm
    reports.send = send
    assert driver.state.failure_deadline_ns is not None
    deadline = min(clock() + 50_000_000, driver.state.failure_deadline_ns)
    cancel = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        issuer=driver.owner,
        target=setup_context,
        deadline_monotonic_ns=deadline,
    )
    assert driver.execute("CancelSetup", cancel, deadline) is None

    assert confirmed == [("ReportWorkerLifecycle", deadline)]
    assert driver.state.cleaned
    assert driver.state.setup is None
    assert not any(
        method == "ReportWorkerLifecycle"
        and message.report.WhichOneof("report") == "ready"
        for method, message, _ in reports.records
    )


@pytest.mark.parametrize("release_failure", (False, True))
def test_unprepared_session_cleanup_requires_native_release(release_failure):
    driver, clock, reports, _, _, command, _ = prepared_driver()
    driver.cleanup(command())
    reports.records.clear()
    cancel = command()
    cancel.target.work.session.session_id = str(uuid4())

    if release_failure:

        def fail(deadline_ns=None):
            raise RuntimeError("native release blocked")

        driver.engine.cleanup = fail
        with pytest.raises(RuntimeError, match="native release blocked"):
            driver.execute("CancelSetup", cancel, clock() + 100_000_000)
        assert not any(
            method == "ReportWorkerLifecycle" for method, _, _ in reports.records
        )
    else:
        driver.execute("CancelSetup", cancel, clock() + 100_000_000)
        proof = next(
            message.report.cleanup
            for method, message, _ in reports.records
            if method == "ReportWorkerLifecycle"
        )
        assert proof.work == cancel.target.work
        assert proof.operation.command_id == cancel.command_id
        assert (
            proof.trial_activity_stopped and not proof.resources and not proof.outputs
        )


def test_preparation_rejection_stays_setup_failure_and_allows_reuse():
    driver, clock, reports, _, _, command, _ = prepared_driver()
    driver.cleanup(command())
    reports.records.clear()
    original_prepare = driver.preparation.prepare_trials

    def setup_request():
        session = pb.SessionContext(session_id=str(uuid4()))
        trial = pb.TrialContext(session=session, trial_id=str(uuid4()))
        request = visual_stimulus.WorkerSetup(
            command=visual_stimulus.WorkerCommand(
                command_id=str(uuid4()),
                issuer=driver.owner,
                target=visual_stimulus.WorkerContext(
                    worker=driver.worker,
                    owner=driver.owner,
                    configuration_revision=1,
                    work=pb.WorkContext(session=session),
                ),
                deadline_monotonic_ns=clock() + 100_000_000,
            )
        )
        request.session.context.CopyFrom(session)
        request.session.trials.add(context=trial)
        request.settings.display.profile_json = valid_display_json()
        request.policies.projection.CopyFrom(
            load_file_policies(Path(__file__).resolve().parents[2]).projection
        )
        request.policies.limits.max_document_bytes = 1_000_000
        return request, trial

    def reject_preparation(
        _request, _announce, _deadline_ns, *, announce_batch=None, progress=None
    ):
        raise ValueError("recording byte budget rejected Setup")

    driver.preparation.prepare_trials = reject_preparation
    failed_setup, _ = setup_request()
    failed_completion = driver.execute(
        "SetupSession", failed_setup, failed_setup.command.deadline_monotonic_ns
    )
    assert failed_completion is not None
    for _ in range(100):
        driver.advance(clock())
        if failed_completion.done():
            break
        threading.Event().wait(0.001)
    with pytest.raises(ValueError, match="budget rejected"):
        failed_completion.result(timeout=1)

    assert driver.state.setup is not None
    assert driver.state.interrupted and driver.cancelled.is_set()
    assert not driver.state.ready
    assert driver.state.failure_deadline_ns is None
    assert not any(method == "ReportError" for method, _, _ in reports.records)
    assert not any(
        method == "ReportWorkerLifecycle"
        and message.report.WhichOneof("report") == "ready"
        for method, message, _ in reports.records
    )

    cancel = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        issuer=driver.owner,
        target=failed_setup.command.target,
        deadline_monotonic_ns=clock() + 100_000_000,
    )
    driver.execute("CancelSetup", cancel, cancel.deadline_monotonic_ns)
    cleanup = reports.lifecycle("cleanup")[-1][0]
    assert cleanup.trial_activity_stopped
    assert driver.state.cleaned and driver.state.setup is None
    assert not driver.state.ready

    driver.preparation.prepare_trials = original_prepare
    ready_setup, trial = setup_request()
    driver.preparation.artifact = make_prepared_trial(
        session_id=ready_setup.session.context.session_id,
        trial_id=trial.trial_id,
    )
    ready_completion = driver.execute(
        "SetupSession", ready_setup, ready_setup.command.deadline_monotonic_ns
    )
    assert ready_completion is not None
    for _ in range(100):
        driver.advance(clock())
        if ready_completion.done():
            break
        threading.Event().wait(0.001)
    ready_completion.result(timeout=1)
    assert driver.state.ready
    assert reports.lifecycle("ready")[-1][0].context.work == (
        ready_setup.command.target.work
    )


def test_session_cleanup_delivery_failure_keeps_setup_unresolved():
    driver, clock, reports, _, _, command, _ = prepared_driver()
    retired_trial = driver.state.trial
    assert retired_trial is not None
    retired_trial.finished = True

    def reject(_method, _message, _deadline_ns):
        raise TimeoutError("cleanup report was not accepted")

    reports.confirm = reject
    with pytest.raises(TimeoutError, match="not accepted"):
        driver.cleanup(command())

    assert driver.state.setup is not None
    assert not driver.state.cleaned
    assert driver.state.trial is retired_trial


@pytest.mark.parametrize(
    "calibration_view", ["frame_grid", "photodiode_placement", "blackout_placement"]
)
@pytest.mark.parametrize("fail_update", [False, True])
def test_sessionless_display_calibration_requires_presentation_then_closed_idle(
    fail_update,
    calibration_view,
):
    import hashlib
    from types import SimpleNamespace

    from cephvr.visual_stimulus.config.models.display_profile import parse_display_json
    from cephvr.visual_stimulus.rendering.types import OutputActivity
    from cephvr.visual_stimulus.v1 import runtime_pb2 as vp
    from cephvr.visual_stimulus.worker.display_calibration import (
        DisplayCalibrationOwner,
    )

    clock = Clock()
    profile = parse_display_json(valid_display_json(), max_bytes=1_000_000)
    profile = profile.model_copy(update=dict(calibration_view=calibration_view))
    profile_json = profile.model_dump_json()
    worker = pb.ProcessIdentity(
        role="visual_stimulus_renderer", generation=str(uuid4())
    )
    controller = pb.ProcessIdentity(role="controller", generation=str(uuid4()))
    coordinator = pb.ProcessIdentity(role="visual_stimulus", generation=str(uuid4()))
    reports = Reports()
    prepared = SimpleNamespace(display=profile, previous_display=None)
    retained_profile = [None]

    class PreparationStub:
        def prepare_display_calibration(self, request, announce, deadline_ns):
            announce("arena", "/accepted/calibration/arena.glb")
            return prepared

        def release_display_calibration(self, asset):
            assert asset is prepared
            return True

    presentations = []
    updates = []
    pulse_failure = [False]

    class EngineStub:
        def present_display_calibration(self, selected, asset):
            assert selected == profile and asset is prepared
            presentations.append(selected)
            return (
                OutputActivity(
                    "projector/main", 10, 11, 1, "failed" if pulse_failure[0] else None
                ),
            )

        def update_display_calibration(self, selected, asset, adjustments):
            assert selected == profile and asset is prepared
            updates.append(adjustments)
            if calibration_view == "frame_grid":
                assert "front" in adjustments
            else:
                from cephvr.visual_stimulus.config.calibration_placement import (
                    CalibrationPlacement,
                )

                assert isinstance(adjustments, CalibrationPlacement)
                assert adjustments.outputs[0].output_id == "projector/main"
            return (
                OutputActivity(
                    "projector/main", 11, 12, 1, "swap failed" if fail_update else None
                ),
            )

        def close_display_calibration(self, selected, asset):
            assert selected == profile and asset is prepared
            return (OutputActivity("projector/main", 12, 13, 1),), True

    owner = DisplayCalibrationOwner(
        worker=worker,
        controller=controller,
        backend=pb.BackendContext(
            backend_name="visual_stimulus", backend_generation=coordinator.generation
        ),
        engine=EngineStub(),
        preparation=PreparationStub(),
        reports=reports,
        display_profile=lambda: None,
        set_display_profile=lambda selected: retained_profile.__setitem__(0, selected),
        clock=clock,
    )
    command = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        issuer=coordinator,
        target=visual_stimulus.WorkerContext(
            worker=worker,
            owner=coordinator,
            configuration_revision=7,
        ),
        parent_operation=pb.OperationContext(command_id=str(uuid4())),
        deadline_monotonic_ns=clock() + 1_000_000,
    )
    opened = visual_stimulus.OpenDisplayCalibrationCommand(
        command=command,
        diagnostic_id=str(uuid4()),
        profile_json=profile_json,
        profile_sha256=hashlib.sha256(profile_json.encode()).hexdigest(),
        asset_root="/accepted",
        arena_relative_path="calibration/arena.glb",
        arena_size_bytes=64,
        arena_sha256="a" * 64,
        policies=vp.VisualStimulusFilePolicies(
            limits=vp.ResourceLimits(max_document_bytes=1_000_000)
        ),
    )
    completion = owner.open(opened, command.deadline_monotonic_ns)
    for _ in range(100):
        owner.advance(clock())
        if completion.done():
            break
        threading.Event().wait(0.001)
    completion.result(timeout=1)
    assert owner.evidence.state == vp.DISPLAY_CALIBRATION_STATE_ACTIVE
    assert owner.evidence.presented is True
    assert not owner.evidence.idle
    assert owner.evidence.resources_closed is False
    assert retained_profile[0] == profile
    assert [item.output_id for item in reports.records[-1][1].outputs] == [
        "projector/main"
    ]
    assert reports.records[-1][1].calibration.diagnostic_id == opened.diagnostic_id
    assert reports.records[-1][1].calibration.renderer_generation == worker.generation

    for _ in range(3):
        owner.advance(clock())
    assert len(presentations) == (
        4 if calibration_view == "photodiode_placement" else 1
    )
    assert owner.evidence.adjustment_sequence == 0

    update = visual_stimulus.UpdateDisplayCalibrationCommand(
        command=command, diagnostic_id=opened.diagnostic_id, adjustment_sequence=1
    )
    update.adjustments.add(
        mapping_id="front", destination_xy=[0.1, 0.1, 0.9, 0.1, 0.1, 0.9, 0.9, 0.9]
    )
    import json

    placement_json = json.dumps(
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
    if calibration_view != "frame_grid":
        update.ClearField("adjustments")
        update.placement_json = placement_json
    if fail_update:
        with pytest.raises(RuntimeError, match="presentation evidence"):
            owner.update(update, command.deadline_monotonic_ns)
        assert owner.evidence.state == vp.DISPLAY_CALIBRATION_STATE_UNKNOWN
        assert not owner.evidence.presented
        assert owner.evidence.adjustment_sequence == 0
        assert owner.prepared is prepared
    else:
        owner.update(update, command.deadline_monotonic_ns)
        assert owner.prepared is prepared
        assert owner.evidence.adjustment_sequence == 1
        assert owner.evidence.state == vp.DISPLAY_CALIBRATION_STATE_ACTIVE
        with pytest.raises(ValueError, match="stale"):
            owner.update(update, command.deadline_monotonic_ns)
        update.adjustment_sequence = 2
        update.diagnostic_id = str(uuid4())
        with pytest.raises(ValueError, match="stale"):
            owner.update(update, command.deadline_monotonic_ns)
        update.diagnostic_id = opened.diagnostic_id
        if calibration_view == "frame_grid":
            update.adjustments[0].destination_xy[0] = -1
        else:
            update.placement_json = "{}"
        with pytest.raises(ValueError):
            owner.update(update, command.deadline_monotonic_ns)
        assert owner.evidence.state == vp.DISPLAY_CALIBRATION_STATE_ACTIVE
        assert owner.evidence.adjustment_sequence == 1
        assert owner.evidence.failure_code == "CALIBRATION_ADJUSTMENT_REJECTED"
        if calibration_view != "frame_grid":
            from copy import deepcopy

            from cephvr.visual_stimulus.config.calibration_adjustments import (
                CalibrationAdjustmentRejected,
            )

            payload = json.loads(placement_json)
            invalid = deepcopy(payload)
            invalid["outputs"][0]["blackout_zones"] = [
                dict(x=100_000, y=1, width=2, height=2)
            ]
            invalid_updates = [invalid]
            invalid = deepcopy(payload)
            invalid["outputs"].append(dict(output_id="unknown", blackout_zones=[]))
            invalid_updates.append(invalid)
            if calibration_view == "photodiode_placement":
                invalid = deepcopy(payload)
                invalid["photodiode_patch"]["rect"]["x"] = 100_000
                invalid_updates.append(invalid)
                invalid = deepcopy(payload)
                invalid["photodiode_patch"]["background_rect"] = dict(
                    x=0, y=0, width=100_000, height=100_000
                )
                invalid_updates.append(invalid)
            applied = updates[-1]
            active_profile = owner.active_profile
            for invalid in invalid_updates:
                update.placement_json = json.dumps(invalid)
                with pytest.raises(CalibrationAdjustmentRejected):
                    owner.update(update, command.deadline_monotonic_ns)
                assert updates == [applied]
                assert owner.active_id == opened.diagnostic_id
                assert owner.active_profile is active_profile
                assert owner.prepared is prepared
                assert owner.evidence.state == vp.DISPLAY_CALIBRATION_STATE_ACTIVE
                assert owner.evidence.presented
                assert owner.evidence.adjustment_sequence == 1
                assert owner.evidence.failure_code == "CALIBRATION_ADJUSTMENT_REJECTED"
                owner.advance(clock())
                assert owner.evidence.state == vp.DISPLAY_CALIBRATION_STATE_ACTIVE
        if calibration_view == "frame_grid":
            update.adjustments[0].destination_xy[0] = 0.1
        else:
            update.placement_json = placement_json
        owner.update(update, command.deadline_monotonic_ns)
        assert owner.evidence.adjustment_sequence == 2
        assert not owner.evidence.failure_code
    if calibration_view == "photodiode_placement":
        if not fail_update:
            pulse_failure[0] = True
            with pytest.raises(RuntimeError, match="preview presentation failed"):
                owner.advance(clock())
            assert owner.evidence.state == vp.DISPLAY_CALIBRATION_STATE_UNKNOWN
            assert owner.evidence.failure_code == "CALIBRATION_PULSE"
        count = len(presentations)
        owner.advance(clock())
        assert len(presentations) == count

    close_command = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        issuer=coordinator,
        target=command.target,
        parent_operation=pb.OperationContext(command_id=str(uuid4())),
        deadline_monotonic_ns=clock() + 1_000_000,
    )
    owner.close(
        visual_stimulus.CloseDisplayCalibrationCommand(
            command=close_command, diagnostic_id=opened.diagnostic_id
        ),
        close_command.deadline_monotonic_ns,
    )
    assert owner.evidence.state == vp.DISPLAY_CALIBRATION_STATE_IDLE
    assert owner.evidence.idle is True
    assert owner.evidence.resources_closed is True
    assert retained_profile[0] is None
    assert reports.records[-1][1].command_id == close_command.command_id
    count = len(presentations)
    owner.advance(clock())
    assert len(presentations) == count

    with pytest.raises(ValueError, match="inactive"):
        owner.update(update, command.deadline_monotonic_ns)


def test_display_calibration_cleanup_retains_and_releases_late_prepare():
    import hashlib
    import threading
    from types import SimpleNamespace

    from cephvr.visual_stimulus.config.models.display_profile import parse_display_json
    from cephvr.visual_stimulus.v1 import runtime_pb2 as vp
    from cephvr.visual_stimulus.worker.display_calibration import (
        DisplayCalibrationOwner,
    )

    clock = Clock()
    profile = parse_display_json(valid_display_json(), max_bytes=1_000_000)
    profile_json = profile.model_dump_json()
    worker = pb.ProcessIdentity(
        role="visual_stimulus_renderer", generation=str(uuid4())
    )
    controller = pb.ProcessIdentity(role="controller", generation=str(uuid4()))
    coordinator = pb.ProcessIdentity(role="visual_stimulus", generation=str(uuid4()))
    arena = SimpleNamespace(display=profile, previous_display=None)
    release_started = threading.Event()
    allow_prepare = threading.Event()

    class PreparationStub:
        def prepare_display_calibration(self, request, announce, deadline_ns):
            release_started.set()
            assert allow_prepare.wait(1)
            return arena

        def release_display_calibration(self, prepared):
            assert prepared is arena
            return True

    class EngineStub:
        def present_display_calibration(self, selected, prepared):
            raise AssertionError("cleanup must not present late preparation")

    reports = Reports()
    owner = DisplayCalibrationOwner(
        worker=worker,
        controller=controller,
        backend=pb.BackendContext(
            backend_name="visual_stimulus", backend_generation=coordinator.generation
        ),
        engine=EngineStub(),
        preparation=PreparationStub(),
        reports=reports,
        display_profile=lambda: None,
        set_display_profile=lambda _selected: None,
        clock=clock,
    )
    command = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        issuer=coordinator,
        target=visual_stimulus.WorkerContext(
            worker=worker, owner=coordinator, configuration_revision=8
        ),
        parent_operation=pb.OperationContext(command_id=str(uuid4())),
        deadline_monotonic_ns=clock() + 1_000_000,
    )
    opened = visual_stimulus.OpenDisplayCalibrationCommand(
        command=command,
        diagnostic_id=str(uuid4()),
        profile_json=profile_json,
        profile_sha256=hashlib.sha256(profile_json.encode()).hexdigest(),
        asset_root="/accepted",
        arena_relative_path="calibration/arena.glb",
        arena_size_bytes=64,
        arena_sha256="a" * 64,
        policies=vp.VisualStimulusFilePolicies(
            limits=vp.ResourceLimits(max_document_bytes=1_000_000)
        ),
    )
    completion = owner.open(opened, command.deadline_monotonic_ns)
    assert release_started.wait(1)
    cleanup = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        issuer=coordinator,
        target=command.target,
        parent_operation=pb.OperationContext(command_id=str(uuid4())),
        deadline_monotonic_ns=clock() + 2_000_000,
    )
    owner.request_cleanup(cleanup, cleanup.deadline_monotonic_ns)
    later_shutdown = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        issuer=coordinator,
        target=command.target,
        parent_operation=pb.OperationContext(command_id=str(uuid4())),
        deadline_monotonic_ns=clock() + 3_000_000,
    )
    owner.request_cleanup(later_shutdown, later_shutdown.deadline_monotonic_ns)
    assert owner.job.cleanup_command.command_id == cleanup.command_id
    assert owner.job.cleanup_deadline_ns == cleanup.deadline_monotonic_ns
    assert owner.advance(clock()) is not None
    assert owner.job is not None
    allow_prepare.set()
    for _ in range(100):
        owner.advance(clock())
        if owner.job is None:
            break
        threading.Event().wait(0.001)

    assert owner.job is None
    assert owner.evidence.state == vp.DISPLAY_CALIBRATION_STATE_IDLE
    assert owner.evidence.resources_closed
    assert not owner.evidence.presented
    assert owner.active_id == ""
    with pytest.raises(InterruptedError, match="superseded by cleanup"):
        completion.result(timeout=1)
    report = reports.records[-1][1]
    assert report.command_id == cleanup.command_id
    assert report.calibration.diagnostic_id == opened.diagnostic_id


@pytest.mark.parametrize("release_fails_once", [False, True])
def test_display_calibration_open_that_prepares_after_its_deadline_returns_to_idle(
    release_fails_once,
):
    import hashlib
    import threading
    from types import SimpleNamespace

    from cephvr.visual_stimulus.config.models.display_profile import parse_display_json
    from cephvr.visual_stimulus.v1 import runtime_pb2 as vp
    from cephvr.visual_stimulus.worker.display_calibration import (
        DisplayCalibrationOwner,
    )

    clock = Clock()
    profile = parse_display_json(valid_display_json(), max_bytes=1_000_000)
    profile_json = profile.model_dump_json()
    worker = pb.ProcessIdentity(
        role="visual_stimulus_renderer", generation=str(uuid4())
    )
    controller = pb.ProcessIdentity(role="controller", generation=str(uuid4()))
    coordinator = pb.ProcessIdentity(role="visual_stimulus", generation=str(uuid4()))
    prepared = SimpleNamespace(display=profile, previous_display=None)
    allow_prepare = threading.Event()
    releases = []

    class PreparationStub:
        def prepare_display_calibration(self, request, announce, deadline_ns):
            assert allow_prepare.wait(1)
            return prepared

        def release_display_calibration(self, asset):
            releases.append(asset)
            return not (release_fails_once and len(releases) == 1)

    class EngineStub:
        def present_display_calibration(self, selected, asset):
            raise AssertionError("a late preparation must not be presented")

        def close_display_calibration(self, selected, asset):
            raise AssertionError("the renderer never held this preparation")

    reports = Reports()
    owner = DisplayCalibrationOwner(
        worker=worker,
        controller=controller,
        backend=pb.BackendContext(
            backend_name="visual_stimulus", backend_generation=coordinator.generation
        ),
        engine=EngineStub(),
        preparation=PreparationStub(),
        reports=reports,
        display_profile=lambda: None,
        set_display_profile=lambda _selected: None,
        clock=clock,
    )
    command = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        issuer=coordinator,
        target=visual_stimulus.WorkerContext(
            worker=worker, owner=coordinator, configuration_revision=9
        ),
        parent_operation=pb.OperationContext(command_id=str(uuid4())),
        deadline_monotonic_ns=clock() + 1_000_000,
    )
    opened = visual_stimulus.OpenDisplayCalibrationCommand(
        command=command,
        diagnostic_id=str(uuid4()),
        profile_json=profile_json,
        profile_sha256=hashlib.sha256(profile_json.encode()).hexdigest(),
        asset_root="/accepted",
        arena_relative_path="calibration/arena.glb",
        arena_size_bytes=64,
        arena_sha256="a" * 64,
        policies=vp.VisualStimulusFilePolicies(
            limits=vp.ResourceLimits(max_document_bytes=1_000_000)
        ),
    )
    completion = owner.open(opened, command.deadline_monotonic_ns)
    late = command.deadline_monotonic_ns + 1
    assert owner.advance(late) is not None  # deadline missed, preparation still running
    assert owner.evidence.state == vp.DISPLAY_CALIBRATION_STATE_UNKNOWN
    with pytest.raises(TimeoutError):
        completion.result(timeout=1)
    allow_prepare.set()
    for _ in range(100):
        owner.advance(late)
        if owner.job is None:
            break
        threading.Event().wait(0.001)
    assert owner.job is None

    close = visual_stimulus.CloseDisplayCalibrationCommand(
        command=visual_stimulus.WorkerCommand(
            command_id=str(uuid4()),
            issuer=coordinator,
            target=command.target,
            parent_operation=pb.OperationContext(command_id=str(uuid4())),
            deadline_monotonic_ns=clock() + 1_000_000,
        ),
        diagnostic_id=opened.diagnostic_id,
    )
    if release_fails_once:
        # The failed release leaves exact evidence; Close retries it without the renderer.
        assert owner.evidence.state == vp.DISPLAY_CALIBRATION_STATE_UNKNOWN
        assert owner.evidence.failure_code == "CALIBRATION_SOURCE_CLOSE"
        assert owner.active_id == opened.diagnostic_id
        owner.close(close, close.command.deadline_monotonic_ns)
    assert owner.evidence.state == vp.DISPLAY_CALIBRATION_STATE_IDLE
    assert owner.evidence.idle and owner.evidence.resources_closed
    assert not owner.evidence.failure_code
    assert owner.evidence.diagnostic_id == opened.diagnostic_id
    assert owner.active_id == "" and owner.prepared is None
    # Repeating the controller's Close confirms the same evidence instead of failing.
    owner.close(close, close.command.deadline_monotonic_ns)
    report = reports.records[-1][1]
    assert report.command_id == close.command.command_id
    assert report.calibration.state == vp.DISPLAY_CALIBRATION_STATE_IDLE
    assert len(releases) == (2 if release_fails_once else 1)


def test_failed_native_calibration_source_close_is_retried_by_lifecycle_cleanup(
    tmp_path, monkeypatch
):
    import hashlib
    from contextlib import contextmanager

    from cephvr.visual_stimulus.rendering.types import ResourceReleaseReport
    from cephvr.visual_stimulus.resources import (
        display_calibration as resource_calibration,
    )
    from cephvr.visual_stimulus.resources.calibration import PreparedCalibration
    from cephvr.visual_stimulus.resources.session import NativePreparation
    from cephvr.visual_stimulus.v1 import runtime_pb2 as vp
    from cephvr.visual_stimulus.worker.lifecycle import LifecycleDriver

    from .support import glb_fixture, pack_glb

    class ProtectedFile:
        def __init__(self, path: Path):
            self.path = path
            self.fail_close = True
            self.close_attempts = 0

        @contextmanager
        def independent_reader(self):
            with self.path.open("rb") as source:
                yield source

        def close_after_consumers(self):
            self.close_attempts += 1
            if self.fail_close:
                raise OSError("protected source still has a consumer")

    class Port:
        def service_display(self):
            return False

        @property
        def diagnostics_pending(self):
            return False

        def poll_diagnostics(self):
            return ()

        def release(self, deadline_ns=None):
            return ResourceReleaseReport(())

    class Engine:
        def service_display(self):
            return False

        @property
        def diagnostics_pending(self):
            return False

        def poll_diagnostics(self):
            return ()

        def cleanup(self, deadline_ns=None):
            return ResourceReleaseReport(())

        def retire_released_resources(self):
            pass

    arena_doc, binary = glb_fixture()
    arena = pack_glb(arena_doc, binary)
    arena_path = tmp_path / "calibration" / "arena.glb"
    arena_path.parent.mkdir()
    arena_path.write_bytes(arena)
    sources = []

    def source_factory(path):
        source = ProtectedFile(path)
        sources.append(source)
        return source

    monkeypatch.setattr(
        resource_calibration,
        "prepare_calibration",
        lambda *_args, **_kwargs: PreparedCalibration(
            assets=(), resources=(), content={}
        ),
    )
    clock = Clock()
    preparation = NativePreparation(
        Port(),
        renderer_generation="renderer-generation",
        clock_ns=clock,
        source_factory=source_factory,
    )
    worker = pb.ProcessIdentity(
        role="visual_stimulus_renderer", generation=str(uuid4())
    )
    owner = pb.ProcessIdentity(role="visual_stimulus", generation=str(uuid4()))
    controller = pb.ProcessIdentity(role="controller", generation=str(uuid4()))
    reports = Reports()
    policies = pb.ControlPolicies(recovery_ns=100_000_000)
    driver = LifecycleDriver(
        worker=worker,
        owner=owner,
        controller=controller,
        policies=policies,
        engine=Engine(),
        preparation=preparation,
        recording=Recorder(),
        reports=reports,
        cancelled=threading.Event(),
        clock=clock,
        shutdown=lambda: None,
    )
    profile = valid_display_json()
    command = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        issuer=owner,
        target=visual_stimulus.WorkerContext(
            worker=worker,
            owner=owner,
            configuration_revision=9,
        ),
        parent_operation=pb.OperationContext(command_id=str(uuid4())),
        deadline_monotonic_ns=clock() + 10_000_000_000,
    )
    request = visual_stimulus.OpenDisplayCalibrationCommand(
        command=command,
        diagnostic_id=str(uuid4()),
        profile_json=profile,
        profile_sha256=hashlib.sha256(profile.encode()).hexdigest(),
        asset_root=str(tmp_path),
        arena_relative_path="calibration/arena.glb",
        arena_size_bytes=len(arena),
        arena_sha256="0" * 64,
        policies=vp.VisualStimulusFilePolicies(
            limits=vp.ResourceLimits(
                max_document_bytes=1_000_000,
                max_asset_cpu_bytes=2_000_000,
                max_asset_gpu_bytes=1_000_000,
            )
        ),
    )
    completion = driver.execute(
        "OpenDisplayCalibration", request, command.deadline_monotonic_ns
    )
    assert completion is not None
    for _ in range(100):
        driver.advance(clock())
        if completion.done():
            break
        threading.Event().wait(0.001)
    with pytest.raises(RuntimeError, match="protected inputs remain owned"):
        completion.result(timeout=1)
    assert len(sources) == 1 and sources[0].close_attempts == 1
    assert (
        driver.display_calibration.evidence.state
        == vp.DISPLAY_CALIBRATION_STATE_UNKNOWN
    )

    sources[0].fail_close = False
    driver.deadline_ns = clock() + 10_000_000_000
    driver.cleanup(command)

    assert sources[0].close_attempts == 2
    assert preparation._protected_sources == []
    assert (
        driver.display_calibration.evidence.state == vp.DISPLAY_CALIBRATION_STATE_IDLE
    )
    assert driver.display_calibration.evidence.idle
    assert driver.display_calibration.evidence.resources_closed
    assert driver.state.cleaned


def test_setup_uses_file_pacing_identity_before_mixed_mode_validation():
    import json

    from cephvr.visual_stimulus.config.models.display_profile import parse_display_json

    source = json.loads(valid_display_json())
    source["presentation_mode"] = "photodiode_only_vsync"
    source["photodiode_enabled"] = False
    source["photodiode_output_id"] = None
    source.pop("pacing_output_id", None)
    driver, *_ = prepared_driver(
        display_json=json.dumps(source),
        pacing_refresh_hz=60.0,
        pacing_output_id="projector/main",
    )
    display = parse_display_json(
        driver.state.setup.settings.display.profile_json,
        max_bytes=1_000_000,
    )
    assert display.selected_pacing_output_id == "projector/main"
    assert display.marker_output_id is None


def test_release_is_required_and_no_activity_before_onset():
    driver, clock, reports, recorder, graphics, command, release = prepared_driver()
    assert driver.advance(clock()) is None
    assert not graphics.begun
    driver.execute("ReleaseTrial", release, clock() + 100_000_000)
    assert driver.advance(clock()) == release.start_monotonic_ns
    assert not reports.lifecycle("started")
    clock.value = release.start_monotonic_ns
    driver.advance(clock())
    started, deadline = reports.lifecycle("started")[0]
    assert started.actual_start_monotonic_ns >= release.start_monotonic_ns
    assert (
        deadline
        == release.start_monotonic_ns + driver.policies.start_evidence_allowance_ns
    )
    clock.value = release.normal_end_monotonic_ns
    driver.advance(clock())
    assert reports.lifecycle("stopped")[0][0].visual_stimulus_idle
    assert not reports.lifecycle("finished")
    recorder.results = ()
    driver.advance(clock())
    assert reports.lifecycle("finished")
    assert recorder.calls == [
        "configure",
        "schedule",
        "before_render",
        "rendered",
        "finish",
    ]


@pytest.mark.parametrize("late_publication", [False, True])
def test_recording_closure_does_not_block_gl_or_extend_deadline(late_publication):
    driver, clock, reports, recorder, graphics, command, release = prepared_driver(
        saving=True
    )
    driver.execute("ReleaseTrial", release, clock() + 100_000_000)
    clock.value = release.start_monotonic_ns
    driver.advance(clock())
    clock.value += 100
    driver.execute(
        "StopTrial",
        visual_stimulus.WorkerStop(command=command(True)),
        clock() + 100_000_000,
    )
    deadline = recorder.deadline
    assert reports.lifecycle("stopped")
    assert not reports.lifecycle("finished")
    assert driver.advance(clock()) is not None
    cleanup = command()
    cleanup_deadline = clock() + 100_000_000
    deferred = driver.execute("Cleanup", cleanup, cleanup_deadline)
    assert deferred is not None and not deferred.done()
    assert not reports.lifecycle("cleanup")
    assert recorder.deadline == deadline
    if late_publication:
        trial = driver.state.trial
        assert trial is not None and trial.schedule is not None
        trial.schedule.outputs.add(
            output_key="recipe", output_tag="stimulus_LOG", path="recipe.json"
        )
        driver.execute(
            "ConfirmRecipePublication",
            visual_stimulus.WorkerRecipePublication(
                command=command(True),
                prepared=trial.artifact.handle,
                published=True,
                path="recipe.json",
            ),
            clock() + 100,
        )
        clock.value += 200
    recorder.results = ()
    driver.advance(clock())
    assert deferred.done() and deferred.exception() is None
    assert reports.lifecycle("finished")
    assert reports.lifecycle("cleanup")
    assert reports.lifecycle("cleanup")[0][1] == cleanup_deadline
    assert reports.lifecycle("finished")[0][1] == deadline


def test_cancel_before_onset_has_no_started_or_finished_and_joins_cleanup():
    driver, clock, reports, recorder, graphics, command, release = prepared_driver(
        saving=True
    )
    driver.execute("ReleaseTrial", release, clock() + 100_000_000)
    future = driver.execute("Cleanup", command(), clock() + 100_000_000)
    assert recorder.calls == ["configure", "schedule", "cancel"]
    assert future is not None
    recorder.results = ()
    driver.advance(clock())
    assert future.done()
    assert not reports.lifecycle("started")
    assert not reports.lifecycle("finished")
    assert not graphics.begun


@pytest.mark.parametrize("begun", [False, True])
@pytest.mark.parametrize("invalid", [None, "prepared", "path", "failure"])
def test_recipe_publication_after_stop_preserves_recording_ownership(begun, invalid):
    driver, clock, reports, recorder, graphics, command, release = prepared_driver(
        saving=True
    )
    trial = driver.state.trial
    assert trial is not None and trial.schedule is not None
    trial.schedule.outputs.add(
        output_key="recipe", output_tag="stimulus_LOG", path="reserved-recipe.json"
    )
    driver.execute("ReleaseTrial", release, clock() + 100_000_000)
    if begun:
        clock.value = release.start_monotonic_ns
        driver.advance(clock())
    driver.execute(
        "InterruptSession",
        visual_stimulus.WorkerStop(command=command(True)),
        clock() + 100_000_000,
    )
    deadline, cutoff = trial.finish_deadline_ns, trial.cutoff_ns
    publication = visual_stimulus.WorkerRecipePublication(
        command=command(True),
        published=True,
        prepared=trial.artifact.handle,
        path="reserved-recipe.json",
    )
    if invalid == "prepared":
        publication.prepared.plan_sha256 = "different"
    elif invalid == "path":
        publication.path = "other-recipe.json"
    elif invalid == "failure":
        publication.published = False
    if invalid:
        with pytest.raises(RuntimeError, match="recipe"):
            driver.execute("ConfirmRecipePublication", publication, clock() + 1000)
    else:
        driver.execute("ConfirmRecipePublication", publication, clock() + 1000)
    assert recorder.calls.count("publication") == int(begun and invalid is None)
    assert trial.stopped and not trial.finished
    assert (trial.finish_deadline_ns, trial.cutoff_ns) == (deadline, cutoff)
    assert not reports.lifecycle("finished")
    assert trial.begun == begun
    assert not graphics.begun


def test_idle_failure_cannot_be_promoted_to_stopped():
    driver, clock, reports, recorder, graphics, command, release = prepared_driver()
    driver.execute("ReleaseTrial", release, clock() + 100_000_000)
    clock.value = release.start_monotonic_ns
    driver.advance(clock())
    graphics.fail_idle = True
    with pytest.raises(RuntimeError, match="Idle"):
        driver.execute(
            "StopTrial",
            visual_stimulus.WorkerStop(command=command(True)),
            clock() + 100_000_000,
        )
    assert not reports.lifecycle("stopped")
    assert not reports.lifecycle("finished")


@pytest.mark.parametrize("interrupted", [False, True])
def test_late_stop_keeps_scheduled_producer_cutoff(interrupted):
    driver, clock, reports, recorder, graphics, command, release = prepared_driver()
    driver.execute("ReleaseTrial", release, clock() + 100_000_000)
    clock.value = release.start_monotonic_ns
    driver.advance(clock())
    clock.value = release.normal_end_monotonic_ns + 100
    if interrupted:
        driver.execute(
            "InterruptSession",
            visual_stimulus.WorkerStop(command=command(True)),
            clock() + 100_000_000,
        )
    else:
        driver.advance(clock())
    stopped, deadline = reports.lifecycle("stopped")[0]
    assert stopped.actual_stop_monotonic_ns == release.normal_end_monotonic_ns
    assert stopped.producer_ends[0].end_monotonic_ns == release.normal_end_monotonic_ns
    assert (
        deadline
        == release.normal_end_monotonic_ns + driver.policies.stop_evidence_allowance_ns
    )
    assert driver.state.trial.finish_deadline_ns == (
        release.normal_end_monotonic_ns + driver.policies.trial_finished.initial_ns
    )


def test_cleanup_keeps_graphics_until_capture_cancellation_is_confirmed():
    from cephvr.visual_stimulus.worker.cleanup import cleanup_resources

    driver, clock, reports, recorder, graphics, command, release = prepared_driver()
    calls = []
    recorder.cleanup = lambda _: ResourceReleaseReport((), ("pending-pbo",))
    graphics.cleanup = lambda deadline_ns=None: (
        calls.append(("graphics", deadline_ns)) or ResourceReleaseReport(())
    )
    cleanup_command = command()
    deadline = clock() + 10_000_000

    def clean():
        cleanup_resources(
            driver.state,
            cleanup_command,
            worker=driver.worker,
            deadline_ns=deadline,
            clock=clock,
            recording=recorder,
            preparation=driver.preparation,
            engine=graphics,
            feedback=None,
            emit=driver.lifecycle,
        )

    with pytest.raises(RuntimeError, match="cleanup remains unconfirmed"):
        clean()
    assert not calls
    assert not driver.state.cleaned
    recorder.cleanup = lambda _: ResourceReleaseReport(())
    clean()
    assert calls == [("graphics", deadline)] and driver.state.cleaned
    assert all(item[1] == deadline for item in reports.lifecycle("cleanup"))


@pytest.mark.parametrize("saving", [False, True])
def test_delayed_clipping_diagnostics_drain_before_finished_with_original_group(saving):
    driver, clock, reports, recorder, graphics, command, release = prepared_driver(
        saving
    )
    driver.execute("ReleaseTrial", release, clock() + 100_000_000)
    clock.value = release.start_monotonic_ns
    driver.advance(clock())
    graphics.diagnostic_queue[0] = replace(
        graphics.diagnostic_queue[0], stages=("linear_output",)
    )
    poll = graphics.poll_diagnostics
    graphics.poll_diagnostics = lambda: ()
    recorder.results = ()
    clock.value = release.normal_end_monotonic_ns
    driver.advance(clock())
    assert reports.lifecycle("stopped") and not reports.lifecycle("finished")
    assert "finish" not in recorder.calls
    graphics.poll_diagnostics = poll
    driver.advance(clock())
    finished, deadline = reports.lifecycle("finished")[0]
    summary = finished.visual_stimulus_timing_summaries[0]
    assert summary.linear_output_clipped_groups == 1
    assert summary.alpha_clipped_groups == summary.device_code_clipped_groups == 0
    assert (
        deadline
        == release.normal_end_monotonic_ns + driver.policies.trial_finished.initial_ns
    )
    assert recorder.calls[-1] == "finish"
    assert recorder.diagnostic_records[0].group_id == 0
    assert (
        recorder.diagnostic_records[0].evaluation_host_ns == release.start_monotonic_ns
    )


def test_timing_counts_actual_submissions_and_epochs_without_attempts():
    driver, clock, reports, recorder, graphics, command, release = prepared_driver()
    graphics.begin_trial(release.command.target.work.trial.trial_id, clock())
    update = graphics.render_tick(clock())
    original = SubmissionSnapshot(
        update.group.outputs[0].output_id,
        0,
        "returned",
        clock(),
        clock(),
        1,
        None,
        None,
        None,
    )
    output_id = original.output_id
    timing = OutputTiming()
    update = replace(
        update,
        evidence_submissions=(
            replace(original, phase="returned", attempt_index=0),
            replace(original, phase="failed", attempt_index=1),
            replace(original, phase="unknown", attempt_index=2),
            replace(original, phase="not_attempted", attempt_index=None),
        ),
    )
    timing.observe(output_id, update)
    summary = timing.report("trial", output_id, 1, {0, 1, 2})
    assert summary.render_groups == 1
    assert summary.submission_attempts == 3
    assert summary.returned_submissions == 1
    assert summary.failed_submissions == 1
    assert summary.unknown_submissions == 1
    assert summary.epochs_without_submission == 2


def test_cleanup_retains_prior_trial_results_and_unscheduled_output_absence():
    driver, clock, reports, recorder, graphics, command, release = prepared_driver()
    driver.state.outputs["previous"] = pb.OutputResult(
        output_key="previous", closure=pb.OUTPUT_CLOSURE_CLOSED, artifact_present=True
    )
    driver.state.outputs["unscheduled"] = pb.OutputResult(
        output_key="unscheduled",
        closure=pb.OUTPUT_CLOSURE_NOT_STARTED,
        artifact_present=False,
    )
    recorder.results = ()
    driver.execute("Cleanup", command(), clock() + 100_000_000)
    outputs = {
        item.output_key: item for item in reports.lifecycle("cleanup")[0][0].outputs
    }
    assert outputs["previous"].artifact_present
    assert outputs["unscheduled"].closure == pb.OUTPUT_CLOSURE_NOT_STARTED
    assert not outputs["unscheduled"].artifact_present


def test_session_cleanup_retires_finished_trial_before_display_calibration():
    import hashlib
    from types import SimpleNamespace

    from cephvr.visual_stimulus.config.models.display_profile import parse_display_json
    from cephvr.visual_stimulus.rendering.types import OutputActivity
    from cephvr.visual_stimulus.v1 import runtime_pb2 as vp

    driver, clock, _, _, _, command, _ = prepared_driver()
    retired_trial = driver.state.trial
    assert retired_trial is not None
    with pytest.raises(RuntimeError, match="cannot overlap a trial"):
        driver.execute(
            "OpenDisplayCalibration",
            visual_stimulus.OpenDisplayCalibrationCommand(command=command()),
            clock() + 100_000_000,
        )
    retired_trial.finished = True
    driver.execute("Cleanup", command(), clock() + 100_000_000)
    assert driver.state.cleaned
    assert driver.state.setup is None

    profile_json = valid_display_json()
    profile = parse_display_json(profile_json, max_bytes=1_000_000)
    prepared = SimpleNamespace(display=profile, previous_display=None)
    driver.preparation.prepare_display_calibration = lambda *_args, **_kwargs: prepared
    driver.preparation.release_display_calibration = lambda _prepared: True
    driver.engine.present_display_calibration = lambda *_args: (
        OutputActivity("projector/main", clock(), clock() + 1, 1),
    )
    calibration_command = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        issuer=driver.owner,
        target=visual_stimulus.WorkerContext(
            worker=driver.worker,
            owner=driver.owner,
            configuration_revision=1,
        ),
        parent_operation=pb.OperationContext(command_id=str(uuid4())),
        deadline_monotonic_ns=clock() + 100_000_000,
    )
    request = visual_stimulus.OpenDisplayCalibrationCommand(
        command=calibration_command,
        diagnostic_id=str(uuid4()),
        profile_json=profile_json,
        profile_sha256=hashlib.sha256(profile_json.encode()).hexdigest(),
        asset_root="/accepted",
        arena_relative_path="calibration/arena.glb",
        arena_size_bytes=64,
        arena_sha256="a" * 64,
        policies=vp.VisualStimulusFilePolicies(
            limits=vp.ResourceLimits(max_document_bytes=1_000_000)
        ),
    )
    completion = driver.execute(
        "OpenDisplayCalibration", request, calibration_command.deadline_monotonic_ns
    )
    assert completion is not None
    for _ in range(100):
        driver.advance(clock())
        if completion.done():
            break
        threading.Event().wait(0.001)
    completion.result(timeout=1)
    assert driver.display_calibration.evidence.state == (
        vp.DISPLAY_CALIBRATION_STATE_ACTIVE
    )


def test_repeated_sessionless_shutdown_retires_release_receipts():
    driver, clock, reports, recorder, graphics, command, _ = prepared_driver()
    driver.state.trial.finished = True
    retired_trial = driver.state.trial
    registered_resources = set(driver.state.resources)
    assert registered_resources

    driver.execute("Cleanup", command(), clock() + 100_000_000)
    cleanup = reports.lifecycle("cleanup")[-1][0]
    assert {item.resource for item in cleanup.resources} == registered_resources
    assert all(item.released for item in cleanup.resources)
    assert driver.state.setup is None
    assert not driver.state.resources
    assert driver.state.trial is None
    assert retired_trial.finished
    assert driver.state.catalogue_revision == cleanup.cleanup_resources_revision + 1
    assert graphics.retired_resource_catalogues == 1
    assert recorder.retired_resource_catalogues == 1

    shutdown = command()
    shutdown.target.ClearField("work")
    driver.execute("Shutdown", shutdown, clock() + 100_000_000)
    assert not driver.state.resources
    assert not driver.state.pending_resources

    repeated_shutdown = command()
    repeated_shutdown.target.ClearField("work")
    driver.execute("Shutdown", repeated_shutdown, clock() + 100_000_000)
    assert not driver.state.resources


@pytest.mark.parametrize(
    ("closure", "artifact_present"),
    [
        (pb.OUTPUT_CLOSURE_UNCONFIRMED, True),
        (pb.OUTPUT_CLOSURE_CLOSED, None),
    ],
)
def test_cleanup_keeps_catalogue_when_output_closure_is_unknown(
    closure, artifact_present
):
    driver, clock, reports, recorder, graphics, command, _ = prepared_driver()
    driver.state.trial.finished = True
    driver.state.outputs["unknown-output"] = pb.OutputResult(
        output_key="unknown-output", closure=closure
    )
    if artifact_present is not None:
        driver.state.outputs["unknown-output"].artifact_present = artifact_present
    registered_resources = set(driver.state.resources)

    with pytest.raises(
        RuntimeError, match="output closure unconfirmed: unknown-output"
    ):
        driver.execute("Cleanup", command(), clock() + 100_000_000)

    cleanup = reports.lifecycle("cleanup")[-1][0]
    assert {item.resource for item in cleanup.resources} == registered_resources
    unknown = next(
        item for item in cleanup.outputs if item.output_key == "unknown-output"
    )
    assert unknown.closure == closure
    assert unknown.HasField("artifact_present") == (artifact_present is not None)
    assert driver.state.setup is not None
    assert driver.state.resources.keys() == registered_resources
    assert not driver.state.cleaned
    assert graphics.retired_resource_catalogues == 0
    assert recorder.retired_resource_catalogues == 0
    assert driver.preparation.retired_resource_catalogues == 0
    assert driver.state.trial is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,rejected,benign",
    [
        ("UpdateDisplayCalibration", True, True),
        ("UpdateDisplayCalibration", False, False),
        ("OpenDisplayCalibration", True, False),
    ],
)
async def test_render_mailbox_retains_typed_update_rejection_without_failing_driver(
    method, rejected, benign
):
    from cephvr.visual_stimulus.config.calibration_adjustments import (
        CalibrationAdjustmentRejected,
    )
    from cephvr.visual_stimulus.worker.owner import RenderOwner

    clock = Clock()
    error = (
        CalibrationAdjustmentRejected("invalid placement")
        if rejected
        else RuntimeError("presentation failed")
    )

    class Driver:
        def __init__(self):
            self.failures = []
            self.commands = []

        def execute(self, selected, request, deadline_ns):
            self.commands.append(selected)
            if len(self.commands) == 1:
                raise error

        def advance(self, now_ns):
            return None

        def fail(self, failure):
            self.failures.append(failure)

    driver = Driver()
    owner = RenderOwner(lambda _: driver, clock=clock)
    try:
        with pytest.raises(type(error), match=str(error)):
            await owner.submit(method, pb.OperationState(), clock() + 1_000_000_000)
        await owner.submit(
            "UpdateDisplayCalibration", pb.OperationState(), clock() + 1_000_000_000
        )
        assert driver.failures == ([] if benign else [error])
        assert owner.failure is None
        assert not owner.cancelled.is_set()
        assert len(driver.commands) == 2
    finally:
        await owner.close(clock() + 1_000_000_000)


@pytest.mark.asyncio
async def test_idle_wakeup_tracks_native_progress_without_counting_idle_as_stall():
    import asyncio

    from cephvr.visual_stimulus.worker.owner import RenderOwner

    clock = Clock()
    entered, unblock = threading.Event(), threading.Event()

    class Driver:
        calls = 0

        def advance(self, now_ns):
            self.calls += 1
            if self.calls > 1:
                entered.set()
                assert unblock.wait(1)
            return None

        def fail(self, error):
            raise AssertionError(error)

    driver = Driver()
    owner = RenderOwner(lambda _: driver, clock=clock)
    try:
        async with asyncio.timeout(1):
            while owner.progress_required:
                await asyncio.sleep(0)
        clock.value += 10_000_000_000
        owner.cancel()
        assert await asyncio.to_thread(entered.wait, 1)
        assert owner.progress_required
        assert owner.last_progress_ns == clock()
    finally:
        unblock.set()
        await owner.close(clock() + 1_000_000_000)


def test_image_loader_cleanup_keeps_protected_sources_until_joined() -> None:
    from cephvr.visual_stimulus.resources.session import NativePreparation

    class Source:
        closed = False

        def close_after_consumers(self):
            self.closed = True

    class Cache:
        joined = False
        deadlines = []

        def close(self, deadline):
            self.deadlines.append(deadline)
            return self.joined

    preparation = NativePreparation(
        Graphics(Clock(), make_prepared_trial()),
        renderer_generation="renderer",
        clock_ns=lambda: 1,
    )
    source, cache = Source(), Cache()
    preparation._protected_sources.append((source, "protected-image"))
    preparation._resource_keys.extend(
        ("protected-image", "visual_stimulus:image-loader")
    )
    preparation.image_residency = cache
    first = preparation.cleanup(100)
    assert first.outstanding == ("image-loader:worker remains active",)
    assert not first.released
    assert not source.closed
    assert preparation.image_residency is cache
    cache.joined = True
    second = preparation.cleanup(100)
    assert not second.outstanding
    assert set(second.released) == {"protected-image", "visual_stimulus:image-loader"}
    assert source.closed
    assert preparation.image_residency is None
    assert cache.deadlines == [100, 100]


def test_native_preparation_compiles_deferred_recipe_and_installs_initial_residency(
    tmp_path,
):
    import json
    import time

    from cephvr.visual_stimulus.rendering.types import (
        DisplayInitialization,
        OutputActivity,
    )
    from cephvr.visual_stimulus.resources.session import NativePreparation
    from cephvr.visual_stimulus.v1 import runtime_pb2 as vp

    from .support import fixture_source

    sources = []
    announcements = []

    class Source:
        def __init__(self, path):
            self.path, self.closed = path, False
            sources.append(self)

        def independent_reader(self):
            assert not self.closed
            return self.path.open("rb")

        def close_after_consumers(self):
            self.closed = True

    class Gpu:
        def upload(self, source, pixels, textures):
            assert len(pixels) == source.width * source.height * 16
            textures.append(object())
            return True

        def fence(self, textures, fences):
            fences.append(object())

        def ready(self, fences):
            return True

        def release(self, textures, fences):
            textures.clear()
            fences.clear()

    class Port:
        cache = None

        def __init__(self):
            self.resources, self.prepared = {}, []

        def install_display_calibration(self, calibration):
            self.calibration = calibration

        def initialize_display(self, display):
            outputs = display.active_outputs
            return DisplayInitialization(
                tuple(output.output_id for output in outputs),
                tuple((output.output_id, 8, 8, 8) for output in outputs),
                tuple(
                    (output.output_id, output.width_px, output.height_px)
                    for output in outputs
                ),
                tuple((output.output_id, 1) for output in outputs),
                tuple(OutputActivity(output.output_id, 1, 1, 1) for output in outputs),
            )

        def replay_provenance(self):
            from cephvr.visual_stimulus.resources.provenance import graphics_provenance

            return graphics_provenance(
                "fixture",
                {
                    "GL_VENDOR": "fixture-vendor",
                    "GL_RENDERER": "fixture-renderer",
                    "GL_VERSION": "fixture-driver",
                },
            )

        def install_image_residency(self, cache, deadline_ns):
            self.cache = cache
            cache.attach(
                Gpu(), self.resources, lambda key, path: announcements.append(key)
            )
            cache.prepare(deadline_ns)

        def prepare_trial(self, artifact, bundle):
            assert "recipe" not in bundle.prepared_content
            for asset_id in bundle.image_sources:
                key = f"{artifact.identity.resource_generation}:{asset_id}"
                assert len(self.resources[key]) == 1
            self.prepared.append(artifact.identity.trial_id)

        def release(self, deadline_ns=None):
            if self.cache is None:
                return ResourceReleaseReport(())
            outstanding = self.cache.release_gpu()
            return ResourceReleaseReport(tuple(self.cache.released_keys), outstanding)

    root_recipe = tmp_path / "texture.json"
    root_recipe.write_text(
        '{"pattern":"checker","params":{"texture_resolution":8,"tile_width_mm":40}}'
    )
    program = json.loads(fixture_source())
    program["assets"] = [
        {
            "asset_id": "recipe",
            "logical_path": "texture.json",
            "profile": "cephvr1_texture_json_v1",
            "color_override": None,
        }
    ]
    for epoch in program["sequence"]:
        epoch["settings"][0]["pattern"] = {
            "kind": "image_tile",
            "asset_id": "recipe",
            "period_x": {"kind": "constant", "value": 40},
            "period_y": {"kind": "constant", "value": 40},
            "sampling": "linear",
        }
    request = visual_stimulus.WorkerSetup()
    request.session.context.session_id = str(uuid4())
    request.session.configuration.asset_root = str(tmp_path)
    request.session.configuration_revision = 1
    trial = request.session.trials.add()
    trial.context.session.CopyFrom(request.session.context)
    trial.context.trial_id = str(uuid4())
    trial.definition.trial_number = 1
    trial.definition.stimulus.program.program_json = json.dumps(program)
    trial.definition.stimulus.arena_boundaries.boundaries_json = (
        '{"format_version":1,"bindings":[]}'
    )
    trial.definition.stimulus.stimulus_seed_decimal = "17"
    request.settings.display.profile_json = valid_display_json()
    from cephvr.visual_stimulus.config.models.display_profile import parse_display_json

    display = parse_display_json(
        request.settings.display.profile_json, max_bytes=1_000_000
    )
    profiles = _geometric_profiles(display)
    for mapping in display.active_mappings:
        path = tmp_path / mapping.geometric_profile.logical_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(profiles[mapping.mapping_id].model_dump_json())
    request.policies.contract_version = 1
    request.policies.limits.CopyFrom(
        vp.ResourceLimits(
            max_document_bytes=1_000_000,
            max_asset_cpu_bytes=64_000_000,
            max_asset_gpu_bytes=64_000_000,
            max_expanded_epochs=1000,
            max_prepared_plan_bytes=1_000_000,
            decoder_threads=1,
            decoder_contexts=1,
            codec_threads_per_context=1,
            codec_threads_total=1,
            decoded_frames_per_instance=1,
            decoded_bytes_total=1_000_000,
            decoder_working_bytes_total=1_000_000,
        )
    )
    port = Port()
    preparation = NativePreparation(
        port, renderer_generation=str(uuid4()), source_factory=Source
    )
    deadline = time.monotonic_ns() + 5_000_000_000
    try:
        batches = []
        progress = []
        artifacts = preparation.prepare_trials(
            request,
            lambda key, path: announcements.append(key),
            deadline,
            announce_batch=batches.append,
            progress=progress.append,
        )
        assert "Trial 1/1 — Decoding and validating textures: 1/1" in progress
        assert not any("uploading" in message for message in progress)
        assert len(batches) == 1
        assert (
            batches[0][0][0] == f"visual_stimulus:{trial.context.trial_id}:asset:recipe"
        )
        bundle = preparation.resources_for(trial.context.trial_id)
        assert "recipe" not in bundle.prepared_content
        assert tuple(bundle.image_sources) == ("recipe",)
        assert bundle.asset_set.assets[0].data is None
        assert (
            artifacts[0].manifest.resources[0].profile_id == "cephvr1_texture_json_v1"
        )
        assert preparation.image_residency is not None
        artifacts = preparation.prepare_graphics(artifacts)
        assert "Decoding and uploading initial textures to projectors: 1/1" in progress
        assert progress[-1] == "Initial textures ready; publishing prepared trials"
        assert any(
            item.role == "graphics_driver" and item.version == "fixture-driver"
            for item in artifacts[0].manifest.provenance
        )
        assert (
            preparation.resources_for(trial.context.trial_id).manifest
            == artifacts[0].manifest
        )
        assert port.prepared == [trial.context.trial_id]
        assert port.cache is preparation.image_residency
        assert len(batches) == 2
        assert all("gpu:resident-image" in key for key, _ in batches[1])
        assert not any("gpu:resident-image" in key for key in announcements)
    finally:
        graphics = preparation.engine.cleanup()
        assert not graphics.outstanding
        closed = preparation.cleanup(time.monotonic_ns() + 5_000_000_000)
        assert not closed.outstanding
    assert sources and all(source.closed for source in sources)
    assert preparation.image_residency is None
    assert not preparation._bundles


@pytest.mark.parametrize("failure", [None, "deadline", "foreign_owner"])
def test_prepared_heap_preserves_gc_ownership_deadline_and_reuse(monkeypatch, failure):
    from types import SimpleNamespace

    from cephvr.visual_stimulus.resources import prepared_heap

    events = []
    frozen = [5 if failure == "foreign_owner" else 0]

    def freeze():
        events.append("freeze")
        frozen[0] = 100

    def unfreeze():
        events.append("unfreeze")
        frozen[0] = 0

    monkeypatch.setattr(
        prepared_heap,
        "gc",
        SimpleNamespace(
            get_freeze_count=lambda: frozen[0],
            collect=lambda: events.append("collect"),
            freeze=freeze,
            unfreeze=unfreeze,
        ),
    )
    heap = prepared_heap.PreparedHeap()

    def check():
        if failure == "deadline" and "collect" in events:
            raise TimeoutError("original Setup deadline")

    try:
        if failure:
            with pytest.raises(TimeoutError if failure == "deadline" else RuntimeError):
                heap.prepare(check)
        else:
            heap.prepare(check)
            heap.prepare(check)
            assert events == ["collect", "freeze"]
    finally:
        heap.release()
        heap.release()
    if failure == "foreign_owner":
        assert frozen == [5] and events == []
    elif failure == "deadline":
        assert frozen == [0] and events == ["collect"]
    else:
        assert frozen == [0] and events == ["collect", "freeze", "unfreeze"]
        heap.prepare(check)
        heap.release()
        assert events == ["collect", "freeze", "unfreeze"] * 2


def test_prepared_heap_collects_new_cycles_and_releases_prepared_cycles():
    import subprocess
    import sys
    import textwrap

    # Isolate the interpreter-global heap from pytest and its fixture graph.
    subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent("""
        import gc
        import weakref
        from cephvr.visual_stimulus.resources.prepared_heap import PreparedHeap
        class Node:
            pass
        old = Node()
        old.link = old
        old_ref = weakref.ref(old)
        heap = PreparedHeap()
        enabled = gc.isenabled()
        heap.prepare(lambda: None)
        try:
            assert gc.isenabled() == enabled
            del old
            young = Node()
            young.link = young
            young_ref = weakref.ref(young)
            del young
            gc.collect()
            assert young_ref() is None
            assert old_ref() is not None
        finally:
            heap.release()
        gc.collect()
        assert old_ref() is None
        assert gc.get_freeze_count() == 0
        assert gc.isenabled() == enabled
        """),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )


@pytest.mark.parametrize("failure", [None, "graphics", "cancelled", "deadline", "size"])
def test_setup_publishes_only_final_graphics_provenance_under_original_deadline(
    failure,
    tmp_path,
):
    import hashlib
    import time

    from cephvr.visual_stimulus.compiler import serialize_prepared_trial
    from cephvr.visual_stimulus.resources.provenance import graphics_provenance
    from cephvr.visual_stimulus.worker.preparation import begin

    artifact = make_prepared_trial()
    manifest = artifact.manifest.model_copy(
        update={
            "provenance": graphics_provenance(
                "test",
                {
                    "GL_VENDOR": "vendor",
                    "GL_RENDERER": "renderer",
                    "GL_VERSION": "driver",
                },
            )
        }
    )
    final = artifact.model_copy(update={"manifest": manifest})
    request = visual_stimulus.WorkerSetup()
    request.session.trials.add().context.trial_id = artifact.identity.trial_id
    if failure == "size":
        request.policies.limits.max_prepared_plan_bytes = len(
            serialize_prepared_trial(artifact)
        )
    deadline = time.perf_counter_ns() + 5_000_000_000
    owner = threading.get_ident()
    recorded, reported, events = [], [], []

    class Prepare:
        def prepare_trials(self, *_, **kwargs):
            assert threading.get_ident() != owner
            return (artifact,)

        def prepare_graphics(self, artifacts):
            assert threading.get_ident() == owner
            events.append("graphics")
            assert artifacts == (artifact,)
            if failure == "graphics":
                raise ValueError("context unavailable")
            return (final,)

    class Recording:
        def prepare_artifacts(self, artifacts, bound):
            assert threading.get_ident() != owner and bound == deadline
            assert artifacts == (final,)
            recorded.extend(artifacts)

    class Report:
        def confirm(self, method, message, bound):
            assert threading.get_ident() != owner and bound == deadline
            reported.append(message)

    preparer = Prepare()
    job = begin(
        request,
        preparer,
        Recording(),
        Report(),
        lambda *_: None,
        deadline,
        time.perf_counter_ns,
    )
    assert job.graphics_input.result(timeout=1) == (artifact,)
    assert not recorded and not reported and not job.result.done()
    job.service_graphics(
        preparer,
        cancelled=failure == "cancelled",
        now_ns=deadline if failure == "deadline" else time.perf_counter_ns(),
    )
    if failure is None:
        records = job.result.result(timeout=1)
        data = serialize_prepared_trial(final)
        assert records[0].artifact == final and records[0].data == data
        assert records[0].handle.plan_sha256 == hashlib.sha256(data).hexdigest()
        assert reported[0].prepared_artifact.prepared_trial_json.encode() == data
        assert recorded == [final]
        from cephvr.visual_stimulus.recording.recipe import (
            prepare_recipe,
            publish_recipe,
        )

        recipe = prepare_recipe(recorded[0], max_bytes=1_000_000)
        path = tmp_path / "trial_stimulus_LOG.json"
        reference = publish_recipe(
            path,
            path.name,
            recipe,
            expected_sha256=records[0].handle.plan_sha256,
            expected_byte_length=records[0].handle.plan_bytes,
            trial_start_host_ns=100,
            now_host_ns=100,
        )
        assert path.read_bytes() == data
        assert reference.sha256 == records[0].handle.plan_sha256
    else:
        with pytest.raises((ValueError, InterruptedError, TimeoutError, MemoryError)):
            job.result.result(timeout=1)
        assert not reported
        assert not recorded
    job.thread.join(timeout=1)
    assert not job.thread.is_alive()
    job.service_graphics(preparer, cancelled=False, now_ns=time.perf_counter_ns())
    assert events == ([] if failure in ("cancelled", "deadline") else ["graphics"])


def test_preparation_job_reports_cpu_and_graphics_progress_with_setup_identity():
    import time

    from cephvr.visual_stimulus.worker.preparation import begin

    artifact = make_prepared_trial()
    request = visual_stimulus.WorkerSetup(
        command=visual_stimulus.WorkerCommand(
            command_id=str(uuid4()),
            target=visual_stimulus.WorkerContext(
                worker=pb.ProcessIdentity(
                    role="visual_stimulus_renderer", generation=str(uuid4())
                ),
                work=pb.WorkContext(
                    session=pb.SessionContext(session_id=artifact.identity.session_id)
                ),
            ),
        )
    )
    request.session.trials.add(
        context=pb.TrialContext(trial_id=artifact.identity.trial_id)
    )
    messages = []

    class ProgressReports(Reports):
        def send(self, method, message, deadline_ns, *, required=True):
            messages.append((method, message, deadline_ns, required))

    class Preparer(Preparation):
        def prepare_trials(self, *args, progress=None, **kwargs):
            self.progress = progress
            progress("Decoding textures: 1/1")
            return (self.artifact,)

        def prepare_graphics(self, artifacts):
            self.progress("Uploading initial textures: 1/1")
            return artifacts

    preparation = Preparer(artifact)
    deadline = time.perf_counter_ns() + 2_000_000_000
    job = begin(
        request,
        preparation,
        Recorder(),
        ProgressReports(),
        lambda *_: None,
        deadline,
        time.perf_counter_ns,
    )
    try:
        job.graphics_input.result(timeout=1)
        job.service_graphics(
            preparation, cancelled=False, now_ns=time.perf_counter_ns()
        )
        assert len(job.result.result(timeout=1)) == 1
        assert [item[1].operation.progress for item in messages] == [
            "Decoding textures: 1/1",
            "Uploading initial textures: 1/1",
        ]
        for method, report, bound, required in messages:
            assert method == "ReportWorkerOperation" and not required
            assert bound == deadline and report.source == request.command.target
            assert report.operation.context.command_id == request.command.command_id
            assert report.operation.work == request.command.target.work
            assert not report.operation.complete
    finally:
        job.thread.join(timeout=2)
        assert not job.thread.is_alive()


def test_preview_rates_use_optional_exact_session_reports_and_clear_on_hide():
    driver, clock, reports, *_ = prepared_driver()
    required_flags = []
    original_send = reports.send

    def send(method, message, deadline_ns, *, required=True):
        required_flags.append(required)
        original_send(method, message, deadline_ns, required=required)

    reports.send = send
    driver.preview_changed(True, True, "")
    driver.preview_rates(59.8, 29.9, clock())
    rate = reports.records[-1][1]
    assert not required_flags[-1]
    assert rate.rates.source_fps == 59.8 and rate.rates.preview_fps == 29.9
    assert rate.session == driver.state.setup.session.context
    driver.preview_changed(True, False, "")
    hidden = reports.records[-1][1]
    assert required_flags[-1] and not hidden.HasField("rates")
    revision = hidden.revision
    driver.preview_rates(60, 30, clock())
    assert reports.records[-1][1].revision == revision


class _HelperProcess:
    def __init__(self, feed):
        self.feed, self.events = feed, []
        self.failure = None

    def send(self, data, *, deadline_ns):
        self.feed.send(data, deadline_ns=deadline_ns)

    def take(self):
        return self.feed.take()

    def close_stdin(self, *, deadline_ns):
        self.events.append("eof")

    def wait(self, *, deadline_ns):
        self.events.append("wait")
        return 0

    def terminate(self, *, deadline_ns):
        self.events.append("terminate")


class _HelperLauncher:
    process_factory = None

    def __init__(self, process):
        self.process, self.calls = process, []

    def bind_operation(self, work, parent_operation):
        self.calls.append(("bind", work, parent_operation))

    def launch(self, argv, *, deadline_ns, role):
        self.calls.append(("launch", tuple(argv), role))
        return self.process

    def terminate_unconfirmed(self, *, deadline_ns):
        self.calls.append(("unconfirmed",))


class _SparseGraphics:
    def __init__(self):
        from tests.visual_stimulus.test_rendering import _SparseOutput

        self.output = _SparseOutput()
        self.sparse_outputs = {"projector/main": self.output}
        self.installed = []

    def install_sparse_noise(self, ring):
        self.installed.append(ring)


def _sparse_owner(**program):
    from tests.visual_stimulus.support import make_prepared_trial
    from tests.visual_stimulus.test_rendering import _SparseFeed
    from tests.visual_stimulus.test_resources import sparse_layer_program

    from cephvr.visual_stimulus.worker.sparse_noise import NativeSparseNoise

    process = _HelperProcess(_SparseFeed())
    launcher, graphics = _HelperLauncher(process), _SparseGraphics()
    owner = NativeSparseNoise(
        launcher=launcher,
        argv=lambda: ["C:/python.exe", "-m", "helper"],
        graphics=graphics,
        lookahead=4,
    )
    return (
        make_prepared_trial(sparse_layer_program(**program)),
        owner,
        launcher,
        process,
        graphics,
    )


def test_sparse_owner_declares_launches_prefills_and_confirms_helper_exit():
    from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus

    plan, owner, launcher, process, graphics = _sparse_owner()
    announced = []
    owner.declare((plan,), lambda key, path: announced.append(key))
    assert announced == ["sparse-noise-child:trial"]
    command = visual_stimulus.WorkerCommand(command_id="prepare")
    command.parent_operation.command_id = "operation"
    owner.prepare(plan, command, deadline_ns=1 << 62)
    assert [c[0] for c in launcher.calls] == ["bind", "launch"]
    assert launcher.calls[0][2].command_id == "operation"
    assert launcher.calls[1][2] == "visual_stimulus_sparse_noise"
    ring = graphics.installed[-1]
    assert ring.received == 8  # Four ahead for each of two layers, before Ready.
    owner.finish(deadline_ns=1 << 62)
    assert graphics.installed[-1] is None and process.events == ["eof", "wait"]
    assert all(t.released for t in graphics.output.created)
    report = owner.cleanup(deadline_ns=1 << 62)
    assert report.released == ("sparse-noise-child:trial",) and not report.outstanding


def test_sparse_owner_terminates_a_failed_helper_at_cleanup():
    from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus

    plan, owner, _, process, _ = _sparse_owner()
    owner.declare((plan,), lambda key, path: None)
    owner.prepare(plan, visual_stimulus.WorkerCommand(), deadline_ns=1 << 62)
    process.failure = RuntimeError("helper exited early with code 1")
    report = owner.cleanup(deadline_ns=1 << 62)
    assert process.events == ["terminate"] and not report.outstanding


def test_sparse_owner_skips_trials_without_sparse_layers():
    from tests.visual_stimulus.support import make_prepared_trial

    from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus

    _, owner, launcher, _, graphics = _sparse_owner()
    plain = make_prepared_trial()
    announced = []
    owner.declare((plain,), lambda key, path: announced.append(key))
    owner.prepare(plain, visual_stimulus.WorkerCommand(), deadline_ns=1 << 62)
    assert announced == [] and launcher.calls == [] and graphics.installed == []


def test_sparse_process_reader_splits_frames_and_rejects_truncation():
    import threading
    from collections import deque

    from cephvr.visual_stimulus.resources.sparse_noise_wire import frame_header
    from cephvr.visual_stimulus.worker.sparse_noise import SparseNoiseProcess

    class Pipe:
        def __init__(self, chunks):
            self.chunks = deque(chunks)

        def read(self, *, deadline_ns):
            return self.chunks.popleft() if self.chunks else None

    def process(chunks, stdin_closed=False):
        item = object.__new__(SparseNoiseProcess)
        item.progress_pipe = Pipe(chunks)
        item._lock, item._frames = threading.Lock(), deque()
        item._reader_error, item._reader_drain_deadline_ns = None, None
        item._stdin_closed, item._exit_code = stdin_closed, None
        item.max_frame_bytes, item.clock_ns = 8, lambda: 0
        return item

    digest = b"\x01" * 32
    data = frame_header(0, 2, digest) + b"ab" + frame_header(1, 1, digest) + b"c"
    complete = process([data[:7], data[7:]])
    complete._read_progress()
    assert complete.take() == [(0, b"ab", digest), (1, b"c", digest)]
    assert complete.failure is None
    truncated = process([data[:-1]])
    truncated._read_progress()
    assert "truncated" in str(truncated.failure)
    early = process([])
    early._exit_code = 1
    assert "exited early" in str(early.failure)
