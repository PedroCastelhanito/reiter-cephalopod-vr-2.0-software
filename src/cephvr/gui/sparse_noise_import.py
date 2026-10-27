"""File preparation for the sparse-noise picker; no widgets or runtime commands."""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from cephvr.visual_stimulus.config.models.display_profile import Geometry
from cephvr.visual_stimulus.config.models.program_model import (
    Program,
    parse_program_json,
)
from cephvr.visual_stimulus.config.models.schema_common import (
    DEFAULT_DOCUMENT_BYTES,
    SurfaceId,
)
from cephvr.visual_stimulus.config.models.sparse_noise import (
    SparseNoiseRecipe,
    parse_sparse_noise_appearance,
)
from cephvr.visual_stimulus.config.models.sparse_noise_appearance import (
    SparseNoiseAppearance,
)
from cephvr.visual_stimulus.configuration import load_file_policies
from cephvr.visual_stimulus.resources.sparse_noise import WORKING_BYTES_PER_CELL
from cephvr.visual_stimulus.resources.sparse_noise_selection import (
    prepare_sparse_noise_selection,
)


@dataclass(frozen=True)
class RecipeSelection:
    path: str
    recipe: SparseNoiseAppearance


def select_recipe(root: Path, path: str) -> RecipeSelection:
    selected = Path(path)
    selected = (
        (root / selected).resolve()
        if not selected.is_absolute()
        else selected.resolve()
    )
    relative = selected.relative_to(root.resolve()).as_posix()
    with selected.open("rb") as source:
        raw = source.read(DEFAULT_DOCUMENT_BYTES + 1)
    recipe = parse_sparse_noise_appearance(
        raw.decode("utf-8"), max_bytes=DEFAULT_DOCUMENT_BYTES
    )
    return RecipeSelection(relative, recipe)


def prepare_selection(
    selections: Mapping[SurfaceId, RecipeSelection],
    root: Path,
    geometry: Geometry,
    *,
    pattern_count: int,
    pattern_duration: str,
    check: Callable[[], None],
) -> tuple[Program, Path]:
    limits = load_file_policies(Path(__file__).resolve().parents[3]).limits
    root = root.resolve()
    destination = (root / "sparse-noise" / uuid4().hex).resolve()
    if not destination.is_relative_to(root):
        raise ValueError("Generated sparse-noise folder must remain inside Assets")
    path = prepare_sparse_noise_selection(
        {
            face: SparseNoiseRecipe.model_validate_json(
                json.dumps(
                    {
                        **value.recipe.model_dump(mode="json"),
                        "surfaces": [face],
                        "pattern_count": pattern_count,
                        "pattern_duration": {"seconds": pattern_duration},
                    }
                )
            )
            for face, value in selections.items()
        },
        geometry,
        destination,
        max_cells=limits.max_asset_cpu_bytes // WORKING_BYTES_PER_CELL,
        max_patterns=limits.max_expanded_epochs,
        max_document_bytes=limits.max_document_bytes,
        check=check,
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    prefix = destination.relative_to(root).as_posix()
    for asset in data["assets"]:
        asset["logical_path"] = f"{prefix}/{asset['logical_path']}"
    program = parse_program_json(json.dumps(data), max_bytes=limits.max_document_bytes)
    with (destination / "selection.json").open("x", encoding="utf-8") as output:
        json.dump(
            {
                "format": "cephvr-sparse-noise-selection-v1",
                "paths": {face: value.path for face, value in selections.items()},
                "pattern_count": pattern_count,
                "pattern_duration": pattern_duration,
            },
            output,
        )
    check()
    return program, path


def saved_selection(root: Path, program_path: str) -> tuple[dict[str, str], int, str]:
    """Restore picker paths only from a recognized bundle within the current root."""
    if not program_path:
        return {}, 600, "0.1"
    path = Path(program_path).resolve()
    if not path.is_relative_to(root.resolve()):
        return {}, 600, "0.1"
    try:
        with path.with_name("selection.json").open("rb") as source:
            raw = source.read(DEFAULT_DOCUMENT_BYTES + 1)
        if len(raw) > DEFAULT_DOCUMENT_BYTES:
            return {}, 600, "0.1"
        data = json.loads(raw)
        paths = data["paths"]
        if data["format"] != "cephvr-sparse-noise-selection-v1" or not isinstance(
            paths, dict
        ):
            return {}, 600, "0.1"
        paths = {
            face: value
            for face, value in paths.items()
            if face in {"front", "left", "right", "bottom"} and isinstance(value, str)
        }
        count = data.get("pattern_count", 600)
        duration = data.get("pattern_duration", "0.1")
        return paths, int(count), str(duration)
    except (OSError, ValueError, KeyError, TypeError):
        return {}, 600, "0.1"
