"""T17/T21 candidate geometry gates and deterministic selection."""

from __future__ import annotations

import math

from cephvr.tracking.config.models.methods import LandmarkQuality
from cephvr.tracking.types import PoseCandidate


def qualified(
    candidate: PoseCandidate, width: int, height: int, quality: LandmarkQuality
) -> bool:
    points = candidate.landmarks
    if not math.isfinite(candidate.score) or candidate.score <= 0:
        return False
    if any(
        not math.isfinite(x)
        or not math.isfinite(y)
        or not 0 <= x <= width - 1
        or not 0 <= y <= height - 1
        for x, y in points
    ):
        return False
    tip, left, right = points
    axis = math.hypot(
        (left[0] + right[0]) / 2 - tip[0], (left[1] + right[1]) / 2 - tip[1]
    )
    base = math.dist(left, right)
    area = (
        abs(
            (left[0] - tip[0]) * (right[1] - tip[1])
            - (left[1] - tip[1]) * (right[0] - tip[0])
        )
        / 2
    )
    return (
        axis >= quality.minimum_axis_px
        and base >= quality.minimum_base_width_px
        and area >= quality.minimum_triangle_area_px2
    )


def select(candidates: tuple[PoseCandidate, ...]) -> tuple[PoseCandidate | None, bool]:
    if not candidates:
        return None, False
    ordered = sorted(candidates, key=lambda c: (-c.score, c.landmarks))
    return ordered[0], len(ordered) > 1 and ordered[0].score == ordered[1].score
