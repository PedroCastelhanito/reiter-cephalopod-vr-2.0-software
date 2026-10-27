"""Bake one arena surface's texture into image bytes for the finite GLB consumer."""

import hashlib
import io
import json
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PIL import Image

from cephvr.visual_stimulus.resources.texture_recipe import (
    generate_texture_recipe,
    parse_texture_recipe,
)

from .files import dependency
from .geometry import Mesh
from .models import Surface
from .textures import display_pixels, texture_pixels


class TextureCache:
    """Bounded LRU of baked field PNGs so unrelated edits skip regeneration."""

    def __init__(self, size: int = 12) -> None:
        self.size = size
        self.entries: OrderedDict[bytes, bytes] = OrderedDict()

    def get(self, key: bytes) -> bytes | None:
        png = self.entries.get(key)
        if png is not None:
            self.entries.move_to_end(key)
        return png

    def put(self, key: bytes, png: bytes) -> None:
        self.entries[key] = png
        self.entries.move_to_end(key)
        while len(self.entries) > self.size:
            self.entries.popitem(last=False)


def _png(pixels: np.ndarray) -> bytes:
    # Legacy recipes are linear RGB8; glTF texture samples are sRGB.
    stream = io.BytesIO()
    Image.fromarray(display_pixels(pixels)).save(stream, format="PNG")
    return stream.getvalue()


def bake_surface_texture(
    surface: Surface,
    meshes: list[Mesh],
    root: Path,
    read: Callable[[str], bytes],
    check: Callable[[], None],
    cache: TextureCache | None = None,
) -> tuple[bytes, bool]:
    """Return image bytes for a surface and whether a baked field remapped its UVs.

    `meshes` are this surface's patches; a texture field is sampled once over their
    physical extent and the UVs are rewritten to cover that single window.
    """
    raw = read(surface.texture)
    if not surface.texture.lower().endswith(".json"):
        return raw, False
    document = json.loads(raw)
    if document.get("kind") == "sparse_noise" or (
        document.get("pattern") == "polar_grating"
        and document.get("cephvr_asset_type") != "texture_field"
        and not document.get("params", {}).get("tile_local", False)
    ):
        raise ValueError(
            "Arena surfaces require static tile recipes, not screen-dependent patterns"
        )
    image_path = document.get("params", {}).get("texture_path")
    if image_path:
        parent = dependency(root, surface.texture).parent
        read((parent / str(image_path)).relative_to(root.resolve()).as_posix())
    if document.get("cephvr_asset_type") != "texture_field":
        pixels = texture_pixels(
            document,
            root,
            check=check,
            recipe_directory=dependency(root, surface.texture).parent,
            read_image=lambda path: read(
                path.resolve().relative_to(root.resolve()).as_posix()
            ),
            authored=False,
        )
        return _png(pixels), False
    coordinates = np.concatenate([m.uv for m in meshes]) * surface.texture_scale_mm
    low, high = coordinates.min(axis=0), coordinates.max(axis=0)
    extent = high - low
    scale = 1024 / max(extent)
    nx, ny = max(1, round(extent[0] * scale)), max(1, round(extent[1] * scale))
    offset = (low + high) / 2
    # Pixels depend only on the recipe bytes and this sampling window.
    key = hashlib.sha256(
        raw + extent.tobytes() + offset.tobytes() + repr((nx, ny)).encode()
    ).digest()
    png = None if cache is None else cache.get(key)
    if png is None:
        png = _png(
            generate_texture_recipe(
                parse_texture_recipe(raw),
                extent_mm=tuple(extent),
                sample_size=(nx, ny),
                offset_mm=tuple(offset),
                check=check,
            )
        )
        if cache is not None:
            cache.put(key, png)
    # Bake this finite GLB consumer, without repeating or resizing the field.
    for mesh in meshes:
        mesh.uv = ((mesh.uv * surface.texture_scale_mm - low) / extent).astype("f4")
        mesh.uv[:, 1] = 1 - mesh.uv[:, 1]
    return png, True
