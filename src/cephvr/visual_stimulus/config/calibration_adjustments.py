"""Bounded normalized rectangles for live GUI affine calibration updates."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .calibration_placement import CalibrationPlacement
from collections.abc import Iterable, Sequence

LIVE_ADJUSTABLE_VIEWS = frozenset(
    {"frame_grid", "photodiode_placement", "blackout_placement"}
)


def validated_update(
    view: str, items: Iterable[tuple[str, Sequence[float]]], placement_json: str = ""
) -> dict[str, tuple[tuple[float, float], ...]] | CalibrationPlacement:
    from .calibration_placement import PLACEMENT_VIEWS, parse_placement

    items = tuple(items)
    if view in PLACEMENT_VIEWS:
        if items or not placement_json:
            raise CalibrationAdjustmentRejected(
                "Placement requires one complete output snapshot"
            )
        placement = parse_placement(placement_json)
        placement.validate_view(view)
        return placement
    if view != "frame_grid" or placement_json:
        raise CalibrationAdjustmentRejected(
            "Update does not match the active calibration view"
        )
    return validated_adjustments(items)


class CalibrationAdjustmentRejected(ValueError):
    """Validation rejected before any active GL resource was changed."""


def validated_adjustments(
    items: Iterable[tuple[str, Sequence[float]]],
) -> dict[str, tuple[tuple[float, float], ...]]:
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
        a, b, c, d = points
        if (
            a[1] != b[1]
            or c[1] != d[1]
            or a[0] != c[0]
            or b[0] != d[0]
            or a[0] == b[0]
            or a[1] == c[1]
        ):
            raise CalibrationAdjustmentRejected(
                "Live calibration requires a nondegenerate affine rectangle"
            )
        result[mapping_id] = points
    if not 1 <= len(result) <= 4:
        raise CalibrationAdjustmentRejected(
            "Live calibration requires one to four mapping adjustments"
        )
    return result


def affine_vertices(
    sx: float,
    sy: float,
    center_x: float,
    center_y: float,
    *,
    quarter_turn: bool = False,
) -> tuple[dict[str, tuple[float, float]], ...]:
    """Clip at fixed pitch; optional +90-degree surface rotation precedes output flips."""
    if (
        not all(math.isfinite(v) for v in (sx, sy, center_x, center_y))
        or sx == 0
        or sy == 0
    ):
        raise CalibrationAdjustmentRejected("Invalid fixed-pitch affine image")

    def axis(
        scale: float, center: float
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        a, b = center - scale / 2, center + scale / 2
        ca, cb = max(0.0, min(1.0, a)), max(0.0, min(1.0, b))
        if ca == cb:
            raise CalibrationAdjustmentRejected("Mapped image is outside its display")
        return (max(0.0, min(1.0, (ca - a) / scale)), ca), (
            max(0.0, min(1.0, (cb - a) / scale)),
            cb,
        )

    x, y = axis(sx, center_x), axis(sy, center_y)
    return tuple(
        dict(
            uv=(y[j][0], 1 - x[i][0]) if quarter_turn else (x[i][0], y[j][0]),
            xy=(x[i][1], y[j][1]),
        )
        for j in (0, 1)
        for i in (0, 1)
    )
