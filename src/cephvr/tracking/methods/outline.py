"""T32 bounded adaptive outline, anatomical posterior origin and arc projection."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def outline(
    a: float, b: float, taper: float, power: float, maximum_vertices: int
) -> Any:
    def at(t: float) -> Any:
        cardinal = {
            0.0: (-a, 0.0),
            math.pi / 2: (0.0, b),
            math.pi: (a, 0.0),
            3 * math.pi / 2: (0.0, -b),
            2 * math.pi: (-a, 0.0),
        }
        if t in cardinal:
            return np.array(cardinal[t])
        c, s = -math.cos(t), math.sin(t)
        x = a * math.copysign(abs(c) ** (2 / power), c)
        return np.array(
            [x, b * (1 - taper * x / a) * math.copysign(abs(s) ** (2 / power), s)]
        )

    pending = [(i * math.pi / 2, (i + 1) * math.pi / 2) for i in reversed(range(4))]
    points = [at(0.0)]
    while pending:
        lo, hi = pending.pop()
        probe = np.array([at(lo + (hi - lo) * i / 4) for i in range(5)])
        chord = probe[-1] - probe[0]
        square = float(chord @ chord)
        if square <= 0 or not np.isfinite(probe).all():
            raise ValueError("unrepresentable outline refinement")
        fractions = np.clip((probe[1:4] - probe[0]) @ chord / square, 0, 1)
        error = np.linalg.norm(
            probe[1:4] - probe[0] - fractions[:, None] * chord, axis=1
        ).max()
        refined = np.linalg.norm(np.diff(probe, axis=0), axis=1).sum()
        if error <= 0.01 and (refined - math.sqrt(square)) / refined <= 0.0001:
            points.append(probe[-1])
        else:
            mid = (lo + hi) / 2
            if mid in (lo, hi):
                raise ValueError("float64 outline refinement exhausted")
            pending.extend(((mid, hi), (lo, mid)))
        if len(points) + len(pending) > maximum_vertices:
            raise ValueError("outline workspace exhausted")
    return np.array(points, dtype=np.float64)


def project_sections(points: Any, curve: Any, count: int, tile_bytes: int) -> Any:
    """Project segment interiors; exact distance ties select lowest wrapped arc."""
    if count <= 0 or tile_bytes < 1024:
        raise ValueError("invalid section workspace")
    delta = np.diff(curve, axis=0)
    length = np.linalg.norm(delta, axis=1)
    perimeter = math.fsum(length)
    if perimeter <= 0 or np.any(length <= 0):
        raise ValueError("degenerate outline")
    # Compensated prefix summation is linear in the number of outline segments.
    starts = np.empty(len(length), dtype=np.float64)
    total = correction = 0.0
    for index, value in enumerate(length):
        starts[index] = total
        adjusted = float(value) - correction
        updated = total + adjusted
        correction = (updated - total) - adjusted
        total = updated
    result = np.empty(len(points), dtype=np.uint32)
    # No pixels-by-entire-outline allocation. Each tile's temporary arrays are bounded.
    batch = max(1, tile_bytes // 256)
    for start in range(0, len(points), batch):
        xy = points[start : start + batch]
        best = np.full(len(xy), np.inf)
        arc = np.full(len(xy), np.inf)
        for index, direction in enumerate(delta):
            fraction = np.clip(
                (xy - curve[index]) @ direction / (length[index] ** 2), 0, 1
            )
            residual = xy - curve[index] - fraction[:, None] * direction
            distance = np.einsum("ij,ij->i", residual, residual)
            q = np.remainder(
                (starts[index] + fraction * length[index]) / perimeter, 1.0
            )
            replace = (distance < best) | ((distance == best) & (q < arc))
            best[replace], arc[replace] = distance[replace], q[replace]
        result[start : start + len(xy)] = np.floor(count * arc).astype(np.uint32)
    return result
