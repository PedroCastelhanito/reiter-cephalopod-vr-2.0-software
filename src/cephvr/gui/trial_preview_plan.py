"""Read-only example timing and retained state for the local planning preview."""

from bisect import bisect_right
from dataclasses import dataclass

from cephvr.visual_stimulus.compiler.expansion import expand_program
from cephvr.visual_stimulus.compiler.transitions import compile_boundaries
from cephvr.visual_stimulus.config.models.artifact_models import CompiledEpoch
from cephvr.visual_stimulus.config.models.program_model import (
    Fixed,
    Program,
    Settings,
    Time,
)
from cephvr.visual_stimulus.rendering.state import InstanceState


@dataclass(frozen=True)
class PreviewLayer:
    setting: Settings
    values: dict[str, float]


class PreviewPlan:
    def __init__(self, program: Program) -> None:
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
                if setting is not None:
                    for assignment in setting.assignments:
                        if isinstance(assignment.value, Time):
                            value = assignment.value.ns() / 1e9
                        elif isinstance(assignment.value, (int, float)):
                            value = float(assignment.value)
                        else:
                            raise ValueError(
                                "Preview assignment contains an unresolved value"
                            )
                        state.values[assignment.target].value = value
            self.cursor += 1
        self.time_ns = now_ns
        self.index = bisect_right(self.starts, now_ns) - 1
        epoch = self.epochs[self.index]
        by_id = {s.instance_id: s for s in epoch.settings}
        scene = next(s for s in self.program.scenes if s.scene_id == epoch.scene_id)
        order = ([scene.arena_instance_id] if scene.arena_instance_id else []) + list(
            scene.layer_instance_ids
        )
        return tuple(
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
