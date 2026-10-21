"""Read-only stimulus epoch timeline with optional advanced motion instruments."""

from collections.abc import Callable
from time import monotonic

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

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
from cephvr.gui.preview_projector_cards import (
    InstrumentGrid,
    ProjectorCard,
    ProjectorHeading,
)
from cephvr.gui.theme import colors_for, retro_console
from cephvr.visual_stimulus.config.models.display_profile import Geometry
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


class StimulusTimeline(QWidget):
    cards_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        # Operator-hidden projector sections; names survive card rebuilds.
        self.hidden_projectors: set[str] = set()
        self.projector_cards: dict[str, QWidget] = {}
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(10)
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
        self.instrument_host = InstrumentGrid(
            (), QSize(MotionDial.SIZE + 16, MotionDial.HEIGHT + 34)
        )
        self.cards = self.instrument_host.grid
        self.notice = QLabel("", self.instrument_host)
        self.notice.setWordWrap(True)
        self.dial_area = QScrollArea()
        self.dial_area.setFrameShape(QFrame.Shape.NoFrame)
        self.dial_area.setWidgetResizable(True)
        self.dial_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.dial_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.dial_area.setWidget(self.instrument_host)
        # The instruments paint their own console surfaces over the card.
        self.dial_area.setStyleSheet(
            "QScrollArea, QScrollArea > QWidget > QWidget {background: transparent;}"
        )
        self.dial_area.setMinimumSize(160, 160)
        self.dial_area.setAccessibleName("Advanced motion previews")
        self.motion_section = QWidget()
        motion_layout = QVBoxLayout(self.motion_section)
        motion_layout.setContentsMargins(0, 0, 0, 0)
        motion_layout.setSpacing(4)
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
        self.glow = False
        self.headings: list[ProjectorHeading] = []
        self.sources: tuple[MotionSource, ...] = ()
        self.panels: list[SourcePanel] = []
        self.plan = InstrumentPlan(())
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
        self.epoch_timeline.epochs = self.size_lane.epochs = ()
        self.epoch_timeline.message = message
        self.reported_elapsed = None
        self.running = False
        self.rebuild_instruments()
        self.set_elapsed(None)

    def set_program(
        self, program: Program, seed: str, title: str, geometry: Geometry | None = None
    ) -> None:
        self.setToolTip(f"{title} · {NOT_MEASURED}")
        if (
            program is self.program
            and seed == self.seed
            and geometry == self.plan.geometry
        ):
            return
        self.clear("")
        self.program, self.seed = program, seed
        try:
            epochs = motion_epochs(program, seed)
            self.epoch_timeline.epochs = self.size_lane.epochs = epochs
            self.sources = motion_sources(epochs)
            self.plan = InstrumentPlan(epochs, geometry)
        except (ValueError, TypeError, OverflowError) as error:
            self.epoch_timeline.message = str(error)
        for index, source in enumerate(self.sources):
            color = COLORS[index % len(COLORS)]
            self.panels.append(self.plan.panel(source, color))
        self.rebuild_instruments()
        self.refresh()

    def rebuild_instruments(self) -> None:
        while self.cards.count():
            item = self.cards.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None and widget is not self.notice:
                widget.hide()
                widget.deleteLater()
        for card in self.projector_cards.values():  # hidden cards are not in the grid
            card.hide()
            card.deleteLater()
        self.projector_cards = {}
        self.dials, self.maps = [], []
        self.headings = []
        cards: list[tuple[str, ProjectorCard]] = []
        for panel in self.panels:
            instruments: list[QWidget] = []
            if panel.arena:
                world = WorldMap()
                self.maps.append(world)
                instruments.append(world)
            for _ in range(2 if panel.driving else 1):
                dial = MotionDial()
                self.dials.append(dial)
                instruments.append(dial)
            heading = ProjectorHeading(panel.source.name.removesuffix(" · reference"))
            heading.setStyleSheet(f"color: {getattr(colors_for(self), panel.color)};")
            self.headings.append(heading)
            cards.append((panel.source.key[0], ProjectorCard(heading, instruments)))
        order = {"Left": 0, "Front": 1, "Right": 2, "Bottom": 3}
        self.projector_cards = dict(
            sorted(cards, key=lambda item: order.get(item[0], 4))
        )
        self.place_projectors()
        self.restyle()
        self.cards_changed.emit()

    def place_projectors(self) -> None:
        """Grid only the shown projector sections so hidden ones free their space."""
        shown = [
            card
            for name, card in self.projector_cards.items()
            if name not in self.hidden_projectors
        ]
        for name, card in self.projector_cards.items():
            card.setVisible(name not in self.hidden_projectors)
        self.instrument_host.instruments = shown or [self.notice]
        self.instrument_host.columns = 0
        self.instrument_host.relayout()

    def projector_names(self) -> tuple[str, ...]:
        return tuple(self.projector_cards)

    def projector_visible(self, name: str) -> bool:
        return name not in self.hidden_projectors

    def set_projector_visible(self, name: str, visible: bool) -> None:
        if visible:
            self.hidden_projectors.discard(name)
        else:
            self.hidden_projectors.add(name)
        self.place_projectors()

    def restyle(self, glow: bool | None = None) -> None:
        """Re-apply Retro heading case and glow after a style or card rebuild."""
        if glow is not None:
            self.glow = glow
        retro = retro_console(self)
        for heading in self.headings:
            heading.restyle(retro, self.glow)

    def readout_lines(self, time: float) -> list[str]:
        index = current_epoch(self.epochs, time)
        lines = []
        for panel in self.panels:
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
        for panel in self.panels:
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
            widgets: list[QWidget] = []
            if panel.arena:
                world = next(maps)
                map_sample = self.plan.map_sample(panel, index, time)
                world.set_sample(map_sample)
                widgets.append(world)
                self.map_samples.append(map_sample)
            for driving in (False, True)[: 2 if panel.driving else 1]:
                dial = next(dials)
                dial_sample = self.plan.dial_sample(panel, index, time, driving)
                dial.set_sample(dial_sample)
                widgets.append(dial)
                self.dial_samples.append(dial_sample)
            for widget in widgets:
                widget.setVisible(True)
        if self.epoch_timeline.message:
            notice = ""
        elif not self.panels:
            notice = "No stimulus source in this trial."
        else:
            notice = ""
        self.notice.setText(notice)
        self.notice.setVisible(bool(notice))
