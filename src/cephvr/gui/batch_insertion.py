"""Atomic placement of a generated batch within the current trial."""

from dataclasses import dataclass

from cephvr.gui.epoch_batch import append_template, epoch_paths
from cephvr.gui.program_editing import data_node, node_at, validate
from cephvr.visual_stimulus.compiler.expansion import expand_program
from cephvr.visual_stimulus.config.models.program_model import Epoch, Program


@dataclass(frozen=True)
class Insertion:
    mode: str = "append"
    stride: int = 1
    label: str = ""


def insert_batch(
    program: Program, template: Program, selected: tuple[int, ...], placement: Insertion
) -> tuple[Program, tuple[tuple[int, ...], ...]]:
    if placement.mode == "label":
        return insert_after_label(program, template, placement.label)
    if placement.mode == "replace":
        candidate = validate(template.model_dump(mode="json"))
        return candidate, epoch_paths(candidate)
    merged, start = append_template(program, template)
    old, incoming = list(merged.sequence[:start]), list(merged.sequence[start:])
    indices: list[int] = []
    if placement.mode == "stride":
        if not 1 <= placement.stride <= 2000:
            raise ValueError("Use an insertion interval between 1 and 2000 blocks")
        result = []
        for i, node in enumerate(old, 1):
            result.append(node)
            if i % placement.stride == 0 and incoming:
                indices.append(len(result))
                result.append(incoming.pop(0))
        indices.extend(range(len(result), len(result) + len(incoming)))
        result.extend(incoming)
    else:
        if placement.mode in ("before", "after") and not selected:
            raise ValueError("Select a timeline epoch for this insertion position")
        positions = {
            "append": len(old),
            "start": 0,
            "before": selected[0] if selected else 0,
            "after": selected[0] + 1 if selected else 0,
        }
        if placement.mode not in positions:
            raise ValueError("Unknown insertion mode")
        at = positions[placement.mode]
        indices = list(range(at, at + len(incoming)))
        result = old[:at] + incoming + old[at:]
    data = merged.model_dump(mode="json")
    data["sequence"] = [node.model_dump(mode="json") for node in result]
    candidate = validate(data)
    return candidate, tuple(p for p in epoch_paths(candidate) if p[0] in indices)


def insert_after_label(
    program: Program, template: Program, label: str
) -> tuple[Program, tuple[tuple[int, ...], ...]]:
    """Insert a fresh batch after each original matching source, retaining group scope."""
    matches = []
    for path in epoch_paths(program):
        epoch = node_at(program, path)
        assert isinstance(epoch, Epoch)
        if label and epoch.batch_label == label:
            matches.append(path)
    if not matches:
        raise ValueError("Choose a label that exists in the current trial")
    size = len(expand_program(template, seed_decimal="0", max_expanded_epochs=2000))
    if size * len(matches) > 2000:
        raise ValueError("Label insertion exceeds 2000 generated epochs")
    result = program
    inserted: set[str] = set()
    # Work backwards so inserting siblings cannot invalidate an earlier source path.
    for path in reversed(matches):
        merged, start = append_template(result, template)
        for new_path in epoch_paths(merged):
            if new_path[0] >= start:
                epoch = node_at(merged, new_path)
                assert isinstance(epoch, Epoch)
                inserted.add(epoch.epoch_id)
        data = merged.model_dump(mode="json")
        incoming = data["sequence"][start:]
        del data["sequence"][start:]
        siblings = (
            data_node(data, path[:-1])["body"] if len(path) > 1 else data["sequence"]
        )
        siblings[path[-1] + 1 : path[-1] + 1] = incoming
        result = validate(data)
    expand_program(result, seed_decimal="0", max_expanded_epochs=2000)
    selected = []
    for path in epoch_paths(result):
        epoch = node_at(result, path)
        assert isinstance(epoch, Epoch)
        if epoch.epoch_id in inserted:
            selected.append(path)
    return result, tuple(selected)
