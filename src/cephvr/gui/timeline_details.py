"""Read-only epoch summaries and content colors for the trial overview."""

import hashlib
import json
from typing import Any

from PyQt6.QtGui import QColor

from cephvr.gui.epoch_batch import parameter_value
from cephvr.gui.projector_layers import layer_title, layers_for
from cephvr.gui.protocol_document import duration
from cephvr.visual_stimulus.config.models.program_model import Epoch, Program, Settings


def stimulus_key(program: Program, epoch: Epoch) -> str:
    """Compare ordered settings/background without epoch, scene or instance names."""
    scene = next(s for s in program.scenes if s.scene_id == epoch.scene_id)
    assets = {
        a.asset_id: a.model_dump(mode="json", exclude={"asset_id"})
        for a in program.assets
    }

    def normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: assets.get(item, item)
                if key == "asset_id" and isinstance(item, str)
                else normalize(item)
                for key, item in value.items()
                if key != "instance_id"
            }
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    content = [
        scene.background_linear_rgb,
        [
            normalize(epoch.settings[i].model_dump(mode="json"))
            for i in layers_for(program, epoch, "")
        ],
    ]
    return json.dumps(content, sort_keys=True, separators=(",", ":"))


def stimulus_color(key: str) -> QColor:
    hue = int.from_bytes(hashlib.sha256(key.encode()).digest()[:2], "big") % 360
    return QColor.fromHsv(hue, 115, 145)


def epoch_heading(epoch: Epoch, index: int) -> str:
    seconds = duration(epoch)
    timing = f"{seconds:g} s" if seconds is not None else "Variable duration"
    return f"{index + 1} · {epoch.epoch_id.replace('_', ' ')} · {timing}"


def layer_description(program: Program, setting: Settings) -> str:
    data = setting.model_dump(mode="json")
    parts = [layer_title(program, setting)]
    length = (
        "mm"
        if setting.kind == "arena" or data["space"]["kind"] == "physical_surface"
        else "°"
    )
    try:
        if setting.kind == "image" and data["width"]["kind"] == "keyframes":
            start = parameter_value(data, "Start size")
            end = parameter_value(data, "End size")
            seconds = parameter_value(data, "Growth duration")
            parts.append(f"{start} → {end} {length} in {seconds} s")
        else:
            speed = parameter_value(data, "Speed")
            direction = parameter_value(data, "Direction")
            parts.append(f"{speed:g} {length}/s · {direction:g}°")
    except ValueError:
        if setting.kind == "texture" and data["pattern"]["kind"] != "image_tile":
            parts.append(data["pattern"]["kind"].replace("_", " "))
        else:
            parts.append("Custom motion / size")
    if setting.kind == "video":
        parts.append(f"Start {setting.initial_playback.seconds} s")
    return " · ".join(parts)
