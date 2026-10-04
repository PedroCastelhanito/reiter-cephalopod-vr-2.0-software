"""Bounded local document snapshots; never an experiment execution history."""

from dataclasses import dataclass, field

from cephvr.visual_stimulus.config.models.program_model import Program


@dataclass(frozen=True)
class Selection:
    program: Program
    scope: tuple[int, ...]
    index: int
    layer: int
    screen: str = ""


@dataclass
class EditHistory:
    past: list[Selection] = field(default_factory=list)
    future: list[Selection] = field(default_factory=list)

    def push(self, previous: Selection) -> None:
        self.past.append(previous)
        self.past[:] = self.past[-40:]
        self.future.clear()

    def travel(self, current: Selection, redo: bool = False) -> Selection | None:
        source, destination = (
            (self.future, self.past) if redo else (self.past, self.future)
        )
        if not source:
            return None
        destination.append(current)
        return source.pop()
