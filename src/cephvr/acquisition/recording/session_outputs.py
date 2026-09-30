"""Map recording closure evidence onto the exact scheduled output obligations."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from cephvr.acquisition.recording.session_contracts import (
    EncoderProcess,
    RecordingFailure,
)
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control


def successful_outputs(
    schedule: acq.WorkerSchedule,
    video_path: Path,
    frame_log_path: Path,
    *,
    recorded_frames: int,
    encoder: EncoderProcess,
    video_identity: object | None,
    stat_identity: Callable[[Path], object | None],
) -> list[control.OutputResult]:
    if encoder.exit_code != 0:
        raise RecordingFailure("successful closure requires encoder exit zero")
    video_content = (
        control.CAMERA_VIDEO_CONTENT_FRAMES_SUBMITTED
        if recorded_frames
        else control.CAMERA_VIDEO_CONTENT_NO_FRAMES
    )
    current_identity = stat_identity(video_path)
    if video_identity is not None and current_identity == video_identity:
        video_result = output_result(
            schedule,
            video_path,
            control.OUTPUT_CLOSURE_CLOSED,
            True,
            video_content,
        )
    else:
        if (
            recorded_frames
            or encoder.created_output
            or encoder.output_identity() is not None
            or current_identity is not None
        ):
            raise RecordingFailure("never-created video predicate is not established")
        video_result = output_result(
            schedule,
            video_path,
            control.OUTPUT_CLOSURE_NOT_STARTED,
            False,
            control.CAMERA_VIDEO_CONTENT_NO_FRAMES,
        )
    return [
        video_result,
        output_result(schedule, frame_log_path, control.OUTPUT_CLOSURE_CLOSED, True),
    ]


def failed_outputs(
    schedule: acq.WorkerSchedule,
    video_path: Path,
    frame_log_path: Path,
    *,
    encoder: EncoderProcess,
    video_identity: object | None,
    stat_identity: Callable[[Path], object | None],
    completion_failed: bool,
) -> list[control.OutputResult]:
    current_identity = stat_identity(video_path)
    if video_identity is not None and current_identity == video_identity:
        video = output_result(
            schedule,
            video_path,
            control.OUTPUT_CLOSURE_FAILED
            if encoder.exit_code not in (None, 0)
            else control.OUTPUT_CLOSURE_UNCONFIRMED,
            True,
        )
    else:
        video = output_result(
            schedule, video_path, control.OUTPUT_CLOSURE_UNCONFIRMED, False
        )
    return [
        video,
        output_result(
            schedule,
            frame_log_path,
            control.OUTPUT_CLOSURE_FAILED
            if completion_failed
            else control.OUTPUT_CLOSURE_CLOSED,
            True,
        ),
    ]


def output_result(
    schedule: acq.WorkerSchedule,
    path: Path,
    closure: control.OutputClosure,
    present: bool,
    content: control.CameraVideoContent = control.CAMERA_VIDEO_CONTENT_UNSPECIFIED,
) -> control.OutputResult:
    matching = next(
        (plan for plan in schedule.outputs if Path(plan.path) == path), None
    )
    if matching is None:
        raise RecordingFailure("output path is not part of retained WorkerSchedule")
    return control.OutputResult(
        output_key=matching.output_key,
        path=str(path),
        closure=closure,
        artifact_present=present,
        camera_video_content=content,
    )
