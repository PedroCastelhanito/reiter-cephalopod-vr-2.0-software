"""Pure projection of 2D stimuli onto calibrated physical surfaces."""

from __future__ import annotations

import math
from typing import Any

from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.rendering.types import InstanceSnapshot


def physical_corners(
    artifact: PreparedTrial,
    snapshot: InstanceSnapshot,
    surface_id: str,
    surface_map: Any,
) -> list[tuple[float, float]]:
    values = dict(snapshot.state)
    matrix = surface_map.matrix
    determinant = matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]
    if abs(determinant) < 1e-15:
        raise RuntimeError("prepared physical surface map is singular")
    width, height = float(values["width"]), float(values["height"])
    center_x, center_y = float(values["x"]), float(values["y"])
    angle = math.radians(float(values.get("rotation", 0.0)))
    surface = next(
        item
        for item in artifact.display.geometry.surfaces
        if item.surface_id == surface_id
    )
    extent_x = math.dist(surface.bottom_left_mm, surface.bottom_right_mm)
    extent_y = math.dist(surface.bottom_left_mm, surface.top_left_mm)
    corners = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        x = (
            center_x
            + sx * width * 0.5 * math.cos(angle)
            - sy * height * 0.5 * math.sin(angle)
        )
        y = (
            center_y
            + sx * width * 0.5 * math.sin(angle)
            + sy * height * 0.5 * math.cos(angle)
        )
        tx, ty = x - matrix[0][2], y - matrix[1][2]
        local_x = (matrix[1][1] * tx - matrix[0][1] * ty) / determinant
        local_y = (-matrix[1][0] * tx + matrix[0][0] * ty) / determinant
        corners.append((2 * local_x / extent_x, 2 * local_y / extent_y))
    return corners


def angular_corners(
    artifact: PreparedTrial, snapshot: InstanceSnapshot, surface_id: str
) -> list[tuple[float, float]]:
    settings = snapshot.settings
    if (
        settings is None
        or settings.kind == "arena"
        or settings.space.kind != "visual_angle"
    ):
        raise RuntimeError("visual-angle projection requires a 2D angular instance")
    values = dict(snapshot.state)
    width, height = float(values["width"]), float(values["height"])
    center_x, center_y = float(values["x"]), float(values["y"])
    rotation = math.radians(float(values.get("rotation", 0.0)))
    qx, qy, qz, qw = settings.space.frame_to_rig_xyzw
    observer = artifact.display.geometry.observer_mm
    surface = next(
        item
        for item in artifact.display.geometry.surfaces
        if item.surface_id == surface_id
    )
    bl, br, tl = (
        surface.bottom_left_mm,
        surface.bottom_right_mm,
        surface.top_left_mm,
    )
    right = tuple(br[i] - bl[i] for i in range(3))
    up = tuple(tl[i] - bl[i] for i in range(3))

    def dot(a: tuple[float, ...], b: tuple[float, ...]) -> float:
        return sum(x * y for x, y in zip(a, b, strict=True))

    def cross(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, float, float]:
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )

    normal = cross(right, up)
    corners = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        angle_x = center_x + sx * width * 0.5
        angle_y = center_y + sy * height * 0.5
        local_x = angle_x * math.cos(rotation) - angle_y * math.sin(rotation)
        local_y = angle_x * math.sin(rotation) + angle_y * math.cos(rotation)
        x, y = math.tan(math.radians(local_x)), math.tan(math.radians(local_y))
        # Apply the accepted unit-quaternion transform to the local ray.
        cross1 = (qy * 1.0 - qz * y, qz * x - qx * 1.0, qx * y - qy * x)
        cross2 = (
            qy * cross1[2] - qz * cross1[1],
            qz * cross1[0] - qx * cross1[2],
            qx * cross1[1] - qy * cross1[0],
        )
        direction = (
            x + 2 * (qw * cross1[0] + cross2[0]),
            y + 2 * (qw * cross1[1] + cross2[1]),
            1.0 + 2 * (qw * cross1[2] + cross2[2]),
        )
        denominator = dot(direction, normal)
        if abs(denominator) < 1e-12:
            raise RuntimeError("visual-angle ray is parallel to mapped surface")
        t = dot(tuple(bl[i] - observer[i] for i in range(3)), normal) / denominator
        if t <= 0:
            raise RuntimeError(
                "visual-angle ray does not meet mapped surface in front of observer"
            )
        point = tuple(observer[i] + t * direction[i] for i in range(3))
        relative = tuple(point[i] - bl[i] for i in range(3))
        corners.append(
            (
                2 * dot(relative, right) / dot(right, right),
                2 * dot(relative, up) / dot(up, up),
            )
        )
    return corners
