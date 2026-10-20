"""Read-only shared stimulus plots and per-projector legend toggles."""

from math import atan2, degrees, hypot
from time import monotonic

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from cephvr.gui.components import Card, label
from cephvr.gui.preview_motion_data import (
    MotionSource,
    MotionTrace,
    PolarSample,
    motion_epochs,
    motion_sources,
    planned_rotation,
    planned_speed,
    planned_velocity,
)
from cephvr.gui.preview_motion_plot import (
    EpochStrip,
    MotionPlot,
    PolarMotionPlot,
    time_window,
)
from cephvr.gui.theme import colors_for
from cephvr.visual_stimulus.config.models.program_model import Program, TextureSettings

COLORS = ("accent", "projection", "footprint", "mirror", "coral", "ready")


class StimulusTimeline(Card):
    def __init__(self) -> None:
        super().__init__("Stimulus timeline", compact=True, grow=True)
        row = QHBoxLayout()
        self.context = label("Planned motion · not measured output", "muted", wrap=True)
        row.addWidget(self.context, 1)
        row.addWidget(label("30 s window", "muted"))
        self.legend = QGridLayout()
        self.legend.setHorizontalSpacing(24)
        self.legend.setVerticalSpacing(4)
        self.body.addLayout(row)
        self.plot = MotionPlot()
        self.plot.setToolTip(
            "Sampled planned speed; feedback and actual display timing are not measured here. Toggle colored sources in the legend."
        )
        self.epoch_strip = EpochStrip()
        speed = QWidget()
        speed_layout = QVBoxLayout(speed)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(2)
        legend_row = QHBoxLayout()
        legend_row.setContentsMargins(64, 0, 0, 6)
        legend_row.addLayout(self.legend)
        legend_row.addStretch(1)
        speed_layout.addLayout(legend_row)
        speed_layout.addWidget(self.epoch_strip)
        speed_layout.addWidget(self.plot, 1)
        self.polar = PolarMotionPlot()
        plots = QHBoxLayout()
        plots.setSpacing(20)
        plots.addWidget(speed, 3)
        plots.addWidget(self.polar, 1)
        self.body.addLayout(plots, 1)
        self.program: Program | None = None
        self.seed = ""
        self.sources: tuple[MotionSource, ...] = ()
        self.toggles: dict[tuple[str, str, int], QCheckBox] = {}
        self.plot.time_selected.connect(self.set_elapsed)
        self.reported_elapsed: float | None = None
        self.reported_at = monotonic()
        self.running = False
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.refresh_clock)
        self.timer.start()

    def set_playback(self, elapsed: float | None, *, running: bool) -> None:
        self.reported_elapsed = elapsed
        self.reported_at = monotonic()
        self.running = running
        if not running or self.plot.elapsed is None:
            self.set_elapsed(elapsed)

    def refresh_clock(self) -> None:
        if not self.isVisible():
            return
        elapsed = self.reported_elapsed
        if elapsed is not None and self.running:
            elapsed += monotonic() - self.reported_at
            if self.plot.epochs:
                elapsed = min(elapsed, self.plot.epochs[-1].end)
        self.set_elapsed(elapsed)

    def clear(self, message: str) -> None:
        self.program = None
        self.sources = ()
        self.reset_legend()
        self.plot.epochs = self.epoch_strip.epochs = ()
        self.plot.traces = []
        self.plot.message = message
        self.reported_elapsed = None
        self.running = False
        self.set_elapsed(None)

    def reset_legend(self) -> None:
        for toggle in self.toggles.values():
            self.legend.removeWidget(toggle)
            toggle.hide()
            toggle.deleteLater()
        self.toggles.clear()

    def set_program(self, program: Program, seed: str, title: str) -> None:
        self.context.setText(f"{title} · planned motion · not measured output")
        if program is self.program and seed == self.seed:
            return
        previous = {key: toggle.isChecked() for key, toggle in self.toggles.items()}
        self.clear("")
        self.program, self.seed = program, seed
        try:
            self.plot.epochs = motion_epochs(program, seed)
            self.sources = motion_sources(self.plot.epochs)
            for index, source in enumerate(self.sources):
                toggle = QCheckBox(f"{source.name} · {source.unit}")
                toggle.setChecked(previous.get(source.key, True))
                toggle.setAccessibleName(f"Show {source.name} motion")
                toggle.toggled.connect(self.refresh_trace)
                self.legend.addWidget(toggle, index // 2, index % 2)
                self.toggles[source.key] = toggle
            self.plot.message = (
                "" if self.sources else "No independent stimulus source in this trial."
            )
        except (ValueError, TypeError, OverflowError) as error:
            self.plot.message = str(error)
        self.epoch_strip.epochs = self.plot.epochs
        self.refresh_trace()

    def refresh_trace(self) -> None:
        self.plot.traces = []
        if self.sources:
            self.plot.message = ""
        errors = []
        elapsed = self.plot.elapsed or 0.0
        start, _ = time_window(elapsed)
        for index, source in enumerate(self.sources):
            toggle = self.toggles[source.key]
            toggle.setText(f"{source.name} · {source.unit}")
            color = COLORS[index % len(COLORS)]
            if not toggle.isChecked():
                continue
            segments = []
            try:
                for epoch, setting in zip(
                    self.plot.epochs, source.settings, strict=True
                ):
                    if isinstance(setting, TextureSettings) and setting.linked_to:
                        continue
                    left, right = max(0.0, start, epoch.start), min(elapsed, epoch.end)
                    if right < left or (left == epoch.end and left < elapsed):
                        continue
                    count = max(1, round((right - left) * 5))
                    trace = []
                    for i in range(count + 1):
                        t = right if i == count else left + (right - left) * i / count
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
                    segments.append(tuple(trace))
                self.plot.traces.append(
                    MotionTrace(source.name, source.unit, color, tuple(segments))
                )
                toggle.setToolTip(f"Show or hide {source.name} in both plots")
            except (ValueError, TypeError, OverflowError) as error:
                errors.append(f"{source.name}: {error}")
                toggle.setText(f"{source.name} · unavailable")
                toggle.setToolTip(str(error))
        self.plot.errors = errors
        if self.sources and not self.plot.traces:
            self.plot.message = (
                "\n".join(errors) if errors else "Select a source in the legend."
            )
        self.epoch_strip.update()
        self.plot.update()
        self.refresh_polar()

    def set_elapsed(self, elapsed: float | None) -> None:
        self.plot.elapsed = self.epoch_strip.elapsed = elapsed
        self.refresh_trace()

    def refresh_polar(self) -> None:
        self.polar.samples = []
        elapsed = self.plot.elapsed
        time = elapsed if elapsed is not None else 0.0
        epoch_index = next(
            (i for i, e in enumerate(self.plot.epochs) if e.start <= time < e.end), None
        )
        if self.plot.epochs and time == self.plot.epochs[-1].end:
            epoch_index = len(self.plot.epochs) - 1
        for index, source in enumerate(self.sources):
            color = getattr(colors_for(self), COLORS[index % len(COLORS)])
            self.toggles[source.key].setStyleSheet(
                f"QCheckBox {{color: {color};}}"
                f"QCheckBox::indicator {{border: 1px solid {color};}}"
                f"QCheckBox::indicator:checked {{background-color: {color};}}"
                "QCheckBox::indicator:unchecked {background-color: transparent;}"
            )
            if not self.toggles[source.key].isChecked():
                continue
            direction = angular_speed = None
            message = "No stimulus"
            if epoch_index is not None:
                epoch = self.plot.epochs[epoch_index]
                setting = source.settings[epoch_index]
                if isinstance(setting, TextureSettings) and setting.linked_to:
                    continue
                if setting is None:
                    angular_speed = 0.0
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
                        direction = degrees(atan2(y, x)) % 360 if hypot(x, y) else None
                        message = "" if direction is not None else "No translation"
                    except (ValueError, TypeError, OverflowError):
                        message = "Direction unavailable"
                    try:
                        angular_speed = planned_rotation(setting, local_ns)
                    except (ValueError, TypeError, OverflowError):
                        pass
            self.polar.samples.append(
                PolarSample(
                    source.name,
                    COLORS[index % len(COLORS)],
                    direction,
                    angular_speed,
                    message,
                )
            )
        self.polar.update()
