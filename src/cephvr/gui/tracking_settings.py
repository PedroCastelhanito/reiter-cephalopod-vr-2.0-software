"""Install authoritative typed Tracking settings into a versioned GUI draft."""

from __future__ import annotations

import json
from typing import Any

from cephvr.control.v1 import types_pb2 as pb
from cephvr.tracking.config.annotations import manual, reference, search
from cephvr.tracking.config.validation import _validate_spatial_settings


def decode_tracking_settings(
    settings: pb.TrackingSettings, *, camera_serial: str = ""
) -> dict[str, Any]:
    """Project authoritative typed settings into the visible Tracking draft."""
    _validate_spatial_settings(settings)
    if settings.HasField("manual_pose"):
        manual(settings.manual_pose)
    reference_size = None
    if settings.HasField("subject_reference"):
        reference_size = reference(settings.subject_reference)
    if settings.HasField("pose_search_region"):
        if reference_size is None:
            raise ValueError("search-region settings require a subject-reference image")
        search(settings.pose_search_region, *reference_size)
    stages = {item.stage_id: json.loads(item.settings_json) for item in settings.stages}
    pose = stages.get("pose", {})
    flow = stages.get("image_flow", {})
    geometry = stages.get("geometry", {})
    estimator = stages.get("estimator", {})
    quality = estimator.get("quality", {})
    support = estimator.get("support", {})
    smoothing = estimator.get("smoothing", {})
    preprocessing: dict[str, Any] = {
        "crop_enabled": settings.preprocessing.crop_enabled
        if settings.HasField("preprocessing")
        and settings.preprocessing.HasField("crop_enabled")
        else False,
        "scale_percent": settings.preprocessing.scale_percent
        if settings.HasField("preprocessing")
        and settings.preprocessing.HasField("scale_percent")
        else 100,
        "region": [0, 0, 0, 0],
    }
    points: dict[str, list[Any]] = {
        key: []
        for key in (
            "Reference points",
            "Manual pose",
            "Search region",
            "Input crop",
            "Distance reference",
        )
    }
    if settings.HasField("preprocessing") and settings.preprocessing.HasField(
        "crop_region"
    ):
        crop = settings.preprocessing.crop_region
        preprocessing["region"] = [
            crop.x_px,
            crop.y_px,
            crop.width_px,
            crop.height_px,
        ]
        x, y, width, height = preprocessing["region"]
        points["Input crop"] = [[x, y], [x + width, y + height]]
    image_size = [0, 0]
    if settings.HasField("subject_reference"):
        subject_reference = settings.subject_reference
        image_size = [
            subject_reference.image_width_px,
            subject_reference.image_height_px,
        ]
        points["Reference points"] = [
            _point_list(subject_reference.anterior),
            _point_list(subject_reference.posterior),
            _point_list(subject_reference.medial_left),
            _point_list(subject_reference.medial_right),
        ]
    elif settings.HasField("manual_pose"):
        image_size = [
            settings.manual_pose.image_width_px,
            settings.manual_pose.image_height_px,
        ]
    if settings.HasField("manual_pose"):
        landmarks = settings.manual_pose.landmarks
        points["Manual pose"] = [
            _point_list(landmarks.tip),
            _point_list(landmarks.left_base),
            _point_list(landmarks.right_base),
        ]
    if settings.HasField("pose_search_region"):
        region = settings.pose_search_region
        points["Search region"] = [
            [region.x_px, region.y_px],
            [region.x_px + region.width_px, region.y_px + region.height_px],
        ]
    if settings.HasField("image_scale"):
        scale = settings.image_scale
        image_size = [scale.image_width_px, scale.image_height_px]
        points["Distance reference"] = [
            _point_list(scale.distance_start),
            _point_list(scale.distance_end),
        ]
    fields = _default_fields()
    pose_stage = next(
        (item for item in settings.stages if item.stage_id == "pose"), None
    )
    choices = {
        "pose_method": "Manual"
        if settings.pose_mode == pb.TRACKING_POSE_MODE_MANUAL
        else "Threshold + contour",
        "polarity": "Dark subject",
        "flow_grid": "4 px",
        "flow_preset": "Medium",
    }
    if settings.pose_mode == pb.TRACKING_POSE_MODE_AUTOMATIC:
        choices["pose_method"] = (
            "Keypoint model"
            if pose_stage is not None and "keypoint" in pose_stage.implementation_id
            else "Threshold + contour"
        )
        if pose_stage is not None:
            fields.update(_decode_pose_fields(pose))
        if pose.get("foreground_polarity") == "bright":
            choices["polarity"] = "Bright subject"
    if "output_grid_px" in flow:
        choices["flow_grid"] = f"{flow['output_grid_px']} px"
    if "preset" in flow:
        choices["flow_preset"] = flow["preset"].capitalize()
    sections = estimator.get("sections", {})
    analysis = {
        "front_fraction": str(geometry.get("front_fraction", "0.60")),
        "taper": str(geometry.get("taper", "0.4")),
        "squareness": str(geometry.get("squareness", "3.5")),
        "sections": str(sections.get("count", "12")),
        "inner_clearance": str(geometry.get("inner_clearance_fraction", "0.1")),
        "outer_extent": str(geometry.get("outer_extent_fraction", "0.75")),
        "fin_offset": str(estimator.get("fin_region", {}).get("offset_degrees", 0)),
        "fin_span": str(estimator.get("fin_region", {}).get("span_degrees", 30)),
        "smoothing": str(smoothing.get("time_constant_s", "0.08")),
        "coverage": str(support.get("minimum_accepted_area_fraction", "0.25")),
        "minimum_neighbors": str(quality.get("minimum_neighbors", "4")),
        "radius": str(quality.get("radius_cells", "1")),
        "noise_floor": str(quality.get("noise_floor_px", "0.1")),
        "residual": str(quality.get("maximum_normalized_residual", "2.0")),
    }
    fields.update(analysis)
    distance_mm = (
        str(settings.image_scale.distance_mm)
        if settings.HasField("image_scale")
        else ""
    )
    return {
        "format": "cephvr-tracking-ui-draft",
        "version": 4,
        "diagnostics": dict.fromkeys(
            ("pose", "sampling_region", "optical_flow", "flow_quality", "locomotion"),
            True,
        ),
        "camera": camera_serial,
        "preprocessing": preprocessing,
        "distance_mm": distance_mm,
        "pipeline": "Fin flow" if settings.pipeline_id == "fin_flow" else "Water flow",
        "fields": fields,
        "choices": choices,
        "analysis_drafts": {"Water flow": analysis.copy(), "Fin flow": analysis.copy()},
        "annotations": points,
        "image_size": image_size,
        "annotation_source": None,
    }


def _point_list(value: Any) -> list[float]:
    return [float(value.x_px), float(value.y_px)]


def _default_fields() -> dict[str, str]:
    return {
        "threshold": "Required",
        "minimum_area": "Required",
        "maximum_area": "Required",
        "model_manifest": "",
        "candidate_score": "Required",
        "landmark_score": "Required",
        "anisotropy": "Required",
        "axis_length": "Required",
        "base_width": "Required",
        "triangle_area": "Required",
        "front_fraction": "0.60",
        "taper": "0.4",
        "squareness": "3.5",
        "sections": "12",
        "inner_clearance": "0.1",
        "outer_extent": "0.75",
        "fin_offset": "Required",
        "fin_span": "Required",
        "smoothing": "0.08",
        "coverage": "0.25",
        "minimum_neighbors": "4",
        "radius": "1",
        "noise_floor": "0.1",
        "residual": "2.0",
    }


def _decode_pose_fields(settings: dict[str, Any]) -> dict[str, str]:
    if "threshold_level" in settings:
        quality = settings["geometry_quality"]
        return {
            "threshold": str(settings["threshold_level"]),
            "minimum_area": str(settings["minimum_area_px2"]),
            "maximum_area": str(settings["maximum_area_px2"]),
            "anisotropy": str(settings["minimum_axis_anisotropy"]),
            "axis_length": str(quality["minimum_axis_px"]),
            "base_width": str(quality["minimum_base_width_px"]),
            "triangle_area": str(quality["minimum_triangle_area_px2"]),
        }
    quality = settings.get("geometry_quality", {})
    manifest = settings.get("manifest", {}).get("relative_path", "")
    return {
        "model_manifest": manifest,
        "candidate_score": str(settings.get("minimum_candidate_score", "Required")),
        "landmark_score": str(settings.get("minimum_landmark_score", "Required")),
        "axis_length": str(quality.get("minimum_axis_px", "Required")),
        "base_width": str(quality.get("minimum_base_width_px", "Required")),
        "triangle_area": str(quality.get("minimum_triangle_area_px2", "Required")),
    }
