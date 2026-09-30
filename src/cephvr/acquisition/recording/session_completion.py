"""Assemble terminal frame-log evidence and reconcile exact file closure."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from cephvr.acquisition.buffers.end_marker import CaptureEndMarker
from cephvr.acquisition.recording.frame_log import FrameLogCompletion, FrameLogWriter
from cephvr.acquisition.recording.session_contracts import (
    EncoderProcess,
    PulseEvidence,
    RecordingCompletionContext,
    RecordingFailure,
    VideoSync,
)
from cephvr.acquisition.recording.session_diagnostics import RecordingDiagnostics
from cephvr.acquisition.recording.session_finalizer import (
    FinalizationProgress,
    append_terminal_and_close,
    close_encoder_and_sync_video,
)
from cephvr.acquisition.recording.session_outputs import (
    failed_outputs,
    successful_outputs,
)
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control


def finish_recording(
    end: CaptureEndMarker,
    pulses: PulseEvidence,
    completion: RecordingCompletionContext,
    *,
    schedule: acq.WorkerSchedule,
    received: int,
    submitted: int,
    logged: int,
    last_frame_id: int,
    diagnostics: RecordingDiagnostics,
    encoder: EncoderProcess,
    frame_log: FrameLogWriter,
    video_sync: VideoSync | None,
    finalization: FinalizationProgress,
    video_path: Path,
    frame_log_path: Path,
    video_identity: object | None,
    observe_video: Callable[[], VideoSync | None],
    stat_identity: Callable[[Path], object | None],
    clock_ns: Callable[[], int],
    original_deadline_ns: int,
    cleanup_deadline_ns: int,
) -> tuple[list[control.OutputResult], VideoSync | None]:
    """Write one terminal record, then return only evidence-backed output states."""
    if completion.outcome not in {"completed", "interrupted"}:
        raise RecordingFailure("terminal recording outcome is invalid")
    stop_matches = (
        end.recording_end_monotonic_ns == completion.stopped_recording_end_monotonic_ns
        and end.actual_stop_monotonic_ns == completion.stopped_actual_stop_monotonic_ns
    )
    timing_valid = (
        end.recording_end_monotonic_ns is not None
        and end.actual_stop_monotonic_ns is not None
        and schedule.start_monotonic_ns
        <= end.recording_end_monotonic_ns
        <= schedule.end_monotonic_ns
    )
    accounting_complete = (
        end.received_frame_count == received == logged and last_frame_id == received - 1
    )
    if received and not submitted and not diagnostics.contains("NO_VIDEO_FRAMES"):
        diagnostics.record(
            "NO_VIDEO_FRAMES",
            native_code=None,
            details=f"received_frames={received}; recorded_frames=0",
            observed_ns=(
                end.recording_end_monotonic_ns
                if end.recording_end_monotonic_ns is not None
                else clock_ns()
            ),
            frame_id=None,
        )
    success_evidence = (
        stop_matches
        and timing_valid
        and accounting_complete
        and end.excluded_accounting_complete
        and pulses.complete()
        and received > 0
    )
    finalization.late |= clock_ns() > original_deadline_ns
    exit_code, video_sync = close_encoder_and_sync_video(
        finalization,
        encoder,
        video_sync,
        deadline_ns=cleanup_deadline_ns,
        clock_ns=clock_ns,
        observe_video=observe_video,
    )
    finalization.late |= clock_ns() > original_deadline_ns
    current_video_identity = (
        video_sync.file_identity
        if video_sync is not None
        else encoder.output_identity()
    )
    log_completion = FrameLogCompletion(
        outcome=(
            completion.outcome
            if success_evidence and exit_code == 0 and not finalization.late
            else "interrupted"
        ),
        recording_end_monotonic_ns=(
            end.recording_end_monotonic_ns if stop_matches and timing_valid else None
        ),
        final_received_frame_count=received if accounting_complete else None,
        accounting_complete=accounting_complete,
        recorded_frame_count=submitted,
        on_outcome=pulses.on_outcome,
        on_dispatched_monotonic_ns=pulses.on_dispatched_monotonic_ns,
        on_acknowledged_monotonic_ns=pulses.on_acknowledged_monotonic_ns,
        off_outcome=pulses.off_outcome,
        off_dispatched_monotonic_ns=pulses.off_dispatched_monotonic_ns,
        off_acknowledged_monotonic_ns=pulses.off_acknowledged_monotonic_ns,
        post_cutoff_accounting_complete=end.excluded_accounting_complete,
        excluded_frame_count=(
            end.excluded_frame_count if end.excluded_accounting_complete else None
        ),
        last_native_counter=(
            end.last_excluded_camera_counter if stop_matches else None
        ),
        transport_summary=completion.transport_summary,
        diagnostics=diagnostics.frame_log_groups(),
    )
    append_terminal_and_close(
        finalization,
        frame_log,
        video_sync,
        log_completion,
        deadline_ns=cleanup_deadline_ns,
        clock_ns=clock_ns,
    )
    finalization.late |= clock_ns() > original_deadline_ns
    if (
        success_evidence
        and exit_code == 0
        and (submitted == 0 or encoder.negotiated)
        and not finalization.late
        and not finalization.completion_failed
        and encoder.reader_error is None
    ):
        return successful_outputs(
            schedule,
            video_path,
            frame_log_path,
            recorded_frames=submitted,
            encoder=encoder,
            video_identity=current_video_identity or video_identity,
            stat_identity=stat_identity,
        ), video_sync
    return failed_outputs(
        schedule,
        video_path,
        frame_log_path,
        encoder=encoder,
        video_identity=current_video_identity or video_identity,
        stat_identity=stat_identity,
        completion_failed=finalization.completion_failed,
    ), video_sync
