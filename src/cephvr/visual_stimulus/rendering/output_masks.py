"""Final output-space black regions, without changing mapping or GL ownership."""

from collections.abc import Callable, Iterable
from typing import Any

from cephvr.visual_stimulus.config.models.display_profile import PixelRect


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
