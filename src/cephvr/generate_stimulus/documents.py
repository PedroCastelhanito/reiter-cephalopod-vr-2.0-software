"""Validated document I/O and image dependency rebasing, independent of widgets."""

import copy
import json
from pathlib import Path
from typing import Any

from .files import atomic_write, json_bytes, limits, read_bytes
from .models import ArenaDesign
from .textures import authored_recipe, texture_pixels, validate_texture


def apply_changes(
    target: dict[str, Any], before: dict[str, Any], after: dict[str, Any]
) -> None:
    """Multi-edit only changed fields, preserving other surfaces' seeds and settings."""
    for key, value in after.items():
        if value == before.get(key):
            continue
        if isinstance(value, dict) and isinstance(before.get(key), dict):
            apply_changes(target[key], before[key], value)
        else:
            target[key] = copy.deepcopy(value)


def read_design(path: Path) -> dict[str, Any]:
    data = json.loads(read_bytes(path, limits().max_document_bytes))
    if not isinstance(data, dict):
        raise ValueError("A design must be a JSON object")
    if data.get("kind") == "arena_design":
        return ArenaDesign.model_validate(data).model_dump(mode="json")
    validate_texture(data)
    return authored_recipe(data)


def save_design(
    document: dict[str, Any], root: Path, path: Path, previous_directory: Path
) -> dict[str, Any]:
    candidate = copy.deepcopy(document)
    if candidate.get("kind") == "arena_design":
        ArenaDesign.model_validate(candidate)
    else:
        candidate = authored_recipe(candidate)
        validate_texture(candidate)
        if candidate.get("pattern") == "image":
            source = (
                previous_directory / candidate["params"]["texture_path"]
            ).resolve()
            try:
                relative = source.relative_to(path.parent.resolve()).as_posix()
            except ValueError as error:
                raise ValueError(
                    "Save image recipes in the image's directory or an ancestor directory"
                ) from error
            candidate["params"]["texture_path"] = relative
            texture_pixels(candidate, root, recipe_directory=path.parent)
    raw = json_bytes(candidate)
    if len(raw) > limits().max_document_bytes:
        raise ValueError("Design exceeds document budget")
    atomic_write(path, raw)
    return candidate
