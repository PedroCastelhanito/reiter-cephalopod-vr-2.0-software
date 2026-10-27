"""Texture authoring delegates pixels and random streams to their existing owners."""

import copy
import io
import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from cephvr.visual_stimulus.config.models.display_profile import Geometry
from cephvr.visual_stimulus.config.models.sparse_noise import (
    SparseNoiseRecipe,
    parse_sparse_noise_appearance,
)
from cephvr.visual_stimulus.resources.physical_field import DEFAULTS
from cephvr.visual_stimulus.resources.sparse_noise import (
    WORKING_BYTES_PER_CELL,
    grid_for_extent,
    pattern_rgba,
    resolve_grids,
)
from cephvr.visual_stimulus.resources.texture_recipe import (
    estimated_working_bytes,
    generate_texture_recipe,
    parse_texture_recipe,
)

from .files import json_bytes, limits, read_bytes

TILE_WIDTH_MM = 100.0


def display_pixels(pixels: np.ndarray) -> np.ndarray:
    """Use the backend transfer function through a bounded RGB8 lookup table."""
    from cephvr.visual_stimulus.rendering.color import linear_to_srgb

    table = np.asarray(
        [round(linear_to_srgb(i / 255) * 255) for i in range(256)], dtype=np.uint8
    )
    return np.asarray(table[pixels])


def authored_recipe(document: dict[str, Any]) -> dict[str, Any]:
    """Normalize appearance without embedding any consumer sampling window."""
    result = copy.deepcopy(document)
    if result.get("kind") == "sparse_noise":
        return parse_sparse_noise_appearance(
            json.dumps(result), max_bytes=limits().max_document_bytes
        ).model_dump(mode="json")
    if result.get("kind") != "texture":
        return result
    params = result["params"]
    params.pop("texture_resolution", None)
    params.pop("size", None)
    result.pop("size", None)
    if result["pattern"] in {"bars_horizontal", "bars_vertical"}:
        bar = float(params.get("bar_width_mm", params.get("line_width_mm", 5)))
        if not math.isfinite(bar * 2) or bar < 0.001:
            raise ValueError("Bar width must be finite and at least 0.001 mm")
        params["bar_width_mm"] = bar
    pattern = result["pattern"]
    if pattern != "image":
        if pattern not in DEFAULTS:
            raise ValueError(f"Unsupported physical texture pattern: {pattern}")
        allowed = DEFAULTS[pattern].keys() | {"color_a", "color_b"}
        derived = {
            "tile_width_mm",
            "tile_height_mm",
            "tile_size_mm",
            "features_per_tile",
            "phase_cycles",
            "fit_cycles_to_tile",
            "tile_local",
            "origin_screen",
            "target_screen",
            "origin_face",
            "target_face",
            "element_size",
            "blur",
            "line_width_mm",
            "line_spacing_mm",
        }
        unknown = params.keys() - allowed - derived
        if unknown:
            raise ValueError(
                f"Unsupported texture appearance parameters: {sorted(unknown)}"
            )
        if pattern in {"noise_binary", "noise_gray"}:
            params.setdefault("element_size_mm", params.get("element_size", 1.0))
            params.setdefault("blur_mm", params.get("blur", 0.0))
        result["params"] = {
            key: value for key, value in params.items() if key in allowed
        }
        result["cephvr_asset_type"] = "texture_field"
        result["format_version"] = 1
    else:
        result["cephvr_asset_type"] = "texture_design"
        result.pop("format_version", None)
        width = TILE_WIDTH_MM
        params["tile_width_mm"] = width
        params["tile_height_mm"] = width
    return result


# The catalogue defines editable parameters; pixel algorithms stay backend-owned.
PATTERNS: dict[str, dict[str, Any]] = {**DEFAULTS, "image": {"texture_path": ""}}


def new_texture(pattern: str = "grating") -> dict[str, Any]:
    if pattern == "sparse_noise":
        return dict(
            format_version=2,
            kind="sparse_noise",
            seed=0,
            square_size_mm=5.0,
            min_active_cell_distance_mm=10.0,
            active_probability=0.5,
            background_linear=0.5,
        )
    return {
        "cephvr_asset_type": "texture_design"
        if pattern == "image"
        else "texture_field",
        **({} if pattern == "image" else {"format_version": 1}),
        "kind": "texture",
        "pattern": pattern,
        "params": {
            **(
                {"tile_width_mm": TILE_WIDTH_MM, "tile_height_mm": TILE_WIDTH_MM}
                if pattern == "image"
                else {}
            ),
            "color_a": [1.0] * 3,
            "color_b": [0.0] * 3,
            **PATTERNS[pattern],
        },
    }


def validate_texture(document: dict[str, Any]) -> None:
    if document.get("kind") == "sparse_noise":
        parse_sparse_noise_appearance(
            json.dumps(document), max_bytes=limits().max_document_bytes
        )
    else:
        budget = limits()
        recipe = parse_texture_recipe(
            json_bytes(document),
            max_document_bytes=budget.max_document_bytes,
            max_texture_pixels=budget.max_asset_cpu_bytes // 192,
        )
        if estimated_working_bytes(recipe) > budget.max_asset_cpu_bytes:
            raise ValueError("Texture exceeds preparation memory budget")


def texture_pixels(
    document: dict[str, Any],
    root: Path,
    geometry: Geometry | None = None,
    *,
    face: str = "front",
    index: int = 0,
    check: Callable[[], None] = lambda: None,
    recipe_directory: Path | None = None,
    read_image: Callable[[Path], bytes] | None = None,
    authored: bool = True,
    extent_mm: tuple[float, float] = (100.0, 100.0),
    sample_size: tuple[int, int] | None = None,
) -> np.ndarray:
    if authored:
        document = authored_recipe(document)
    validate_texture(document)
    check()
    budget = limits()
    if document.get("kind") == "sparse_noise":
        if type(index) is not int or not 0 <= index < budget.max_expanded_epochs:
            raise ValueError("Sparse-noise preview index exceeds preparation budget")
        # Preview timing only satisfies the preparation model; it is never saved.
        recipe = SparseNoiseRecipe.model_validate_json(
            json.dumps(
                {
                    **authored_recipe(document),
                    "surfaces": [face],
                    "pattern_count": index + 1,
                    "pattern_duration": {"seconds": "60"},
                }
            )
        )
        grid = (
            grid_for_extent(
                recipe,
                "front",
                100,
                100,
                max_cells=budget.max_asset_cpu_bytes // WORKING_BYTES_PER_CELL,
            )
            if geometry is None
            else resolve_grids(
                recipe,
                geometry,
                max_cells=budget.max_asset_cpu_bytes // WORKING_BYTES_PER_CELL,
            )[0]
        )
        rgba = np.frombuffer(
            pattern_rgba(recipe, grid, index, check=check), dtype=np.uint8
        ).reshape(grid.rows, grid.columns, 4)
        rgb = np.full(
            (grid.rows, grid.columns, 3),
            round(recipe.background_linear * 255),
            dtype=np.uint8,
        )
        return np.where(rgba[:, :, 3:4] != 0, rgba[:, :, :3], rgb)
    parsed = parse_texture_recipe(json_bytes(document))
    if (
        sample_size is not None
        and sample_size[0] * sample_size[1] * 192 > budget.max_asset_cpu_bytes
    ):
        raise ValueError("Texture sampling exceeds preparation memory budget")
    corners: dict[str, object] | None = (
        None
        if geometry is None
        else {
            s.surface_id: [
                s.bottom_left_mm,
                s.bottom_right_mm,
                s.top_right_mm,
                s.top_left_mm,
            ]
            for s in geometry.surfaces
        }
    )
    pixels = None
    if parsed.pattern == "image":
        name = str(parsed.params.get("texture_path", ""))
        base = recipe_directory or root
        source = (base / name).resolve()
        if Path(name).is_absolute() or ".." in Path(name).parts or "\\" in name:
            raise ValueError(
                "Texture path must be a relative child of the recipe directory"
            )
        source.relative_to(root.resolve())
        raw = (
            read_bytes(source, budget.max_asset_cpu_bytes)
            if read_image is None
            else read_image(source)
        )
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height * 192 > budget.max_asset_cpu_bytes:
                raise ValueError("Image exceeds preparation pixel budget")
            pixels = np.asarray(image.convert("RGB"))
    return generate_texture_recipe(
        parsed,
        surface_corners=corners,
        image_pixels=pixels,
        check=check,
        extent_mm=extent_mm,
        sample_size=sample_size,
    )


def load_geometry(path: Path) -> Geometry:
    data = json.loads(read_bytes(path, limits().max_document_bytes))
    if data.get("format") == "cephvr-rig-calibration":
        from cephvr.gui.calibration_arena import geometry_from_calibration
        from cephvr.visual_stimulus.configuration import load_projection_settings

        rig, screens = geometry_from_calibration(data)
        data = {
            "frame_id": "rig-mm",
            "observer_mm": rig.subject,
            **load_projection_settings(),
            "surfaces": [
                {
                    "surface_id": name.lower(),
                    **dict(
                        zip(
                            (
                                "bottom_left_mm",
                                "bottom_right_mm",
                                "top_right_mm",
                                "top_left_mm",
                            ),
                            corners,
                            strict=True,
                        )
                    ),
                }
                for name, corners in screens.items()
            ],
        }
    return Geometry.model_validate_json(json.dumps(data.get("geometry", data)))
