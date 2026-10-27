"""Bind prepared reference motion to the existing retained follower state fields."""

from collections.abc import Mapping

from cephvr.visual_stimulus.config.models.display_profile import Geometry
from cephvr.visual_stimulus.config.models.program_model import (
    Constant,
    Rate,
    TextureSettings,
)
from cephvr.visual_stimulus.config.texture_links import (
    linked_rates,
    validate_spin_pivot,
)
from cephvr.visual_stimulus.rendering.state import InstanceState


def bind_texture_links(
    instances: Mapping[str, InstanceState], geometry: Geometry, *, now_ns: int
) -> None:
    for target in instances.values():
        setting = target.settings
        if (
            not target.active
            or not isinstance(setting, TextureSettings)
            or setting.linked_to is None
            or setting.grating
        ):
            continue
        source = instances[setting.linked_to]
        if not source.active or not isinstance(source.settings, TextureSettings):
            raise ValueError("Prepared texture reference is not active")
        validate_spin_pivot(
            source.settings,
            geometry,
            (source.values["x"].value, source.values["y"].value),
        )
        rates = linked_rates(
            source.settings,
            setting,
            geometry,
            source_rotation=source.values["rotation"].value,
            target_rotation=target.values["rotation"].value,
        )
        for name, value in zip(("phase_x", "phase_y", "rotation"), rates, strict=True):
            target.values[name].bind(
                Rate(kind="rate", function=Constant(kind="constant", value=value)),
                epoch_start_ns=now_ns,
                now_ns=now_ns,
            )
