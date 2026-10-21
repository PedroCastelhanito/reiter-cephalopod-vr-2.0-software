"""Read-only stimulus epoch timeline with optional advanced motion instruments."""

from collections.abc import Callable
from time import monotonic

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import Card
from cephvr.gui.preview_motion_data import (
    DialSample,
    MotionEpoch,
    MotionSource,
    MotionTrace,
    motion_epochs,
    motion_sources,
    planned_size,
)
from cephvr.gui.preview_motion_dial import (
    MapSample,
    MotionDial,
    WorldMap,
    rotation_text,
    vector_text,
)
from cephvr.gui.preview_motion_plot import (
    PLOT_LEFT,
    EpochTimeline,
    TraceLane,
    current_epoch,
    time_window,
)
from cephvr.gui.preview_motion_samples import InstrumentPlan, SourcePanel
from cephvr.gui.theme import colors_for
from cephvr.visual_stimulus.config.models.program_model import (
    Program,
    Settings,
)

COLORS = ("accent", "projection", "footprint", "mirror", "coral", "ready")
NOT_MEASURED = (
    "Planned motion; feedback and actual display timing are not measured here."
)


class ConsolePanel(QWidget):
    """One console surface behind the epoch timeline and size lane."""

    def paintEvent(self, event: QPaintEvent | None) -> None:
        QPainter(self).fillRect(self.rect(), QColor(colors_for(self).console))


def sampled(
    value: Callable[[int], float],
    epoch: MotionEpoch,
    left: float,
    right: float,
) -> tuple[tuple[float, float], ...]:
    """Sample one epoch's planned value at 5 Hz, including both endpoints."""
    count = max(1, round((right - left) * 5))
    trace = []
    for i in range(count + 1):
        t = right if i == count else left + (right - left) * i / count
        trace.append((t, value(epoch.local_ns(t))))
    return tuple(trace)


def size_at(setting: Settings, axis: int) -> Callable[[int], float]:
    return lambda local_ns: planned_size(setting, local_ns)[axis]


class StimulusTimeline(Card):
    def __init__(self) -> None:
        super().__init__("Stimulus timeline", compact=True)
        self.legend = QGridLayout()
        self.legend.setHorizontalSpacing(24)
        self.legend.setVerticalSpacing(4)
        self.setToolTip(NOT_MEASURED)
        self.epoch_timeline = EpochTimeline()
        self.epoch_timeline.setToolTip(
            f"{NOT_MEASURED} Hover for planned values; click to inspect an instant."
        )
        self.epoch_label = QLabel("")
        self.epoch_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.epoch_label.setAccessibleName("Current epoch")
        self.size_lane = TraceLane("Size")
        console = ConsolePanel()
        console_layout = QVBoxLayout(console)
        console_layout.setContentsMargins(0, 6, 0, 6)
        console_layout.setSpacing(2)
        # Only the epoch readout belongs to the timeline header.
        legend_row = QHBoxLayout()
        legend_row.setContentsMargins(PLOT_LEFT, 0, 24, 4)
        legend_row.addStretch(1)
        legend_row.addWidget(self.epoch_label)
        console_layout.addLayout(legend_row)
        console_layout.addWidget(self.epoch_timeline)
        console_layout.addWidget(self.size_lane)
        console_layout.addStretch(1)
        self.instrument_host = QWidget()
        self.instruments = QHBoxLayout(self.instrument_host)
        self.instruments.setContentsMargins(0, 0, 0, 0)
        self.instruments.setSpacing(12)
        self.notice = QLabel("", self.instrument_host)
        self.notice.setWordWrap(True)
        self.dial_area = QScrollArea()
        self.dial_area.setFrameShape(QFrame.Shape.NoFrame)
        self.dial_area.setWidgetResizable(True)
        self.dial_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.dial_area.setWidget(self.instrument_host)
        # The instruments paint their own console surfaces over the card.
        self.dial_area.setStyleSheet(
            "QScrollArea, QScrollArea > QWidget > QWidget {background: transparent;}"
        )
        self.instruments.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.dial_area.setMinimumHeight(MotionDial.HEIGHT + 18)
        self.dial_area.setAccessibleName("Advanced motion previews")
        self.motion_section = QWidget()
        motion_layout = QVBoxLayout(self.motion_section)
        motion_layout.setContentsMargins(0, 0, 0, 0)
        motion_layout.setSpacing(4)
        motion_layout.addLayout(self.legend)
        motion_layout.addWidget(self.dial_area)
        plots = QHBoxLayout()
        plots.setSpacing(20)
        plots.addWidget(console, 1)
        plots.addWidget(self.motion_section, 0)
        self.plots = plots
        self.body.addLayout(plots, 1)
        self.program: Program | None = None
        self.seed = ""
        self.advanced = False
        self.sources: tuple[MotionSource, ...] = ()
        self.panels: list[SourcePanel] = []
        self.plan = InstrumentPlan(())
        self.toggles: dict[tuple[str, str, int], QCheckBox] = {}
        self.dials: list[MotionDial] = []
        self.maps: list[WorldMap] = []
        self.dial_samples: list[DialSample] = []
        self.map_samples: list[MapSample] = []
        self.epoch_timeline.time_selected.connect(self.set_elapsed)
        self.size_lane.time_selected.connect(self.set_elapsed)
        self.epoch_timeline.readout_lines = self.size_lane.readout_lines = (
            self.readout_lines
        )
        self.reported_elapsed: float | None = None
        self.reported_at = monotonic()
        self.running = False
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.refresh_clock)
        self.timer.start()
        self.set_advanced(False)

    @property
    def epochs(self) -> tuple[MotionEpoch, ...]:
        return self.epoch_timeline.epochs

    @property
    def elapsed(self) -> float | None:
        return self.epoch_timeline.elapsed

    def set_stacked(self, stacked: bool) -> None:
        """Put the instruments under the timeline when the card is a narrow column."""
        self.plots.setDirection(
            QBoxLayout.Direction.TopToBottom
            if stacked
            else QBoxLayout.Direction.LeftToRight
        )
        self.plots.setAlignment(
            self.motion_section,
            Qt.AlignmentFlag.AlignLeft if stacked else Qt.AlignmentFlag(0),
        )

    def set_advanced(self, advanced: bool) -> None:
        """Show or hide every dial, map and size lane without changing the plan."""
        self.advanced = advanced
        self.motion_section.setVisible(advanced)
        self.dial_area.setVisible(advanced)
        self.refresh()
        # The card takes only its content height, so shrink back immediately.
        layout = self.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
        self.updateGeometry()

    def set_playback(self, elapsed: float | None, *, running: bool) -> None:
        self.reported_elapsed = elapsed
        self.reported_at = monotonic()
        self.running = running
        if not running or self.elapsed is None:
            self.set_elapsed(elapsed)

    def refresh_clock(self) -> None:
        if not self.isVisible():
            return
        elapsed = self.reported_elapsed
        if elapsed is not None and self.running:
            elapsed += monotonic() - self.reported_at
            if self.epochs:
                elapsed = min(elapsed, self.epochs[-1].end)
        self.set_elapsed(elapsed)

    def clear(self, message: str) -> None:
        self.program = None
        self.sources = ()
        self.panels = []
        self.plan = InstrumentPlan(())
        self.reset_legend()
        self.epoch_timeline.epochs = self.size_lane.epochs = ()
        self.epoch_timeline.message = message
        self.reported_elapsed = None
        self.running = False
        self.rebuild_instruments()
        self.set_elapsed(None)

    def reset_legend(self) -> None:
        for toggle in self.toggles.values():
            self.legend.removeWidget(toggle)
            toggle.hide()
            toggle.deleteLater()
        self.toggles.clear()

    def set_program(self, program: Program, seed: str, title: str) -> None:
        self.setToolTip(f"{title} · {NOT_MEASURED}")
        if program is self.program and seed == self.seed:
            return
        previous = {key: toggle.isChecked() for key, toggle in self.toggles.items()}
        self.clear("")
        self.program, self.seed = program, seed
        try:
            epochs = motion_epochs(program, seed)
            self.epoch_timeline.epochs = self.size_lane.epochs = epochs
            self.sources = motion_sources(epochs)
            self.plan = InstrumentPlan(epochs)
        except (ValueError, TypeError, OverflowError) as error:
            self.epoch_timeline.message = str(error)
        for index, source in enumerate(self.sources):
            color = COLORS[index % len(COLORS)]
            self.panels.append(self.plan.panel(source, color))
            toggle = QCheckBox(source.name)
            toggle.setChecked(previous.get(source.key, True))
            toggle.setAccessibleName(f"Show {source.name} motion")
            toggle.setToolTip(f"Show or hide {source.name} in every preview")
            toggle.toggled.connect(self.refresh)
            css = getattr(colors_for(self), color)
            toggle.setStyleSheet(
                f"QCheckBox {{color: {css};}}"
                f"QCheckBox::indicator {{border: 1px solid {css};}}"
                f"QCheckBox::indicator:checked {{background-color: {css};}}"
                "QCheckBox::indicator:unchecked {background-color: transparent;}"
            )
            self.legend.addWidget(toggle, index // 2, index % 2)
            self.toggles[source.key] = toggle
        self.rebuild_instruments()
        self.refresh()

    def rebuild_instruments(self) -> None:
        while self.instruments.count():
            item = self.instruments.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None and widget is not self.notice:
                widget.deleteLater()
        self.dials, self.maps = [], []
        self.instruments.addWidget(self.notice)
        for panel in self.panels:
            if panel.arena:
                world = WorldMap()
                self.maps.append(world)
                self.instruments.addWidget(world)
            for _ in range(2 if panel.driving else 1):
                dial = MotionDial()
                self.dials.append(dial)
                self.instruments.addWidget(dial)
        self.instruments.addStretch(1)
        # Fixed-size instruments never overlap: up to two fit, more scroll sideways.
        count = len(self.dials) + len(self.maps)
        natural = count * (MotionDial.SIZE + self.instruments.spacing())
        self.instrument_host.setMinimumWidth(natural)
        self.dial_area.setFixedWidth(
            max(240, min(natural, 2 * (MotionDial.SIZE + self.instruments.spacing())))
        )

    def visible_panels(self) -> list[SourcePanel]:
        return [p for p in self.panels if self.toggles[p.source.key].isChecked()]

    def readout_lines(self, time: float) -> list[str]:
        index = current_epoch(self.epochs, time)
        lines = []
        for panel in self.visible_panels():
            sample = self.plan.dial_sample(panel, index, time)
            lines.append(
                f"{sample.name}: {vector_text(sample)} · {rotation_text(sample)}"
            )
        return lines

    def set_elapsed(self, elapsed: float | None) -> None:
        self.epoch_timeline.elapsed = self.size_lane.elapsed = elapsed
        self.refresh()

    def refresh(self) -> None:
        epochs = self.epochs
        time = self.elapsed if self.elapsed is not None else 0.0
        index = current_epoch(epochs, self.elapsed)
        self.epoch_label.setText(
            f"Epoch {index + 1 if index is not None else '—'} / {len(epochs)}"
            if epochs
            else ""
        )
        self.refresh_size(index is not None)
        self.refresh_instruments(index, time)
        self.epoch_timeline.right_margin = (
            self.size_lane.lane_margin if self.size_lane.isVisibleTo(self) else 24
        )
        self.size_lane.right_margin = self.epoch_timeline.right_margin
        self.epoch_timeline.update()
        self.size_lane.update()

    def refresh_size(self, active: bool) -> None:
        lane = self.size_lane
        lane.traces = []
        elapsed = self.elapsed or 0.0
        start, end = time_window(elapsed)
        for panel in self.visible_panels():
            unit = "mm" if panel.source.unit == "mm/s" else "deg"
            for axis in (0, 1):
                if not panel.size[axis]:
                    continue
                label = panel.source.name + ("" if axis == 0 else " · height")
                segments, planned = [], []
                try:
                    for epoch, setting in zip(
                        self.epochs, panel.source.settings, strict=True
                    ):
                        if setting is None or setting.kind == "arena":
                            continue
                        bound = size_at(setting, axis)
                        left, right = max(start, epoch.start), min(elapsed, epoch.end)
                        if not (right < left or (left == epoch.end and left < elapsed)):
                            segments.append(sampled(bound, epoch, left, right))
                        # The remaining plan continues from current time to window end.
                        left, right = max(elapsed, epoch.start), min(end, epoch.end)
                        if left < right:
                            planned.append(sampled(bound, epoch, left, right))
                except (ValueError, TypeError, OverflowError):
                    continue
                lane.traces.append(
                    MotionTrace(
                        label, unit, panel.color, tuple(segments), tuple(planned)
                    )
                )
        lane.setVisible(self.advanced and bool(lane.traces))

    def refresh_instruments(self, index: int | None, time: float) -> None:
        self.dial_samples, self.map_samples = [], []
        dials, maps = iter(self.dials), iter(self.maps)
        for panel in self.panels:
            shown = self.toggles[panel.source.key].isChecked()
            widgets: list[QWidget] = []
            if panel.arena:
                world = next(maps)
                map_sample = self.plan.map_sample(panel, index, time)
                world.set_sample(map_sample)
                widgets.append(world)
                if shown:
                    self.map_samples.append(map_sample)
            for driving in (False, True)[: 2 if panel.driving else 1]:
                dial = next(dials)
                dial_sample = self.plan.dial_sample(panel, index, time, driving)
                dial.set_sample(dial_sample)
                widgets.append(dial)
                if shown:
                    self.dial_samples.append(dial_sample)
            for widget in widgets:
                widget.setVisible(shown)
        if self.epoch_timeline.message:
            notice = ""
        elif not self.panels:
            notice = "No independent stimulus source in this trial."
        elif not self.dial_samples and not self.map_samples:
            notice = "Select a source in the legend."
        else:
            notice = ""
        self.notice.setText(notice)
        self.notice.setVisible(bool(notice))
