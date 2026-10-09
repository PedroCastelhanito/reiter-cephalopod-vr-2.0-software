"""Recording fault isolation, bounded closure and exact output ownership."""

from __future__ import annotations

import json
from concurrent.futures import Future
from fractions import Fraction
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
from cephvr.acquisition.worker.recording_runtime import WorkerRecordingRuntime
from cephvr.acquisition.worker.trial_recording_terminal import TrialRecordingTerminal
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.nominal_video_grid import NominalVideoGrid


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


def test_camera_video_uses_first_source_per_slot_and_streams_prior_pixels_for_gaps() -> (
    None
):
    from cephvr.acquisition.recording.session_pump import write_ordered_entry

    class Log:
        def __init__(self) -> None:
            self.video_grid = NominalVideoGrid(1_000_000_000, 1)
            self.next_video_slot = 0
            self.last_video_source = None
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
            self, *, slot, source_frame_id, source_host_receipt_ns, disposition
        ):
            assert slot == self.next_video_slot
            self.encoded.append(
                (slot, source_frame_id, source_host_receipt_ns, disposition)
            )
            self.next_video_slot += 1
            self.last_video_source = (source_frame_id, source_host_receipt_ns)

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

    assert submitted == [1, 0, 3]
    assert encoder.payloads == [b"aaaa", b"aaaa", b"aaaa", b"cccc"]
    assert log.rows == [
        (0, 1_000_000_000, False, 0, "real"),
        (1, 1_500_000_000, True, None, "same_slot_omission"),
        (2, 4_000_000_000, False, 3, "real"),
    ]
    assert log.encoded == [
        (0, 0, 1_000_000_000, "real"),
        (1, 0, 1_000_000_000, "interior_duplicate"),
        (2, 0, 1_000_000_000, "interior_duplicate"),
        (3, 2, 4_000_000_000, "real"),
    ]


def test_recording_session_pads_and_closes_with_original_tail_deadline(
    tmp_path: Path,
) -> None:
    from cephvr.acquisition.buffers.end_marker import CaptureEndMarker

    now = [1_000_000_000]

    class Encoder(_Encoder):
        def __init__(self) -> None:
            super().__init__(identity="owned-video")
            self.progress_frame = 0
            self.fail_writes = 0
            self.deadlines: list[int] = []
            self.payloads: list[bytes] = []

        def write(self, frame, *, deadline_ns: int) -> None:
            self.deadlines.append(deadline_ns)
            if self.fail_writes:
                self.fail_writes -= 1
                raise OSError("temporary tail input failure")
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
        "behavioral",
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
        nominal_rate_source="free_running_frame_rate",
        sync_interval_ns=1,
        syncer=file_sync,
    )
    frame_log.create()
    assert frame_log.video_grid.rate == Fraction("29.97002997")
    queue = RecordingQueue(capacity_frames=2, pending_records_capacity=2)
    pool = PixelBufferPool(payload_bytes=4, capacity=2)
    for frame_id, receipt_ns, pixels in (
        (0, start_ns + 70_000_000, b"aaaa"),
        (1, start_ns + 140_000_000, b"cccc"),
    ):
        owned = pool.acquire_nowait()
        owned[:] = pixels
        queue.enqueue(FrameRecord(frame_id, receipt_ns, None, None, True, None), owned)

    encoder = Encoder()
    video_sync = VideoSync()
    session = object.__new__(RecordingSession)
    session.settings = SimpleNamespace(
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
    session._started_observation_ns = None
    session.started_observed = lambda _observed_ns: None
    session._watchdog = EncoderProgressWatchdog(
        encoder,
        queue,
        1_000_000_000,
        session.clock_ns,  # type: ignore[arg-type]
    )
    session._video_sync = video_sync
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
    session._observe_video_identity = lambda: video_sync
    session._stat_identity = lambda _path: "owned-video"

    assert session.process_available(max_entries=2) == 2
    assert encoder.payloads == [b"aaaa"] * 3 + [b"aaaa", b"cccc"]
    # Integer-ns cutoff one tick before rational slot 20 starts.
    cutoff_ns = start_ns + 667_333_333
    end = CaptureEndMarker(2, cutoff_ns, cutoff_ns, 0, None, True)
    pulses = PulseEvidence()
    completion = RecordingCompletionContext("completed", cutoff_ns, cutoff_ns, None)

    # The first tail write fails before submission. Retrying may use a later
    # cleanup caller deadline, but cannot move the original input bound.
    original_deadline = start_ns + 100
    encoder.fail_writes = 1
    with pytest.raises(OSError, match="tail input failure"):
        session.finish(end, pulses, completion, deadline_ns=original_deadline)
    assert encoder.deadlines[-1] == original_deadline
    now[0] += 5
    original_check_progress = session._check_progress
    fail_progress = [True]

    def fail_progress_after_input() -> None:
        if fail_progress and fail_progress.pop():
            raise OSError("tail maintenance failure after encoder input")
        original_check_progress()

    session._check_progress = fail_progress_after_input
    with pytest.raises(OSError, match="maintenance failure after encoder input"):
        session.finish(end, pulses, completion, deadline_ns=start_ns + 500)
    assert frame_log.next_video_slot == 6
    assert encoder.writes == 6
    session.finish(end, pulses, completion, deadline_ns=start_ns + 500)

    lines = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert Fraction(str(lines[0]["video"]["nominal_frame_rate_hz"])) == (
        frame_log.video_grid.rate
    )
    video_rows = [line for line in lines if line["type"] == "video_frame"]
    completion_row = next(line for line in lines if line["type"] == "completion")
    assert len(video_rows) == 20
    assert [line["disposition"] for line in video_rows[:5]] == [
        "leading_duplicate",
        "leading_duplicate",
        "real",
        "interior_duplicate",
        "real",
    ]
    assert all(line["disposition"] == "trailing_duplicate" for line in video_rows[5:])
    assert completion_row["outcome"] == "completed"
    assert completion_row["video"] == {
        "recorded_frame_count": 20,
        "selected_source_frame_count": 2,
        "duplicate_frame_count": 18,
    }
    assert encoder.writes == 20
    assert encoder.deadlines[-1] == original_deadline
    assert file_sync.calls >= 20 and video_sync.sync_count >= 20
    assert session._finish_results[0].closure == control.OUTPUT_CLOSURE_CLOSED
    assert video_sync.closed and session._finished


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
    frame_log = SimpleNamespace(last_video_source=(0, start_ns), next_video_slot=1)
    session = object.__new__(RecordingSession)
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


def test_unlogged_submitted_tail_input_cannot_be_retried_as_normal_closure(
    tmp_path: Path,
) -> None:
    from contextlib import nullcontext

    from cephvr.acquisition.buffers.end_marker import CaptureEndMarker

    start_ns = 1_000_000_000
    cutoff_ns = start_ns + 100_000_000
    schedule = _schedule(tmp_path / "unlogged.mp4", tmp_path / "unlogged.jsonl")
    schedule.start_monotonic_ns = start_ns
    schedule.end_monotonic_ns = start_ns + 2_000_000_000

    class FrameLog:
        last_video_source = (0, start_ns)
        next_video_slot = 0
        video_grid = SimpleNamespace(slots_before=lambda _cutoff: 1)

        def append_video_frame(self, **_fields) -> None:
            raise OSError("frame mapping append failed")

    class Watchdog:
        def active_input_work(self):
            return nullcontext()

    encoder = _Encoder()
    session = object.__new__(RecordingSession)
    session._finished = False
    session._finish_results = None
    session._error = None
    session._encoder = encoder
    session._frame_log = FrameLog()
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
    session._prepared_buffer = bytearray(b"frame")
    session._watchdog = Watchdog()
    session._video_sync = None
    session._video_identity = None
    session._diagnostics = RecordingDiagnostics(lambda *_args: None)
    session._finalization = FinalizationProgress()
    session.clock_ns = lambda: start_ns
    session._write_deadline = lambda: start_ns + 1_000_000_000

    end = CaptureEndMarker(0, cutoff_ns, cutoff_ns, 0, None, True)
    completion = RecordingCompletionContext("completed", cutoff_ns, cutoff_ns, None)
    with pytest.raises(RecordingFailure, match="required slot mapping was not logged"):
        session.finish(
            end,
            PulseEvidence(),
            completion,
            deadline_ns=start_ns + 1_000_000_000,
        )
    assert encoder.writes == 1
    with pytest.raises(RecordingFailure, match="cannot retry terminal input"):
        session.finish(
            end,
            PulseEvidence(),
            completion,
            deadline_ns=start_ns + 2_000_000_000,
        )
    assert encoder.writes == 1


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
