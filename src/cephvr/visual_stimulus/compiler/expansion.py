"""Bounded V08 ordering and condition expansion for immutable plan occurrences."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import islice
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
    SparseNoiseSettings,
)
from cephvr.visual_stimulus.config.repetition_values import resolve_repetition

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
        if type(value).model_config.get("frozen") and all(
            payload[key] is getattr(value, key) for key in payload
        ):
            return value
        return type(value).model_validate(payload, strict=True)
    if isinstance(value, tuple):
        items = tuple(_substitute(item, scope) for item in value)
        return (
            value if all(a is b for a, b in zip(items, value, strict=True)) else items
        )
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
    return tuple(
        iter_expanded_program(
            program, seed_decimal=seed_decimal, max_expanded_epochs=max_expanded_epochs
        )
    )


def iter_expanded_program(
    program: Program,
    *,
    seed_decimal: str,
    max_expanded_epochs: int,
    source_only: bool = False,
) -> Iterator[ExpandedEpoch]:
    """Stream bounded visits; source_only omits settings for duration planning."""
    if type(max_expanded_epochs) is not int or max_expanded_epochs <= 0:
        raise ValueError("max_expanded_epochs must be positive")
    count = _count(program.sequence, max_expanded_epochs)
    observed = 0
    for item in _iter_program(
        program, seed_decimal=seed_decimal, source_only=source_only
    ):
        observed += 1
        yield item
    if observed != count:
        raise RuntimeError(
            "bounded expansion count disagrees with materialized occurrences"
        )


def expand_program_prefix(
    program: Program, *, seed_decimal: str, max_expanded_epochs: int
) -> tuple[ExpandedEpoch, ...]:
    """Materialize only a canonical prefix for read-only planning previews."""
    if type(max_expanded_epochs) is not int or max_expanded_epochs <= 0:
        raise ValueError("max_expanded_epochs must be positive")
    return tuple(
        islice(_iter_program(program, seed_decimal=seed_decimal), max_expanded_epochs)
    )


def _iter_program(
    program: Program, *, seed_decimal: str, source_only: bool = False
) -> Iterator[ExpandedEpoch]:
    sparse_visits: dict[tuple[str, str], int] = {}

    def visit(
        nodes: tuple[Node, ...],
        scope: dict[str, dict[str, object]],
        lineage: tuple[GroupVisit, ...],
        path: tuple[str, ...],
    ) -> Iterator[ExpandedEpoch]:
        for node in nodes:
            if isinstance(node, Epoch):
                if source_only:
                    yield ExpandedEpoch(node, (), lineage)
                    continue
                source_settings = (
                    node.repetition_settings[lineage[-1].repetition_index]
                    if node.repetition_settings
                    else node.settings
                )
                settings = tuple(_substitute(block, scope) for block in source_settings)
                if node.repetition_rules:
                    settings = resolve_repetition(
                        settings, node.repetition_rules, lineage[-1].repetition_index
                    )
                resolved = []
                for block in settings:
                    if (
                        isinstance(block, SparseNoiseSettings)
                        and block.pattern_duration is None
                    ):
                        key = (node.epoch_id, block.instance_id)
                        ordinal = sparse_visits.get(key, 0)
                        sparse_visits[key] = ordinal + 1
                        block = block.model_copy(
                            update={
                                "appearance": block.appearance.model_copy(
                                    update={
                                        "seed": (block.appearance.seed + ordinal)
                                        % (1 << 64)
                                    }
                                )
                            }
                        )
                    resolved.append(block)
                settings = tuple(resolved)
                yield ExpandedEpoch(node, settings, lineage)
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
                        yield from visit(
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
                        yield from visit(
                            (child,), child_scope, lineage + (visit_record,), next_path
                        )

    yield from visit(program.sequence, {}, (), ())
