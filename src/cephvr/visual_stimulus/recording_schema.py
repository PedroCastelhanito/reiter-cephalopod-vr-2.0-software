"""Lightweight experiment-output schemas and shared analysis contract exports."""

from cephvr.controller.planning import WriterSchema, WriterSchemaKey
from cephvr.visual_stimulus.config.models.evidence_model import (  # noqa: F401
    ArtifactRef,
    Capture,
    Completion,
    Coverage,
    EncoderOutcome,
    EvidenceRecord,
    ExportImage,
    ExportIndex,
    FeedbackEvidence,
    GroupRange,
    GroupUpdate,
    Header,
    Identity,
    Interval,
    MediaSelection,
    Pose,
    RenderGroup,
    ReplayReport,
    ReplayRequest,
    State,
    Submission,
    UniformLayout,
    UniformValue,
    parse_evidence_json,
)


def get_writer_schemas() -> dict[WriterSchemaKey, WriterSchema]:
    """Return the schemas emitted by the canonical Visual Stimulus evidence writer."""
    recipe = WriterSchema(
        schema_version=2,
        format="json",
        fields={
            "document": "cephvr.visual_stimulus.prepared_trial.v2 canonical PreparedTrial",
            "format_version": "2",
            "identity": "exact session/trial/configuration/prepared generations",
            "source": "canonical source Program and source_sha256",
            "epochs": "resolved ordered stimulus presentations",
            "manifest": "immutable resource identities and interpretation",
        },
        units={"epoch_boundaries": "trial-relative nanoseconds"},
        clocks={
            "presentation": "trial-relative schedule; host onset retained in trial LOG"
        },
    )
    evidence = WriterSchema(
        schema_version=1,
        format="jsonl",
        fields={
            "line": "EvidenceRecord(payload: Header|RenderGroup|GroupUpdate|FeedbackEvidence|Interval|EncoderOutcome|Completion)",
            "group_id": "monotonic render-group identity; admitted video frame index is independent",
            "submission": "per-output attempt/return/failure/unknown/cutoff_excluded observation",
            "capture": "per-group tiled-composite admission and encoder-input outcome",
        },
        units={
            "host_time": "host monotonic ns",
            "source_pts": "media stream time-base ticks",
        },
        clocks={
            "host": "cephvr.host.perf_counter_ns.v1",
            "video": "n-th admitted render group",
        },
    )
    video = WriterSchema(
        schema_version=1,
        format="mp4",
        fields={
            "review_composite": "one tiled lossy review stream; no original-pixel guarantee",
            "frame_correspondence": "video frame n is the n-th admitted render group",
            "fragmentation": "fragmented MP4; no hybrid conversion or remux",
        },
        units={"frame_rate": "photodiode output refresh rate"},
        clocks={
            "presentation": "cephvr.host.perf_counter_ns.v1; constant-rate encoder timeline"
        },
    )
    return {
        ("visual_stimulus", "stimulus_LOG", "json"): recipe,
        ("visual_stimulus", "stimulus_frames", "jsonl"): evidence,
        ("visual_stimulus", "stimulus", "mp4"): video,
    }


__all__ = [name for name in globals() if not name.startswith("_")]
