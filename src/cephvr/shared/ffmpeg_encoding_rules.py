"""Option aliases and cross-option rules shared by validation and argv building."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping

from cephvr.shared.ffmpeg_arguments import (
    canonical_option as _shared_canonical_option,
)
from cephvr.shared.ffmpeg_pixel_formats import (
    pixel_format_depth as shared_pixel_format_depth,
)
from cephvr.shared.ffmpeg_types import (
    EncoderCapabilities,
    EncodingOptionsError,
)

_COLOR_METADATA = {
    "-color_range": {"pc", "jpeg", "tv", "mpeg"},
    "-colorspace": {
        "bt709",
        "fcc",
        "bt470bg",
        "smpte170m",
        "smpte240m",
        "bt2020nc",
        "bt2020c",
    },
    "-color_primaries": {
        "bt709",
        "bt470m",
        "bt470bg",
        "smpte170m",
        "smpte240m",
        "film",
        "bt2020",
        "smpte428",
        "smpte431",
        "smpte432",
        "jedec-p22",
    },
    "-color_trc": {
        "bt709",
        "gamma22",
        "gamma28",
        "smpte170m",
        "smpte240m",
        "linear",
        "log",
        "log_sqrt",
        "iec61966-2-4",
        "bt1361e",
        "iec61966-2-1",
        "bt2020-10",
        "bt2020-12",
        "smpte2084",
        "smpte428",
        "arib-std-b67",
    },
}
_BITRATE = re.compile(r"^(?:0|[0-9]+(?:\.[0-9]+)?(?:[kKmMgG])?)$")
_DECIMAL = re.compile(r"^(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$")
_INTEGER = re.compile(r"^[0-9]+$")


def pixel_format_depth(value: str) -> int:
    return shared_pixel_format_depth(value, error=EncodingOptionsError)


def _canonical(option: str) -> str:
    return _shared_canonical_option(option)


def _validate_option(name: str, value: str, caps: EncoderCapabilities) -> None:
    """Check spelling and range before any device-dependent numeric comparisons."""
    choices = caps.options.get(name)
    if choices is None:
        raise EncodingOptionsError(
            f"installed build has no capability evidence for {name}"
        )
    if name in {"-b:v", "-maxrate:v", "-minrate:v", "-bufsize:v"}:
        if not _BITRATE.fullmatch(value) or not math.isfinite(_bitrate_value(value)):
            raise EncodingOptionsError(f"invalid bitrate value {value!r}")
    elif name in {"-cq", "-qp", "-aq-strength"}:
        if not _DECIMAL.fullmatch(value) or not math.isfinite(float(value)):
            raise EncodingOptionsError(f"invalid finite numeric value for {name}")
        low, high = caps.numeric_ranges.get(name, (float("inf"), float("-inf")))
        if not low <= float(value) <= high:
            raise EncodingOptionsError(f"{name} value outside installed range")
    elif name in {"-rc-lookahead", "-surfaces"}:
        if not _INTEGER.fullmatch(value):
            raise EncodingOptionsError(f"{name} requires a nonnegative integer")
        low, high = caps.numeric_ranges.get(name, (float("inf"), float("-inf")))
        try:
            number = int(value)
        except ValueError as exc:
            raise EncodingOptionsError(f"{name} integer value is too large") from exc
        if not low <= number <= high:
            raise EncodingOptionsError(f"{name} value outside installed range")
    elif name in {"-spatial-aq", "-temporal-aq", "-zerolatency"}:
        if value not in {"0", "1"}:
            raise EncodingOptionsError(f"{name} requires 0 or 1")
    if name in _COLOR_METADATA and value not in _COLOR_METADATA[name]:
        raise EncodingOptionsError(f"unsupported {name[1:]} metadata enum")
    if choices and value not in choices:
        raise EncodingOptionsError(
            f"unsupported installed-build value {value!r} for {name}"
        )


def _validate_cross_options(parsed: Mapping[str, list[str]]) -> None:
    """Check combinations after each individual option has passed validation."""
    rc = parsed.get("-rc", [None])[0]
    cq = parsed.get("-cq", [None])[0]
    qp = parsed.get("-qp", [None])[0]
    spatial_aq = parsed.get("-spatial-aq", ["0"])[0] == "1"
    if cq is not None and qp is not None:
        raise EncodingOptionsError("-cq and -qp cannot be combined")
    if cq is not None and rc not in {"vbr", "vbr_hq"}:
        raise EncodingOptionsError(
            "-cq requires a compatible variable-rate control mode"
        )
    if qp is not None and rc not in {"constqp"}:
        raise EncodingOptionsError("-qp requires constant-QP rate control")
    if "-aq-strength" in parsed and not spatial_aq:
        raise EncodingOptionsError("-aq-strength requires -spatial-aq 1")
    minimum = _bitrate_value(parsed.get("-minrate:v", ["0"])[0])
    maximum = _bitrate_value(parsed.get("-maxrate:v", ["0"])[0])
    if minimum and maximum and minimum > maximum:
        raise EncodingOptionsError("-minrate:v cannot exceed -maxrate:v")


def _profiles_for_representation(codec: str, pixel_format: str) -> frozenset[str]:
    if codec == "h264_nvenc":
        if pixel_format == "yuv420p":
            return frozenset({"baseline", "main", "high"})
        if pixel_format == "yuv444p":
            return frozenset({"high444p"})
    if codec == "hevc_nvenc":
        if pixel_format == "yuv420p":
            return frozenset({"main"})
        if pixel_format == "p010le":
            return frozenset({"main10"})
        if pixel_format in {"yuv444p", "yuv444p10le"}:
            return frozenset({"rext"})
    if codec == "av1_nvenc" and pixel_format in {"yuv420p", "p010le"}:
        return frozenset({"main"})
    return frozenset()


def _bitrate_value(value: str) -> float:
    multiplier = {"k": 1_000, "m": 1_000_000, "g": 1_000_000_000}
    suffix = value[-1:].lower()
    number = float(value[:-1] if suffix in multiplier else value)
    return number * multiplier.get(suffix, 1)


def _format_rate(value: float) -> str:
    if not math.isfinite(value) or value <= 0:
        raise EncodingOptionsError("nominal frame rate must be finite and positive")
    return format(value, ".12g")
