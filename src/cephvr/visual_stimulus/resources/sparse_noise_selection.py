"""Combine independently authored screen recipes using the existing preparer."""

import json
from collections.abc import Callable, Mapping
from pathlib import Path

from cephvr.visual_stimulus.config.models.display_profile import Geometry
from cephvr.visual_stimulus.config.models.program_model import parse_program_json
from cephvr.visual_stimulus.config.models.schema_common import SurfaceId
from cephvr.visual_stimulus.config.models.sparse_noise import SparseNoiseRecipe
from cephvr.visual_stimulus.resources.sparse_noise import (
    prepare_sparse_noise,
    resolve_grids,
)


def prepare_sparse_noise_selection(
    recipes: Mapping[SurfaceId, SparseNoiseRecipe],
    geometry: Geometry,
    destination: Path,
    *,
    max_cells: int,
    max_patterns: int,
    max_document_bytes: int,
    check: Callable[[], None],
) -> Path:
    """One synchronized trial; selected rows override each recipe's surface list."""
    if not recipes:
        raise ValueError("Select a recipe for at least one projector")
    first = next(iter(recipes.values()))
    prepared = {}
    for face, recipe in sorted(recipes.items()):
        check()
        if (
            recipe.pattern_count,
            recipe.pattern_duration.ns(),
            recipe.background_linear,
        ) != (
            first.pattern_count,
            first.pattern_duration.ns(),
            first.background_linear,
        ):
            raise ValueError(
                "Recipes must have matching pattern counts, durations and backgrounds"
            )
        selected = SparseNoiseRecipe.model_validate_json(
            recipe.model_copy(update={"surfaces": (face,)}).model_dump_json()
        )
        resolve_grids(selected, geometry, max_cells=max_cells)
        prepared[face] = selected
    if first.pattern_count > max_patterns:
        raise ValueError("Sparse-noise pattern count exceeds epoch budget")
    if first.pattern_count * len(prepared) * 4096 > max_document_bytes:
        raise ValueError("Sparse-noise combined program exceeds document budget")
    destination.mkdir(parents=True, exist_ok=False)
    combined = None
    for face, recipe in prepared.items():
        path = prepare_sparse_noise(
            recipe,
            geometry,
            destination / face,
            max_cells=max_cells,
            max_patterns=max_patterns,
            max_document_bytes=max_document_bytes,
            check=check,
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        for asset in data["assets"]:
            asset["logical_path"] = f"{face}/{asset['logical_path']}"
        if combined is None:
            combined = data
        else:
            combined["assets"].extend(data["assets"])
            combined["instances"].extend(data["instances"])
            combined["scenes"][0]["layer_instance_ids"].extend(
                data["scenes"][0]["layer_instance_ids"]
            )
            for left, right in zip(combined["sequence"], data["sequence"], strict=True):
                left["settings"].extend(right["settings"])
    raw = json.dumps(combined, separators=(",", ":"), allow_nan=False)
    parse_program_json(raw, max_bytes=max_document_bytes)
    check()
    pending = destination / "program.pending"
    pending.write_text(raw, encoding="utf-8")
    path = destination / "program.json"
    pending.rename(path)
    return path
