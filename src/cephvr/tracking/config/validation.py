"""Pure typed Tracking validation; successful validation never means native readiness."""

from __future__ import annotations

from cephvr.acquisition.v1 import camera_pb2
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.deadlines import duration_ns
from cephvr.tracking.config.annotations import manual, reference, search
from cephvr.tracking.config.models.methods import StageConfiguration
from cephvr.tracking.config.pipeline import ResolvedPipeline, resolve_pipeline
from cephvr.tracking.config.stages import builtin_registry


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
        validate_settings(backend.tracking)
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
