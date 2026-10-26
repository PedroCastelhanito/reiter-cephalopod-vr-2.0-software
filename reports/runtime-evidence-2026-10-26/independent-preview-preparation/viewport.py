"""Private square display transforms; source and acquired coordinates stay intact."""

from __future__ import annotations

import math
from typing import Any


class SquareViewport:
    def __init__(self, width: int, height: int, side: int = 640) -> None:
        self.width, self.height, self.side = width, height, side
        self.fit = side / max(width, height)
        self.zoom = 1.0
        self.tx = (side - width * self.fit) / 2
        self.ty = (side - height * self.fit) / 2
        self.dirty = False
        self._pan_anchor: tuple[int, int] | None = None

    def resize(self, side: int) -> None:
        self.end_pan()
        ratio = side / self.side
        self.side = side
        self.fit = side / max(self.width, self.height)
        self.tx *= ratio
        self.ty *= ratio
        self._clamp()
        self.dirty = True

    def wheel(self, x: int, y: int, flags: int) -> None:
        self.end_pan()
        delta = (flags >> 16) & 0xFFFF
        if delta >= 0x8000:
            delta -= 0x10000
        previous = self.zoom
        self.zoom = max(
            1.0, min(16.0, self.zoom * 1.2 ** (max(-1200, min(1200, delta)) / 120))
        )
        ratio = self.zoom / previous
        self.tx = x - (x - self.tx) * ratio
        self.ty = y - (y - self.ty) * ratio
        self._clamp()
        self.dirty = self.dirty or self.zoom != previous

    def reset(self) -> None:
        self.end_pan()
        self.zoom = 1.0
        self._clamp()
        self.dirty = True

    def start_pan(self, x: int, y: int) -> None:
        self._pan_anchor = (x, y) if self.zoom > 1 else None

    def pan(self, x: int, y: int) -> None:
        if self._pan_anchor is None:
            return
        previous = self.tx, self.ty
        self.tx += x - self._pan_anchor[0]
        self.ty += y - self._pan_anchor[1]
        self._pan_anchor = x, y
        self._clamp()
        self.dirty |= (self.tx, self.ty) != previous

    def end_pan(self) -> None:
        self._pan_anchor = None

    def _clamp(self) -> None:
        scale = self.fit * self.zoom
        for name, extent in (("tx", self.width * scale), ("ty", self.height * scale)):
            setattr(
                self,
                name,
                (self.side - extent) / 2
                if extent <= self.side
                else max(self.side - extent, min(0.0, getattr(self, name))),
            )

    @property
    def transform(self) -> tuple[int, float, float, float, float]:
        """Immutable display identity for rejecting work superseded by native input."""
        return self.side, self.fit, self.zoom, self.tx, self.ty

    def render(self, frame: Any, cv: Any, numpy: Any) -> Any:
        scale = self.fit * self.zoom
        matrix = numpy.array(
            ((scale, 0, self.tx), (0, scale, self.ty)), dtype=numpy.float64
        )
        image = cv.warpAffine(
            frame,
            matrix,
            (self.side, self.side),
            flags=cv.INTER_LINEAR,
            borderMode=cv.BORDER_REPLICATE,
        )
        # Replicate edge samples for interpolation, then clear only true padding.
        x0, y0 = max(0, math.ceil(self.tx)), max(0, math.ceil(self.ty))
        x1 = min(self.side, math.ceil(self.tx + self.width * scale))
        y1 = min(self.side, math.ceil(self.ty + self.height * scale))
        image[:y0] = 0
        image[y1:] = 0
        image[:, :x0] = 0
        image[:, x1:] = 0
        self.dirty = False
        return image
