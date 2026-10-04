"""Canonical reference transformations; incomplete asset choices remain GUI state."""

from cephvr.gui.program_editing import validate
from cephvr.gui.stimulus_presets import add_stimulus, remove_stimulus
from cephvr.visual_stimulus.config.models.program_model import Epoch, Program


def replace_reference(
    program: Program, layer: int, kind: str, face: str
) -> tuple[Program, int]:
    epoch = program.sequence[0]
    assert isinstance(epoch, Epoch)
    order = next(
        s.layer_instance_ids for s in program.scenes if s.scene_id == epoch.scene_id
    )
    old_id = epoch.settings[layer].instance_id if layer >= 0 else ""
    position = order.index(old_id) if old_id in order else len(order)
    if layer >= 0:
        program = remove_stimulus(program, 0, layer)
    if kind == "None":
        return program, -1
    program = add_stimulus(program, 0, kind, (face,) if face else ())
    data = program.model_dump(mode="json")
    node = data["sequence"][0]
    selected = len(node["settings"]) - 1
    if kind != "3D arena":
        scene = next(s for s in data["scenes"] if s["scene_id"] == node["scene_id"])
        identity = node["settings"][selected]["instance_id"]
        scene["layer_instance_ids"].remove(identity)
        scene["layer_instance_ids"].insert(position, identity)
    return validate(data), selected


def reference_mode(program: Program, arena: bool) -> Program:
    data = program.model_dump(mode="json")
    node = data["sequence"][0]
    node["settings"] = [s for s in node["settings"] if (s["kind"] == "arena") == arena]
    scene = next(s for s in data["scenes"] if s["scene_id"] == node["scene_id"])
    if arena:
        scene["layer_instance_ids"] = []
    else:
        scene["arena_instance_id"] = None
    identities = {s["instance_id"] for s in node["settings"]}
    asset_ids = {
        s.get("asset_id", s.get("pattern", {}).get("asset_id"))
        for s in node["settings"]
    }
    data["instances"] = [i for i in data["instances"] if i["instance_id"] in identities]
    data["assets"] = [a for a in data["assets"] if a["asset_id"] in asset_ids]
    data["scenes"] = [scene]
    return validate(data)
