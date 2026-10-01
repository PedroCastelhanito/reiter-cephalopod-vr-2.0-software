"""Exact shader uniform snapshots captured at the upload boundary."""

from __future__ import annotations

import math
import struct
from collections.abc import Sequence
from typing import Any

from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.rendering.arena import arena_model_matrix, gl_matrix_words
from cephvr.visual_stimulus.rendering.types import InstanceSnapshot, UniformSnapshot


def clip_vertex_components(
    normalized: Sequence[tuple[float, float]],
) -> tuple[float, ...]:
    """Canonical bottom-left, bottom-right, top-right, top-left GLSL vertex order."""
    if len(normalized) != 4:
        raise ValueError("a mapped layer requires four projected corners")
    ordered = (normalized[0], normalized[1], normalized[3], normalized[2])
    values = tuple(component for corner in ordered for component in corner)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("projected clip vertices must be finite")
    return values


def float32_words(values: Sequence[float]) -> tuple[int, ...]:
    """Return the exact low-word-first binary32 payload uploaded to GLSL."""
    return tuple(struct.unpack("<I", struct.pack("<f", item))[0] for item in values)


def uniform_values(
    artifact: PreparedTrial, snapshot: InstanceSnapshot
) -> dict[str, Any]:

    state = dict(snapshot.state)
    settings = snapshot.settings
    if settings is not None and settings.kind == "arena":
        model = arena_model_matrix(settings, state)
        components = tuple(
            model[row][column] for row in range(4) for column in range(4)
        )
        values = {"arena_model_matrix": components}
    else:
        pattern = getattr(settings, "pattern", None)
        width = float(state.get("width", 0.0))
        height = float(state.get("height", 0.0))
        frequency = float(state.get("frequency", 0.0))
        frequency_pair = (frequency * width, 0.0)
        if pattern is not None and pattern.kind == "checkerboard":
            frequency_pair = (
                float(state.get("frequency_x", 0.0)) * width,
                float(state.get("frequency_y", 0.0)) * height,
            )
        phase_pair = (
            float(state.get("phase_x", 0.0)),
            float(state.get("phase_y", 0.0)),
        )
        period_pair = (
            width / float(state.get("period_x", 1.0)),
            height / float(state.get("period_y", 1.0)),
        )
        values = {
            "opacity": (float(state.get("opacity", 1.0)),),
            "contrast": (float(state.get("contrast", 1.0)),),
            "mean_rgb": tuple(getattr(settings, "mean_linear_rgb", (0.0, 0.0, 0.0))),
            "modulation_rgb": tuple(
                getattr(settings, "modulation_linear_rgb", (0.0, 0.0, 0.0))
            ),
            "frequency": frequency_pair,
            "phase": phase_pair,
            "period": period_pair,
        }
    result = {}
    for layout in artifact.uniform_layouts:
        if layout.instance_id != snapshot.instance_id or layout.name.startswith(
            "clip_vertices_"
        ):
            continue
        components = values[layout.name]
        words = (
            gl_matrix_words(arena_model_matrix(settings, state))
            if layout.name == "arena_model_matrix"
            else float32_words(components)
        )
        result[layout.binding_id] = UniformSnapshot(layout.binding_id, words)
    return result
