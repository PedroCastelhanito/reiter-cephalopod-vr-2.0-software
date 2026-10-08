"""Declared feedback inputs and compatible targets, using the canonical unit rules."""

from typing import Any

from cephvr.tracking.config.pipeline import CHANNELS
from cephvr.visual_stimulus.config.models.parameter_catalogue import (
    DIRECT_GAIN_UNITS,
    MOVEMENT_GAIN_UNITS,
    parameter_units,
)
from cephvr.visual_stimulus.config.models.program_model import Settings

NAMES = {
    "forward_drive": "Longitudinal velocity",
    "sideways_drive": "Lateral velocity",
    "turn_drive": "Angular velocity",
}
TARGETS = {
    "x": "Position X",
    "y": "Position Y",
    "rotation": "Rotation",
    "yaw": "Heading",
    "phase_x": "Texture phase X",
    "phase_y": "Texture phase Y",
    "opacity": "Opacity",
    "width": "Width",
    "height": "Height",
    "contrast": "Contrast",
    "frequency": "Frequency",
    "frequency_x": "Frequency X",
    "frequency_y": "Frequency Y",
    "period_x": "Tile width",
    "period_y": "Tile height",
}


def tracking_signals() -> list[dict[str, Any]]:
    return [
        {
            "channel_id": c.channel_id,
            "stream_id": "tracking",
            "value_kind": c.quantity,
            "unit": c.unit,
            "frame_id": c.coordinate_frame,
        }
        for c in CHANNELS
    ]


def targets(setting: Settings, signal: dict[str, Any]) -> dict[str, str]:
    units = parameter_units(setting)
    if signal["frame_id"] == "anatomical_body":
        return (
            {"yaw": "Heading"}
            if setting.kind == "arena"
            and signal["value_kind"] == "interval_average_rate"
            and signal["unit"] == "deg/s"
            else {}
        )
    state = {"x", "y", "yaw"} if setting.kind == "arena" else {"x", "y", "rotation"}
    if setting.kind == "texture":
        state.update(("phase_x", "phase_y"))
    return {
        key: TARGETS.get(key, key)
        for key, unit in units.items()
        if (
            signal["value_kind"] == "absolute"
            and (signal["unit"], unit) in DIRECT_GAIN_UNITS
        )
        or (
            key in state
            and (signal["value_kind"], signal["unit"], unit) in MOVEMENT_GAIN_UNITS
        )
    }
