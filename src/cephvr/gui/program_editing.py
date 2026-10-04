"""Tree addressing and atomic canonical edits shared by planner components."""

import json
from copy import deepcopy
from typing import Any, cast

from cephvr.visual_stimulus.config.models.program_model import (
    Group,
    Node,
    Program,
    parse_program_json,
)

NodePath = int | tuple[int, ...]


def path_tuple(path: NodePath) -> tuple[int, ...]:
    return (path,) if isinstance(path, int) else path


def nodes_at(program: Program, scope: tuple[int, ...] = ()) -> tuple[Node, ...]:
    nodes = program.sequence
    for index in scope:
        node = nodes[index]
        if not isinstance(node, Group):
            raise ValueError("Only groups contain epochs")
        nodes = node.body
    return nodes


def node_at(program: Program, path: NodePath) -> Node:
    indexes = path_tuple(path)
    return nodes_at(program, indexes[:-1])[indexes[-1]]


def data_nodes(
    data: dict[str, Any], scope: tuple[int, ...] = ()
) -> list[dict[str, Any]]:
    nodes = data["sequence"]
    for index in scope:
        nodes = nodes[index]["body"]
    return cast(list[dict[str, Any]], nodes)


def data_node(data: dict[str, Any], path: NodePath) -> dict[str, Any]:
    indexes = path_tuple(path)
    return data_nodes(data, indexes[:-1])[indexes[-1]]


def validate(data: dict[str, Any]) -> Program:
    return parse_program_json(json.dumps(data, allow_nan=False), max_bytes=1_048_576)


def unique_id(data: object, prefix: str) -> str:
    taken: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key.endswith("_id") and isinstance(item, str):
                    taken.add(item)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(data)
    index = 1
    while f"{prefix}_{index}" in taken:
        index += 1
    return f"{prefix}_{index}"


def private_scene(data: dict[str, Any], epoch: dict[str, Any]) -> dict[str, Any]:
    """Copy-on-write composition; instance state identity remains explicit."""
    scene = deepcopy(
        next(s for s in data["scenes"] if s["scene_id"] == epoch["scene_id"])
    )
    scene["scene_id"] = unique_id(data, "scene")
    data["scenes"].append(scene)
    epoch["scene_id"] = scene["scene_id"]
    return cast(dict[str, Any], scene)
