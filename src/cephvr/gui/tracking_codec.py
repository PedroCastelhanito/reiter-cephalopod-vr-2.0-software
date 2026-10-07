"""Translate the Tracking page draft into the controller's typed E07 settings."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cephvr.acquisition.v1 import camera_pb2
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.tracking_settings import decode_tracking_settings
from cephvr.tracking.config.validation import validate_settings

__all__ = ["decode_tracking_settings", "encode_tracking_draft"]


def encode_tracking_draft(
    base: pb.TrackingSettings,
    draft: dict[str, Any],
    *,
    asset_root: str = "",
) -> pb.TrackingSettings:
    """Apply edited frontend values while retaining unexposed typed settings."""
    result = pb.TrackingSettings.FromString(base.SerializeToString())
    result.input_camera_role = camera_pb2.CAMERA_ROLE_TRACKING
    result.pipeline_id = "fin_flow" if draft["pipeline"] == "Fin flow" else "water_flow"
    preprocessing = draft["preprocessing"]
    result.preprocessing.crop_enabled = bool(preprocessing["crop_enabled"])
    result.preprocessing.scale_percent = int(preprocessing["scale_percent"])
    result.preprocessing.ClearField("crop_region")
    region = preprocessing.get("region", (0, 0, 0, 0))
    if len(region) == 4 and region[2] > 0 and region[3] > 0:
        result.preprocessing.crop_region.x_px = int(region[0])
        result.preprocessing.crop_region.y_px = int(region[1])
        result.preprocessing.crop_region.width_px = int(region[2])
        result.preprocessing.crop_region.height_px = int(region[3])
    elif base.HasField("preprocessing") and base.preprocessing.HasField("crop_region"):
        result.preprocessing.crop_region.CopyFrom(base.preprocessing.crop_region)
    if result.preprocessing.crop_enabled and not result.preprocessing.HasField(
        "crop_region"
    ):
        raise ValueError("Set a positive Input crop rectangle before enabling crop.")

    _encode_scale(result, draft)
    _encode_pose(result, draft, asset_root)
    _encode_stages(result, draft, asset_root)
    validate_settings(result)
    return result


def encode_diagnostic_draft(
    base: pb.TrackingSettings,
    draft: Mapping[str, Any],
    selected_stages: tuple[int, ...],
    *,
    asset_root: str = "",
) -> pb.TrackingSettings:
    """Compatibility entry point for pre-experiment diagnostic encoding."""
    from cephvr.gui.tracking_diagnostic_codec import encode_diagnostic_draft as encode

    return encode(base, draft, selected_stages, asset_root=asset_root)


def _encode_scale(result: pb.TrackingSettings, draft: dict[str, Any]) -> None:
    points = draft["annotations"].get("Distance reference", [])
    distance_text = str(draft.get("distance_mm", "")).strip()
    if not points and not distance_text:
        result.ClearField("image_scale")
        return
    if len(points) != 2 or not distance_text:
        raise ValueError("Complete both distance points and the known length.")
    width, height = (int(value) for value in draft["image_size"])
    start, end = (tuple(float(axis) for axis in point) for point in points)
    distance_mm = _number(distance_text, "Reference length", positive=True)
    pixels_per_mm = math.dist(start, end) / distance_mm
    if width <= 0 or height <= 0 or pixels_per_mm <= 0:
        raise ValueError("Load the matching Tracking reference image and set scale.")
    scale = result.image_scale
    scale.image_width_px, scale.image_height_px = width, height
    scale.distance_start.x_px, scale.distance_start.y_px = start
    scale.distance_end.x_px, scale.distance_end.y_px = end
    scale.distance_mm = distance_mm
    scale.pixels_per_mm = pixels_per_mm


def _encode_pose(
    result: pb.TrackingSettings, draft: dict[str, Any], asset_root: str
) -> None:
    method = draft["choices"]["pose_method"]
    fields = draft["fields"]
    points = draft["annotations"]
    reference = points.get("Reference points", [])
    if reference:
        width, height = (int(value) for value in draft["image_size"])
        if width <= 0 or height <= 0 or len(reference) != 4:
            raise ValueError("Subject reference requires four points on one image.")
        result.subject_reference.image_width_px = width
        result.subject_reference.image_height_px = height
        for name, point in zip(
            ("anterior", "posterior", "medial_left", "medial_right"),
            reference,
            strict=True,
        ):
            _set_point(getattr(result.subject_reference, name), point)
    else:
        result.ClearField("subject_reference")
    if method == "Manual":
        result.pose_mode = pb.TRACKING_POSE_MODE_MANUAL
        width, height = (int(value) for value in draft["image_size"])
        landmarks = points.get("Manual pose", [])
        if width <= 0 or height <= 0 or len(landmarks) != 3:
            raise ValueError(
                "Manual pose requires three landmarks on a reference image."
            )
        result.manual_pose.image_width_px = width
        result.manual_pose.image_height_px = height
        for name, point in zip(
            ("tip", "left_base", "right_base"), landmarks, strict=True
        ):
            _set_point(getattr(result.manual_pose.landmarks, name), point)
        result.ClearField("pose_search_region")
        _remove_stage(result, "pose")
        return

    result.pose_mode = pb.TRACKING_POSE_MODE_AUTOMATIC
    result.ClearField("manual_pose")
    width, height = (int(value) for value in draft["image_size"])
    if width <= 0 or height <= 0 or len(reference) != 4:
        raise ValueError("Automatic pose requires four subject-reference points.")
    result.subject_reference.image_width_px = width
    result.subject_reference.image_height_px = height
    for name, point in zip(
        ("anterior", "posterior", "medial_left", "medial_right"),
        reference,
        strict=True,
    ):
        _set_point(getattr(result.subject_reference, name), point)
    region = draft["annotations"].get("Search region", [])
    if len(region) != 2:
        raise ValueError("Automatic pose requires a positive Search region.")
    (x, y), (right, bottom) = region
    region_width, region_height = right - x, bottom - y
    if region_width <= 0 or region_height <= 0:
        raise ValueError("Automatic pose requires a positive Search region.")
    result.pose_search_region.x_px = int(x)
    result.pose_search_region.y_px = int(y)
    result.pose_search_region.width_px = int(region_width)
    result.pose_search_region.height_px = int(region_height)
    method_id = {
        "Threshold + contour": "threshold_contour",
        "Keypoint model": "keypoint_model",
    }.get(method)
    if method_id is None:
        raise ValueError("Select a supported pose method.")
    _update_pose_stage(result, method_id, fields, draft["choices"], asset_root)


def _encode_stages(
    result: pb.TrackingSettings, draft: dict[str, Any], asset_root: str
) -> None:
    choices = draft["choices"]
    current = draft["analysis_drafts"].get(draft["pipeline"], {})
    _update_stage(
        result,
        "image_flow",
        {
            "output_grid_px": int(choices["flow_grid"].split()[0]),
            "preset": choices["flow_preset"].lower(),
        },
    )
    _update_stage(
        result,
        "geometry",
        {
            "front_fraction": _number(
                current.get("front_fraction", ""), "Front fraction", positive=True
            ),
            "taper": _number(current.get("taper", ""), "Taper"),
            "squareness": _number(
                current.get("squareness", ""), "Squareness", positive=True
            ),
            "inner_clearance_fraction": _number(
                current.get("inner_clearance", ""), "Inner clearance"
            ),
            "outer_extent_fraction": _number(
                current.get("outer_extent", ""), "Outer extent", positive=True
            ),
        },
    )
    quality = {
        "radius_cells": _integer(current.get("radius", ""), "Neighbour radius"),
        "minimum_neighbors": _integer(
            current.get("minimum_neighbors", ""), "Minimum neighbours"
        ),
        "noise_floor_px": _number(
            current.get("noise_floor", ""), "Noise floor", positive=True
        ),
        "maximum_normalized_residual": _number(
            current.get("residual", ""), "Maximum residual", positive=True
        ),
    }
    estimator: dict[str, Any] = {
        "schema_version": 1,
        "sections": {
            "schema_version": 1,
            "count": _integer(current.get("sections", ""), "Sections"),
        },
        "quality": {"schema_version": 1, **quality, "maximum_native_cost": None},
        "support": {
            "schema_version": 1,
            "minimum_accepted_area_fraction": _number(
                current.get("coverage", ""), "Minimum coverage", positive=True
            ),
        },
        "smoothing": {
            "schema_version": 1,
            "time_constant_s": _number(
                current.get("smoothing", ""), "Smoothing", positive=True
            ),
        },
    }
    existing_estimator = next(
        (item for item in result.stages if item.stage_id == "estimator"), None
    )
    if existing_estimator is not None:
        existing_quality = json.loads(existing_estimator.settings_json).get(
            "quality", {}
        )
        estimator["quality"]["maximum_native_cost"] = existing_quality.get(
            "maximum_native_cost"
        )
    if result.pipeline_id == "fin_flow":
        estimator["fin_region"] = {
            "schema_version": 1,
            "offset_degrees": _number(current.get("fin_offset", ""), "Fin angle"),
            "span_degrees": _number(
                current.get("fin_span", ""), "Fin span", positive=True
            ),
        }
    else:
        estimator.pop("fin_region", None)
    _update_stage(
        result,
        "estimator",
        estimator,
        implementation=result.pipeline_id + "_proxy",
        schema=f"tracking.{result.pipeline_id.replace('_', '-')}-settings.v1",
    )


def _update_pose_stage(
    result: pb.TrackingSettings,
    method: str,
    fields: dict[str, str],
    choices: dict[str, str],
    asset_root: str,
) -> None:
    if method == "threshold_contour":
        settings: dict[str, Any] = {
            "schema_version": 2,
            "minimum_axis_anisotropy": _number(
                fields["anisotropy"], "Minimum axis anisotropy", positive=True
            ),
            "threshold_level": _number(fields["threshold"], "Threshold"),
            "foreground_polarity": "dark"
            if choices["polarity"] == "Dark subject"
            else "bright",
            "minimum_area_px2": _integer(fields["minimum_area"], "Minimum area"),
            "maximum_area_px2": _integer(fields["maximum_area"], "Maximum area"),
            "geometry_quality": {
                "minimum_axis_px": _number(
                    fields["axis_length"], "Minimum axis", positive=True
                ),
                "minimum_base_width_px": _number(
                    fields["base_width"], "Minimum base width", positive=True
                ),
                "minimum_triangle_area_px2": _number(
                    fields["triangle_area"], "Minimum triangle area", positive=True
                ),
            },
        }
        schema = "tracking.contour-settings.v2"
    else:
        if not fields["model_manifest"]:
            raise ValueError("Select a model manifest for Keypoint model pose.")
        manifest = Path(fields["model_manifest"])
        root = Path(asset_root).resolve()
        if not manifest.is_absolute():
            manifest = root / manifest
        try:
            relative = manifest.resolve().relative_to(root)
        except (OSError, ValueError) as error:
            raise ValueError(
                "Model manifest must be inside the configured asset folder."
            ) from error
        existing_pose = next(
            (item for item in result.stages if item.stage_id == "pose"), None
        )
        device_ordinal = 0
        if existing_pose is not None and existing_pose.implementation_id == method:
            device_ordinal = json.loads(existing_pose.settings_json).get(
                "device_ordinal", 0
            )
        settings = {
            "schema_version": 1,
            "manifest": {"relative_path": relative.as_posix()},
            "device_ordinal": device_ordinal,
            "minimum_candidate_score": _number(
                fields["candidate_score"], "Candidate confidence"
            ),
            "minimum_landmark_score": _number(
                fields["landmark_score"], "Landmark confidence"
            ),
            "geometry_quality": {
                "minimum_axis_px": _number(
                    fields["axis_length"], "Minimum axis", positive=True
                ),
                "minimum_base_width_px": _number(
                    fields["base_width"], "Minimum base width", positive=True
                ),
                "minimum_triangle_area_px2": _number(
                    fields["triangle_area"], "Minimum triangle area", positive=True
                ),
            },
        }
        schema = "tracking.model-settings.v1"
    _update_stage(
        result,
        "pose",
        settings,
        implementation=method,
        schema=schema,
    )


def _update_stage(
    result: pb.TrackingSettings,
    stage_id: str,
    updates: dict[str, Any],
    *,
    implementation: str | None = None,
    schema: str | None = None,
) -> None:
    stage = next((item for item in result.stages if item.stage_id == stage_id), None)
    if stage is None:
        if implementation is None or schema is None:
            raise ValueError(f"Tracking settings are missing the {stage_id} stage.")
        stage = result.stages.add(
            stage_id=stage_id,
            implementation_id=implementation,
            settings_schema_id=schema,
        )
        value: dict[str, Any] = {}
    else:
        value = json.loads(stage.settings_json)
        if not isinstance(value, dict):
            raise ValueError(f"Tracking {stage_id} settings are not an object.")
        if implementation is not None and stage.implementation_id != implementation:
            value = {}
        if schema is not None and stage.settings_schema_id != schema:
            value = {}
    _merge(value, updates)
    stage.settings_json = json.dumps(
        value, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    if implementation is not None:
        stage.implementation_id = implementation
    if schema is not None:
        stage.settings_schema_id = schema


def _merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = value


def _remove_stage(result: pb.TrackingSettings, stage_id: str) -> None:
    for index in range(len(result.stages) - 1, -1, -1):
        if result.stages[index].stage_id == stage_id:
            del result.stages[index]


def _set_point(target: Any, point: list[float] | tuple[float, float]) -> None:
    if len(point) != 2:
        raise ValueError("image point requires X and Y coordinates")
    target.x_px, target.y_px = float(point[0]), float(point[1])


def _number(value: Any, name: str, *, positive: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error
    if not math.isfinite(number) or positive and number <= 0:
        raise ValueError(
            f"{name} must be finite" + (" and positive." if positive else ".")
        )
    return number


def _integer(value: Any, name: str) -> int:
    number = _number(value, name, positive=True)
    if not number.is_integer() or number > 4_294_967_295:
        raise ValueError(f"{name} must be a positive whole number.")
    return int(number)
