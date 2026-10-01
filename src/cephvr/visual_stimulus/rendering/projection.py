"""Four calibrated off-axis projector frusta and output correction geometry."""

from __future__ import annotations

import math
from collections.abc import Sequence

Vector3 = tuple[float, float, float]


def _sub(a: Vector3, b: Vector3) -> Vector3:
    return tuple(x - y for x, y in zip(a, b, strict=True))  # type: ignore[return-value]


def _dot(a: Vector3, b: Vector3) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def _cross(a: Vector3, b: Vector3) -> Vector3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _unit(a: Vector3) -> Vector3:
    length = math.sqrt(_dot(a, a))
    if not math.isfinite(length) or length <= 0:
        raise ValueError("degenerate projection basis")
    return tuple(x / length for x in a)  # type: ignore[return-value]


def off_axis_frustum(
    *,
    observer: Vector3,
    bottom_left: Vector3,
    bottom_right: Vector3,
    top_left: Vector3,
    near: float,
    far: float,
) -> tuple[float, float, float, float]:
    """Return OpenGL (left,right,bottom,top) planes for a physical rectangle."""
    if not (math.isfinite(near) and math.isfinite(far) and 0 < near < far):
        raise ValueError("finite positive near/far planes required")
    right = _unit(_sub(bottom_right, bottom_left))
    up = _unit(_sub(top_left, bottom_left))
    normal = _unit(_cross(right, up))
    distance = _dot(_sub(bottom_left, observer), normal)
    if distance <= 0:
        raise ValueError("observer must be in front of projection surface")
    scale = near / distance
    va, vb, vc = (
        _sub(bottom_left, observer),
        _sub(bottom_right, observer),
        _sub(top_left, observer),
    )
    left = _dot(right, va) * scale
    right_plane = _dot(right, vb) * scale
    bottom = _dot(up, va) * scale
    top = _dot(up, vc) * scale
    if not left < right_plane or not bottom < top:
        raise ValueError("projection rectangle is degenerate or reversed")
    return left, right_plane, bottom, top


def projection_matrix(
    frustum: Sequence[float], near: float, far: float
) -> tuple[float, ...]:
    if len(frustum) != 4:
        raise ValueError("frustum requires four planes")
    left, right, bottom, top = frustum
    if not (left < right and bottom < top and 0 < near < far):
        raise ValueError("invalid frustum")
    # Column-major OpenGL matrix.
    return (
        2 * near / (right - left),
        0,
        0,
        0,
        0,
        2 * near / (top - bottom),
        0,
        0,
        (right + left) / (right - left),
        (top + bottom) / (top - bottom),
        -(far + near) / (far - near),
        -1,
        0,
        0,
        -2 * far * near / (far - near),
        0,
    )


def apply_surface_map(
    matrix: Sequence[Sequence[float]], x_mm: float, y_mm: float
) -> tuple[float, float]:
    if len(matrix) != 2 or any(len(row) != 3 for row in matrix):
        raise ValueError("surface map must be 2x3 affine")
    if not all(math.isfinite(v) for row in matrix for v in row) or not all(
        math.isfinite(v) for v in (x_mm, y_mm)
    ):
        raise ValueError("finite coordinates and map required")
    return tuple(row[0] * x_mm + row[1] * y_mm + row[2] for row in matrix)  # type: ignore[return-value]
