"""Build acquisition-owned FFmpeg argv after argument and device validation."""

from __future__ import annotations

from collections.abc import Sequence

from cephvr.acquisition.recording.encoding_rules import (
    _format_rate,
    pixel_format_depth,
)
from cephvr.acquisition.recording.encoding_types import (
    EncoderCapabilities,
    EncodingOptionsError,
    ResolvedEncoding,
)
from cephvr.acquisition.recording.encoding_validation import validate_arguments
from cephvr.acquisition.recording.identity import RecordingIdentity

__all__ = [
    "EncodingOptionsError",
    "EncoderCapabilities",
    "ResolvedEncoding",
    "build_command",
    "pixel_format_depth",
    "validate_arguments",
]


def build_command(
    *,
    executable: str,
    user_args: Sequence[str],
    effective: ResolvedEncoding,
    width: int,
    height: int,
    nominal_rate_hz: float,
    fragment_target_ns: int,
    video_path: str,
    identity: RecordingIdentity,
) -> list[str]:
    if min(width, height, fragment_target_ns) <= 0 or nominal_rate_hz <= 0:
        raise EncodingOptionsError("invalid raw-video geometry/rate/fragment interval")
    seconds = format(fragment_target_ns / 1_000_000_000, ".9f").rstrip("0").rstrip(".")
    force = f"expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+{seconds}))"
    output = [
        executable,
        "-hide_banner",
        "-nostdin",
        "-progress",
        "pipe:1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        effective.input_pixel_format,
        "-s",
        f"{width}x{height}",
        "-framerate",
        _format_rate(nominal_rate_hz),
        "-i",
        "-",
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-dn",
        *user_args,
        "-gpu",
        str(effective.encoder_gpu_ordinal),
        "-bf",
        "0",
        "-force_key_frames",
        force,
        "-fps_mode:v",
        "passthrough",
        "-map_metadata",
        "-1",
        "-movflags",
        "+hybrid_fragmented+frag_keyframe+use_metadata_tags",
    ]
    output.extend(("-n",))
    if effective.force_idr:
        output.extend(("-forced-idr", "1"))
    for key, value in identity.mp4_tags():
        output.extend(("-metadata:g", f"{key}={value}"))
    output.extend(("-f", "mp4", video_path))
    return output
