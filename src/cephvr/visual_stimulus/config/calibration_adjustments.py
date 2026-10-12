"""Bounded normalized rectangles for live GUI affine calibration updates."""

import math
from collections.abc import Iterable, Sequence


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
