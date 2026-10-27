"""Atomic batch edits and template insertion over canonical programs."""

from dataclasses import dataclass
from typing import Any

from cephvr.gui.arena_movement import patch_arena
from cephvr.gui.program_editing import data_node, node_at, unique_id, validate
from cephvr.gui.projector_layers import detach_layer, layers_for
from cephvr.gui.rig_parameter_edits import (
    parameter_value as parameter_value,
)
from cephvr.gui.rig_parameter_edits import patch_setting as patch_setting
from cephvr.gui.stimulus_columns import is_sparse_noise
from cephvr.gui.stimulus_fades import retime_fades
from cephvr.gui.stimulus_files import (
    apply_texture_dimensions,
    resolve_stimulus_file,
    select_epoch_asset,
)
from cephvr.visual_stimulus.config.models.program_model import (
    Epoch,
    Group,
    Node,
    Program,
    Time,
)
from cephvr.visual_stimulus.config.parameter_edits import END_BEHAVIORS as END_BEHAVIORS


def epoch_paths(program: Program) -> tuple[tuple[int, ...], ...]:
    result = []

    def visit(nodes: tuple[Node, ...], prefix: tuple[int, ...]) -> None:
        for i, node in enumerate(nodes):
            path = (*prefix, i)
            if isinstance(node, Group):
                visit(node.body, path)
            else:
                result.append(path)

    visit(program.sequence, ())
    return tuple(result)


def family(setting: Any) -> str:
    if setting.kind == "texture" and setting.uniform:
        return "Uniform"
    if is_sparse_noise(setting):
        return "Sparse noise"
    if setting.kind == "texture" and setting.grating:
        return "Grating"
    if setting.kind == "image" and setting.width.kind == "keyframes":
        return "Looming image"
    return {
        "texture": "Texture drift",
        "image": "Image",
        "video": "Video",
        "arena": "3D arena",
    }[setting.kind]


@dataclass(frozen=True)
class LayerTarget:
    face: str
    family: str
    ordinal: int = 0


def matching_layer(program: Program, path: tuple[int, ...], target: LayerTarget) -> int:
    node = node_at(program, path)
    assert isinstance(node, Epoch)
    candidates = [
        i
        for i in layers_for(program, node, target.face)
        if family(node.settings[i]) == target.family
    ]
    if target.ordinal >= len(candidates):
        raise ValueError(
            f"{node.epoch_id}: no {target.family} layer {target.ordinal + 1} on {target.face or 'All projectors'}"
        )
    return candidates[target.ordinal]


def apply_batch(
    program: Program,
    paths: tuple[tuple[int, ...], ...],
    target: LayerTarget | None,
    changes: dict[str, str],
    asset_root: str = "",
) -> Program:
    if not paths or not changes:
        raise ValueError("Select epochs and mark at least one field to change")
    result = program
    for path in dict.fromkeys(paths):
        setting_changes = {k: v for k, v in changes.items() if k != "Duration"}
        if setting_changes:
            if target is None:
                raise ValueError("Choose a stimulus layer")
            if target.family == "3D arena" and target.face:
                raise ValueError("Arena edits require All projectors")
            layer = matching_layer(result, path, target)
            result, layer = detach_layer(result, path, layer, target.face)
        data = result.model_dump(mode="json")
        node = data_node(data, path)
        if "Duration" in changes:
            old = node["duration"]
            if old["kind"] == "fixed":
                retime_fades(
                    node["settings"],
                    Time.model_validate(old["duration"]).ns(),
                    Time(seconds=changes["Duration"]).ns(),
                )
            node["duration"] = dict(
                kind="fixed", duration={"seconds": changes["Duration"]}
            )
        if setting_changes:
            setting = node["settings"][layer]
            if setting["kind"] == "arena":
                patch_arena(setting, setting_changes, data)
            patch_setting(
                setting, {k: v for k, v in setting_changes.items() if k != "Asset"}
            )
            if "Asset" in changes:
                selected_file = resolve_stimulus_file(
                    asset_root,
                    changes["Asset"],
                    texture=setting["kind"] == "texture",
                    grating=setting.get("grating", False),
                )
                apply_texture_dimensions(setting, selected_file)
                identity = setting.get(
                    "asset_id", setting.get("pattern", {}).get("asset_id")
                )
                if not isinstance(identity, str):
                    raise ValueError(
                        "This layer does not use a replaceable prepared file"
                    )
                select_epoch_asset(
                    data,
                    path,
                    layer,
                    identity,
                    selected_file.path,
                    selected_file.profile,
                )
        result = validate(data)
    return result


def append_template(
    program: Program, template: Program, after: tuple[int, ...] | None = None
) -> tuple[Program, int]:
    """Import one generated block, remapping identities and preserving reference closure."""
    data = program.model_dump(mode="json")
    incoming = template.model_dump(mode="json")
    definitions: dict[str, str] = {}

    def collect(value: object) -> None:
        if isinstance(value, dict):
            for key in ("asset_id", "instance_id", "scene_id", "epoch_id", "group_id"):
                if isinstance(value.get(key), str) and value[key] not in definitions:
                    definitions[value[key]] = unique_id(
                        [data, [{"epoch_id": v} for v in definitions.values()]],
                        key.removesuffix("_id").title(),
                    )
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(incoming)

    def remap(value: object) -> object:
        if isinstance(value, list):
            return [remap(v) for v in value]
        if isinstance(value, dict):
            return {
                k: (
                    [definitions.get(v, v) for v in item]
                    if k == "layer_instance_ids"
                    else definitions.get(item, item)
                    if isinstance(item, str)
                    and k
                    in (
                        "asset_id",
                        "instance_id",
                        "scene_id",
                        "epoch_id",
                        "group_id",
                        "arena_instance_id",
                    )
                    else remap(item)
                )
                for k, item in value.items()
            }
        return value

    imported = remap(incoming)
    assert isinstance(imported, dict)
    for key in ("assets", "instances", "scenes"):
        data[key].extend(imported[key])
    channels = {c["channel_id"]: c for c in data["input_channels"]}
    for channel in imported["input_channels"]:
        identity = channel["channel_id"]
        if identity in channels and channels[identity] != channel:
            raise ValueError(f"Input {identity} conflicts with the trial definition")
        if identity not in channels:
            data["input_channels"].append(channel)
    index = after[0] + 1 if after else len(data["sequence"])
    data["sequence"][index:index] = imported["sequence"]
    return validate(data), index
