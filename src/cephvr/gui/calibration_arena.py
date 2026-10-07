"""Export a static calibration GLB from the GUI's physical rig geometry."""

from __future__ import annotations

import json
import math
import struct
from collections.abc import Mapping
from pathlib import Path

from cephvr.gui.calibration_guides import add_face_guides
from cephvr.gui.projector_geometry import FACES, RigDimensions, screen_corners

Point = tuple[float, float, float]


def _number(values: Mapping[str, object], key: str, *, positive: bool) -> float:
    value = values.get(key)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"{key} must be a finite number in the saved calibration")
    result = float(value)
    if positive and result <= 0:
        raise ValueError(f"{key} must be positive")
    return result


def geometry_from_calibration(
    payload: Mapping[str, object],
) -> tuple[RigDimensions, dict[str, list[Point]]]:
    """Resolve the same four physical screen planes used by the GUI diagram."""
    if payload.get("format") != "cephvr-rig-calibration" or payload.get("version") != 2:
        raise ValueError("Expected a version 2 CephVR rig calibration JSON")
    values = payload.get("values")
    if not isinstance(values, dict):
        raise ValueError("Calibration values must be an object")
    rig = RigDimensions(
        _number(values, "rig.width", positive=True),
        _number(values, "rig.depth", positive=True),
        _number(values, "rig.height", positive=True),
        (
            _number(values, "rig.subject_x", positive=False),
            _number(values, "rig.subject_y", positive=False),
            _number(values, "rig.subject_z", positive=False),
        ),
    )
    if not all(
        0 < coordinate < extent
        for coordinate, extent in zip(
            rig.subject, (rig.width, rig.depth, rig.height), strict=True
        )
    ):
        raise ValueError("Subject position must be inside the tank")
    front_distance = _number(values, "screens.Front.subject_distance", positive=True)
    left_distance = _number(values, "screens.Left.subject_distance", positive=True)
    right_distance = rig.width + left_distance - 2 * rig.subject[0]
    if right_distance <= 0:
        raise ValueError("Derived Right screen distance must be positive")
    screens: dict[str, list[Point]] = {}
    for face in FACES:
        prefix = f"screens.{face}."
        dimensions = {
            key: str(_number(values, prefix + key, positive=True))
            for key in ("width", "height")
        }
        dimensions["subject_distance"] = str(
            right_distance
            if face == "Right"
            else _number(values, prefix + "subject_distance", positive=True)
        )
        screens[face] = screen_corners(
            rig, face, dimensions, front_distance=str(front_distance)
        )
    return rig, screens


def _add(a: Point, b: Point) -> Point:
    return tuple(a[i] + b[i] for i in range(3))  # type: ignore[return-value]


def _scale(a: Point, factor: float) -> Point:
    return tuple(value * factor for value in a)  # type: ignore[return-value]


def _subtract(a: Point, b: Point) -> Point:
    return tuple(a[i] - b[i] for i in range(3))  # type: ignore[return-value]


class _Mesh:
    def __init__(self) -> None:
        self.positions: list[Point] = []
        self.colors: list[tuple[float, float, float, float]] = []
        self.indices: list[int] = []

    def quad(
        self,
        corners: tuple[Point, Point, Point, Point],
        color: tuple[float, float, float, float],
    ) -> None:
        start = len(self.positions)
        self.positions.extend(corners)
        self.colors.extend((color,) * 4)
        self.indices.extend((start, start + 1, start + 2, start, start + 2, start + 3))

    def line(
        self,
        start: Point,
        end: Point,
        width: float,
        normal: Point,
        color: tuple[float, float, float, float],
    ) -> None:
        direction = _subtract(end, start)
        length = math.sqrt(sum(value * value for value in direction))
        if length == 0:
            return
        side = (
            direction[1] * normal[2] - direction[2] * normal[1],
            direction[2] * normal[0] - direction[0] * normal[2],
            direction[0] * normal[1] - direction[1] * normal[0],
        )
        side_length = math.sqrt(sum(value * value for value in side))
        half = _scale(side, width / (2 * side_length))
        self.quad(
            (
                _subtract(start, half),
                _add(start, half),
                _add(end, half),
                _subtract(end, half),
            ),
            color,
        )


def make_calibration_glb(
    rig: RigDimensions,
    screens: Mapping[str, list[Point]],
    *,
    spacing_mm: float = 10.0,
) -> bytes:
    """Create grid, center cross, face names and a thin tank outline in rig millimetres."""
    if not math.isfinite(spacing_mm) or spacing_mm <= 0:
        raise ValueError("Grid spacing must be finite and positive")
    mesh = _Mesh()
    dark = (0.025, 0.035, 0.055, 1.0)
    outline = (0.4, 0.42, 0.46, 1.0)
    for face in FACES:
        corners = screens[face]
        if len(corners) != 4:
            raise ValueError(f"{face} requires four screen corners")
        origin = corners[0]
        horizontal = _subtract(corners[1], origin)
        vertical = _subtract(corners[3], origin)
        width = math.sqrt(sum(value * value for value in horizontal))
        height = math.sqrt(sum(value * value for value in vertical))
        if not all(math.isfinite(value) and value > 0 for value in (width, height)):
            raise ValueError(f"{face} screen has invalid dimensions")
        u, v = _scale(horizontal, 1 / width), _scale(vertical, 1 / height)
        normal = (
            u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0],
        )

        def at(
            x: float,
            y: float,
            layer: float,
            origin: Point = origin,
            u: Point = u,
            v: Point = v,
            normal: Point = normal,
        ) -> Point:
            return _add(
                _add(_add(origin, _scale(u, x)), _scale(v, y)), _scale(normal, layer)
            )

        mesh.quad(tuple(corners), dark)  # type: ignore[arg-type]
        add_face_guides(mesh, face, at, origin, u, v, normal, width, height, spacing_mm)

    # The tank outline is a spatial reference; screens remain the calibration surfaces.
    for x in (0.0, rig.width):
        for y in (0.0, rig.depth):
            mesh.line((x, y, 0.0), (x, y, rig.height), 0.8, (0.0, 1.0, 0.0), outline)
    for z in (0.0, rig.height):
        for y in (0.0, rig.depth):
            mesh.line((0.0, y, z), (rig.width, y, z), 0.8, (0.0, 0.0, 1.0), outline)
        for x in (0.0, rig.width):
            mesh.line((x, 0.0, z), (x, rig.depth, z), 0.8, (0.0, 0.0, 1.0), outline)
    return _pack_glb(mesh)


def _pack_glb(mesh: _Mesh) -> bytes:
    positions = b"".join(struct.pack("<3f", *point) for point in mesh.positions)
    colors = b"".join(struct.pack("<4f", *color) for color in mesh.colors)
    indices = b"".join(struct.pack("<I", index) for index in mesh.indices)
    binary = positions + colors + indices
    count = len(mesh.positions)
    bounds = {
        "min": [min(point[i] for point in mesh.positions) for i in range(3)],
        "max": [max(point[i] for point in mesh.positions) for i in range(3)],
    }
    document = {
        "asset": {"version": "2.0", "generator": "CephVR calibration arena exporter"},
        "extensionsUsed": ["KHR_materials_unlit"],
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "COLOR_0": 1},
                        "indices": 2,
                        "material": 0,
                    }
                ]
            }
        ],
        "materials": [
            {
                "extensions": {"KHR_materials_unlit": {}},
                "doubleSided": True,
                "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1]},
            }
        ],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(positions)},
            {"buffer": 0, "byteOffset": len(positions), "byteLength": len(colors)},
            {
                "buffer": 0,
                "byteOffset": len(positions) + len(colors),
                "byteLength": len(indices),
            },
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": count,
                "type": "VEC3",
                **bounds,
            },
            {"bufferView": 1, "componentType": 5126, "count": count, "type": "VEC4"},
            {
                "bufferView": 2,
                "componentType": 5125,
                "count": len(mesh.indices),
                "type": "SCALAR",
            },
        ],
    }
    source = json.dumps(document, separators=(",", ":")).encode("utf-8")
    source += b" " * (-len(source) % 4)
    binary += b"\0" * (-len(binary) % 4)
    chunks = struct.pack("<II", len(source), 0x4E4F534A) + source
    chunks += struct.pack("<II", len(binary), 0x004E4942) + binary
    return struct.pack("<4sII", b"glTF", 2, 12 + len(chunks)) + chunks


def export_calibration_arena(
    calibration_path: Path, output_path: Path, *, spacing_mm: float = 10.0
) -> None:
    payload = json.loads(calibration_path.read_text(encoding="utf-8"))
    rig, screens = geometry_from_calibration(payload)
    output_path.write_bytes(make_calibration_glb(rig, screens, spacing_mm=spacing_mm))


def main() -> None:
    """Export a GLB after saving the rig's calibration JSON in Projectors."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Export a CephVR projector calibration arena"
    )
    parser.add_argument(
        "calibration", type=Path, help="Saved Projectors calibration JSON"
    )
    parser.add_argument(
        "output", type=Path, help="GLB path inside the Visual Stimulus asset root"
    )
    parser.add_argument("--spacing-mm", type=float, default=10.0)
    args = parser.parse_args()
    export_calibration_arena(args.calibration, args.output, spacing_mm=args.spacing_mm)
    print(args.output)


if __name__ == "__main__":
    main()
