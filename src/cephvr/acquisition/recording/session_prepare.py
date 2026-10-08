"""Validate locked recording input and allocate its bounded prepared-frame buffer."""

from __future__ import annotations

from pathlib import Path

from cephvr.acquisition.recording.encoding import (
    EncoderCapabilities,
    ResolvedEncoding,
    validate_arguments,
)
from cephvr.acquisition.recording.identity import RecordingIdentity
from cephvr.acquisition.recording.paths import RecordingPaths
from cephvr.acquisition.recording.session_contracts import (
    RecordingFailure,
    RecordingQueue,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.shared.pixels.preparer import PixelPreparer


def prepare_recording(
    settings: acq.RecordingSettings,
    layout: camera.CameraImageLayout,
    identity: RecordingIdentity,
    paths: RecordingPaths,
    queue: RecordingQueue,
    pixel_preparer: PixelPreparer,
    capabilities: EncoderCapabilities,
    *,
    role: str,
) -> tuple[ResolvedEncoding, bytearray, str]:
    paths.validate(role, identity)
    identity.validate()
    for field in (
        "video_sync_interval_ns",
        "fragment_target_ns",
        "encoder_stall_timeout_ns",
        "frame_log_sync_interval_ns",
        "pending_records_capacity",
        "recording_queue_frames",
        "recording_bit_depth",
    ):
        if not settings.HasField(field) or getattr(settings, field) <= 0:
            raise RecordingFailure(f"resolved RecordingSettings.{field} is required")
    if queue.pending_records_capacity != settings.pending_records_capacity:
        raise RecordingFailure(
            "recording queue pending capacity differs from locked settings"
        )
    if queue.capacity_frames != settings.recording_queue_frames:
        raise RecordingFailure(
            "recording queue pixel capacity differs from locked settings"
        )
    if not layout.HasField("width") or not layout.HasField("height"):
        raise RecordingFailure("camera image layout lacks resolved dimensions")
    pixel_layout = pixel_preparer.layout
    if pixel_layout.width != layout.width or pixel_layout.height != layout.height:
        raise RecordingFailure(
            "pixel preparer dimensions differ from prepared camera layout"
        )
    channels = 1 if pixel_layout.pixel_format.channel_layout.startswith("mono") else 3
    target_depth = int(settings.recording_bit_depth)
    if target_depth == 8:
        input_format = "gray" if channels == 1 else "rgb24"
        container_bytes = 1
    else:
        input_format = "gray16le" if channels == 1 else "rgb48le"
        container_bytes = 2
    output = bytearray(
        int(layout.width) * int(layout.height) * channels * container_bytes
    )
    encoding = validate_arguments(
        settings.ffmpeg_args,
        capabilities=capabilities,
        input_pixel_format=input_format,
        recording_bit_depth=target_depth,
        input_width=int(layout.width),
        input_height=int(layout.height),
    )
    if not Path(settings.ffmpeg_executable).is_absolute():
        raise RecordingFailure("resolved FFmpeg executable path must be absolute")
    return encoding, output, input_format
