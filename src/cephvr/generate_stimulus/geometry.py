"""Pure, bounded mesh construction for the five static arena templates (millimetres)."""

import hashlib
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from .models import ArenaDesign, Relief, Surface


@dataclass
class Mesh:
    surface: str
    positions: np.ndarray
    uv: np.ndarray
    indices: np.ndarray


class GeometryCache:
    """Retain only the latest mesh of each surface, keyed by geometry inputs."""

    def __init__(self) -> None:
        self.entries: dict[str, tuple[str, list[Mesh]]] = {}

    def build(
        self, design: ArenaDesign, maximum: int, check: Callable[[], None]
    ) -> list[Mesh]:
        meshes = []
        used = 0
        for name, surface in design.surfaces.items():
            check()
            isolated = design.model_copy(deep=True)
            for key, value in isolated.surfaces.items():
                value.visible = key == name and surface.visible
                value.color = (1, 1, 1, 1)
                value.alpha_mode = "OPAQUE"
                value.alpha_cutoff = 0.5
                value.texture = ""
                value.scatters = []
                if key != name:
                    value.relief = Relief()
                    value.texture_scale_mm = 100
            key = isolated.model_dump_json()
            previous = self.entries.get(name)
            if previous is None or previous[0] != key:
                result = build_geometry(
                    isolated, max_vertices=maximum - used, check=check
                )
                self.entries[name] = key, result
            else:
                result = previous[1]
            used += sum(len(m.positions) for m in result)
            if used > maximum:
                raise ValueError("Arena geometry exceeds preparation budget")
            meshes.extend(result)
        return meshes


def outline(design: ArenaDesign) -> list[tuple[float, float]]:
    x, y, c = design.width_mm / 2, design.depth_mm / 2, design.corridor_mm / 2
    if design.shape == "cross":
        return [
            (-c, -y),
            (c, -y),
            (c, -c),
            (x, -c),
            (x, c),
            (c, c),
            (c, y),
            (-c, y),
            (-c, c),
            (-x, c),
            (-x, -c),
            (-c, -c),
        ]
    if design.shape == "two_choice":
        return [
            (-c, -y),
            (c, -y),
            (c, y - 2 * c),
            (x, y - 2 * c),
            (x, y),
            (-x, y),
            (-x, y - 2 * c),
            (-c, y - 2 * c),
        ]
    return [(-x, -y), (x, -y), (x, y), (-x, y)]


def _inside(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
    inside = False
    for (ax, ay), (bx, by) in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


def relief_values(u: np.ndarray, v: np.ndarray, surface: Surface) -> np.ndarray:
    relief = surface.relief
    if relief.pattern == "none" or relief.height_mm == 0:
        return np.zeros_like(u)
    phase = (
        int.from_bytes(hashlib.sha256(str(relief.seed).encode()).digest()[:4], "big")
        / 2**32
        * math.tau
    )
    a, b = u * math.tau / relief.scale_mm, v * math.tau / relief.scale_mm
    if relief.pattern == "ridges":
        value = 1 - np.abs(np.sin(a + phase))
    elif relief.pattern == "waves":
        value = (1 + np.sin(a + phase)) / 2
    else:
        value = (
            np.sin(a + phase) * np.cos(b - phase)
            + 0.5 * np.sin(2.3 * a + b + phase)
            + 1.5
        ) / 3
    return value * relief.height_mm


def build_geometry(
    design: ArenaDesign, *, max_vertices: int, check: Callable[[], None] = lambda: None
) -> list[Mesh]:
    """Create inward-facing surface meshes; never derive movement regions."""
    meshes: list[Mesh] = []
    count = 0

    def patch(
        name: str,
        evaluate: Callable[..., Any],
        normal: Callable[..., Any],
        n: int,
        m: int,
    ) -> None:
        nonlocal count
        check()
        surface = design.surfaces[name]
        if not surface.visible:
            return
        count += (n + 1) * (m + 1)
        if count > max_vertices:
            raise ValueError("Arena geometry exceeds preparation budget")
        u, v = np.meshgrid(np.linspace(0, 1, n + 1), np.linspace(0, 1, m + 1))
        positions, coordinates = evaluate(u, v)
        positions = (
            positions
            + normal(u, v)
            * relief_values(coordinates[..., 0], coordinates[..., 1], surface)[
                ..., None
            ]
        )
        base = np.arange(m)[:, None] * (n + 1) + np.arange(n)[None, :]
        indices = np.stack(
            [base, base + 1, base + n + 2, base, base + n + 2, base + n + 1], axis=-1
        ).reshape(-1)
        meshes.append(
            Mesh(
                name,
                positions.reshape(-1, 3).astype("f4"),
                (coordinates / surface.texture_scale_mm).reshape(-1, 2).astype("f4"),
                indices.astype("u4"),
            )
        )

    n = design.subdivisions
    curved = design.shape in {"circular", "torus"}
    if curved:
        rx, ry = design.width_mm / 2, design.depth_mm / 2
        inner = (
            0 if design.shape == "circular" else 1 - design.corridor_mm / min(rx, ry)
        )
        if inner < 0:
            raise ValueError("Torus corridor must be smaller than its outer radius")
        # A tiny center ring is avoided: disk sectors use explicit triangle fans below.
        for name, z, direction in (("floor", 0, 1), ("roof", design.height_mm, -1)):

            def disk(
                u: np.ndarray, v: np.ndarray, z: float = z, direction: int = direction
            ) -> tuple[np.ndarray, np.ndarray]:
                angle = direction * u * math.tau
                r = inner + (1 - inner) * v
                xx, yy = rx * r * np.cos(angle), ry * r * np.sin(angle)
                return np.stack([xx, yy, np.full_like(xx, z)], -1), np.stack(
                    [xx, yy], -1
                )

            # Radial-first orientation makes the floor face upward.
            patch(
                name,
                lambda u, v: disk(v, u),
                lambda u, v, d=direction: np.array([0, 0, d]),
                n,
                design.segments,
            )
        loops = [(rx, ry, False)]
        if inner > 0:
            loops.append((rx * inner, ry * inner, True))
        for ax, ay, reverse in loops:
            polygon = [
                (
                    ax * math.cos(t * math.tau / design.segments),
                    ay * math.sin(t * math.tau / design.segments),
                )
                for t in range(design.segments)
            ]
            if reverse:
                polygon.reverse()
            _walls(polygon, design, patch, n)
    else:
        polygon = outline(design)
        xs, ys = sorted({p[0] for p in polygon}), sorted({p[1] for p in polygon})
        for x0, x1 in zip(xs, xs[1:], strict=False):
            for y0, y1 in zip(ys, ys[1:], strict=False):
                if not _inside((x0 + x1) / 2, (y0 + y1) / 2, polygon):
                    continue
                for name, z, direction in (
                    ("floor", 0, 1),
                    ("roof", design.height_mm, -1),
                ):

                    def plane(
                        u: np.ndarray,
                        v: np.ndarray,
                        z: float = z,
                        direction: int = direction,
                        x0: float = x0,
                        x1: float = x1,
                        y0: float = y0,
                        y1: float = y1,
                    ) -> tuple[np.ndarray, np.ndarray]:
                        xx = x0 + (x1 - x0) * (u if direction == 1 else 1 - u)
                        yy = y0 + (y1 - y0) * v
                        return np.stack([xx, yy, np.full_like(xx, z)], -1), np.stack(
                            [xx, yy], -1
                        )

                    patch(
                        name, plane, lambda u, v, d=direction: np.array([0, 0, d]), n, n
                    )
        _walls(polygon, design, patch, n)
    # Remove zero-area center triangles from circular disks.
    for mesh in meshes:
        tri = mesh.indices.reshape(-1, 3)
        points = mesh.positions[tri]
        valid = (
            np.linalg.norm(
                np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0]),
                axis=1,
            )
            > 1e-8
        )
        mesh.indices = tri[valid].reshape(-1)
    return meshes


def _walls(
    polygon: list[tuple[float, float]],
    design: ArenaDesign,
    patch: Callable[..., Any],
    n: int,
) -> None:
    for a, b in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        length = math.dist(a, b)
        inward = np.array([-(b[1] - a[1]) / length, (b[0] - a[0]) / length, 0])

        def wall(
            u: np.ndarray,
            v: np.ndarray,
            a: tuple[float, float] = a,
            b: tuple[float, float] = b,
            length: float = length,
        ) -> tuple[np.ndarray, np.ndarray]:
            # Reverse horizontal winding to face the arena interior.
            xx = b[0] + (a[0] - b[0]) * u
            yy = b[1] + (a[1] - b[1]) * u
            zz = design.height_mm * v
            return np.stack([xx, yy, zz], -1), np.stack([u * length, zz], -1)

        dx, dy = b[0] - a[0], b[1] - a[1]
        name = (
            ("wall_s" if dx > 0 else "wall_n")
            if abs(dx) >= abs(dy)
            else ("wall_e" if dy > 0 else "wall_w")
        )
        patch(name, wall, lambda u, v, inward=inward: inward, n, n)
