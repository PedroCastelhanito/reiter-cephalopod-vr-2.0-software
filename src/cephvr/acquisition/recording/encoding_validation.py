"""Validate configured FFmpeg tokens against the installed encoder evidence."""

from __future__ import annotations

from collections.abc import Sequence

from cephvr.acquisition.recording.encoding_rules import (
    _FORBIDDEN,
    _SIMPLE_OPTIONS,
    _canonical,
    _profiles_for_representation,
    _validate_cross_options,
    _validate_option,
    pixel_format_depth,
)
from cephvr.acquisition.recording.encoding_types import (
    EncoderCapabilities,
    EncodingOptionsError,
    ResolvedEncoding,
)
from cephvr.acquisition.recording.filters import (
    FilterError,
    source_format,
    validate_filter_chain,
)


def validate_arguments(
    values: Sequence[str],
    *,
    capabilities: EncoderCapabilities,
    input_pixel_format: str,
    recording_bit_depth: int,
    input_width: int,
    input_height: int,
) -> ResolvedEncoding:
    """Resolve only an explicitly supported build/device/filter combination (A08)."""
    if not values:
        raise EncodingOptionsError("complete per-camera ffmpeg_args are required")
    if recording_bit_depth not in {8, 10}:
        raise EncodingOptionsError("recording bit depth must be resolved to 8 or 10")
    parsed = _parse_arguments(values)
    for key, option_values in parsed.items():
        if key in {"-c:v", "-pix_fmt", "-vf", "-metadata:s:v:0"}:
            continue
        _validate_option(key, option_values[0], capabilities)
    codec = parsed["-c:v"][0]
    if codec not in {"h264_nvenc", "hevc_nvenc", "av1_nvenc"}:
        raise EncodingOptionsError(f"unsupported required NVIDIA codec {codec!r}")
    if codec not in capabilities.codecs:
        raise EncodingOptionsError(f"installed FFmpeg does not advertise {codec}")
    if capabilities.encoder_gpu_ordinal < 0 or not capabilities.device_uuid:
        raise EncodingOptionsError(
            "encoding adapter is not resolved to an adopted physical GPU"
        )
    pix_fmt_value = parsed["-pix_fmt"][0]
    if not pix_fmt_value.startswith("+") or pix_fmt_value == "+":
        raise EncodingOptionsError("-pix_fmt must be +<one explicit pixel format>")
    pixel_format = pix_fmt_value[1:]
    if pixel_format not in capabilities.pixel_formats:
        raise EncodingOptionsError(
            f"installed FFmpeg does not advertise {pixel_format}"
        )
    if input_pixel_format not in capabilities.pixel_formats:
        raise EncodingOptionsError(
            f"installed FFmpeg does not advertise prepared input format {input_pixel_format}"
        )
    depth = pixel_format_depth(pixel_format)
    if depth != recording_bit_depth:
        raise EncodingOptionsError(
            f"terminal pixel format {pixel_format} is {depth}-bit, expected "
            f"recording_bit_depth={recording_bit_depth}"
        )
    if (
        capabilities.codec_pixel_formats is None
        or pixel_format not in capabilities.codec_pixel_formats.get(codec, frozenset())
    ):
        raise EncodingOptionsError(
            f"{codec} does not advertise output format {pixel_format}"
        )
    if (
        capabilities.device_codec_pixel_formats is None
        or pixel_format
        not in capabilities.device_codec_pixel_formats.get(codec, frozenset())
    ):
        raise EncodingOptionsError(
            f"resolved encoding device does not support {codec}/{pixel_format}"
        )
    _validate_device_options(parsed, capabilities, codec, pixel_format)
    color_range = parsed.get("-color_range", [None])[0]
    colorspace = parsed.get("-colorspace", [None])[0]
    if input_width <= 0 or input_height <= 0:
        raise EncodingOptionsError("resolved input dimensions are required")
    try:
        source = source_format(input_pixel_format, input_width, input_height, "full")
    except FilterError as exc:
        raise EncodingOptionsError(str(exc)) from exc
    output_image = source
    if "-vf" not in parsed:
        if input_pixel_format != pixel_format:
            raise EncodingOptionsError(
                "explicit format/scale conversion chain is required"
            )
    else:
        try:
            filter_result = validate_filter_chain(
                parsed["-vf"][0],
                source=source,
                target_depth=recording_bit_depth,
                accepted_pixel_formats=capabilities.pixel_formats,
                terminal_pixel_format=pixel_format,
                output_range=color_range,
                output_matrix=colorspace,
            )
            output_image = filter_result.image
        except FilterError as exc:
            raise EncodingOptionsError(str(exc)) from exc
    _validate_stream_metadata(parsed.get("-metadata:s:v:0", []))
    # A08 applies device limits to the actual filtered output, not the source image.
    maximum = (capabilities.device_max_dimensions or {}).get((codec, pixel_format))
    if maximum is None or min(maximum) <= 0:
        raise EncodingOptionsError(
            f"device dimension limits are missing for {codec}/{pixel_format}"
        )
    if output_image.width > maximum[0] or output_image.height > maximum[1]:
        raise EncodingOptionsError(
            f"{codec}/{pixel_format} output {output_image.width}x{output_image.height} "
            f"exceeds device maximum {maximum[0]}x{maximum[1]}"
        )
    required_flags = {"hybrid_fragmented", "frag_keyframe", "use_metadata_tags"}
    if not required_flags.issubset(capabilities.muxer_flags):
        raise EncodingOptionsError(
            "installed MP4 muxer lacks required fragment/identity flags"
        )
    _validate_cross_options(parsed)
    force_idr = codec in capabilities.force_idr_codecs
    if not force_idr or "-forced-idr" not in capabilities.options:
        raise EncodingOptionsError(
            "selected encoder lacks advertised forced-IDR support"
        )
    return ResolvedEncoding(
        codec,
        input_pixel_format,
        pixel_format,
        depth,
        tuple(values),
        capabilities.encoder_gpu_ordinal,
        force_idr,
        output_image.width,
        output_image.height,
    )


def _parse_arguments(values: Sequence[str]) -> dict[str, list[str]]:
    """Normalize aliases before checking ownership, arity and duplicate options."""
    parsed: dict[str, list[str]] = {}
    i = 0
    while i < len(values):
        raw = values[i]
        if not raw or "\x00" in raw:
            raise EncodingOptionsError(f"invalid empty/NUL argument at token {i}")
        if not raw.startswith("-") or raw == "-":
            raise EncodingOptionsError(f"positional token {i} is unsupported")
        if "=" in raw:
            raise EncodingOptionsError(
                "each supported FFmpeg option takes a separate value token"
            )
        canonical = _canonical(raw)
        if canonical in _FORBIDDEN:
            raise EncodingOptionsError(f"{raw} is acquisition-owned")
        if canonical not in _SIMPLE_OPTIONS:
            raise EncodingOptionsError(
                f"unsupported FFmpeg option {raw!r} at token {i}"
            )
        if i + 1 >= len(values) or values[i + 1].startswith("-"):
            raise EncodingOptionsError(f"{raw} is missing its one value")
        value = values[i + 1]
        i += 2
        if not value or "\x00" in value:
            raise EncodingOptionsError(f"{raw} has an empty/NUL value")
        parsed.setdefault(canonical, []).append(value)

    for option, supplied in parsed.items():
        if option != "-metadata:s:v:0" and len(supplied) != 1:
            raise EncodingOptionsError(f"duplicate single-value option {option}")
    if "-c:v" not in parsed or "-pix_fmt" not in parsed:
        raise EncodingOptionsError("-c:v and explicit -pix_fmt are required")
    return parsed


def _validate_device_options(
    parsed: dict[str, list[str]],
    capabilities: EncoderCapabilities,
    codec: str,
    pixel_format: str,
) -> None:
    """Require native evidence for the selected profile and optional NVENC features."""
    supported_profiles = (
        capabilities.device_codec_profiles.get(codec, frozenset())
        if capabilities.device_codec_profiles is not None
        else frozenset()
    )
    profile = parsed.get("-profile:v", [None])[0]
    compatible_profiles = _profiles_for_representation(codec, pixel_format)
    if not supported_profiles.intersection(compatible_profiles):
        raise EncodingOptionsError(
            f"device has no NVENC profile for {codec}/{pixel_format}"
        )
    if profile is not None and profile not in supported_profiles:
        raise EncodingOptionsError(
            f"device does not advertise NVENC profile {codec}/{profile}"
        )
    if profile is not None and profile not in compatible_profiles:
        raise EncodingOptionsError(
            f"NVENC profile {profile} is incompatible with {pixel_format}"
        )
    rate_modes = (
        capabilities.device_rate_controls.get(codec, frozenset())
        if capabilities.device_rate_controls is not None
        else frozenset()
    )
    if not rate_modes:
        raise EncodingOptionsError(
            f"device has no NVENC rate-control evidence for {codec}"
        )
    rc = parsed.get("-rc", [None])[0]
    native_rc = None if rc is None else {"vbr_hq": "vbr", "cbr_hq": "cbr"}.get(rc, rc)
    if native_rc is not None and native_rc not in rate_modes:
        raise EncodingOptionsError(
            f"device does not support {codec} rate-control mode {native_rc}"
        )
    if int(parsed.get("-rc-lookahead", ["0"])[0]) > 0 and not (
        capabilities.device_lookahead or {}
    ).get(codec, False):
        raise EncodingOptionsError("NVENC device does not support lookahead")
    if parsed.get("-temporal-aq", ["0"])[0] == "1" and not (
        capabilities.device_temporal_aq or {}
    ).get(codec, False):
        raise EncodingOptionsError("NVENC device does not support temporal AQ")
    if parsed.get("-spatial-aq", ["0"])[0] == "1":
        raise EncodingOptionsError(
            "NVENC API does not expose device evidence for spatial AQ"
        )
    if parsed.get("-tune", [None])[0] == "lossless" and not (
        capabilities.device_lossless or {}
    ).get(codec, False):
        raise EncodingOptionsError("NVENC device does not advertise lossless encode")
    if parsed.get("-multipass", ["disabled"])[0] != "disabled":
        raise EncodingOptionsError(
            "NVENC API does not expose device evidence for multipass mode"
        )


def _validate_stream_metadata(values: Sequence[str]) -> None:
    """Allow only distinct descriptive keys; identity metadata belongs to acquisition."""
    seen: set[str] = set()
    for value in values:
        if "=" not in value:
            raise EncodingOptionsError("stream metadata must be key=value")
        key, _ = value.split("=", 1)
        if key not in {"title", "comment", "description"}:
            raise EncodingOptionsError(f"reserved/unsupported metadata key {key!r}")
        if key in seen:
            raise EncodingOptionsError(f"duplicate stream metadata key {key!r}")
        seen.add(key)
