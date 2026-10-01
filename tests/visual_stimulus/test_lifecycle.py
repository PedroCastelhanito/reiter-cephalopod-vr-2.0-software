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


def prepared_driver(saving=False):
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
    setup.settings.display.profile_json = valid_display_json()
    setup.policies.limits.max_document_bytes = 1_000_000
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
    assert reports.lifecycle("finished")
    assert recorder.calls == ["configure"]


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
    if saving:
        assert recorder.calls[-1] == "finish"
        assert recorder.diagnostic_records[0].group_id == 0
        assert (
            recorder.diagnostic_records[0].evaluation_host_ns
            == release.start_monotonic_ns
        )
    else:
        assert recorder.diagnostic_records == []


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
