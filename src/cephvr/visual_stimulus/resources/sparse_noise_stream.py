"""Time-ordered sparse-noise pattern requests for one prepared trial (V04).

The renderer and the generator helper derive the same request order from the same
prepared trial, so a ring slot only needs its request sequence number.
"""

from __future__ import annotations

import hashlib
import heapq
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.config.models.program_model import (
    Constant,
    SparseNoiseSettings,
    Time,
)
from cephvr.visual_stimulus.config.models.sparse_noise import SparseNoisePatternRecipe

from .sparse_noise import SparseNoiseGrid, pattern_rgba, resolve_grids

# Structural bound only; Setup admission bounds the actual ring memory.
MAX_GRID_CELLS = 1 << 24


@dataclass(frozen=True, slots=True)
class SparseLayer:
    """One sparse-noise layer in one epoch occurrence."""

    epoch_index: int
    instance_id: str
    start_ns: int  # Trial-relative epoch start.
    pattern_duration_ns: int
    shown: int  # Patterns this occurrence can present before its epoch ends.
    recipe: SparseNoisePatternRecipe
    grid: SparseNoiseGrid

    @property
    def texel_bytes(self) -> int:
        return self.grid.columns * self.grid.rows * 4


@dataclass(frozen=True, slots=True)
class PatternRequest:
    sequence: int
    layer: int  # Index into the trial's layers.
    pattern: int
    due_ns: int  # Trial-relative presentation time.


def layer_recipe(settings: SparseNoiseSettings) -> SparseNoisePatternRecipe:
    """Generator input; its duration is unused for epoch-held index-zero patterns."""
    surface = settings.space.mappings[0].surface_id  # type: ignore[union-attr]
    return SparseNoisePatternRecipe.model_validate(
        {
            **settings.appearance.model_dump(),
            "surfaces": (surface,),
            "pattern_count": settings.pattern_count,
            "pattern_duration": settings.pattern_duration or Time(seconds="1"),
        }
    )


def with_grid_extent(
    settings: SparseNoiseSettings, display: DisplayProfile
) -> SparseNoiseSettings:
    """Fix width/height to the centered complete-cell grid on the active screen."""
    (grid,) = resolve_grids(layer_recipe(settings), display, max_cells=MAX_GRID_CELLS)
    return settings.model_copy(
        update={
            "width": Constant(kind="constant", value=grid.width_mm),
            "height": Constant(kind="constant", value=grid.height_mm),
        }
    )


def trial_layers(artifact: PreparedTrial) -> tuple[SparseLayer, ...]:
    layers = []
    for index, epoch in enumerate(artifact.epochs):
        for settings in epoch.settings:
            if not isinstance(settings, SparseNoiseSettings):
                continue
            recipe = layer_recipe(settings)
            (grid,) = resolve_grids(recipe, artifact.display, max_cells=MAX_GRID_CELLS)
            span = epoch.end_ns - epoch.start_ns
            duration = (
                settings.pattern_duration.ns() if settings.pattern_duration else span
            )
            layers.append(
                SparseLayer(
                    index,
                    settings.instance_id,
                    epoch.start_ns,
                    duration,
                    min(settings.pattern_count, -(-span // duration)),
                    recipe,
                    grid,
                )
            )
    return tuple(layers)


def requests(layers: tuple[SparseLayer, ...]) -> Iterator[PatternRequest]:
    """Every pattern of every layer occurrence, ordered by due time then layer."""

    def patterns(index: int) -> Iterator[tuple[int, int, int]]:
        layer = layers[index]
        for pattern in range(layer.shown):
            yield layer.start_ns + pattern * layer.pattern_duration_ns, index, pattern

    merged = heapq.merge(*(patterns(i) for i in range(len(layers))))
    for sequence, (due, layer, pattern) in enumerate(merged):
        yield PatternRequest(sequence, layer, pattern, due)


def pattern_frame(
    layer: SparseLayer, pattern: int, *, check: Callable[[], None] = lambda: None
) -> tuple[bytes, bytes]:
    """GL-order texels and the SHA-256 of the generator's top-row-first cell bytes."""
    rgba = pattern_rgba(layer.recipe, layer.grid, pattern, check=check)
    stride = layer.grid.columns * 4
    view = memoryview(rgba)
    texels = b"".join(
        view[row * stride : (row + 1) * stride]
        for row in reversed(range(layer.grid.rows))
    )
    return texels, hashlib.sha256(rgba).digest()


def pattern_texels(
    layer: SparseLayer, pattern: int, *, check: Callable[[], None] = lambda: None
) -> bytes:
    """Premultiplied RGBA8, bottom row first for GL upload; cells equal pattern_rgba."""
    return pattern_frame(layer, pattern, check=check)[0]
