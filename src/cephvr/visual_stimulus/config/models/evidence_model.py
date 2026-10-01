"""V12/V13/V28 typed evidence-line declarations; no writer or replay implementation.

Each `_stimulus_frames.jsonl` line is one EvidenceRecord. Cross-line/recipe validation
is specified in evidence-format.md. Structure alone cannot establish reference
integrity, complete replay coverage or file closure.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .schema_common import (
    NS,
    U32,
    U64,
    Digest,
    FrameId,
    Model,
    OutputId,
    SwapInterval,
    UnitQuaternion,
    Version1,
    parse_json,
    portable_path,
)
from .schema_common import Name as Id
from .schema_common import PositiveInt as Pos


class Identity(Model):
    session_id: Id
    trial_id: Id
    configuration_revision: U64
    prepared_generation: Id
    renderer_generation: Id
    resource_generation: Id


class ArtifactRef(Model):
    relative_path: str
    sha256: Digest
    byte_length: U64
    schema_id: Id

    @model_validator(mode="after")
    def portable_path(self) -> Self:
        portable_path(self.relative_path)
        return self


class UniformLayout(Model):
    binding_id: Id
    instance_id: Id | None  # None for output/global bindings.
    output_id: OutputId | None  # None for state shared by outputs.
    shader_resource_id: Id
    name: Id
    scalar_type: Literal["float32", "float64", "int32", "uint32"]
    shape: tuple[Pos, ...]  # Empty shape denotes one scalar; GLSL matrix column order.


class UniformValue(Model):
    binding_id: Id
    words: tuple[U32, ...]  # Exact bits consumed by GPU, low word first for float64.


class MediaSelection(Model):
    instance_id: Id
    asset_id: Id
    stream_index: U32
    source_frame_index: U64
    source_pts: int
    time_base_numerator: Pos
    time_base_denominator: Pos
    playback_generation: U64
    loop_index: U64
    target_media_numerator: int
    target_media_denominator: Pos
    disposition: Literal["current", "starvation_hold", "clip_end_hold"]


class Pose(Model):
    instance_id: Id
    frame_id: FrameId
    position_mm: tuple[float, float, float]
    orientation_xyzw: UnitQuaternion


class Header(Model):
    kind: Literal["header"]
    format_version: Version1
    identity: Identity
    writer_generation: Id
    recipe: (
        ArtifactRef  # The always-retained _stimulus_LOG.json; no separate recipe file.
    )
    trial_start_host_ns: NS
    required_output_ids: Annotated[tuple[OutputId, ...], Field(min_length=1)]
    renderer_compatibility: Id

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len(set(self.required_output_ids)) != len(self.required_output_ids):
            raise ValueError("duplicate output")
        return self


class State(Model):
    epoch_occurrence: U32
    scene_id: Id
    evaluation_host_ns: NS
    active_instance_ids: tuple[Id, ...]
    uniforms: tuple[UniformValue, ...]
    media: tuple[MediaSelection, ...]
    effective_poses: tuple[Pose, ...]


class Submission(Model):
    output_id: OutputId
    attempt_index: U64 | None
    # cutoff_excluded: this output's view of an in-flight group was abandoned, never
    # submitted, because the trial cutoff arrived first (evidence-format.md).
    phase: Literal["attempt", "returned", "failed", "unknown", "cutoff_excluded"]
    entry_host_ns: NS | None
    return_host_ns: NS | None
    swap_interval: SwapInterval
    marker_index: U64 | None
    marker_high: bool | None
    failure_code: str | None

    @model_validator(mode="after")
    def outcome(self) -> Self:
        if self.phase == "cutoff_excluded":
            if self.entry_host_ns is not None or self.attempt_index is not None:
                raise ValueError(
                    "unsubmitted output has no entry time or attempt index"
                )
        elif self.entry_host_ns is None or self.attempt_index is None:
            raise ValueError(
                "submission observation requires entry time and attempt index"
            )
        if self.phase == "returned" and self.return_host_ns is None:
            raise ValueError("returned requires return time")
        if self.return_host_ns is not None and (
            self.entry_host_ns is None or self.return_host_ns < self.entry_host_ns
        ):
            raise ValueError("return before entry")
        if self.phase == "attempt" and (
            self.return_host_ns is not None or self.failure_code is not None
        ):
            raise ValueError("attempt cannot contain outcome")
        if self.phase == "failed" and not self.failure_code:
            raise ValueError("failed requires a failure code")
        if self.phase == "unknown" and self.return_host_ns is not None:
            raise ValueError("unknown cannot carry a return time")
        if self.phase == "cutoff_excluded" and (
            self.return_host_ns is not None
            or self.failure_code is not None
            or self.marker_index is not None
        ):
            raise ValueError("cutoff-excluded output was never submitted")
        if (self.marker_index is None) != (self.marker_high is None):
            raise ValueError("marker identity/value must be paired")
        return self


class Capture(
    Model
):  # One tiled review composite per group (E13); tiles map via the recipe layout.
    disposition: Literal[
        "admitted",
        "capacity_drop",
        "cutoff_excluded",
        "transfer_complete",
        "transfer_failed",
        "input_submitted",
        "unknown",
    ]
    # E13: n-th admitted render group is review-video frame n (zero-based); None if not admitted.
    video_frame_index: U64 | None
    source_pixel_format: Id
    encoder_pixel_format: Id | None
    failure_code: str | None


class FeedbackEvidence(Model):
    kind: Literal["feedback"]
    stream_id: Id
    result_id: Id
    reset_generation: Id
    binding_id: Id | None
    group_id: U64 | None
    source_frame_ids: tuple[Id, ...]  # Every contributing source frame ID.
    source_receipt_ns: NS  # Newest contributing frame's host receipt.
    application_check_ns: NS
    age_limit_ns: Annotated[int, Field(gt=0, le=(1 << 63) - 1)] | None
    disposition: Literal[
        "applied",
        "invalid",
        "stale",
        "old_generation",
        "absent",
        "wrong_trial",
        "baseline_only",
    ]
    requested_increment: tuple[float, ...]
    applied_increment: tuple[float, ...]
    target_units: tuple[str, ...]
    target_frame_id: FrameId | None

    @model_validator(mode="after")
    def application(self) -> Self:
        if self.disposition in ("applied", "stale"):
            if self.age_limit_ns is None or not self.source_frame_ids:
                raise ValueError(
                    "freshness decision requires age limit and source frames"
                )
            age = self.application_check_ns - self.source_receipt_ns
            if age < 0:
                raise ValueError("application check precedes source receipt")
            if (age > self.age_limit_ns) != (self.disposition == "stale"):
                raise ValueError("feedback disposition disagrees with source age")
            if self.disposition == "stale" and any(self.applied_increment):
                raise ValueError(
                    "stale feedback cannot contribute an applied increment"
                )
        if self.disposition == "applied":
            if self.group_id is None or self.binding_id is None:
                raise ValueError("applied feedback requires group and binding identity")
            if not self.source_frame_ids:
                raise ValueError("applied feedback requires its source frames")
            if self.application_check_ns < self.source_receipt_ns:
                raise ValueError("application check precedes source receipt")
        return self


class RenderGroup(Model):
    kind: Literal["render_group"]
    group_id: U64
    state: State
    submissions: tuple[Submission, ...]
    captures: tuple[Capture, ...]


class GroupUpdate(Model):
    kind: Literal["group_update"]
    group_id: U64
    submissions: tuple[Submission, ...]
    captures: tuple[Capture, ...]

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if not self.submissions and not self.captures:
            raise ValueError("empty group update")
        return self


class Interval(Model):
    kind: Literal["interval"]
    interval_id: Id
    phase: Literal["begin", "end"]
    category: Literal[
        "epoch_without_submission",
        "starvation",
        "feedback_hold",
        "clipping",
        "arena_constraint",
    ]
    instance_id: Id | None
    output_id: OutputId | None
    occurrence_index: U32 | None
    observation_host_ns: NS
    reason: str


class Clipping(Model):
    kind: Literal["clipping"]
    group_id: U64
    output_id: OutputId
    occurrence_index: U32
    observation_host_ns: NS
    stages: tuple[Literal["alpha", "linear_output", "device_code"], ...]

    @model_validator(mode="after")
    def unique_stages(self) -> Self:
        if len(set(self.stages)) != len(self.stages):
            raise ValueError("clipping stages must be unique")
        return self


class EncoderOutcome(Model):  # One final account for the single composite encoder.
    kind: Literal["encoder_outcome"]
    admitted_count: U64
    input_submitted_count: U64
    capacity_drop_count: U64
    final_input_group_id: U64 | None
    cutoff_host_ns: NS | None
    exit_code: int | None
    eof_sent: bool | None
    drain_confirmed: bool | None
    # Closure evidence stays in E06's independent output reports after file close.


class Completion(Model):  # The closing line; its absence makes replay partial (V13).
    kind: Literal["completion"]
    cutoff_host_ns: NS
    last_group_id: U64 | None
    state_count: U64
    submission_attempt_count: U64
    capture_admission_count: U64
    capture_drop_count: U64
    unresolved_attempt_count: U64
    outcome: Literal[
        "completed", "interrupted"
    ]  # Same values as SESSION_LOG trial outcomes.


Record = Annotated[
    Header
    | RenderGroup
    | GroupUpdate
    | FeedbackEvidence
    | Interval
    | Clipping
    | EncoderOutcome
    | Completion,
    Field(discriminator="kind"),
]


class EvidenceRecord(Model):  # One complete UTF-8 JSON line; no framing or checksum.
    payload: Record


class GroupRange(Model):
    first: U64
    end_exclusive: U64

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end_exclusive <= self.first:
            raise ValueError("empty/reversed range")
        return self


class Coverage(Model):
    output_id: OutputId
    reconstructable: tuple[GroupRange, ...]
    failed_submission: tuple[GroupRange, ...]
    unknown_submission: tuple[GroupRange, ...]
    diagnostic_coverage: tuple[GroupRange, ...]
    missing_diagnostic_coverage: tuple[GroupRange, ...]


class ReplayRequest(Model):
    evidence_path: str
    session_root: str
    expected_identity: Identity
    max_line_bytes: Pos
    asset_root: str
    explicit_asset_map: tuple[tuple[Id, str], ...]
    mode: Literal["full", "partial"]  # Full requires the closing Completion line.
    export_directory: str
    output_ids: Annotated[tuple[OutputId, ...], Field(min_length=1)]


class ReplayReport(Model):
    identity: Identity
    mode: Literal["full", "partial"]
    evidence_complete: bool  # Closing Completion line present and valid.
    last_group_id: U64 | None  # Partial label: "partial, up to render group N".
    input_state_validation: Literal["passed", "failed"]
    original_pixel_equality: Literal["unverified"]
    optical_presentation: Literal["unverified"]
    compatibility_differences: tuple[str, ...]
    coverage: tuple[Coverage, ...]
    created_files: tuple[str, ...]

    @model_validator(mode="after")
    def full_requires_closing_line(self) -> Self:
        if self.mode == "full" and not self.evidence_complete:
            raise ValueError("full-trial replay requires a complete evidence file")
        return self


class ExportImage(Model):
    relative_path: str
    output_id: OutputId
    group_id: U64
    attempt_index: U64
    state_evaluation_host_ns: NS
    submission_entry_host_ns: NS
    submission_return_host_ns: NS
    width: Pos
    height: Pos
    code_bits: Literal[8, 10]
    png_storage_bits: Literal[8, 16]


class ExportIndex(Model):
    format_version: Version1
    report: ReplayReport
    images: tuple[ExportImage, ...]


def parse_evidence_json(source: str, *, max_bytes: int) -> EvidenceRecord:
    return parse_json(EvidenceRecord, source, max_bytes=max_bytes, max_depth=32)
