"""Prepared, hardware-free checks for worker accounting and warning contracts.

The behavioral camera and synchronization suite is intentionally reserved for the
owner's E15 rig-first verification plan.
"""

from __future__ import annotations

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
from cephvr.acquisition.worker.capture import CameraCaptureLoop, CaptureWindow
from cephvr.acquisition.worker.capture_runtime import WorkerCaptureResources
from cephvr.acquisition.worker.limits import AcquisitionControlLimits
from cephvr.acquisition.worker.state import WorkerBootstrap, WorkerState
from cephvr.acquisition.worker.trial_lifecycle import WorkerTrialLifecycle
from cephvr.acquisition.worker.warnings import WarningOccurrence, WorkerWarningLedger
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.commands import CommandLedger
from cephvr.shared.pixels.types import NativePixelFormat, PixelLayout


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
    times = iter((150, 250))
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


def test_capture_stop_retains_first_cutoff_and_original_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Adapter:
        def __init__(self) -> None:
            self.deadlines: list[int] = []

        def begin_terminal_drain(self) -> bool:
            return True

        def confirm_drain_margin(self) -> None:
            return None

        def stop_capture(
            self, deadline_ns: int, *, should_continue_drain: object
        ) -> object:
            self.deadlines.append(deadline_ns)
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

    resources.stop(1000, drain_margin_ns=0)
    resources.stop(2000, drain_margin_ns=0)

    assert resources.admission_stop_ns == 200
    assert adapter.deadlines == [1000, 1000]


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
            role="acquisition_behavioral_worker", generation="worker"
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
            "worker",
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
            "worker-generation",
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
