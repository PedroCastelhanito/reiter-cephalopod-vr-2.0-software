"""Static physical grid/ruler overlays adapted from CephVR1.0 calibration."""

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
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    ".": ("00000", "00000", "00000", "00000", "00000", "00100", "00100"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    " ": ("00000",) * 7,
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
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
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
}


GRID_COLORS: tuple[Color, ...] = (
    (0.9, 0.25, 0.2, 1.0),
    (0.95, 0.65, 0.15, 1.0),
    (0.8, 0.9, 0.15, 1.0),
    (0.2, 0.8, 0.35, 1.0),
    (0.15, 0.75, 0.9, 1.0),
    (0.25, 0.4, 0.95, 1.0),
    (0.65, 0.3, 0.85, 1.0),
    (0.9, 0.3, 0.65, 1.0),
)
WHITE = (1.0, 1.0, 1.0, 1.0)
CENTER = (1.0, 0.86, 0.12, 1.0)


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
) -> None:
    """World-phase grid and face-local center/dimensions/50 mm ruler, built once."""
    if int(width / spacing) + int(height / spacing) > 1000:
        raise ValueError(f"{face} grid exceeds 1000 lines; increase spacing")
    stroke = min(1.0, spacing / 8)
    for vertical, direction, extent, other, length in (
        (True, u, width, v, height),
        (False, v, height, u, width),
    ):
        axis = max(range(3), key=lambda index: abs(direction[index]))
        along = max(range(3), key=lambda index: abs(other[index]))
        low, high = sorted((origin[axis], origin[axis] + direction[axis] * extent))
        for index in range(math.ceil(low / spacing), math.floor(high / spacing) + 1):
            offset = (index * spacing - origin[axis]) / direction[axis]
            if not stroke / 2 < offset < extent - stroke / 2:
                continue
            color = GRID_COLORS[index % len(GRID_COLORS)]
            segments = [(0.0, length)]
            if index % 2:
                other_low, other_high = sorted(
                    (origin[along], origin[along] + other[along] * length)
                )
                segments = []
                for dash in range(
                    math.floor(other_low / 10), math.ceil(other_high / 10) + 1
                ):
                    a = (dash * 10 - origin[along]) / other[along]
                    b = (dash * 10 + 5 - origin[along]) / other[along]
                    lo, hi = sorted((a, b))
                    if max(0, lo) < min(length, hi):
                        segments.append((max(0, lo), min(length, hi)))
            for lo, hi in segments:
                start = at(offset, lo, 0.02) if vertical else at(lo, offset, 0.02)
                end = at(offset, hi, 0.02) if vertical else at(hi, offset, 0.02)
                mesh.line(start, end, stroke, normal, color)
    # The cross marks the full physical face midpoint, independently of grid phase.
    mesh.line(at(0, height / 2, 0.04), at(width, height / 2, 0.04), 1.5, normal, CENTER)
    mesh.line(at(width / 2, 0, 0.04), at(width / 2, height, 0.04), 1.5, normal, CENTER)
    for corner_a, corner_b in (
        ((0, 0), (width, 0)),
        ((width, 0), (width, height)),
        ((width, height), (0, height)),
        ((0, height), (0, 0)),
    ):
        mesh.line(
            at(corner_a[0], corner_a[1], 0.04),
            at(corner_b[0], corner_b[1], 0.04),
            1.0,
            normal,
            WHITE,
        )
    _text(
        mesh,
        at,
        face.upper(),
        width / 2,
        height * 0.78,
        min(width / (len(face) * 6 + 2), height / 42),
    )
    dimensions = f"{width:g} X {height:g} MM".upper()
    _text(
        mesh,
        at,
        dimensions,
        width / 2,
        height * 0.65,
        min(width / (len(dimensions) * 6 + 4), height / 72),
    )
    if width >= 62.5:
        left, right, y = width / 2 - 25, width / 2 + 25, height * 0.25
        mesh.line(at(left, y, 0.04), at(right, y, 0.04), 1.0, normal, WHITE)
        tick = min(3.0, height * 0.1)
        for x in (left, right):
            mesh.line(at(x, y - tick, 0.04), at(x, y + tick, 0.04), 1.0, normal, WHITE)
        _text(
            mesh,
            at,
            "REF 50 MM",
            width / 2,
            height * 0.08,
            min(width / 70, height / 64),
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
    # A dark label background keeps characters readable across the colored grid.
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
                    size = pixel * 0.85
                    mesh.quad(
                        (
                            at(x, bottom, 0.06),
                            at(x + size, bottom, 0.06),
                            at(x + size, bottom + size, 0.06),
                            at(x, bottom + size, 0.06),
                        ),
                        WHITE,
                    )
