"""Resolve prepared media and CephVR1 texture export bundles inside one asset root."""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cephvr.gui.program_editing import NodePath, data_node
from cephvr.visual_stimulus.config.models.schema_common import portable_path

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


def resolve_stimulus_file(root: str, path: str, *, texture: bool) -> StimulusFile:
    if not root:
        raise ValueError("Choose the Assets folder first")
    base = Path(root).resolve()
    selected = Path(path).resolve()
    selected.relative_to(base)
    width = height = None
    if selected.name.endswith(".texture.json"):
        if not texture:
            raise ValueError("Texture designs can only be selected for a texture")
        with selected.open("rb") as stream:
            raw = stream.read(1_048_577)
        if len(raw) > 1_048_576:
            raise ValueError("Texture design exceeds 1 MiB")
        design = json.loads(raw)
        if (
            not isinstance(design, dict)
            or design.get("cephvr_asset_type") != "texture_design"
            or design.get("kind") != "texture"
        ):
            raise ValueError("Expected a CephVR1.0 texture design export")
        preview = portable_path(design.get("preview_file", ""))
        if not preview:
            raise ValueError("Export the texture with its companion PNG first")
        parameters = design.get("params", {})
        if not isinstance(parameters, dict):
            raise ValueError("Invalid texture design parameters")
        width = float(parameters.get("tile_width_mm", 0))
        height = float(parameters.get("tile_height_mm", width))
        if not all(math.isfinite(value) and value > 0 for value in (width, height)):
            raise ValueError("Texture export must declare a positive tile_width_mm")
        selected = (selected.parent / preview).resolve()
        selected.relative_to(base)
        if selected.suffix.lower() != ".png":
            raise ValueError("Texture design companion must be its exported PNG")
    if not selected.is_file():
        raise ValueError("Selected media or texture companion file is missing")
    suffix = selected.suffix.lower()
    if suffix not in PROFILES:
        raise ValueError(
            "Select a supported image, video, GLB arena or .texture.json export"
        )
    return StimulusFile(
        portable_path(selected.relative_to(base).as_posix()),
        PROFILES[suffix],
        width,
        height,
    )


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
