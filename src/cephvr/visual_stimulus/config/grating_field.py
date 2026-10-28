"""One infinite, screen-local grating shared by directly linked projectors."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models.program_model import TextureSettings


def field_on_surface(
    source: TextureSettings,
    values: Mapping[str, float],
    target: TextureSettings,
) -> tuple[float, float, float]:
    """Follower frequency, angle and phase for the same local physical wave."""
    assert source.space.kind == target.space.kind == "physical_surface"
    sm, tm = source.space.mappings[0], target.space.mappings[0]
    for mapping in (sm, tm):
        m, n = mapping.matrix
        if m[0] * n[1] - m[1] * n[0] <= 0:
            raise ValueError(
                "Shared grating requires orientation-preserving surface maps"
            )
    angle = math.radians(values["rotation"])
    c, s, frequency = math.cos(angle), math.sin(angle), values["frequency"]
    m, n = sm.matrix
    gx, gy = frequency * (c * m[0] + s * n[0]), frequency * (c * m[1] + s * n[1])
    center_phase = values.get("phase_x", 0) + frequency * (
        c * (m[2] - values["x"]) + s * (n[2] - values["y"])
    )
    m, n = tm.matrix
    det = m[0] * n[1] - m[1] * n[0]
    vx, vy = (gx * n[1] - gy * n[0]) / det, (-gx * m[1] + gy * m[0]) / det
    magnitude = math.hypot(vx, vy)
    return (
        magnitude,
        math.degrees(math.atan2(vy, vx)),
        center_phase - vx * m[2] - vy * n[2],
    )
