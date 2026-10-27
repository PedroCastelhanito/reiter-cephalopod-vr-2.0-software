"""Read-only example timing and retained state for the local planning preview."""

from bisect import bisect_right
from dataclasses import dataclass

from cephvr.visual_stimulus.compiler.expansion import expand_program
from cephvr.visual_stimulus.compiler.texture_links import validate_link_geometry
from cephvr.visual_stimulus.compiler.transitions import compile_boundaries
from cephvr.visual_stimulus.config.models.artifact_models import CompiledEpoch
from cephvr.visual_stimulus.config.models.display_profile import Geometry
from cephvr.visual_stimulus.config.models.program_model import (
    Fixed,
    Program,
    Settings,
)
from cephvr.visual_stimulus.rendering.state import InstanceState
from cephvr.visual_stimulus.rendering.texture_links import bind_texture_links


@dataclass(frozen=True)
class PreviewLayer:
    setting: Settings
    values: dict[str, float]


class PreviewPlan:
    def __init__(self, program: Program, geometry: Geometry | None = None) -> None:
        self.program = program
        self.epochs = []
        elapsed = 0
        for i, occurrence in enumerate(
            expand_program(program, seed_decimal="0", max_expanded_epochs=2000)
        ):
            source = occurrence.source
            if not isinstance(source.duration, Fixed):
                raise ValueError(
                    "Preview needs fixed epoch durations; variable durations are resolved at Setup"
                )
            end = elapsed + source.duration.duration.ns()
            self.epochs.append(
                CompiledEpoch(
                    occurrence_index=i,
                    source_epoch_id=source.epoch_id,
                    duration_origin="fixed",
                    lineage=occurrence.lineage,
                    scene_id=source.scene_id,
                    start_ns=elapsed,
                    end_ns=end,
                    truncated_curves=(),
                    settings=occurrence.settings,
                )
            )
            elapsed = end
        if not self.epochs:
            raise ValueError("Add an epoch before previewing")
        self.total_ns = elapsed
        self.starts = [e.start_ns for e in self.epochs]
        self.boundaries = compile_boundaries(self.epochs)
        self.geometry = geometry
        if any(getattr(s, "linked_to", None) for e in self.epochs for s in e.settings):
            if geometry is None or len(geometry.surfaces) != 4:
                raise ValueError(
                    "Configure all four screen planes for linked preview motion"
                )
            validate_link_geometry(self.epochs, self.boundaries, geometry)
        self.states: dict[str, InstanceState] = {}
        self.cursor = 0
        self.time_ns = -1
        self.index = 0

    def seek(self, now_ns: int) -> tuple[PreviewLayer, ...]:
        """Replay boundaries on backward seeks so retained state stays reproducible."""
        now_ns = max(0, min(now_ns, self.total_ns - 1))
        if now_ns < self.time_ns:
            self.states.clear()
            self.cursor = 0
        while (
            self.cursor < len(self.boundaries)
            and self.boundaries[self.cursor].time_ns <= now_ns
        ):
            boundary = self.boundaries[self.cursor]
            if boundary.after is None:
                break
            epoch = self.epochs[boundary.after]
            for prior_state in self.states.values():
                if prior_state.family == "video" and prior_state.active:
                    prior_state.values["playback"].value += (
                        boundary.time_ns - prior_state.last_epoch_start_ns
                    ) / 1e9
                prior_state.advance(boundary.time_ns)
            if self.geometry is not None:
                from cephvr.visual_stimulus.rendering.grating_field import (
                    retain_shared_grating_phase,
                )

                retain_shared_grating_phase(
                    self.states, self.geometry, boundary.time_ns
                )
            for operation in boundary.operations:
                setting = (
                    epoch.settings[operation.next_settings_index]
                    if operation.next_settings_index is not None
                    else None
                )
                state = self.states.get(operation.instance_id)
                if state is None:
                    assert setting is not None
                    state = InstanceState.initialize(
                        setting, now_ns=boundary.time_ns, epoch_start_ns=epoch.start_ns
                    )
                    self.states[operation.instance_id] = state
                else:
                    state.transition(
                        setting,
                        action=operation.action,
                        epoch_start_ns=epoch.start_ns,
                        now_ns=boundary.time_ns,
                    )
                if setting is not None and not (
                    setting.kind == "texture" and setting.grating
                ):
                    for assignment in setting.assignments:
                        from cephvr.visual_stimulus.config.models.program_model import (
                            Time,
                        )

                        if isinstance(assignment.value, Time):
                            value = assignment.value.ns() / 1e9
                        elif isinstance(assignment.value, (int, float)):
                            value = float(assignment.value)
                        else:
                            raise ValueError(
                                "Preview assignment contains an unresolved value"
                            )
                        state.values[assignment.target].value = value
            if self.geometry is not None:
                bind_texture_links(self.states, self.geometry, now_ns=boundary.time_ns)
            self.cursor += 1
        self.time_ns = now_ns
        self.index = bisect_right(self.starts, now_ns) - 1
        epoch = self.epochs[self.index]
        by_id = {s.instance_id: s for s in epoch.settings}
        scene = next(s for s in self.program.scenes if s.scene_id == epoch.scene_id)
        order = ([scene.arena_instance_id] if scene.arena_instance_id else []) + list(
            scene.layer_instance_ids
        )
        layers = tuple(
            PreviewLayer(
                by_id[key],
                dict(
                    self.states[key].snapshot(
                        now_ns=now_ns, epoch_start_ns=epoch.start_ns
                    )
                ),
            )
            for key in order
            if key in by_id
        )

        if self.geometry is None:
            return layers
        from cephvr.visual_stimulus.rendering.grating_field import (
            shared_grating_snapshots,
        )
        from cephvr.visual_stimulus.rendering.types import InstanceSnapshot

        snapshots = shared_grating_snapshots(
            tuple(
                InstanceSnapshot(
                    layer.setting.instance_id,
                    layer.setting.kind,
                    True,
                    tuple(layer.values.items()),
                    layer.setting,
                )
                for layer in layers
            ),
            self.geometry,
        )
        return tuple(
            PreviewLayer(
                snapshot.settings,
                {k: float(v) for k, v in snapshot.state if isinstance(v, (int, float))},
            )
            for snapshot in snapshots
            if snapshot.settings is not None
        )
