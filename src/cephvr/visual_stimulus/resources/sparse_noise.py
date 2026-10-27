"""Seeded sparse-noise grids; the runtime helper streams them per pattern (V04).

Offline reproduction (analysis machine)
---------------------------------------
`pattern_rgba(recipe, grid, index)` is a pure function: integer RNG streams seeded
from SHA-256 of (GENERATOR, seed, surface, index, stream), IEEE double arithmetic, no
GPU, numpy, threads or dict/set iteration order. It returns the same bytes on any OS
or CPU when all of these hold:

1. Generator: the trial's recorded GENERATOR id equals this module's. Any change that
   alters output must bump GENERATOR; the stencil rewrite of `eligible_cells` kept
   output byte-identical under the same id.
2. Python: the version recorded in the trial's renderer provenance (3.11 on the rig).
   `random.random()` is stable across versions, but `random.shuffle` is not guaranteed.
3. Inputs: the layer's appearance, pattern count and surface, plus the display
   profile, all from the trial's `_stimulus_LOG.json` prepared snapshot. Resolve the
   grid with `resolve_grids` on that logged profile, never a later calibration.
4. Index: per-frame evidence (Save On) `State.images` holds one ImageSelection per
   sparse layer, with asset_id equal to the instance_id; pair it with
   `State.epoch_occurrence`, since indices restart at 0 each occurrence. Use
   image_index (actual), not requested_image_index. Disposition is current,
   residency_hold (newest earlier pattern held) or background_hold (image_index null:
   only the background was drawn before the occurrence's first pattern arrived).

Layout: byte offset 4 * (row * columns + column); row 0 is the surface's top edge and
column 0 its left edge (bottom_left to top_left side). Inactive cells are transparent
(alpha 0) and show the layer's linear background. The GL upload flips rows.
Residual risk: `math.dist` may differ in the last bit between platforms, which only
changes the grid when width / square size is within ~1e-13 of an integer.
Verification: the first frame showing each pattern (repeated false) records
pattern_sha256, the hex SHA-256 of these `pattern_rgba` bytes, and pattern_generator.
Check each regenerated pattern against it; a mismatch means a condition above failed.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Callable, Collection
from dataclasses import dataclass

from cephvr.visual_stimulus.config.models.display_profile import (
    DisplayProfile,
    Geometry,
)
from cephvr.visual_stimulus.config.models.schema_common import SurfaceId
from cephvr.visual_stimulus.config.models.sparse_noise import SparseNoisePatternRecipe

GENERATOR = "cephvr-sparse-noise-spaced-bernoulli-v2"
# Absorbs float error in mm/mm ratios (2.1 / 0.3 > 7) so exact cell distances qualify.
_DISTANCE_TOLERANCE = 1e-9
WORKING_BYTES_PER_CELL = 512  # Candidate order, blocked mask, selections and RGBA.


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
    active_surfaces: Collection[str] | None = None,
) -> tuple[SparseNoiseGrid, ...]:
    """Fit centered complete cells; never stretch squares or repeat the field.

    A DisplayProfile supplies its active output mappings. A bare Geometry carries no
    output data, so unless the caller passes `active_surfaces` every geometry surface
    counts as active and inactive outputs fail at Setup/compile instead (V04).
    """
    if type(max_cells) is not int or max_cells <= 0:
        raise ValueError("positive integer cell budget required")
    geometry = display.geometry if isinstance(display, DisplayProfile) else display
    active: set[str]
    if isinstance(display, DisplayProfile):
        active = {m.surface_id for m in display.active_mappings}
        if active_surfaces is not None:
            active &= {str(name) for name in active_surfaces}
    else:
        active = (
            {s.surface_id for s in geometry.surfaces}
            if active_surfaces is None
            else {str(name) for name in active_surfaces}
        )
    grids = []
    for name in sorted(recipe.surfaces):
        if name not in active:
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
    if distance <= 1 + _DISTANCE_TOLERANCE:
        return tuple(candidates)
    columns, rows = grid.columns, grid.rows
    # Integer-offset disk: row offset dy excludes |dx| <= reach[dy]. Same strict test
    # as comparing every accepted pair, so layouts are unchanged; marking costs one
    # slice per stencil row instead of a neighbour scan per candidate.
    limit = distance * distance - _DISTANCE_TOLERANCE
    reach: list[int] = []
    dx = min(columns - 1, math.ceil(distance))
    for dy in range(rows):
        while dx >= 0 and dx * dx + dy * dy >= limit:
            dx -= 1
        if dx < 0:
            break
        reach.append(dx)
    blocked = bytearray(columns * rows)
    ones = b"\x01" * columns
    selected = []
    for count, cell in enumerate(candidates):
        if count % 256 == 0:
            check()
        if blocked[cell]:
            continue
        selected.append(cell)
        y, x = divmod(cell, columns)
        for dy, dx in enumerate(reach):
            left = max(0, x - dx)
            span = min(columns, x + dx + 1) - left
            for row in (y - dy, y + dy) if dy else (y,):
                if 0 <= row < rows:
                    start = row * columns + left
                    blocked[start : start + span] = ones[:span]
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
    draw, flip, probability = (
        activation.random,
        polarity.getrandbits,
        recipe.active_probability,
    )
    texels = (b"\x00\x00\x00\xff", b"\xff\xff\xff\xff")
    pixels = bytearray(grid.columns * grid.rows * 4)
    for count, cell in enumerate(selected):
        if count % 256 == 0:
            check()
        # Both streams advance for every eligible cell, active or not.
        active = draw() < probability
        texel = texels[flip(1)]
        if active:
            pixels[cell * 4 : cell * 4 + 4] = texel
    return bytes(pixels)
