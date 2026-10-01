"""Installed FFmpeg help parsing without test encodes or implicit defaults."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol

from cephvr.platform.windows.nvenc_capabilities import NvencProbeOwner
from cephvr.platform.windows.nvidia_device import (
    NvidiaDevice,
    discover_encoder_device,
)
from cephvr.shared.encoder_probe import ProbeResult
from cephvr.shared.ffmpeg_arguments import SIMPLE_OPTIONS as _SIMPLE_OPTIONS
from cephvr.shared.ffmpeg_types import EncoderCapabilities

SUPPORTED_NVENC_CODECS = frozenset({"h264_nvenc", "hevc_nvenc", "av1_nvenc"})


class CapabilityProbeError(ValueError):
    """Installed build/device evidence is missing or incompatible with recording."""


class CapabilityProbe(Protocol):
    """Process runner must use the existing registered Windows child owner."""

    def run(
        self, executable: str, args: Sequence[str], *, deadline_ns: int
    ) -> ProbeResult: ...


def probe_nvenc_capabilities(
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
    supported_codecs: frozenset[str] = SUPPORTED_NVENC_CODECS,
) -> EncoderCapabilities:
    """Read advertised build capabilities; never create a video/test stream."""
    if codec not in supported_codecs:
        raise CapabilityProbeError("unsupported NVIDIA encoder")
    adopted_device = device or discover_encoder_device()
    encoders = _run(probe, executable, ("-hide_banner", "-encoders"), deadline_ns)
    pixfmts = _run(probe, executable, ("-hide_banner", "-pix_fmts"), deadline_ns)
    encoder_help = _run(
        probe, executable, ("-hide_banner", "-h", f"encoder={codec}"), deadline_ns
    )
    muxer_help = _run(
        probe, executable, ("-hide_banner", "-h", "muxer=mp4"), deadline_ns
    )
    full_help = _run(probe, executable, ("-hide_banner", "-h", "full"), deadline_ns)
    if not re.search(rf"\b{re.escape(codec)}\b", encoders):
        raise CapabilityProbeError(f"installed FFmpeg does not advertise {codec}")
    all_formats = frozenset(_parse_pixel_formats(pixfmts))
    codec_formats = frozenset(_parse_encoder_formats(encoder_help)) & all_formats
    if not codec_formats:
        raise CapabilityProbeError(f"no advertised pixel formats for {codec}")
    options, ranges = _encoder_options(encoder_help, full_help)
    flags = _parse_muxer_flags(muxer_help)
    if not required_muxer_flags.issubset(flags):
        raise CapabilityProbeError(
            "MP4 muxer help lacks required flags: "
            + ", ".join(sorted(required_muxer_flags - flags))
        )
    # FFmpeg's advertised formats describe the build, not the adopted GPU.
    # Until the native NVENC capability query completes, do not infer hardware
    # support from a rig probe or a GPU product name.
    try:
        native = nvenc_owner.query(adopted_device, deadline_ns=deadline_ns)
        device_formats = native.codec_pixel_formats[codec]
        device_profiles = native.codec_profiles[codec] & options.get(
            "-profile:v", frozenset()
        )
        if not device_profiles:
            raise CapabilityProbeError(
                f"FFmpeg and NVENC have no common {codec} profile evidence"
            )
        dimensions = {
            (codec, pixel_format): native.max_dimensions[codec]
            for pixel_format in device_formats
        }
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        raise CapabilityProbeError(
            f"NVENC device capability query failed: {exc}"
        ) from exc
    return EncoderCapabilities(
        codecs=frozenset({codec}),
        pixel_formats=all_formats,
        options=options,
        numeric_ranges=ranges,
        muxer_flags=flags,
        encoder_gpu_ordinal=adopted_device.ordinal,
        device_uuid=adopted_device.uuid,
        codec_pixel_formats={codec: codec_formats},
        device_codec_pixel_formats={codec: device_formats},
        device_codec_profiles={codec: device_profiles},
        device_rate_controls={codec: native.codec_rate_controls[codec]},
        device_lookahead={codec: native.codec_lookahead[codec]},
        device_temporal_aq={codec: native.codec_temporal_aq[codec]},
        device_lossless={codec: native.codec_lossless[codec]},
        force_idr_codecs=(
            frozenset({codec}) if "-forced-idr" in options else frozenset()
        ),
        device_max_dimensions=dimensions,
    )


def _run(
    probe: CapabilityProbe, executable: str, args: Sequence[str], deadline_ns: int
) -> str:
    result = probe.run(executable, args, deadline_ns=deadline_ns)
    if result.returncode:
        raise CapabilityProbeError(
            f"FFmpeg capability query {' '.join(args)} failed: {result.stderr[-2048:]}"
        )
    return result.stdout + "\n" + result.stderr


def _parse_pixel_formats(text: str) -> set[str]:
    output: set[str] = set()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 5 and re.fullmatch(r"[IOHPB\.]{5}", parts[0]):
            output.add(parts[1])
    return output


def _parse_encoder_formats(text: str) -> set[str]:
    match = re.search(r"Supported pixel formats:\s*([^\r\n]+)", text, re.IGNORECASE)
    if match is None:
        return set()
    return set(match.group(1).split())


def _encoder_options(
    encoder_help: str, full_help: str
) -> tuple[dict[str, frozenset[str]], dict[str, tuple[float, float]]]:
    """Combine common codec options with only the selected encoder's private ones."""
    common_lines: list[str] = []
    in_common = False
    for line in full_help.splitlines():
        if line.strip() == "AVCodecContext AVOptions:":
            in_common = True
        elif in_common:
            if line and not line[0].isspace():
                break
            common_lines.append(line)
    common, common_ranges = _parse_options("\n".join(common_lines))
    options, ranges = _parse_options(encoder_help)
    # Full help also includes unrelated encoders. Even generic profile/level rows
    # cannot establish the selected NVENC encoder's private option support.
    for name in (
        "-b:v",
        "-maxrate:v",
        "-minrate:v",
        "-bufsize:v",
        "-color_range",
        "-colorspace",
        "-color_primaries",
        "-color_trc",
    ):
        if name not in options and name in common:
            options[name] = common[name]
            if name in common_ranges:
                ranges[name] = common_ranges[name]
    return options, ranges


def _parse_options(
    text: str,
) -> tuple[dict[str, frozenset[str]], dict[str, tuple[float, float]]]:
    options: dict[str, frozenset[str]] = {}
    ranges: dict[str, tuple[float, float]] = {}
    current = ""
    supported = (_SIMPLE_OPTIONS - {"-metadata:s:v:0"}) | {"-forced-idr"}
    for line in text.splitlines():
        declaration = re.match(
            r"\s*(-[a-zA-Z0-9_-]+)(?::([a-zA-Z]+)(?::([0-9]+))?)?\s+(?:<([^>]+)>|([^\s]+))",
            line,
        )
        if declaration:
            stem, selector, index = declaration.group(1, 2, 3)
            valid_selector = selector is None or (
                selector == "v" and index in {None, "0"}
            )
            candidate = _canonical_encoder_option(stem) if valid_selector else ""
            current = candidate if candidate in supported else ""
            if current:
                options.setdefault(current, frozenset())
        elif line and not line[0].isspace():
            current = ""
        if not current:
            continue
        values = re.search(
            r"(?:supported values|values):\s*([^\r\n]+)", line, re.IGNORECASE
        )
        if values:
            options[current] = frozenset(values.group(1).replace(",", " ").split())
        else:
            enum = re.match(
                r"\s{2,}([a-zA-Z][a-zA-Z0-9_-]*)\s+(?:-?[0-9]+\s+)?([A-Z.]{10,})\s+",
                line,
            )
            if enum:
                options[current] = options[current] | frozenset({enum.group(1)})
        bounds = re.search(
            r"(?:from|range)\s+(-?[0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?)\s+(?:to|\.\.)\s+(-?[0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?|I64_MAX|INT64_MAX|INT_MAX|UINT_MAX)",
            line,
            re.IGNORECASE,
        )
        if bounds:
            maxima = {
                "I64_MAX": float(2**63 - 1),
                "INT64_MAX": float(2**63 - 1),
                "INT_MAX": float(2**31 - 1),
                "UINT_MAX": float(2**32 - 1),
            }
            maximum_text = bounds.group(2).upper()
            maximum = (
                maxima[maximum_text]
                if maximum_text in maxima
                else float(bounds.group(2))
            )
            ranges[current] = (float(bounds.group(1)), maximum)
    return options, ranges


def _parse_muxer_flags(text: str) -> frozenset[str]:
    # FFmpeg AVOption help prints a parent `-movflags <flags>` row followed by
    # unit constants (name, option flags, description). Only collect constants
    # in that section; do not mistake unrelated AVOptions for movflags.
    output: set[str] = set()
    in_flags = False
    for line in text.splitlines():
        if re.match(r"\s*-movflags\s+<", line):
            in_flags = True
            continue
        if in_flags and re.match(r"\s*-[a-zA-Z0-9_-]+(?:\s|$)", line):
            in_flags = False
        if not in_flags:
            continue
        match = re.match(
            r"\s{2,}([a-z][a-z0-9_]*)\s+(?:-?[0-9]+\s+)?([A-Z.]{10,})\s+\S",
            line,
        )
        if match:
            output.add(match.group(1))
    return frozenset(output)


def _canonical_encoder_option(value: str) -> str:
    mapping = {
        "-vcodec": "-c:v",
        "-c": "-c:v",
        "-codec": "-c:v",
        "-profile": "-profile:v",
        "-level": "-level:v",
        "-b": "-b:v",
        "-maxrate": "-maxrate:v",
        "-minrate": "-minrate:v",
        "-bufsize": "-bufsize:v",
    }
    return mapping.get(value, value)
