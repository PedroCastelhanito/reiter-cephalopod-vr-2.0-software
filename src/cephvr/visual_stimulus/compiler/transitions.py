"""V07 transition construction from adjacent resolved epoch instance lists."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from cephvr.visual_stimulus.config.models.artifact_models import (
    Boundary,
    CompiledEpoch,
    Transition,
)
from cephvr.visual_stimulus.config.models.program_model import (
    ArenaSettings,
    ImageSettings,
    ImageTile,
    Settings,
    TextureSettings,
    VideoSettings,
)


def _compatibility(settings: Settings) -> tuple[object, ...]:
    """Return the resource/coordinate identity that determines live-state reuse."""
    if isinstance(settings, ArenaSettings):
        return (
            settings.kind,
            settings.asset_id,
            settings.world_frame_id,
            settings.asset_to_world,
        )
    resource: object
    if isinstance(settings, (ImageSettings, VideoSettings)):
        resource = settings.asset_id
    elif isinstance(settings, TextureSettings) and isinstance(
        settings.pattern, ImageTile
    ):
        resource = (settings.pattern.kind, settings.pattern.asset_id)
    elif isinstance(settings, TextureSettings):
        resource = settings.pattern.kind
    else:
        raise TypeError(f"unsupported settings model: {type(settings).__name__}")
    return settings.kind, resource, settings.space.model_dump(mode="json")


def _assignments(settings: Settings) -> tuple[int, ...]:
    return tuple(range(len(settings.assignments)))


def compile_boundaries(epochs: Sequence[CompiledEpoch]) -> tuple[Boundary, ...]:
    """Compile chronological transition operations and terminal deactivation."""
    if not epochs:
        raise ValueError("prepared plan needs at least one epoch")
    boundaries: list[Boundary] = []
    prior_settings: dict[str, Settings] = {}
    retained_settings: dict[str, Settings] = {}
    for index, epoch in enumerate(epochs):
        current_settings = {setting.instance_id: setting for setting in epoch.settings}
        operations: list[Transition] = []
        for instance_id, _old in prior_settings.items():
            if instance_id not in current_settings:
                operations.append(
                    Transition(
                        instance_id=instance_id,
                        action="pause",
                        reason="instance leaves the active scene",
                        next_settings_index=None,
                        assignment_indices=(),
                    )
                )
        for settings_index, (instance_id, new) in enumerate(current_settings.items()):
            was_active = instance_id in prior_settings
            old = prior_settings.get(instance_id, retained_settings.get(instance_id))
            action: Literal[
                "initialize", "restart_incompatible", "reset", "resume", "continue"
            ]
            if old is None:
                action, reason = "initialize", "first activation in trial"
            elif _compatibility(old) != _compatibility(new):
                action, reason = (
                    "restart_incompatible",
                    "resource or coordinate interpretation changed",
                )
            elif new.reset:
                action, reason = "reset", "explicit authored reset"
            elif not was_active:
                action, reason = "resume", "compatible instance returns after absence"
            else:
                action, reason = "continue", "compatible state continues"
            operations.append(
                Transition(
                    instance_id=instance_id,
                    action=action,
                    reason=reason,
                    next_settings_index=settings_index,
                    assignment_indices=_assignments(new),
                )
            )
        boundaries.append(
            Boundary(
                time_ns=epoch.start_ns,
                before=index - 1 if index else None,
                after=index,
                operations=tuple(operations),
            )
        )
        prior_settings = current_settings
        retained_settings.update(current_settings)
    terminal = tuple(
        Transition(
            instance_id=instance_id,
            action="deactivate",
            reason="normal trial end",
            next_settings_index=None,
            assignment_indices=(),
        )
        for instance_id in prior_settings
    )
    boundaries.append(
        Boundary(
            time_ns=epochs[-1].end_ns,
            before=len(epochs) - 1,
            after=None,
            operations=terminal,
        )
    )
    return tuple(boundaries)
