"""Canonical repeat/condition authoring with bounded, unit-checked variation."""

from copy import deepcopy
from dataclasses import dataclass
from itertools import product
from math import atan2, cos, degrees, hypot, isfinite, radians, sin
from typing import Any

from cephvr.gui.epoch_motion import constant_rate
from cephvr.gui.program_editing import (
    NodePath,
    data_node,
    data_nodes,
    unique_id,
    validate,
)
from cephvr.visual_stimulus.config.models.program_model import Program


@dataclass(frozen=True)
class Variation:
    path: tuple[int, ...]
    layer: int
    parameter: str
    values: tuple[float, ...]


def motion_numbers(setting: dict[str, Any]) -> tuple[float, float, float]:
    texture = setting["kind"] == "texture"
    if texture:
        pattern = setting["pattern"]
        if pattern["kind"] != "image_tile" or any(
            pattern[k]["kind"] != "constant"
            or not isinstance(pattern[k]["value"], (int, float))
            for k in ("period_x", "period_y")
        ):
            raise ValueError(
                "Speed/direction variations need an image tile with constant dimensions"
            )
        if any(setting["motion"][k]["kind"] != "hold" for k in ("x", "y")):
            raise ValueError(
                "Speed variations cannot replace simultaneous texture translation"
            )
        x, y = [constant_rate(setting[f"phase_{axis}"]) for axis in ("x", "y")]
        if x is not None and y is not None:
            x, y = -x * pattern["period_x"]["value"], -y * pattern["period_y"]["value"]
    else:
        x, y = [constant_rate(setting["motion"][axis]) for axis in ("x", "y")]
    angular = constant_rate(
        setting["motion"]["yaw" if setting["kind"] == "arena" else "rotation"]
    )
    if x is None or y is None or angular is None:
        raise ValueError("Choose constant motion before varying speed/direction")
    return hypot(x, y), degrees(atan2(y, x)) if x or y else 0.0, angular


def varied_fields(
    setting: dict[str, Any], values: dict[str, float]
) -> dict[tuple[str, ...], tuple[float, str]]:
    result: dict[tuple[str, ...], tuple[float, str]] = {}
    length = (
        "mm"
        if setting["kind"] == "arena" or setting["space"]["kind"] == "physical_surface"
        else "deg"
    )
    if any(key in values for key in ("Speed", "Direction", "Angular speed")):
        speed, angle, angular = motion_numbers(setting)
        speed, angle, angular = (
            values.get("Speed", speed),
            values.get("Direction", angle),
            values.get("Angular speed", angular),
        )
        if speed < 0:
            raise ValueError("Speed must be nonnegative")
        if "Speed" in values or "Direction" in values:
            x, y = speed * cos(radians(angle)), speed * sin(radians(angle))
            for axis, value in (("x", x), ("y", y)):
                if setting["kind"] == "texture":
                    result[(f"phase_{axis}", "function", "value")] = (
                        -value / setting["pattern"][f"period_{axis}"]["value"],
                        "cycle/s",
                    )
                else:
                    result[("motion", axis, "function", "value")] = (
                        value,
                        f"{length}/s",
                    )
        if "Angular speed" in values:
            result[
                (
                    "motion",
                    "yaw" if setting["kind"] == "arena" else "rotation",
                    "function",
                    "value",
                )
            ] = (angular, "deg/s")
    for name, key in (("Width", "width"), ("Height", "height"), ("Opacity", "opacity")):
        if name in values:
            if key not in setting:
                raise ValueError(f"{name} is not available for this stimulus")
            result[(key, "value")] = (values[name], "1" if key == "opacity" else length)
    return result


def assign_ref(
    setting: dict[str, Any], path: tuple[str, ...], ref: dict[str, str] | float
) -> None:
    if path[0] == "motion":
        setting["motion"][path[1]] = {
            "kind": "rate",
            "function": {"kind": "constant", "value": ref},
        }
    elif path[0].startswith("phase_"):
        setting[path[0]] = {
            "kind": "rate",
            "function": {"kind": "constant", "value": ref},
        }
    else:
        setting[path[0]] = {"kind": "constant", "value": ref}


def make_group(
    program: Program,
    scope: tuple[int, ...],
    first: int,
    last: int,
    repetitions: int,
    shuffle: bool,
    rules: tuple[Variation, ...] = (),
    combinations: bool = False,
) -> tuple[Program, int]:
    data = program.model_dump(mode="json")
    sequence = data_nodes(data, scope)
    if not 0 <= first <= last < len(sequence):
        raise ValueError("Select a valid consecutive range")
    identity = unique_id(data, "Group")
    group: dict[str, Any] = dict(
        kind="group",
        group_id=identity,
        repetitions=repetitions,
        order="shuffle_each_repetition" if shuffle else "as_listed",
        order_unit="condition_rows" if rules else "child_blocks",
        conditions=None,
        body=deepcopy(sequence[first : last + 1]),
    )
    if rules:
        keys = [(r.path, r.layer, r.parameter) for r in rules]
        if len(keys) != len(set(keys)):
            raise ValueError("Each parameter may be varied once per group")
        if any(not r.values or any(not isfinite(v) for v in r.values) for r in rules):
            raise ValueError(
                "Provide finite comma-separated values for every variation"
            )
        if not combinations and len({len(r.values) for r in rules}) != 1:
            raise ValueError("Paired variations require equally long value lists")
        count = 1
        for r in rules:
            if r.path[: len(scope)] != scope or not first <= r.path[len(scope)] <= last:
                raise ValueError("Variation target must be inside the selected range")
            count = count * len(r.values) if combinations else len(r.values)
        if count > 512:
            raise ValueError(
                "The authoring editor supports at most 512 condition rows per operation"
            )
        rows = (
            list(product(*(r.values for r in rules)))
            if combinations
            else list(zip(*(r.values for r in rules), strict=True))
        )
        targets: dict[tuple[tuple[int, ...], int], list[int]] = {}
        for index, rule in enumerate(rules):
            relative = (rule.path[len(scope)] - first, *rule.path[len(scope) + 1 :])
            targets.setdefault((relative, rule.layer), []).append(index)
        columns = []
        cells: list[list[dict[str, Any]]] = [[] for _ in rows]
        container = {"sequence": group["body"]}
        for target_number, ((path, layer), indices) in enumerate(targets.items()):
            setting = data_node(container, path)["settings"][layer]
            source = deepcopy(setting)
            for row_number, values in enumerate(rows):
                fields = varied_fields(
                    source, {rules[i].parameter: values[i] for i in indices}
                )
                for field_path, (value, unit) in fields.items():
                    column = f"layer{target_number + 1}_{'_'.join(field_path[:-1])}"
                    if row_number == 0:
                        columns.append(
                            dict(column_id=column, value_type="number", unit=unit)
                        )
                        assign_ref(
                            setting,
                            field_path,
                            dict(kind="condition", group_id=identity, column_id=column),
                        )
                    cells[row_number].append(dict(column_id=column, value=float(value)))
        group["conditions"] = dict(
            columns=columns,
            rows=[
                dict(row_id=f"Condition_{i + 1}", cells=row)
                for i, row in enumerate(cells)
            ],
        )
    sequence[first : last + 1] = [group]
    return validate(data), first


def update_group(
    program: Program,
    path: NodePath,
    repetitions: int,
    shuffle: bool,
    conditions: object,
) -> Program:
    data = program.model_dump(mode="json")
    node = data_node(data, path)
    if node["kind"] != "group":
        raise ValueError("Select a group")
    node.update(
        repetitions=repetitions,
        order="shuffle_each_repetition" if shuffle else "as_listed",
        conditions=conditions,
    )
    return validate(data)
