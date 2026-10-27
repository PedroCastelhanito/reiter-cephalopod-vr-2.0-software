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


# Legacy names that authored_recipe maps onto retained field parameters.
_RENAMED = {"line_width_mm", "element_size", "blur"}


def conversion_notice(raw: dict[str, Any], converted: dict[str, Any]) -> str | None:
    """Describe a legacy raster recipe converted to a physical field, else None."""
    if raw.get("cephvr_asset_type") == "texture_field" or (
        converted.get("cephvr_asset_type") != "texture_field"
    ):
        return None
    top = raw.keys() - converted.keys() - {"cephvr_asset_type"}
    params = raw.get("params", {}).keys() - converted["params"].keys() - _RENAMED
    dropped = ", ".join(sorted(top) + sorted(params)) or "none"
    return (
        "Legacy texture converted to a physical field; dropped fields: "
        f"{dropped}. The pattern is rendered by the seeded field algorithm and can "
        "differ from the legacy raster. The original file is never overwritten; "
        "save the converted design as a new file."
    )


def save_suggestion(previous: Path | None, legacy: bool, default: Path) -> str:
    """Default Save as… name; a converted legacy file gets a new, suffixed name."""
    if previous is not None and legacy:
        return str(previous.with_name(f"{previous.stem}.converted.json"))
    return str(previous or default)


def load_design(path: Path) -> tuple[dict[str, Any], str | None]:
    """Read a design plus a notice when a legacy recipe was converted on open."""
    data = json.loads(read_bytes(path, limits().max_document_bytes))
    if not isinstance(data, dict):
        raise ValueError("A design must be a JSON object")
    if data.get("kind") == "arena_design":
        return ArenaDesign.model_validate(data).model_dump(mode="json"), None
    validate_texture(data)
    design = authored_recipe(data)
    return design, conversion_notice(data, design)


def read_design(path: Path) -> dict[str, Any]:
    return load_design(path)[0]


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
            texture_pixels(
                candidate, root, recipe_directory=path.parent, authored=False
            )
    raw = json_bytes(candidate)
    if len(raw) > limits().max_document_bytes:
        raise ValueError("Design exceeds document budget")
    atomic_write(path, raw)
    return candidate
