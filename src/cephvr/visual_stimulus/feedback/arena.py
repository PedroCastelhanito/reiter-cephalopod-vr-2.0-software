"""Bounded V16 planar swept-slide constraints."""

from __future__ import annotations

import math
from collections.abc import Sequence

Point = tuple[float, float]


def inset_convex_polygon(
    vertices: Sequence[Point], margin: float
) -> tuple[tuple[Point, float], ...]:
    if len(vertices) < 3 or not math.isfinite(margin) or margin < 0:
        raise ValueError("a polygon and finite nonnegative margin are required")
    area = sum(
        a[0] * b[1] - b[0] * a[1]
        for a, b in zip(vertices, (*vertices[1:], vertices[0]), strict=True)
    )
    if area <= 0:
        raise ValueError("arena polygon must be strictly convex and counterclockwise")
    walls: list[tuple[Point, float]] = []
    for a, b in zip(vertices, (*vertices[1:], vertices[0]), strict=True):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length == 0:
            raise ValueError("arena polygon has a zero-length edge")
        nx, ny = dy / length, -dx / length  # outward normal for CCW polygon
        offset = nx * a[0] + ny * a[1] - margin
        walls.append(((nx, ny), offset))
    for i, (a, b) in enumerate(
        zip(vertices, (*vertices[1:], vertices[0]), strict=True)
    ):
        c = vertices[(i + 2) % len(vertices)]
        if (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]) <= 0:
            raise ValueError("arena polygon must be strictly convex")
    return tuple(walls)


def slide_displacement(
    position: Point,
    displacement: Point,
    walls: Sequence[tuple[Point, float]],
    *,
    tolerance: float,
) -> tuple[Point, Point, bool]:
    """Sweep to first contact, then remove infeasible components at each contact."""
    if (
        tolerance <= 0
        or not math.isfinite(tolerance)
        or not all(math.isfinite(v) for v in (*position, *displacement))
    ):
        raise ValueError("finite coordinates and positive tolerance required")
    point = position
    remaining = displacement
    constrained = False
    for _ in range(len(walls) + 1):
        if math.hypot(*remaining) <= tolerance:
            return point, (point[0] - position[0], point[1] - position[1]), constrained
        earliest = 1.0
        hits: list[tuple[Point, float]] = []
        for normal, offset in walls:
            start = normal[0] * point[0] + normal[1] * point[1] - offset
            rate = normal[0] * remaining[0] + normal[1] * remaining[1]
            if rate > tolerance and start + rate > tolerance:
                t = max(0.0, (tolerance - start) / rate)
                if t < earliest - tolerance:
                    earliest, hits = t, [(normal, offset)]
                elif abs(t - earliest) <= tolerance:
                    hits.append((normal, offset))
        point = (point[0] + earliest * remaining[0], point[1] + earliest * remaining[1])
        if not hits:
            return point, (point[0] - position[0], point[1] - position[1]), constrained
        constrained = True
        residual = ((1 - earliest) * remaining[0], (1 - earliest) * remaining[1])
        # 2D feasible cone projection: compare original, each active wall tangent, zero.
        candidates = [residual, (0.0, 0.0)]
        for normal, _ in hits:
            dot = residual[0] * normal[0] + residual[1] * normal[1]
            candidates.append(
                (residual[0] - dot * normal[0], residual[1] - dot * normal[1])
            )
        feasible = [
            v
            for v in candidates
            if all(v[0] * n[0] + v[1] * n[1] <= tolerance for n, _ in hits)
        ]
        remaining = min(
            feasible,
            key=lambda v: (
                (v[0] - residual[0]) ** 2 + (v[1] - residual[1]) ** 2,
                candidates.index(v),
            ),
        )
    raise ArithmeticError("arena boundary sweep exceeded edge_count+1 contacts")
