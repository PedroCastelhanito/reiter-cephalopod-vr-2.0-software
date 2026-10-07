"""Shared camera-style tables with optional persistent form controls."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QTableWidget,
    QWidget,
)

from cephvr.gui.theme import SIZES


class DataTable(QTableWidget):
    def __init__(self, rows: int, columns: int) -> None:
        super().__init__(rows, columns)
        self.setShowGrid(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        vertical, header = self.verticalHeader(), self.horizontalHeader()
        assert vertical is not None and header is not None
        vertical.hide()
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def set_control(self, row: int, column: int, control: QWidget) -> None:
        host = QWidget()
        layout = QHBoxLayout(host)
        # The shared item style already insets persistent cell widgets.
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(control)
        self.setCellWidget(row, column, host)

    def sizeHintForColumn(self, column: int) -> int:
        return max(
            super().sizeHintForColumn(column),
            0,
            *(
                control.sizeHint().width() + 2 * SIZES.table_cell_padding
                for row in range(self.rowCount())
                if (control := self.cellWidget(row, column)) is not None
            ),
        )

    def fit_rows(self) -> None:
        # Persistent editors need their styled height plus the item insets.
        self.ensurePolished()
        for child in self.findChildren(QWidget):
            child.ensurePolished()
        self.resizeRowsToContents()
        for row in range(self.rowCount()):
            height = self.rowHeight(row)
            for column in range(self.columnCount()):
                control = self.cellWidget(row, column)
                if control is not None:
                    height = max(height, control.sizeHint().height() + 12)
            self.setRowHeight(row, height)
        header = self.horizontalHeader()
        assert header is not None
        self.setFixedHeight(
            header.sizeHint().height()
            + sum(
                self.rowHeight(row)
                for row in range(self.rowCount())
                if not self.isRowHidden(row)
            )
            + 2 * self.frameWidth()
        )
