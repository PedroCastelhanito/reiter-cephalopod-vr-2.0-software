"""Materialize paired numeric and media variations into canonical epochs."""

from copy import deepcopy
from dataclasses import dataclass
from math import isfinite
from typing import Any

from cephvr.gui.epoch_batch import patch_setting
from cephvr.gui.feedback_signals import tracking_signals
from cephvr.gui.program_editing import document_ids, unique_id, validate
from cephvr.visual_stimulus.config.models.program_model import Program

END_BEHAVIORS = {
    "loop": "loop",
    "hold": "hold_final_frame",
    "hold final frame": "hold_final_frame",
}


@dataclass(frozen=True)
class ValueRule:
    path: tuple[int, ...]
    layer: int
    parameter: str
    values: tuple[str, ...]


def patch_arena(
    setting: dict[str, Any], changes: dict[str, str], document: dict[str, Any]
) -> None:
    for name, value in changes.items():
        if name not in ("Longitudinal", "Lateral", "Angular"):
            continue
        gain = float(value)
        if not isfinite(gain):
            raise ValueError("Movement gains must be finite")
        operation = (
            "movement_integration"
            if name == "Angular"
            else "heading_relative_planar_integration"
        )
        binding = next(
            (
                b
                for b in setting["feedback"]
                if b["operation"] == operation
                and (name != "Angular" or b.get("target") == "yaw")
            ),
            None,
        )
        if binding is None:
            binding = dict(
                binding_id=unique_id(setting["feedback"], "arena_variation"),
                operation=operation,
                gain=dict(kind="constant", value=0),
            )
            if name == "Angular":
                binding.update(
                    source_channel="turn_drive",
                    target="yaw",
                    offset=dict(kind="constant", value=0),
                )
            else:
                binding.update(
                    forward_channel="forward_drive",
                    sideways_channel="sideways_drive",
                    sideways_gain=dict(kind="constant", value=0),
                )
            setting["feedback"].append(binding)
        key = "sideways_gain" if name == "Lateral" else "gain"
        if binding[key]["kind"] != "constant":
            raise ValueError("Custom movement gains cannot be replaced by a variation")
        binding[key] = dict(kind="constant", value=gain)
        needed = {
            binding.get(k)
            for k in ("source_channel", "forward_channel", "sideways_channel")
        }
        existing = {c["channel_id"]: c for c in document["input_channels"]}
        streams = {existing[key]["stream_id"] for key in needed if key in existing}
        if len(streams) > 1:
            raise ValueError("Arena movement axes must use the same Tracking stream")
        stream = next(iter(streams), "tracking")
        for channel in tracking_signals():
            channel = {**channel, "stream_id": stream}
            identity = channel["channel_id"]
            if identity not in needed:
                continue
            if identity in existing and existing[identity] != channel:
                raise ValueError(
                    f"{identity} conflicts with the Tracking movement channel"
                )
            if identity not in existing:
                document["input_channels"].append(deepcopy(channel))


def materialize_values(
    program: Program, rules: tuple[ValueRule, ...], *, max_variations: int = 512
) -> Program:
    counts = {len(rule.values) for rule in rules}
    if len(counts) != 1 or not counts or 0 in counts:
        raise ValueError("Paired variations require equally long, nonempty value lists")
    count = next(iter(counts))
    if count > max_variations:
        raise ValueError(
            f"The authoring editor supports at most {max_variations} variations"
        )
    keys = [(r.path, r.layer, r.parameter) for r in rules]
    if len(keys) != len(set(keys)):
        raise ValueError("Each parameter may be varied once per batch")
    data = program.model_dump(mode="json")
    source = data["sequence"][0]
    data["sequence"] = []
    taken = document_ids(data)
    for i in range(count):
        epoch = deepcopy(source)
        epoch["epoch_id"] = unique_id(data, "Epoch", taken=taken)
        changes: dict[int, dict[str, str]] = {}
        for rule in rules:
            changes.setdefault(rule.layer, {})[rule.parameter] = rule.values[i]
        for index, patch in changes.items():
            setting = epoch["settings"][index]
            if setting["kind"] == "arena":
                patch_arena(setting, patch, data)
            else:
                numeric = {k: v for k, v in patch.items() if k != "At end"}
                if any(not isfinite(float(v)) for v in numeric.values()):
                    raise ValueError("Provide finite values for every variation")
                patch_setting(setting, numeric)
                if "At end" in patch:
                    setting["end_behavior"] = END_BEHAVIORS[patch["At end"].lower()]
        data["sequence"].append(epoch)
    return validate(data)
