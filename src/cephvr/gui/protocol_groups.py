"""Canonical repeat/condition authoring with bounded, unit-checked variation."""

from copy import deepcopy
from dataclasses import dataclass
from itertools import product
from math import isfinite
from typing import Any

from cephvr.gui.program_editing import (
    NodePath,
    data_node,
    data_nodes,
    unique_id,
    validate,
)
from cephvr.visual_stimulus.config.models.program_model import Program
from cephvr.visual_stimulus.config.parameter_edits import assign_ref as assign_ref
from cephvr.visual_stimulus.config.parameter_edits import (
    motion_numbers as motion_numbers,
)
from cephvr.visual_stimulus.config.parameter_edits import varied_fields as varied_fields


@dataclass(frozen=True)
class Variation:
    path: tuple[int, ...]
    layer: int
    parameter: str
    values: tuple[float, ...]


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
    name: str | None = None,
) -> Program:
    data = program.model_dump(mode="json")
    node = data_node(data, path)
    if node["kind"] != "group":
        raise ValueError("Select a group")
    if node["repetitions"] != repetitions:
        editable_batches = {
            child.get("batch_id")
            for child in node["body"]
            if child.get("subgroup_draft") is not None
        }
        for child in node["body"]:
            if child["kind"] == "epoch":
                if (
                    child.get("repetition_settings")
                    and child.get("batch_id") not in editable_batches
                ):
                    raise ValueError(
                        "Imported repetition settings have no editable variation rules"
                    )
                child["repetition_settings"] = []
    node.update(
        repetitions=repetitions,
        order="shuffle_each_repetition" if shuffle else "as_listed",
        conditions=conditions,
    )
    if name is not None:
        original = node["group_id"]
        identity = name.strip().replace(" ", "_")
        node["group_id"] = identity

        def rename_references(value: object) -> None:
            if isinstance(value, dict):
                if (
                    value.get("kind") == "condition"
                    and value.get("group_id") == original
                ):
                    value["group_id"] = identity
                for child in value.values():
                    rename_references(child)
            elif isinstance(value, list):
                for child in value:
                    rename_references(child)

        rename_references(data)
    result = validate(data)
    from cephvr.gui.subgroup_repetitions import rebuild_repetitions

    return rebuild_repetitions(result, (path,) if isinstance(path, int) else path)
