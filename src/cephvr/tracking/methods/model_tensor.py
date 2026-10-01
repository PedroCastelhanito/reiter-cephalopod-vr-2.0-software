"""T11 reusable centre-aligned letterbox and strict exported triplet decoding."""

from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np

from cephvr.tracking.config.models.methods import ModelManifest, ModelSettings
from cephvr.tracking.methods.images import GrayPreparation, pixels
from cephvr.tracking.methods.landmarks import qualified
from cephvr.tracking.types import ImageLayout, PoseCandidate, PrivateFrame
from cephvr.tracking.v1.pose_pb2 import PoseSearchRegion


class ModelTensor:
    def __init__(
        self, manifest: ModelManifest, layout: ImageLayout, search: PoseSearchRegion
    ) -> None:
        self.manifest, self.layout, self.search = manifest, layout, search
        self.gray = GrayPreparation(layout)
        w, h = manifest.input_width_px, manifest.input_height_px
        ratio = min(w / search.width_px, h / search.height_px)
        self.rw = max(1, min(w, math.floor(search.width_px * ratio + 0.5)))
        self.rh = max(1, min(h, math.floor(search.height_px * ratio + 0.5)))
        self.left, self.top = (w - self.rw) // 2, (h - self.rh) // 2
        self.sx, self.sy = self.rw / search.width_px, self.rh / search.height_px
        channels = 1 if manifest.channels == "gray" else 3
        self.tensor = np.empty((1, channels, h, w), dtype=np.float32)
        self.resized = np.empty((self.rh, self.rw, channels), dtype=np.float32)
        self.crop = np.empty(
            (search.height_px, search.width_px, channels), dtype=np.float32
        )

    def prepare(self, frame: PrivateFrame) -> Any:
        s, m = self.search, self.manifest
        if m.channels == "gray":
            self.crop[:, :, 0] = self.gray.source_gray(frame)[
                s.y_px : s.y_px + s.height_px, s.x_px : s.x_px + s.width_px
            ]
        else:
            source = pixels(frame)[
                s.y_px : s.y_px + s.height_px, s.x_px : s.x_px + s.width_px
            ]
            self.crop[:] = source
            if self.layout.channels == "gray":
                self.crop[:] = source[:, :, 0, None]
            if self.layout.storage == "uint16" and self.layout.alignment == "msb":
                self.crop /= 1 << (16 - self.layout.effective_bits)
        if (
            not np.isfinite(self.crop).all()
            or self.crop.min() < 0
            or self.crop.max() > self.layout.maximum_code
        ):
            raise ValueError("model source intensity outside declared range")
        cv2.resize(
            self.crop,
            (self.rw, self.rh),
            dst=self.resized,
            interpolation=cv2.INTER_LINEAR,
        )
        for c in range(self.tensor.shape[1]):
            self.tensor[0, c].fill(
                (m.padding_source_fraction[c] - m.mean[c]) / m.std[c]
            )
            target = self.tensor[
                0, c, self.top : self.top + self.rh, self.left : self.left + self.rw
            ]
            np.divide(self.resized[:, :, c], self.layout.maximum_code, out=target)
            np.subtract(target, m.mean[c], out=target)
            np.divide(target, m.std[c], out=target)
        return self.tensor

    def candidates(
        self, output: Any, settings: ModelSettings
    ) -> tuple[PoseCandidate, ...]:
        m, s = self.manifest, self.search
        if (
            output.dtype != np.float32
            or output.ndim != 3
            or output.shape[0] != 1
            or output.shape[2] != 10
            or output.shape[1] > m.maximum_candidates
        ):
            raise ValueError("ONNX output violates exported [1,K,10] float32 contract")
        result = []
        for index, row in enumerate(output[0]):
            scores = row[[0, 3, 6, 9]]
            if not np.isfinite(row).all() or np.any(scores < 0) or np.any(scores > 1):
                raise ValueError("malformed ONNX candidate values")
            if (
                row[0] == 0
                or row[0] < settings.minimum_candidate_score
                or np.any(scores[1:] < settings.minimum_landmark_score)
            ):
                continue
            points = []
            for j in (1, 4, 7):
                x = (float(row[j]) - self.left + 0.5) / self.sx - 0.5 + s.x_px
                y = (float(row[j + 1]) - self.top + 0.5) / self.sy - 0.5 + s.y_px
                points.append((x, y))
            if any(
                not s.x_px <= x <= s.x_px + s.width_px - 1
                or not s.y_px <= y <= s.y_px + s.height_px - 1
                for x, y in points
            ):
                continue
            candidate = PoseCandidate(
                index, float(row[0]), (points[0], points[1], points[2])
            )
            if qualified(
                candidate,
                self.layout.width,
                self.layout.height,
                settings.geometry_quality,
            ):
                result.append(candidate)
        return tuple(result)
