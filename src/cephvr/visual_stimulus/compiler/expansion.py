"""Bounded V08 ordering and condition expansion for immutable plan occurrences."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from cephvr.visual_stimulus.config.models.artifact_models import GroupVisit
from cephvr.visual_stimulus.config.models.program_model import (
    Epoch,
    Group,
    Node,
    Program,
    Ref,
    Settings,
)

ORDER_IMPLEMENTATION = "cephvr-order-python-v1"


@dataclass(frozen=True)
class ExpandedEpoch:
    """One ordered source epoch with fully substituted immutable settings."""

    source: Epoch
    settings: tuple[Settings, ...]
    lineage: tuple[GroupVisit, ...]


def _count(nodes: tuple[Node, ...], limit: int) -> int:
    total = 0
    for node in nodes:
        if isinstance(node, Epoch):
            amount = 1
        else:
            child_count = _count(node.body, limit)
            multiplier = len(node.conditions.rows) if node.conditions is not None else 1
            amount = node.repetitions * multiplier * child_count
        total += amount
        if total > limit:
            raise ValueError(f"expanded program exceeds max_expanded_epochs ({limit})")
    return total


def _ordering_rng(seed: str, path: tuple[str, ...]) -> random.Random:
    encoded = f"cephvr.order.v1:{seed}:{'/'.join(path)}".encode()
    return random.Random(int.from_bytes(hashlib.sha256(encoded).digest(), "big"))


def _substitute(value: Any, scope: dict[str, dict[str, object]]) -> Any:
    if isinstance(value, Ref):
        try:
            return scope[value.group_id][value.column_id]
        except KeyError as exc:
            raise ValueError(
                f"unresolved condition reference {value.group_id}.{value.column_id}"
            ) from exc
    if isinstance(value, BaseModel):
        payload = {
            key: _substitute(getattr(value, key), scope)
            for key in type(value).model_fields
        }
        return type(value).model_validate(payload, strict=True)
    if isinstance(value, tuple):
        return tuple(_substitute(item, scope) for item in value)
    if isinstance(value, list):
        return [_substitute(item, scope) for item in value]
    if isinstance(value, dict):
        return {key: _substitute(item, scope) for key, item in value.items()}
    return value


def _row_values(group: Group, row_id: str) -> dict[str, object]:
    if group.conditions is None:
        return {}
    row = next((item for item in group.conditions.rows if item.row_id == row_id), None)
    if row is None:
        raise ValueError(f"unknown condition row {row_id}")
    return {cell.column_id: cell.value for cell in row.cells}


def expand_program(
    program: Program, *, seed_decimal: str, max_expanded_epochs: int
) -> tuple[ExpandedEpoch, ...]:
    """Expand group visits after checking multiplicative size bounds."""
    if type(max_expanded_epochs) is not int or max_expanded_epochs <= 0:
        raise ValueError("max_expanded_epochs must be positive")
    count = _count(program.sequence, max_expanded_epochs)
    expanded: list[ExpandedEpoch] = []

    def visit(
        nodes: tuple[Node, ...],
        scope: dict[str, dict[str, object]],
        lineage: tuple[GroupVisit, ...],
        path: tuple[str, ...],
    ) -> None:
        for node in nodes:
            if isinstance(node, Epoch):
                settings = tuple(_substitute(block, scope) for block in node.settings)
                expanded.append(ExpandedEpoch(node, settings, lineage))
                continue
            if node.order_unit == "condition_rows":
                if node.conditions is None:
                    raise ValueError("condition row group requires a table")
                authored_units = [row.row_id for row in node.conditions.rows]
            else:
                authored_units = [
                    child.epoch_id if isinstance(child, Epoch) else child.group_id
                    for child in node.body
                ]
            rng = _ordering_rng(seed_decimal, path + (node.group_id,))
            visit_index = 0
            for repetition in range(node.repetitions):
                units = list(authored_units)
                if node.order == "shuffle_each_repetition":
                    for position in range(len(units) - 1, 0, -1):
                        swap = rng.randrange(position + 1)
                        units[position], units[swap] = units[swap], units[position]
                for unit_id in units:
                    visit_record = GroupVisit(
                        group_id=node.group_id,
                        repetition_index=repetition,
                        unit_id=unit_id,
                        visit_index=visit_index,
                    )
                    visit_index += 1
                    child_scope = dict(scope)
                    next_path = path + (f"{node.group_id}[{repetition}]:{unit_id}",)
                    if node.order_unit == "condition_rows":
                        child_scope[node.group_id] = _row_values(node, unit_id)
                        visit(
                            node.body, child_scope, lineage + (visit_record,), next_path
                        )
                    else:
                        child = next(
                            item
                            for item in node.body
                            if (
                                item.epoch_id
                                if isinstance(item, Epoch)
                                else item.group_id
                            )
                            == unit_id
                        )
                        visit(
                            (child,), child_scope, lineage + (visit_record,), next_path
                        )

    visit(program.sequence, {}, (), ())
    if len(expanded) != count:
        raise RuntimeError(
            "bounded expansion count disagrees with materialized occurrences"
        )
    return tuple(expanded)
