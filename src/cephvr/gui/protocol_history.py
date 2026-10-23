"""Bounded local document snapshots; never an experiment execution history."""

from dataclasses import dataclass, field

from cephvr.visual_stimulus.config.categories import Category, validate_category
from cephvr.visual_stimulus.config.models.program_model import Program


@dataclass(frozen=True)
class Selection:
    program: Program
    scope: tuple[int, ...]
    index: int
    layer: int
    screen: str = ""
    paths: tuple[tuple[int, ...], ...] = ()
    arena_boundaries_json: str = ""
    protocol_categories: tuple[Category | None, ...] = ()


def restored_programs(
    programs: tuple[Program, ...], index: int, target: Selection
) -> tuple[Program, ...]:
    """Validate the complete category transaction before consuming an undo entry."""
    categories = target.protocol_categories
    if categories and len(categories) != len(programs):
        raise ValueError(
            "Restore the trial schedule before undoing its category change"
        )
    restored = tuple(
        (target.program if i == index else program).model_copy(
            update={"category": categories[i] if categories else program.category}
        )
        for i, program in enumerate(programs)
    )
    for program in restored:
        validate_category(program)
    return restored


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
