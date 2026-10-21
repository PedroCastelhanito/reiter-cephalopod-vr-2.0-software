"""Planned dial and world-map samples for each legend source of a trial."""

from dataclasses import dataclass
from math import hypot

from cephvr.gui.preview_motion_data import (
    DialSample,
    MotionSource,
    planned_rotation,
    planned_velocity,
    size_functions_vary,
)
from cephvr.gui.preview_motion_dial import MapSample
from cephvr.gui.preview_motion_state import WAITING, PlannedStates, uses_trajectory
from cephvr.visual_stimulus.config.models.program_model import (
    Settings,
    TextureSettings,
)
from cephvr.visual_stimulus.config.rig_coordinates import direction_frame
from cephvr.visual_stimulus.config.texture_links import unfolded_direction

DRIVE_UNIT = "mm/s"
# Per-epoch samples used only to fix each dial's ring scale for the trial.
SCALE_SAMPLES = 20
MAP_SAMPLES = 1500


def follower(setting: Settings | None) -> bool:
    return isinstance(setting, TextureSettings) and bool(setting.linked_to)


@dataclass
class SourcePanel:
    """Which instruments one legend source shows, fixed for the whole trial."""

    source: MotionSource
    color: str
    form: str
    arena: bool
    driving: bool
    size: tuple[bool, bool]
    scale: float = 0.0
    rotation_scale: float = 0.0
    path: tuple[tuple[tuple[float, float, float], ...], ...] = ()
    extent: tuple[float, float, float, float] = (-50.0, -50.0, 50.0, 50.0)


class InstrumentPlan(PlannedStates):
    """Per-source instrument choices and samples over one trial's planned state."""

    def panel(self, source: MotionSource, color: str) -> SourcePanel:
        settings = [s for s in source.settings if s is not None and not follower(s)]
        arena = any(s.kind == "arena" for s in settings)
        panel = SourcePanel(
            source,
            color,
            "tracking" if arena or any(map(uses_trajectory, settings)) else "texture",
            arena,
            not arena and any(s.feedback for s in settings),
            (False, False) if arena else size_functions_vary(source.settings),
        )
        speeds, turns = [0.0], [0.0]
        for index, epoch in enumerate(self.epochs):
            for step in range(SCALE_SAMPLES + 1):
                time = epoch.start + (epoch.end - epoch.start) * step / SCALE_SAMPLES
                sample = self.dial_sample(panel, index, time)
                if sample.vector is not None:
                    speeds.append(hypot(*sample.vector))
                if sample.angular_speed is not None:
                    turns.append(abs(sample.angular_speed))
        panel.scale, panel.rotation_scale = max(speeds), max(turns)
        if arena:
            panel.path, panel.extent = self.arena_path(source)
        return panel

    def arena_path(
        self, source: MotionSource
    ) -> tuple[
        tuple[tuple[tuple[float, float, float], ...], ...],
        tuple[float, float, float, float],
    ]:
        """Sample the planned world path once; unplanned spans break the line."""
        epochs = self.epochs
        step = max(0.2, epochs[-1].end / MAP_SAMPLES) if epochs else 1.0
        segments: list[tuple[tuple[float, float, float], ...]] = []
        current: list[tuple[float, float, float]] = []
        for index, (epoch, setting) in enumerate(
            zip(epochs, source.settings, strict=True)
        ):
            count = max(1, round((epoch.end - epoch.start) / step))
            for i in range(count + 1):
                time = epoch.start + (epoch.end - epoch.start) * i / count
                try:
                    if setting is None:
                        raise ValueError("No stimulus")
                    x, y, _ = self.pose(index, setting.instance_id, time)
                    current.append((time, x, y))
                except (ValueError, TypeError, OverflowError):
                    if current:
                        segments.append(tuple(current))
                    current = []
        if current:
            segments.append(tuple(current))
        points = [(x, y) for segment in segments for _, x, y in segment]
        if not points:
            return (), (-50.0, -50.0, 50.0, 50.0)
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        pad = max(50.0 - (max(xs) - min(xs)) / 2, 50.0 - (max(ys) - min(ys)) / 2, 5.0)
        return tuple(segments), (
            min(xs) - pad,
            min(ys) - pad,
            max(xs) + pad,
            max(ys) + pad,
        )

    def dial_sample(
        self, panel: SourcePanel, index: int | None, time: float, driving: bool = False
    ) -> DialSample:
        source = panel.source
        form = "tracking" if driving else panel.form
        unit = DRIVE_UNIT if driving else source.unit
        role = "tracking" if driving else "texture" if form == "texture" else "motion"
        name = f"{source.name.split(' · ')[0]} · {role}"
        scale = 0.0 if driving else panel.scale
        turns = 0.0 if driving else panel.rotation_scale

        display_rotation = {"Front": 90.0, "Right": 180.0}.get(source.key[0], 0.0)

        display_sign = 1.0

        def sample(
            vector: tuple[float, float] | None = None,
            angular: float | None = None,
            message: str = "",
            orientation: float | None = None,
        ) -> DialSample:
            return DialSample(
                name,
                panel.color,
                form,
                unit,
                vector,
                angular,
                scale,
                turns,
                message,
                orientation,
                display_rotation if form == "texture" else 0.0,
                display_sign,
            )

        setting = source.settings[index] if index is not None else None
        if index is None or setting is None:
            return sample(
                angular=0.0 if index is not None else None, message="No stimulus"
            )
        if driving:
            return sample(message=WAITING if setting.feedback else "No feedback")
        if setting.feedback:
            return sample(message=WAITING)
        local_ns = self.epochs[index].local_ns(time)
        try:
            if isinstance(setting, TextureSettings) and setting.linked_to:
                setting = self.resolved_texture(index, setting)
            if form == "tracking":
                forward, left, turn = self.body_velocity(index, setting, local_ns)
                orientation = None
                if not (forward or left):
                    angle = "yaw" if setting.kind == "arena" else "rotation"
                    orientation = self.values(index, setting.instance_id, local_ns)[
                        angle
                    ]
                return sample(
                    (forward, left) if forward or left else None,
                    turn,
                    orientation=orientation,
                )
            if (
                isinstance(setting, TextureSettings)
                and setting.space.kind == "physical_surface"
                and self.geometry is not None
            ):
                display_sign = -1.0
                display_rotation = unfolded_direction(
                    setting,
                    self.geometry,
                    source.key[0].lower(),
                    self.values(index, setting.instance_id, local_ns)["rotation"]
                    if any(m.kind != "hold" for m in (setting.phase_x, setting.phase_y))
                    else 0.0,
                )
            elif (
                isinstance(setting, TextureSettings)
                and setting.space.kind == "physical_surface"
            ):
                data = setting.model_dump(mode="json")
                data["initial"]["rotation_deg"] = self.values(
                    index, setting.instance_id, local_ns
                )["rotation"]
                if setting.space.kind == "physical_surface":
                    data["space"]["mappings"] = [
                        m
                        for m in data["space"]["mappings"]
                        if m["surface_id"] == source.key[0].lower()
                    ]
                else:
                    data["space"]["surfaces"] = [source.key[0].lower()]
                display_rotation, display_sign = direction_frame(data)
            x, y = planned_velocity(setting, local_ns)
            orientation = None
            if not (x or y):
                orientation = self.values(index, setting.instance_id, local_ns)[
                    "rotation"
                ]
        except (ValueError, TypeError, OverflowError, KeyError) as error:
            return sample(message=str(error))
        try:
            angular: float | None = planned_rotation(setting, local_ns)
        except (ValueError, TypeError, OverflowError):
            angular = None
        return sample((x, y) if x or y else None, angular, orientation=orientation)

    def map_sample(
        self, panel: SourcePanel, index: int | None, time: float
    ) -> MapSample:
        path = tuple(
            tuple((x, y) for t, x, y in segment if t <= time) for segment in panel.path
        )
        pose = None
        message = "No stimulus"
        setting = panel.source.settings[index] if index is not None else None
        if index is not None and setting is not None:
            try:
                pose = self.pose(index, setting.instance_id, time)
                message = ""
            except (ValueError, TypeError, OverflowError) as error:
                message = str(error)
        return MapSample(
            panel.source.name.split(" · ")[0],
            panel.color,
            path,
            pose,
            panel.extent,
            message,
        )
