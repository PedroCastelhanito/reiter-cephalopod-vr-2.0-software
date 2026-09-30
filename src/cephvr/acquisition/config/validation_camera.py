"""Camera, device-settings and recording-argument validation stage."""

from __future__ import annotations

import math

from cephvr.acquisition.v1 import camera_pb2
from cephvr.control.v1 import types_pb2

from .validation_values import issue


def validate_camera_role(
    settings: types_pb2.AcquisitionSettings,
    role: str,
    result: types_pb2.ValidationResult,
) -> str | None:
    camera = getattr(settings, role)
    prefix = f"backends.acquisition.{role}"
    device = camera.device
    enabled = camera.HasField("enabled") and camera.enabled
    if enabled and not device.device_id:
        issue(
            result,
            f"{prefix}.device.device_id",
            "DEVICE_REQUIRED",
            "enabled camera requires an explicit device assignment",
        )
    if device.HasField("frame_timing"):
        if device.frame_timing not in (
            camera_pb2.FRAME_TIMING_EXTERNAL_TRIGGER,
            camera_pb2.FRAME_TIMING_FREE_RUNNING,
        ):
            issue(
                result,
                f"{prefix}.device.frame_timing",
                "INVALID_FRAME_TIMING",
                "frame timing must be external_trigger or free_running",
            )
        if device.frame_timing == camera_pb2.FRAME_TIMING_FREE_RUNNING and (
            not device.HasField("unaligned_free_running")
            or not device.unaligned_free_running
        ):
            issue(
                result,
                f"{prefix}.device.unaligned_free_running",
                "UNALIGNED_ACK_REQUIRED",
                "free-running camera must be explicitly acknowledged as unaligned",
            )
    elif enabled:
        issue(
            result,
            f"{prefix}.device.frame_timing",
            "FRAME_TIMING_REQUIRED",
            "enabled camera requires an explicit frame timing mode",
        )
    if camera.HasField("recording_bit_depth") and camera.recording_bit_depth not in (
        8,
        10,
    ):
        issue(
            result,
            f"{prefix}.recording_bit_depth",
            "INVALID_BIT_DEPTH",
            "recording bit depth must be 8 or 10",
        )
    if camera.HasField("sdk_buffer_count") and camera.sdk_buffer_count == 0:
        issue(
            result,
            f"{prefix}.sdk_buffer_count",
            "INVALID_COUNT",
            "SDK buffer count must be positive",
        )
    if (
        camera.HasField("save_video")
        and camera.save_video
        and (not camera.HasField("ffmpeg_args") or not camera.ffmpeg_args.values)
    ):
        issue(
            result,
            f"{prefix}.ffmpeg_args",
            "ENCODER_ARGUMENTS_REQUIRED",
            "saving requires a complete nonempty camera argument list",
        )
    _validate_device_settings(device.settings, result, prefix)
    if camera.HasField("ffmpeg_args") and any(
        not item or "\x00" in item for item in camera.ffmpeg_args.values
    ):
        issue(
            result,
            f"{prefix}.ffmpeg_args",
            "INVALID_ARGUMENT",
            "encoder arguments must be nonempty strings without NUL",
        )
    return device.device_id if enabled and device.device_id else None


def _validate_device_settings(
    settings: camera_pb2.CameraSettings,
    result: types_pb2.ValidationResult,
    prefix: str,
) -> None:
    for field in ("exposure_us", "frame_rate_hz"):
        if settings.HasField(field) and (
            not math.isfinite(getattr(settings, field)) or getattr(settings, field) <= 0
        ):
            issue(
                result,
                f"{prefix}.device.settings.{field}",
                "INVALID_VALUE",
                "value must be finite and positive",
            )
    if settings.HasField("gain"):
        gain = settings.gain
        arm = gain.WhichOneof("value")
        if arm == "decimal_value" and not math.isfinite(gain.decimal_value):
            issue(
                result,
                f"{prefix}.device.settings.gain.decimal_value",
                "INVALID_VALUE",
                "gain must be finite",
            )
        if not arm or not gain.unit:
            issue(
                result,
                f"{prefix}.device.settings.gain",
                "GAIN_UNIT_REQUIRED",
                "numeric gain requires an explicit value and unit",
            )
        if gain.HasField("selector") and not gain.selector:
            issue(
                result,
                f"{prefix}.device.settings.gain.selector",
                "INVALID_SELECTOR",
                "gain selector cannot be empty",
            )
    if settings.HasField("roi"):
        for field in ("width", "height"):
            if settings.roi.HasField(field) and getattr(settings.roi, field) == 0:
                issue(
                    result,
                    f"{prefix}.device.settings.roi.{field}",
                    "INVALID_ROI",
                    "ROI dimensions must be positive",
                )
    for field in (
        "pixel_format",
        "trigger_selector",
        "trigger_source",
        "trigger_activation",
        "exposure_duration_mode",
    ):
        if settings.HasField(field) and not getattr(settings, field):
            issue(
                result,
                f"{prefix}.device.settings.{field}",
                "EMPTY_SETTING",
                "an explicitly present setting cannot be empty",
            )
