"""Bounded, read-only stimulus motion plot; never measured renderer evidence."""

from collections import Counter
from math import atan2, degrees, hypot

from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from cephvr.gui.components import Card, combo, label
from cephvr.gui.preview_motion_plot import (
    EpochStrip,
    MotionEpoch,
    MotionPlot,
    PolarMotionPlot,
)
from cephvr.visual_stimulus.compiler.expansion import expand_program
from cephvr.visual_stimulus.config.models.program_model import (
    Fixed,
    Group,
    Hold,
    Program,
    Rate,
    Settings,
    TextureSettings,
)
from cephvr.visual_stimulus.rendering.motion import evaluate_function


def motion_epochs(program: Program, seed: str) -> tuple[MotionEpoch, ...]:
    """Use canonical expansion without inventing unresolved timing or order."""
    pending = list(program.sequence)
    while pending:
        node = pending.pop()
        if isinstance(node, Group):
            if node.order == "shuffle_each_repetition" and not seed:
                raise ValueError("Set a stimulus seed to preview shuffled order.")
            pending.extend(node.body)
    epochs = []
    elapsed = 0.0
    for occurrence in expand_program(
        program, seed_decimal=seed or "0", max_expanded_epochs=2000
    ):
        source = occurrence.source
        if not isinstance(source.duration, Fixed):
            raise ValueError("Variable epoch timing is resolved at Setup.")
        end = elapsed + source.duration.duration.ns() / 1e9
        epochs.append(MotionEpoch(elapsed, end, source.epoch_id, occurrence.settings))
        elapsed = end
    return tuple(epochs)


def planned_velocity(setting: Settings, local_ns: int) -> tuple[float, float]:
    """Match the speed editor's units; unsupported motion stays explicitly unknown."""
    if setting.feedback:
        raise ValueError("Feedback-driven speed requires live renderer evidence.")
    motions = (setting.motion.x, setting.motion.y)
    if isinstance(setting, TextureSettings):
        if setting.linked_to:
            raise ValueError(
                f"Linked motion follows {setting.linked_to}; select its reference."
            )
        if not all(isinstance(item, Hold) for item in motions):
            raise ValueError(
                "Combined texture translation and phase motion is not plotted."
            )
        motions = (setting.phase_x, setting.phase_y)
    rates = []
    for motion in motions:
        if isinstance(motion, Hold):
            rates.append(0.0)
        elif isinstance(motion, Rate):
            rates.append(evaluate_function(motion.function, local_ns))
        else:
            raise ValueError(
                "Position trajectories have no speed trace in this preview."
            )
    if isinstance(setting, TextureSettings):
        pattern = setting.pattern
        if pattern.kind == "image_tile":
            periods = (
                evaluate_function(pattern.period_x, local_ns),
                evaluate_function(pattern.period_y, local_ns),
            )
        else:
            fx = evaluate_function(
                pattern.frequency_x
                if pattern.kind == "checkerboard"
                else pattern.frequency,
                local_ns,
            )
            fy = (
                evaluate_function(pattern.frequency_y, local_ns)
                if pattern.kind == "checkerboard"
                else fx
            )
            if fx <= 0 or fy <= 0:
                raise ValueError("Texture frequency must be positive to plot speed.")
            periods = (1 / fx, 1 / fy)
            if pattern.kind != "checkerboard":
                rates[1] = 0.0  # Gratings vary only along their local X axis.
        rates = [-rate * period for rate, period in zip(rates, periods, strict=True)]
    return rates[0], rates[1]


def planned_speed(setting: Settings, local_ns: int) -> float:
    return hypot(*planned_velocity(setting, local_ns))


def planned_rotation(setting: Settings, local_ns: int) -> float:
    if setting.feedback:
        raise ValueError("Feedback-driven rotation requires live renderer evidence.")
    motion = setting.motion.yaw if setting.kind == "arena" else setting.motion.rotation
    if isinstance(motion, Hold):
        return 0.0
    if isinstance(motion, Rate):
        return evaluate_function(motion.function, local_ns)
    raise ValueError("Angle trajectories have no angular speed trace in this preview.")


def projector_name(setting: Settings) -> str:
    if setting.kind == "arena":
        return "Arena"
    surfaces = (
        tuple(mapping.surface_id for mapping in setting.space.mappings)
        if setting.space.kind == "physical_surface"
        else setting.space.surfaces
    )
    return " + ".join(surface.title() for surface in surfaces)


class StimulusTimeline(Card):
    def __init__(self) -> None:
        super().__init__("Stimulus timeline", compact=True)
        row = QHBoxLayout()
        self.context = label("Planned motion · not measured output", "muted", wrap=True)
        self.trace_selector = combo(())
        self.trace_selector.setMinimumWidth(260)
        self.trace_selector.setAccessibleName("Motion source projector")
        row.addWidget(self.context, 1)
        row.addWidget(self.trace_selector)
        self.body.addLayout(row)
        self.plot = MotionPlot()
        self.plot.setToolTip(
            "Sampled planned translation speed; feedback and actual display timing are not measured here."
        )
        self.epoch_strip = EpochStrip()
        speed = QWidget()
        speed_layout = QVBoxLayout(speed)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(2)
        speed_layout.addWidget(self.epoch_strip)
        speed_layout.addWidget(self.plot, 1)
        self.polar = PolarMotionPlot()
        plots = QHBoxLayout()
        plots.addWidget(speed, 3)
        plots.addWidget(self.polar, 1)
        self.body.addLayout(plots, 1)
        self.program: Program | None = None
        self.seed = ""
        self.trace_selector.currentIndexChanged.connect(self.refresh_trace)
        self.plot.time_selected.connect(self.set_elapsed)

    def clear(self, message: str) -> None:
        self.program = None
        self.trace_selector.clear()
        self.trace_selector.setEnabled(False)
        self.plot.epochs = self.epoch_strip.epochs = ()
        self.plot.traces = []
        self.plot.message = message
        self.set_elapsed(None)
        self.epoch_strip.update()

    def set_program(self, program: Program, seed: str, title: str) -> None:
        self.context.setText(f"{title} · planned motion · not measured output")
        if program is self.program and seed == self.seed:
            return
        self.program, self.seed = program, seed
        self.plot.traces = []
        self.plot.epochs = ()
        previous = self.trace_selector.currentData()
        self.trace_selector.blockSignals(True)
        self.trace_selector.clear()
        try:
            self.plot.epochs = motion_epochs(program, seed)
            references = {
                setting.linked_to
                for epoch in self.plot.epochs
                for setting in epoch.settings
                if isinstance(setting, TextureSettings) and setting.linked_to
            }
            choices = {}
            for epoch in self.plot.epochs:
                for setting in epoch.settings:
                    if isinstance(setting, TextureSettings) and setting.linked_to:
                        continue
                    unit = (
                        "mm/s"
                        if setting.kind == "arena"
                        or setting.space.kind == "physical_surface"
                        else "deg/s"
                    )
                    title = projector_name(setting)
                    if setting.instance_id in references:
                        title += " · reference"
                    choices[(setting.instance_id, unit)] = f"{title} · {unit}"
            labels = Counter(choices.values())
            occurrences: Counter[str] = Counter()
            for key, title in choices.items():
                occurrences[title] += 1
                if labels[title] > 1:
                    title += f" · source {occurrences[title]}"
                self.trace_selector.addItem(title, key)
            index = self.trace_selector.findData(previous)
            self.trace_selector.setCurrentIndex(max(0, index))
            self.plot.message = (
                "No moving stimulus in this trial." if not choices else ""
            )
        except (ValueError, TypeError, OverflowError) as error:
            self.plot.message = str(error)
        finally:
            self.trace_selector.blockSignals(False)
        self.trace_selector.setEnabled(self.trace_selector.count() > 1)
        self.epoch_strip.epochs = self.plot.epochs
        self.epoch_strip.update()
        self.refresh_trace()

    def refresh_trace(self) -> None:
        self.plot.traces = []
        selected = self.trace_selector.currentData()
        if selected is not None:
            instance, self.plot.unit = selected
            self.plot.message = ""
            try:
                for epoch in self.plot.epochs:
                    setting = next(
                        (s for s in epoch.settings if s.instance_id == instance), None
                    )
                    if isinstance(setting, TextureSettings) and setting.linked_to:
                        continue  # Only independently driven epochs belong to this source.
                    # Bounded display sampling; this is not a timing/peak diagnostic.
                    count = max(2, min(64, 4000 // max(1, len(self.plot.epochs))))
                    trace = []
                    for i in range(count + 1):
                        t = epoch.start + (epoch.end - epoch.start) * i / count
                        local_ns = max(
                            0,
                            min(
                                round((t - epoch.start) * 1e9),
                                round((epoch.end - epoch.start) * 1e9) - 1,
                            ),
                        )
                        trace.append(
                            (t, planned_speed(setting, local_ns) if setting else 0.0)
                        )
                    self.plot.traces.append(tuple(trace))
            except (ValueError, TypeError, OverflowError) as error:
                self.plot.traces = []
                self.plot.message = str(error)
        self.set_elapsed(self.plot.elapsed)

    def set_elapsed(self, elapsed: float | None) -> None:
        self.plot.elapsed = elapsed
        self.epoch_strip.elapsed = elapsed
        self.epoch_strip.update()
        self.plot.update()
        self.polar.direction = self.polar.angular_speed = None
        self.polar.message = "No stimulus"
        self.polar.rotation_message = ""
        selected = self.trace_selector.currentData()
        time = elapsed if elapsed is not None else 0.0
        epoch = next((e for e in self.plot.epochs if e.start <= time < e.end), None)
        if self.plot.epochs and time == self.plot.epochs[-1].end:
            epoch = self.plot.epochs[-1]
        if selected is not None and epoch is not None:
            setting = next(
                (s for s in epoch.settings if s.instance_id == selected[0]), None
            )
            if isinstance(setting, TextureSettings) and setting.linked_to:
                self.polar.message = "Linked to another source"
            elif setting is None:
                self.polar.angular_speed = 0.0
            else:
                local_ns = max(
                    0,
                    min(
                        round((time - epoch.start) * 1e9),
                        round((epoch.end - epoch.start) * 1e9) - 1,
                    ),
                )
                try:
                    x, y = planned_velocity(setting, local_ns)
                    self.polar.direction = (
                        degrees(atan2(y, x)) % 360 if hypot(x, y) else None
                    )
                    self.polar.message = ""
                except (ValueError, TypeError, OverflowError):
                    self.polar.message = "Direction unavailable"
                try:
                    self.polar.angular_speed = planned_rotation(setting, local_ns)
                except (ValueError, TypeError, OverflowError):
                    self.polar.rotation_message = "Rotation unavailable"
        self.polar.update()
