"""Scheduled graphics-owner lifecycle with controlled time and native-only adapters."""

from __future__ import annotations

import threading
from dataclasses import replace
from uuid import uuid4

import pytest

from cephvr.control.v1 import types_pb2 as pb
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
        assert "cephvr-python.exe" in view.issues[0].failure.message
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
    driver.cleanup(command)
    assert driver.state.cleaned
    assert not driver.state.pending_resources
    assert not driver.state.resources
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
    graphics.cleanup = lambda: ResourceReleaseReport((), ("display:unknown",))
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


@pytest.mark.parametrize("fail_update", [False, True])
def test_sessionless_display_calibration_requires_presentation_then_closed_idle(
    fail_update,
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

    class EngineStub:
        def present_display_calibration(self, selected, asset):
            assert selected == profile and asset is prepared
            return (OutputActivity("projector/main", 10, 11, 1),)

        def update_display_calibration(self, selected, asset, adjustments):
            assert selected == profile and asset is prepared
            assert "front" in adjustments
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

    update = visual_stimulus.UpdateDisplayCalibrationCommand(
        command=command, diagnostic_id=opened.diagnostic_id, adjustment_sequence=1
    )
    update.adjustments.add(
        mapping_id="front", destination_xy=[0.1, 0.1, 0.9, 0.1, 0.1, 0.9, 0.9, 0.9]
    )
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
        update.adjustments[0].destination_xy[0] = -1
        with pytest.raises(ValueError):
            owner.update(update, command.deadline_monotonic_ns)
        assert owner.evidence.state == vp.DISPLAY_CALIBRATION_STATE_ACTIVE
        assert owner.evidence.adjustment_sequence == 1
        assert owner.evidence.failure_code == "CALIBRATION_ADJUSTMENT_REJECTED"
        update.adjustments[0].destination_xy[0] = 0.1
        owner.update(update, command.deadline_monotonic_ns)
        assert owner.evidence.adjustment_sequence == 2
        assert not owner.evidence.failure_code
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
    from pathlib import Path

    from cephvr.visual_stimulus.rendering.types import ResourceReleaseReport
    from cephvr.visual_stimulus.resources import (
        display_calibration as resource_calibration,
    )
    from cephvr.visual_stimulus.resources.calibration import PreparedCalibration
    from cephvr.visual_stimulus.resources.session import NativePreparation
    from cephvr.visual_stimulus.v1 import runtime_pb2 as vp
    from cephvr.visual_stimulus.worker.lifecycle import LifecycleDriver

    from .test_resources import glb_fixture, pack_glb

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

        def release(self):
            return ResourceReleaseReport(())

    class Engine:
        def service_display(self):
            return False

        @property
        def diagnostics_pending(self):
            return False

        def poll_diagnostics(self):
            return ()

        def cleanup(self):
            return ResourceReleaseReport(())

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


def test_recording_closure_does_not_block_gl_or_extend_deadline():
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
    deferred = driver.execute("Cleanup", cleanup, clock() + 100_000_000)
    assert deferred is not None and not deferred.done()
    assert not reports.lifecycle("cleanup")
    assert recorder.deadline == deadline
    recorder.results = ()
    driver.advance(clock())
    assert deferred.done() and deferred.exception() is None
    assert reports.lifecycle("finished")
    assert reports.lifecycle("cleanup")


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
    graphics.cleanup = lambda: calls.append("graphics") or ResourceReleaseReport(())
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
    assert calls == ["graphics"] and driver.state.cleaned
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

        def fence(self, fences):
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

        def release(self):
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

    from .test_display_calibration_rendering import _geometric_profiles

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
        artifacts = preparation.prepare_trials(
            request, lambda key, path: announcements.append(key), deadline
        )
        bundle = preparation.resources_for(trial.context.trial_id)
        assert "recipe" not in bundle.prepared_content
        assert tuple(bundle.image_sources) == ("recipe",)
        assert bundle.asset_set.assets[0].data is None
        assert (
            artifacts[0].manifest.resources[0].profile_id == "cephvr1_texture_json_v1"
        )
        assert preparation.image_residency is not None
        preparation.prepare_graphics(artifacts)
        assert port.prepared == [trial.context.trial_id]
        assert port.cache is preparation.image_residency
        assert any("gpu:resident-image" in key for key in announcements)
    finally:
        graphics = preparation.engine.cleanup()
        assert not graphics.outstanding
        closed = preparation.cleanup(time.monotonic_ns() + 5_000_000_000)
        assert not closed.outstanding
    assert sources and all(source.closed for source in sources)
    assert preparation.image_residency is None
    assert not preparation._bundles
