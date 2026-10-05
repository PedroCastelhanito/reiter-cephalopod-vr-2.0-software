"""Authoring templates expressed only in the accepted V03 program grammar."""

import json
from copy import deepcopy

from cephvr.gui.program_editing import NodePath, data_node, node_at
from cephvr.gui.protocol_document import review_program
from cephvr.visual_stimulus.config.models.program_model import (
    Epoch,
    Program,
    parse_program_json,
)
from cephvr.visual_stimulus.config.models.schema_common import DEFAULT_DOCUMENT_BYTES

FILE_TYPES = ("Texture", "Image", "Looming image", "Video", "3D arena")

PRESETS = (
    "Texture",
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
    program: Program, index: NodePath, preset: str, screens: tuple[str, ...]
) -> Program:
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
    family = "texture"
    profile = None
    path = ""
    if preset in ("Image", "Looming image", "Video"):
        family = "video" if preset == "Video" else "image"
        source = {
            key: value
            for key, value in source.items()
            if key
            in (
                "instance_id",
                "space",
                "initial",
                "width",
                "height",
                "opacity",
                "motion",
                "reset",
                "assignments",
                "feedback",
            )
        }
        source.update(kind=family, asset_id=identity, sampling="linear")
        profile, path = (
            ("mp4_h264_sdr8_v1", "video.mp4")
            if family == "video"
            else ("png_uint_v1", "image.png")
        )
        if family == "video":
            source.update(
                initial_playback={"seconds": "0"}, end_behavior="hold_final_frame"
            )
        if preset == "Looming image":
            curve = {
                "kind": "keyframes",
                "interpolation": "linear",
                "knots": [
                    {"time": {"seconds": "0"}, "value": 1.0},
                    {"time": {"seconds": "10"}, "value": 90.0},
                ],
            }
            source.update(width=curve, height=deepcopy(curve))
    elif preset == "3D arena":
        family, profile, path = "arena", "glb2_static_unlit_v1", "arena.glb"
        source = dict(
            kind="arena",
            instance_id=identity,
            asset_id=identity,
            world_frame_id="rig",
            asset_to_world=[
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
            initial={"position_mm": [0.0, 0.0], "yaw_deg": 0.0},
            fixed_height_mm=0.0,
            fixed_pitch_deg=0.0,
            fixed_roll_deg=0.0,
            motion={key: {"kind": "hold"} for key in ("x", "y", "yaw")},
            reset=False,
            assignments=[],
            feedback=[],
        )
    elif preset == "Checkerboard":
        source["pattern"] = {
            "kind": "checkerboard",
            "frequency_x": {"kind": "constant", "value": 0.05},
            "frequency_y": {"kind": "constant", "value": 0.05},
        }
    elif preset == "Square grating":
        source["pattern"]["kind"] = "square_grating"
    elif preset in ("Image tile", "Texture"):
        profile, path = "png_uint_v1", "texture.png"
        source["pattern"] = {
            "kind": "image_tile",
            "asset_id": identity,
            "period_x": {"kind": "constant", "value": 20.0},
            "period_y": {"kind": "constant", "value": 20.0},
            "sampling": "linear",
        }
    if preset == "Texture":
        source["space"] = {
            "kind": "physical_surface",
            "frame_id": "rig",
            "mappings": [
                {"surface_id": face, "matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]}
                for face in source["space"]["surfaces"]
            ],
        }
        source["phase_x"] = {"kind": "hold"}
        source["phase_y"] = {"kind": "hold"}
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
    identity = epoch["settings"].pop(layer)["instance_id"]
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
    return parse_program_json(json.dumps(data), max_bytes=DEFAULT_DOCUMENT_BYTES)


def add_file_stimulus(
    program: Program,
    index: NodePath,
    preset: str,
    screens: tuple[str, ...],
    root: str,
    path: str,
) -> Program:
    from cephvr.gui.stimulus_files import resolve_stimulus_file

    selected = resolve_stimulus_file(root, path, texture=preset == "Texture")
    candidate = add_stimulus(program, index, preset, screens).model_dump(mode="json")
    target = data_node(candidate, index)["settings"][-1]
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
