"""Prepare sparse-noise recipes as ordinary timed image programs, before Setup."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import random
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cephvr.visual_stimulus.config.models.display_profile import (
    DisplayProfile,
    Geometry,
)
from cephvr.visual_stimulus.config.models.program_model import Program
from cephvr.visual_stimulus.config.models.schema_common import SurfaceId
from cephvr.visual_stimulus.config.models.sparse_noise import SparseNoisePatternRecipe

GENERATOR = "cephvr-sparse-noise-spaced-bernoulli-v2"
WORKING_BYTES_PER_CELL = 512  # Candidate order, spatial buckets, selections and RGBA.


@dataclass(frozen=True)
class SparseNoiseGrid:
    surface_id: SurfaceId
    columns: int
    rows: int
    width_mm: float
    height_mm: float


def resolve_grids(
    recipe: SparseNoisePatternRecipe,
    display: DisplayProfile | Geometry,
    *,
    max_cells: int,
) -> tuple[SparseNoiseGrid, ...]:
    """Fit centered complete cells; never stretch squares or repeat the field."""
    if type(max_cells) is not int or max_cells <= 0:
        raise ValueError("positive integer cell budget required")
    geometry = display.geometry if isinstance(display, DisplayProfile) else display
    active_surfaces = (
        {m.surface_id for m in display.active_mappings}
        if isinstance(display, DisplayProfile)
        else {s.surface_id for s in geometry.surfaces}
    )
    grids = []
    for name in sorted(recipe.surfaces):
        if name not in active_surfaces:
            raise ValueError(f"sparse-noise surface {name} has no active output")
        surface = next(s for s in geometry.surfaces if s.surface_id == name)
        width = math.dist(surface.bottom_left_mm, surface.bottom_right_mm)
        height = math.dist(surface.bottom_left_mm, surface.top_left_mm)
        grids.append(grid_for_extent(recipe, name, width, height, max_cells=max_cells))
    return tuple(grids)


def grid_for_extent(
    recipe: SparseNoisePatternRecipe,
    name: SurfaceId,
    width: float,
    height: float,
    *,
    max_cells: int,
) -> SparseNoiseGrid:
    """Resolve a bounded cell grid for a physical surface or an appearance preview."""
    ratios = (width / recipe.square_size_mm, height / recipe.square_size_mm)
    if any(not math.isfinite(v) or v > max_cells for v in ratios):
        raise ValueError("sparse-noise grid exceeds cell budget")
    columns, rows = (math.floor(v) for v in ratios)
    cells = columns * rows
    if cells == 0:
        raise ValueError("square size must fit at least one complete screen cell")
    if cells > max_cells:
        raise ValueError("sparse-noise grid exceeds cell budget")
    return SparseNoiseGrid(
        name,
        columns,
        rows,
        columns * recipe.square_size_mm,
        rows * recipe.square_size_mm,
    )


def _pattern_rng(
    recipe: SparseNoisePatternRecipe, grid: SparseNoiseGrid, index: int, stream: str
) -> random.Random:
    if type(index) is not int or not 0 <= index < recipe.pattern_count:
        raise ValueError("Sparse-noise pattern index is outside the recipe")
    identity = (
        f"{GENERATOR}\n{recipe.seed}\n{grid.surface_id}\n{index}\n{stream}".encode(
            "ascii"
        )
    )
    return random.Random(int.from_bytes(hashlib.sha256(identity).digest(), "big"))


def eligible_cells(
    recipe: SparseNoisePatternRecipe,
    grid: SparseNoiseGrid,
    index: int,
    *,
    check: Callable[[], None] = lambda: None,
) -> tuple[int, ...]:
    """Random-order greedy separated layout; maximal, not maximum or uniform packing."""
    check()
    candidates = list(range(grid.columns * grid.rows))
    _pattern_rng(recipe, grid, index, "layout").shuffle(candidates)
    distance = min(
        recipe.min_active_cell_distance_mm / recipe.square_size_mm,
        math.hypot(grid.columns, grid.rows) + 1,
    )
    if distance <= 1:
        return tuple(candidates)
    buckets: dict[tuple[int, int], list[tuple[int, int]]] = {}
    selected = []
    for count, cell in enumerate(candidates):
        if count % 256 == 0:
            check()
        x, y = cell % grid.columns, cell // grid.columns
        bx, by = math.floor(x / distance), math.floor(y / distance)
        if any(
            (x - px) ** 2 + (y - py) ** 2 < distance * distance
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for px, py in buckets.get((bx + dx, by + dy), ())
        ):
            continue
        buckets.setdefault((bx, by), []).append((x, y))
        selected.append(cell)
    return tuple(selected)


def pattern_rgba(
    recipe: SparseNoisePatternRecipe,
    grid: SparseNoiseGrid,
    index: int,
    *,
    check: Callable[[], None] = lambda: None,
) -> bytes:
    """Independent layout, activation and polarity streams for one indexed pattern."""
    selected = eligible_cells(recipe, grid, index, check=check)
    activation = _pattern_rng(recipe, grid, index, "activation")
    polarity = _pattern_rng(recipe, grid, index, "polarity")
    pixels = bytearray(grid.columns * grid.rows * 4)
    for count, cell in enumerate(selected):
        if count % 256 == 0:
            check()
        active = activation.random() < recipe.active_probability
        level = 255 * polarity.getrandbits(1)
        if not active:
            continue
        offset = cell * 4
        pixels[offset : offset + 4] = bytes((level, level, level, 255))
    return bytes(pixels)


def _setting(grid: SparseNoiseGrid, asset_id: str) -> dict[str, Any]:
    def constant(value: float) -> dict[str, Any]:
        return {"kind": "constant", "value": value}

    return {
        "kind": "image",
        "instance_id": f"noise-{grid.surface_id}",
        "asset_id": asset_id,
        "sampling": "nearest",
        "fit": "stretch",
        "space": {
            "kind": "physical_surface",
            "frame_id": f"noise-{grid.surface_id}",
            "mappings": [
                {"surface_id": grid.surface_id, "matrix": [[1, 0, 0], [0, 1, 0]]}
            ],
        },
        "initial": {"x": 0, "y": 0, "rotation_deg": 0},
        "width": constant(grid.width_mm),
        "height": constant(grid.height_mm),
        "opacity": constant(1),
        "motion": {axis: {"kind": "hold"} for axis in ("x", "y", "rotation")},
        "reset": False,
        "assignments": [],
        "feedback": [],
    }


def prepare_sparse_noise(
    recipe: SparseNoisePatternRecipe,
    display: DisplayProfile | Geometry,
    destination: Path,
    *,
    max_cells: int,
    max_patterns: int,
    max_document_bytes: int,
    layer_sequence: bool = False,
    check: Callable[[], None] = lambda: None,
) -> Path:
    """Write a new bundle; publish program.json last, never overwrite existing data.

    Limits are supplied by the caller, not scientific defaults. A failed/cancelled
    preparation can leave an incomplete directory, without a playable program.json.
    Normal runtime Setup still performs resource admission and protects all assets.
    """
    for value in (max_patterns, max_document_bytes):
        if type(value) is not int or value <= 0:
            raise ValueError("positive integer preparation limits required")
    check()
    if recipe.pattern_count > max_patterns:
        raise ValueError("sparse-noise pattern count exceeds epoch budget")
    grids = resolve_grids(recipe, display, max_cells=max_cells)
    # Bound the expanded document before constructing its Python object graph.
    if recipe.pattern_count * len(grids) * 4096 > max_document_bytes:
        raise ValueError("sparse-noise expanded program exceeds document budget")
    assets, epochs = [], []
    for index in range(recipe.pattern_count):
        check()
        settings = []
        for grid in grids:
            asset_id = f"noise-{grid.surface_id}-{index}"
            assets.append(
                {
                    "asset_id": asset_id,
                    "logical_path": f"{asset_id}.png",
                    "profile": "png_uint_v1",
                    "color_override": {
                        "transfer": "linear",
                        "primaries": "rec709_d65",
                        "range": "full",
                        "matrix": "rgb",
                        "chroma_location": "none",
                        "reason": "Sparse-noise black/white with transparent background cells",
                    },
                }
            )
            settings.append(_setting(grid, asset_id))
        epochs.append(
            {
                "kind": "epoch",
                "epoch_id": f"pattern-{index}",
                "scene_id": "noise",
                "duration": {
                    "kind": "fixed",
                    "duration": recipe.pattern_duration.model_dump(),
                },
                "settings": settings,
            }
        )
    document = {
        "format_version": 2,
        "category": "media_presentation",
        "assets": assets,
        "instances": [
            {"instance_id": f"noise-{g.surface_id}", "family": "image"} for g in grids
        ],
        "scenes": [
            {
                "scene_id": "noise",
                "background_linear_rgb": [recipe.background_linear] * 3,
                "arena_instance_id": None,
                "layer_instance_ids": [f"noise-{g.surface_id}" for g in grids],
            }
        ],
        "input_channels": [],
        "duration": {"kind": "explicit_epochs"},
        "sequence": epochs,
    }
    if layer_sequence:
        document["format"] = "cephvr-sparse-noise-layer-v1"
    source = json.dumps(document, separators=(",", ":"), allow_nan=False)
    if len(source.encode("utf-8")) > max_document_bytes:
        raise ValueError("sparse-noise expanded program exceeds document budget")
    if not layer_sequence:
        Program.model_validate_json(source)
    from PIL import Image

    check()
    destination.mkdir(parents=True, exist_ok=False)
    records = []
    for index in range(recipe.pattern_count):
        for grid in grids:
            check()
            pixels = pattern_rgba(recipe, grid, index, check=check)
            path = destination / f"noise-{grid.surface_id}-{index}.png"
            with Image.frombytes("RGBA", (grid.columns, grid.rows), pixels) as image:
                with path.open("xb") as output:
                    image.save(output, format="PNG")
            records.append(
                {
                    "path": path.name,
                    "active_count": sum(pixels[3::4]) // 255,
                    "rgba_sha256": hashlib.sha256(pixels).hexdigest(),
                    "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    from dataclasses import asdict

    provenance = {
        "generator": GENERATOR,
        "python_version": platform.python_version(),
        "recipe": recipe.model_dump(mode="json"),
        "display"
        if isinstance(display, DisplayProfile)
        else "geometry": display.model_dump(mode="json"),
        "grids": [asdict(g) for g in grids],
        "patterns": records,
        "program_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
    }
    with (destination / "provenance.json").open(
        "x", encoding="utf-8", newline="\n"
    ) as output:
        json.dump(provenance, output, indent=2, allow_nan=False)
        output.write("\n")
    check()
    # Atomic visibility: a failed preparation must not advertise a complete program.
    staged = destination / "program.pending"
    with staged.open("x", encoding="utf-8", newline="\n") as output:
        output.write(source)
    target = destination / ("sequence.json" if layer_sequence else "program.json")
    staged.rename(target)
    return target
