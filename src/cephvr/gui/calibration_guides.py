"""Simple physical calibration grid and screen identifiers."""

import math
from collections.abc import Callable
from typing import Protocol

Point = tuple[float, float, float]
Color = tuple[float, float, float, float]


class GuideMesh(Protocol):
    def quad(
        self, corners: tuple[Point, Point, Point, Point], color: Color
    ) -> None: ...
    def line(
        self, start: Point, end: Point, width: float, normal: Point, color: Color
    ) -> None: ...


# Five-column glyphs stay readable without a font dependency in the GLB asset.
GLYPHS = {
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
}


GRID = (0.35, 0.4, 0.45, 1.0)
WHITE = (1.0, 1.0, 1.0, 1.0)


def add_face_guides(
    mesh: GuideMesh,
    face: str,
    at: Callable[[float, float, float], Point],
    origin: Point,
    u: Point,
    v: Point,
    normal: Point,
    width: float,
    height: float,
    spacing: float,
    *,
    raster_size: tuple[int, int] | None = None,
) -> None:
    """Solid world-phase grid, a face border and one readable screen name."""
    if int(width / spacing) + int(height / spacing) > 1000:
        raise ValueError(f"{face} grid exceeds 1000 lines; increase spacing")
    stroke = min(0.2, spacing / 50)
    for vertical, direction, extent, length, pixels in (
        (True, u, width, height, None if raster_size is None else raster_size[0]),
        (False, v, height, width, None if raster_size is None else raster_size[1]),
    ):
        # Two source pixels survive fractional output translations and filtering.
        line_stroke = stroke if pixels is None else max(stroke, 2 * extent / pixels)
        axis = max(range(3), key=lambda index: abs(direction[index]))
        low, high = sorted((origin[axis], origin[axis] + direction[axis] * extent))
        for index in range(math.ceil(low / spacing), math.floor(high / spacing) + 1):
            offset = (index * spacing - origin[axis]) / direction[axis]
            if not stroke / 2 < offset < extent - stroke / 2:
                continue
            start = at(offset, 0, 0.02) if vertical else at(0, offset, 0.02)
            end = at(offset, length, 0.02) if vertical else at(length, offset, 0.02)
            mesh.line(start, end, line_stroke, normal, GRID)
    for corner_a, corner_b in (
        ((0, 0), (width, 0)),
        ((width, 0), (width, height)),
        ((width, height), (0, height)),
        ((0, height), (0, 0)),
    ):
        mesh.line(
            at(corner_a[0], corner_a[1], 0.04),
            at(corner_b[0], corner_b[1], 0.04),
            min(0.4, spacing / 25),
            normal,
            WHITE,
        )
    _text(
        mesh,
        at,
        face.upper(),
        width / 2,
        height / 2 - 3.5 * min(0.6, width / (len(face) * 10 + 2), height / 70),
        min(0.6, width / (len(face) * 10 + 2), height / 70),
    )


def _text(
    mesh: GuideMesh,
    at: Callable[[float, float, float], Point],
    text: str,
    center_x: float,
    y: float,
    pixel: float,
) -> None:
    start = center_x - (len(text) * 6 - 1) * pixel / 2
    # A dark label background keeps characters readable across the grid.
    right = center_x + (len(text) * 6 - 1) * pixel / 2
    padding = pixel * 0.3
    mesh.quad(
        (
            at(start - padding, y - padding, 0.05),
            at(right + padding, y - padding, 0.05),
            at(right + padding, y + 7 * pixel + padding, 0.05),
            at(start - padding, y + 7 * pixel + padding, 0.05),
        ),
        (0.0, 0.0, 0.0, 1.0),
    )
    for index, char in enumerate(text):
        for row, bits in enumerate(GLYPHS[char]):
            for col, bit in enumerate(bits):
                if bit == "1":
                    x, bottom = start + (index * 6 + col) * pixel, y + (6 - row) * pixel
                    size = pixel
                    mesh.quad(
                        (
                            at(x, bottom, 0.06),
                            at(x + size, bottom, 0.06),
                            at(x + size, bottom + size, 0.06),
                            at(x, bottom + size, 0.06),
                        ),
                        WHITE,
                    )
