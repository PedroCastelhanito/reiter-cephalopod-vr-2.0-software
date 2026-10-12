"""Flat GUI group creation and persistent generated-batch identity."""

from uuid import uuid4

from cephvr.gui.program_editing import node_at
from cephvr.gui.protocol_groups import make_group
from cephvr.visual_stimulus.config.models.program_model import (
    Epoch,
    Group,
    Node,
    Program,
)


def grouped_program(program: Program) -> Program:
    """Wrap a new GUI trial; imported documents are never silently rewritten."""
    return make_group(program, (), 0, len(program.sequence) - 1, 1, False)[0]


def flat_group(program: Program, scope: tuple[int, ...]) -> bool:
    if len(scope) != 1:
        return False
    node = node_at(program, scope)
    return isinstance(node, Group) and all(isinstance(n, Epoch) for n in node.body)


def generated_batch(template: Program) -> Program:
    """Materialize bounded generated repeats, preserving settings and shared instances."""
    epochs: list[Epoch] = []
    identity = "batch_" + uuid4().hex

    def visit(nodes: tuple[Node, ...]) -> None:
        for node in nodes:
            if isinstance(node, Epoch):
                if len(epochs) >= 2000:
                    raise ValueError("Generate at most 2000 epochs at a time")
                epochs.append(
                    node.model_copy(
                        update={
                            "epoch_id": f"Generated_{len(epochs) + 1}",
                            "batch_id": identity,
                            "subgroup_draft": None,
                            "repetition_settings": (),
                            "repetition_rules": (),
                        }
                    )
                )
            else:
                if node.conditions is not None or node.order != "as_listed":
                    raise ValueError("Generated batches require listed epochs")
                for _ in range(node.repetitions):
                    visit(node.body)

    visit(template.sequence)
    return template.model_copy(update={"sequence": tuple(epochs)})


def batches(
    program: Program, scope: tuple[int, ...]
) -> dict[str, tuple[tuple[int, ...], ...]]:
    if not flat_group(program, scope):
        return {}
    node = node_at(program, scope)
    assert isinstance(node, Group)
    found: dict[str, list[tuple[int, ...]]] = {}
    for i, epoch in enumerate(node.body):
        assert isinstance(epoch, Epoch)
        if epoch.batch_id:
            found.setdefault(epoch.batch_id, []).append((*scope, i))
    return {identity: tuple(paths) for identity, paths in found.items()}


def subgroup_paths(
    program: Program, paths: tuple[tuple[int, ...], ...]
) -> tuple[tuple[int, ...], ...]:
    """Expand source clicks to complete batches without crossing group boundaries."""
    selected: set[tuple[int, ...]] = set()
    for path in paths:
        node = node_at(program, path)
        if isinstance(node, Epoch) and node.batch_id:
            selected.update(batches(program, path[:-1]).get(node.batch_id, (path,)))
        else:
            selected.add(path)
    return tuple(sorted(selected))
