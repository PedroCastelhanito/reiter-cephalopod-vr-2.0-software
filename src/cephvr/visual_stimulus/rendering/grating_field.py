"""Resolve linked grating snapshots from one reference at the same evaluation time."""

from dataclasses import replace

from cephvr.visual_stimulus.config.grating_field import field_on_surface
from cephvr.visual_stimulus.config.models.display_profile import Geometry
from cephvr.visual_stimulus.config.models.program_model import (
    Constant,
    Grating,
    TextureSettings,
)

from .state import InstanceState
from .types import InstanceSnapshot


def shared_grating_snapshots(
    snapshots: tuple[InstanceSnapshot, ...], geometry: Geometry
) -> tuple[InstanceSnapshot, ...]:
    by_id = {s.instance_id: s for s in snapshots}
    result = []
    for snapshot in snapshots:
        target = snapshot.settings
        if (
            not isinstance(target, TextureSettings)
            or not target.grating
            or target.linked_to is None
        ):
            result.append(snapshot)
            continue
        source = by_id[target.linked_to]
        settings = source.settings
        assert isinstance(settings, TextureSettings) and isinstance(
            settings.pattern, Grating
        )
        source_values = {
            k: float(v) for k, v in source.state if isinstance(v, (int, float))
        }
        frequency, rotation, phase = field_on_surface(
            settings, source_values, target, geometry
        )
        values = dict(snapshot.state)
        values.update(
            frequency=frequency,
            rotation=rotation,
            phase_x=phase,
            phase_y=0.0,
            x=0.0,
            y=0.0,
            contrast=source_values.get("contrast", 1.0),
        )
        pattern = settings.pattern.model_copy(
            update={"frequency": Constant(kind="constant", value=frequency)}
        )
        resolved = target.model_copy(
            update={
                "pattern": pattern,
                "mean_linear_rgb": settings.mean_linear_rgb,
                "modulation_linear_rgb": settings.modulation_linear_rgb,
            }
        )
        result.append(replace(snapshot, settings=resolved, state=tuple(values.items())))
    return tuple(result)


def retain_shared_grating_phase(
    instances: dict[str, InstanceState], geometry: Geometry, now_ns: int
) -> None:
    """Resolve the exact boundary phase before unlink/reset transitions (V07)."""
    linked = {
        key
        for key, live in instances.items()
        if live.active
        and isinstance(live.settings, TextureSettings)
        and live.settings.grating
        and live.settings.linked_to is not None
    }
    if not linked:
        return
    snapshots = tuple(
        InstanceSnapshot(
            key,
            live.family,
            True,
            live.snapshot(now_ns=now_ns, epoch_start_ns=live.last_epoch_start_ns),
            live.settings,
        )
        for key, live in instances.items()
        if live.active
    )
    for snapshot in shared_grating_snapshots(snapshots, geometry):
        if snapshot.instance_id in linked:
            values = dict(snapshot.state)
            for name in ("x", "y", "rotation", "phase_x", "phase_y"):
                field = instances[snapshot.instance_id].values[name]
                value = values[name]
                assert isinstance(value, (int, float))
                field.value = float(value)
                field.anchor_ns = now_ns
