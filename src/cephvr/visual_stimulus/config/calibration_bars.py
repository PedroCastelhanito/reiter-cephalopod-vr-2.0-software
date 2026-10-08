"""Output-pixel reference geometry shared by calibration display and operator UI."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ReferenceScale:
    mm_per_pixel_x: float
    mm_per_pixel_y: float
    projected_width_mm: float
    projected_height_mm: float
    projector_distance_mm: float


def reference_lengths(width_px: float, height_px: float) -> tuple[float, float]:
    if not all(math.isfinite(v) and v > 0 for v in (width_px, height_px)):
        raise ValueError("Reference bars require positive output pixel dimensions")
    return (
        float(round(width_px * 0.625) - round(width_px * 0.375)),
        float(round(height_px * 0.625) - round(height_px * 0.375)),
    )


def reference_scale(
    width_px: float, height_px: float, x_mm: float, y_mm: float, throw_ratio: float
) -> ReferenceScale:
    if not all(
        math.isfinite(v) and v > 0
        for v in (width_px, height_px, x_mm, y_mm, throw_ratio)
    ):
        raise ValueError(
            "Complete both reference-bar measurements and positive throw ratio"
        )
    x_px, y_px = reference_lengths(width_px, height_px)
    if min(x_px, y_px) <= 0:
        raise ValueError("Output resolution is too small for reference bars")
    scale_x, scale_y = x_mm / x_px, y_mm / y_px
    width, height = width_px * scale_x, height_px * scale_y
    distance = width * throw_ratio
    if not all(
        math.isfinite(v) and v > 0 for v in (scale_x, scale_y, width, height, distance)
    ):
        raise ValueError("Reference measurements produce an invalid scale or distance")
    return ReferenceScale(scale_x, scale_y, width, height, distance)
