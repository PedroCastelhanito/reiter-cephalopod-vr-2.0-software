"""Resolve exact schedule outputs and launch FFmpeg before T (A08/E11)."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from cephvr.acquisition.recording.encoding import (
    ResolvedEncoding,
    build_command,
)
from cephvr.acquisition.recording.identity import RecordingIdentity
from cephvr.acquisition.recording.negotiation import (
    NegotiatedVideo,
    VideoNegotiationExpectation,
)
from cephvr.acquisition.recording.paths import RecordingPaths, resolve_recording_paths
from cephvr.acquisition.recording.progress_watchdog import EncoderProgressWatchdog
from cephvr.acquisition.recording.session_contracts import (
    EncoderLauncher,
    EncoderProcess,
    RecordingFailure,
    RecordingQueue,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq


def launch_scheduled_encoder(
    settings: acq.RecordingSettings,
    layout: camera.CameraImageLayout,
    identity: RecordingIdentity,
    paths: RecordingPaths,
    schedule: acq.WorkerSchedule,
    queue: RecordingQueue,
    launcher: EncoderLauncher,
    encoding: ResolvedEncoding,
    *,
    role: str,
    nominal_frame_rate_hz: float,
    fragment_target_ns: int,
    clock_ns: Callable[[], int] = time.perf_counter_ns,
    deadline_ns: int,
) -> tuple[Path, Path, EncoderProcess, EncoderProgressWatchdog]:
    """Materialize only schedule-authorized paths and a supervised FFmpeg child."""
    video_path, frame_log_path = resolve_recording_paths(
        paths, role, identity, schedule
    )
    for path in (video_path, frame_log_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() or path.is_symlink():
            raise RecordingFailure(f"reserved recording path already exists: {path}")
    argv = build_command(
        executable=settings.ffmpeg_executable,
        user_args=settings.ffmpeg_args,
        effective=encoding,
        width=int(layout.width),
        height=int(layout.height),
        nominal_rate_hz=nominal_frame_rate_hz,
        fragment_target_ns=fragment_target_ns,
        video_path=str(video_path),
        identity=identity,
    )
    launcher.bind_schedule(schedule)
    encoder = launcher.launch(
        argv,
        deadline_ns=deadline_ns,
        negotiation=VideoNegotiationExpectation(
            input=NegotiatedVideo(
                "rawvideo",
                encoding.input_pixel_format,
                int(layout.width),
                int(layout.height),
            ),
            output=NegotiatedVideo(
                _encoded_codec_name(encoding.codec),
                encoding.output_pixel_format,
                encoding.output_width,
                encoding.output_height,
            ),
        ),
    )
    watchdog = EncoderProgressWatchdog(
        encoder,
        queue,
        int(settings.encoder_stall_timeout_ns),
        clock_ns,
    )
    return video_path, frame_log_path, encoder, watchdog


def _encoded_codec_name(encoder_name: str) -> str:
    if encoder_name == "h264_nvenc":
        return "h264"
    if encoder_name == "hevc_nvenc":
        return "hevc"
    if encoder_name == "av1_nvenc":
        return "av1"
    raise RecordingFailure(f"unsupported resolved NVENC codec: {encoder_name}")
