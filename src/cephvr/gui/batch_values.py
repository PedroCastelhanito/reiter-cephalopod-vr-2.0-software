"""Materialize paired numeric and media variations into canonical epochs."""

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import isfinite

from cephvr.gui.arena_movement import patch_arena
from cephvr.gui.epoch_batch import END_BEHAVIORS, patch_setting
from cephvr.gui.program_editing import document_ids, unique_id, validate
from cephvr.visual_stimulus.config.models.program_model import Program


@dataclass(frozen=True)
class ValueRule:
    path: tuple[int, ...]
    layer: int
    parameter: str
    values: tuple[str, ...]
    rig_coordinates: bool = True
    rig_angle_version: int = 2


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
                frames = {
                    (r.rig_coordinates, r.rig_angle_version if r.rig_coordinates else 1)
                    for r in rules
                    if r.layer == index
                    and r.parameter in ("Speed", "Direction", "Orientation")
                }
                if len(frames) > 1:
                    raise ValueError(
                        "Speed and direction variations must use the same coordinates"
                    )
                rig_coordinates, angle_version = next(iter(frames), (True, 2))
                patch_setting(
                    setting,
                    numeric,
                    rig_coordinates=rig_coordinates,
                    rig_angle_version=angle_version,
                )
                if "At end" in patch:
                    setting["end_behavior"] = END_BEHAVIORS[patch["At end"].lower()]
        data["sequence"].append(epoch)
    return validate(data)


def listed_values(method: int, text: str, parameter: str) -> tuple[str, ...]:
    """Parse bounded legacy list/sweep inputs independently of their widget."""
    if method == 0:
        values = tuple(v.strip() for v in text.split(","))
        if parameter == "At end":
            if any(v.lower() not in END_BEHAVIORS for v in values):
                raise ValueError("At end values must be loop or hold final frame")
        else:
            for value in values:
                float(value)
        return values
    try:
        start, stop, step = (Decimal(part.strip()) for part in text.split(","))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("Sweep needs min, max, step") from error
    if not all(v.is_finite() for v in (start, stop, step)) or step <= 0 or stop < start:
        raise ValueError("Sweep needs finite min ≤ max and positive step")
    count = int((stop - start) // step) + 1
    if count > 512:
        raise ValueError("Sweep exceeds 512 values")
    return tuple(str(start + i * step) for i in range(count))
