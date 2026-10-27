"""Authoring templates expressed only in the accepted V03 program grammar."""

import json
from copy import deepcopy

from cephvr.gui.program_editing import NodePath, data_node, drop_unused_assets, node_at
from cephvr.gui.protocol_document import review_program
from cephvr.gui.stimulus_layers import new_layer
from cephvr.visual_stimulus.config.models.program_model import (
    Epoch,
    Program,
    parse_program_json,
)
from cephvr.visual_stimulus.config.models.schema_common import DEFAULT_DOCUMENT_BYTES

FILE_TYPES = (
    "Uniform",
    "Image",
    "Video",
    "Sparse noise",
    "Grating",
    "Texture drift",
    "3D arena",
)

PRESETS = (
    "Uniform",
    "Sparse noise",
    "Texture drift",
    "Texture",
    "Grating",
    "Sine grating",
    "Square grating",
    "Checkerboard",
    "Image tile",
    "Image",
    "Looming image",
    "Video",
    "3D arena",
)


def add_stimulus(
    program: Program,
    index: NodePath,
    preset: str,
    screens: tuple[str, ...],
    *,
    subject_height_mm: float = 0.0,
) -> Program:
    if preset == "Texture drift":
        preset = "Texture"
    if preset not in PRESETS:
        raise ValueError("Unknown stimulus type")
    if not isinstance(node_at(program, index), Epoch):
        raise ValueError("Select an epoch before adding a stimulus")
    data = program.model_dump(mode="json")
    node = data_node(data, index)
    taken = {item["instance_id"] for item in data["instances"]}
    number = 1
    while f"stimulus_{number}" in taken:
        number += 1
    identity = f"stimulus_{number}"
    source = review_program().model_dump(mode="json")["sequence"][1]["settings"][0]
    source["reset"] = False
    source["instance_id"] = identity
    source["space"]["surfaces"] = [name.lower() for name in screens] or ["front"]
    seed = new_layer(preset, source, identity, subject_height_mm)
    source, family, profile, path = seed.setting, seed.family, seed.profile, seed.path
    scene = deepcopy(
        next(item for item in data["scenes"] if item["scene_id"] == node["scene_id"])
    )
    scene_ids = {item["scene_id"] for item in data["scenes"]}
    scene_id = f"scene_{identity}"
    while scene_id in scene_ids:
        scene_id += "_new"
    scene["scene_id"] = scene_id
    if family == "arena":
        if scene["arena_instance_id"] is not None:
            raise ValueError(
                "A scene supports one arena; remove the existing arena first"
            )
        scene["arena_instance_id"] = identity
    else:
        scene["layer_instance_ids"].append(identity)
    data["scenes"].append(scene)
    data["instances"].append({"instance_id": identity, "family": family})
    if profile:
        data["assets"].append(
            {
                "asset_id": identity,
                "logical_path": path,
                "profile": profile,
                "color_override": None,
            }
        )
    node["scene_id"] = scene_id
    node["settings"].append(source)
    return parse_program_json(json.dumps(data), max_bytes=DEFAULT_DOCUMENT_BYTES)


def remove_stimulus(program: Program, index: NodePath, layer: int) -> Program:
    node = node_at(program, index)
    if not isinstance(node, Epoch) or not 0 <= layer < len(node.settings):
        return program
    data = program.model_dump(mode="json")
    epoch = data_node(data, index)
    removed = epoch["settings"].pop(layer)
    identity = removed["instance_id"]
    old_assets = {
        removed.get("asset_id", removed.get("pattern", {}).get("asset_id", ""))
    }
    scene = deepcopy(
        next(item for item in data["scenes"] if item["scene_id"] == epoch["scene_id"])
    )
    scene_ids = {item["scene_id"] for item in data["scenes"]}
    scene_id = "edited_scene"
    while scene_id in scene_ids:
        scene_id += "_new"
    scene["scene_id"] = scene_id
    if scene["arena_instance_id"] == identity:
        scene["arena_instance_id"] = None
    scene["layer_instance_ids"] = [
        item for item in scene["layer_instance_ids"] if item != identity
    ]
    data["scenes"].append(scene)
    epoch["scene_id"] = scene_id
    drop_unused_assets(data, old_assets)
    return parse_program_json(json.dumps(data), max_bytes=DEFAULT_DOCUMENT_BYTES)


def add_file_stimulus(
    program: Program,
    index: NodePath,
    preset: str,
    screens: tuple[str, ...],
    root: str,
    path: str,
    *,
    subject_height_mm: float = 0.0,
) -> Program:
    from cephvr.gui.stimulus_files import resolve_stimulus_file

    selected = resolve_stimulus_file(
        root,
        path,
        texture=preset in ("Texture", "Texture drift", "Grating"),
        grating=preset == "Grating",
    )
    candidate = add_stimulus(
        program, index, preset, screens, subject_height_mm=subject_height_mm
    ).model_dump(mode="json")
    target = data_node(candidate, index)["settings"][-1]
    if preset == "Grating":
        identity = target["instance_id"]
        target["pattern"] = dict(
            kind="image_tile",
            asset_id=identity,
            period_x=dict(kind="constant", value=selected.tile_width_mm or 20.0),
            period_y=dict(kind="constant", value=selected.tile_height_mm or 20.0),
            sampling="linear",
        )
        candidate["assets"].append(
            dict(
                asset_id=identity,
                logical_path=selected.path,
                profile=selected.profile,
                color_override=None,
            )
        )
    identity = (
        target["pattern"]["asset_id"]
        if target["kind"] == "texture"
        else target["asset_id"]
    )
    for asset in candidate["assets"]:
        if asset["asset_id"] == identity:
            asset.update(logical_path=selected.path, profile=selected.profile)
    if selected.tile_width_mm is not None:
        target["pattern"]["period_x"] = {
            "kind": "constant",
            "value": selected.tile_width_mm,
        }
        target["pattern"]["period_y"] = {
            "kind": "constant",
            "value": selected.tile_height_mm,
        }
    return parse_program_json(json.dumps(candidate), max_bytes=DEFAULT_DOCUMENT_BYTES)
