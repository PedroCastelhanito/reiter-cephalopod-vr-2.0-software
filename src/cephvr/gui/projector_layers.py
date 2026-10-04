"""Projector/layer selection and canonical isolation of projector-local edits."""

from copy import deepcopy
from dataclasses import dataclass
from pathlib import PurePosixPath

from cephvr.gui.program_editing import (
    NodePath,
    data_node,
    node_at,
    private_scene,
    unique_id,
    validate,
)
from cephvr.gui.stimulus_scope import set_surfaces, surfaces
from cephvr.visual_stimulus.config.models.program_model import Epoch, Program, Settings


def layer_title(program: Program, setting: Settings) -> str:
    data = setting.model_dump(mode="json")
    asset = data.get("asset_id", data.get("pattern", {}).get("asset_id"))
    source = next((a.logical_path for a in program.assets if a.asset_id == asset), "")
    kind = "3D arena (rig-wide)" if setting.kind == "arena" else setting.kind.title()
    if setting.kind == "image" and setting.width.kind == "keyframes":
        kind = "Looming"
    return f"{kind} · {PurePosixPath(source).name}" if source else kind


def layers_for(program: Program, epoch: Epoch, face: str) -> list[int]:
    scene = next(s for s in program.scenes if s.scene_id == epoch.scene_id)
    order = ([scene.arena_instance_id] if scene.arena_instance_id else []) + list(
        scene.layer_instance_ids
    )
    return [
        next(i for i, s in enumerate(epoch.settings) if s.instance_id == identity)
        for identity in order
        if any(
            s.instance_id == identity
            and (
                not face
                or s.kind == "arena"
                or face.lower() in surfaces(s.model_dump(mode="json"))
            )
            for s in epoch.settings
        )
    ]


def detach_layer(
    program: Program, path: NodePath, layer: int, face: str
) -> tuple[Program, int]:
    data = program.model_dump(mode="json")
    epoch = data_node(data, path)
    setting = epoch["settings"][layer]
    faces = surfaces(setting)
    if not face or face.lower() not in faces or len(faces) < 2:
        return program, layer
    copy = deepcopy(setting)
    copy["instance_id"] = unique_id(data, f"{face.lower()}_layer")
    set_surfaces(copy, [face.lower()])
    set_surfaces(setting, [f for f in faces if f != face.lower()])
    scene = private_scene(data, epoch)
    position = scene["layer_instance_ids"].index(setting["instance_id"])
    scene["layer_instance_ids"].insert(position + 1, copy["instance_id"])
    data["instances"].append(dict(instance_id=copy["instance_id"], family=copy["kind"]))
    epoch["settings"].insert(layer + 1, copy)
    return validate(data), layer + 1


def projector_edit(
    original: Program, edited: Program, path: NodePath, layer: int, face: str
) -> tuple[Program, int]:
    if original == edited:
        return original, layer
    detached, selected = detach_layer(original, path, layer, face)
    if detached == original:
        return edited, layer
    data = detached.model_dump(mode="json")
    candidate = edited.model_dump(mode="json")
    settings = data_node(data, path)["settings"]
    value = deepcopy(data_node(candidate, path)["settings"][layer])
    value["instance_id"] = settings[selected]["instance_id"]
    set_surfaces(value, [face.lower()])
    settings[selected] = value
    known = {a["asset_id"] for a in data["assets"]}
    data["assets"].extend(a for a in candidate["assets"] if a["asset_id"] not in known)
    data["input_channels"] = candidate["input_channels"]
    return validate(data), selected


@dataclass
class ProjectorLayers:
    """Current canonical selection, independent of any selection widget."""

    face: str = ""
    layer: int = -1

    def bind(
        self,
        program: Program,
        path: NodePath,
        screens: tuple[str, ...],
        preferred: int | None,
    ) -> None:
        node = node_at(program, path)
        available = (
            layers_for(program, node, self.face) if isinstance(node, Epoch) else []
        )
        self.layer = preferred if preferred in available else next(iter(available), -1)


def reorder_projector_layer(
    program: Program, path: NodePath, layer: int, face: str, delta: int
) -> tuple[Program, int]:
    epoch = node_at(program, path)
    assert isinstance(epoch, Epoch)
    visible = [
        i for i in layers_for(program, epoch, face) if epoch.settings[i].kind != "arena"
    ]
    if layer not in visible:
        raise ValueError("The arena is always behind 2D layers")
    other = visible.index(layer) + delta
    if not 0 <= other < len(visible):
        return program, layer
    other_id = epoch.settings[visible[other]].instance_id
    local, selected = detach_layer(program, path, layer, face)
    data = local.model_dump(mode="json")
    target = data_node(data, path)
    scene = private_scene(data, target)
    order = scene["layer_instance_ids"]
    selected_id = target["settings"][selected]["instance_id"]
    a, b = order.index(selected_id), order.index(other_id)
    # Move only the detached layer; the other projectors retain their stack order.
    order.pop(a)
    order.insert(b, selected_id)
    return validate(data), selected
