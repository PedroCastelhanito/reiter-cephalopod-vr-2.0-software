"""Exact recording-output closure projections from retained online evidence."""

from __future__ import annotations

from pathlib import Path

from cephvr.control.v1 import types_pb2 as pb
from cephvr.visual_stimulus.recording.capture import RecordingCounts
from cephvr.visual_stimulus.recording.completion import resolve_video_completion
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus


def closed_results(
    schedule: visual_stimulus.WorkerSchedule,
    counts: RecordingCounts,
    *,
    evidence_closed: bool,
    cutoff_known: bool,
    encoder_cleanup_confirmed: bool,
    encoder_exit: int | None,
    video_sync_closed: bool,
    artifact_present: bool | None,
    artifact_created_by_session: bool | None,
) -> tuple[pb.OutputResult, ...]:
    outputs = {item.output_tag: item for item in schedule.outputs}
    completion = resolve_video_completion(
        counts,
        final_cutoff_known=cutoff_known,
        every_eligible_group_resolved=counts.unresolved_capture_count == 0,
        no_partial_input_write=True,
        encoder_cleanup_confirmed=encoder_cleanup_confirmed,
        encoder_finalized=encoder_exit == 0,
        file_sync_and_close_confirmed=video_sync_closed,
        artifact_present=artifact_present,
        artifact_created_by_session=artifact_created_by_session,
        reserved_path_absent_after_cleanup=artifact_present is False,
    )
    video = pb.OutputResult(
        output_key=outputs["stimulus"].output_key,
        path=outputs["stimulus"].path,
        closure={
            "CLOSED": pb.OUTPUT_CLOSURE_CLOSED,
            "NOT_STARTED": pb.OUTPUT_CLOSURE_NOT_STARTED,
        }.get(completion.closure, pb.OUTPUT_CLOSURE_UNCONFIRMED),
        visual_stimulus_review_video_content={
            "NO_FRAMES": pb.VISUAL_STIMULUS_REVIEW_VIDEO_CONTENT_NO_FRAMES,
            "FRAMES_SUBMITTED": pb.VISUAL_STIMULUS_REVIEW_VIDEO_CONTENT_FRAMES_SUBMITTED,
        }.get(completion.content, pb.VISUAL_STIMULUS_REVIEW_VIDEO_CONTENT_UNKNOWN),
    )
    if completion.artifact_present is not None:
        video.artifact_present = completion.artifact_present
    if completion.warning:
        video.failure.message = completion.warning
    frames = pb.OutputResult(
        output_key=outputs["stimulus_frames"].output_key,
        path=outputs["stimulus_frames"].path,
        closure=pb.OUTPUT_CLOSURE_CLOSED
        if evidence_closed
        else pb.OUTPUT_CLOSURE_UNCONFIRMED,
        artifact_present=evidence_closed,
    )
    return video, frames


def failed_results(
    schedule: visual_stimulus.WorkerSchedule | None, message: str
) -> tuple[pb.OutputResult, ...]:
    if schedule is None:
        return ()
    return tuple(
        pb.OutputResult(
            output_key=item.output_key,
            path=item.path,
            closure=pb.OUTPUT_CLOSURE_FAILED,
            failure=pb.Failure(
                code="VISUAL_STIMULUS_RECORDING", message=message[:2048]
            ),
        )
        for item in schedule.outputs
        if item.output_tag in {"stimulus", "stimulus_frames"}
    )


def not_started_results(
    schedule: visual_stimulus.WorkerSchedule | None,
) -> tuple[pb.OutputResult, ...]:
    if schedule is None:
        return ()
    return tuple(
        pb.OutputResult(
            output_key=item.output_key,
            path=item.path,
            closure=pb.OUTPUT_CLOSURE_NOT_STARTED,
            artifact_present=False,
        )
        for item in schedule.outputs
        if item.output_tag in {"stimulus", "stimulus_frames"}
    )


def uncertain_pre_header_results(
    schedule: visual_stimulus.WorkerSchedule | None,
    video_path: Path | None,
    evidence_path: Path | None,
) -> tuple[pb.OutputResult, ...]:
    if schedule is None or video_path is None or evidence_path is None:
        return ()
    outputs = {item.output_tag: item for item in schedule.outputs}
    return tuple(
        pb.OutputResult(
            output_key=outputs[tag].output_key,
            path=outputs[tag].path,
            closure=pb.OUTPUT_CLOSURE_UNCONFIRMED,
            artifact_present=Path(outputs[tag].path).exists(),
            failure=pb.Failure(
                code="VISUAL_STIMULUS_PRE_ONSET_CLEANUP",
                message="pre-onset cancellation could not prove output absence",
            ),
        )
        for tag in ("stimulus", "stimulus_frames")
    )
