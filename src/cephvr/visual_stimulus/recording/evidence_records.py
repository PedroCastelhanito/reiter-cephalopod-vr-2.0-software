"""Recording-thread construction of canonical, immutable evidence records."""

from __future__ import annotations

from dataclasses import asdict
from typing import Literal, cast

from cephvr.visual_stimulus.config.models.evidence_model import (
    Capture,
    Clipping,
    FeedbackEvidence,
    GroupUpdate,
    Interval,
    MediaSelection,
    Pose,
    RenderGroup,
    State,
    Submission,
    UniformValue,
)
from cephvr.visual_stimulus.rendering.types import (
    DiagnosticSnapshot,
    EvidenceStateSnapshot,
    FeedbackEvidenceSnapshot,
    SubmissionSnapshot,
)

CaptureDisposition = Literal[
    "admitted",
    "capacity_drop",
    "same_slot_omission",
    "cutoff_excluded",
    "transfer_complete",
    "transfer_failed",
    "input_submitted",
    "leading_duplicate",
    "interior_duplicate",
    "trailing_duplicate",
    "unknown",
]


def build_render_group_record(
    group_id: int,
    state: EvidenceStateSnapshot,
    submissions: tuple[SubmissionSnapshot, ...],
    capture_values: tuple[tuple[CaptureDisposition, int | None, str | None], ...],
    source_format: str,
    encoder_format: str,
) -> RenderGroup:
    canonical_state = State(
        epoch_occurrence=state.epoch_occurrence,
        scene_id=state.scene_id,
        evaluation_host_ns=state.evaluation_host_ns,
        active_instance_ids=state.active_instance_ids,
        uniforms=tuple(
            UniformValue(binding_id=x.binding_id, words=x.words) for x in state.uniforms
        ),
        media=tuple(MediaSelection(**asdict(x)) for x in state.media),
        effective_poses=tuple(Pose(**asdict(x)) for x in state.effective_poses),
    )
    canonical_submissions = tuple(Submission(**asdict(x)) for x in submissions)
    return RenderGroup(
        kind="render_group",
        group_id=group_id,
        state=canonical_state,
        submissions=canonical_submissions,
        captures=tuple(
            Capture(
                disposition=disposition,
                video_frame_index=frame_index,
                source_pixel_format=source_format,
                encoder_pixel_format=encoder_format,
                failure_code=failure,
            )
            for disposition, frame_index, failure in capture_values
        ),
    )


def build_capture_update(
    group_id: int,
    disposition: CaptureDisposition,
    frame_index: int | None,
    failure: str | None,
    source_format: str,
    encoder_format: str,
) -> GroupUpdate:
    return GroupUpdate(
        kind="group_update",
        group_id=group_id,
        submissions=(),
        captures=(
            Capture(
                disposition=disposition,
                video_frame_index=frame_index,
                source_pixel_format=source_format,
                encoder_pixel_format=encoder_format,
                failure_code=failure,
            ),
        ),
    )


def build_clipping_record(snapshot: DiagnosticSnapshot) -> Clipping:
    return Clipping(
        kind="clipping",
        group_id=snapshot.group_id,
        output_id=snapshot.output_id,
        occurrence_index=snapshot.epoch_index,
        observation_host_ns=snapshot.evaluation_host_ns,
        stages=cast(
            tuple[Literal["alpha", "linear_output", "device_code"], ...],
            snapshot.stages,
        ),
    )


def build_feedback_record(snapshot: FeedbackEvidenceSnapshot) -> FeedbackEvidence:
    return FeedbackEvidence(
        kind="feedback",
        stream_id=snapshot.stream_id,
        result_id=snapshot.result_id,
        reset_generation=snapshot.reset_generation,
        binding_id=snapshot.binding_id,
        group_id=snapshot.group_id,
        source_frame_ids=snapshot.source_frame_ids,
        source_receipt_ns=snapshot.source_receipt_ns,
        application_check_ns=snapshot.application_check_ns,
        age_limit_ns=snapshot.age_limit_ns,
        disposition=snapshot.disposition,
        requested_increment=snapshot.requested_increment,
        applied_increment=snapshot.applied_increment,
        target_units=snapshot.target_units,
        target_frame_id=snapshot.target_frame_id,
    )


def build_feedback_interval(
    interval_id: str,
    phase: Literal["begin", "end"],
    category: Literal["feedback_hold", "arena_constraint"],
    snapshot: FeedbackEvidenceSnapshot,
    observation_host_ns: int,
    reason: str,
) -> Interval:
    return Interval(
        kind="interval",
        interval_id=interval_id,
        phase=phase,
        category=category,
        instance_id=None,
        output_id=None,
        occurrence_index=None,
        observation_host_ns=observation_host_ns,
        reason=reason,
    )
