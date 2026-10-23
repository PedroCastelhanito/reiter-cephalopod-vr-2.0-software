"""Protocol capabilities shared by authoring and canonical input validation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from cephvr.visual_stimulus.config.models.program_model import Program

Category = Literal["media_presentation", "texture_drift", "navigation_3d"]
CATEGORY_LABELS: dict[Category, str] = {
    "media_presentation": "Media presentation",
    "texture_drift": "Texture drift",
    "navigation_3d": "3D navigation",
}
MOTION_TARGETS = {
    "x",
    "y",
    "rotation",
    "phase_x",
    "phase_y",
    "width",
    "height",
    "frequency",
    "frequency_x",
    "frequency_y",
    "period_x",
    "period_y",
}


def validate_category(program: Program) -> None:
    """Reject incompatible executable settings, including repetition alternatives."""
    from cephvr.visual_stimulus.config.models.program_model import (
        Constant,
        Epoch,
        Group,
        Hold,
        Rate,
    )

    if program.category is None:
        return  # Unclassified legacy programs retain their exact executable content.

    def stationary(motion: object) -> bool:
        return isinstance(motion, Hold) or (
            isinstance(motion, Rate)
            and isinstance(motion.function, Constant)
            and motion.function.value == 0
        )

    def walk(nodes: tuple[Epoch | Group, ...]) -> None:
        for node in nodes:
            if isinstance(node, Group):
                walk(node.body)
                continue
            for settings in (node.settings, *node.repetition_settings):
                for setting in settings:
                    prefix = f"{node.epoch_id} / {setting.instance_id}"
                    if setting.kind == "arena":
                        if program.category != "navigation_3d":
                            raise ValueError(f"{prefix}: arena requires 3D navigation")
                        continue
                    if program.category != "media_presentation":
                        continue
                    motions = [
                        setting.motion.x,
                        setting.motion.y,
                        setting.motion.rotation,
                    ]
                    if setting.kind == "texture":
                        motions.extend((setting.phase_x, setting.phase_y))
                        for field in type(setting.pattern).model_fields:
                            value = getattr(setting.pattern, field)
                            if field in {
                                "frequency",
                                "frequency_x",
                                "frequency_y",
                                "period_x",
                                "period_y",
                            } and not isinstance(value, Constant):
                                raise ValueError(
                                    f"{prefix}: presentation requires fixed texture spacing"
                                )
                    if not all(stationary(motion) for motion in motions):
                        raise ValueError(
                            f"{prefix}: presentation requires stationary layers"
                        )
                    if not all(
                        isinstance(size, Constant)
                        for size in (setting.width, setting.height)
                    ):
                        raise ValueError(
                            f"{prefix}: presentation requires fixed layer size"
                        )
                    if any(
                        binding.target in MOTION_TARGETS for binding in setting.feedback
                    ):
                        raise ValueError(
                            f"{prefix}: presentation cannot use motion feedback"
                        )
            if program.category == "media_presentation" and any(
                rule.parameter != "Playback start" for rule in node.repetition_rules
            ):
                raise ValueError(f"{node.epoch_id}: presentation cannot vary motion")

    walk(program.sequence)


def suggested_category(program: Program) -> Category:
    """Classify for display only; never silently accept a category for legacy input."""
    if any(scene.arena_instance_id for scene in program.scenes):
        return "navigation_3d"
    try:
        validate_category(program.model_copy(update={"category": "media_presentation"}))
    except ValueError:
        return "texture_drift"
    return "media_presentation"
