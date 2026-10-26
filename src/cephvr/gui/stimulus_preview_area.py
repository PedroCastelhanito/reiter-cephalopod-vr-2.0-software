"""Category-aware placement surfaces; native renderer windows own all pixels."""

from math import ceil

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import (
    QBoxLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import combo
from cephvr.gui.preview_frame import PreviewFrame
from cephvr.gui.preview_projector_cards import ProjectorCard
from cephvr.gui.preview_timeline import StimulusTimeline
from cephvr.gui.view import PreviewView
from cephvr.visual_stimulus.config.categories import CATEGORY_LABELS, suggested_category


class StimulusPreviewArea(QWidget):
    layout_changed = pyqtSignal()
    projectors_changed = pyqtSignal()
    snap_requested = pyqtSignal(str)

    def __init__(self, timeline: StimulusTimeline) -> None:
        super().__init__()
        self.timeline = timeline
        timeline.available_projectors = set()
        timeline.merge_directions = True
        self.projectors: tuple[str, ...] = ()
        self.frames: dict[str, PreviewFrame] = {}
        self.cells: list[QWidget] = []
        self.view: PreviewView | None = None
        self.allowed = False
        self.projection_visible = True
        self.body = QVBoxLayout(self)
        self.body.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.body.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        self.category = QLabel()
        self.mode = combo(("Combined", "Per-projector"))
        self.mode.setMinimumContentsLength(len("Per-projector"))
        self.mode.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.mode.setAccessibleName("Stimulus preview mode")
        header.addWidget(self.category)
        header.addStretch(1)
        header.addWidget(self.mode)
        self.body.addLayout(header)
        self.grid = QGridLayout()
        self.body.addLayout(self.grid, 1)
        self.mode.currentIndexChanged.connect(self.change_mode)
        timeline.cards_changed.connect(self.rebuild)
        timeline.instruments_changed.connect(self.update_instruments)
        self.rebuild()

    def change_mode(self) -> None:
        self.timeline.combined = self.mode.currentIndex() == 0
        self.timeline.rebuild_instruments()
        self.timeline.refresh()

    def set_projectors(self, names: tuple[str, ...]) -> None:
        order = {
            name: index
            for index, name in enumerate(("Left", "Front", "Right", "Bottom"))
        }
        names = tuple(sorted(names, key=lambda name: order[name]))
        if names != self.projectors:
            self.projectors = names
            self.timeline.available_projectors = set(names)
            self.timeline.refresh()
            self.rebuild()
            self.projectors_changed.emit()

    def rebuild(self) -> None:
        # Return borrowed instruments before disposing of the previous layout cells.
        for card in self.timeline.projector_cards.values():
            card.setParent(self.timeline.instrument_host)
        self.timeline.motion_section.setParent(self)
        while self.grid.count():
            self.grid.takeAt(0)
        previous = dict(zip(self.frames, self.cells, strict=True))
        previous_frames = self.frames
        self.cells = []
        self.frames = {}
        program = self.timeline.program
        category = (
            (program.category or suggested_category(program)) if program else None
        )
        self.category.setText(CATEGORY_LABELS[category] if category else "Stimulus")
        navigation = category == "navigation_3d"
        if navigation:
            self.mode.blockSignals(True)
            self.mode.setCurrentIndex(0)
            self.mode.blockSignals(False)
            self.timeline.combined = True
        self.mode.setVisible(not navigation)
        individual = self.mode.currentIndex() == 1 and not navigation
        if individual:
            self.timeline.motion_section.hide()
        selected = tuple(
            name for name in self.projectors if self.timeline.projector_visible(name)
        )
        names = selected if individual else ("",) if selected else ()
        for name, old_cell in previous.items():
            if name not in names:
                old_cell.hide()
                old_cell.deleteLater()
        for name in names:
            cell = previous.get(name)
            if cell is None:
                cell = QWidget()
                layout = QHBoxLayout(cell)
                layout.setContentsMargins(0, 0, 0, 0)
                frame = PreviewFrame(decorated=False)
                frame.setMinimumWidth(160)
                frame.snap_button.clicked.connect(
                    lambda: self.snap_requested.emit("stimulus")
                )
                layout.addWidget(frame)
            else:
                existing_layout = cell.layout()
                assert isinstance(existing_layout, QHBoxLayout)
                layout = existing_layout
                frame = previous_frames[name]
            frame.metrics.setToolTip(
                "Source and representative viewer rates for the stimulus preview group. "
                "— means hidden, stale or not yet measured."
            )
            frame.caption.setText(name or "Rig preview")
            if not individual:
                frame.target.setToolTip("Drag to rotate · Double-click to reset view")
            frame.status.setText("Available after Setup")
            frame.status.show()
            layout.setStretchFactor(frame, 3 if individual else 2 if navigation else 1)
            self.frames[name] = frame
            frame.setVisible(self.projection_visible)
            if individual:
                instrument = self.timeline.projector_cards.get(name)
                if instrument is not None:
                    layout.addWidget(instrument, 2)
                    instrument.setVisible(
                        self.timeline.advanced and category != "media_presentation"
                    )
            else:
                self.timeline.place_projectors()
                layout.addWidget(self.timeline.motion_section, 1)
                self.timeline.motion_section.setVisible(
                    self.timeline.advanced and category != "media_presentation"
                )
            self.cells.append(cell)
        self.relayout_cells()
        self.layout_changed.emit()
        self.update_instruments()
        self.apply_view(self.view, self.allowed)

    def relayout_cells(self) -> None:
        individual = self.mode.currentIndex() == 1
        header = self.body.itemAt(0)
        height = max(
            1,
            self.height()
            - (header.sizeHint().height() if header else 0)
            - self.body.spacing(),
        )
        frame_height = max(
            (frame.minimumHeight() for frame in self.frames.values()), default=192
        )
        plots = any(
            not card.isHidden() for card in self.timeline.projector_cards.values()
        )

        def fit(candidate: tuple[int, bool]) -> float:
            columns, stacked = candidate
            rows = ceil(len(self.cells) / columns)
            width = (
                self.width() - (columns - 1) * self.grid.horizontalSpacing()
            ) / columns
            row_height = (height - (rows - 1) * self.grid.verticalSpacing()) / rows
            # Reserve space for the plot as well as the image heading and FPS footer.
            plot_space = 126 if plots else 0
            return min(
                width / (160 + (0 if stacked else plot_space)),
                row_height / (frame_height + (plot_space if stacked else 0)),
            )

        columns, compact = (
            max(
                (
                    (count, stacked)
                    for count in range(1, len(self.cells) + 1)
                    for stacked in (False, True)
                ),
                key=fit,
            )
            if individual and self.cells
            else (1, False)
        )
        while self.grid.count():
            self.grid.takeAt(0)
        for i in range(max(self.grid.rowCount(), self.grid.columnCount())):
            self.grid.setRowStretch(i, 0)
            self.grid.setColumnStretch(i, 0)
        for index, cell in enumerate(self.cells):
            layout = cell.layout()
            assert isinstance(layout, QBoxLayout)
            layout.setDirection(
                QBoxLayout.Direction.TopToBottom
                if compact
                else QBoxLayout.Direction.LeftToRight
            )
            row, column = divmod(index, max(1, columns))
            self.grid.addWidget(cell, row, column)
            self.grid.setRowStretch(row, 1)
            self.grid.setColumnStretch(column, 1)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self.relayout_cells()

    def set_projection_visible(self, visible: bool) -> None:
        """The Stimulus selection governs every frame in the current preview mode."""
        if visible == self.projection_visible:
            return
        self.projection_visible = visible
        for frame in self.frames.values():
            frame.setVisible(visible)
        self.update_instruments()
        self.relayout_cells()
        self.layout_changed.emit()

    def update_instruments(self) -> None:
        timeline = self.timeline
        enabled = timeline.advanced and self.category.text() != "Media presentation"
        timeline.motion_section.setVisible(
            enabled
            and bool(self.cells)
            and self.mode.currentIndex() == 0
            and bool(timeline.active_sources)
        )
        for name, card in timeline.projector_cards.items():
            if isinstance(card, ProjectorCard):
                card.set_heading_visible(
                    self.mode.currentIndex() != 1 or not self.projection_visible
                )
            card.setVisible(
                enabled
                and bool(self.cells)
                and timeline.projector_available(name)
                and name in timeline.active_sources
                and name not in timeline.hidden_projectors
                and name not in timeline.shared_faces
            )
        for cell in self.cells:
            cell.setVisible(self.projection_visible or enabled)
        self.relayout_cells()

    def apply_view(self, view: PreviewView | None, allowed: bool) -> None:
        self.view, self.allowed = view, allowed
        for frame in self.frames.values():
            frame.status.setVisible(view is None or not view.visible)
            frame.status.setText(
                view.reason if view and view.reason else "Show stimulus preview"
            )
            frame.snap_button.setEnabled(allowed and bool(view and view.visible))
            frame.snap_button.setVisible(bool(view and view.visible))
            frame.set_metrics(view)
