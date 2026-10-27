"""Headless arena compilation and transactional, self-contained GLB export."""

import hashlib
import io
import math
import os
import platform
import shutil
import struct
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from cephvr.visual_stimulus.resources.glb import GLBScene, parse_glb

from .bake import TextureCache, bake_surface_texture
from .files import dependency, json_bytes, limits, read_bytes
from .geometry import GeometryCache, Mesh, build_geometry
from .models import ArenaDesign

GENERATOR = "cephvr-arena-v1"


@dataclass
class CompiledArena:
    glb: bytes
    scene: GLBScene
    dependencies: dict[str, str]
    surface_names: list[str]


class Writer:
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self.binary = bytearray()
        self.document: dict[str, Any] = {
            "asset": {"version": "2.0", "generator": GENERATOR},
            "scene": 0,
            "scenes": [{"nodes": []}],
            "nodes": [],
            "meshes": [],
            "bufferViews": [],
            "accessors": [],
            "materials": [],
            "images": [],
            "textures": [],
            "samplers": [],
        }

    def view(self, data: bytes) -> int:
        self.binary.extend(b"\0" * (-len(self.binary) % 4))
        if len(self.binary) + len(data) > self.maximum:
            raise ValueError("Arena exceeds preparation byte budget")
        views = self.document["bufferViews"]
        views.append(
            {"buffer": 0, "byteOffset": len(self.binary), "byteLength": len(data)}
        )
        self.binary.extend(data)
        return len(views) - 1

    def accessor(self, data: np.ndarray, kind: str) -> int:
        arrays = self.document["accessors"]
        data = np.ascontiguousarray(data, dtype="<u4" if kind == "SCALAR" else "<f4")
        item = {
            "bufferView": self.view(data.tobytes()),
            "componentType": 5125 if kind == "SCALAR" else 5126,
            "count": len(data),
            "type": kind,
        }
        if kind == "VEC3":
            item.update(min=data.min(axis=0).tolist(), max=data.max(axis=0).tolist())
        arrays.append(item)
        return len(arrays) - 1

    def texture(self, raw: bytes, *, sampler: dict[str, int] | None = None) -> int:
        doc = self.document
        image = len(doc["images"])
        doc["images"].append(
            {
                "bufferView": self.view(raw),
                "mimeType": "image/png" if raw.startswith(b"\x89PNG") else "image/jpeg",
            }
        )
        doc["samplers"].append(
            sampler
            or {"wrapS": 10497, "wrapT": 10497, "magFilter": 9729, "minFilter": 9729}
        )
        doc["textures"].append({"source": image, "sampler": len(doc["samplers"]) - 1})
        return len(doc["textures"]) - 1

    def mesh(self, mesh: Mesh, material: int, colors: np.ndarray | None = None) -> None:
        attributes = {
            "POSITION": self.accessor(mesh.positions, "VEC3"),
            "TEXCOORD_0": self.accessor(mesh.uv, "VEC2"),
        }
        if colors is not None:
            attributes["COLOR_0"] = self.accessor(
                colors, "VEC4" if colors.shape[1] == 4 else "VEC3"
            )
        doc = self.document
        doc["meshes"].append(
            {
                "primitives": [
                    {
                        "attributes": attributes,
                        "indices": self.accessor(mesh.indices, "SCALAR"),
                        "material": material,
                    }
                ]
            }
        )
        doc["scenes"][0]["nodes"].append(len(doc["nodes"]))
        doc["nodes"].append({"name": mesh.surface, "mesh": len(doc["meshes"]) - 1})

    def finish(self) -> bytes:
        self.binary.extend(b"\0" * (-len(self.binary) % 4))
        self.document["buffers"] = [{"byteLength": len(self.binary)}]
        raw = json_bytes(self.document)
        raw += b" " * (-len(raw) % 4)
        total = 28 + len(raw) + len(self.binary)
        if total > self.maximum:
            raise ValueError("Arena container exceeds preparation byte budget")
        return (
            struct.pack("<4sII", b"glTF", 2, total)
            + struct.pack("<II", len(raw), 0x4E4F534A)
            + raw
            + struct.pack("<II", len(self.binary), 0x004E4942)
            + self.binary
        )


def triangle_sampler(areas: np.ndarray, rng: np.random.Generator) -> Callable[[], int]:
    """Draw area-weighted triangle indices exactly as `rng.choice(n, p=areas/sum)`.

    The cumulative distribution is built once, not per draw (O(log n) each).
    """
    cdf = (areas / areas.sum()).cumsum()
    cdf /= cdf[-1]
    return lambda: int(cdf.searchsorted(rng.random(), side="right"))


def compile_arena(
    design: ArenaDesign,
    root: Path,
    *,
    check: Callable[[], None] = lambda: None,
    geometry_cache: GeometryCache | None = None,
    texture_cache: TextureCache | None = None,
) -> CompiledArena:
    budget = limits().max_asset_cpu_bytes
    maximum = max(1, budget // 256)
    writer = Writer(budget)
    dependencies: dict[str, str] = {}
    snapshots: dict[str, bytes] = {}
    retained_bytes = 0

    def read(name: str) -> bytes:
        nonlocal retained_bytes
        check()
        name = dependency(root, name).relative_to(root.resolve()).as_posix()
        if name in snapshots:
            return snapshots[name]
        bound = budget - retained_bytes
        if name.lower().endswith(".json"):
            bound = min(bound, limits().max_document_bytes)
        data = read_bytes(dependency(root, name), bound)
        retained_bytes += len(data)
        snapshots[name] = data
        dependencies[name] = hashlib.sha256(data).hexdigest()
        return data

    meshes = (
        geometry_cache.build(design, maximum, check)
        if geometry_cache is not None
        else build_geometry(design, max_vertices=maximum, check=check)
    )
    meshes = [replace(mesh) for mesh in meshes]
    if not meshes:
        raise ValueError("At least one arena surface must be visible")
    material_ids = {}
    for name, surface in design.surfaces.items():
        field_texture = False
        material: dict[str, Any] = {
            "pbrMetallicRoughness": {"baseColorFactor": list(surface.color)},
            "doubleSided": False,
            "alphaMode": surface.alpha_mode,
            "alphaCutoff": surface.alpha_cutoff,
        }
        if surface.visible and surface.texture:
            raw, field_texture = bake_surface_texture(
                surface,
                [m for m in meshes if m.surface == name],
                root,
                read,
                check,
                texture_cache,
            )
            with Image.open(io.BytesIO(raw)) as image:
                if image.width * image.height * 16 > budget:
                    raise ValueError("Surface texture exceeds decoded image budget")
            with Image.open(io.BytesIO(raw)) as image:
                image.verify()
            texture = writer.texture(
                raw,
                sampler={
                    "wrapS": 33071,
                    "wrapT": 33071,
                    "magFilter": 9729,
                    "minFilter": 9729,
                }
                if field_texture
                else None,
            )
            material["pbrMetallicRoughness"]["baseColorTexture"] = {"index": texture}
        material_ids[name] = len(writer.document["materials"])
        writer.document["materials"].append(material)
    names = []
    for mesh in meshes:
        check()
        writer.mesh(mesh, material_ids[mesh.surface])
        names.append(mesh.surface)
    used = sum(len(m.positions) for m in meshes)
    for name, surface in design.surfaces.items():
        source_meshes = [m for m in meshes if m.surface == name]
        if not source_meshes:
            continue
        triangles = np.concatenate(
            [m.positions[m.indices.reshape(-1, 3)] for m in source_meshes]
        )
        areas = (
            np.linalg.norm(
                np.cross(
                    triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
                ),
                axis=1,
            )
            / 2
        )
        for layer in surface.scatters:
            check()
            count = math.floor(float(areas.sum()) / 100 * layer.density_per_cm2 + 0.5)
            if count == 0:
                continue
            if count > maximum:
                raise ValueError("Scatter count exceeds preparation budget")
            path = dependency(root, layer.model)

            def resolve(uri: str, path: Path = path) -> bytes:
                return read(
                    (path.parent / uri).resolve().relative_to(root.resolve()).as_posix()
                )

            scene = parse_glb(
                read(layer.model),
                max_bytes=budget,
                max_elements=maximum,
                resolve=resolve,
            )
            vertices = sum(
                len(p.positions) for node in scene.nodes for p in node.primitives
            )
            used += count * vertices
            if used > maximum:
                raise ValueError("Scattered geometry exceeds preparation budget")
            material_offset = len(writer.document["materials"])
            texture_offset = len(writer.document["textures"])
            for tex in scene.textures:
                writer.texture(
                    tex.image,
                    sampler={
                        "wrapS": tex.wrap_s,
                        "wrapT": tex.wrap_t,
                        "minFilter": tex.min_filter,
                        "magFilter": tex.mag_filter,
                    },
                )
            for mat in scene.materials:
                pbr: dict[str, Any] = {"baseColorFactor": list(mat.base_color_factor)}
                if mat.texture_index is not None:
                    pbr["baseColorTexture"] = {
                        "index": texture_offset + mat.texture_index
                    }
                writer.document["materials"].append(
                    {
                        "pbrMetallicRoughness": pbr,
                        "doubleSided": mat.double_sided,
                        "alphaMode": mat.alpha_mode,
                        "alphaCutoff": mat.alpha_cutoff,
                    }
                )
            default = len(writer.document["materials"])
            writer.document["materials"].append({})
            rng = np.random.default_rng(layer.seed)
            pick = triangle_sampler(areas, rng)
            anchor = pick()
            for _ in range(count):
                check()
                selected = anchor if rng.random() < layer.clustering else pick()
                tri = triangles[selected]
                a, b = rng.random(2)
                if a + b > 1:
                    a, b = 1 - a, 1 - b
                position = tri[0] + a * (tri[1] - tri[0]) + b * (tri[2] - tri[0])
                normal = np.cross(tri[1] - tri[0], tri[2] - tri[0])
                normal /= np.linalg.norm(normal)
                tangent = tri[1] - tri[0]
                tangent /= np.linalg.norm(tangent)
                angle = rng.uniform(0, math.tau)
                side = np.cross(normal, tangent)
                rotation = np.stack(
                    [
                        tangent * math.cos(angle) + side * math.sin(angle),
                        side * math.cos(angle) - tangent * math.sin(angle),
                        normal,
                    ],
                    axis=1,
                ) * rng.uniform(layer.min_scale, layer.max_scale)
                for node in scene.nodes:
                    transform = np.asarray(node.matrix).reshape(4, 4).T
                    for primitive in node.primitives:
                        points = np.asarray(primitive.positions)
                        points = points @ transform[:3, :3].T + transform[:3, 3]
                        points = points @ rotation.T + position
                        indices = np.asarray(primitive.indices, dtype="u4")
                        if np.linalg.det(transform[:3, :3]) < 0:
                            indices = indices.reshape(-1, 3)[:, [0, 2, 1]].reshape(-1)
                        uv = (
                            np.zeros((len(points), 2))
                            if primitive.texcoords is None
                            else np.asarray(primitive.texcoords)
                        )
                        mesh = Mesh(name, points, uv, indices)
                        writer.mesh(
                            mesh,
                            default
                            if primitive.material_index is None
                            else material_offset + primitive.material_index,
                            None
                            if primitive.colors is None
                            else np.asarray(primitive.colors),
                        )
                        names.append(name)
    check()
    data = writer.finish()
    scene = parse_glb(data, max_bytes=budget, max_elements=maximum)
    decoded_bytes = 0
    for source_texture in scene.textures:
        check()
        with Image.open(io.BytesIO(source_texture.image)) as image:
            decoded_bytes += image.width * image.height * 16
            if decoded_bytes > budget:
                raise ValueError("Arena textures exceed decoded image budget")
            image.verify()
    return CompiledArena(data, scene, dependencies, names)


def arena_job(
    document: dict[str, Any],
    root: Path,
    geometry_cache: GeometryCache,
    texture_cache: TextureCache,
) -> Callable[[Callable[[], None]], CompiledArena]:
    """Worker operation validating and compiling a snapshot of the arena document."""

    def run(check: Callable[[], None]) -> CompiledArena:
        return compile_arena(
            ArenaDesign.model_validate(document),
            root,
            check=check,
            geometry_cache=geometry_cache,
            texture_cache=texture_cache,
        )

    return run


def export_arena(
    design: ArenaDesign,
    root: Path,
    destination: Path,
    *,
    check: Callable[[], None] = lambda: None,
) -> Path:
    """Publish a new complete bundle with one rename; never replace an existing bundle."""
    result = compile_arena(design, root, check=check)
    if destination.exists():
        raise FileExistsError(
            "Choose a new bundle directory; existing exports are preserved"
        )
    temporary = Path(tempfile.mkdtemp(prefix=".cephvr-arena-", dir=destination.parent))
    try:
        (temporary / "arena.glb").write_bytes(result.glb)
        (temporary / "design.arena.json").write_bytes(
            json_bytes(design.model_dump(mode="json"))
        )
        (temporary / "provenance.json").write_bytes(
            json_bytes(
                {
                    "generator": GENERATOR,
                    "python": platform.python_version(),
                    "numpy": np.__version__,
                    "units": "mm",
                    "dependencies": result.dependencies,
                    "glb_sha256": hashlib.sha256(result.glb).hexdigest(),
                }
            )
        )
        check()
        os.rename(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination / "arena.glb"
