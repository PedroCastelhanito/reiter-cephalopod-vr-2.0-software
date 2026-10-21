"""Planned layer/arena pose continuity for tracking-form dials and the arena map."""

from dataclasses import replace
from math import cos, radians, sin

from cephvr.gui.preview_motion_data import MotionEpoch
from cephvr.visual_stimulus.compiler.transitions import compile_boundaries
from cephvr.visual_stimulus.config.models.artifact_models import CompiledEpoch
from cephvr.visual_stimulus.config.models.display_profile import Geometry
from cephvr.visual_stimulus.config.models.program_model import (
    Rate,
    Settings,
    TextureSettings,
    Trajectory,
)
from cephvr.visual_stimulus.config.texture_links import validate_links
from cephvr.visual_stimulus.rendering.state import InstanceState, StateField
from cephvr.visual_stimulus.rendering.texture_links import bind_texture_links

# Central-difference half step for planned velocity, in epoch-local nanoseconds.
DIFFERENCE_NS = 50_000_000
WAITING = "Waiting for tracking"


def uses_trajectory(setting: Settings) -> bool:
    angle = setting.motion.yaw if setting.kind == "arena" else setting.motion.rotation
    return any(
        isinstance(item, Trajectory)
        for item in (setting.motion.x, setting.motion.y, angle)
    )


class PlannedStates:
    """Replay V07 boundaries through renderer state so continuity matches playback.

    Feedback-driven epochs make an instance's later pose unknown until a fresh
    initialize/reset/restart; those instants raise instead of guessing.
    """

    def __init__(
        self, epochs: tuple[MotionEpoch, ...], geometry: Geometry | None = None
    ) -> None:
        self.epochs = epochs
        self.geometry = geometry
        self.errors: list[dict[str, str]] = []
        self.starts: list[dict[str, dict[str, StateField]]] = []
        if not epochs:
            return
        compiled = [
            CompiledEpoch(
                occurrence_index=index,
                source_epoch_id=epoch.name,
                duration_origin="fixed",
                lineage=(),
                scene_id=epoch.scene_id,
                start_ns=epoch.start_ns,
                end_ns=epoch.end_ns,
                truncated_curves=(),
                settings=epoch.settings,
            )
            for index, epoch in enumerate(epochs)
        ]
        instances: dict[str, InstanceState] = {}
        unknown: dict[str, str] = {}
        for epoch, boundary in zip(epochs, compile_boundaries(compiled), strict=False):
            by_id = {setting.instance_id: setting for setting in epoch.settings}
            for operation in boundary.operations:
                setting = by_id.get(operation.instance_id)
                existing = instances.get(operation.instance_id)
                if setting is not None and (
                    operation.action == "initialize" or existing is None
                ):
                    instances[operation.instance_id] = InstanceState.initialize(
                        setting, now_ns=epoch.start_ns, epoch_start_ns=epoch.start_ns
                    )
                elif existing is not None:
                    existing.transition(
                        setting,
                        action=operation.action,
                        epoch_start_ns=epoch.start_ns,
                        now_ns=epoch.start_ns,
                    )
                if operation.action in ("initialize", "reset", "restart_incompatible"):
                    unknown.pop(operation.instance_id, None)
            for key, setting in by_id.items():
                if not isinstance(setting, TextureSettings) or not setting.linked_to:
                    continue
                reference = by_id.get(setting.linked_to)
                try:
                    if geometry is None:
                        raise ValueError(
                            "Linked motion needs calibrated screen geometry"
                        )
                    if reference is None:
                        raise ValueError("Linked texture reference is unavailable")
                    if key in unknown or setting.linked_to in unknown:
                        raise ValueError(unknown.get(key) or unknown[setting.linked_to])
                    validate_links((reference, setting), resolved=True)
                    bind_texture_links(
                        {name: instances[name] for name in (setting.linked_to, key)},
                        geometry,
                        now_ns=epoch.start_ns,
                    )
                except (ValueError, TypeError, KeyError, OverflowError) as error:
                    unknown[key] = str(error)
            self.errors.append(dict(unknown))
            self.starts.append(
                {
                    key: {name: replace(item) for name, item in state.values.items()}
                    for key, state in instances.items()
                    if key in by_id and key not in unknown
                }
            )
            unknown.update(
                {key: WAITING for key, setting in by_id.items() if setting.feedback}
            )

    def values(self, index: int, instance_id: str, local_ns: int) -> dict[str, float]:
        epoch = self.epochs[index]
        start = self.starts[index].get(instance_id)
        setting = next(s for s in epoch.settings if s.instance_id == instance_id)
        if start is None or setting.feedback:
            raise ValueError(self.errors[index].get(instance_id, WAITING))
        now_ns = epoch.start_ns + local_ns
        return {name: replace(item).advance(now_ns) for name, item in start.items()}

    def resolved_texture(self, index: int, setting: TextureSettings) -> TextureSettings:
        """Expose the renderer-bound rates without copying reference phase or pose."""
        self.values(index, setting.instance_id, 0)
        fields = self.starts[index][setting.instance_id]
        rates = {}
        for name in ("phase_x", "phase_y", "rotation"):
            function = fields[name].function
            if function is None:
                raise ValueError("Linked motion rate is unavailable")
            rates[name] = Rate(kind="rate", function=function)
        return setting.model_copy(
            update={
                "linked_to": None,
                "phase_x": rates["phase_x"],
                "phase_y": rates["phase_y"],
                "motion": setting.motion.model_copy(
                    update={"rotation": rates["rotation"]}
                ),
            }
        )

    def body_velocity(
        self, index: int, setting: Settings, local_ns: int
    ) -> tuple[float, float, float]:
        """Forward, animal-left and CCW angular speed in the instance heading frame."""
        if isinstance(setting, TextureSettings) and not all(
            item.kind == "hold" for item in (setting.phase_x, setting.phase_y)
        ):
            raise ValueError(
                "Combined texture translation and phase motion is not plotted."
            )
        span = self.epochs[index].end_ns - self.epochs[index].start_ns - 1
        left, right = (
            max(0, local_ns - DIFFERENCE_NS),
            min(span, local_ns + DIFFERENCE_NS),
        )
        if right <= left:
            return 0.0, 0.0, 0.0
        before = self.values(index, setting.instance_id, left)
        after = self.values(index, setting.instance_id, right)
        seconds = (right - left) / 1e9
        dx, dy = ((after[k] - before[k]) / seconds for k in ("x", "y"))
        angle = "yaw" if setting.kind == "arena" else "rotation"
        # The heading frame is the instant's own angle, not the window midpoint.
        heading = radians(self.values(index, setting.instance_id, local_ns)[angle])
        turn = (after[angle] - before[angle]) / seconds
        if setting.kind == "arena":
            # V24 body frame: forward is (-sin yaw, cos yaw); sideways is animal-left.
            forward = -sin(heading) * dx + cos(heading) * dy
            lateral = -cos(heading) * dx - sin(heading) * dy
        else:
            # Layers move forward along their rotated local +X, with +Y to the left.
            forward = cos(heading) * dx + sin(heading) * dy
            lateral = -sin(heading) * dx + cos(heading) * dy
        # Drop trigonometric round-off so pure forward motion reads as such.
        return round(forward, 9), round(lateral, 9), round(turn, 9)

    def pose(
        self, index: int, instance_id: str, time: float
    ) -> tuple[float, float, float]:
        epoch = self.epochs[index]
        values = self.values(index, instance_id, epoch.local_ns(time))
        return values["x"], values["y"], values["yaw"]
