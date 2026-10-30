"""Version-gated readers for per-trial backend files (A07 camera, V12 stimulus, T19 tracking).

Each reader returns a ``Stream``: compact column tables plus the header/closing
line kept as JSON. Field names follow the writers' schemas; unknown versions fail.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from .jsonl import JsonlFile
from .tables import JSON, Table, build

CAMERA_VERSIONS = (5, 6)
STIMULUS_FORMATS = (6,)
TRACKING_VERSIONS = (3,)


@dataclass
class Stream:
    path: Path
    version: int
    header: JSON
    completion: JSON | None = None
    tables: dict[str, Table] = field(default_factory=dict)
    summaries: dict[str, JSON] = field(default_factory=dict)
    truncated: bool = False

    @property
    def partial(self) -> bool:
        return self.truncated or self.completion is None


def _open(
    path: Path, unwrap: str | None, version_key: str, supported: tuple[int, ...]
) -> tuple[Stream, JsonlFile, Iterator[JSON]]:
    """Read and version-check the header line; the iterator continues after it."""
    lines = JsonlFile(path)
    iterator = iter(lines)
    first = next(iterator, None) or {}
    record = first.get(unwrap) if unwrap else first
    if (
        not isinstance(record, dict)
        or record.get("kind", record.get("type")) != "header"
    ):
        raise ValueError(f"{Path(path).name}: first line is not a header")
    version = record.get(version_key)
    if version not in supported:
        raise ValueError(f"{Path(path).name}: unsupported {version_key} {version}")
    return Stream(Path(path), int(version), record), lines, iterator


CAMERA_FRAME = {
    "frame_id": ("frame_id", "i8"),
    "host_receipt_ns": ("host_receipt_ns", "i8"),
    "dropped": ("dropped", "b"),
    "video_frame": ("video_frame", "i8"),
    "video_disposition": ("video_disposition", "str"),
    "camera_frame_counter": ("camera_frame_counter", "i8"),
    "camera_timestamp_ns": ("camera_timestamp_ns", "i8"),
    "invalid_code": ("invalid_code", "str"),
}
CAMERA_VIDEO = {
    "encoded_frame_index": ("encoded_frame_index", "i8"),
    "source_frame_id": ("source_frame_id", "i8"),
    "source_host_receipt_ns": ("source_host_receipt_ns", "i8"),
    "disposition": ("disposition", "str"),
}


def read_camera(path: Path) -> Stream:
    stream, lines, iterator = _open(path, None, "schema_version", CAMERA_VERSIONS)
    rows: dict[str, list[JSON]] = {"frame": [], "video_frame": []}
    for line in iterator:
        kind = line.get("type")
        if kind == "completion":
            stream.completion = line
        elif kind in rows:
            rows[kind].append(line)
    stream.truncated = lines.truncated
    stream.tables["frames"] = build(rows["frame"], CAMERA_FRAME)
    stream.tables["video_map"] = build(rows["video_frame"], CAMERA_VIDEO)
    return stream


SUBMISSION = {
    "group_id": ("group_id", "i8"),
    "group_update": ("group_update", "b"),
    "output_id": ("output_id", "str"),
    "attempt_index": ("attempt_index", "i8"),
    "phase": ("phase", "str"),
    "entry_host_ns": ("entry_host_ns", "i8"),
    "return_host_ns": ("return_host_ns", "i8"),
    "swap_interval": ("swap_interval", "i8"),
    "marker_index": ("marker_index", "i8"),
    "marker_high": ("marker_high", "b"),
    "failure_code": ("failure_code", "str"),
}
CAPTURE = {
    "group_id": ("group_id", "i8"),
    "group_update": ("group_update", "b"),
    "disposition": ("disposition", "str"),
    "video_frame_index": ("video_frame_index", "i8"),
    "failure_code": ("failure_code", "str"),
}
STIMULUS_SPECS = {
    "render_groups": {
        "group_id": ("group_id", "i8"),
        "epoch_occurrence": ("state.epoch_occurrence", "i8"),
        "scene_id": ("state.scene_id", "str"),
        "evaluation_host_ns": ("state.evaluation_host_ns", "i8"),
    },
    "submissions": SUBMISSION,
    "captures": CAPTURE,
    "image_selections": {
        "group_id": ("group_id", "i8"),
        "instance_id": ("instance_id", "str"),
        "requested_asset_id": ("requested_asset_id", "str"),
        "requested_image_index": ("requested_image_index", "i8"),
        "asset_id": ("asset_id", "str"),
        "image_index": ("image_index", "i8"),
        "disposition": ("disposition", "str"),
        "repeated": ("repeated", "b"),
        "pattern_sha256": ("pattern_sha256", "str"),
    },
    "feedback": {
        "stream_id": ("stream_id", "str"),
        "result_id": ("result_id", "str"),
        "reset_generation": ("reset_generation", "str"),
        "binding_id": ("binding_id", "str"),
        "group_id": ("group_id", "i8"),
        "source_frame_ids": ("source_frame_ids", "json"),
        "source_receipt_ns": ("source_receipt_ns", "i8"),
        "application_check_ns": ("application_check_ns", "i8"),
        "age_limit_ns": ("age_limit_ns", "i8"),
        "disposition": ("disposition", "str"),
    },
    "intervals": {
        "interval_id": ("interval_id", "str"),
        "phase": ("phase", "str"),
        "category": ("category", "str"),
        "instance_id": ("instance_id", "str"),
        "output_id": ("output_id", "str"),
        "occurrence_index": ("occurrence_index", "i8"),
        "observation_host_ns": ("observation_host_ns", "i8"),
        "reason": ("reason", "str"),
    },
    "clipping": {
        "group_id": ("group_id", "i8"),
        "output_id": ("output_id", "str"),
        "occurrence_index": ("occurrence_index", "i8"),
        "observation_host_ns": ("observation_host_ns", "i8"),
        "stages": ("stages", "json"),
    },
}
_STIMULUS_ROW_KIND = {"feedback": "feedback", "interval": "intervals"}


def read_stimulus(path: Path) -> Stream:
    """Keep compact timing tables only; uniforms, media and poses stay in the file (AN01)."""
    stream, lines, iterator = _open(path, "payload", "format_version", STIMULUS_FORMATS)
    rows: dict[str, list[JSON]] = {name: [] for name in STIMULUS_SPECS}
    for line in iterator:
        record = line.get("payload") or {}
        kind = record.get("kind")
        if kind in ("render_group", "group_update"):
            group = record["group_id"]
            if kind == "render_group":
                rows["render_groups"].append(record)
                for image in record["state"].get("images", ()):
                    rows["image_selections"].append({"group_id": group, **image})
            update = kind == "group_update"
            for item in record.get("submissions", ()):
                rows["submissions"].append(
                    {"group_id": group, "group_update": update, **item}
                )
            for item in record.get("captures", ()):
                rows["captures"].append(
                    {"group_id": group, "group_update": update, **item}
                )
        elif kind == "clipping":
            rows["clipping"].append(record)
        elif kind in _STIMULUS_ROW_KIND:
            rows[_STIMULUS_ROW_KIND[kind]].append(record)
        elif kind == "encoder_outcome":
            stream.summaries["encoder_outcome"] = record
        elif kind == "completion":
            stream.completion = record
    stream.truncated = lines.truncated
    stream.tables = {
        name: build(rows[name], spec) for name, spec in STIMULUS_SPECS.items()
    }
    return stream


TRACKING_SPECS = {
    "poses": {
        "observation_id": ("observation_id", "str"),
        "reset_generation": ("reset_generation", "str"),
        "source_frame_id": ("source.frame_id", "i8"),
        "source_host_receipt_ns": ("source.host_receipt_ns", "i8"),
        "completion_host_ns": ("completion_host_ns", "i8"),
        "method": ("method", "str"),
        "validity": ("validity", "str"),
        "reason": ("reason", "str"),
        "tip_x_px": ("landmarks.tip.x_px", "f8"),
        "tip_y_px": ("landmarks.tip.y_px", "f8"),
        "left_base_x_px": ("landmarks.left_base.x_px", "f8"),
        "left_base_y_px": ("landmarks.left_base.y_px", "f8"),
        "right_base_x_px": ("landmarks.right_base.x_px", "f8"),
        "right_base_y_px": ("landmarks.right_base.y_px", "f8"),
        "selected_score": ("selected_score", "f8"),
        "disposition": ("disposition", "str"),
    },
    "results": {
        "produced_host_ns": ("produced_host_ns", "i8"),
        "pose_disposition": ("pose.disposition", "str"),
        "pose_observation_id": ("pose.observation_id", "str"),
        "feedback_result": ("feedback_result", "json"),
    },
    "resets": {
        "reset_generation": ("reset_generation", "str"),
        "causes": ("causes", "json"),
        "observed_host_ns": ("observed_host_ns", "i8"),
    },
    "discards": {
        "reset_generation": ("reset_generation", "str"),
        "observed_host_ns": ("observed_host_ns", "i8"),
        "target": ("target", "str"),
        "ids": ("ids", "json"),
        "reason": ("reason", "str"),
    },
}
_TRACKING_KIND = {"pose": "poses", "result": "results", "reset": "resets"}
_TRACKING_KIND["discard"] = "discards"


def read_tracking(path: Path) -> Stream:
    stream, lines, iterator = _open(path, "record", "schema_version", TRACKING_VERSIONS)
    if stream.header.get("stream_kind") != "tracking":
        raise ValueError(f"{Path(path).name}: not a tracking record stream")
    rows: dict[str, list[JSON]] = {name: [] for name in TRACKING_SPECS}
    for line in iterator:
        record = line.get("record") or {}
        kind = record.get("kind")
        if kind == "completion":
            stream.completion = record
        elif kind in _TRACKING_KIND:
            rows[_TRACKING_KIND[kind]].append(record)
    stream.truncated = lines.truncated
    stream.tables = {
        name: build(rows[name], spec) for name, spec in TRACKING_SPECS.items()
    }
    return stream
