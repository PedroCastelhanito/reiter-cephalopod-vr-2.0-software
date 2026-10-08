"""Explicit pixel sample depth and chroma geometry used by recording validation."""

from __future__ import annotations

from collections.abc import Callable

# Entries are (component depth, horizontal chroma subsampling, vertical subsampling).
PIXEL_FORMAT_LAYOUTS: dict[str, tuple[int, int, int]] = {
    "gray": (8, 1, 1),
    "gray8": (8, 1, 1),
    "gray9le": (9, 1, 1),
    "gray10le": (10, 1, 1),
    "gray12le": (12, 1, 1),
    "gray14le": (14, 1, 1),
    "gray16le": (16, 1, 1),
    "gray16be": (16, 1, 1),
    "rgb24": (8, 1, 1),
    "rgba": (8, 1, 1),
    "x2bgr10le": (10, 1, 1),
    "bgr24": (8, 1, 1),
    "rgb48le": (16, 1, 1),
    "rgb48be": (16, 1, 1),
    "bgr48le": (16, 1, 1),
    "bgr48be": (16, 1, 1),
    "gbrp": (8, 1, 1),
    "gbrp10le": (10, 1, 1),
    "gbrp12le": (12, 1, 1),
    "gbrp16le": (16, 1, 1),
    "yuv420p": (8, 2, 2),
    "yuvj420p": (8, 2, 2),
    "nv12": (8, 2, 2),
    "p010le": (10, 2, 2),
    "p010be": (10, 2, 2),
    "p016le": (16, 2, 2),
    "yuv422p": (8, 2, 1),
    "yuvj422p": (8, 2, 1),
    "yuv444p": (8, 1, 1),
    "yuvj444p": (8, 1, 1),
    "yuv420p9le": (9, 2, 2),
    "yuv420p10le": (10, 2, 2),
    "yuv420p12le": (12, 2, 2),
    "yuv420p14le": (14, 2, 2),
    "yuv420p16le": (16, 2, 2),
    "yuv422p9le": (9, 2, 1),
    "yuv422p10le": (10, 2, 1),
    "yuv422p12le": (12, 2, 1),
    "yuv422p14le": (14, 2, 1),
    "yuv422p16le": (16, 2, 1),
    "yuv444p9le": (9, 1, 1),
    "yuv444p10le": (10, 1, 1),
    "yuv444p12le": (12, 1, 1),
    "yuv444p14le": (14, 1, 1),
    "yuv444p16le": (16, 1, 1),
}


def pixel_format_depth(
    value: str, *, error: Callable[[str], Exception] = ValueError
) -> int:
    try:
        return PIXEL_FORMAT_LAYOUTS[value][0]
    except KeyError as exc:
        raise error(f"cannot establish component depth for {value!r}") from exc
