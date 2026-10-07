"""T06 native-depth threshold, component moments and observed boundary extrema."""

from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np

from cephvr.tracking.config.annotations import reference as validate_reference
from cephvr.tracking.config.annotations import search as validate_search
from cephvr.tracking.config.models.methods import ContourSettings, FileLimits
from cephvr.tracking.methods.images import GrayPreparation
from cephvr.tracking.methods.landmarks import qualified
from cephvr.tracking.types import ImageLayout, PoseCandidate, PrivateFrame
from cephvr.tracking.v1.pose_pb2 import PoseSearchRegion, SubjectReferenceSettings


class ContourPose:
    def prepare(
        self,
        settings: ContourSettings,
        layout: ImageLayout,
        search: PoseSearchRegion,
        reference: SubjectReferenceSettings,
        asset_root: str,
        limits: FileLimits,
        *,
        reference_is_transformed: bool = False,
    ) -> None:
        validate_search(search, layout.width, layout.height)
        if (reference.image_width_px, reference.image_height_px) != (
            layout.width,
            layout.height,
        ):
            raise ValueError("reference dimensions differ from prepared image")
        if reference_is_transformed:
            _validate_transformed_reference(reference)
        else:
            validate_reference(reference)
        if not 0 <= settings.threshold_level <= layout.maximum_code:
            raise ValueError("threshold outside native intensity range")
        if layout.width * layout.height * 40 > limits.max_native_bytes:
            raise ValueError("contour workspace exceeds prepared budget")
        self.settings, self.layout = settings, layout
        self.crop = (search.x_px, search.y_px, search.width_px, search.height_px)
        self.head = np.array(
            [
                reference.anterior.x_px - reference.posterior.x_px,
                reference.anterior.y_px - reference.posterior.y_px,
            ]
        )
        self.left = np.array(
            [
                reference.medial_left.x_px - reference.medial_right.x_px,
                reference.medial_left.y_px - reference.medial_right.y_px,
            ]
        )
        self.gray = GrayPreparation(layout)
        self.mask = np.empty((search.height_px, search.width_px), dtype=np.uint8)
        self.component = np.empty_like(self.mask)

    def compute(self, frame: PrivateFrame) -> tuple[PoseCandidate, ...]:
        x, y, w, h = self.crop
        gray = self.gray.source_gray(frame)[y : y + h, x : x + w]
        compare = (
            np.less_equal if self.settings.foreground_polarity == "dark" else np.greater
        )
        compare(gray, self.settings.threshold_level, out=self.mask)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(
            self.mask, connectivity=8, ltype=cv2.CV_32S
        )
        candidates = []
        for index in range(1, count):
            sx, sy, sw, sh, area = (int(v) for v in stats[index])
            if (
                not self.settings.minimum_area_px2
                <= area
                <= self.settings.maximum_area_px2
            ):
                continue
            if sx == 0 or sy == 0 or sx + sw == w or sy + sh == h:
                continue
            np.equal(labels, index, out=self.component)
            moments = cv2.moments(self.component, binaryImage=True)
            covariance = (
                np.array(
                    [
                        [moments["mu20"], moments["mu11"]],
                        [moments["mu11"], moments["mu02"]],
                    ]
                )
                / area
            )
            values, vectors = np.linalg.eigh(covariance)
            if (
                values[0] < 0
                or values.sum() <= 0
                or (values[1] - values[0]) / values.sum()
                < self.settings.minimum_axis_anisotropy
            ):
                continue
            axis = vectors[:, 1]
            dot = float(axis @ self.head)
            if dot == 0:
                continue
            axis *= 1 if dot > 0 else -1
            lateral = np.array([-axis[1], axis[0]])
            dot = float(lateral @ self.left)
            if dot == 0:
                continue
            lateral *= 1 if dot > 0 else -1
            contours, _ = cv2.findContours(
                self.component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            boundary = np.concatenate(contours).reshape(-1, 2).astype(np.float64)
            centre = np.array([moments["m10"] / area, moments["m01"] / area])
            local = boundary - centre
            longitudinal, transverse = local @ axis, local @ lateral
            posterior = min(
                range(len(boundary)),
                key=lambda i: (
                    longitudinal[i],
                    abs(transverse[i]),
                    boundary[i, 1],
                    boundary[i, 0],
                ),
            )
            left = np.flatnonzero((longitudinal > 0) & (transverse > 0))
            right = np.flatnonzero((longitudinal > 0) & (transverse < 0))
            if not len(left) or not len(right):
                continue
            li = min(
                left,
                key=lambda i: (
                    -longitudinal[i],
                    -transverse[i],
                    boundary[i, 1],
                    boundary[i, 0],
                ),
            )
            ri = min(
                right,
                key=lambda i: (
                    -longitudinal[i],
                    transverse[i],
                    boundary[i, 1],
                    boundary[i, 0],
                ),
            )
            points: Any = tuple(
                (float(boundary[i, 0] + x), float(boundary[i, 1] + y))
                for i in (posterior, li, ri)
            )
            candidate = PoseCandidate(index, float(area), points)
            tip, lb, rb = np.array(points)
            if ((lb + rb) / 2 - tip) @ axis <= 0 or (lb - rb) @ lateral <= 0:
                continue
            if qualified(
                candidate,
                self.layout.width,
                self.layout.height,
                self.settings.geometry_quality,
            ):
                candidates.append(candidate)
        return tuple(candidates)

    def reset(self, generation: str) -> None:
        pass

    def close(self, deadline_host_ns: int) -> bool:
        return True


def _validate_transformed_reference(reference: SubjectReferenceSettings) -> None:
    coordinates = []
    for name in ("anterior", "posterior", "medial_left", "medial_right"):
        point = getattr(reference, name)
        if not point.HasField("x_px") or not point.HasField("y_px"):
            raise ValueError("transformed subject reference requires complete points")
        coordinates.append((point.x_px, point.y_px))
    if not all(math.isfinite(value) for point in coordinates for value in point):
        raise ValueError("transformed subject reference points must be finite")
    anterior, posterior, medial_left, medial_right = coordinates
    if anterior == posterior or medial_left == medial_right:
        raise ValueError("transformed subject reference directions must be nonzero")
