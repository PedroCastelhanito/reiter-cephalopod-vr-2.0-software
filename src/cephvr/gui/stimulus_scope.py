"""Copy-on-write screen scopes and independent per-screen layer settings."""

from copy import deepcopy
from typing import Any

from cephvr.gui.program_editing import (
    NodePath,
    data_node,
    private_scene,
    unique_id,
    validate,
)
from cephvr.visual_stimulus.config.models.program_model import Program

FACES = ("front", "left", "right", "bottom")


def surfaces(setting: dict[str, Any]) -> list[str]:
    if setting["kind"] == "arena":
        return []
    space = setting["space"]
    return (
        list(space["surfaces"])
        if space["kind"] == "visual_angle"
        else [m["surface_id"] for m in space["mappings"]]
    )


def set_surfaces(setting: dict[str, Any], faces: list[str]) -> None:
    if not faces:
        raise ValueError(
            "Choose at least one screen; remove the layer to make it blank"
        )
    space = setting["space"]
    if space["kind"] == "visual_angle":
        space["surfaces"] = faces
    else:
        existing = {m["surface_id"]: m for m in space["mappings"]}
        space["mappings"] = [
            existing.get(
                face, {"surface_id": face, "matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]}
            )
            for face in faces
        ]


def change_scope(
    program: Program, path: NodePath, layer: int, faces: list[str]
) -> Program:
    data = program.model_dump(mode="json")
    setting = data_node(data, path)["settings"][layer]
    if setting["kind"] == "arena":
        raise ValueError("Arena projection follows enabled rig screens")
    set_surfaces(setting, faces)
    return validate(data)


def split_screens(program: Program, path: NodePath, layer: int) -> Program:
    data = program.model_dump(mode="json")
    epoch = data_node(data, path)
    source = epoch["settings"][layer]
    faces = surfaces(source)
    if len(faces) < 2:
        raise ValueError("Select a layer shared by at least two screens")
    scene = private_scene(data, epoch)
    original = source["instance_id"]
    position = scene["layer_instance_ids"].index(original)
    replacements = []
    for index, face in enumerate(faces):
        setting = deepcopy(source)
        if index:
            setting["instance_id"] = unique_id(data, f"{face}_layer")
            data["instances"].append(
                {"instance_id": setting["instance_id"], "family": source["kind"]}
            )
        set_surfaces(setting, [face])
        replacements.append(setting)
    scene["layer_instance_ids"][position : position + 1] = [
        s["instance_id"] for s in replacements
    ]
    epoch["settings"][layer : layer + 1] = replacements
    return validate(data)


def move_layer(
    program: Program, path: NodePath, layer: int, delta: int
) -> tuple[Program, int]:
    data = program.model_dump(mode="json")
    epoch = data_node(data, path)
    source = epoch["settings"][layer]
    if source["kind"] == "arena":
        raise ValueError("The arena is always behind 2D layers")
    scene = private_scene(data, epoch)
    order = scene["layer_instance_ids"]
    position = order.index(source["instance_id"])
    other = position + delta
    if not 0 <= other < len(order):
        return program, layer
    order[position], order[other] = order[other], order[position]
    settings = {s["instance_id"]: s for s in epoch["settings"]}
    ids = ([scene["arena_instance_id"]] if scene["arena_instance_id"] else []) + order
    epoch["settings"] = [settings[identity] for identity in ids]
    return validate(data), ids.index(source["instance_id"])
