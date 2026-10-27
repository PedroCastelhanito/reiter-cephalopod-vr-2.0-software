"""Physical tile/screen sampling for the editor; pixel generation stays backend-owned."""

import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from cephvr.visual_stimulus.config.models.display_profile import Geometry

from .textures import authored_recipe, texture_pixels


def preview_texture(
    document: dict[str, Any],
    root: Path,
    geometry: Geometry | None,
    *,
    face: str,
    index: int,
    screen: bool,
    directory: Path,
    check: Callable[[], None],
) -> tuple[np.ndarray, str]:
    document = authored_recipe(document)
    sparse = document.get("kind") == "sparse_noise"
    if screen:
        if geometry is None:
            raise ValueError("Load calibration for a physical screen preview")
        surface = next(s for s in geometry.surfaces if s.surface_id == face)
        width = math.dist(surface.bottom_left_mm, surface.bottom_right_mm)
        height = math.dist(surface.bottom_left_mm, surface.top_left_mm)
    else:
        width = float(document.get("params", {}).get("tile_width_mm", 100))
        height = float(document.get("params", {}).get("tile_height_mm", width))
    if not math.isfinite(width + height) or min(width, height) <= 0:
        raise ValueError("Preview extent must be finite and positive")
    scale = min(1920 / width, 1080 / height)
    nx, ny = max(1, round(scale * width)), max(1, round(scale * height))
    field = document.get("cephvr_asset_type") == "texture_field"
    if not sparse and not field:
        document["params"]["texture_resolution"] = max(nx, ny)
    pixels = texture_pixels(
        document,
        root,
        geometry if screen else None,
        face=face if screen else "front",
        index=index,
        check=check,
        recipe_directory=directory,
        authored=False,
        extent_mm=(width, height),
        sample_size=(nx, ny),
    )
    x = (np.arange(nx) + 0.5) * width / nx - width / 2
    y = (np.arange(ny) + 0.5) * height / ny - height / 2
    if field:
        result = pixels
    elif sparse:
        cell = document["square_size_mm"]
        columns, rows = pixels.shape[1], pixels.shape[0]
        u = np.floor((x + columns * cell / 2) / cell).astype(int)
        v = np.floor((y + rows * cell / 2) / cell).astype(int)
        result = pixels[
            np.clip(v, 0, rows - 1)[:, None], np.clip(u, 0, columns - 1)[None, :]
        ].copy()
        valid = ((v >= 0) & (v < rows))[:, None] & ((u >= 0) & (u < columns))[None, :]
        result[~valid] = round(document["background_linear"] * 255)
    else:
        params = document["params"]
        tw = float(params.get("tile_width_mm", 100))
        th = float(params.get("tile_height_mm", tw))
        u = np.floor(np.mod(x / tw + 0.5, 1) * pixels.shape[1]).astype(int)
        v = np.floor(np.mod(y / th + 0.5, 1) * pixels.shape[0]).astype(int)
        result = pixels[v[:, None], u[None, :]]
    check()
    title = f"{face.capitalize()} screen" if screen else "Appearance sample"
    if sparse and not screen:
        title = "Appearance sample (Protocol resolves screen patterns)"
    suffix = f" · Pattern {index}" if sparse else ""
    return (
        np.asarray(result),
        f"{title}: {width:g} × {height:g} mm{suffix}. Display sRGB preview; optical accuracy requires rig verification.",
    )
