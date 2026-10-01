"""T01/T07 source-depth interpretation and explicit gray8 feature conversion."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from cephvr.tracking.types import ImageLayout, PrivateFrame


def validate_layout(layout: ImageLayout) -> None:
    size = {"uint8": 1, "uint16": 2, "float32": 4}[layout.storage]
    channels = 1 if layout.channels == "gray" else 3
    if (
        min(layout.width, layout.height) <= 0
        or layout.row_stride_bytes < layout.width * channels * size
        or not math.isfinite(layout.maximum_code)
        or layout.minimum_code != 0
        or layout.maximum_code <= 0
    ):
        raise ValueError("invalid prepared source layout/range")
    if layout.storage != "float32" and not 0 < layout.effective_bits <= size * 8:
        raise ValueError("effective depth exceeds storage")


def pixels(frame: PrivateFrame) -> Any:
    layout = frame.layout
    validate_layout(layout)
    dtype = np.dtype({"uint8": "u1", "uint16": "<u2", "float32": "<f4"}[layout.storage])
    channels = 1 if layout.channels == "gray" else 3
    row = layout.width * channels * dtype.itemsize
    if not frame.pixels.readonly or not frame.pixels.c_contiguous:
        raise ValueError("private input must be a contiguous read-only lease")
    if frame.pixels.nbytes < (layout.height - 1) * layout.row_stride_bytes + row:
        raise ValueError("private image span is truncated")
    return np.ndarray(
        (layout.height, layout.width, channels),
        dtype=dtype,
        buffer=frame.pixels,
        strides=(layout.row_stride_bytes, channels * dtype.itemsize, dtype.itemsize),
    )


class GrayPreparation:
    """Worker-owned reusable float32 native code and uint8 feature buffers."""

    def __init__(self, layout: ImageLayout) -> None:
        validate_layout(layout)
        self.layout = layout
        self.gray = np.empty((layout.height, layout.width), dtype=np.float32)
        self.scratch = np.empty_like(self.gray)
        self.gray8 = np.empty(self.gray.shape, dtype=np.uint8)

    def source_gray(self, frame: PrivateFrame) -> Any:
        if frame.layout != self.layout:
            raise ValueError("frame layout changed after preparation")
        image = pixels(frame)
        scale = 1.0
        if self.layout.storage == "uint16" and self.layout.alignment == "msb":
            scale = 1.0 / (1 << (16 - self.layout.effective_bits))
        if self.layout.channels == "gray":
            np.multiply(image[..., 0], scale, out=self.gray, casting="unsafe")
        else:
            # Shared A01 fixed RGB luminance coefficients; preserve fractional codes.
            np.multiply(image[..., 0], scale * 0.299, out=self.gray, casting="unsafe")
            for channel, coefficient in ((1, 0.587), (2, 0.114)):
                np.multiply(
                    image[..., channel],
                    scale * coefficient,
                    out=self.scratch,
                    casting="unsafe",
                )
                np.add(self.gray, self.scratch, out=self.gray)
        if (
            not np.isfinite(self.gray).all()
            or self.gray.min() < 0
            or self.gray.max() > self.layout.maximum_code
        ):
            raise ValueError("pixels outside declared source code range")
        return self.gray

    def feature(self, frame: PrivateFrame) -> Any:
        self.source_gray(frame)
        np.multiply(self.gray, 255.0 / self.layout.maximum_code, out=self.scratch)
        np.add(self.scratch, 0.5, out=self.scratch)
        np.floor(self.scratch, out=self.scratch)
        np.copyto(self.gray8, self.scratch, casting="unsafe")
        return self.gray8
