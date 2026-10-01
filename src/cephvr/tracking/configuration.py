"""Controller-facing Tracking configuration; no images, SDKs or devices are opened."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from google.protobuf.json_format import ParseDict

from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.config import ConfigurationError
from cephvr.shared.deadlines import duration_ns
from cephvr.tracking.config.files import load_files
from cephvr.tracking.config.models.methods import FileLimits
from cephvr.tracking.config.validation import validate_configuration
from cephvr.tracking.v1 import methods_pb2

__all__ = [
    "load_defaults",
    "load_file_policies",
    "resolve_settings",
    "validate_configuration",
]


def _plain(value: Any) -> Any:
    from decimal import Decimal

    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return float(value) if isinstance(value, Decimal) else value


def load_file_policies(root: Path) -> methods_pb2.TrackingFilePolicies:
    config = load_files(root).config
    limits = FileLimits.model_validate_json(
        json.dumps({"schema_version": 1, **_plain(config["limits"])})
    )
    age = duration_ns(config["frames"]["max_frame_age_ms"], "ms")
    capacity = config["results"]["capacity_results"]
    if age <= 0 or type(capacity) is not int or not 0 < capacity < 1 << 32:
        raise ConfigurationError(
            "Tracking requires positive bounded frame age and result capacity"
        )
    result = methods_pb2.TrackingFilePolicies(
        limits_json=limits.model_dump_json(),
        maximum_input_frame_age_ns=age,
        result_capacity=capacity,
    )
    recording = config["recording"]
    for name in ("sync_interval_s", "write_progress_timeout_s"):
        if duration_ns(recording[name], "s") <= 0:
            raise ConfigurationError(f"recording.{name} must be positive")
        setattr(result.recording, name, float(recording[name]))
    for name, bits in (
        ("max_pending_records", 32),
        ("max_pending_bytes", 64),
        ("max_record_bytes", 32),
    ):
        value = recording[name]
        if type(value) is not int or not 0 < value < 1 << bits:
            raise ConfigurationError(f"recording.{name} must be a positive uint{bits}")
        setattr(result.recording, name, value)
    if (
        result.recording.max_pending_bytes < 4 * (result.recording.max_record_bytes + 1)
        or result.recording.max_pending_records < 4
    ):
        raise ConfigurationError(
            "recording capacity must reserve at least four maximum lines"
        )
    return result


def load_defaults(root: Path) -> pb.TrackingSettings:
    return resolve_settings(root, pb.TrackingSettings())


def resolve_settings(root: Path, saved: pb.TrackingSettings) -> pb.TrackingSettings:
    """Fill absent settings from files, retaining explicit values and unset rig inputs."""
    config = _plain(load_files(root).config)
    result = pb.TrackingSettings.FromString(saved.SerializeToString())
    defaults = dict(
        pipeline_id=config["pipeline"]["name"],
        pose_mode={
            "manual": pb.TRACKING_POSE_MODE_MANUAL,
            "automatic": pb.TRACKING_POSE_MODE_AUTOMATIC,
        }.get(config["pose"]["mode"], 0),
        pose_max_age_ms=config["pose"]["max_age_ms"],
        pose_history_capacity=config["pose"]["history_capacity"],
        save_tracking_data=config["recording"]["save_tracking_data"],
    )
    if "camera_role" in config["input"]:
        from cephvr.acquisition.v1 import camera_pb2

        roles = {
            "behavioral": camera_pb2.CAMERA_ROLE_BEHAVIORAL,
            "tracking": camera_pb2.CAMERA_ROLE_TRACKING,
        }
        try:
            defaults["input_camera_role"] = roles[config["input"]["camera_role"]]
        except KeyError as exc:
            raise ConfigurationError("unsupported tracking input camera role") from exc
    for name, value in defaults.items():
        if not result.HasField(name):
            setattr(result, name, value)
    for source, target in (
        ("manual", "manual_pose"),
        ("search_region", "pose_search_region"),
        ("subject_reference", "subject_reference"),
    ):
        if (
            source in config["pose"]
            and config["pose"][source]
            and not result.HasField(target)
        ):
            ParseDict(
                config["pose"][source],
                getattr(result, target),
                ignore_unknown_fields=False,
            )
    # Complete explicit stage blocks are atomic; a selected implementation is never
    # replaced with the file's default method or silently repaired after validation.
    existing = {stage.stage_id for stage in result.stages}
    flow = {
        "schema_version": 1,
        "adapter": "nvof_cuda_v1",
        "input_mapping": "declared_full_range_gray8_v1",
        **config["flow"],
    }
    geometry = {"schema_version": 2, **config["geometry"]}
    estimator: dict[str, Any] = {
        "schema_version": 1,
        **{
            k: {"schema_version": 1, **v}
            for k, v in config["estimator"].items()
            if k != "fin_region"
        },
    }
    estimator["quality"].setdefault("maximum_native_cost", None)
    if result.pipeline_id == "fin_flow":
        estimator["fin_region"] = {
            "schema_version": 1,
            **config["estimator"]["fin_region"],
        }
    stages = [
        ("image_flow", "nvidia_optical_flow", "flow-settings.v1", flow),
        ("geometry", "three_point_ellipse", "ellipse-settings.v2", geometry),
        (
            "estimator",
            result.pipeline_id + "_proxy",
            result.pipeline_id.replace("_", "-") + "-settings.v1",
            estimator,
        ),
    ]
    if result.pose_mode == pb.TRACKING_POSE_MODE_AUTOMATIC:
        method = config["pose"]["automatic_method"]
        if method == "threshold_contour":
            pose = {"schema_version": 2, **config["pose"]["contour"]}
            for source, target in (
                ("level", "threshold_level"),
                ("polarity", "foreground_polarity"),
            ):
                if source in config["pose"]["threshold"]:
                    pose[target] = config["pose"]["threshold"][source]
            stages.insert(0, ("pose", method, "contour-settings.v2", pose))
        elif method == "keypoint_model":
            stages.insert(
                0,
                (
                    "pose",
                    method,
                    "model-settings.v1",
                    {"schema_version": 1, **config["pose"]["model"]},
                ),
            )
        else:
            raise ConfigurationError("unsupported automatic pose method")
    for stage, implementation, schema, settings in stages:
        if stage not in existing:
            result.stages.add(
                stage_id=stage,
                implementation_id=implementation,
                settings_schema_id="tracking." + schema,
                settings_json=json.dumps(
                    settings, allow_nan=False, separators=(",", ":")
                ),
            )
    return result
