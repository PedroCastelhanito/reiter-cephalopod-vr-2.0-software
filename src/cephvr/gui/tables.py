"""Shared camera-style tables with optional persistent form controls."""

from PyQt6.QtCore import QEvent, QSize, Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QColor, QPainter, QPaintEvent
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
from cephvr.gui.table_header import TableHeader
from cephvr.gui.theme import SIZES, colors_for


def refresh_button(hint: str) -> QPushButton:
    control = button("", "icon", hint=hint)
    control.setAccessibleName(hint)
    control.setIcon(device_icon("refresh"))
    # The appearance recolours named icons to the active palette.
    control.setProperty("iconName", "refresh")
    control.setIconSize(QSize(16, 16))
    control.setFixedSize(26, 26)
    return control


class DataTable(QTableWidget):
    def __init__(self, rows: int, columns: int) -> None:
        super().__init__(rows, columns)
        self._hide_empty_header = False
        self.empty_text = ""
        self._extra_height = 0
        self.fit_timer = QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.timeout.connect(self.fit_rows)
        self.use_header(TableHeader(Qt.Orientation.Horizontal))
        self.setShowGrid(False)
        self.setTabKeyNavigation(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        vertical, header = self.verticalHeader(), self.horizontalHeader()
        assert vertical is not None and header is not None
        vertical.hide()
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def has_visible_rows(self) -> bool:
        return any(not self.isRowHidden(row) for row in range(self.rowCount()))

    def paintEvent(self, event: QPaintEvent | None) -> None:
        super().paintEvent(event)
        viewport = self.viewport()
        if viewport is None or not self.empty_text or self.has_visible_rows():
            return
        painter = QPainter(viewport)
        painter.setPen(QColor(colors_for(self).muted))
        painter.drawText(
            viewport.rect().adjusted(12, 0, -12, 0),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            self.empty_text,
        )

    def add_refresh_action(self, hint: str) -> QPushButton:
        """Use one inventory header/selection pattern; the last column holds Refresh."""
        control = refresh_button(hint)
        self.use_header(ActionHeader(control))
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

    def use_header(self, header: QHeaderView) -> None:
        self.setHorizontalHeader(header)
        header.sectionResized.connect(self.schedule_fit)

    @pyqtSlot(int, int, int)
    def schedule_fit(self, section: int, previous: int, current: int) -> None:
        self.fit_timer.start()

    def changeEvent(self, event: QEvent | None) -> None:
        super().changeEvent(event)
        if (
            event is not None
            and event.type() in {QEvent.Type.StyleChange, QEvent.Type.FontChange}
            and hasattr(self, "fit_timer")
        ):
            self.fit_timer.start()

    def set_control(self, row: int, column: int, control: QWidget) -> None:
        host = QWidget()
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(control)
        self.setCellWidget(row, column, host)
        timer = QTimer(host)
        timer.setSingleShot(True)
        timer.timeout.connect(layout.activate)
        timer.start()

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
        self, *, hide_empty_header: bool | None = None, extra_height: int | None = None
    ) -> None:
        if hide_empty_header is not None:
            self._hide_empty_header = hide_empty_header
        if extra_height is not None:
            self._extra_height = extra_height
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
        if self._hide_empty_header:
            header.setVisible(
                any(not self.isRowHidden(row) for row in range(self.rowCount()))
            )
        header.setFixedHeight(header.sizeHint().height())
        self.setFixedHeight(
            (0 if header.isHidden() else header.sizeHint().height())
            + sum(
                self.rowHeight(row)
                for row in range(self.rowCount())
                if not self.isRowHidden(row)
            )
            + 2 * self.frameWidth()
            + self._extra_height
            + (0 if self.has_visible_rows() or not self.empty_text else 56)
        )
