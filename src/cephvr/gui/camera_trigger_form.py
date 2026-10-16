"""Reflow the camera trigger controls without replacing their editors."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QGridLayout, QWidget

from cephvr.gui.theme import SIZES


class CameraTriggerForm(QWidget):
    def __init__(
        self, fields: tuple[QWidget, QWidget, QWidget], controls: tuple[QWidget, ...]
    ) -> None:
        super().__init__()
        self.fields = fields
        self.controls = controls
        self.stacked: bool | None = None
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(SIZES.field_x_gap)
        self.grid.setVerticalSpacing(SIZES.field_y_gap)
        for column in range(3):
            self.grid.setColumnStretch(column, 1)
        self.arrange(self.width())

    def arrange(self, width: int) -> None:
        minimums = tuple(control.minimumSizeHint().width() for control in self.controls)
        stacked = width < sum(minimums) + 2 * SIZES.field_x_gap
        if stacked == self.stacked:
            return
        self.stacked = stacked
        self.grid.setColumnMinimumWidth(0, 0 if stacked else minimums[0])
        for field_widget in self.fields:
            self.grid.removeWidget(field_widget)
        for field_widget, (row, column, span) in zip(
            self.fields,
            ((0, 0, 3), (1, 0, 2), (1, 2, 1))
            if stacked
            else ((0, 0, 1), (0, 1, 1), (0, 2, 1)),
            strict=True,
        ):
            self.grid.addWidget(
                field_widget, row, column, 1, span, Qt.AlignmentFlag.AlignBottom
            )

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self.arrange(self.width())
