"""Canonical epoch operations, including nested group bodies."""

from copy import deepcopy
from typing import Any

from cephvr.gui.program_editing import (
    NodePath,
    data_node,
    data_nodes,
    node_at,
    path_tuple,
    unique_id,
    validate,
)
from cephvr.gui.protocol_document import blank_program
from cephvr.visual_stimulus.config.models.program_model import Epoch, Fixed, Program


def edit_epoch(
    program: Program, index: NodePath, operation: str
) -> tuple[Program, int]:
    data = program.model_dump(mode="json")
    path = path_tuple(index)
    position = path[-1]
    sequence = data_nodes(data, path[:-1])
    if operation in ("add", "duplicate"):
        if operation == "add":
            source = blank_program().model_dump(mode="json")
            node = source["sequence"][0]
            scene = source["scenes"][0]
            scene["scene_id"] = unique_id(data, "blank")
            node["scene_id"] = scene["scene_id"]
            node["epoch_id"] = unique_id(data, "Epoch")
            data["scenes"].append(scene)
        else:
            node = deepcopy(sequence[position])
            # Remap local group references as well as node identities in copied trees.
            mapping: dict[str, str] = {}

            def rename(value: dict[str, Any]) -> None:
                key = "epoch_id" if value["kind"] == "epoch" else "group_id"
                new = unique_id(
                    [data, [{"epoch_id": v} for v in mapping.values()]], "Copy"
                )
                while new in mapping.values():
                    new += "_copy"
                mapping[value[key]] = new
                value[key] = new
                for child in value.get("body", []):
                    rename(child)

            rename(node)

            def references(value: object) -> None:
                if isinstance(value, dict):
                    if (
                        value.get("kind") == "condition"
                        and value["group_id"] in mapping
                    ):
                        value["group_id"] = mapping[value["group_id"]]
                    for child in value.values():
                        references(child)
                elif isinstance(value, list):
                    for child in value:
                        references(child)

            references(node)
        position += 1
        sequence.insert(position, node)
    elif operation == "remove":
        if len(sequence) == 1:
            raise ValueError("A trial or group must contain at least one epoch")
        sequence.pop(position)
        position = min(position, len(sequence) - 1)
    elif operation in ("earlier", "later"):
        other = position + (-1 if operation == "earlier" else 1)
        if not 0 <= other < len(sequence):
            return program, position
        sequence[position], sequence[other] = sequence[other], sequence[position]
        position = other
    else:
        raise ValueError("Unknown epoch action")
    return validate(data), position


def edit_epoch_metadata(
    program: Program, path: NodePath, name: str, duration: str
) -> Program:
    node = node_at(program, path)
    if not isinstance(node, Epoch):
        return program
    data = program.model_dump(mode="json")
    target = data_node(data, path)
    target["epoch_id"] = name.strip().replace(" ", "_")
    if isinstance(node.duration, Fixed):
        target["duration"]["duration"]["seconds"] = duration.strip()
    return validate(data)
