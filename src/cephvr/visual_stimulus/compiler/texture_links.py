"""Preflight linked movement against display geometry and retained pivot history."""

from cephvr.visual_stimulus.config.models.artifact_models import Boundary, CompiledEpoch
from cephvr.visual_stimulus.config.models.display_profile import Geometry
from cephvr.visual_stimulus.config.models.program_model import TextureSettings
from cephvr.visual_stimulus.config.texture_links import (
    linked_rates,
    validate_spin_pivot,
)


def validate_link_geometry(
    epochs: list[CompiledEpoch], boundaries: tuple[Boundary, ...], geometry: Geometry
) -> None:
    positions: dict[str, tuple[float, float] | None] = {}
    for epoch, boundary in zip(epochs, boundaries, strict=False):
        settings = {s.instance_id: s for s in epoch.settings}
        for operation in boundary.operations:
            setting = settings.get(operation.instance_id)
            if setting is None or setting.kind == "arena":
                continue
            if operation.action in ("initialize", "reset", "restart_incompatible"):
                assert isinstance(setting.initial.x, (float, int)) and isinstance(
                    setting.initial.y, (float, int)
                )
                positions[setting.instance_id] = (
                    float(setting.initial.x),
                    float(setting.initial.y),
                )
        for target in epoch.settings:
            if not isinstance(target, TextureSettings) or target.linked_to is None:
                continue
            source = settings[target.linked_to]
            assert isinstance(source, TextureSettings)
            linked_rates(source, target, geometry, source_rotation=0, target_rotation=0)
            validate_spin_pivot(source, geometry, positions.get(source.instance_id))
        for setting in epoch.settings:
            if setting.kind == "arena":
                continue
            if (
                any(m.kind != "hold" for m in (setting.motion.x, setting.motion.y))
                or any(b.target in ("x", "y") for b in setting.feedback)
                or any(a.target in ("x", "y") for a in setting.assignments)
            ):
                positions[setting.instance_id] = None
