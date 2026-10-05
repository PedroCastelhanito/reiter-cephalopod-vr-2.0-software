"""Bounded immutable authoring views; selection never expands the same trial twice."""

from collections import OrderedDict
from dataclasses import dataclass

from cephvr.gui.epoch_batch import epoch_paths
from cephvr.gui.program_editing import node_at
from cephvr.gui.timeline_details import stimulus_key
from cephvr.visual_stimulus.compiler.expansion import expand_program
from cephvr.visual_stimulus.config.models.program_model import Epoch, Program


@dataclass(frozen=True)
class TimelineView:
    program: Program
    sources: tuple[tuple[int, ...], ...]
    paths: tuple[tuple[int, ...], ...]
    nodes: tuple[Epoch, ...]
    keys: tuple[str, ...]
    error: str


class TimelineViews:
    def __init__(self) -> None:
        self.entries: OrderedDict[int, TimelineView] = OrderedDict()

    def get(self, program: Program) -> TimelineView:
        """Cache by immutable object identity; entries retain their program references."""
        identity = id(program)
        if identity in self.entries:
            self.entries.move_to_end(identity)
            return self.entries[identity]
        sources = epoch_paths(program)
        by_id = {}
        for path in sources:
            source = node_at(program, path)
            assert isinstance(source, Epoch)
            by_id[source.epoch_id] = path
        error = ""
        try:
            expanded = expand_program(
                program, seed_decimal="0", max_expanded_epochs=2000
            )
            nodes = tuple(
                e.source.model_copy(update={"settings": e.settings}) for e in expanded
            )
            paths = tuple(by_id[e.source.epoch_id] for e in expanded)
        except ValueError as failure:
            nodes, paths = (), ()
            error = str(failure)
        view = TimelineView(
            program,
            sources,
            paths,
            nodes,
            tuple(stimulus_key(program, n) for n in nodes),
            error,
        )
        self.entries[identity] = view
        if len(self.entries) > 4:
            self.entries.popitem(last=False)
        return view
