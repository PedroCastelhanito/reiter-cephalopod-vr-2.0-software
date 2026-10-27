"""Protocol categories shared by authoring and canonical validation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from cephvr.visual_stimulus.config.models.program_model import Program

Category = Literal["media_presentation", "navigation_3d"]
CATEGORY_LABELS: dict[Category, str] = {
    "media_presentation": "Media presentation",
    "navigation_3d": "3D navigation",
}


def validate_category(program: Program) -> None:
    """Media permits 2D motion; arenas require navigation, including alternatives."""
    from cephvr.visual_stimulus.config.models.program_model import Epoch, Group

    def walk(nodes: tuple[Epoch | Group, ...]) -> None:
        for node in nodes:
            if isinstance(node, Group):
                walk(node.body)
            elif program.category == "media_presentation":
                for settings in (node.settings, *node.repetition_settings):
                    if any(setting.kind == "arena" for setting in settings):
                        raise ValueError(
                            f"{node.epoch_id}: arena requires 3D navigation"
                        )

    walk(program.sequence)


def suggested_category(program: Program) -> Category:
    """Classify for display without changing unclassified legacy content."""
    return (
        "navigation_3d"
        if any(scene.arena_instance_id for scene in program.scenes)
        else "media_presentation"
    )
