"""Shared camera-style tables with optional persistent form controls."""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QWidget,
)

from cephvr.gui.components import ActionHeader, button
from cephvr.gui.icons import device_icon
from cephvr.gui.theme import SIZES


def refresh_button(hint: str) -> QPushButton:
    control = button("", "icon", hint=hint)
    control.setAccessibleName(hint)
    control.setIcon(device_icon("refresh"))
    control.setIconSize(QSize(16, 16))
    control.setFixedSize(26, 26)
    return control


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

    def add_refresh_action(self, hint: str) -> QPushButton:
        """Use one inventory header/selection pattern; the last column holds Refresh."""
        control = refresh_button(hint)
        self.setHorizontalHeader(ActionHeader(control))
        header = self.horizontalHeader()
        assert header is not None
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        header.setSectionResizeMode(
            self.columnCount() - 1, QHeaderView.ResizeMode.Fixed
        )
        header.resizeSection(self.columnCount() - 1, 36)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        return control

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

    def fit_rows(
        self, *, hide_empty_header: bool = False, extra_height: int = 0
    ) -> None:
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
        if hide_empty_header:
            header.setVisible(
                any(not self.isRowHidden(row) for row in range(self.rowCount()))
            )
        self.setFixedHeight(
            (0 if header.isHidden() else header.sizeHint().height())
            + sum(
                self.rowHeight(row)
                for row in range(self.rowCount())
                if not self.isRowHidden(row)
            )
            + 2 * self.frameWidth()
            + extra_height
        )
