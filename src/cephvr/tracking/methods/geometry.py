"""T25–T32 complete pre-clip raster band and exact immutable geometry ownership."""

from __future__ import annotations

import math
from typing import Any, cast
from uuid import uuid4

import cv2
import numpy as np

from cephvr.tracking.config.models.methods import EllipseSettings, FileLimits
from cephvr.tracking.config.models.records import Triplet
from cephvr.tracking.methods.outline import outline
from cephvr.tracking.types import ImageLayout, SamplingGeometry


class EllipseGeometry:
    def __init__(self, capacity: int = 2) -> None:
        if capacity < 1:
            raise ValueError("positive geometry lease capacity required")
        self.capacity = capacity

    def prepare(
        self, settings: EllipseSettings, layout: ImageLayout, limits: FileLimits
    ) -> None:
        self.settings, self.layout, self.maximum = (
            settings,
            layout,
            limits.max_native_bytes,
        )
        self.binding = str(uuid4())
        self.live: dict[str, tuple[SamplingGeometry, int]] = {}
        self.maximum_vertices = max(8, self.maximum // 8 // (256 + 16 * self.capacity))
        curve_bytes = self.maximum_vertices * (256 + 16 * self.capacity)
        self.maximum_pixels = (self.maximum - curve_bytes) // (96 + self.capacity)
        if self.maximum_pixels < 1:
            raise ValueError("geometry storage cannot fit preparation budget")
        self.coordinates = np.arange(self.maximum_pixels, dtype=np.float64)
        self.scratch = np.empty((4, self.maximum_pixels), dtype=np.float64)
        self.masks = np.empty((2, self.maximum_pixels), dtype=bool)
        self.body = np.empty((2, self.maximum_pixels), dtype=np.uint8)
        self.distance = np.empty(self.maximum_pixels, dtype=np.float32)
        self.bands = np.empty((self.capacity, self.maximum_pixels), dtype=np.uint8)
        self.curves = np.empty(
            (self.capacity, self.maximum_vertices, 2), dtype=np.float64
        )
        self.available = list(range(self.capacity))

    def compute(self, pose: Triplet) -> SamplingGeometry | None:
        tip, left, right = (
            np.array([p.x_px, p.y_px])
            for p in (pose.tip, pose.left_base, pose.right_base)
        )
        midpoint = (left + right) / 2
        d, w = (
            float(np.linalg.norm(midpoint - tip)),
            float(np.linalg.norm(left - right)),
        )
        if min(d, w) <= 0:
            return None
        settings = self.settings
        axis = (midpoint - tip) / d
        lateral = np.array([-axis[1], axis[0]])
        side = float(lateral @ (left - right))
        if side == 0:
            return None
        lateral *= 1 if side > 0 else -1
        a, b = d / (2 * settings.front_fraction), w / 2
        centre = tip + a * axis
        outer, inner = (
            w * settings.outer_extent_fraction,
            w * settings.inner_clearance_fraction,
        )
        # Conservative analytic extent, independent of display tessellation accuracy.
        extent = (
            a * np.abs(axis)
            + b * (1 + abs(settings.taper)) * np.abs(lateral)
            + outer
            + 2
        )
        bounds = np.concatenate((centre - extent, centre + extent))
        if not np.isfinite(bounds).all():
            raise ValueError("nonfinite geometry extent")
        x0, y0 = math.floor(bounds[0]), math.floor(bounds[1])
        x1, y1 = math.ceil(bounds[2]), math.ceil(bounds[3])
        width, height = x1 - x0 + 1, y1 - y0 + 1
        count = width * height
        if count > self.maximum_pixels or not self.available:
            raise ValueError("geometry exceeds prepared raster or lease capacity")
        slot = self.available[-1]
        curve = outline(
            a, b, settings.taper, settings.squareness, self.maximum_vertices
        )
        u, v, term, denominator = (
            array[:count].reshape(height, width) for array in self.scratch
        )
        inside, selected = (
            array[:count].reshape(height, width) for array in self.masks
        )
        body, inverse = (array[:count].reshape(height, width) for array in self.body)
        distance = self.distance[:count].reshape(height, width)
        band = self.bands[slot, :count].reshape(height, width)
        x = self.coordinates[:width] + (x0 - centre[0])
        y = self.coordinates[:height] + (y0 - centre[1])
        np.multiply(x[None, :], axis[0], out=u)
        u += y[:, None] * axis[1]
        u /= a
        np.multiply(x[None, :], lateral[0], out=v)
        v += y[:, None] * lateral[1]
        np.abs(u, out=term)
        np.less_equal(term, 1, out=inside)
        np.power(term, settings.squareness, out=term)
        # Outside-domain pixels stay excluded; clipping only keeps the unused
        # denominator positive and never extends the body predicate.
        np.clip(u, -1, 1, out=denominator)
        denominator *= -settings.taper
        denominator += 1
        denominator *= b
        np.divide(v, denominator, out=v)
        np.abs(v, out=v)
        np.power(v, settings.squareness, out=v)
        term += v
        np.less_equal(term, 1, out=selected)
        np.logical_and(inside, selected, out=selected)
        np.copyto(body, selected, casting="unsafe")
        if not body.any():
            return None
        np.subtract(1, body, out=inverse)
        cv2.distanceTransform(inverse, cv2.DIST_L2, cv2.DIST_MASK_PRECISE, dst=distance)
        np.copyto(denominator, distance)
        np.greater_equal(denominator, inner, out=selected)
        np.less(denominator, outer, out=inside)
        np.logical_and(inside, selected, out=selected)
        np.equal(body, 0, out=inside)
        np.logical_and(inside, selected, out=selected)
        np.copyto(band, selected, casting="unsafe")
        if not band.any():
            return None
        image_curve = self.curves[slot, : len(curve)]
        for coordinate in range(2):
            image_curve[:, coordinate] = (
                centre[coordinate]
                + curve[:, 0] * axis[coordinate]
                + curve[:, 1] * lateral[coordinate]
            )
        band.flags.writeable = False
        image_curve.flags.writeable = False
        key = str(uuid4())
        geometry = SamplingGeometry(
            key,
            self.binding,
            (x0, y0),
            memoryview(cast(Any, band)),
            width,
            height,
            memoryview(cast(Any, image_curve)),
            tuple(centre),
            tuple(axis),
            tuple(lateral),
        )
        self.available.pop()
        self.live[key] = (geometry, slot)
        return geometry

    def release(self, geometry: SamplingGeometry) -> None:
        current = self.live.get(geometry.lease_id)
        if current is None or current[0] is not geometry:
            raise ValueError("unknown or already released geometry lease")
        self.available.append(current[1])
        del self.live[geometry.lease_id]

    def reset(self, generation: str) -> None:
        # History owner returns every retired lease, including borrowed observations.
        pass

    def close(self, deadline_host_ns: int) -> bool:
        if self.live:
            return False
        for name in (
            "coordinates",
            "scratch",
            "masks",
            "body",
            "distance",
            "bands",
            "curves",
        ):
            if hasattr(self, name):
                delattr(self, name)
        return True
