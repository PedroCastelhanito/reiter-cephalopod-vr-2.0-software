"""One translated grating sheet projected onto calibrated physical screens."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, cast

from .texture_links import Vector, _basis, _dot

if TYPE_CHECKING:
    from .models.display_profile import Geometry
    from .models.program_model import TextureSettings


class SurfaceProjection:
    """Fixed reference-view sheet coordinates, built once per calibrated face.

    Everything but the sampled point is geometry-only. The instance is bound to the
    geometry object it was built from, so a changed geometry needs a new unfolder.
    """

    def __init__(self, geometry: Geometry) -> None:
        self.geometry = geometry
        self._surfaces = {str(s.surface_id): s for s in geometry.surfaces}
        self._maps: dict[str, Callable[[float, float], tuple[float, float]]] = {}

    def point(self, face: str, x: float, y: float) -> tuple[float, float]:
        project = self._maps.get(face)
        if project is None:
            project = self._maps[face] = self._build(face)
        return project(x, y)

    def _build(self, face: str) -> Callable[[float, float], tuple[float, float]]:
        surfaces = self._surfaces
        if face not in surfaces:
            raise ValueError("Shared grating requires the calibrated selected surface")
        surface = surfaces[face]
        right, up, _ = _basis(surface)
        center = tuple(
            (a + b) / 2
            for a, b in zip(surface.bottom_left_mm, surface.top_right_mm, strict=True)
        )
        # V02 fixes the accepted reference view; rotating a preview never changes stimuli.
        yaw, pitch = math.radians(-35), math.radians(25)
        across: Vector = (math.cos(yaw), -math.sin(yaw), 0.0)
        vertical: Vector = (
            -math.sin(yaw) * math.sin(pitch),
            -math.cos(yaw) * math.sin(pitch),
            math.cos(pitch),
        )

        def project(x: float, y: float) -> tuple[float, float]:
            point = tuple(center[i] + right[i] * x + up[i] * y for i in range(3))
            return _dot(cast(Vector, point), across), _dot(
                cast(Vector, point), vertical
            )

        return project


def projected_point(
    geometry: Geometry, face: str, x: float, y: float
) -> tuple[float, float]:
    return SurfaceProjection(geometry).point(face, x, y)


def field_on_surface(
    source: TextureSettings,
    values: Mapping[str, float],
    target: TextureSettings,
    geometry: Geometry,
    projection: SurfaceProjection | None = None,
) -> tuple[float, float, float]:
    """Return follower frequency, local bar-normal angle and centered phase cycles.

    A caller resolving several followers of one geometry may share its projection.
    """
    if projection is None or projection.geometry is not geometry:
        projection = SurfaceProjection(geometry)
    point_on_sheet = projection.point
    assert source.space.kind == target.space.kind == "physical_surface"
    sm, tm = source.space.mappings[0], target.space.mappings[0]
    for mapping in (sm, tm):
        row_x, row_y = mapping.matrix
        if row_x[0] * row_y[1] - row_x[1] * row_y[0] <= 0:
            raise ValueError(
                "Shared grating requires orientation-preserving surface maps"
            )
    so = point_on_sheet(sm.surface_id, 0, 0)
    sx = point_on_sheet(sm.surface_id, 1, 0)
    sy = point_on_sheet(sm.surface_id, 0, 1)
    a, b, c, d = sx[0] - so[0], sy[0] - so[0], sx[1] - so[1], sy[1] - so[1]
    determinant = a * d - b * c
    if abs(determinant) < 1e-12:
        raise ValueError("Shared grating requires a nonsingular projected reference")
    angle = math.radians(values["rotation"])
    cosine, sine = math.cos(angle), math.sin(angle)
    m, n = sm.matrix

    def coordinate(x: float, y: float) -> float:
        q = point_on_sheet(tm.surface_id, x, y)
        dx, dy = q[0] - so[0], q[1] - so[1]
        lx, ly = (d * dx - b * dy) / determinant, (-c * dx + a * dy) / determinant
        return cosine * (m[0] * lx + m[1] * ly + m[2]) + sine * (
            n[0] * lx + n[1] * ly + n[2]
        )

    center = coordinate(0, 0)
    ux, uy = coordinate(1, 0) - center, coordinate(0, 1) - center
    # Translation changes phase only; keep it out of finite-difference gradients.
    origin = center - cosine * values["x"] - sine * values["y"]
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
