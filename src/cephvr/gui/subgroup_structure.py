"""Source-only structural actions on one selected subgroup."""

from copy import deepcopy
from uuid import uuid4

from cephvr.gui.program_editing import data_nodes, document_ids, unique_id, validate
from cephvr.visual_stimulus.config.models.program_model import Program


def edit_subgroup(
    program: Program, paths: tuple[tuple[int, ...], ...], operation: str
) -> tuple[Program, tuple[tuple[int, ...], ...]]:
    if not paths or any(p[:-1] != paths[0][:-1] for p in paths):
        raise ValueError("Select epochs in one group")
    scope = paths[0][:-1]
    data = program.model_dump(mode="json")
    nodes = data_nodes(data, scope)
    positions = sorted(p[-1] for p in paths)
    selected = [nodes[i] for i in positions]
    remaining = [n for i, n in enumerate(nodes) if i not in positions]
    if operation == "remove":
        if not remaining:
            raise ValueError("A group must contain at least one epoch")
        nodes[:] = remaining
        return validate(data), ((*scope, min(positions[0], len(nodes) - 1)),)
    if operation == "duplicate":
        taken = document_ids(data)
        identities = {
            epoch.get("batch_id"): "batch_" + uuid4().hex for epoch in selected
        }
        copies = deepcopy(selected)
        for epoch in copies:
            epoch["epoch_id"] = unique_id(data, "Epoch", taken=taken)
            epoch["batch_id"] = identities[epoch.get("batch_id")]
        at = positions[-1] + 1
        nodes[at:at] = copies
        return validate(data), tuple((*scope, at + i) for i in range(len(copies)))
    if operation not in ("earlier", "later"):
        raise ValueError("Unknown subgroup action")
    if positions != list(range(positions[0], positions[-1] + 1)):
        raise ValueError("Select consecutive epochs to move a subgroup")
    at = positions[0]
    if operation == "earlier":
        if at == 0:
            return program, paths
        at -= 1
        neighbor = remaining[at].get("batch_id")
        while at > 0 and neighbor and remaining[at - 1].get("batch_id") == neighbor:
            at -= 1
    else:
        if at == len(remaining):
            return program, paths
        neighbor = remaining[at].get("batch_id")
        at += 1
        while (
            at < len(remaining)
            and neighbor
            and remaining[at].get("batch_id") == neighbor
        ):
            at += 1
    nodes[:] = remaining[:at] + selected + remaining[at:]
    return validate(data), tuple((*scope, at + i) for i in range(len(selected)))
