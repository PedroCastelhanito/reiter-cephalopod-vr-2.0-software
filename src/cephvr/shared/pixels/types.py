"""Immutable source-layout records shared by acquisition and pixel consumers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class NativePixelFormat:
    """Exact SDK mapping; sdk-mappings.md owns binding and interpretation."""

    sdk_name: str
    sdk_value: int = field(compare=False)
    effective_bits: int
    channel_layout: str
    packing: str
    byte_order: Literal["little", "byte"]
    alignment: Literal["lsb", "msb", "packed"]


@dataclass(frozen=True)
class PixelLayout:
    """Confirmed native layout; row stride includes SDK row padding."""

    width: int
    height: int
    pixel_format: NativePixelFormat
    row_stride_bytes: int
    image_payload_bytes: int
