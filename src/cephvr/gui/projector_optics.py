"""Ideal direct and mirror-folded optics for the operator diagram only."""

import math
from dataclasses import dataclass
from typing import cast

Point3 = tuple[float, float, float]


@dataclass(frozen=True)
class ProjectionFootprint:
    projector: Point3
    corners: tuple[Point3, ...]
    width: float
    height: float
    mirror: tuple[Point3, ...] = ()
    mirror_center: Point3 | None = None
    warning: str = ""


def projection_footprint(
    corners: list[Point3], distance: str, throw: str, aspect: float
) -> ProjectionFootprint:
    """Ideal footprint on the screen plane, with a centered perpendicular optical axis."""
    length, ratio = float(distance), float(throw)
    if not all(math.isfinite(v) and v > 0 for v in (length, ratio, aspect)):
        raise ValueError(
            "Set positive projector distance, throw ratio and display aspect"
        )
    width = length / ratio
    height = width / aspect
    if not all(math.isfinite(v) and v > 0 for v in (width, height)):
        raise ValueError("Projection dimensions must be finite and positive")
    center = tuple(sum(p[i] for p in corners) / 4 for i in range(3))
    right = tuple(corners[1][i] - corners[0][i] for i in range(3))
    up = tuple(corners[3][i] - corners[0][i] for i in range(3))
    right = tuple(v / math.sqrt(sum(c * c for c in right)) for v in right)
    up = tuple(v / math.sqrt(sum(c * c for c in up)) for v in up)
    normal = (
        right[1] * up[2] - right[2] * up[1],
        right[2] * up[0] - right[0] * up[2],
        right[0] * up[1] - right[1] * up[0],
    )
    projector = tuple(center[i] - normal[i] * length for i in range(3))
    footprint = tuple(
        tuple(
            center[i] + u * width / 2 * right[i] + v * height / 2 * up[i]
            for i in range(3)
        )
        for u, v in ((-1, -1), (1, -1), (1, 1), (-1, 1))
    )
    return ProjectionFootprint(
        cast(Point3, projector),
        tuple(cast(Point3, p) for p in footprint),
        width,
        height,
    )


def bottom_mirror_footprint(
    bottom: list[Point3],
    right: list[Point3],
    distance: str,
    throw: str,
    aspect: float,
    right_distance: str,
) -> ProjectionFootprint:
    """Fold the centered Bottom cone at a 45° mirror, beneath the Right projector."""
    straight = projection_footprint(bottom, distance, throw, aspect)
    right_length = float(right_distance)
    if not math.isfinite(right_length) or right_length <= 0:
        raise ValueError("Set Right projector distance to locate the Bottom projector")
    length = float(distance)
    cx, cy, cz = (sum(p[i] for p in bottom) / 4 for i in range(3))
    projector_x = sum(p[0] for p in right) / 4 + right_length
    projector_y = sum(p[1] for p in right) / 4
    dx, dy = projector_x - cx, projector_y - cy
    horizontal = math.hypot(dx, dy)
    vertical = length - horizontal
    if horizontal <= 0 or vertical <= 0:
        raise ValueError(
            "Bottom total path must exceed the horizontal distance to the Right projector"
        )
    projector = (projector_x, projector_y, cz - vertical)
    mirror_center = (cx, cy, projector[2])
    if mirror_center[2] >= 0:
        raise ValueError(
            "Bottom central mirror must lie below the tank; increase total path"
        )
    ux, uy = dx / horizontal, dy / horizontal
    mirror = []
    for corner in straight.corners:
        denominator = length + (corner[0] - cx) * ux + (corner[1] - cy) * uy
        if denominator <= horizontal:
            return ProjectionFootprint(
                projector,
                straight.corners,
                straight.width,
                straight.height,
                mirror_center=mirror_center,
                warning="Central path is valid; outer rays cannot all reflect before reaching the screen. Increase total path or throw ratio for full-cone clearance.",
            )
        fraction = horizontal / denominator
        virtual = straight.projector
        mirror.append(
            cast(
                Point3,
                tuple(
                    virtual[i] + fraction * (corner[i] - virtual[i]) for i in range(3)
                ),
            )
        )
    if max(p[2] for p in mirror) >= 0:
        return ProjectionFootprint(
            projector,
            straight.corners,
            straight.width,
            straight.height,
            mirror_center=mirror_center,
            warning="Central path is valid; the full beam-intercept area extends above the tank bottom. Increase total path or throw ratio for full-cone clearance.",
        )
    return ProjectionFootprint(
        projector,
        straight.corners,
        straight.width,
        straight.height,
        tuple(mirror),
        mirror_center,
    )
