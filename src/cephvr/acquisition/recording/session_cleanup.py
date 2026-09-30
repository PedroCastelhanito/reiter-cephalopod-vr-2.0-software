"""Failure and pre-T cleanup of exact recording resources (A07/A08)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from cephvr.acquisition.recording.frame_log import FrameLogWriter
from cephvr.acquisition.recording.session_contracts import (
    EncoderProcess,
    PixelBufferPool,
    RecordingFailure,
    RecordingQueue,
    VideoSync,
)
from cephvr.acquisition.recording.session_finalizer import (
    FinalizationProgress,
    close_encoder_and_sync_video,
)
from cephvr.acquisition.recording.session_outputs import output_result
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control


def drain_pending(queue: RecordingQueue, pool: PixelBufferPool) -> None:
    """Return every admitted payload while retaining incomplete frame accounting."""
    while True:
        entry = queue.dequeue(0.0)
        if entry is None:
            return
        recycled = queue.complete(entry.record)
        if recycled is not None:
            pool.release(recycled)


def close_failed_recording(
    schedule: acq.WorkerSchedule,
    video_path: Path,
    frame_log_path: Path,
    *,
    queue: RecordingQueue,
    pool: PixelBufferPool,
    encoder: EncoderProcess,
    frame_log: FrameLogWriter | None,
    video_sync: VideoSync | None,
    finalization: FinalizationProgress,
    submitted: int,
    observe_video: Callable[[], VideoSync | None],
    stat_identity: Callable[[Path], object | None],
    clock_ns: Callable[[], int],
    deadline_ns: int,
) -> tuple[list[control.OutputResult], VideoSync | None]:
    """Close known resources without writing a misleading normal completion row."""
    drain_pending(queue, pool)
    finalization.completion_failed = True
    _, video_sync = close_encoder_and_sync_video(
        finalization,
        encoder,
        video_sync,
        deadline_ns=deadline_ns,
        clock_ns=clock_ns,
        observe_video=observe_video,
    )
    if frame_log is not None and not finalization.frame_log_closed:
        frame_log.close_failed()
        finalization.frame_log_closed = True
    if video_sync is not None and not finalization.video_closed:
        video_sync.close()
        finalization.video_closed = True
    if not encoder.cleanup_complete:
        raise RecordingFailure("failed cleanup retains encoder resources")
    if frame_log is not None and not finalization.frame_log_closed:
        raise RecordingFailure("failed cleanup retains frame-log resources")
    if video_sync is not None and not finalization.video_closed:
        raise RecordingFailure("failed cleanup retains video-sync resources")

    current = stat_identity(video_path)
    owned_identity = video_sync.file_identity if video_sync is not None else None
    if current is None and owned_identity is None and not encoder.created_output:
        video = output_result(
            schedule,
            video_path,
            control.OUTPUT_CLOSURE_NOT_STARTED,
            False,
            control.CAMERA_VIDEO_CONTENT_NO_FRAMES,
        )
    elif owned_identity is not None and current == owned_identity:
        video = output_result(
            schedule,
            video_path,
            (
                control.OUTPUT_CLOSURE_FAILED
                if encoder.exit_code not in (None, 0)
                else control.OUTPUT_CLOSURE_UNCONFIRMED
            ),
            True,
            (
                control.CAMERA_VIDEO_CONTENT_FRAMES_SUBMITTED
                if submitted
                else control.CAMERA_VIDEO_CONTENT_NO_FRAMES
            ),
        )
    else:
        video = output_result(
            schedule,
            video_path,
            control.OUTPUT_CLOSURE_UNCONFIRMED,
            current is not None,
        )
    log = output_result(
        schedule,
        frame_log_path,
        (
            control.OUTPUT_CLOSURE_FAILED
            if frame_log is not None
            else control.OUTPUT_CLOSURE_NOT_STARTED
        ),
        frame_log is not None,
    )
    return [video, log], video_sync


def unlaunched_outputs(
    schedule: acq.WorkerSchedule,
    video_path: Path,
    frame_log_path: Path,
    *,
    stat_identity: Callable[[Path], object | None],
) -> list[control.OutputResult]:
    """Classify outputs after exact helper cleanup when no process was returned."""
    results = []
    for path in (video_path, frame_log_path):
        present = stat_identity(path) is not None
        results.append(
            output_result(
                schedule,
                path,
                (
                    control.OUTPUT_CLOSURE_UNCONFIRMED
                    if present
                    else control.OUTPUT_CLOSURE_NOT_STARTED
                ),
                present,
            )
        )
    return results


def cancel_before_start(
    schedule: acq.WorkerSchedule | None,
    video_path: Path | None,
    frame_log_path: Path | None,
    *,
    encoder: EncoderProcess | None,
    video_sync: VideoSync | None,
    observe_video: Callable[[], VideoSync | None],
    stat_identity: Callable[[Path], object | None],
    delete_created_video: Callable[[Path, object, int], bool],
    deadline_ns: int,
) -> tuple[list[control.OutputResult], VideoSync | None]:
    """Delete only the exact positively observed pre-T FFmpeg-created video."""
    creation_identity: object | None = None
    results: list[control.OutputResult] = []
    if encoder is not None:
        encoder.terminate(deadline_ns=deadline_ns)
        creation_identity = encoder.output_creation_identity
        video_sync = observe_video()
    if video_sync is not None:
        video_sync.close()
        video_sync = None
    if video_path is not None:
        if schedule is None:
            raise RecordingFailure("video output lacks its retained schedule")
        current = stat_identity(video_path)
        deleted = False
        if (
            current is not None
            and creation_identity is not None
            and current == creation_identity
        ):
            deleted = delete_created_video(video_path, creation_identity, deadline_ns)
        if current is not None and not deleted:
            results.append(
                output_result(
                    schedule,
                    video_path,
                    control.OUTPUT_CLOSURE_UNCONFIRMED,
                    True,
                )
            )
        else:
            results.append(
                output_result(
                    schedule,
                    video_path,
                    control.OUTPUT_CLOSURE_NOT_STARTED,
                    False,
                )
            )
    if frame_log_path is not None:
        if schedule is None:
            raise RecordingFailure("frame-log output lacks its retained schedule")
        if frame_log_path.exists():
            raise RecordingFailure("pre-T frame log exists unexpectedly; preserving it")
        results.append(
            output_result(
                schedule,
                frame_log_path,
                control.OUTPUT_CLOSURE_NOT_STARTED,
                False,
            )
        )
    return results, video_sync
