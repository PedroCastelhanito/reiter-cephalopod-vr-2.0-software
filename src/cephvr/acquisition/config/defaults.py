"""Resolve acquisition operator defaults into the authoritative protobuf schema."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from cephvr.acquisition.v1 import camera_pb2
from cephvr.control.v1 import types_pb2
from cephvr.controller.microcontroller.config import load_microcontroller_pair
from cephvr.shared.config import ConfigurationError

from .policy import _load_pair
from .values import (
    _bool,
    _number,
    _positive_int,
    _required,
    _role,
    _token,
    _validate_microcontroller_defaults,
)


def load_defaults(root: Path) -> types_pb2.AcquisitionSettings:
    """Load typed operator defaults while preserving protobuf optional presence."""
    pair = _load_pair(Path(root))
    config = pair.config
    result = types_pb2.AcquisitionSettings()
    for role in ("behavioral", "tracking"):
        values = config.get("cameras", {}).get(role, {})
        camera = getattr(result, role)
        camera.enabled = _bool(
            _required(values, "enabled", f"cameras.{role}.enabled"),
            f"cameras.{role}.enabled",
        )
        camera.save_video = _bool(
            _required(values, "save_video", f"cameras.{role}.save_video"),
            f"cameras.{role}.save_video",
        )
        camera.sdk_buffer_count = _positive_int(
            _required(values, "sdk_buffer_count", f"cameras.{role}.sdk_buffer_count"),
            f"cameras.{role}.sdk_buffer_count",
        )
        if "recording_bit_depth" in values:
            depth = _positive_int(
                values["recording_bit_depth"], f"cameras.{role}.recording_bit_depth"
            )
            if depth not in (8, 10):
                raise ConfigurationError(
                    f"cameras.{role}.recording_bit_depth must be 8 or 10"
                )
            camera.recording_bit_depth = depth
        ffmpeg_args = _required(values, "ffmpeg_args", f"cameras.{role}.ffmpeg_args")
        if not isinstance(ffmpeg_args, list) or not all(
            isinstance(x, str) for x in ffmpeg_args
        ):
            raise ConfigurationError(
                f"cameras.{role}.ffmpeg_args must be a string array"
            )
        camera.ffmpeg_args.values.extend(ffmpeg_args)
        device = camera.device
        if "device_id" in values:
            device.device_id = _token(values["device_id"], f"cameras.{role}.device_id")
        if "frame_timing" in values:
            timing = values["frame_timing"]
            if timing not in ("external_trigger", "free_running"):
                raise ConfigurationError(f"cameras.{role}.frame_timing is unsupported")
            device.frame_timing = (
                camera_pb2.FRAME_TIMING_EXTERNAL_TRIGGER
                if timing == "external_trigger"
                else camera_pb2.FRAME_TIMING_FREE_RUNNING
            )
        if "unaligned_free_running" in values:
            device.unaligned_free_running = _bool(
                values["unaligned_free_running"],
                f"cameras.{role}.unaligned_free_running",
            )
        for field in (
            "trigger_selector",
            "trigger_source",
            "trigger_activation",
            "exposure_duration_mode",
        ):
            if field in values:
                setattr(
                    device.settings,
                    field,
                    _token(values[field], f"cameras.{role}.{field}"),
                )
        camera_settings = device.settings
        if "pfs_source_filename" in values:
            source = values["pfs_source_filename"]
            if not isinstance(source, str) or not source or "\x00" in source:
                raise ConfigurationError(
                    f"cameras.{role}.pfs_source_filename must be nonempty path text"
                )
            device.pfs_source_filename = source
        if "exposure_us" in values:
            camera_settings.exposure_us = _number(
                values["exposure_us"], f"cameras.{role}.exposure_us"
            )
        if "frame_rate_hz" in values:
            camera_settings.frame_rate_hz = _number(
                values["frame_rate_hz"], f"cameras.{role}.frame_rate_hz"
            )
        if "gain" in values:
            gain = values["gain"]
            unit = _token(
                _required(values, "gain_unit", f"cameras.{role}.gain_unit"),
                f"cameras.{role}.gain_unit",
            )
            if type(gain) is int:
                camera_settings.gain.integer_value = gain
            elif isinstance(gain, Decimal):
                camera_settings.gain.decimal_value = _number(
                    gain, f"cameras.{role}.gain", positive=False
                )
            else:
                raise ConfigurationError(
                    f"cameras.{role}.gain must be an integer or decimal"
                )
            camera_settings.gain.unit = unit
            if "gain_selector" in values:
                camera_settings.gain.selector = _token(
                    values["gain_selector"], f"cameras.{role}.gain_selector"
                )
        elif "gain_unit" in values or "gain_selector" in values:
            raise ConfigurationError(
                f"cameras.{role}.gain_unit and gain_selector require gain"
            )
        if "pixel_format" in values:
            camera_settings.pixel_format = _token(
                values["pixel_format"], f"cameras.{role}.pixel_format"
            )
        roi_values = values.get("roi", {})
        if roi_values:
            if not isinstance(roi_values, dict):
                raise ConfigurationError(f"cameras.{role}.roi must be a table")
            for field in ("width", "height", "offset_x", "offset_y"):
                if field in roi_values:
                    number = roi_values[field]
                    minimum = 1 if field in ("width", "height") else 0
                    if type(number) is not int or number < minimum or number >= 1 << 32:
                        raise ConfigurationError(
                            f"cameras.{role}.roi.{field} is outside uint32 bounds"
                        )
                    setattr(camera_settings.roi, field, number)
        pulse = _role(config, role)
        if pulse.ListFields():
            getattr(result.pulses, role).CopyFrom(pulse)
    mc = load_microcontroller_pair(Path(root)).config["microcontroller"]
    if "port" in mc:
        result.pulses.port = _token(mc["port"], "microcontroller.port")
    for role in ("trial_state", "projector_flip"):
        pin_key = f"{role}_pin"
        enabled_key = f"{role}_enabled"
        if pin_key in mc:
            setattr(
                result.pulses,
                pin_key,
                _token(mc[pin_key], f"microcontroller.{pin_key}"),
            )
        if enabled_key in mc:
            setattr(
                result.pulses,
                enabled_key,
                _bool(mc[enabled_key], f"microcontroller.{enabled_key}"),
            )
    buffers = config.get("buffers", {})
    result.tracking_ring_frames = _positive_int(
        _required(buffers, "tracking_ring_frames", "buffers.tracking_ring_frames"),
        "buffers.tracking_ring_frames",
    )
    result.recording_queue_frames = _positive_int(
        _required(buffers, "recording_queue_frames", "buffers.recording_queue_frames"),
        "buffers.recording_queue_frames",
    )
    if "recording_startup_allowance_ms" in buffers:
        result.recording_startup_allowance_ms = _positive_int(
            buffers["recording_startup_allowance_ms"],
            "buffers.recording_startup_allowance_ms",
        )
    recording = config.get("recording", {})
    options = result.recording_options
    options.pending_records_capacity = _positive_int(
        _required(
            recording, "pending_records_capacity", "recording.pending_records_capacity"
        ),
        "recording.pending_records_capacity",
    )
    diagnostics = recording.get("diagnostics", {})
    options.diagnostic_tail_max_lines = _positive_int(
        _required(diagnostics, "max_lines", "recording.diagnostics.max_lines"),
        "recording.diagnostics.max_lines",
    )
    options.diagnostic_tail_max_bytes = _positive_int(
        _required(diagnostics, "max_bytes", "recording.diagnostics.max_bytes"),
        "recording.diagnostics.max_bytes",
    )
    preview = config.get("preview", {})
    result.preview_output_bit_depth = _positive_int(
        _required(preview, "output_bit_depth", "preview.output_bit_depth"),
        "preview.output_bit_depth",
    )
    if result.preview_output_bit_depth not in (8, 16):
        raise ConfigurationError("preview.output_bit_depth must be 8 or 16")
    result.session_preview_max_hz = _number(
        _required(preview, "session_preview_max_hz", "preview.session_preview_max_hz"),
        "preview.session_preview_max_hz",
        positive=False,
    )
    if result.session_preview_max_hz < 0:
        raise ConfigurationError("preview.session_preview_max_hz must be nonnegative")
    _validate_microcontroller_defaults(mc)
    return result
