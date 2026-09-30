"""A07 frame-log schema shared by output planning and the recording writer."""

from __future__ import annotations

from cephvr.acquisition.recording.frame_log import FRAME_LOG_FIELDS
from cephvr.acquisition.recording.identity import MP4_IDENTITY_KEYS
from cephvr.controller.planning import WriterSchema, WriterSchemaKey


def get_writer_schemas() -> dict[WriterSchemaKey, WriterSchema]:
    """Return definitions that are also used by ``FrameLogWriter``."""
    frame_log = WriterSchema(
        schema_version=2,
        format="jsonl",
        fields={key: ", ".join(fields) for key, fields in FRAME_LOG_FIELDS.items()},
        units={
            "host_receipt_ns": "ns",
            "recording_end_monotonic_ns": "ns",
            "camera_timestamp_ns": "device-origin ns",
            "nominal_frame_rate_hz": "frames/s",
        },
        clocks={
            "host_clock": "cephvr.host.perf_counter_ns.v1",
            "camera_timestamp_ns": "cephvr.camera.native.v1",
            "video_frame": "constant-rate index at nominal_frame_rate_hz",
        },
    )
    video = WriterSchema(
        schema_version=1,
        format="mp4",
        fields={
            "container_identity_tags": ", ".join(MP4_IDENTITY_KEYS),
            "video_timeline": "constant-rate frame index at nominal_frame_rate_hz",
            "frame_correspondence": "nth non-dropped frame-log record is video frame n",
        },
        units={"frame_rate": "frames/s"},
        clocks={
            "presentation": "constant-rate index; scientific time is frame-log host receipt"
        },
    )
    return {
        ("acquisition", "behavioral_cam", "mp4"): video,
        ("acquisition", "tracking_cam", "mp4"): video,
        ("acquisition", "behavioral_cam_frames", "jsonl"): frame_log,
        ("acquisition", "tracking_cam_frames", "jsonl"): frame_log,
    }
