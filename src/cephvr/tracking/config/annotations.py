"""Pure source-coordinate annotation checks shared by editing and preparation."""

from __future__ import annotations

import math

from cephvr.tracking.config.models.records import Point, Triplet
from cephvr.tracking.v1 import pose_pb2


def point(value: pose_pb2.ImagePoint, width: int, height: int) -> tuple[float, float]:
    if not value.HasField("x_px") or not value.HasField("y_px"):
        raise ValueError("point requires explicit x_px and y_px")
    x, y = value.x_px, value.y_px
    if (
        not math.isfinite(x)
        or not math.isfinite(y)
        or not 0 <= x <= width - 1
        or not 0 <= y <= height - 1
    ):
        raise ValueError("point lies outside acquired-image pixel centres")
    return x, y


def reference(value: pose_pb2.SubjectReferenceSettings) -> tuple[int, int]:
    width, height = value.image_width_px, value.image_height_px
    if width <= 0 or height <= 0:
        raise ValueError("subject reference requires positive source dimensions")
    points = {
        name: point(getattr(value, name), width, height)
        for name in ("anterior", "posterior", "medial_left", "medial_right")
    }
    if (
        points["anterior"] == points["posterior"]
        or points["medial_left"] == points["medial_right"]
    ):
        raise ValueError("subject direction references must not coincide")
    return width, height


def manual(value: pose_pb2.ManualPoseSettings) -> Triplet:
    width, height = value.image_width_px, value.image_height_px
    if width <= 0 or height <= 0:
        raise ValueError("manual pose requires positive source dimensions")
    points = {
        name: Point(x_px=xy[0], y_px=xy[1])
        for name in ("tip", "left_base", "right_base")
        for xy in (point(getattr(value.landmarks, name), width, height),)
    }
    return Triplet(**points)


def search(value: pose_pb2.PoseSearchRegion, width: int, height: int) -> None:
    if any(
        not value.HasField(name) for name in ("x_px", "y_px", "width_px", "height_px")
    ):
        raise ValueError("automatic pose requires an explicit search rectangle")
    if (
        value.width_px <= 0
        or value.height_px <= 0
        or value.x_px + value.width_px > width
        or value.y_px + value.height_px > height
    ):
        raise ValueError("pose search rectangle exceeds the acquired image")
