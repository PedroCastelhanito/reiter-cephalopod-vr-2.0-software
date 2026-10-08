"""Validate and migrate local Tracking drafts before touching visible controls."""

from copy import deepcopy
from math import isfinite
from typing import Any

from cephvr.gui.tracking_annotation import POINTS
from cephvr.gui.tracking_stages import STAGES
from cephvr.shared.identity import require_uuid4


def validated_draft(
    data: dict[str, Any],
    field_keys: set[str],
    choice_values: dict[str, tuple[str, ...]],
    analysis_keys: tuple[str, ...],
) -> dict[str, Any]:
    data = deepcopy(data)
    if not isinstance(data, dict) or type(data.get("version")) is not int:
        raise ValueError("Expected a versioned Tracking draft object.")
    if data.get("format") == "cephvr-tracking-ui-draft" and data.get("version") == 1:
        data["version"] = 2
        data["preprocessing"] = {
            "crop_enabled": False,
            "scale_percent": 100,
            "region": [0, 0, 0, 0],
        }
        data["distance_mm"] = ""
        if isinstance(data.get("annotations"), dict):
            data["annotations"].setdefault("Input crop", [])
            data["annotations"].setdefault("Distance reference", [])
    if data.get("format") == "cephvr-tracking-ui-draft" and data.get("version") == 2:
        data["version"] = 3
        data["diagnostics"] = dict.fromkeys(("preprocessing", *STAGES), True)
    if data.get("format") == "cephvr-tracking-ui-draft" and data.get("version") == 3:
        stages = data.get("diagnostics")
        if (
            not isinstance(stages, dict)
            or set(stages) != {"preprocessing", *STAGES}
            or any(type(value) is not bool for value in stages.values())
        ):
            raise ValueError("Invalid diagnostic stage switches.")
        stages.pop("preprocessing")
        data["version"] = 4
    if data.get("format") != "cephvr-tracking-ui-draft" or data.get("version") != 4:
        raise ValueError("Expected a Tracking frontend draft, version 1, 2, 3 or 4.")
    data.setdefault("annotation_source", None)
    if set(data) != {
        "format",
        "version",
        "diagnostics",
        "camera",
        "preprocessing",
        "distance_mm",
        "pipeline",
        "fields",
        "choices",
        "analysis_drafts",
        "annotations",
        "image_size",
        "annotation_source",
    }:
        raise ValueError("Invalid Tracking draft field inventory.")
    stages = data.get("diagnostics")
    if (
        not isinstance(stages, dict)
        or set(stages) != set(STAGES)
        or any(type(value) is not bool for value in stages.values())
    ):
        raise ValueError("Invalid diagnostic stage switches.")
    if data.get("pipeline") not in ("Water flow", "Fin flow") or not isinstance(
        data.get("camera"), str
    ):
        raise ValueError("Invalid Tracking source or pipeline.")
    fields, choices, points = (
        data.get("fields"),
        data.get("choices"),
        data.get("annotations"),
    )
    if (
        not isinstance(fields, dict)
        or set(fields) != field_keys
        or any(not isinstance(value, str) for value in fields.values())
    ):
        raise ValueError("Invalid Tracking fields.")
    if (
        not isinstance(choices, dict)
        or set(choices) != choice_values.keys()
        or any(
            not isinstance(value, str) or value not in choice_values[key]
            for key, value in choices.items()
        )
    ):
        raise ValueError("Invalid Tracking method selection.")
    if not isinstance(points, dict) or set(points) != set(POINTS):
        raise ValueError("Invalid Tracking annotations.")
    analysis = data.get("analysis_drafts")
    if not isinstance(analysis, dict) or set(analysis) != {
        "Water flow",
        "Fin flow",
    }:
        raise ValueError("Missing pipeline settings.")
    for values in analysis.values():
        if (
            not isinstance(values, dict)
            or set(values) != set(analysis_keys)
            or any(not isinstance(value, str) for value in values.values())
        ):
            raise ValueError("Invalid pipeline settings.")
    if any(analysis[data["pipeline"]][key] != fields[key] for key in analysis_keys):
        raise ValueError("Selected pipeline settings disagree.")
    size = data.get("image_size")
    if (
        not isinstance(size, list)
        or len(size) != 2
        or any(type(v) is not int or not 0 <= v <= 100_000 for v in size)
    ):
        raise ValueError("Invalid reference image size.")
    source = data["annotation_source"]
    if source is not None:
        if (
            not isinstance(source, dict)
            or set(source)
            != {
                "camera_serial",
                "configuration_revision",
                "preview_run_id",
                "source_frame_id",
                "source_host_receipt_ns",
            }
            or source["camera_serial"] != data["camera"]
            or not isinstance(source["camera_serial"], str)
            or not source["camera_serial"]
            or type(source["configuration_revision"]) is not int
            or source["configuration_revision"] <= 0
            or type(source["source_frame_id"]) is not int
            or source["source_frame_id"] < 0
            or type(source["source_host_receipt_ns"]) is not int
            or source["source_host_receipt_ns"] < 0
            or size[0] <= 0
            or size[1] <= 0
        ):
            raise ValueError("Invalid acquired Tracking annotation source.")
        try:
            require_uuid4(source["preview_run_id"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid acquired Tracking preview identity.") from exc
    for key, values in points.items():
        if not isinstance(values, list) or len(values) > (len(POINTS[key]) or 2):
            raise ValueError("Invalid annotation point count.")
        for point in values:
            if (
                not isinstance(point, list)
                or len(point) != 2
                or any(
                    type(v) not in (int, float)
                    or not isfinite(v)
                    or not 0 <= v <= 100_000
                    or (bound > 0 and (v > bound if not POINTS[key] else v >= bound))
                    or (bound == 0 and key in ("Reference points", "Manual pose"))
                    for v, bound in zip(point, size, strict=True)
                )
            ):
                raise ValueError("Annotation lies outside its reference image.")
    preprocessing = data.get("preprocessing")
    if isinstance(preprocessing, dict) and "region" not in preprocessing:
        crop_points = points["Input crop"]
        preprocessing["region"] = (
            [
                crop_points[0][0],
                crop_points[0][1],
                crop_points[1][0] - crop_points[0][0],
                crop_points[1][1] - crop_points[0][1],
            ]
            if len(crop_points) == 2
            else [0, 0, 0, 0]
        )
    if (
        not isinstance(preprocessing, dict)
        or set(preprocessing) != {"crop_enabled", "scale_percent", "region"}
        or type(preprocessing.get("crop_enabled")) is not bool
        or type(preprocessing.get("scale_percent")) is not int
        or not 10 <= preprocessing["scale_percent"] <= 100
        or not isinstance(preprocessing.get("region"), list)
        or len(preprocessing["region"]) != 4
        or any(type(value) is not int or value < 0 for value in preprocessing["region"])
    ):
        raise ValueError("Invalid preprocessing settings.")
    distance = data.get("distance_mm")
    if not isinstance(distance, str):
        raise ValueError("Invalid calibration distance.")
    if distance and (not isfinite(float(distance)) or float(distance) <= 0):
        raise ValueError("Calibration distance must be positive.")
    for mode in ("Search region", "Input crop"):
        region = points[mode]
        if region and (
            len(region) != 2
            or any(type(value) is not int for point in region for value in point)
            or region[1][0] <= region[0][0]
            or region[1][1] <= region[0][1]
        ):
            raise ValueError("A region requires integer X/Y and positive width/height.")
    crop = preprocessing["region"]
    points_crop = points["Input crop"]
    expected_crop = (
        [
            points_crop[0][0],
            points_crop[0][1],
            points_crop[1][0] - points_crop[0][0],
            points_crop[1][1] - points_crop[0][1],
        ]
        if len(points_crop) == 2
        else [0, 0, 0, 0]
    )
    if crop != expected_crop:
        raise ValueError("Crop rectangle fields disagree with the annotation.")
    return data
