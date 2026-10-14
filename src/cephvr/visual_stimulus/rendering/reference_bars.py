"""Calibration-only output-pixel guides, drawn after geometric correction."""

from typing import Any

from cephvr.visual_stimulus.config.calibration_bars import reference_lengths

Rectangle = tuple[int, int, int, int]
Color = tuple[float, float, float]

_TICK_STEP_PX = 100
_MAJOR_EVERY = 5
_FRAME_PX = 2


def _clamped(rect: Rectangle, width: int, height: int) -> Rectangle | None:
    """Intersect with the output; scissor origins stay non-negative."""
    x0, y0 = max(0, rect[0]), max(0, rect[1])
    x1, y1 = min(width, rect[0] + rect[2]), min(height, rect[1] + rect[3])
    return (x0, y0, x1 - x0, y1 - y0) if x1 > x0 and y1 > y0 else None


def _outline(rect: Rectangle, thickness: int) -> list[Rectangle]:
    x, y, w, h = rect
    return [
        (x, y, w, thickness),
        (x, y + h - thickness, w, thickness),
        (x, y, thickness, h),
        (x + w - thickness, y, thickness, h),
    ]


def _edge_ticks(width: int, height: int) -> list[tuple[Rectangle, Color]]:
    """Ruler ticks inside each output edge, counted from the frame (every 100 px)."""
    ticks: list[tuple[Rectangle, Color]] = []
    for index, position in enumerate(
        range(_TICK_STEP_PX, max(width, height), _TICK_STEP_PX), 1
    ):
        major = index % _MAJOR_EVERY == 0
        length = 28 if major else 12
        color = (1.0, 0.9, 0.0) if major else (1.0, 1.0, 1.0)
        if position < width:
            ticks.append(((position - 1, 0, 2, length), color))
            ticks.append(((position - 1, height - length, 2, length), color))
        if position < height:
            ticks.append(((0, position - 1, length, 2), color))
            ticks.append(((width - length, position - 1, length, 2), color))
    return ticks


def draw_reference_bars(
    context: Any,
    width: int,
    height: int,
    *,
    x_px: int | None = None,
    y_px: int | None = None,
    guide: tuple[int, int] | None = None,
) -> None:
    """Clear bounded device-framebuffer rectangles; create no additional GL resource.

    Draws the output frame and 100 px edge ticks (yellow every 500 px), an optional
    centered guide outline with the screen's aspect ratio, then the measurement bars.
    """
    x_length, y_length = reference_lengths(width, height, x_px, y_px)
    # Endpoints are integer pixel boundaries so measured spans are exact pixels.
    x0 = round(width * 0.375) if x_px is None else round((width - x_length) / 2)
    y0 = round(height * 0.375) if y_px is None else round((height - y_length) / 2)
    x1, y1 = x0 + int(x_length), y0 + int(y_length)
    cx, cy = width // 2, height // 2
    shapes: list[tuple[Rectangle, Color]] = [
        (rect, (1.0, 1.0, 1.0)) for rect in _outline((0, 0, width, height), _FRAME_PX)
    ]
    shapes.extend(_edge_ticks(width, height))
    if guide is not None:
        guide_w, guide_h = min(guide[0], width), min(guide[1], height)
        shapes.extend(
            (rect, (0.0, 0.8, 1.0))
            for rect in _outline(
                ((width - guide_w) // 2, (height - guide_h) // 2, guide_w, guide_h),
                _FRAME_PX,
            )
        )
    shapes.extend(
        (
            ((x0 - 5, cy - 8, x1 - x0 + 10, 16), (0.0, 0.0, 0.0)),
            ((cx - 8, y0 - 5, 16, y1 - y0 + 10), (0.0, 0.0, 0.0)),
            ((x0, cy - 1, x1 - x0, 2), (1.0, 0.3, 0.0)),
            ((cx - 1, y0, 2, y1 - y0), (0.0, 1.0, 0.3)),
        )
    )
    previous = context.scissor
    try:
        for rect, color in shapes:
            rectangle = _clamped(rect, width, height)
            if rectangle is None:
                continue
            context.scissor = rectangle
            context.clear(*color, alpha=1.0, viewport=rectangle)
    finally:
        context.scissor = previous
