"""Compatibility exports for common FFmpeg value and cross-option rules."""

from cephvr.shared.ffmpeg_encoding_rules import (
    _BITRATE,
    _COLOR_METADATA,
    _DECIMAL,
    _INTEGER,
    _bitrate_value,
    _canonical,
    _format_rate,
    _profiles_for_representation,
    _validate_cross_options,
    _validate_option,
    pixel_format_depth,
)

__all__ = [
    "_BITRATE",
    "_COLOR_METADATA",
    "_DECIMAL",
    "_INTEGER",
    "_bitrate_value",
    "_canonical",
    "_format_rate",
    "_profiles_for_representation",
    "_validate_cross_options",
    "_validate_option",
    "pixel_format_depth",
]
