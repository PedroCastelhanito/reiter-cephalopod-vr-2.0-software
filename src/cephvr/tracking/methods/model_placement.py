"""T11 verify actual prepared ORT placement; CPU is limited to shape metadata."""

from __future__ import annotations

from typing import Any


def verify_placement(graph: Any, events: list[dict[str, Any]]) -> tuple[str, ...]:
    nodes = {node.name: node for node in graph.graph.node}
    if len(nodes) != len(graph.graph.node) or "" in nodes:
        raise ValueError("optimized graph needs unique retained node names")
    metadata = {
        tensor.name
        for tensor in graph.graph.initializer
        if tensor.data_type in (6, 7) and len(tensor.dims) <= 1
    }
    allowed = set()
    operations = {
        "Gather",
        "GatherElements",
        "Unsqueeze",
        "Squeeze",
        "Concat",
        "Cast",
        "Slice",
        "Add",
        "Sub",
        "Mul",
        "Div",
        "Min",
        "Max",
        "Reshape",
        "Identity",
        "Range",
        "Equal",
        "Where",
    }
    for node in graph.graph.node:
        if any(attribute.type in (5, 10) for attribute in node.attribute):
            raise ValueError(
                "control-flow subgraphs require complete placement evidence"
            )
        if node.op_type in ("Shape", "Size") or (
            node.op_type in operations
            and all(not name or name in metadata for name in node.input)
        ):
            metadata.update(node.output)
            allowed.add(node.name)
    cpu = set()
    executed = set()
    cuda = False
    for event in events:
        args = event.get("args", {})
        provider = args.get("provider")
        if not provider:
            continue
        name = str(event.get("name", "")).removesuffix("_kernel_time")
        if name not in nodes:
            raise ValueError(
                "profile node cannot be matched to prepared optimized graph"
            )
        executed.add(name)
        if provider == "CUDAExecutionProvider":
            cuda = True
        elif provider == "CPUExecutionProvider" and name in allowed:
            cpu.add(name)
        else:
            raise ValueError(
                "CPU tensor computation or unapproved provider in prepared graph"
            )
    if not cuda or executed != set(nodes):
        raise ValueError("incomplete CUDA graph placement evidence")
    return tuple(sorted(cpu))
