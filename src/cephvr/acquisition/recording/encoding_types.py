"""Small typed records for accepted acquisition FFmpeg encodings."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


class EncodingOptionsError(ValueError):
    pass


@dataclass(frozen=True)
class EncoderCapabilities:
    codecs: frozenset[str]
    pixel_formats: frozenset[str]
    options: Mapping[str, frozenset[str]]
    numeric_ranges: Mapping[str, tuple[float, float]]
    muxer_flags: frozenset[str]
    encoder_gpu_ordinal: int
    device_uuid: str = ""
    codec_pixel_formats: Mapping[str, frozenset[str]] | None = None
    device_codec_pixel_formats: Mapping[str, frozenset[str]] | None = None
    device_codec_profiles: Mapping[str, frozenset[str]] | None = None
    device_rate_controls: Mapping[str, frozenset[str]] | None = None
    device_lookahead: Mapping[str, bool] | None = None
    device_temporal_aq: Mapping[str, bool] | None = None
    device_lossless: Mapping[str, bool] | None = None
    force_idr_codecs: frozenset[str] = frozenset()
    device_max_dimensions: Mapping[tuple[str, str], tuple[int, int]] | None = None


@dataclass(frozen=True)
class ResolvedEncoding:
    codec: str
    input_pixel_format: str
    output_pixel_format: str
    output_bit_depth: int
    effective_output_args: tuple[str, ...]
    encoder_gpu_ordinal: int
    force_idr: bool
    output_width: int
    output_height: int
