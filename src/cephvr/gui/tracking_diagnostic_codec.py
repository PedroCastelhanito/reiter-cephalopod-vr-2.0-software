"""Encode the runnable subset of a local Tracking diagnostic draft."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

from cephvr.acquisition.v1 import camera_pb2
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.tracking_codec import (
    _encode_pose,
    _encode_stages,
    _integer,
    _number,
    _set_point,
    _update_stage,
)


def encode_diagnostic_draft(
    base: pb.TrackingSettings,
    draft: Mapping[str, Any],
    selected_stages: tuple[int, ...],
    *,
    asset_root: str = "",
) -> pb.TrackingSettings:
    """Patch only settings a pre-experiment diagnostic can consume."""
    result = pb.TrackingSettings.FromString(base.SerializeToString())
    result.input_camera_role = camera_pb2.CAMERA_ROLE_TRACKING
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
    elif result.preprocessing.crop_enabled:
        raise ValueError("preprocessing.crop_region: enabled crop needs a rectangle")

    _encode_optional_scale(result, draft)
    selected = set(selected_stages)
    if len(selected) != len(selected_stages):
        raise ValueError("diagnostic stages contain a duplicate selection")
    known = {
        1,  # pose
        2,  # sampling_region
        3,  # optical_flow
        4,  # flow_quality
        5,  # locomotion
    }
    if not selected <= known:
        raise ValueError("diagnostic stages contain an unknown selection")

    pose_ready = False
    if 1 in selected:
        _encode_diagnostic_pose(result, draft, asset_root)
        annotations = draft["annotations"]
        pose_ready = bool(
            annotations.get("Manual pose")
            if draft["choices"]["pose_method"] == "Manual"
            else annotations.get("Reference points")
            and annotations.get("Search region")
        )
    if {1, 2} <= selected and pose_ready:
        _encode_diagnostic_geometry(result, draft)
    if 3 in selected:
        _encode_diagnostic_flow(result, draft)
    if {1, 2, 3, 4} <= selected and pose_ready:
        result.pipeline_id = (
            "fin_flow" if draft["pipeline"] == "Fin flow" else "water_flow"
        )
        _encode_diagnostic_quality(result, draft)
    if selected == {1, 2, 3, 4, 5} and pose_ready:
        result.pipeline_id = (
            "fin_flow" if draft["pipeline"] == "Fin flow" else "water_flow"
        )
        _encode_stages(result, dict(draft), asset_root)
    return result


def _encode_optional_scale(
    result: pb.TrackingSettings, draft: Mapping[str, Any]
) -> None:
    points = draft["annotations"].get("Distance reference", [])
    text = str(draft.get("distance_mm", "")).strip()
    if not points and not text:
        return
    if not points or not text:
        result.ClearField("image_scale")
        return
    if len(points) != 2:
        raise ValueError("image_scale.distance: provide exactly two points")
    if any(len(point) != 2 for point in points):
        raise ValueError("image_scale.distance: each point needs X and Y")
    width, height = (int(value) for value in draft["image_size"])
    start = (float(points[0][0]), float(points[0][1]))
    end = (float(points[1][0]), float(points[1][1]))
    distance_mm = _number(text, "image_scale.distance_mm", positive=True)
    if width <= 0 or height <= 0:
        result.ClearField("image_scale")
        return
    pixels_per_mm = math.dist(start, end) / distance_mm
    if pixels_per_mm <= 0:
        raise ValueError("image_scale.distance: points must be separated")
    result.image_scale.image_width_px = width
    result.image_scale.image_height_px = height
    _set_point(result.image_scale.distance_start, start)
    _set_point(result.image_scale.distance_end, end)
    result.image_scale.distance_mm = distance_mm
    result.image_scale.pixels_per_mm = pixels_per_mm


def _encode_diagnostic_pose(
    result: pb.TrackingSettings, draft: Mapping[str, Any], asset_root: str
) -> None:
    points = draft["annotations"]
    method = draft["choices"]["pose_method"]
    if method == "Manual":
        landmarks = points.get("Manual pose", [])
        if not landmarks:
            result.ClearField("manual_pose")
            result.pose_mode = pb.TRACKING_POSE_MODE_MANUAL
            return
        if len(landmarks) != 3:
            raise ValueError("manual_pose.landmarks: provide three points")
        _encode_pose(result, dict(draft) | {"fields": draft["fields"]}, asset_root)
        return
    reference = points.get("Reference points", [])
    search_region = points.get("Search region", [])
    if not reference:
        result.ClearField("subject_reference")
        result.ClearField("pose_search_region")
        result.pose_mode = pb.TRACKING_POSE_MODE_AUTOMATIC
        return
    if len(reference) != 4:
        raise ValueError("subject_reference: provide four points")
    if not search_region:
        result.ClearField("pose_search_region")
        result.pose_mode = pb.TRACKING_POSE_MODE_AUTOMATIC
        width, height = (int(value) for value in draft["image_size"])
        result.subject_reference.image_width_px = width
        result.subject_reference.image_height_px = height
        for name, point in zip(
            ("anterior", "posterior", "medial_left", "medial_right"),
            reference,
            strict=True,
        ):
            _set_point(getattr(result.subject_reference, name), point)
        return
    _encode_pose(result, dict(draft), asset_root)


def _encode_diagnostic_flow(
    result: pb.TrackingSettings, draft: Mapping[str, Any]
) -> None:
    if not any(item.stage_id == "image_flow" for item in result.stages):
        raise ValueError(
            "stages.image_flow: accepted flow settings are unavailable; load the Tracking configuration"
        )
    choices = draft["choices"]
    _update_stage(
        result,
        "image_flow",
        {
            "output_grid_px": int(choices["flow_grid"].split()[0]),
            "preset": choices["flow_preset"].lower(),
        },
        implementation="nvidia_optical_flow",
        schema="tracking.flow-settings.v1",
    )


def _encode_diagnostic_geometry(
    result: pb.TrackingSettings, draft: Mapping[str, Any]
) -> None:
    values = draft["analysis_drafts"].get(draft["pipeline"], {})
    updates = {
        "schema_version": 2,
        "front_fraction": _number(
            values.get("front_fraction", ""), "geometry.front_fraction", positive=True
        ),
        "taper": _number(values.get("taper", ""), "geometry.taper"),
        "squareness": _number(
            values.get("squareness", ""), "geometry.squareness", positive=True
        ),
        "inner_clearance_fraction": _number(
            values.get("inner_clearance", ""), "geometry.inner_clearance_fraction"
        ),
        "outer_extent_fraction": _number(
            values.get("outer_extent", ""),
            "geometry.outer_extent_fraction",
            positive=True,
        ),
    }
    _update_stage(
        result,
        "geometry",
        updates,
        implementation="three_point_ellipse",
        schema="tracking.ellipse-settings.v2",
    )


def _encode_diagnostic_quality(
    result: pb.TrackingSettings, draft: Mapping[str, Any]
) -> None:
    values = draft["analysis_drafts"].get(draft["pipeline"], {})
    existing = next(
        (item for item in result.stages if item.stage_id == "estimator"), None
    )
    document: dict[str, Any] = {}
    if existing is not None:
        try:
            document = json.loads(existing.settings_json)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "stages.estimator.settings_json: invalid document"
            ) from error
        if not isinstance(document, dict):
            raise ValueError("stages.estimator.settings_json: expected an object")
    previous_quality = document.get("quality", {})
    maximum_native_cost = (
        previous_quality.get("maximum_native_cost")
        if isinstance(previous_quality, dict)
        else None
    )
    document["schema_version"] = 1
    document["sections"] = {
        "schema_version": 1,
        "count": _integer(values.get("sections", ""), "estimator.sections.count"),
    }
    document["quality"] = {
        "schema_version": 1,
        "radius_cells": _integer(
            values.get("radius", ""), "estimator.quality.radius_cells"
        ),
        "minimum_neighbors": _integer(
            values.get("minimum_neighbors", ""), "estimator.quality.minimum_neighbors"
        ),
        "noise_floor_px": _number(
            values.get("noise_floor", ""),
            "estimator.quality.noise_floor_px",
            positive=True,
        ),
        "maximum_normalized_residual": _number(
            values.get("residual", ""),
            "estimator.quality.maximum_normalized_residual",
            positive=True,
        ),
        "maximum_native_cost": maximum_native_cost,
    }
    if result.pipeline_id == "fin_flow":
        document["fin_region"] = {
            "schema_version": 1,
            "offset_degrees": _number(
                values.get("fin_offset", ""), "estimator.fin_region.offset_degrees"
            ),
            "span_degrees": _number(
                values.get("fin_span", ""),
                "estimator.fin_region.span_degrees",
                positive=True,
            ),
        }
    else:
        document.pop("fin_region", None)
    _update_stage(
        result,
        "estimator",
        document,
        implementation=result.pipeline_id + "_proxy",
        schema=f"tracking.{result.pipeline_id.replace('_', '-')}-settings.v1",
    )
