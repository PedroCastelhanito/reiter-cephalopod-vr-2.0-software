"""Calibration-only output-pixel bars, drawn after geometric correction."""

from typing import Any

from cephvr.visual_stimulus.config.calibration_bars import reference_lengths


def draw_reference_bars(context: Any, width: int, height: int) -> None:
    """Clear bounded device-framebuffer rectangles; create no additional GL resource."""
    x_length, y_length = reference_lengths(width, height)
    # Endpoints are integer pixel boundaries so measured spans are exact pixels.
    x0, x1 = round(width * 0.375), round(width * 0.375) + int(x_length)
    y0, y1 = round(height * 0.375), round(height * 0.375) + int(y_length)
    cx, cy = width // 2, height // 2
    previous = context.scissor
    try:
        for rectangle, color in (
            ((x0 - 5, cy - 8, x1 - x0 + 10, 16), (0.0, 0.0, 0.0)),
            ((cx - 8, y0 - 5, 16, y1 - y0 + 10), (0.0, 0.0, 0.0)),
            ((x0, cy - 1, x1 - x0, 2), (1.0, 0.3, 0.0)),
            ((cx - 1, y0, 2, y1 - y0), (0.0, 1.0, 0.3)),
        ):
            context.scissor = rectangle
            context.clear(*color, alpha=1.0, viewport=rectangle)
    finally:
        context.scissor = previous
