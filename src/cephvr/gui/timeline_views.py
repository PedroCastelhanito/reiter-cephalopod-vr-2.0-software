"""Compact source-node views; repetitions never allocate presentation nodes."""

from collections import OrderedDict
from dataclasses import dataclass

from cephvr.gui.program_editing import nodes_at
from cephvr.gui.protocol_document import duration
from cephvr.gui.timeline_details import stimulus_key
from cephvr.visual_stimulus.config.models.program_model import Epoch, Node, Program


def epoch_count(node: Node) -> int:
    if isinstance(node, Epoch):
        return 1
    return (
        sum(epoch_count(child) for child in node.body)
        * node.repetitions
        * (len(node.conditions.rows) if node.conditions else 1)
    )


@dataclass(frozen=True)
class TimelineView:
    program: Program
    paths: tuple[tuple[int, ...], ...]
    nodes: tuple[Node, ...]
    keys: tuple[str, ...]
    counts: tuple[int, ...]
    durations: tuple[float | None, ...]
    batch_runs: tuple[tuple[int, int, str] | None, ...]


class TimelineViews:
    def __init__(self) -> None:
        self.entries: OrderedDict[tuple[int, tuple[int, ...]], TimelineView] = (
            OrderedDict()
        )

    def get(self, program: Program, scope: tuple[int, ...] = ()) -> TimelineView:
        """Retain at most four immutable program/scope views, including source owners."""
        identity = (id(program), scope)
        if identity in self.entries:
            self.entries.move_to_end(identity)
            return self.entries[identity]
        nodes = nodes_at(program, scope)
        runs: list[tuple[int, int, str] | None] = [None] * len(nodes)
        numbers: dict[str, int] = {}
        start = 0
        while start < len(nodes):
            node = nodes[start]
            if not isinstance(node, Epoch) or not node.batch_id:
                start += 1
                continue
            number = numbers.setdefault(node.batch_id, len(numbers) + 1)
            end = start + 1
            while (
                end < len(nodes)
                and isinstance(next_node := nodes[end], Epoch)
                and next_node.batch_id == node.batch_id
            ):
                end += 1
            title = f"Batch {number}" + (
                f" · {node.batch_label}" if node.batch_label else ""
            )
            runs[start:end] = [(start, end, title)] * (end - start)
            start = end
        view = TimelineView(
            program,
            tuple((*scope, i) for i in range(len(nodes))),
            nodes,
            tuple(
                stimulus_key(program, n) if isinstance(n, Epoch) else "group"
                for n in nodes
            ),
            tuple(epoch_count(n) for n in nodes),
            tuple(duration(n) for n in nodes),
            tuple(runs),
        )
        self.entries[identity] = view
        if len(self.entries) > 4:
            self.entries.popitem(last=False)
        return view
