"""Recording fault isolation, bounded closure and exact output ownership."""

from __future__ import annotations

import json
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from cephvr.acquisition.buffers.pixel_pool import PixelBufferPool
from cephvr.acquisition.buffers.queue import RecordingQueue
from cephvr.acquisition.buffers.records import FrameRecord
from cephvr.acquisition.recording.frame_log import FrameLogWriter
from cephvr.acquisition.recording.identity import RecordingIdentity
from cephvr.acquisition.recording.progress_watchdog import EncoderProgressWatchdog
from cephvr.acquisition.recording.session import RecordingSession
from cephvr.acquisition.recording.session_cleanup import cancel_before_start
from cephvr.acquisition.recording.session_completion import terminal_capture_proof
from cephvr.acquisition.recording.session_contracts import (
    PulseEvidence,
    RecordingCompletionContext,
    RecordingFailure,
)
from cephvr.acquisition.recording.session_diagnostics import RecordingDiagnostics
from cephvr.acquisition.recording.session_finalizer import (
    FinalizationProgress,
    append_terminal_and_close,
)
from cephvr.acquisition.recording.session_outputs import successful_outputs
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.worker.cleanup_lifecycle import WorkerCleanupLifecycle
from cephvr.acquisition.worker.recording_fault import RecordingFaultLifecycle
from cephvr.acquisition.worker.recording_preparation import TrialRecordingPreparation
from cephvr.acquisition.worker.recording_runtime import WorkerRecordingRuntime
from cephvr.acquisition.worker.trial_recording_terminal import TrialRecordingTerminal
from cephvr.acquisition.worker.trial_state import WorkerTrialState
from cephvr.control.v1 import types_pb2 as control


@pytest.mark.parametrize(
    "end,observed,matched",
    [(200, 210, 210), (200, 210, None), (200, 210, 211), (150, 160, 160)],
)
def test_continuous_terminal_requires_matched_normal_admission_proof(
    end, observed, matched
):
    from cephvr.acquisition.buffers.end_marker import CaptureEndMarker

    proof = terminal_capture_proof(
        CaptureEndMarker(
            1, end, None, 0, None, True, admission_stop_monotonic_ns=observed
        ),
        RecordingCompletionContext(
            "completed", end, None, None, stopped_admission_stop_monotonic_ns=matched
        ),
        schedule=acq.WorkerSchedule(start_monotonic_ns=100, end_monotonic_ns=200),
        received=1,
        logged=1,
        last_frame_id=0,
    )
    assert proof == (
        end == 200 and observed == matched,
        end == 200 and observed == matched,
        True,
    )


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
            captures=SimpleNamespace(active=False),
            recording_finish_pending=lambda: False,
            recording=SimpleNamespace(
                enabled=True, recording_queue=None, fail_cleanup=fail_cleanup
            ),
            _future=None,
        ),
    )
    WorkerCleanupLifecycle.begin(cleanup, 100)
    assert WorkerCleanupLifecycle._reconcile(cleanup, 100)
    assert cleanup._future is None


@pytest.mark.parametrize("expired", [False, True])
def test_cleanup_preserves_pending_terminal_writer_until_original_bound(
    monkeypatch: pytest.MonkeyPatch, expired: bool
) -> None:
    from cephvr.acquisition.worker import cleanup_lifecycle

    now = [100]
    monkeypatch.setattr(cleanup_lifecycle, "host_time_ns", lambda: now[0])
    events = []
    future = Future()
    request = acq.WorkerInterrupt(command=acq.WorkerCommand(command_id="interrupt"))
    request.command.target.work.session.session_id = "session"
    trial = WorkerTrialState(
        finished_future=future, stop_request=request, finish_deadline_ns=500
    )
    output = control.OutputResult(
        output_key="owned-video",
        path="owned.mp4",
        closure=control.OUTPUT_CLOSURE_CLOSED,
        artifact_present=True,
    )

    class Recording:
        enabled = True
        recording_queue = object()

        def completed_results(self):
            return future.result()

        def recycle_finished(self, deadline):
            events.append(("recycle", deadline))
            self.recording_queue = None

        def fail_cleanup(self, *, deadline_ns):
            assert now[0] >= deadline_ns
            events.append(("abort-after-bound", deadline_ns))
            result = Future()
            result.set_result([])
            return result

    recording = Recording()
    captures = SimpleNamespace(
        active=False,
        advance_due_stage=lambda: None,
        release=lambda: events.append("release-buffers") or (),
    )
    state = SimpleNamespace(
        context=acq.WorkerContext(worker=control.ProcessIdentity(generation="worker")),
        state_revision=0,
        complete_operation=lambda *args, **kwargs: events.append("complete-cleanup"),
        finalize_scope=lambda *args: None,
        finalize_terminal_command=lambda *args: None,
    )
    terminal = object.__new__(TrialRecordingTerminal)
    terminal.trial = trial
    terminal.recording = recording
    terminal.captures = captures
    terminal.state = state
    terminal.recording_fault = SimpleNamespace(
        cleanup_pending=False, faulted_session=False
    )
    terminal._source = lambda target: target
    terminal._report_lifecycle = lambda request, evidence, deadline: events.append(
        ("finished", evidence.operation.command_id, tuple(evidence.finished.outputs))
    )
    terminal._operation_deadline = lambda command: 500
    cleanup = WorkerCleanupLifecycle(
        state,
        SimpleNamespace(release_device=lambda: events.append("release-device")),
        captures,
        recording,  # type: ignore[arg-type]
        capacity=2,
        extra_resources=lambda: {},
        report_lifecycle=lambda *args: events.append("cleanup-evidence"),
        report_operation=lambda *args: events.append("cleanup-operation"),
        shutdown=lambda deadline: None,
        recording_reconciled=lambda: setattr(trial, "finished_future", None),
        external_wake=lambda: None,
        recording_finish_pending=lambda: trial.finished_future is not None,
    )
    command = acq.WorkerCommand(command_id="cleanup", target=request.command.target)
    assert not cleanup.begin_operation(
        "Cleanup", command, 400, acq.WorkerOperationReport()
    )
    cleanup.advance()
    assert events == [] and not future.done()
    if expired:
        now[0] = 400
        cleanup.advance()
        assert events[0] == ("abort-after-bound", 400)
        assert not future.done()
    else:
        future.set_result([output])
        terminal.advance_due_stages()
        cleanup.advance()
        assert events[0] == ("finished", "interrupt", (output,))
        assert events[1] == ("recycle", 500)
        assert "abort-after-bound" not in str(events)
        assert events.index("release-device") > events.index("release-buffers")


def test_cancel_setup_before_trial_recording_is_installed_is_confirmed() -> None:
    runtime = object.__new__(WorkerRecordingRuntime)
    runtime._settings = acq.RecordingSettings()
    runtime._capabilities = object()
    runtime._preparer = object()
    runtime._queue = None
    runtime._pool = None
    runtime._session_id = "session-1"
    runtime._device_id = "camera-1"
    runtime._camera_clock = camera.CameraClockDescriptor(device_id="camera-1")
    runtime._layout = camera.CameraImageLayout()
    runtime._installed = False
    runtime._handoff = None
    runtime._run_future = None
    runtime._pending_session = None

    completed = runtime.cancel_before_start(deadline_ns=500)
    preparation = object.__new__(TrialRecordingPreparation)
    preparation._recording = runtime
    preparation._session = object()
    preparation.cancel_setup()

    assert completed.done()
    assert completed.result() == []
    assert not runtime.enabled
    assert runtime._session_id == ""
    assert runtime._device_id == ""
    assert runtime._camera_clock is None
    assert runtime._layout is None
    assert preparation._session is None


def test_cancel_setup_preserves_an_installed_trial_cleanup_continuation() -> None:
    runtime = object.__new__(WorkerRecordingRuntime)
    runtime._settings = acq.RecordingSettings()
    runtime._installed = True
    runtime._handoff = object()
    runtime._run_future = None
    preparation = object.__new__(TrialRecordingPreparation)
    preparation._recording = runtime
    session = object()
    preparation._session = session

    preparation.cancel_setup()

    assert runtime.enabled
    assert runtime._installed
    assert preparation._session is session


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


def test_progress_watchdog_keeps_empty_queue_tail_work_under_one_stall_bound() -> None:
    queue = RecordingQueue(capacity_frames=1, pending_records_capacity=2)
    now = [100]

    class Reader:
        reader_error = None
        progress_frame = 0
        negotiated = True

    reader = Reader()
    watchdog = EncoderProgressWatchdog(reader, queue, 10, lambda: now[0])  # type: ignore[arg-type]
    with watchdog.active_input_work():
        watchdog.note_input_submitted()
        now[0] = 109
        watchdog.check()
        assert watchdog.write_deadline(1_000) == 110
        now[0] = 111
        with pytest.raises(RecordingFailure, match="watchdog"):
            watchdog.check()


def test_progress_watchdog_advances_tail_bound_only_on_real_encoder_progress() -> None:
    queue = RecordingQueue(capacity_frames=1, pending_records_capacity=2)
    now = [100]

    class Reader:
        reader_error = None
        progress_frame = 0
        negotiated = True

    reader = Reader()
    watchdog = EncoderProgressWatchdog(reader, queue, 10, lambda: now[0])  # type: ignore[arg-type]
    with watchdog.active_input_work():
        watchdog.note_input_submitted()
        now[0] = 109
        reader.progress_frame = 1
        watchdog.check()
        assert watchdog.write_deadline(1_000) == 119
        now[0] = 118
        watchdog.check()
        now[0] = 120
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

        def append_frame(
            self,
            record: FrameRecord,
            *,
            dropped: bool,
            video_disposition: str | None = None,
        ) -> None:
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


def test_camera_video_keeps_same_interval_sources_without_gap_padding() -> None:
    from cephvr.acquisition.recording.session_pump import write_ordered_entry

    class Log:
        def __init__(self) -> None:
            self.frame_count = 0
            self.selected_source_count = 0
            self.rows = []
            self.encoded = []

        def append_frame(
            self, record, *, dropped, video_frame=None, video_disposition=None
        ):
            self.rows.append(
                (
                    record.frame_id,
                    record.acquisition_time_ns,
                    dropped,
                    video_frame,
                    video_disposition,
                )
            )
            self.selected_source_count += int(not dropped)

        def append_video_frame(
            self, *, encoded_frame_index, source_frame_id, source_host_receipt_ns
        ):
            assert encoded_frame_index == self.frame_count
            self.encoded.append(
                (encoded_frame_index, source_frame_id, source_host_receipt_ns, "real")
            )
            self.frame_count += 1

    class Preparer:
        layout = SimpleNamespace(pixel_format=SimpleNamespace(effective_bits=8))

        def prepare_recording_into(self, pixels, buffer, *, target_bits):
            buffer[:] = pixels
            return SimpleNamespace(
                data=memoryview(buffer),
                effective_bits=target_bits,
                source_effective_bits=8,
            )

    class Encoder(_Encoder):
        def __init__(self):
            super().__init__()
            self.payloads = []

        def write(self, frame, *, deadline_ns):
            super().write(frame, deadline_ns=deadline_ns)
            self.payloads.append(bytes(frame))

    log, encoder = Log(), Encoder()
    schedule = acq.WorkerSchedule(
        start_monotonic_ns=1_000_000_000, end_monotonic_ns=5_000_000_000
    )
    source_rows = (
        (FrameRecord(0, 1_000_000_000, None, None, True, None), b"aaaa"),
        (FrameRecord(1, 1_500_000_000, None, None, True, None), b"bbbb"),
        (FrameRecord(2, 4_000_000_000, None, None, True, None), b"cccc"),
    )
    submitted = []
    prepared_buffer = bytearray(4)
    for index, (record, pixels) in enumerate(source_rows):
        submitted.append(
            write_ordered_entry(
                SimpleNamespace(record=record, pixels=pixels, dropped=False),
                expected_frame_id=index,
                schedule=schedule,
                frame_log=log,  # type: ignore[arg-type]
                encoder=encoder,
                pixel_preparer=Preparer(),  # type: ignore[arg-type]
                prepared_buffer=prepared_buffer,
                target_bits=8,
                on_started=lambda: None,
                write_deadline=lambda: 100,
                record_diagnostic=lambda _record: None,
            )
        )

    assert submitted == [1, 1, 1]
    assert encoder.payloads == [b"aaaa", b"bbbb", b"cccc"]
    assert log.rows == [
        (0, 1_000_000_000, False, 0, "real"),
        (1, 1_500_000_000, False, 1, "real"),
        (2, 4_000_000_000, False, 2, "real"),
    ]
    assert log.encoded == [
        (0, 0, 1_000_000_000, "real"),
        (1, 1, 1_500_000_000, "real"),
        (2, 2, 4_000_000_000, "real"),
    ]


@pytest.mark.parametrize("role", ["behavioral", "tracking", "eye_tracking"])
@pytest.mark.parametrize("rate_source", ["applied_mcu_rate", "free_running_frame_rate"])
@pytest.mark.parametrize("outcome", ["completed", "interrupted"])
@pytest.mark.parametrize("background_sync", [False, True])
def test_recording_session_preserves_all_images_and_timestamps_without_padding(
    tmp_path: Path,
    role: str,
    rate_source: str,
    outcome: str,
    background_sync: bool,
) -> None:
    from cephvr.acquisition.buffers.end_marker import CaptureEndMarker

    now = [1_000_000_000]

    class Encoder(_Encoder):
        def __init__(self) -> None:
            super().__init__(identity="owned-video")
            self.progress_frame = 0
            self.deadlines: list[int] = []
            self.payloads: list[bytes] = []

        def write(self, frame, *, deadline_ns: int) -> None:
            self.deadlines.append(deadline_ns)
            super().write(frame, deadline_ns=deadline_ns)
            self.payloads.append(bytes(frame))
            self.progress_frame += 1
            now[0] += 2

    class FileSync:
        def __init__(self) -> None:
            self.calls = 0

        def sync(self, _file) -> None:
            self.calls += 1

    class VideoSync(_Video):
        file_identity = "owned-video"
        fail_sync = False

        def sync(self):
            if self.fail_sync:
                self.fail_sync = False
                raise OSError("temporary video sync failure")
            super().sync()

    class Preparer:
        layout = SimpleNamespace(pixel_format=SimpleNamespace(effective_bits=8))

        def prepare_recording_into(self, pixels, buffer, *, target_bits):
            buffer[:] = pixels
            return SimpleNamespace(
                data=memoryview(buffer),
                effective_bits=target_bits,
                source_effective_bits=8,
            )

    start_ns = now[0]
    video_path, log_path = tmp_path / "trial.mp4", tmp_path / "trial.jsonl"
    schedule = _schedule(video_path, log_path)
    schedule.start_monotonic_ns = start_ns
    schedule.end_monotonic_ns = start_ns + 30_000_000_000
    camera_clock = camera.CameraClockDescriptor(
        device_id="device-17",
        timestamp_source="unavailable",
        timestamp_semantics="raw",
        reset_semantics="per-process",
        wrap_semantics="unknown",
        unavailable_reason="SDK unavailable",
        counter_source="unavailable",
        counter_semantics="raw",
        counter_width_bits=0,
        counter_wrap_semantics="unknown",
        counter_unavailable_reason="SDK unavailable",
        conversion_available=False,
    )
    identity = RecordingIdentity(
        str(uuid4()),
        str(uuid4()),
        1,
        role,
        "device-17",
        "config.json",
        camera_clock,
    )
    file_sync = FileSync()
    frame_log = FrameLogWriter(
        log_path,
        identity,
        start_ns=start_ns,
        nominal_frame_rate_hz=29.97002997002997,
        nominal_rate_source=rate_source,
        sync_interval_ns=1,
        syncer=file_sync,
    )
    frame_log.create()
    queue = RecordingQueue(capacity_frames=3, pending_records_capacity=3)
    pool = PixelBufferPool(payload_bytes=4, capacity=3)
    for frame_id, receipt_ns, pixels in (
        (0, start_ns + 70_000_000, b"aaaa"),
        (1, start_ns + 71_000_000, b"bbbb"),
        (2, start_ns + 140_000_000, b"cccc"),
    ):
        owned = pool.acquire_nowait()
        owned[:] = pixels
        queue.enqueue(
            FrameRecord(
                frame_id, receipt_ns, 100 + frame_id, 900 + frame_id, True, None
            ),
            owned,
        )

    encoder = Encoder()
    video_sync = VideoSync()
    import threading

    from cephvr.acquisition.recording.video_sync import PeriodicVideoSync

    release_sync = threading.Event()
    entered_sync = threading.Event()
    if background_sync:
        original_sync = video_sync.sync

        def blocked_sync():
            entered_sync.set()
            assert release_sync.wait(2)
            original_sync()

        video_sync.sync = blocked_sync
        owned_sync = PeriodicVideoSync(video_sync, lambda: now[0])
        assert owned_sync.request()
        assert entered_sync.wait(1)
    else:
        owned_sync = video_sync
    session = object.__new__(RecordingSession)
    session.settings = SimpleNamespace(
        metadata_only=False,
        recording_bit_depth=8,
        video_sync_interval_ns=1,
        frame_log_sync_interval_ns=1,
    )
    session.identity = identity
    session.queue = queue
    session.pixel_pool = pool
    session.pixel_preparer = Preparer()
    session.clock_ns = lambda: now[0]
    session._released = True
    session._scheduled = schedule
    session._encoder = encoder
    session._frame_log = frame_log
    session._prepared_buffer = bytearray(4)
    session._started = False
    session.started_observed = lambda _observed_ns: None
    session._watchdog = EncoderProgressWatchdog(
        encoder,
        queue,
        1_000_000_000,
        session.clock_ns,  # type: ignore[arg-type]
    )
    session._video_sync = owned_sync
    session._video_identity = "owned-video"
    session._video_path = video_path
    session._frame_log_path = log_path
    session._received = 0
    session._submitted = 0
    session._logged = 0
    session._last_frame_id = -1
    session._diagnostics = RecordingDiagnostics(lambda *_args: None)
    session._last_video_sync_ns = start_ns
    session._active_io_deadline_ns = None
    session._finish_arguments = None
    session._original_finish_deadline_ns = None
    session._finish_results = None
    session._error = None
    session._finished = False
    session._finalization = FinalizationProgress()
    identity_observations = []

    def observe_owned():
        identity_observations.append(True)
        return owned_sync

    session._observe_video_identity = observe_owned
    session._stat_identity = lambda _path: "owned-video"

    assert session.process_available(max_entries=3) == 3
    assert encoder.payloads == [b"aaaa", b"bbbb", b"cccc"]
    assert identity_observations == []
    cutoff_ns = start_ns + 667_333_333
    end = CaptureEndMarker(3, cutoff_ns, cutoff_ns, 0, None, True)
    completion = RecordingCompletionContext(outcome, cutoff_ns, cutoff_ns, None)
    original_deadline = start_ns + (1_000_000_000 if background_sync else 100)
    if background_sync:
        # All three real frames/mappings were consumed while flush stayed blocked.
        assert not release_sync.is_set() and video_sync.sync_count == 0
        release_sync.set()
        session.finish(end, PulseEvidence(), completion, deadline_ns=original_deadline)
    else:
        video_sync.fail_sync = True
        with pytest.raises(OSError, match="temporary video sync failure"):
            session.finish(
                end, PulseEvidence(), completion, deadline_ns=original_deadline
            )
    now[0] += 5
    session.finish(end, PulseEvidence(), completion, deadline_ns=start_ns + 500)
    assert session._original_finish_deadline_ns == original_deadline
    # Closure, including retries, must never submit invented tail images.
    session.finish(end, PulseEvidence(), completion, deadline_ns=start_ns + 600)
    lines = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert lines[0]["schema_version"] == 6
    assert lines[0]["identity"]["camera_role"] == role
    assert lines[0]["video"] == {
        "enabled": True,
        "nominal_frame_rate_hz": 29.97002997,
        "nominal_rate_source": rate_source,
    }
    source_rows = [line for line in lines if line["type"] == "frame"]
    video_rows = [line for line in lines if line["type"] == "video_frame"]
    assert [row["video_frame"] for row in source_rows] == [0, 1, 2]
    assert [row["camera_frame_counter"] for row in source_rows] == [100, 101, 102]
    assert [row["camera_timestamp_ns"] for row in source_rows] == [900, 901, 902]
    assert [row["host_receipt_ns"] for row in source_rows] == [
        start_ns + offset for offset in (70_000_000, 71_000_000, 140_000_000)
    ]
    assert video_rows == [
        {
            "type": "video_frame",
            "encoded_frame_index": i,
            "source_frame_id": i,
            "source_host_receipt_ns": row["host_receipt_ns"],
            "disposition": "real",
        }
        for i, row in enumerate(source_rows)
    ]
    assert lines[-1]["outcome"] == outcome
    assert lines[-1]["video"] == {
        "recorded_frame_count": 3,
        "selected_source_frame_count": 3,
        "duplicate_frame_count": 0,
    }
    assert lines[-1]["timing"]["recording_end_monotonic_ns"] == cutoff_ns
    assert encoder.writes == 3
    assert file_sync.calls >= 3
    assert video_sync.sync_count >= (2 if background_sync else 3)
    assert session._finish_results[0].closure == control.OUTPUT_CLOSURE_CLOSED
    assert video_sync.closed and session._finished
    assert identity_observations  # Explicit finalization still revalidates.


def test_unproved_terminal_stop_never_generates_trailing_video_slots(
    monkeypatch, tmp_path: Path
) -> None:
    import cephvr.acquisition.recording.session as session_module
    from cephvr.acquisition.buffers.end_marker import CaptureEndMarker

    start_ns = 1_000_000_000
    cutoff_ns = start_ns + 100_000_000
    schedule = _schedule(tmp_path / "unproved.mp4", tmp_path / "unproved.jsonl")
    schedule.start_monotonic_ns = start_ns
    schedule.end_monotonic_ns = start_ns + 2_000_000_000
    encoder = _Encoder()
    frame_log = SimpleNamespace(frame_count=1)
    session = object.__new__(RecordingSession)
    session.settings = SimpleNamespace(metadata_only=False)
    session._finished = False
    session._finish_results = None
    session._error = None
    session._encoder = encoder
    session._frame_log = frame_log
    session._finish_arguments = None
    session._original_finish_deadline_ns = None
    session._active_io_deadline_ns = None
    session._scheduled = schedule
    session.queue = SimpleNamespace(pending_records=0, waiting_pixels=0)
    session._received = 0
    session._logged = 0
    session._last_frame_id = -1
    session._video_path = Path(schedule.outputs[0].path)
    session._frame_log_path = Path(schedule.outputs[1].path)
    session._submitted = 0
    session._video_sync = None
    session._video_identity = None
    session._diagnostics = RecordingDiagnostics(lambda *_args: None)
    session._finalization = FinalizationProgress()
    session.clock_ns = lambda: start_ns
    session._observe_video_identity = lambda: None
    session._stat_identity = lambda _path: None

    called = []

    def close_without_padding(*_args, submitted: int, **_kwargs):
        called.append(submitted)
        return [], None

    monkeypatch.setattr(session_module, "finish_recording", close_without_padding)
    end = CaptureEndMarker(0, cutoff_ns, cutoff_ns, 0, None, True)
    completion = RecordingCompletionContext("completed", cutoff_ns + 1, cutoff_ns, None)
    session.finish(
        end,
        PulseEvidence(),
        completion,
        deadline_ns=start_ns + 1_000_000_000,
    )

    assert encoder.writes == 0
    assert called == [0]
    assert session._finished


@pytest.mark.parametrize("failure", ["input", "mapping", "maintenance"])
def test_failed_source_submission_cannot_be_retried_as_normal_closure(
    tmp_path: Path,
    failure: str,
) -> None:
    from cephvr.acquisition.buffers.end_marker import CaptureEndMarker

    start_ns = 1_000_000_000
    schedule = _schedule(tmp_path / "failed.mp4", tmp_path / "failed.jsonl")
    schedule.start_monotonic_ns = start_ns
    schedule.end_monotonic_ns = start_ns + 2_000_000_000
    queue = RecordingQueue(1, 1)
    pool = PixelBufferPool(payload_bytes=4, capacity=1)
    pixels = pool.acquire_nowait()
    pixels[:] = b"data"
    queue.enqueue(FrameRecord(0, start_ns + 1, None, None, True, None), pixels)

    class FrameLog:
        frame_count = 0

        def append_frame(self, *_args, **_kwargs):
            pass

        def append_video_frame(self, **_fields):
            if failure == "mapping":
                raise OSError("mapping failure")
            self.frame_count += 1

    class Encoder(_Encoder):
        def write(self, frame, *, deadline_ns):
            if failure == "input":
                raise OSError("input failure")
            super().write(frame, deadline_ns=deadline_ns)

    encoder = Encoder()
    session = object.__new__(RecordingSession)
    session.settings = SimpleNamespace(metadata_only=False, recording_bit_depth=8)
    session._released = True
    session._finished = False
    session._finish_results = None
    session._error = None
    session._encoder = encoder
    session._frame_log = FrameLog()
    session._scheduled = schedule
    session.queue, session.pixel_pool = queue, pool
    session._prepared_buffer = bytearray(4)
    session._started = True
    session._last_frame_id = -1
    session._submitted = 0
    session._watchdog = None
    session._diagnostics = RecordingDiagnostics(lambda *_args: None)
    session._write_deadline = lambda: start_ns + 100
    session._sync_due = lambda: None
    session._observe_video_identity = lambda: None

    def check_progress():
        if failure == "maintenance":
            raise OSError("maintenance failure")

    session._check_progress = check_progress
    session.pixel_preparer = SimpleNamespace(
        layout=SimpleNamespace(pixel_format=SimpleNamespace(effective_bits=8)),
        prepare_recording_into=lambda pixels, buffer, **kwargs: SimpleNamespace(
            data=bytes(pixels), effective_bits=8, source_effective_bits=8
        ),
    )
    with pytest.raises(RecordingFailure):
        session.process_available()
    assert encoder.writes == (0 if failure == "input" else 1)
    assert session._submitted == encoder.writes
    from cephvr.acquisition.recording.session_cleanup import close_failed_recording

    video = _Video()
    results, _ = close_failed_recording(
        schedule,
        Path(schedule.outputs[0].path),
        Path(schedule.outputs[1].path),
        queue=queue,
        pool=pool,
        encoder=encoder,
        frame_log=_FrameLog(),
        video_sync=video,
        finalization=FinalizationProgress(),
        submitted=session._submitted,
        observe_video=lambda: video,
        stat_identity=lambda path: video.file_identity,
        clock_ns=lambda: start_ns + 10,
        deadline_ns=start_ns + 200,
    )
    assert results[0].camera_video_content == (
        control.CAMERA_VIDEO_CONTENT_NO_FRAMES
        if failure == "input"
        else control.CAMERA_VIDEO_CONTENT_FRAMES_SUBMITTED
    )
    assert results[0].closure == control.OUTPUT_CLOSURE_UNCONFIRMED
    assert results[1].closure == control.OUTPUT_CLOSURE_FAILED
    assert queue.pending_records == 0
    # The only private buffer is returned even after a partially submitted image.
    assert pool.acquire_nowait().obj is pixels.obj
    end = CaptureEndMarker(1, start_ns + 10, start_ns + 10, 0, None, True)
    completion = RecordingCompletionContext(
        "completed", start_ns + 10, start_ns + 10, None
    )
    with pytest.raises(RecordingFailure, match="cannot finalize recording"):
        session.finish(end, PulseEvidence(), completion, deadline_ns=start_ns + 200)
    assert encoder.writes == (0 if failure == "input" else 1)


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
        source_frames=7,
        encoder=EmptyEncoder(),  # type: ignore[arg-type]
        video_identity=None,
        stat_identity=lambda path: None,
    )
    assert outputs[0].closure == control.OUTPUT_CLOSURE_NOT_STARTED
    assert not outputs[0].artifact_present
    assert dict(outputs[0].counts) == {"frames": 0}
    assert dict(outputs[1].counts) == {"video_frames": 0, "source_frames": 7}


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


def test_recording_fault_retains_real_outputs_and_original_cleanup_deadline(
    monkeypatch,
) -> None:
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
    ordering: list[str] = []
    details: list[str] = []
    original_cleanup = run.fail_cleanup

    def fail_cleanup(*, deadline_ns):
        ordering.append("cleanup")
        return original_cleanup(deadline_ns=deadline_ns)

    monkeypatch.setattr(run, "fail_cleanup", fail_cleanup)

    def report_isolation(
        actual_work: control.WorkContext,
        operation: str,
        observed_ns: int,
        resource_ids: tuple[str, ...],
        detail: str,
        confirmed: bool,
        actual_capture: control.ContinuingFunctionEvidence,
    ) -> None:
        assert actual_work == work
        assert operation == "schedule-command"
        assert actual_capture == capture
        ordering.append("report")
        details.append(detail)
        reports.append((resource_ids, observed_ns, confirmed))

    tracker = RecordingFaultLifecycle(
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
        detach_recording=lambda: ordering.append("detach"),
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
    assert details == ["stdin write failed"]
    assert ordering == ["detach", "report", "cleanup"]
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


@pytest.mark.parametrize(
    "present,owned",
    [(False, None), (False, "old"), (True, None), (True, "old"), (True, "current")],
)
def test_failed_video_presence_is_independent_of_ownership(tmp_path, present, owned):
    from cephvr.acquisition.recording.session_outputs import failed_outputs

    video, log = tmp_path / "video.mp4", tmp_path / "frames.jsonl"
    if present:
        video.write_bytes(b"partial video")
    encoder = _Encoder(identity=owned)
    encoder.exit_code = 1
    outputs = failed_outputs(
        _schedule(video, log),
        video,
        log,
        encoder=encoder,
        video_identity=owned,
        stat_identity=lambda path: "current" if path.is_file() else None,
        completion_failed=True,
    )
    assert outputs[0].artifact_present is present
    assert outputs[0].closure == (
        control.OUTPUT_CLOSURE_FAILED
        if present and owned == "current"
        else control.OUTPUT_CLOSURE_UNCONFIRMED
    )
    assert outputs[1].closure == control.OUTPUT_CLOSURE_FAILED
    assert video.exists() is present


def test_periodic_video_sync_is_single_flight_and_final_flush_is_distinct():
    import threading
    import time

    from cephvr.acquisition.recording.video_sync import PeriodicVideoSync

    started = threading.Event()
    release = threading.Event()

    class Video(_Video):
        def sync(self):
            super().sync()
            if self.sync_count == 1:
                started.set()
                assert release.wait(2)

    video = Video()
    owner = PeriodicVideoSync(video, time.perf_counter_ns)
    assert owner.request()
    assert started.wait(1)
    for _ in range(100):
        assert not owner.request()
    assert video.sync_count == 1
    with pytest.raises(RuntimeError, match="retains its handle"):
        owner.close()
    # Closing fences further periodic work without releasing pending ownership.
    release.set()
    owner.sync_until(time.perf_counter_ns() + 1_000_000_000)
    assert video.sync_count == 2
    owner.sync_until(time.perf_counter_ns() + 1_000_000_000)
    assert video.sync_count == 2
    owner.close()
    assert video.closed
    with pytest.raises(RuntimeError, match="fenced"):
        owner.request()


def test_periodic_video_sync_timeout_retains_exact_operation_and_late_retry():
    import threading
    import time

    from cephvr.acquisition.recording.video_sync import PeriodicVideoSync

    started = threading.Event()
    release = threading.Event()

    class Video(_Video):
        def sync(self):
            super().sync()
            started.set()
            assert release.wait(2)

    video = Video()
    owner = PeriodicVideoSync(video, time.perf_counter_ns)
    with pytest.raises(TimeoutError, match="pending"):
        owner.sync_until(time.perf_counter_ns() + 10_000_000)
    assert started.is_set() and not video.closed
    with pytest.raises(RuntimeError, match="retains its handle"):
        owner.close()
    release.set()
    owner.sync_until(time.perf_counter_ns() + 1_000_000_000)
    assert video.sync_count == 1 and owner.late
    owner.close()
    assert video.closed


def test_periodic_video_sync_failure_latches_and_does_not_restart():
    import time

    from cephvr.acquisition.recording.video_sync import PeriodicVideoSync

    class Video(_Video):
        def sync(self):
            super().sync()
            raise OSError("storage failure")

    video = Video()
    owner = PeriodicVideoSync(video, time.perf_counter_ns)
    with pytest.raises(RuntimeError, match="synchronization failed"):
        owner.sync_until(time.perf_counter_ns() + 1_000_000_000)
    with pytest.raises(RuntimeError, match="synchronization failed"):
        owner.poll()
    assert video.sync_count == 1
    owner.close()
    assert video.closed


def test_periodic_video_sync_cadence_does_not_reset_while_pending():
    import threading
    import time

    from cephvr.acquisition.recording.session_storage import sync_due
    from cephvr.acquisition.recording.video_sync import PeriodicVideoSync

    release = threading.Event()

    class Video(_Video):
        def sync(self):
            super().sync()
            assert release.wait(2)

    owner = PeriodicVideoSync(Video(), time.perf_counter_ns)
    last = sync_due(None, owner, 0, 10, 10)
    assert last == 10
    assert sync_due(None, owner, last, 10, 30) == 10
    release.set()
    owner.sync_until(time.perf_counter_ns() + 1_000_000_000)
    owner.close()


def test_periodic_video_sync_thread_start_failure_retains_close_owner(monkeypatch):
    import threading
    import time

    from cephvr.acquisition.recording.video_sync import (
        PeriodicVideoSync,
        VideoSyncFailure,
    )

    video = _Video()
    owner = PeriodicVideoSync(video, time.perf_counter_ns)

    def fail_start(_thread):
        raise RuntimeError("thread start failed")

    monkeypatch.setattr(threading.Thread, "start", fail_start)
    with pytest.raises(VideoSyncFailure, match="could not start"):
        owner.sync_until(time.perf_counter_ns() + 1_000_000_000)
    with pytest.raises(VideoSyncFailure, match="synchronization failed"):
        owner.sync_until(time.perf_counter_ns() + 1_000_000_000)
    owner.close()
    assert video.closed and video.sync_count == 0


def test_failed_periodic_flush_cleanup_closes_exact_handles_without_durability(
    tmp_path,
):
    import time

    from cephvr.acquisition.recording.session_cleanup import close_failed_recording
    from cephvr.acquisition.recording.video_sync import (
        PeriodicVideoSync,
        VideoSyncFailure,
    )

    class Video(_Video):
        def sync(self):
            raise OSError("disk sync failed")

    native = Video()
    owner = PeriodicVideoSync(native, time.perf_counter_ns)
    with pytest.raises(VideoSyncFailure):
        owner.sync_until(time.perf_counter_ns() + 1_000_000_000)
    log = _FrameLog()
    progress = FinalizationProgress()
    video_path, log_path = tmp_path / "trial.mp4", tmp_path / "trial.jsonl"
    results, retained = close_failed_recording(
        _schedule(video_path, log_path),
        video_path,
        log_path,
        queue=RecordingQueue(capacity_frames=1, pending_records_capacity=1),
        pool=PixelBufferPool(payload_bytes=4, capacity=1),
        encoder=_Encoder(identity="original"),
        frame_log=log,
        video_sync=owner,
        finalization=progress,
        submitted=1,
        observe_video=lambda: owner,
        stat_identity=lambda _path: "original",
        clock_ns=time.perf_counter_ns,
        deadline_ns=time.perf_counter_ns() + 1_000_000_000,
    )
    assert retained is owner and native.closed
    assert progress.video_closed and not progress.video_synced
    assert log.failed_closes == 1
    assert [r.closure for r in results] == [
        control.OUTPUT_CLOSURE_UNCONFIRMED,
        control.OUTPUT_CLOSURE_FAILED,
    ]


def test_pending_periodic_sync_does_not_extend_recording_run_deadline():
    import threading

    from cephvr.acquisition.recording.video_sync import PeriodicVideoSync

    release = threading.Event()

    class Video(_Video):
        def sync(self):
            assert release.wait(2)

    now = [10]
    owner = PeriodicVideoSync(Video(), lambda: now[0])
    assert owner.request()
    session = object.__new__(RecordingSession)
    session._released = True
    session._frame_log = object()
    session._scheduled = None
    session._active_io_deadline_ns = None
    session.queue = SimpleNamespace(pending_records=0, waiting_pixels=0)
    session.clock_ns = lambda: now[0]
    deadlines = []

    def process(**_kwargs):
        now[0] = 20
        assert not owner.request()

    session.process_available = process
    session.fail_cleanup = lambda *, deadline_ns: deadlines.append(deadline_ns) or []
    marker = SimpleNamespace(
        abort_request=lambda: None, completion_deadline_ns=None, poll=lambda: None
    )
    try:
        assert session.run(marker, lambda: None, lambda: None, deadline_ns=20) == []
        assert deadlines == [20] and session._active_io_deadline_ns == 20
    finally:
        release.set()
        owner.sync_until(1_000_000_020)
        owner.close()


@pytest.mark.parametrize("current_identity", [None, "replacement"])
def test_adopted_video_handle_still_rejects_path_change_at_final_observation(
    tmp_path, current_identity
):
    from cephvr.acquisition.recording.session_storage import observe_video_identity

    native = _Video()
    observed = []
    factory = SimpleNamespace(
        identity=lambda path: observed.append(path) or current_identity
    )
    with pytest.raises(RecordingFailure, match="path is absent|path identity differs"):
        observe_video_identity(
            _Encoder(identity="original"),
            tmp_path / "video.mp4",
            "original",
            native,
            10,
            factory=factory,
            clock_ns=lambda: 20,
        )
    assert len(observed) == 1 and not native.closed


@pytest.mark.parametrize(
    "finished,released,has_encoder",
    [
        (True, True, True),
        (False, True, True),
        (True, False, True),
        (True, True, False),
    ],
)
def test_recycle_retains_exact_encoder_release_independent_of_output_success(
    finished,
    released,
    has_encoder,
):
    session = object.__new__(RecordingSession)
    session._finished = finished
    session._encoder = (
        SimpleNamespace(launch_id="recording-helper", cleanup_complete=released)
        if has_encoder
        else None
    )
    events = []
    removed = Future()
    removed.set_result(None)
    runtime = object.__new__(WorkerRecordingRuntime)
    runtime._run_future = Future()
    runtime._run_future.set_result(
        [
            control.OutputResult(
                output_key="video",
                closure=control.OUTPUT_CLOSURE_UNCONFIRMED,
            )
        ]
    )
    runtime._queue = runtime._pool = None
    runtime._pending_session = session
    runtime.writer = SimpleNamespace(remove_finished=lambda: removed)
    runtime._wait = lambda future, deadline: future.result()
    runtime._resource_released = lambda *args: events.append(args)
    runtime.recycle_finished(100)
    assert events == (
        [("ffmpeg:recording-helper", True)]
        if finished and released and has_encoder
        else []
    )
    assert runtime._pending_session is None
