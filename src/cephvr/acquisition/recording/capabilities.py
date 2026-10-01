"""Acquisition policy wrapper around shared FFmpeg/NVENC capability mechanisms."""

from __future__ import annotations

from cephvr.platform.windows.nvenc_capabilities import NvencProbeOwner
from cephvr.platform.windows.nvidia_device import NvidiaDevice
from cephvr.shared.encoder_probe import ProbeResult
from cephvr.shared.ffmpeg_capabilities import (
    SUPPORTED_NVENC_CODECS,
    CapabilityProbe,
    CapabilityProbeError,
    _encoder_options,
    _parse_muxer_flags,
    _parse_options,
    probe_nvenc_capabilities,
)
from cephvr.shared.ffmpeg_types import EncoderCapabilities


def inspect_encoder(
    executable: str,
    *,
    codec: str,
    device: NvidiaDevice | None = None,
    nvenc_owner: NvencProbeOwner,
    probe: CapabilityProbe,
    deadline_ns: int,
    required_muxer_flags: frozenset[str] = frozenset(
        {"hybrid_fragmented", "frag_keyframe", "use_metadata_tags"}
    ),
) -> EncoderCapabilities:
    """Preserve acquisition's codec and muxer policy with shared probe mechanics."""
    return probe_nvenc_capabilities(
        executable,
        codec=codec,
        device=device,
        nvenc_owner=nvenc_owner,
        probe=probe,
        deadline_ns=deadline_ns,
        required_muxer_flags=required_muxer_flags,
        supported_codecs=SUPPORTED_NVENC_CODECS,
    )


__all__ = [
    "CapabilityProbeError",
    "EncoderCapabilities",
    "ProbeResult",
    "_encoder_options",
    "_parse_muxer_flags",
    "_parse_options",
    "inspect_encoder",
]
