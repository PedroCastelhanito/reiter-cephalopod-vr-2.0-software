"""Shared buffer and recording-option value validation stage."""

from __future__ import annotations

import math

from cephvr.acquisition.identity import CAMERA_NAMES
from cephvr.control.v1 import types_pb2

from .validation_values import issue


def validate_shared_options(
    settings: types_pb2.AcquisitionSettings,
    result: types_pb2.ValidationResult,
    active_ids: dict[str, str],
) -> None:
    if len(active_ids) != sum(
        1
        for role in CAMERA_NAMES
        if getattr(settings, role).HasField("enabled")
        and getattr(settings, role).enabled
        and getattr(settings, role).device.device_id
    ):
        issue(
            result,
            "backends.acquisition",
            "DUPLICATE_DEVICE",
            "enabled camera roles must use distinct explicit device IDs",
        )
    if settings.HasField("tracking_ring_frames") and settings.tracking_ring_frames == 0:
        issue(
            result,
            "backends.acquisition.tracking_ring_frames",
            "INVALID_CAPACITY",
            "tracking ring capacity must be positive",
        )
    if (
        settings.HasField("recording_queue_frames")
        and settings.recording_queue_frames == 0
    ):
        issue(
            result,
            "backends.acquisition.recording_queue_frames",
            "INVALID_CAPACITY",
            "recording queue capacity must be positive",
        )
    if (
        settings.HasField("recording_startup_allowance_ms")
        and settings.recording_startup_allowance_ms == 0
    ):
        issue(
            result,
            "backends.acquisition.recording_startup_allowance_ms",
            "INVALID_DURATION",
            "recording startup allowance must be positive when present",
        )
    if settings.HasField(
        "preview_output_bit_depth"
    ) and settings.preview_output_bit_depth not in (
        8,
        16,
    ):
        issue(
            result,
            "backends.acquisition.preview_output_bit_depth",
            "INVALID_PREVIEW_DEPTH",
            "preview output bit depth must be 8 or 16",
        )
    if settings.HasField("session_preview_max_hz") and (
        not math.isfinite(settings.session_preview_max_hz)
        or settings.session_preview_max_hz < 0
    ):
        issue(
            result,
            "backends.acquisition.session_preview_max_hz",
            "INVALID_PREVIEW_RATE",
            "session preview rate must be finite and nonnegative",
        )
    if settings.HasField("recording_options"):
        for field in (
            "pending_records_capacity",
            "diagnostic_tail_max_lines",
            "diagnostic_tail_max_bytes",
        ):
            if (
                settings.recording_options.HasField(field)
                and getattr(settings.recording_options, field) == 0
            ):
                issue(
                    result,
                    f"backends.acquisition.recording_options.{field}",
                    "INVALID_CAPACITY",
                    "recording option must be positive when present",
                )
