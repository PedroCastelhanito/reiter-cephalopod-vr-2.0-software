"""Final output-space black regions, without changing mapping or GL ownership."""

from collections.abc import Callable, Iterable
from typing import Any

from cephvr.visual_stimulus.config.models.display_profile import (
    DisplayProfile,
    Output,
    PixelRect,
)
from cephvr.visual_stimulus.resources.calibration import PreparedCalibration


def clear_regions(
    context: Any,
    clear: Callable[..., None],
    regions: Iterable[PixelRect],
    color: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> None:
    previous = context.scissor
    try:
        for region in regions:
            rect = (region.x, region.y, region.width, region.height)
            context.scissor = rect
            clear(*color, alpha=1.0, viewport=rect)
    finally:
        context.scissor = previous


def clear_valid_background(
    context: Any,
    color: tuple[float, float, float],
    output: Output,
    display: DisplayProfile,
    calibration: PreparedCalibration | None,
) -> None:
    """Keep uniform Idle background inside the union of prepared valid areas."""
    from math import ceil

    from cephvr.visual_stimulus.config.models.artifact_models import GeometricProfile

    mappings = [m for m in display.active_mappings if m.output_id == output.output_id]
    profiles = [
        calibration.content.get(m.mapping_id) if calibration is not None else None
        for m in mappings
    ]
    if not profiles or any(
        not isinstance(p, GeometricProfile) or p.valid_area is None for p in profiles
    ):
        context.clear(*color, alpha=1.0)
        return
    previous = context.scissor
    try:
        context.scissor = None
        context.clear(0, 0, 0, alpha=1.0)
        for profile in profiles:
            assert (
                isinstance(profile, GeometricProfile) and profile.valid_area is not None
            )
            a, b, c, d = profile.valid_area
            x0, y0 = ceil(a * output.width_px - 0.5), ceil(b * output.height_px - 0.5)
            x1, y1 = ceil(c * output.width_px - 0.5), ceil(d * output.height_px - 0.5)
            rect = x0, y0, x1 - x0, y1 - y0
            context.scissor = rect
            context.clear(*color, alpha=1.0, viewport=rect)
    finally:
        context.scissor = previous
