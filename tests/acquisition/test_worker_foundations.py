"""Hardware-free worker accounting, lifecycle, ownership and warning behavior checks.

Native camera and synchronization acceptance remains under the owner's E15 rig plan.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from itertools import count
from threading import Event, get_ident
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from cephvr.acquisition.buffers.end_marker import CaptureEndMarker
from cephvr.acquisition.buffers.pixel_pool import PixelBufferPool
from cephvr.acquisition.buffers.queue import (
    PendingRecordCapacityError,
    RecordingQueue,
)
from cephvr.acquisition.buffers.records import FrameRecord
from cephvr.acquisition.camera.types import PurgeEvidence, TransportCounters
from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.worker.blocking_wait import verify_blocking_wait
from cephvr.acquisition.worker.capture import CameraCaptureLoop, CaptureWindow
from cephvr.acquisition.worker.capture_runtime import WorkerCaptureResources
from cephvr.acquisition.worker.cleanup_lifecycle import WorkerCleanupLifecycle
from cephvr.acquisition.worker.execution import WorkerOperationExecutor
from cephvr.acquisition.worker.health import WorkerHealthReporter
from cephvr.acquisition.worker.limits import AcquisitionControlLimits
from cephvr.acquisition.worker.owner import SerializedCameraOwner
from cephvr.acquisition.worker.preview_lifecycle import WorkerPreviewLifecycle
from cephvr.acquisition.worker.report_dispatch import WorkerReportDispatcher
from cephvr.acquisition.worker.session_preparation import WorkerSessionPreparation
from cephvr.acquisition.worker.state import WorkerBootstrap, WorkerState
from cephvr.acquisition.worker.trial_lifecycle import WorkerTrialLifecycle
from cephvr.acquisition.worker.warnings import WarningOccurrence, WorkerWarningLedger
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.commands import CommandLedger
from cephvr.shared.pixels.types import NativePixelFormat, PixelLayout


def _worker_context() -> acq.WorkerContext:
    return acq.WorkerContext(
        worker=control.ProcessIdentity(
            role="acquisition_behavioral_worker", generation=str(uuid4())
        ),
        owner=control.ProcessIdentity(role="acquisition", generation=str(uuid4())),
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
    )


def _worker_state(context: acq.WorkerContext | None = None) -> WorkerState:
    source = context or _worker_context()
    return WorkerState(
        source,
        control.ProcessIdentity(role="supervisor", generation=str(uuid4())),
        CommandLedger(
            source.worker.generation,
            10_000,
            max_records=8,
            max_bytes=1024 * 1024,
            result_reservation_bytes=1024,
        ),
    )


def test_worker_executor_retains_unknown_operation_failure_under_original_deadline() -> (
    None
):
    state = _worker_state()
    command_id = str(uuid4())
    deadline_ns = 10**18
    request = acq.WorkerCommand(command_id=command_id, target=state.context)
    state.commands.admit(
        command_id,
        b"unknown-operation",
        1,
        work_key=state.context.worker.generation,
        deadline_ns=deadline_ns,
    )
    state.operations[command_id] = control.OperationState(
        context=control.OperationContext(command_id=command_id),
        command="Unknown",
    )
    reports: list[tuple[acq.WorkerOperationReport, int]] = []
    executor = object.__new__(WorkerOperationExecutor)
    executor.bootstrap = SimpleNamespace(context=state.context)
    executor.state = state
    executor._latest_work = None
    executor._coordinator_loss_handled = False
    executor.report_dispatcher = SimpleNamespace(
        operation=lambda report, bound: reports.append((report, bound))
    )

    executor.execute("Unknown", request, deadline_ns)

    result = state.operations[command_id]
    assert result.complete and not result.succeeded
    assert result.progress == "failed"
    assert result.failure.code == "WORKER_OPERATION_FAILED"
    assert "unknown worker operation" in result.failure.message
    assert reports[0][0].operation == result
    assert reports[0][1] == deadline_ns


def test_blocking_wait_wakeup_verification_uses_loop_and_respects_deadline() -> None:
    async def run() -> list[int]:
        loop = asyncio.get_running_loop()
        wake = Event()
        timeouts: list[int] = []

        class Camera:
            def verify_blocking_wait_wakeup(self, schedule, timeout_ns: int) -> None:
                timeouts.append(timeout_ns)
                acknowledgement = schedule(wake.set)
                assert acknowledgement.wait(1)
                assert wake.wait(1)

        await asyncio.to_thread(
            verify_blocking_wait, loop, Camera(), 200, clock_ns=lambda: 100
        )
        return timeouts

    assert asyncio.run(run()) == [100]


def test_session_preparation_requires_exact_work_and_configuration_revision() -> None:
    context = _worker_context()
    state = _worker_state(context)
    state.confirmed_configuration_revision = 4
    bootstrap = cast(WorkerBootstrap, SimpleNamespace())
    preparation = WorkerSessionPreparation(
        bootstrap,
        state,
        cast(object, SimpleNamespace()),  # type: ignore[arg-type]
        cast(object, SimpleNamespace()),  # type: ignore[arg-type]
        begin_warning_scope=lambda *_args, **_kwargs: None,
        verify_wait=lambda _deadline: None,
        report_lifecycle=lambda *_args: None,
    )
    work = control.WorkContext(session=control.SessionContext(session_id=str(uuid4())))
    request = acq.WorkerPrepareTrial(
        command=acq.WorkerCommand(command_id=str(uuid4()), target=context),
        required_configuration_revision=4,
    )
    request.command.target.work.CopyFrom(work)

    with pytest.raises(RuntimeError, match="session is not prepared"):
        preparation.require_ready_session(request)
    preparation.session_ready = True
    preparation.require_ready_session(request)
    request.required_configuration_revision = 3
    with pytest.raises(RuntimeError, match="configuration revision is stale"):
        preparation.require_ready_session(request)


def test_session_and_trial_preparation_report_after_confirmed_resources() -> None:
    from cephvr.acquisition.v1 import runtime_pb2

    context = _worker_context()
    state = _worker_state(context)
    state.confirmed_configuration_revision = 5
    bootstrap = cast(
        WorkerBootstrap,
        SimpleNamespace(
            file_policy=runtime_pb2.CameraFilePolicy(post_cutoff_drain_margin_ns=1)
        ),
    )
    events: list[object] = []
    resource = acq.AttachedResource(resource_id="allocation")

    class CameraConfiguration:
        def require_adopted_setup(self, _request: object) -> None:
            events.append("adopted")

    class Captures:
        def prepare(
            self, _camera: object, *, session_preview: bool
        ) -> tuple[object, ...]:
            events.append(("capture-prepare", session_preview))
            return (resource,)

    class RecordingPreparation:
        def prepare_session(self, _request: object) -> None:
            events.append("recording-session-prepare")

        def prepare_trial(self, _request: object, deadline_ns: int) -> None:
            events.append(("recording-trial-prepare", deadline_ns))

    trial = SimpleNamespace(
        pulse_required=False,
        trial_prepared=False,
        recording_preparation=RecordingPreparation(),
        prepare_trial_state=lambda _request, deadline_ns: events.append(
            ("trial-state-prepare", deadline_ns)
        ),
    )
    preparation = WorkerSessionPreparation(
        bootstrap,
        state,
        CameraConfiguration(),  # type: ignore[arg-type]
        Captures(),  # type: ignore[arg-type]
        begin_warning_scope=lambda *_args, **_kwargs: events.append("warning-scope"),
        verify_wait=lambda deadline: events.append(("wait-verified", deadline)),
        report_lifecycle=lambda request, evidence, deadline: events.append(
            ("report", request.command.command_id, evidence, deadline)
        ),
    )
    session_work = control.WorkContext(
        session=control.SessionContext(session_id=str(uuid4()))
    )
    setup = acq.WorkerSetupSession(
        command=acq.WorkerCommand(
            command_id=str(uuid4()),
            target=acq.WorkerContext(),
        ),
        configuration_revision=5,
    )
    setup.command.target.work.CopyFrom(session_work)
    setup.camera.device.frame_timing = camera_pb2.FRAME_TIMING_EXTERNAL_TRIGGER
    setup.camera.capture.session_preview_max_hz = 10

    preparation.setup_session(setup, 100, trial)  # type: ignore[arg-type]

    assert preparation.session_ready
    assert trial.pulse_required
    setup_report = events[-1]
    assert setup_report[0:2] == ("report", setup.command.command_id)
    assert setup_report[2].ready.required_checks_passed
    assert setup_report[2].ready.attached_resources[0] == resource
    assert events.index("recording-session-prepare") < events.index(
        next(item for item in events if isinstance(item, tuple) and item[0] == "report")
    )

    trial_work = control.WorkContext(
        trial=control.TrialContext(session=session_work.session, trial_id=str(uuid4()))
    )
    prepare_trial = acq.WorkerPrepareTrial(
        command=acq.WorkerCommand(command_id=str(uuid4()), target=context),
        required_configuration_revision=5,
    )
    prepare_trial.command.target.work.CopyFrom(trial_work)
    preparation.prepare_trial(prepare_trial, 200, trial)  # type: ignore[arg-type]

    assert trial.trial_prepared
    assert events[-1][0:2] == ("report", prepare_trial.command.command_id)
    assert events[-1][2].ready.configuration_revision == 5


def test_coordinator_loss_fences_paths_and_reuses_first_cleanup_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _worker_state()
    clock = iter((100, 200))
    monkeypatch.setattr(
        "cephvr.acquisition.worker.execution.host_time_ns", lambda: next(clock)
    )
    events: list[object] = []
    executor = object.__new__(WorkerOperationExecutor)
    executor.state = state
    executor.bootstrap = SimpleNamespace(
        control_policies=SimpleNamespace(recovery_ns=50)
    )
    executor._coordinator_loss = Event()
    executor._coordinator_loss_handled = False
    executor._coordinator_loss_details = None
    executor._coordinator_loss_deadline_ns = None
    executor._cancelled = Event()
    executor.external_wake = lambda: events.append("wake")
    executor.preview = SimpleNamespace(
        fence=lambda: events.append("preview-fenced"),
        advance_due_stage=lambda: events.append("preview-advance"),
    )
    executor.health = SimpleNamespace(
        coordinator_lost=lambda **kwargs: events.append(("health-loss", kwargs))
    )
    executor.trial = SimpleNamespace(
        stop_trial=lambda deadline: events.append(("trial-stop", deadline)),
        advance_due_stages=lambda: events.append("trial-advance"),
    )
    executor.cleanup = SimpleNamespace(
        begin_ambient_release=lambda deadline: events.append(
            ("cleanup-begin", deadline)
        ),
        advance=lambda: events.append("cleanup-advance"),
    )
    executor._refresh_health_snapshot = lambda: None

    executor.coordinator_lost(details="owner receipt lost")
    executor.coordinator_lost(details="repeated observation")
    executor.advance_due_stages()
    executor.advance_due_stages()

    assert state.interrupted
    assert executor._coordinator_loss_deadline_ns == 150
    assert executor._coordinator_loss_handled
    assert executor._cancelled.is_set()
    assert events.count("preview-fenced") == 1
    assert events.count(("trial-stop", 150)) == 1
    assert events.count(("cleanup-begin", 150)) == 1
    assert ("health-loss", {"details": "owner receipt lost"}) in events
    assert events.count("preview-advance") == 2
    assert events.count("trial-advance") == 2
    assert events.count("cleanup-advance") == 2


def _frame(frame_id: int, valid: bool = True) -> FrameRecord:
    return FrameRecord(
        frame_id,
        frame_id + 1,
        None,
        None,
        valid,
        None if valid else "INVALID_IMAGE",
    )


def test_queue_drops_oldest_pixels_and_preserves_ordered_rows() -> None:
    pool = PixelBufferPool(payload_bytes=4, capacity=2)
    queue = RecordingQueue(capacity_frames=1, pending_records_capacity=3)
    first, second = pool.acquire_nowait(), pool.acquire_nowait()
    first[:] = b"one!"
    second[:] = b"two!"
    assert queue.enqueue(_frame(0), first).dropped_pixels is None
    dropped = queue.enqueue(_frame(1), second)
    assert dropped.dropped_record == _frame(0)
    assert dropped.dropped_pixels is not None
    pool.release(dropped.dropped_pixels)
    entry = queue.dequeue()
    assert entry is not None
    assert entry.record == _frame(0)
    assert entry.dropped
    assert entry.pixels is None
    assert queue.complete(entry.record) is None
    entry = queue.dequeue()
    assert entry is not None and entry.record == _frame(1)
    recycled = queue.complete(entry.record)
    assert recycled is not None
    pool.release(recycled)
    queue.close()
    pool.close()


def test_pending_record_capacity_fences_instead_of_losing_accounting() -> None:
    queue = RecordingQueue(capacity_frames=1, pending_records_capacity=1)
    queue.enqueue(_frame(0, valid=False), None)
    with pytest.raises(PendingRecordCapacityError):
        queue.enqueue(_frame(1, valid=False), None)
    assert queue.pending_records == 1
    retained = queue.dequeue()
    assert retained is not None and retained.record == _frame(0, valid=False)
    queue.complete(retained.record)
    assert queue.pending_records == 0
    queue.close()


def test_warning_view_is_cumulative_and_unavailability_counts_transitions() -> None:
    source = acq.WorkerContext(
        worker=control.ProcessIdentity(
            role="acquisition_behavioral_worker", generation="worker-generation"
        ),
        owner=control.ProcessIdentity(
            role="acquisition", generation="owner-generation"
        ),
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
    )
    work = control.WorkContext(session=control.SessionContext(session_id="session"))
    ledger = WorkerWarningLedger(source)
    ledger.begin_scope(work, configuration_revision=2)
    first = ledger.observe_unavailability(
        "NATIVE_TIMESTAMP_UNAVAILABLE", True, 10, details="missing"
    )
    assert first is not None and first.warnings[0].acquisition_occurrence.count == 1
    assert (
        ledger.observe_unavailability(
            "NATIVE_TIMESTAMP_UNAVAILABLE", True, 11, details="still missing"
        )
        is None
    )
    assert (
        ledger.observe_unavailability("NATIVE_TIMESTAMP_UNAVAILABLE", False, 12) is None
    )
    second = ledger.observe_unavailability(
        "NATIVE_TIMESTAMP_UNAVAILABLE", True, 13, details="missing again"
    )
    assert second is not None and second.warnings[0].acquisition_occurrence.count == 2
    completed = ledger.complete_scope()
    assert completed.warning_revision == second.warning_revision
    assert len(ledger.views(work)) == 1


def test_warning_text_is_bounded_without_splitting_utf8() -> None:
    source = acq.WorkerContext(
        worker=control.ProcessIdentity(
            role="acquisition_tracking_worker", generation="worker-generation"
        ),
        owner=control.ProcessIdentity(
            role="acquisition", generation="owner-generation"
        ),
        camera=camera_pb2.CAMERA_ROLE_TRACKING,
    )
    work = control.WorkContext(session=control.SessionContext(session_id="session"))
    ledger = WorkerWarningLedger(source)
    ledger.begin_scope(work)
    view = ledger.observe(WarningOccurrence("INVALID_IMAGE", 1, details="魚" * 500))
    message = view.warnings[0].message
    assert len(message.encode("utf-8")) <= 1024
    assert message.endswith(" [truncated]")


def test_worker_control_limits_follow_shared_transport_ceiling() -> None:
    ordinary = AcquisitionControlLimits.from_message_limit(4 * 1024 * 1024)
    assert ordinary.max_records == 1024
    assert ordinary.max_bytes == 64 * 1024 * 1024
    assert ordinary.normal_result_reservation_bytes == 64 * 1024
    assert ordinary.large_result_reservation_bytes == 4 * 1024 * 1024
    assert ordinary.safety_reserve_records == 16
    assert ordinary.safety_reserve_bytes == 2 * 1024 * 1024

    large = AcquisitionControlLimits.from_message_limit(32 * 1024 * 1024)
    assert large.max_bytes == 128 * 1024 * 1024


def test_priority_lifecycle_evidence_uses_the_reserved_safety_budget() -> None:
    worker = control.ProcessIdentity(
        role="acquisition_behavioral_worker", generation=str(uuid4())
    )
    owner = control.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    work = control.WorkContext(session=control.SessionContext(session_id=str(uuid4())))
    ledger = CommandLedger(
        worker.generation,
        10_000,
        max_records=8,
        max_bytes=4096,
        result_reservation_bytes=128,
        safety_reserve_records=2,
        safety_reserve_bytes=1024,
    )
    stop_id = str(uuid4())
    ledger.admit(
        stop_id,
        b"StopTrial\\0request",
        1,
        work_key=work.session.session_id,
        result_reservation_bytes=128,
        priority=True,
    )
    ledger.admit(
        str(uuid4()),
        b"ordinary-operation",
        2,
        work_key=work.session.session_id,
        result_reservation_bytes=2800,
    )
    context = acq.WorkerContext(
        worker=worker,
        owner=owner,
        work=work,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
    )
    state = WorkerState(
        context,
        control.ProcessIdentity(role="supervisor", generation=str(uuid4())),
        ledger,
    )
    evidence = acq.WorkerLifecycleEvidence(source=context, state_revision=1)
    evidence.operation.command_id = stop_id
    evidence.finished.activity_stopped = True
    evidence.finished.outputs.add(
        output_key="camera-output",
        path="C:/trial.mp4",
        closure=control.OUTPUT_CLOSURE_CLOSED,
        artifact_present=True,
    )
    assert ledger.retained_bytes + evidence.ByteSize() > (
        ledger.max_bytes - ledger.safety_reserve_bytes
    )
    state.retain_lifecycle(evidence)
    assert ledger.has_payload(f"worker-lifecycle:{stop_id}:finished")


def test_continuous_invalid_result_stream_cannot_suppress_silence_deadline() -> None:
    class InvalidResult:
        valid_image = False
        pixels = None
        layout = None
        camera_frame_counter = None
        camera_timestamp_ns = None
        error_code = "bad-frame"
        error_message = "invalid"
        released = False

        def release(self) -> None:
            self.released = True

    result = InvalidResult()

    class Adapter:
        def wait_for_frame_or_control(self, timeout_ns: int) -> str:
            assert timeout_ns >= 0
            return "frame"

        def retrieve(self, timeout_ns: int) -> InvalidResult:
            assert timeout_ns == 0
            return result

    pixel_layout = PixelLayout(
        width=1,
        height=1,
        pixel_format=NativePixelFormat(
            "Mono8", 1, 8, "mono", "unpacked", "byte", "lsb"
        ),
        row_stride_bytes=1,
        image_payload_bytes=1,
    )
    loop = CameraCaptureLoop(
        adapter=Adapter(),  # type: ignore[arg-type]
        layout=pixel_layout,
        wait_timeout_ns=lambda: 10,
        frame_silence_timeout_ns=5,
        recording_window=lambda: CaptureWindow(10, 100),
        clock_ns=lambda: 20,
    )

    with pytest.raises(RuntimeError, match="usable camera frame silence"):
        loop.capture_once(lambda: True)
    assert loop.received_frame_count == 1
    assert result.released


def test_early_cutoff_retrieval_is_excluded_from_trial_accounting() -> None:
    class Result:
        valid_image = True
        pixels = memoryview(b"x")
        layout: PixelLayout
        camera_frame_counter = None
        camera_timestamp_ns = None
        released = False

        def release(self) -> None:
            self.released = True

    results = [Result(), Result()]
    layout = PixelLayout(
        width=1,
        height=1,
        pixel_format=NativePixelFormat(
            "Mono8", 1, 8, "mono", "unpacked", "byte", "lsb"
        ),
        row_stride_bytes=1,
        image_payload_bytes=1,
    )
    for result in results:
        result.layout = layout

    class Adapter:
        def __init__(self) -> None:
            self.index = 0

        def wait_for_frame_or_control(self, timeout_ns: int) -> str:
            assert timeout_ns >= 0
            return "frame"

        def retrieve(self, timeout_ns: int) -> Result:
            assert timeout_ns == 0
            result = results[self.index]
            self.index += 1
            return result

    pool = PixelBufferPool(payload_bytes=1, capacity=3)
    queue = RecordingQueue(capacity_frames=1, pending_records_capacity=3)
    times = iter((150, 150, 250, 250))
    loop = CameraCaptureLoop(
        adapter=Adapter(),  # type: ignore[arg-type]
        layout=layout,
        wait_timeout_ns=lambda: 100,
        frame_silence_timeout_ns=1_000,
        recording_queue=queue,
        pixel_pool=pool,
        recording_window=lambda: CaptureWindow(100, 200),
        clock_ns=lambda: next(times),
    )

    assert loop.capture_once(lambda: True)
    assert loop.capture_once(lambda: True)
    assert loop.received_frame_count == 1
    assert loop.excluded_frame_count == 1
    entry = queue.dequeue()
    assert entry is not None and entry.record.frame_id == 0
    recycled = queue.complete(entry.record)
    assert recycled is not None
    pool.release(recycled)
    queue.close()
    pool.close()
    assert all(result.released for result in results)


def test_manual_preview_capture_publishes_ordered_tracking_and_preview_pixels() -> None:
    from cephvr.acquisition.buffers.records import FrameDiagnostic

    layout = PixelLayout(
        width=2,
        height=1,
        pixel_format=NativePixelFormat(
            "Mono8", 1, 8, "mono", "unpacked", "byte", "lsb"
        ),
        row_stride_bytes=2,
        image_payload_bytes=2,
    )

    class Result:
        valid_image = True
        camera_timestamp_ns = None

        def __init__(self, counter: int, pixels: bytes) -> None:
            self.camera_frame_counter = counter
            self.layout = layout
            self.pixels = memoryview(pixels)
            self.released = False

        def release(self) -> None:
            self.released = True

    results = [Result(10, b"\x12\x34"), Result(12, b"\x56\x78")]

    class Adapter:
        def __init__(self) -> None:
            self.next_result = 0

        def wait_for_frame_or_control(self, _timeout_ns: int) -> str:
            return "frame"

        def retrieve(self, _timeout_ns: int) -> Result:
            result = results[self.next_result]
            self.next_result += 1
            return result

    class Ring:
        def __init__(self) -> None:
            self.records: list[FrameRecord] = []
            self.pixels: list[bytes] = []
            self.discontinuities = 0

        def publish(self, record: FrameRecord, pixels: memoryview) -> None:
            self.records.append(record)
            self.pixels.append(bytes(pixels))

        def advance_discontinuity(self) -> None:
            self.discontinuities += 1

    tracking, preview = Ring(), Ring()
    receipts = count(100)
    loop = CameraCaptureLoop(
        adapter=Adapter(),  # type: ignore[arg-type]
        layout=layout,
        wait_timeout_ns=lambda: 1_000_000,
        frame_silence_timeout_ns=1_000_000,
        tracking_ring=tracking,  # type: ignore[arg-type]
        preview_ring=preview,  # type: ignore[arg-type]
        diagnostics_for=lambda result: (
            (FrameDiagnostic("NATIVE_COUNTER_GAP"),)
            if result.camera_frame_counter == 12
            else ()
        ),
        clock_ns=lambda: next(receipts),
    )

    assert loop.capture_once(lambda: True)
    assert loop.capture_once(lambda: True)

    assert [record.frame_id for record in tracking.records] == [0, 1]
    assert [record.frame_id for record in preview.records] == [0, 1]
    assert tracking.pixels == [b"\x12\x34", b"\x56\x78"]
    assert preview.pixels == tracking.pixels
    assert tracking.discontinuities == 1
    assert not hasattr(loop, "recording_queue") or loop.recording_queue is None
    assert all(result.released for result in results)


def test_cancel_after_release_before_t_prevents_later_camera_start() -> None:
    class Adapter:
        started = False

        def start_free_running(self) -> None:
            self.started = True

        def arm_external_trigger(self) -> None:
            self.started = True

    worker = acq.WorkerContext(
        worker=control.ProcessIdentity(
            role="acquisition_behavioral_worker", generation="worker-generation"
        ),
        owner=control.ProcessIdentity(
            role="acquisition", generation="owner-generation"
        ),
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
    )
    adapter = Adapter()
    resources = WorkerCaptureResources(
        adapter,  # type: ignore[arg-type]
        worker,
        warning_occurrence=lambda _occurrence: None,
    )
    resources.capture = object()  # type: ignore[assignment]
    resources.layout = PixelLayout(
        width=1,
        height=1,
        pixel_format=NativePixelFormat(
            "Mono8", 1, 8, "mono", "unpacked", "byte", "lsb"
        ),
        row_stride_bytes=1,
        image_payload_bytes=1,
    )
    resources._timing = "free_running"
    resources._sdk_buffer_count = 1
    run_id = uuid4()
    resources.schedule(100, 200, run_id)
    resources.release_schedule()
    resources.cancel_schedule()

    resources.advance_due_stage(now_ns=150)

    assert resources.next_deadline_ns() is None
    assert not resources.active
    assert not adapter.started


@pytest.mark.parametrize("generation_stopped", [False, True])
@pytest.mark.parametrize("terminal_off", [False, True])
def test_capture_stop_retains_first_cutoff_and_original_deadline(
    monkeypatch: pytest.MonkeyPatch,
    generation_stopped: bool,
    terminal_off: bool,
) -> None:
    events: list[object] = []

    class Adapter:
        def __init__(self) -> None:
            self.deadlines: list[int] = []

        def begin_terminal_drain(self) -> bool:
            events.append("generation_stop")
            return generation_stopped

        def confirm_drain_margin(self) -> None:
            events.append("drain_margin")
            return None

        def stop_capture(
            self, deadline_ns: int, *, should_continue_drain: object
        ) -> object:
            self.deadlines.append(deadline_ns)
            events.append("purge")
            return SimpleNamespace(
                discarded_frame_count=None,
                last_native_counter=None,
                accounting_complete=False,
            )

    adapter = Adapter()
    worker = acq.WorkerContext(
        worker=control.ProcessIdentity(
            role="acquisition_behavioral_worker", generation="worker-generation"
        ),
        owner=control.ProcessIdentity(
            role="acquisition", generation="owner-generation"
        ),
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
    )
    resources = WorkerCaptureResources(
        adapter,  # type: ignore[arg-type]
        worker,
        warning_occurrence=lambda _occurrence: None,
    )
    resources._active = True
    resources._timing = "free_running"
    resources._window = CaptureWindow(100, 500)
    monkeypatch.setattr(
        "cephvr.acquisition.worker.capture_runtime.host_time_ns", lambda: 200
    )

    resources.stop(
        1000,
        drain_margin_ns=0,
        terminal_off_confirmed=terminal_off,
        activity_stopped=lambda observed: events.append(observed),
    )
    resources.stop(2000, drain_margin_ns=0)

    assert resources.admission_stop_ns == 200
    assert adapter.deadlines == [1000, 1000]
    assert (200 in events) == (generation_stopped and terminal_off)
    if 200 in events:
        assert (
            events.index("generation_stop") < events.index(200) < events.index("purge")
        )


def test_consecutive_non_saving_trials_reset_shared_trial_state() -> None:
    class Captures:
        active = False
        layout = None
        frame_silence_timeout_ns = 100

        def __init__(self) -> None:
            self.prepared: list[object] = []

        def should_continue_drain(self) -> bool:
            return True

        def prepare_trial(
            self, run_id: object, _deadline_ns: int, **_kwargs: object
        ) -> None:
            self.prepared.append(run_id)

    class Adapter:
        def read_transport_counters(self) -> None:
            return None

    class Activity:
        def __init__(self) -> None:
            self.resets = 0

        def reset(self) -> None:
            self.resets += 1

    session = control.SessionContext(session_id="session")
    source = acq.WorkerContext(
        worker=control.ProcessIdentity(
            role="acquisition_behavioral_worker", generation=str(uuid4())
        ),
        owner=control.ProcessIdentity(role="acquisition", generation="owner"),
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
    )
    bootstrap = cast(
        WorkerBootstrap,
        SimpleNamespace(
            context=source,
            control_policies=SimpleNamespace(),
            file_policy=SimpleNamespace(),
        ),
    )
    worker_state = WorkerState(
        context=source,
        supervisor=control.ProcessIdentity(role="supervisor", generation="supervisor"),
        commands=CommandLedger(
            source.worker.generation,
            1_000,
            max_records=8,
            max_bytes=1024 * 1024,
            result_reservation_bytes=1024,
        ),
    )
    captures = Captures()
    lifecycle = WorkerTrialLifecycle(
        bootstrap,
        worker_state,
        Adapter(),  # type: ignore[arg-type]
        captures,  # type: ignore[arg-type]
        None,
        report_lifecycle=lambda *_args: None,
        source=lambda target: target,
        warning_occurrence=lambda _occurrence: None,
        recording_warning_occurrence=lambda *_args: None,
        begin_warning_scope=lambda *_args, **_kwargs: None,
        complete_warning_scope=lambda: None,
        external_wake=lambda: None,
        recording_first_frame=lambda _observed: None,
        recording_isolated=lambda *_args: None,
        require_ready_session=lambda _request: None,
        capability_resource_released=lambda _resource, _released: None,
    )
    activity = Activity()
    lifecycle.activity = activity  # type: ignore[assignment]
    lifecycle.trial_state.end_marker = CaptureEndMarker(0, 1, None, None, None, False)
    lifecycle.trial_state.purge_evidence = PurgeEvidence(None, None, False)
    lifecycle.trial_state.stop_request = acq.WorkerStop()
    lifecycle.trial_state.finish_deadline_ns = 123
    lifecycle.trial_state.transport_start = TransportCounters(
        None, None, None, None, None, None
    )
    lifecycle.trial_state.transport_summary = {"missed_frames": 2}
    lifecycle.trial_state.transport_observed_ns = 456

    requests = [
        acq.WorkerPrepareTrial(
            command=acq.WorkerCommand(
                command_id=f"prepare-{index}",
                target=acq.WorkerContext(
                    worker=source.worker,
                    owner=source.owner,
                    camera=source.camera,
                    work=control.WorkContext(
                        trial=control.TrialContext(
                            session=session,
                            trial_id=str(uuid4()),
                            trial_number=index,
                        )
                    ),
                ),
            )
        )
        for index in range(2)
    ]
    for index, request in enumerate(requests, start=1):
        lifecycle.prepare_trial_state(request, deadline_ns=1000 + index)
        assert lifecycle.end_marker is None
        assert lifecycle.trial_state.purge_evidence is None
        assert lifecycle.stop_request is None
        assert lifecycle.trial_state.finish_deadline_ns is None
        assert lifecycle.trial_state.transport_summary is None
        assert lifecycle.trial_state.transport_observed_ns is None
    assert len(captures.prepared) == 2
    assert activity.resets == 2


def test_camera_owner_serializes_safety_work_ahead_of_committed_normal_work() -> None:
    entered_wait = Event()
    release_wait = Event()
    wake = Event()
    completed = Event()
    observed: list[tuple[str, int, int]] = []
    owner_ref: list[SerializedCameraOwner] = []

    def wait_control(_timeout_ns: int) -> None:
        entered_wait.set()
        release_wait.wait(1)
        wake.clear()

    def execute(name: str, _request: object, deadline_ns: int) -> None:
        observed.append((name, get_ident(), deadline_ns))
        if len(observed) == 2:
            completed.set()

    owner = SerializedCameraOwner(
        capacity=2,
        safety_capacity=2,
        execute=execute,
        capture_once=lambda _handoff: False,
        capture_active=lambda: False,
        next_deadline_ns=lambda: None,
        advance_due_stages=lambda: None,
        wait_control=wait_control,
        wake_control=wake.set,
        clear_control=wake.clear,
        operation_failed=lambda _name, error: pytest.fail(str(error)),
        owner_failed=lambda error: pytest.fail(str(error)),
        idle_maintenance_interval_ns=1_000_000,
    )
    owner_ref.append(owner)
    owner.start()
    try:
        assert entered_wait.wait(1)
        normal = owner.reserve("ResolveCameraConfiguration", object(), 100)
        safety = owner.reserve("Cleanup", object(), 200)
        normal.commit()
        safety.commit()
        release_wait.set()
        assert completed.wait(1)
    finally:
        assert owner_ref[0].stop(1)

    assert [item[0] for item in observed] == ["Cleanup", "ResolveCameraConfiguration"]
    assert {item[1] for item in observed} == {owner.owner_thread_id}
    assert [item[2] for item in observed] == [200, 100]


def test_preview_start_reports_only_first_usable_frame_for_retained_run() -> None:
    state = _worker_state()
    run_id = str(uuid4())
    deadline = 900
    events: list[object] = []

    class Captures:
        active = False

        def start(self) -> None:
            events.append("capture-start")

    request = acq.WorkerStartPreview(
        command=acq.WorkerCommand(command_id=str(uuid4())),
        preview_run_id=run_id,
    )
    lifecycle = WorkerPreviewLifecycle(
        state,
        Captures(),  # type: ignore[arg-type]
        cast(
            object,
            SimpleNamespace(release_device=lambda: events.append("device-release")),
        ),  # type: ignore[arg-type]
        begin_warning_scope=lambda *_args, **_kwargs: None,
        complete_warning_scope=lambda: None,
        verify_wait=lambda _deadline: None,
        operation_deadline=lambda command_id: (
            deadline if command_id == request.command.command_id else 0
        ),
        report_lifecycle=lambda req, evidence, bound: events.append(
            (req.command.command_id, evidence, bound)
        ),
        owner_failure=lambda error: events.append(error),
        recovery_ns=100,
        clock_ns=lambda: 500,
    )
    lifecycle.manual_preview = True
    lifecycle.run_id = run_id
    lifecycle.start(request)

    assert lifecycle.next_deadline_ns == deadline
    assert lifecycle.first_usable_frame(_frame(0))
    report_id, evidence, bound = events[-1]  # type: ignore[misc]
    assert report_id == request.command.command_id
    assert bound == deadline
    assert evidence.started.first_activity[0].device_evidence.camera == (
        camera_pb2.CAMERA_ROLE_BEHAVIORAL
    )
    assert evidence.started.first_activity[0].device_evidence.producer == (
        state.context.worker
    )
    assert lifecycle.next_deadline_ns is None
    assert not lifecycle.first_usable_frame(_frame(1))


def test_preview_start_deadline_stops_and_releases_unusable_capture() -> None:
    state = _worker_state()
    run_id = str(uuid4())
    events: list[object] = []

    class Captures:
        active = True

        def start(self) -> None:
            events.append("capture-start")

        def stop(self, deadline_ns: int) -> None:
            events.append(("capture-stop", deadline_ns))

        def release(self) -> tuple[object, ...]:
            events.append("capture-release")
            return ()

    class Adapter:
        def release_device(self) -> None:
            events.append("device-release")

    request = acq.WorkerStartPreview(
        command=acq.WorkerCommand(command_id=str(uuid4())),
        preview_run_id=run_id,
    )
    captures = Captures()
    lifecycle = WorkerPreviewLifecycle(
        state,
        captures,  # type: ignore[arg-type]
        Adapter(),  # type: ignore[arg-type]
        begin_warning_scope=lambda *_args, **_kwargs: None,
        complete_warning_scope=lambda: None,
        verify_wait=lambda _deadline: None,
        operation_deadline=lambda _command_id: 500,
        report_lifecycle=lambda *_args: pytest.fail(
            "timed-out preview start cannot report started evidence"
        ),
        owner_failure=lambda error: events.append(error),
        recovery_ns=100,
        clock_ns=lambda: 500,
    )
    lifecycle.manual_preview = True
    lifecycle.run_id = run_id
    lifecycle.start(request)

    lifecycle.advance_due_stage()

    assert state.interrupted
    assert not lifecycle.manual_preview and lifecycle.run_id is None
    assert events[:4] == [
        "capture-start",
        ("capture-stop", 600),
        "capture-release",
        "device-release",
    ]
    assert isinstance(events[4], TimeoutError)
    assert "no usable frame" in str(events[4])


def test_cleanup_releases_owned_resources_before_reporting_exact_evidence() -> None:
    state = _worker_state()
    events: list[str] = []
    reports: list[acq.WorkerLifecycleEvidence] = []

    class Captures:
        def release(self) -> tuple[object, ...]:
            events.append("capture-release")
            return (SimpleNamespace(resource_id="ring:preview"),)

    class Adapter:
        def release_device(self) -> None:
            events.append("device-release")

    request = acq.WorkerCommand(command_id=str(uuid4()))
    cleanup = WorkerCleanupLifecycle(
        state,
        Adapter(),  # type: ignore[arg-type]
        Captures(),  # type: ignore[arg-type]
        None,
        capacity=2,
        extra_resources=lambda: {"ring:tracking": True, "ring:other": False},
        report_lifecycle=lambda _request, evidence, _deadline: (
            events.append("report"),
            reports.append(evidence),
        ),
        report_operation=lambda *_args: None,
        shutdown=lambda _deadline: events.append("shutdown"),
        recording_reconciled=lambda: None,
        external_wake=lambda: None,
    )

    assert cleanup.begin_operation(
        "Cleanup", request, 1_000, acq.WorkerOperationReport()
    )

    assert events == ["capture-release", "device-release", "report"]
    assert reports[0].cleanup.resources[0].resource == (
        f"camera-device:{state.context.worker.generation}"
    )
    assert [item.resource for item in reports[0].cleanup.resources] == [
        f"camera-device:{state.context.worker.generation}",
        "ring:preview",
        "ring:other",
        "ring:tracking",
    ]
    assert [item.released for item in reports[0].cleanup.resources] == [
        True,
        True,
        False,
        True,
    ]


def test_cleanup_continuation_fails_at_original_deadline_without_releasing_camera(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _worker_state()
    command_id = str(uuid4())
    deadline_ns = 500
    request = acq.WorkerCommand(command_id=command_id, target=state.context)
    state.commands.admit(
        command_id,
        b"cleanup",
        1,
        work_key=state.context.worker.generation,
        deadline_ns=deadline_ns,
    )
    state.operations[command_id] = control.OperationState(
        context=control.OperationContext(command_id=command_id), command="Cleanup"
    )
    recording_cleanup: Future[list[control.OutputResult]] = Future()
    events: list[object] = []

    class Recording:
        enabled = True
        recording_queue = object()

        def fail_cleanup(
            self, *, deadline_ns: int
        ) -> Future[list[control.OutputResult]]:
            events.append(("recording-cleanup", deadline_ns))
            return recording_cleanup

    class Captures:
        def release(self) -> tuple[object, ...]:
            events.append("capture-release")
            return ()

    class Adapter:
        def release_device(self) -> None:
            events.append("device-release")

    cleanup = WorkerCleanupLifecycle(
        state,
        Adapter(),  # type: ignore[arg-type]
        Captures(),  # type: ignore[arg-type]
        Recording(),  # type: ignore[arg-type]
        capacity=2,
        extra_resources=lambda: {},
        report_lifecycle=lambda *_args: events.append("lifecycle-report"),
        report_operation=lambda _report, bound: events.append(
            ("operation-report", bound)
        ),
        shutdown=lambda _deadline: None,
        recording_reconciled=lambda: None,
        external_wake=lambda: None,
    )
    assert not cleanup.begin_operation(
        "Cleanup", request, deadline_ns, acq.WorkerOperationReport()
    )
    monkeypatch.setattr(
        "cephvr.acquisition.worker.cleanup_lifecycle.host_time_ns", lambda: deadline_ns
    )

    cleanup.advance()

    result = state.operations[command_id]
    assert result.complete and not result.succeeded
    assert result.failure.code == "DEADLINE_EXCEEDED"
    assert events == [
        ("recording-cleanup", deadline_ns),
        ("operation-report", deadline_ns),
    ]


def test_ambient_cleanup_waits_for_recording_proof_then_wakes_and_releases() -> None:
    state = _worker_state()
    recording_cleanup: Future[list[control.OutputResult]] = Future()
    wake = Event()
    events: list[object] = []

    class Recording:
        enabled = True
        recording_queue = object()

        def fail_cleanup(
            self, *, deadline_ns: int
        ) -> Future[list[control.OutputResult]]:
            events.append(("recording-cleanup", deadline_ns))
            return recording_cleanup

        def recycle_finished(self, deadline_ns: int) -> None:
            events.append(("recording-reconciled", deadline_ns))

    class Captures:
        def release(self) -> tuple[object, ...]:
            events.append("capture-release")
            return ()

    class Adapter:
        def release_device(self) -> None:
            events.append("device-release")

    cleanup = WorkerCleanupLifecycle(
        state,
        Adapter(),  # type: ignore[arg-type]
        Captures(),  # type: ignore[arg-type]
        Recording(),  # type: ignore[arg-type]
        capacity=2,
        extra_resources=lambda: {},
        report_lifecycle=lambda *_args: events.append("lifecycle-report"),
        report_operation=lambda *_args: None,
        shutdown=lambda _deadline: None,
        recording_reconciled=lambda: events.append("reconciliation-callback"),
        external_wake=wake.set,
    )

    cleanup.begin_ambient_release(700)
    cleanup.advance()
    assert events == [("recording-cleanup", 700)]
    assert not wake.is_set()

    recording_cleanup.set_result([])
    assert wake.wait(1)
    cleanup.advance()

    assert events == [
        ("recording-cleanup", 700),
        ("recording-reconciled", 700),
        "reconciliation-callback",
        "capture-release",
        "device-release",
    ]


def test_worker_report_dispatch_marks_rejection_and_drains_accepted_rpc() -> None:
    async def run() -> tuple[WorkerState, list[str]]:
        state = _worker_state()
        failures: list[str] = []

        class Reports:
            async def report_operation(
                self, _report: acq.WorkerOperationReport, *, deadline_ns: int
            ) -> control.ReportReceipt:
                assert deadline_ns > 0
                return control.ReportReceipt(
                    result=control.COMMAND_RESULT_REJECTED,
                    failure=control.Failure(code="STALE", message="wrong generation"),
                )

        dispatcher = WorkerReportDispatcher(
            asyncio.get_running_loop(),
            state,
            Reports(),  # type: ignore[arg-type]
            1,
            failures.append,
        )
        dispatcher.operation(acq.WorkerOperationReport(), 10**18)
        assert await dispatcher.drain(10**18)
        return state, failures

    state, failures = asyncio.run(run())
    assert state.interrupted
    assert failures == ["worker report rejected: STALE: wrong generation"]


def test_camera_resolution_rejects_unassigned_device_before_adapter_access() -> None:
    from cephvr.acquisition.worker.camera_resolution import resolve_camera

    class Adapter:
        touched = False

        def open(self, _device_id: str) -> None:
            self.touched = True

    adapter = Adapter()
    request = acq.WorkerResolveCamera(configuration_revision=1)

    with pytest.raises(ValueError, match="assigned device"):
        resolve_camera(adapter, request)  # type: ignore[arg-type]

    assert not adapter.touched


def test_camera_resolution_applies_the_assigned_device_before_readback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cephvr.acquisition.camera.types import CameraSettings
    from cephvr.acquisition.worker import camera_resolution

    events: list[object] = []
    request = acq.WorkerResolveCamera(
        configuration_revision=7,
        requested=camera_pb2.CameraDeviceConfiguration(
            device_id="serial-A",
            frame_timing=camera_pb2.FRAME_TIMING_FREE_RUNNING,
        ),
    )
    actual = CameraSettings(
        exposure_us=125.0,
        gain=None,
        frame_rate_hz=60.0,
        roi=None,
        pixel_format="Mono8",
        trigger_selector=None,
        trigger_source=None,
        trigger_activation=None,
        exposure_duration_mode=None,
    )

    class Adapter:
        def open(self, device_id: str) -> None:
            events.append(("open", device_id))

        def configure_capture(self, timing: str, buffer_count: int) -> None:
            events.append(("capture", timing, buffer_count))

        def apply_settings(self, settings: CameraSettings) -> object:
            events.append(("settings", settings))
            return SimpleNamespace(actual=actual, effective_exposure_us=125.0)

        def apply_transport_settings(self, settings: object) -> object:
            events.append(("transport", settings))
            return settings

        def configure_native_metadata(self) -> object:
            events.append("metadata")
            return object()

        def read_layout(self) -> object:
            events.append("layout")
            return object()

        def read_device_identity(self) -> object:
            events.append("identity")
            return object()

        def capabilities(self) -> object:
            events.append("capabilities")
            return object()

    resolved: list[dict[str, object]] = []

    def serialize(**kwargs: object) -> camera_pb2.CameraResolvedState:
        resolved.append(kwargs)
        return camera_pb2.CameraResolvedState(configuration_revision=7)

    monkeypatch.setattr(camera_resolution, "resolved_state_to_wire", serialize)
    result = camera_resolution.resolve_camera(Adapter(), request)  # type: ignore[arg-type]

    assert result.configuration_revision == 7
    assert events[0] == ("open", "serial-A")
    assert events[1] == ("capture", "free_running", 1)
    assert [item if isinstance(item, str) else item[0] for item in events] == [
        "open",
        "capture",
        "settings",
        "transport",
        "metadata",
        "layout",
        "identity",
        "capabilities",
    ]
    assert resolved[0]["configuration_revision"] == 7
    assert resolved[0]["effective_exposure_us"] == 125.0


def test_worker_health_owner_failure_is_retained_when_supervisor_report_fails() -> None:
    state = _worker_state()
    dispatched: list[object] = []
    bootstrap = cast(
        WorkerBootstrap,
        SimpleNamespace(
            context=state.context,
            control_policies=SimpleNamespace(recovery_ns=100),
        ),
    )

    class Supervisor:
        async def report_error(
            self, request: control.ErrorReport, *, deadline_ns: int
        ) -> control.ReportReceipt:
            assert deadline_ns == request.occurred_monotonic_ns + 100
            dispatched.append(request)
            raise RuntimeError("supervisor unavailable")

    def dispatch(awaitable: object) -> None:
        asyncio.run(cast(object, awaitable))  # type: ignore[arg-type]

    reporter = WorkerHealthReporter(
        bootstrap,
        state,
        cast(object, SimpleNamespace()),  # type: ignore[arg-type]
        Supervisor(),  # type: ignore[arg-type]
        dispatch,
        lambda: None,
    )

    reporter.owner_failed(RuntimeError("camera owner stopped"))

    assert state.interrupted
    assert len(dispatched) == 1
    error = cast(control.ErrorReport, dispatched[0])
    assert error.source == state.context.worker
    assert error.failure.code == "WORKER_OWNER_FAILURE"
    assert error.failure.message == "camera owner stopped"


def test_health_ages_owner_published_capture_snapshot_without_runtime_reads() -> None:
    source = acq.WorkerContext(
        worker=control.ProcessIdentity(
            role="acquisition_behavioral_worker", generation="worker-generation"
        ),
        owner=control.ProcessIdentity(
            role="acquisition", generation="owner-generation"
        ),
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
    )
    state = WorkerState(
        context=source,
        supervisor=control.ProcessIdentity(role="supervisor", generation="supervisor"),
        commands=CommandLedger(
            str(uuid4()),
            1_000,
            max_records=16,
            max_bytes=1024 * 1024,
            result_reservation_bytes=1024,
        ),
    )
    capture = control.ContinuingFunctionEvidence(
        resource_id="behavioral.capture",
        functioning=True,
        control_path_valid=True,
        observed_monotonic_ns=100,
    )
    state.update_continuing_snapshot((capture,))
    state.update_health_snapshot(
        work=None,
        session_phase=control.SESSION_PHASE_READY,
        trial_phase=control.TRIAL_PHASE_RUNNING,
        progress_required=True,
        last_progress_ns=100,
        observed_ns=100,
    )

    fresh = state.heartbeat_report(150, health_silence_ns=100)
    assert fresh.continuing_functions[0].resource_id == "behavioral.capture"
    assert fresh.continuing_functions[0].functioning
    assert fresh.continuing_functions[0].control_path_valid

    stale = state.heartbeat_report(250, health_silence_ns=100)
    assert stale.continuing_functions[0].resource_id == "behavioral.capture"
    assert not stale.continuing_functions[0].functioning
    assert not stale.continuing_functions[0].control_path_valid
