"""Pure typed Tracking validation; successful validation never means native readiness."""

from __future__ import annotations

import math

from cephvr.acquisition.v1 import camera_pb2
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.deadlines import duration_ns
from cephvr.tracking.config.annotations import manual, point, reference, search
from cephvr.tracking.config.models.methods import StageConfiguration
from cephvr.tracking.config.pipeline import ResolvedPipeline, resolve_pipeline
from cephvr.tracking.config.stages import builtin_registry
from cephvr.visual_stimulus.config.models.program_model import parse_program_json


def validate_settings(
    settings: pb.TrackingSettings, *, max_bytes: int = 16_777_216
) -> ResolvedPipeline:
    if not settings.HasField("save_tracking_data"):
        raise ValueError("save_tracking_data requires an explicit resolved value")
    if settings.input_camera_role not in (
        camera_pb2.CAMERA_ROLE_BEHAVIORAL,
        camera_pb2.CAMERA_ROLE_TRACKING,
    ):
        raise ValueError("input_camera_role requires one acquisition camera")
    modes = {
        pb.TRACKING_POSE_MODE_MANUAL: "manual",
        pb.TRACKING_POSE_MODE_AUTOMATIC: "automatic",
    }
    if settings.pose_mode not in modes:
        raise ValueError("pose_mode must be manual or automatic")
    if settings.pose_mode == pb.TRACKING_POSE_MODE_MANUAL:
        manual(settings.manual_pose)
        if settings.HasField("subject_reference"):
            dimensions = reference(settings.subject_reference)
            if dimensions != (
                settings.manual_pose.image_width_px,
                settings.manual_pose.image_height_px,
            ):
                raise ValueError("manual pose and subject reference dimensions differ")
    else:
        width, height = reference(settings.subject_reference)
        search(settings.pose_search_region, width, height)
        if (
            not settings.HasField("pose_max_age_ms")
            or duration_ns(settings.pose_max_age_ms, "ms") <= 0
        ):
            raise ValueError("pose_max_age_ms must be a positive exact duration")
        if (
            not settings.HasField("pose_history_capacity")
            or settings.pose_history_capacity <= 0
        ):
            raise ValueError("pose_history_capacity must be positive")
    if not settings.HasField("image_scale"):
        raise ValueError(
            "Tracking requires two camera distance endpoints and known millimetres"
        )
    _validate_spatial_settings(settings)
    dimensions = (
        (
            settings.manual_pose.image_width_px,
            settings.manual_pose.image_height_px,
        )
        if settings.pose_mode == pb.TRACKING_POSE_MODE_MANUAL
        else reference(settings.subject_reference)
    )
    if dimensions != (
        settings.image_scale.image_width_px,
        settings.image_scale.image_height_px,
    ):
        raise ValueError("image scale and pose source dimensions differ")
    return resolve_pipeline(
        settings.pipeline_id,
        modes[settings.pose_mode],
        tuple(
            StageConfiguration(
                stage_id=x.stage_id,
                implementation_id=x.implementation_id,
                settings_schema_id=x.settings_schema_id,
                settings_json=x.settings_json,
            )
            for x in settings.stages
        ),
        builtin_registry(),
        max_bytes=max_bytes,
    )


def _validate_spatial_settings(settings: pb.TrackingSettings) -> None:
    if settings.HasField("preprocessing"):
        preprocessing = settings.preprocessing
        if not preprocessing.HasField("crop_enabled") or not preprocessing.HasField(
            "scale_percent"
        ):
            raise ValueError("preprocessing requires explicit crop and scale values")
        if not 10 <= preprocessing.scale_percent <= 100:
            raise ValueError("preprocessing scale_percent must be within 10..100")
        if preprocessing.crop_enabled and not preprocessing.HasField("crop_region"):
            raise ValueError("enabled preprocessing crop requires crop_region")
        if preprocessing.HasField("crop_region"):
            region = preprocessing.crop_region
            if (
                any(
                    not region.HasField(name)
                    for name in ("x_px", "y_px", "width_px", "height_px")
                )
                or region.width_px <= 0
                or region.height_px <= 0
            ):
                raise ValueError(
                    "preprocessing crop must be a positive pixel rectangle"
                )
    if not settings.HasField("image_scale"):
        return
    image_scale = settings.image_scale
    required = (
        "image_width_px",
        "image_height_px",
        "distance_start",
        "distance_end",
        "distance_mm",
        "pixels_per_mm",
    )
    if any(not image_scale.HasField(name) for name in required):
        raise ValueError("image scale requires dimensions, endpoints, length and scale")
    width, height = image_scale.image_width_px, image_scale.image_height_px
    if width <= 0 or height <= 0:
        raise ValueError("image scale requires positive acquired-image dimensions")
    if settings.HasField("subject_reference") and reference(
        settings.subject_reference
    ) != (width, height):
        raise ValueError("image scale and subject reference dimensions differ")
    start = point(image_scale.distance_start, width, height)
    end = point(image_scale.distance_end, width, height)
    if not math.isfinite(image_scale.distance_mm) or image_scale.distance_mm <= 0:
        raise ValueError("image scale distance_mm must be finite and positive")
    expected = math.dist(start, end) / image_scale.distance_mm
    if not math.isfinite(expected) or expected <= 0:
        raise ValueError("image scale endpoints must be distinct")
    if (
        not math.isfinite(image_scale.pixels_per_mm)
        or image_scale.pixels_per_mm <= 0
        or not math.isclose(
            image_scale.pixels_per_mm, expected, rel_tol=1e-9, abs_tol=1e-12
        )
    ):
        raise ValueError("pixels_per_mm does not match its endpoints and known length")


def validate_configuration(
    candidate: pb.ExperimentConfiguration,
) -> pb.ValidationResult:
    result = pb.ValidationResult(
        completed=True,
        valid=True,
        component="tracking",
        configuration_module_version="tracking-config-v1",
    )
    selected = [b for b in candidate.backends if b.backend_name == "tracking"]
    if not selected:
        return result

    def issue(code: str, message: str) -> None:
        result.valid = False
        item = result.issues.add(component="tracking", field_path="backends.tracking")
        item.failure.code = code
        item.failure.message = message

    if len(selected) != 1:
        issue("DUPLICATE_BACKEND", "Tracking settings appear more than once")
        return result
    backend = selected[0]
    if backend.WhichOneof("settings") != "tracking":
        issue("MISSING_SETTINGS", "Tracking requires typed settings")
        return result
    if not backend.enabled:
        return result
    try:
        resolved = validate_settings(backend.tracking)
        channels = {channel.channel_id: channel for channel in resolved.channels}
        visual_enabled = any(
            item.backend_name == "visual_stimulus" and item.enabled
            for item in candidate.backends
        )
        for trial in candidate.trials if visual_enabled else ():
            if not trial.HasField("stimulus") or not trial.stimulus.HasField("program"):
                continue
            program = parse_program_json(
                trial.stimulus.program.program_json, max_bytes=16_777_216
            )
            for channel in program.input_channels:
                expected = channels.get(channel.channel_id)
                if expected is None or (
                    channel.unit,
                    channel.value_kind,
                    channel.frame_id,
                ) != (expected.unit, expected.quantity, expected.coordinate_frame):
                    raise ValueError(
                        f"{channel.channel_id}: stimulus input must match calibrated Tracking units; "
                        "update its unit declaration and gain explicitly"
                    )
        acquisitions = [
            b
            for b in candidate.backends
            if b.backend_name == "acquisition"
            and b.enabled
            and b.WhichOneof("settings") == "acquisition"
        ]
        if len(acquisitions) != 1:
            raise ValueError("Tracking requires its acquisition backend")
        role = (
            "behavioral"
            if backend.tracking.input_camera_role == camera_pb2.CAMERA_ROLE_BEHAVIORAL
            else "tracking"
        )
        if not getattr(acquisitions[0].acquisition, role).enabled:
            raise ValueError(f"Tracking requires enabled acquisition camera {role}")
    except (ValueError, TypeError, OverflowError) as exc:
        issue("INVALID_TRACKING_CONFIGURATION", str(exc))
    return result
