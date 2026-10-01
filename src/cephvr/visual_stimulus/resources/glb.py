"""Bounded GLB 2 static geometry reader for the accepted unlit arena profile."""

from __future__ import annotations

import json
import math
import struct
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .glb_materials import GLBMaterial, GLBTexture, prepare_materials


class GLBError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GLBPrimitive:
    positions: tuple[tuple[float, float, float], ...]
    texcoords: tuple[tuple[float, float], ...] | None
    colors: tuple[tuple[float, ...], ...] | None
    indices: tuple[int, ...]
    material_index: int | None


@dataclass(frozen=True, slots=True)
class GLBNode:
    matrix: tuple[float, ...]
    primitives: tuple[GLBPrimitive, ...]


@dataclass(frozen=True, slots=True)
class GLBScene:
    nodes: tuple[GLBNode, ...]
    materials: tuple[GLBMaterial, ...]
    textures: tuple[GLBTexture, ...] = ()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GLBError(f"duplicate GLB JSON key {key!r}")
        result[key] = value
    return result


def _matrix(node: dict[str, Any]) -> tuple[float, ...]:
    if "matrix" in node:
        if any(key in node for key in ("translation", "rotation", "scale")):
            raise GLBError("node cannot combine matrix and TRS")
        values = tuple(float(v) for v in node["matrix"])
        if len(values) != 16:
            raise GLBError("node matrix must have 16 values")
    else:
        translation = tuple(float(v) for v in node.get("translation", (0, 0, 0)))
        scale = tuple(float(v) for v in node.get("scale", (1, 1, 1)))
        rotation = tuple(float(v) for v in node.get("rotation", (0, 0, 0, 1)))
        if len(translation) != 3 or len(scale) != 3 or len(rotation) != 4:
            raise GLBError("invalid node TRS")
        qx, qy, qz, qw = rotation
        if not math.isclose(sum(v * v for v in rotation), 1.0, rel_tol=0, abs_tol=1e-5):
            raise GLBError("node quaternion must have unit length")
        xx, yy, zz = qx * qx, qy * qy, qz * qz
        xy, xz, yz = qx * qy, qx * qz, qy * qz
        wx, wy, wz = qw * qx, qw * qy, qw * qz
        # Column-major affine matrix.
        values = (
            (1 - 2 * (yy + zz)) * scale[0],
            (2 * (xy + wz)) * scale[0],
            (2 * (xz - wy)) * scale[0],
            0,
            (2 * (xy - wz)) * scale[1],
            (1 - 2 * (xx + zz)) * scale[1],
            (2 * (yz + wx)) * scale[1],
            0,
            (2 * (xz + wy)) * scale[2],
            (2 * (yz - wx)) * scale[2],
            (1 - 2 * (xx + yy)) * scale[2],
            0,
            *translation,
            1,
        )
    if any(not math.isfinite(v) for v in values):
        raise GLBError("node transform must be finite")
    return values


def parse_glb(
    data: bytes,
    *,
    max_bytes: int,
    max_elements: int,
    resolve: Callable[[str], bytes] | None = None,
    reserve_workspace: Callable[[int], None] | None = None,
) -> GLBScene:
    if not data or len(data) > max_bytes or max_elements <= 0:
        raise GLBError("GLB exceeds configured preparation bounds")
    if len(data) < 20:
        raise GLBError("truncated GLB header")
    magic, version, total = struct.unpack_from("<4sII", data)
    if magic != b"glTF" or version != 2 or total != len(data):
        raise GLBError("invalid GLB 2 header or declared length")
    offset = 12
    document: dict[str, Any] | None = None
    binary: memoryview | None = None
    document_bytes = 0
    while offset < total:
        if offset + 8 > total:
            raise GLBError("truncated GLB chunk header")
        length, kind = struct.unpack_from("<II", data, offset)
        offset += 8
        if length % 4 or length > total - offset:
            raise GLBError("GLB chunk exceeds container")
        chunk = memoryview(data)[offset : offset + length]
        if kind == 0x4E4F534A and document is None:
            document_bytes = length * 64
            if reserve_workspace is not None:
                reserve_workspace(document_bytes)
            try:
                document = json.loads(
                    chunk.tobytes().decode("utf-8"), object_pairs_hook=_unique_object
                )
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise GLBError("invalid GLB JSON chunk") from exc
        elif kind == 0x004E4942 and binary is None:
            binary = chunk
        else:
            raise GLBError("duplicate or unsupported GLB chunk")
        offset += length
    if document is None or binary is None:
        raise GLBError("GLB requires JSON and BIN chunks")
    if not isinstance(document, dict):
        raise GLBError("GLB JSON root must be an object")
    asset = document.get("asset", {})
    if asset.get("version") != "2.0":
        raise GLBError("GLB asset version must be 2.0")
    if set(document.get("extensionsRequired", [])) - {"KHR_materials_unlit"}:
        raise GLBError(
            "required GLB extensions are unsupported by static unlit profile"
        )
    if document.get("skins") or document.get("animations"):
        raise GLBError(
            "skins and imported animation are outside the static arena profile"
        )
    if (
        len(document.get("nodes", [])) > max_elements
        or len(document.get("meshes", [])) > max_elements
    ):
        raise GLBError("GLB node/mesh count exceeds configured bound")
    buffers = document.get("buffers", [])
    buffer_data: list[memoryview] = []
    for index, buffer in enumerate(buffers):
        if "uri" in buffer:
            if resolve is None:
                raise GLBError("external buffer requires protected resolver")
            content = memoryview(resolve(buffer["uri"]))
        elif index == 0:
            content = binary
        else:
            raise GLBError("only the first buffer can use the GLB BIN chunk")
        length = buffer.get("byteLength")
        if (
            type(length) is not int
            or not 0 < length <= len(content)
            or len(content) > max_bytes
        ):
            raise GLBError("invalid declared buffer length")
        buffer_data.append(content[:length])
    views = document.get("bufferViews", [])
    accessors = document.get("accessors", [])

    def view_data(index: int) -> memoryview:
        if type(index) is not int or not 0 <= index < len(views):
            raise GLBError("buffer view reference is invalid")
        view = views[index]
        buffer_index = view.get("buffer")
        if type(buffer_index) is not int or not 0 <= buffer_index < len(buffer_data):
            raise GLBError("buffer view references invalid buffer")
        content = buffer_data[buffer_index]
        start, length = view.get("byteOffset", 0), view.get("byteLength")
        if (
            type(start) is not int
            or type(length) is not int
            or start < 0
            or length < 0
            or start + length > len(content)
        ):
            raise GLBError("buffer view exceeds its buffer")
        return content[start : start + length]

    decoded_elements = 0

    def read_accessor(
        index: int,
        expected_type: str,
        allow_normalized: bool = False,
        *,
        indices: bool = False,
    ) -> tuple[tuple[float, ...], ...]:
        nonlocal decoded_elements
        if type(index) is not int or not 0 <= index < len(accessors):
            raise GLBError("accessor reference is out of range")
        accessor = accessors[index]
        if "sparse" in accessor:
            raise GLBError(
                "sparse accessor materialization is not enabled in this provider"
            )
        if accessor.get("type") != expected_type or "bufferView" not in accessor:
            raise GLBError("accessor type/layout is unsupported")
        count = accessor.get("count")
        if type(count) is not int or count <= 0 or count > max_elements:
            raise GLBError("accessor count exceeds configured bound")
        decoded_elements += count
        if decoded_elements > max_elements:
            raise GLBError("aggregate accessor elements exceed configured bound")
        if reserve_workspace is not None:
            reserve_workspace(document_bytes + decoded_elements * 256)
        component_type = accessor.get("componentType")
        layouts = {
            5126: ("f", 4, False),
            5121: ("B", 1, True),
            5123: ("H", 2, True),
            5125: ("I", 4, True),
        }
        if component_type not in layouts:
            raise GLBError("accessor component type is unsupported")
        fmt, component_size, integer = layouts[component_type]
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}.get(expected_type)
        if (
            width is None
            or (integer and not (allow_normalized or indices))
            or (indices and (not integer or accessor.get("normalized", False)))
            or (
                integer
                and not indices
                and (component_type == 5125 or not accessor.get("normalized", False))
            )
        ):
            raise GLBError("accessor interpretation is unsupported")
        view_index = accessor["bufferView"]
        if not 0 <= view_index < len(views):
            raise GLBError("buffer view reference is out of range")
        view = views[view_index]
        content = view_data(view_index)
        accessor_start = accessor.get("byteOffset", 0)
        stride = view.get("byteStride", component_size * width)
        if any(type(v) is not int or v < 0 for v in (accessor_start, stride)):
            raise GLBError("negative or invalid accessor offset/stride")
        span = (count - 1) * stride + component_size * width
        if (
            stride < component_size * width
            or stride % component_size
            or accessor_start % component_size
            or accessor_start + span > len(content)
        ):
            raise GLBError("accessor exceeds its declared buffer view")
        result = []
        for row in range(count):
            start = accessor_start + row * stride
            values = struct.unpack_from("<" + fmt * width, content, start)
            if integer and accessor.get("normalized"):
                maximum = (1 << (component_size * 8)) - 1
                values = tuple(v / maximum for v in values)
            if any(not math.isfinite(float(v)) for v in values):
                raise GLBError("accessor contains nonfinite values")
            result.append(tuple(float(v) for v in values))
        return tuple(result)

    try:
        materials, textures = prepare_materials(
            document,
            lambda index: view_data(index).tobytes(),
            resolve,
            max_bytes=max_bytes,
        )
    except ValueError as exc:
        raise GLBError(str(exc)) from exc
    mesh_primitives: list[tuple[GLBPrimitive, ...]] = []
    for mesh in document.get("meshes", []):
        entries = []
        for primitive in mesh.get("primitives", []):
            if (
                primitive.get("targets")
                or primitive.get("extensions")
                or mesh.get("weights")
            ):
                raise GLBError("compressed or morphed mesh is unsupported")
            if primitive.get("mode", 4) != 4:
                raise GLBError("only triangle primitives are supported")
            attrs = primitive.get("attributes", {})
            if (
                set(attrs) - {"POSITION", "TEXCOORD_0", "COLOR_0", "NORMAL", "TANGENT"}
                or "POSITION" not in attrs
            ):
                raise GLBError("primitive has unsupported required vertex attributes")
            positions = read_accessor(attrs["POSITION"], "VEC3")
            texcoords = (
                read_accessor(attrs["TEXCOORD_0"], "VEC2", True)
                if "TEXCOORD_0" in attrs
                else None
            )
            colors = (
                read_accessor(
                    attrs["COLOR_0"],
                    "VEC4"
                    if document["accessors"][attrs["COLOR_0"]]["type"] == "VEC4"
                    else "VEC3",
                    True,
                )
                if "COLOR_0" in attrs
                else None
            )
            if (
                texcoords is not None
                and len(texcoords) != len(positions)
                or colors is not None
                and len(colors) != len(positions)
            ):
                raise GLBError("vertex attribute counts differ")
            if "indices" in primitive:
                raw = read_accessor(primitive["indices"], "SCALAR", indices=True)
                indices = tuple(int(v[0]) for v in raw)
            else:
                indices = tuple(range(len(positions)))
            if len(indices) % 3 or any(i < 0 or i >= len(positions) for i in indices):
                raise GLBError("triangle index list is invalid")
            material_index = primitive.get("material")
            if material_index is not None and not 0 <= material_index < len(materials):
                raise GLBError("primitive material reference is invalid")
            if (
                material_index is not None
                and materials[material_index].texture_index is not None
                and texcoords is None
            ):
                raise GLBError("textured material requires TEXCOORD_0")
            if colors is not None and any(
                not 0 <= value <= 1 for color in colors for value in color
            ):
                raise GLBError("vertex color must be within [0,1]")
            entries.append(
                GLBPrimitive(
                    tuple((v[0], v[1], v[2]) for v in positions),
                    tuple((v[0], v[1]) for v in texcoords)
                    if texcoords is not None
                    else None,
                    colors,
                    indices,
                    material_index,
                )
            )
        mesh_primitives.append(tuple(entries))
    nodes = document.get("nodes", [])
    roots = (
        document.get("scenes", [{}])[document.get("scene", 0)].get("nodes", [])
        if document.get("scenes")
        else list(range(len(nodes)))
    )
    resolved: list[GLBNode] = []
    visited: set[int] = set()

    def visit(node_index: int, parent: tuple[float, ...], ancestors: set[int]) -> None:
        if (
            type(node_index) is not int
            or not 0 <= node_index < len(nodes)
            or node_index in visited
        ):
            raise GLBError("node graph reference is invalid or cyclic")
        visited.add(node_index)
        local = _matrix(nodes[node_index])
        combined = tuple(
            sum(parent[k * 4 + r] * local[c * 4 + k] for k in range(4))
            for c in range(4)
            for r in range(4)
        )
        node = nodes[node_index]
        if "mesh" in node:
            mesh_index = node["mesh"]
            if not 0 <= mesh_index < len(mesh_primitives):
                raise GLBError("node mesh reference is invalid")
            resolved.append(GLBNode(combined, mesh_primitives[mesh_index]))
        for child in node.get("children", []):
            visit(child, combined, ancestors | {node_index})

    identity = (
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )
    for root in roots:
        visit(root, identity, set())
    if not resolved:
        raise GLBError("selected GLB scene contains no triangle mesh")
    return GLBScene(tuple(resolved), materials, textures)
