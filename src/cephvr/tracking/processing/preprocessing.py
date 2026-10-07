"""Private acquired-image preprocessing and source-coordinate transforms (T01/T20)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ImageTransform:
    """Actual per-axis pixel-centre mapping after crop and integer output sizing."""

    source_width: int
    source_height: int
    crop_x: int
    crop_y: int
    crop_width: int
    crop_height: int
    output_width: int
    output_height: int

    @property
    def scale_x(self) -> float:
        return self.output_width / self.crop_width

    @property
    def scale_y(self) -> float:
        return self.output_height / self.crop_height

    def source_to_output(self, point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        return (
            (x - self.crop_x + 0.5) * self.scale_x - 0.5,
            (y - self.crop_y + 0.5) * self.scale_y - 0.5,
        )

    def output_to_source(self, point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        return (
            self.crop_x + (x + 0.5) / self.scale_x - 0.5,
            self.crop_y + (y + 0.5) / self.scale_y - 0.5,
        )

    def source_region_to_output(
        self, x: int, y: int, width: int, height: int
    ) -> tuple[int, int, int, int]:
        """Map a right/bottom-exclusive source rectangle into bounded pixel indices."""
        left = max(x, self.crop_x)
        top = max(y, self.crop_y)
        right = min(x + width, self.crop_x + self.crop_width)
        bottom = min(y + height, self.crop_y + self.crop_height)
        if right <= left or bottom <= top:
            raise ValueError("region does not overlap the preprocessed crop")
        x0 = max(0, math.floor((left - self.crop_x) * self.scale_x))
        y0 = max(0, math.floor((top - self.crop_y) * self.scale_y))
        x1 = min(self.output_width, math.ceil((right - self.crop_x) * self.scale_x))
        y1 = min(self.output_height, math.ceil((bottom - self.crop_y) * self.scale_y))
        if x1 <= x0 or y1 <= y0:
            raise ValueError("region is empty after preprocessing")
        return x0, y0, x1 - x0, y1 - y0

    def apply(self, source: object, destination: object) -> None:
        """Crop then resize into caller-owned storage without changing pixel dtype."""
        import cv2
        import numpy as np

        source_array = np.asarray(source)
        expected = (self.source_height, self.source_width)
        if source_array.shape[:2] != expected:
            raise ValueError("source pixels do not match the declared image transform")
        target = np.asarray(destination)
        target_shape = (self.output_height, self.output_width, *source_array.shape[2:])
        if target.shape != target_shape or target.dtype != source_array.dtype:
            raise ValueError("destination pixels do not match transformed layout")
        crop = source_array[
            self.crop_y : self.crop_y + self.crop_height,
            self.crop_x : self.crop_x + self.crop_width,
        ]
        if crop.shape == target.shape:
            np.copyto(target, crop)
            return
        interpolation = cv2.INTER_AREA
        result = cv2.resize(
            crop,
            (self.output_width, self.output_height),
            dst=target,
            interpolation=interpolation,
        )
        if result is not target and not np.shares_memory(result, target):
            raise RuntimeError(
                "image resampler did not use bounded destination storage"
            )


def resolve_transform(
    source_width: int,
    source_height: int,
    *,
    crop_enabled: bool = False,
    crop: tuple[int, int, int, int] | None = None,
    scale_percent: int = 100,
) -> ImageTransform:
    if source_width <= 0 or source_height <= 0:
        raise ValueError("source image dimensions must be positive")
    if not 10 <= scale_percent <= 100:
        raise ValueError("downscale percentage must be within 10..100")
    if crop_enabled:
        if crop is None:
            raise ValueError("enabled crop requires a source-image rectangle")
        x, y, width, height = crop
        if (
            min(x, y) < 0
            or min(width, height) <= 0
            or x + width > source_width
            or y + height > source_height
        ):
            raise ValueError("crop rectangle exceeds the acquired image")
    else:
        x, y, width, height = 0, 0, source_width, source_height
    # Round half up once; the resulting actual x/y scales are retained for inverse mapping.
    output_width = max(1, (width * scale_percent + 50) // 100)
    output_height = max(1, (height * scale_percent + 50) // 100)
    return ImageTransform(
        source_width,
        source_height,
        x,
        y,
        width,
        height,
        output_width,
        output_height,
    )
