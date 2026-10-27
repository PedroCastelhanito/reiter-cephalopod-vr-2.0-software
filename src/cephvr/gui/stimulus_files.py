"""Resolve selected media, importing external files into the protocol asset root."""

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cephvr.gui.program_editing import NodePath, data_node
from cephvr.visual_stimulus.config.models.program_model import Asset
from cephvr.visual_stimulus.config.models.schema_common import (
    DEFAULT_DOCUMENT_BYTES,
    portable_path,
)
from cephvr.visual_stimulus.resources.recipe_dependencies import image_dependency
from cephvr.visual_stimulus.resources.texture_recipe import (
    TextureRecipe,
    parse_texture_recipe,
)

PROFILES = {
    ".png": "png_uint_v1",
    ".tif": "tiff_uint_v1",
    ".tiff": "tiff_uint_v1",
    ".jpg": "jpeg8_v1",
    ".jpeg": "jpeg8_v1",
    ".mp4": "mp4_h264_sdr8_v1",
    ".mkv": "matroska_ffv1_v3_uint_v1",
    ".glb": "glb2_static_unlit_v1",
}


@dataclass(frozen=True)
class StimulusFile:
    path: str
    profile: str
    tile_width_mm: float | None = None
    tile_height_mm: float | None = None


def resolve_stimulus_file(
    root: str, path: str, *, texture: bool, grating: bool = False
) -> StimulusFile:
    if not root:
        raise ValueError("Choose the Assets folder first")
    base = Path(root).resolve()
    if not base.is_dir():
        raise ValueError("Choose an existing Assets folder first")
    selected = Path(path).resolve()
    width = height = None
    recipe = None
    if selected.suffix.lower() == ".json":
        if not texture:
            raise ValueError("Texture designs can only be selected for a texture")
        with selected.open("rb") as stream:
            raw = stream.read(DEFAULT_DOCUMENT_BYTES + 1)
        recipe = parse_texture_recipe(raw, max_document_bytes=DEFAULT_DOCUMENT_BYTES)
        from cephvr.visual_stimulus.config.media_profiles import GRATING_PROFILE
        from cephvr.visual_stimulus.resources.grating_recipe import interpreted_recipe

        profile = GRATING_PROFILE if grating else "cephvr1_texture_json_v1"
        recipe = interpreted_recipe(recipe, profile)
        width, height = recipe.tile_width_mm, recipe.tile_height_mm
        if recipe.physical_field and width is None:
            # One phase cycle represents one mm; appearance has no repeat period.
            width = height = 1.0
    else:
        if grating:
            raise ValueError("Grating requires a Grating texture design (.json)")
        if not selected.is_file():
            raise ValueError("Selected media file is missing")
        suffix = selected.suffix.lower()
        if suffix not in PROFILES:
            raise ValueError(
                "Select a supported image, video, GLB arena or texture JSON recipe"
            )
        profile = PROFILES[suffix]
    if not selected.is_relative_to(base):
        selected = _import_file(base, selected, recipe)
    return StimulusFile(
        portable_path(selected.relative_to(base).as_posix()),
        profile,
        width,
        height,
    )


# Imports made this session, keyed by (root, source, size, mtime) so that re-selecting
# an unchanged external file reuses its copy instead of copying again.
_IMPORTS: dict[tuple[Any, ...], Path] = {}


def _stamp(path: Path) -> tuple[str, int, int]:
    stat = path.stat()
    return str(path), stat.st_size, stat.st_mtime_ns


def _import_file(base: Path, selected: Path, recipe: TextureRecipe | None) -> Path:
    """Keep each import isolated; preserve recipe-relative image dependencies."""
    name = portable_path(selected.name)
    dependency = None
    if recipe is not None:
        dependency = image_dependency(
            selected.parent,
            Asset(
                asset_id="import",
                logical_path=name,
                profile="cephvr1_texture_json_v1",
                color_override=None,
            ),
            recipe,
        )
    source_dependency = (
        selected.parent / dependency.logical_path if dependency is not None else None
    )
    key = (
        str(base),
        _stamp(selected),
        _stamp(source_dependency) if source_dependency is not None else None,
    )
    cached = _IMPORTS.get(key)
    if (
        cached is not None
        and cached.is_file()
        and (dependency is None or (cached.parent / dependency.logical_path).is_file())
    ):
        return cached
    destination = Path(tempfile.mkdtemp(prefix="import-", dir=base))
    try:
        shutil.copyfile(selected, destination / name)
        if dependency is not None:
            assert source_dependency is not None
            target = destination / dependency.logical_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_dependency, target)
        _IMPORTS[key] = destination / name
        return destination / name
    except BaseException:
        shutil.rmtree(destination)
        raise


def select_epoch_asset(
    data: dict[str, Any],
    node: NodePath,
    layer: int,
    old_id: str,
    path: str,
    profile: str,
) -> None:
    """Replace this epoch's file without rewriting another epoch's shared asset."""
    previous = next(asset for asset in data["assets"] if asset["asset_id"] == old_id)
    if previous["logical_path"] == path and previous["profile"] == profile:
        return
    taken = {asset["asset_id"] for asset in data["assets"]}
    number = 1
    while f"asset_{number}" in taken:
        number += 1
    identity = f"asset_{number}"
    data["assets"].append(
        dict(previous, asset_id=identity, logical_path=path, profile=profile)
    )
    setting = data_node(data, node)["settings"][layer]
    if setting["kind"] == "texture":
        setting["pattern"]["asset_id"] = identity
    else:
        setting["asset_id"] = identity

    def contains(value: object) -> bool:
        if isinstance(value, dict):
            if value.get("asset_id") == old_id or (
                "column_id" in value and value.get("value") == old_id
            ):
                return True
            return any(contains(item) for item in value.values())
        if isinstance(value, list):
            return any(contains(item) for item in value)
        return False

    if not contains(data["sequence"]):
        data["assets"] = [
            asset for asset in data["assets"] if asset["asset_id"] != old_id
        ]


def apply_texture_dimensions(target: dict[str, Any], selected: StimulusFile) -> None:
    """Adopt exported physical tile dimensions while preserving linear speed."""
    if selected.tile_width_mm is None:
        return
    if target["space"]["kind"] != "physical_surface":
        raise ValueError(
            "A physical texture design requires physical-surface placement; angular conversion needs calibration"
        )
    for axis, period in (("x", selected.tile_width_mm), ("y", selected.tile_height_mm)):
        previous = target["pattern"][f"period_{axis}"]
        motion = target[f"phase_{axis}"]
        if previous["kind"] != "constant":
            raise ValueError("Cannot replace a texture with animated tile dimensions")
        if (
            motion["kind"] == "rate"
            and motion["function"]["kind"] == "constant"
            and isinstance(motion["function"]["value"], (int, float))
        ):
            motion["function"]["value"] *= previous["value"] / period
        elif motion["kind"] != "hold":
            raise ValueError(
                "Reset custom phase motion before replacing texture dimensions"
            )
        target["pattern"][f"period_{axis}"] = {"kind": "constant", "value": period}
