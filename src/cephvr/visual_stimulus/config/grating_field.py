"""Bottom-centered unfolding for one reference-owned physical grating field."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from .texture_links import Vector, _basis, _dot, _fold, _sub

if TYPE_CHECKING:
    from .models.display_profile import Geometry
    from .models.program_model import TextureSettings


def unfolded_point(
    geometry: Geometry, face: str, x: float, y: float
) -> tuple[float, float]:
    surfaces = {str(s.surface_id): s for s in geometry.surfaces}
    if "bottom" not in surfaces or face not in surfaces:
        raise ValueError(
            "Shared grating requires calibrated Bottom and selected surface planes"
        )
    bottom, surface = surfaces["bottom"], surfaces[face]
    br, bu, bn = _basis(bottom)
    right, up, normal = _basis(surface)
    origin = tuple(
        (a + b) / 2
        for a, b in zip(bottom.bottom_left_mm, bottom.top_right_mm, strict=True)
    )
    center = tuple(
        (a + b) / 2
        for a, b in zip(surface.bottom_left_mm, surface.top_right_mm, strict=True)
    )
    point = tuple(center[i] + right[i] * x + up[i] * y for i in range(3))
    cosine = _dot(normal, bn)
    if cosine < -1 + 1e-10:
        raise ValueError("Shared grating cannot unfold a surface opposite Bottom")
    hinge_normal = tuple(normal[i] - cosine * bn[i] for i in range(3))
    length2 = _dot(cast(Vector, hinge_normal), cast(Vector, hinge_normal))
    distance = _dot(_sub(surface.bottom_left_mm, cast(Vector, origin)), normal)
    pivot = tuple(
        origin[i] + (hinge_normal[i] * distance / length2 if length2 > 1e-20 else 0)
        for i in range(3)
    )
    rotated = _fold(_sub(cast(Vector, point), cast(Vector, pivot)), normal, bn)
    offset = tuple(pivot[i] + rotated[i] - origin[i] for i in range(3))
    return _dot(cast(Vector, offset), br), _dot(cast(Vector, offset), bu)


def field_on_surface(
    source: TextureSettings,
    values: Mapping[str, float],
    target: TextureSettings,
    geometry: Geometry,
) -> tuple[float, float, float]:
    """Return follower frequency, local bar-normal angle and centered phase cycles."""
    assert source.space.kind == target.space.kind == "physical_surface"
    sm, tm = source.space.mappings[0], target.space.mappings[0]
    for mapping in (sm, tm):
        row_x, row_y = mapping.matrix
        if row_x[0] * row_y[1] - row_x[1] * row_y[0] <= 0:
            raise ValueError(
                "Shared grating requires orientation-preserving surface maps"
            )
    so = unfolded_point(geometry, sm.surface_id, 0, 0)
    sx = unfolded_point(geometry, sm.surface_id, 1, 0)
    sy = unfolded_point(geometry, sm.surface_id, 0, 1)
    a, b, c, d = sx[0] - so[0], sy[0] - so[0], sx[1] - so[1], sy[1] - so[1]
    determinant = a * d - b * c
    if abs(determinant) < 1e-12:
        raise ValueError("Shared grating requires a nonsingular unfolded reference")
    angle = math.radians(values["rotation"])
    cosine, sine = math.cos(angle), math.sin(angle)
    m, n = sm.matrix

    def coordinate(x: float, y: float) -> float:
        q = unfolded_point(geometry, tm.surface_id, x, y)
        dx, dy = q[0] - so[0], q[1] - so[1]
        lx, ly = (d * dx - b * dy) / determinant, (-c * dx + a * dy) / determinant
        return cosine * (m[0] * lx + m[1] * ly + m[2] - values["x"]) + sine * (
            n[0] * lx + n[1] * ly + n[2] - values["y"]
        )

    origin = coordinate(0, 0)
    ux, uy = coordinate(1, 0) - origin, coordinate(0, 1) - origin
    m, n = tm.matrix
    det = m[0] * n[1] - m[1] * n[0]
    if det <= 0:
        raise ValueError("Shared grating requires orientation-preserving surface maps")
    vx, vy = (ux * n[1] - uy * n[0]) / det, (-ux * m[1] + uy * m[0]) / det
    magnitude = math.hypot(vx, vy)
    if magnitude <= 1e-12:
        raise ValueError("Shared grating normal is degenerate")
    frequency = values["frequency"]
    phase = values.get("phase_x", 0) + frequency * (origin - vx * m[2] - vy * n[2])
    return frequency * magnitude, math.degrees(math.atan2(vy, vx)), phase
