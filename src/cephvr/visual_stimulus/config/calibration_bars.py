"""Output-pixel reference geometry shared by calibration display and operator UI."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ReferenceScale:
    mm_per_pixel_x: float
    mm_per_pixel_y: float
    projected_width_mm: float
    projected_height_mm: float
    projector_distance_mm: float | None


def reference_frame_rectangles(
    width: int, height: int
) -> tuple[tuple[int, int, int, int], ...]:
    """Return an inside-only native output border, independent of physical scale."""
    if min(width, height) <= 0:
        raise ValueError("Reference frame requires positive output dimensions")
    stroke = min(2, width, height)
    return (
        (0, 0, width, stroke),
        (0, height - stroke, width, stroke),
        (0, 0, stroke, height),
        (width - stroke, 0, stroke, height),
    )


def reference_lengths(
    width_px: float,
    height_px: float,
    x_px: float | None = None,
    y_px: float | None = None,
) -> tuple[float, float]:
    if not all(math.isfinite(v) and v > 0 for v in (width_px, height_px)):
        raise ValueError("Reference bars require positive output pixel dimensions")
    defaults = (
        float(round(width_px * 0.625) - round(width_px * 0.375)),
        float(round(height_px * 0.625) - round(height_px * 0.375)),
    )
    lengths = tuple(
        default if configured is None else configured
        for default, configured in zip(defaults, (x_px, y_px), strict=True)
    )
    if any(
        not math.isfinite(length)
        or length <= 0
        or not float(length).is_integer()
        or length > dimension
        for length, dimension in zip(lengths, (width_px, height_px), strict=True)
    ):
        raise ValueError(
            "Reference bar lengths must be positive whole pixels within the output"
        )
    return lengths[0], lengths[1]


def reference_scale(
    width_px: float,
    height_px: float,
    x_mm: float,
    y_mm: float,
    throw_ratio: float | None = None,
    *,
    x_px: float | None = None,
    y_px: float | None = None,
) -> ReferenceScale:
    if not all(math.isfinite(v) and v > 0 for v in (width_px, height_px, x_mm, y_mm)):
        raise ValueError("Complete both reference-bar measurements")
    x_px, y_px = reference_lengths(width_px, height_px, x_px, y_px)
    scale_x, scale_y = x_mm / x_px, y_mm / y_px
    width, height = width_px * scale_x, height_px * scale_y
    distance = None
    if throw_ratio is not None:
        if not math.isfinite(throw_ratio) or throw_ratio <= 0:
            raise ValueError("Throw ratio must be positive when estimating distance")
        distance = width * throw_ratio
        if not math.isfinite(distance) or distance <= 0:
            raise ValueError("Reference measurements produce an invalid distance")
    if not all(math.isfinite(v) and v > 0 for v in (scale_x, scale_y, width, height)):
        raise ValueError("Reference measurements produce an invalid scale or distance")
    return ReferenceScale(scale_x, scale_y, width, height, distance)
