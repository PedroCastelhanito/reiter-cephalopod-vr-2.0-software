"""Bounded normalized quadrilaterals for live GUI calibration updates.

A GUI diagnostic mapping is a unit-square image mapped onto a convex output quadrilateral
by a projective transform, tessellated into a fixed grid. Four corners (bottom-left,
bottom-right, top-left, top-right of the source) describe every update.
"""

import math
from collections.abc import Iterable, Sequence

# Views that draw through the geometric correction mesh and accept live edge updates.
LIVE_ADJUSTABLE_VIEWS = frozenset({"frame_grid", "seam_check"})
# Vertices per side of every GUI diagnostic/measured mesh; more cells track the
# projective map more closely at negligible cost.
GUI_MESH_SIZE = 17

Corners = tuple[tuple[float, float], ...]


class CalibrationAdjustmentRejected(ValueError):
    """Validation rejected before any active GL resource was changed."""


def corner_cross_products(corners: Corners) -> tuple[float, float, float, float]:
    """Turn cross products around the polygon bl, br, tr, tl (all one sign if convex)."""
    bl, br, tl, tr = corners
    ring = (bl, br, tr, tl)
    result = []
    for index in range(4):
        a, b, c = ring[index], ring[(index + 1) % 4], ring[(index + 2) % 4]
        result.append((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
    return result[0], result[1], result[2], result[3]


def is_convex_quadrilateral(corners: Corners) -> bool:
    crosses = corner_cross_products(corners)
    return all(c > 1e-15 for c in crosses) or all(c < -1e-15 for c in crosses)


def projective_mesh(
    corners: Corners, rows: int, columns: int
) -> tuple[tuple[float, float, float, float], ...]:
    """(u, v, x, y) for a rows x columns grid of the unit square mapped onto `corners`.

    `corners` follow the source corners (0,0), (1,0), (0,1), (1,1). The projective map
    keeps straight lines straight and spaces the grid in perspective, unlike bilinear
    interpolation of the corners.
    """
    if rows < 2 or columns < 2 or not is_convex_quadrilateral(corners):
        raise ValueError("Projective mesh requires a convex quadrilateral and a grid")
    (x0, y0), (x1, y1), (x3, y3), (x2, y2) = corners  # unit-square order p0..p3
    dx1, dx2, dx3 = x1 - x2, x3 - x2, x0 - x1 + x2 - x3
    dy1, dy2, dy3 = y1 - y2, y3 - y2, y0 - y1 + y2 - y3
    if abs(dx3) < 1e-15 and abs(dy3) < 1e-15:
        g = h = 0.0
        a, b, d, e = x1 - x0, x3 - x0, y1 - y0, y3 - y0
    else:
        det = dx1 * dy2 - dy1 * dx2
        g = (dx3 * dy2 - dy3 * dx2) / det
        h = (dx1 * dy3 - dy1 * dx3) / det
        a, b = x1 - x0 + g * x1, x3 - x0 + h * x3
        d, e = y1 - y0 + g * y1, y3 - y0 + h * y3
    mesh = []
    for row in range(rows):
        v = row / (rows - 1)
        for column in range(columns):
            u = column / (columns - 1)
            w = g * u + h * v + 1.0
            mesh.append((u, v, (a * u + b * v + x0) / w, (d * u + e * v + y0) / w))
    return tuple(mesh)


def validated_adjustments(
    items: Iterable[tuple[str, Sequence[float]]],
) -> dict[str, Corners]:
    result = {}
    for mapping_id, coordinates in items:
        if (
            not mapping_id
            or len(mapping_id) > 128
            or mapping_id in result
            or len(coordinates) != 8
            or any(not math.isfinite(v) or not 0 <= v <= 1 for v in coordinates)
        ):
            raise CalibrationAdjustmentRejected(
                "Invalid calibration adjustment identity or coordinates"
            )
        points = tuple((coordinates[i], coordinates[i + 1]) for i in range(0, 8, 2))
        if not is_convex_quadrilateral(points):
            raise CalibrationAdjustmentRejected(
                "Live calibration requires a convex, nondegenerate quadrilateral"
            )
        result[mapping_id] = points
    if not 1 <= len(result) <= 4:
        raise CalibrationAdjustmentRejected(
            "Live calibration requires one to four mapping adjustments"
        )
    return result
