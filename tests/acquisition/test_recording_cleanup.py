"""Recording fault isolation, bounded closure and exact output ownership."""

from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from cephvr.acquisition.buffers.pixel_pool import PixelBufferPool
from cephvr.acquisition.buffers.queue import RecordingQueue
from cephvr.acquisition.buffers.records import FrameRecord
from cephvr.acquisition.recording.progress_watchdog import EncoderProgressWatchdog
from cephvr.acquisition.recording.session_cleanup import cancel_before_start
from cephvr.acquisition.recording.session_contracts import RecordingFailure
from cephvr.acquisition.recording.session_finalizer import (
    FinalizationProgress,
    append_terminal_and_close,
)
from cephvr.acquisition.recording.session_outputs import successful_outputs
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.worker.cleanup_lifecycle import WorkerCleanupLifecycle
from cephvr.acquisition.worker.recording_fault import RecordingFaultLifecycle
from cephvr.acquisition.worker.recording_runtime import WorkerRecordingRuntime
from cephvr.acquisition.worker.trial_recording_terminal import TrialRecordingTerminal
from cephvr.control.v1 import types_pb2 as control


@pytest.mark.parametrize(
    "stop_request",
    [
        acq.WorkerCommand(),
        acq.WorkerStop(issued_monotonic_ns=20),
        acq.WorkerInterrupt(issued_monotonic_ns=20),
    ],
)
def test_bare_cleanup_uses_original_finish_deadline_without_stop_timestamp(
    stop_request,
) -> None:
    terminal = object.__new__(TrialRecordingTerminal)
    terminal.recording = None
    terminal.trial = SimpleNamespace(
        pulses=SimpleNamespace(off_boundary_ns=None), stop_request=stop_request
    )
    terminal.bootstrap = SimpleNamespace(
        control_policies=control.ControlPolicies(
            trial_finished=control.WaitPolicy(initial_ns=100)
        )
    )
    assert terminal.finish_deadline(200, None, None) == (
        200 if isinstance(stop_request, acq.WorkerCommand) else 120
    )


def test_setup_cleanup_does_not_submit_to_an_uninstalled_recording_thread() -> None:
    def fail_cleanup(**kwargs):
        raise AssertionError("Setup has not installed a writer session")

    cleanup = cast(
        WorkerCleanupLifecycle,
        SimpleNamespace(
            recording=SimpleNamespace(
                enabled=True, recording_queue=None, fail_cleanup=fail_cleanup
            ),
            _future=None,
        ),
    )
    WorkerCleanupLifecycle.begin(cleanup, 100)
    assert WorkerCleanupLifecycle._reconcile(cleanup, 100)
    assert cleanup._future is None


class _Encoder:
    created_output = True
    output_creation_identity = None
    progress_frame: int | None = None
    reader_error: BaseException | None = None
    exit_code = 0
    cleanup_complete = True
    diagnostic_tail: tuple[str, ...] = ()
    stdout_text = ""
    negotiated = True

    def __init__(self, identity: object | None = None) -> None:
        self.identity = identity
        self.terminated = False
        self.stdin_closed = False
        self.writes = 0

    def output_identity(self) -> object | None:
        return self.identity

    def terminate(self, *, deadline_ns: int) -> None:
        self.terminated = True

    def close_stdin(self, *, deadline_ns: int) -> None:
        self.stdin_closed = True

    def wait(self, *, deadline_ns: int) -> int:
        return 0

    def write(self, frame: memoryview | bytes, *, deadline_ns: int) -> None:
        self.writes += 1

    def check_negotiation(self) -> None:
        return None


class _Video:
    file_identity = "original"

    def __init__(self) -> None:
        self.closed = False
        self.sync_count = 0

    def sync(self) -> None:
        self.sync_count += 1

    def close(self) -> None:
        self.closed = True


class _FrameLog:
    def __init__(self, *, fail_append: bool = False) -> None:
        self.fail_append = fail_append
        self.append_calls = 0
        self.failed_closes = 0
        self.closes = 0

    def append_completion(self, completion: object) -> None:
        self.append_calls += 1
        if self.fail_append:
            raise OSError("partial completion write")

    def close_failed(self) -> None:
        self.failed_closes += 1

    def close(self) -> None:
        self.closes += 1


def _schedule(video: Path, frame_log: Path) -> acq.WorkerSchedule:
    session = control.SessionContext(session_id="session")
    trial = control.TrialContext(session=session, trial_id="trial", trial_number=1)
    outputs = (
        control.OutputPlan(
            backend=control.BackendContext(backend_name="acquisition"),
            output_key="trial:acquisition:behavioral_cam",
            path=str(video),
            trial=trial,
            output_tag="behavioral_cam",
            extension="mp4",
        ),
        control.OutputPlan(
            backend=control.BackendContext(backend_name="acquisition"),
            output_key="trial:acquisition:behavioral_cam_frames",
            path=str(frame_log),
            trial=trial,
            output_tag="behavioral_cam_frames",
            extension="jsonl",
        ),
    )
    return acq.WorkerSchedule(outputs=outputs)


def test_pre_t_cancel_preserves_unowned_replacement_and_closes_video_handle(
    tmp_path: Path,
) -> None:
    video_path, log_path = tmp_path / "trial.mp4", tmp_path / "trial.jsonl"
    video_path.write_bytes(b"replacement")
    video = _Video()
    encoder = _Encoder(identity=None)
    results, retained = cancel_before_start(
        _schedule(video_path, log_path),
        video_path,
        log_path,
        encoder=encoder,
        video_sync=video,
        observe_video=lambda: video,
        stat_identity=lambda path: "replacement" if path == video_path else None,
        delete_created_video=lambda path, identity, deadline_ns: False,
        deadline_ns=50,
    )
    assert encoder.terminated
    assert video.closed
    assert retained is None
    assert video_path.read_bytes() == b"replacement"
    assert results[0].closure == control.OUTPUT_CLOSURE_UNCONFIRMED
    assert results[0].artifact_present
    assert results[1].closure == control.OUTPUT_CLOSURE_NOT_STARTED


def test_terminal_write_is_fenced_and_late_video_handle_is_closed() -> None:
    progress = FinalizationProgress()
    log = _FrameLog(fail_append=True)
    video = _Video()
    clock = iter((10, 11, 12, 13, 14, 15))
    completion = object()
    for _ in range(2):
        append_terminal_and_close(
            progress,
            log,  # type: ignore[arg-type]
            video,
            completion,  # type: ignore[arg-type]
            deadline_ns=20,
            clock_ns=lambda: next(clock),
        )
    assert progress.completion_failed
    assert log.append_calls == 1
    assert log.failed_closes == 1
    assert video.closed
    assert progress.video_closed


def test_progress_watchdog_bounds_blocked_input_while_records_are_pending() -> None:
    queue = RecordingQueue(capacity_frames=1, pending_records_capacity=2)
    queue.enqueue(FrameRecord(0, 10, None, None, False, "INVALID_IMAGE"), None)
    now = [100]

    class Reader:
        reader_error = None
        progress_frame = None

    watchdog = EncoderProgressWatchdog(Reader(), queue, 25, lambda: now[0])  # type: ignore[arg-type]
    watchdog.check()
    now[0] = 126
    with pytest.raises(RecordingFailure, match="watchdog"):
        watchdog.check()


def test_overload_dropped_frame_is_still_logged_without_encoder_write() -> None:
    queue = RecordingQueue(capacity_frames=1, pending_records_capacity=2)
    pool = PixelBufferPool(payload_bytes=4, capacity=2)
    first, second = pool.acquire_nowait(), pool.acquire_nowait()
    queue.enqueue(FrameRecord(0, 10, None, None, True, None), first)
    admission = queue.enqueue(FrameRecord(1, 11, None, None, True, None), second)
    assert admission.dropped_record is not None
    pool.release(admission.dropped_pixels)  # type: ignore[arg-type]
    entry = queue.dequeue()
    assert entry is not None and entry.dropped and entry.pixels is None

    class Log:
        def __init__(self) -> None:
            self.rows: list[tuple[FrameRecord, bool]] = []

        def append_frame(self, record: FrameRecord, *, dropped: bool) -> None:
            self.rows.append((record, dropped))

    from cephvr.acquisition.recording.session_pump import write_ordered_entry

    log, encoder = Log(), _Encoder()
    write_ordered_entry(
        entry,
        expected_frame_id=0,
        schedule=acq.WorkerSchedule(start_monotonic_ns=1, end_monotonic_ns=100),
        frame_log=log,  # type: ignore[arg-type]
        encoder=encoder,
        pixel_preparer=object(),  # type: ignore[arg-type]
        prepared_buffer=bytearray(4),
        target_bits=8,
        on_started=lambda: None,
        write_deadline=lambda: 50,
        record_diagnostic=lambda record: None,
    )
    assert encoder.writes == 0
    assert log.rows == [(entry.record, True)]
    recycled = queue.complete(entry.record)
    assert recycled is None


def test_all_dropped_run_uses_only_explicit_never_created_predicate(
    tmp_path: Path,
) -> None:
    video_path, log_path = tmp_path / "empty.mp4", tmp_path / "empty.jsonl"
    schedule = _schedule(video_path, log_path)

    class EmptyEncoder:
        created_output = False
        exit_code = 0

        def output_identity(self) -> None:
            return None

    outputs = successful_outputs(
        schedule,
        video_path,
        log_path,
        recorded_frames=0,
        encoder=EmptyEncoder(),  # type: ignore[arg-type]
        video_identity=None,
        stat_identity=lambda path: None,
    )
    assert outputs[0].closure == control.OUTPUT_CLOSURE_NOT_STARTED
    assert not outputs[0].artifact_present


def test_exact_path_replacement_never_proves_encoder_output_closure(
    tmp_path: Path,
) -> None:
    video_path, log_path = tmp_path / "trial.mp4", tmp_path / "trial.jsonl"
    schedule = _schedule(video_path, log_path)
    with pytest.raises(RecordingFailure, match="never-created"):
        successful_outputs(
            schedule,
            video_path,
            log_path,
            recorded_frames=1,
            encoder=_Encoder(identity="original"),
            video_identity="original",
            stat_identity=lambda path: "replacement",
        )


class _Runtime:
    def __init__(self) -> None:
        self.failed_run: Future[list[control.OutputResult]] = Future()
        self.failed_run.set_exception(RuntimeError("stdin write failed"))
        self.cleanup: Future[list[control.OutputResult]] = Future()
        self.deadline_ns: int | None = None
        self.recycled_deadline_ns: int | None = None

    @property
    def run_future(self) -> Future[list[control.OutputResult]]:
        return self.failed_run

    def fail_cleanup(self, *, deadline_ns: int) -> Future[list[control.OutputResult]]:
        self.deadline_ns = deadline_ns
        return self.cleanup

    def recycle_finished(self, deadline_ns: int) -> None:
        self.recycled_deadline_ns = deadline_ns


def test_recording_fault_retains_real_outputs_and_original_cleanup_deadline() -> None:
    work = control.WorkContext(
        trial=control.TrialContext(
            session=control.SessionContext(session_id="session"),
            trial_id="trial",
            trial_number=1,
        )
    )
    schedule = acq.WorkerSchedule(
        command=acq.WorkerCommand(command_id="schedule-command"),
        start_monotonic_ns=100,
        end_monotonic_ns=200,
        outputs=(
            control.OutputPlan(output_key="behavioral_video", path="C:/data/trial.mp4"),
        ),
    )
    schedule.command.target.work.CopyFrom(work)
    run = _Runtime()
    run.cleanup.set_result(
        [
            control.OutputResult(
                output_key="behavioral_video",
                path="C:/data/trial.mp4",
                closure=control.OUTPUT_CLOSURE_FAILED,
                artifact_present=True,
            )
        ]
    )
    reports: list[tuple[tuple[str, ...], int, bool]] = []
    wake_count: list[int] = []

    def report_isolation(
        _work: control.WorkContext,
        _operation: str,
        observed_ns: int,
        resource_ids: tuple[str, ...],
        _detail: str,
        confirmed: bool,
        _capture: control.ContinuingFunctionEvidence,
    ) -> None:
        reports.append((resource_ids, observed_ns, confirmed))

    tracker = RecordingFaultLifecycle(
        warning_occurrence=lambda *_args: None,
        report_isolation=report_isolation,
        external_wake=lambda: wake_count.append(1),
    )
    capture = control.ContinuingFunctionEvidence(
        resource_id="behavioral.capture", functioning=True
    )
    cleanup_deadline = 500
    future = tracker.observe_failure(
        schedule,
        cast(WorkerRecordingRuntime, run),
        observed_ns=250,
        recovery_deadline_ns=cleanup_deadline,
        capture_function=capture,
        capture_resource_id="behavioral.capture",
        resource_ids=(
            "behavioral.recording",
            "behavioral_video",
            "behavioral_depth",
        ),
        detach_recording=lambda: None,
    )
    assert future is run.cleanup
    assert tracker.cleanup_pending
    assert run.deadline_ns == cleanup_deadline
    expected_closure = (
        "behavioral.recording",
        "behavioral_video",
        "behavioral_depth",
    )
    assert reports == [(expected_closure, 250, False)]
    assert wake_count == [1]

    assert tracker.reconcile(
        future,
        observed_ns=300,
        capture_function=capture,
    )
    assert tracker.outputs == run.cleanup.result()
    assert run.recycled_deadline_ns == cleanup_deadline
    assert reports[-1] == (
        expected_closure,
        300,
        True,
    )
    assert not tracker.cleanup_pending
