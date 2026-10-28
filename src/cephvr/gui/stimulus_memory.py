"""Shared per-type parameter defaults, retained by the normal GUI snapshot."""

import json
from copy import deepcopy
from typing import Any

from pydantic import TypeAdapter

from cephvr.gui.configuration_files import fields
from cephvr.gui.epoch_batch import family
from cephvr.gui.program_editing import validate
from cephvr.gui.stimulus_fades import retime_epoch_settings
from cephvr.gui.stimulus_scope import set_surfaces
from cephvr.visual_stimulus.config.models.program_model import Program, Settings

SETTING: TypeAdapter[Settings] = TypeAdapter(Settings)
CONTEXT_FIELDS = {
    "instance_id",
    "asset_id",
    "feedback",
    "linked_to",
    "pattern_count",
    "pattern_duration",
}


def has_condition(value: Any) -> bool:
    if isinstance(value, dict):
        return value.get("kind") == "condition" or any(
            has_condition(item) for item in value.values()
        )
    return isinstance(value, list) and any(has_condition(item) for item in value)


class StimulusMemory:
    def __init__(self) -> None:
        self.entries: dict[str, dict[str, Any]] = {}

    def remember(
        self, setting: Settings, duration_ns: int, *, overwrite: bool = True
    ) -> None:
        kind = family(setting)
        if not overwrite and kind in self.entries:
            return
        self.entries[kind] = {
            "setting": setting.model_dump(mode="json"),
            "duration_ns": duration_ns,
        }

    @staticmethod
    def validate(value: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(value, dict):
            raise ValueError("Stimulus defaults must be an object")
        for kind, raw in value.items():
            entry = fields(raw, {"setting", "duration_ns"}, "Stimulus defaults")
            setting = SETTING.validate_json(json.dumps(entry["setting"]))
            if kind != family(setting):
                raise ValueError("Remembered stimulus parameters have the wrong type")
            duration = entry["duration_ns"]
            if type(duration) is not int or not 0 < duration < (1 << 63):
                raise ValueError("Remembered epoch duration must be positive int64")
        return deepcopy(value)

    def apply(
        self, program: Program, index: int, kind: str, face: str, duration_ns: int
    ) -> Program:
        if index < 0 or kind not in self.entries:
            return program
        entry = self.entries[kind]
        data = program.model_dump(mode="json")
        setting = data["sequence"][0]["settings"][index]
        for key, value in entry["setting"].items():
            if key in CONTEXT_FIELDS or key not in setting or has_condition(value):
                continue
            if key == "pattern":
                if value["kind"] != setting[key]["kind"]:
                    continue
                value = deepcopy(value)
                if "asset_id" in value:
                    value["asset_id"] = setting[key]["asset_id"]
            setting[key] = deepcopy(value)
        if face:
            set_surfaces(setting, [face.lower()])
        retime_epoch_settings([setting], entry["duration_ns"], duration_ns)
        return validate(data)
