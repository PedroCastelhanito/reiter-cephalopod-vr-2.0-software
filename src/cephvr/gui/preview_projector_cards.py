"""Per-projector cards that hold the advanced preview instruments."""

from collections.abc import Iterable
from math import ceil

from PyQt6.QtCore import QRectF, QSize
from PyQt6.QtGui import QPainter, QPaintEvent, QResizeEvent
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.preview_motion_dial import MotionDial
from cephvr.gui.retro_instruments import double_frame
from cephvr.gui.retro_overlay import set_glow
from cephvr.gui.theme import retro_console

SPACING = 16


class InstrumentGrid(QWidget):
    """Fit all cells, choosing the columns that maximize their uniform scale."""

    def __init__(
        self, instruments: Iterable[QWidget], cell_size: QSize | None = None
    ) -> None:
        super().__init__()
        self.instruments = list(instruments)
        self.cell_size = cell_size or QSize(MotionDial.SIZE, MotionDial.HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.columns = 0
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(SPACING)
        self.grid.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        for widget in self.instruments:
            widget.setParent(self)
        self.relayout()

    def relayout(self) -> None:
        count = max(1, len(self.instruments))

        def scale(columns: int) -> float:
            rows = ceil(count / columns)
            return min(
                (self.width() - SPACING * (columns - 1))
                / columns
                / self.cell_size.width(),
                (self.height() - SPACING * (rows - 1)) / rows / self.cell_size.height(),
            )

        columns = max(range(1, count + 1), key=scale)
        if columns == self.columns and self.grid.count() == len(self.instruments):
            return
        self.columns = columns
        while self.grid.count():
            self.grid.takeAt(0)
        for index in range(max(self.grid.rowCount(), self.grid.columnCount())):
            self.grid.setRowStretch(index, 0)
            self.grid.setColumnStretch(index, 0)
        for index, widget in enumerate(self.instruments):
            row, column = divmod(index, columns)
            self.grid.addWidget(widget, row, column)
            self.grid.setRowStretch(row, 1)
            self.grid.setColumnStretch(column, 1)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 0)

    def sizeHint(self) -> QSize:
        return self.cell_size

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self.relayout()


class ProjectorHeading(QLabel):
    """Projector name; Retro shows it uppercase while the source name is unchanged."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name_text = name

    def restyle(self, retro: bool, glow: bool) -> None:
        self.setText(self.name_text.upper() if retro else self.name_text)
        set_glow(self, retro and glow)


class ProjectorCard(QFrame):
    """One projector's heading and centered instruments."""

    def __init__(
        self,
        header: QWidget,
        instruments: Iterable[QWidget] = (),
    ) -> None:
        super().__init__()
        self.setObjectName("ProjectorCard")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(4)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(header)
        row.addStretch(1)
        layout.addLayout(row)
        self.grid: InstrumentGrid | None = None
        instruments = list(instruments)
        if instruments:
            self.grid = InstrumentGrid(instruments)
            layout.addWidget(self.grid, 1)

    def paintEvent(self, event: QPaintEvent | None) -> None:
        super().paintEvent(event)
        if retro_console(self):
            # The QSS border is the outer line; add the Retro card's inner line/marks.
            painter = QPainter(self)
            double_frame(
                painter,
                QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                self,
            )
