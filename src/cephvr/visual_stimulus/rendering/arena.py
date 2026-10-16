"""Pure arena model and off-axis surface transform preparation (V15–V18)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, cast

from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile, Surface
from cephvr.visual_stimulus.rendering.projection import (
    off_axis_frustum,
    projection_matrix,
)
from cephvr.visual_stimulus.rendering.types import InstanceSnapshot, PoseSnapshot

Matrix4 = tuple[tuple[float, float, float, float], ...]


def _multiply(
    left: Sequence[Sequence[float]], right: Sequence[Sequence[float]]
) -> Matrix4:
    return cast(
        Matrix4,
        tuple(
            tuple(
                sum(left[row][k] * right[k][column] for k in range(4))
                for column in range(4)
            )
            for row in range(4)
        ),
    )


def _rotation_x(degrees: float) -> Matrix4:
    angle = math.radians(degrees)
    cosine, sine = math.cos(angle), math.sin(angle)
    return ((1, 0, 0, 0), (0, cosine, -sine, 0), (0, sine, cosine, 0), (0, 0, 0, 1))


def _rotation_y(degrees: float) -> Matrix4:
    angle = math.radians(degrees)
    cosine, sine = math.cos(angle), math.sin(angle)
    return ((cosine, 0, sine, 0), (0, 1, 0, 0), (-sine, 0, cosine, 0), (0, 0, 0, 1))


def _rotation_z(degrees: float) -> Matrix4:
    angle = math.radians(degrees)
    cosine, sine = math.cos(angle), math.sin(angle)
    return ((cosine, -sine, 0, 0), (sine, cosine, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))


def _pose_values(
    settings: Any, state: dict[str, float | int | str | bool]
) -> tuple[float, float, float, float, float, float]:
    x, y, yaw = (float(state[key]) for key in ("x", "y", "yaw"))
    height = float(settings.fixed_height_mm)
    pitch, roll = float(settings.fixed_pitch_deg), float(settings.fixed_roll_deg)
    values = (x, y, yaw, height, pitch, roll)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("arena pose and fixed orientation must be finite")
    return values


def effective_arena_pose(snapshot: InstanceSnapshot) -> PoseSnapshot:
    """Retain the shared rigid pose before the authored asset transform (V13/V16)."""
    settings = snapshot.settings
    if settings is None or settings.kind != "arena":
        raise ValueError("effective arena pose requires arena settings")
    x, y, yaw, height, pitch, roll = _pose_values(settings, dict(snapshot.state))
    sz, cz = math.sin(math.radians(yaw) / 2), math.cos(math.radians(yaw) / 2)
    sx, cx = math.sin(math.radians(pitch) / 2), math.cos(math.radians(pitch) / 2)
    sy, cy = math.sin(math.radians(roll) / 2), math.cos(math.radians(roll) / 2)
    # Match the exact Rz(yaw) Rx(pitch) Ry(roll) order used for rendering.
    orientation = (
        cz * sx * cy - sz * cx * sy,
        cz * cx * sy + sz * sx * cy,
        sz * cx * cy + cz * sx * sy,
        cz * cx * cy - sz * sx * sy,
    )
    return PoseSnapshot(
        snapshot.instance_id, settings.world_frame_id, (x, y, height), orientation
    )


def arena_model_matrix(
    settings: Any, state: dict[str, float | int | str | bool]
) -> Matrix4:
    """Compose effective virtual observer pose with authored asset-to-world data."""
    x, y, yaw, height, pitch, roll = _pose_values(settings, state)
    translation: Matrix4 = ((1, 0, 0, x), (0, 1, 0, y), (0, 0, 1, height), (0, 0, 0, 1))
    authored: Matrix4 = settings.asset_to_world
    model = _multiply(translation, _rotation_z(yaw))
    model = _multiply(model, _rotation_x(pitch))
    model = _multiply(model, _rotation_y(roll))
    return _multiply(model, authored)


def off_axis_view_projection(display: DisplayProfile, surface: Surface) -> Matrix4:
    """Build Kooima off-axis projection times the fixed physical observer view."""
    eye = display.geometry.observer_mm
    bl, br, tl = surface.bottom_left_mm, surface.bottom_right_mm, surface.top_left_mm
    frustum = off_axis_frustum(
        observer=eye,
        bottom_left=bl,
        bottom_right=br,
        top_left=tl,
        near=display.geometry.near_mm,
        far=display.geometry.far_mm,
    )
    projection = _from_column_major(
        projection_matrix(frustum, display.geometry.near_mm, display.geometry.far_mm)
    )
    right = _unit(_subtract(br, bl))
    up = _unit(_subtract(tl, bl))
    normal = _unit(_cross(right, up))
    view = cast(
        Matrix4,
        (
            (*right, -_dot(right, eye)),
            (*up, -_dot(up, eye)),
            (*normal, -_dot(normal, eye)),
            (0, 0, 0, 1),
        ),
    )
    return _multiply(projection, view)


def gl_matrix_words(matrix: Matrix4) -> tuple[int, ...]:
    """Return column-major float32 words for the exact GLSL mat4 upload."""
    import struct

    return tuple(
        struct.unpack("<I", struct.pack("<f", matrix[row][column]))[0]
        for column in range(4)
        for row in range(4)
    )


def _from_column_major(values: Sequence[float]) -> Matrix4:
    return cast(
        Matrix4,
        tuple(
            tuple(values[column * 4 + row] for column in range(4)) for row in range(4)
        ),
    )


def _subtract(
    left: Sequence[float], right: Sequence[float]
) -> tuple[float, float, float]:
    return tuple(left[index] - right[index] for index in range(3))  # type: ignore[return-value]


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(left[index] * right[index] for index in range(3))


def _cross(left: Sequence[float], right: Sequence[float]) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _unit(vector: Sequence[float]) -> tuple[float, float, float]:
    length = math.sqrt(_dot(vector, vector))
    if not math.isfinite(length) or length <= 0:
        raise ValueError("arena view has a degenerate physical basis")
    return tuple(value / length for value in vector)  # type: ignore[return-value]
