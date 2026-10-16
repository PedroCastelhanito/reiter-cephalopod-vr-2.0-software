"""Shared variation columns while rule widgets retain validation and sampled values."""

from PyQt6.QtCore import QEvent, QObject, QTimer, pyqtSlot
from PyQt6.QtGui import QCursor, QResizeEvent
from PyQt6.QtWidgets import QHeaderView

from cephvr.gui.batch_variation import BatchVariationRow
from cephvr.gui.tables import DataTable


class VariationTable(DataTable):
    def __init__(self) -> None:
        super().__init__(0, 6)
        self.rules: list[BatchVariationRow] = []
        self.hover_timer = QTimer(self)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self.refresh_hover)
        self.setHorizontalHeaderLabels(
            ["Projectors", "Layer", "Parameter", "Method", "Values / range", ""]
        )
        header = self.horizontalHeader()
        assert header is not None
        for column, width in enumerate((150, 96, 175, 170, 300, 48)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            header.resizeSection(column, width)
        header.setStretchLastSection(False)
        self.setMinimumWidth(0)
        self.fit_rows(hide_empty_header=True)
        self.hide()

    def append_rule(self, rule: BatchVariationRow) -> None:
        row = len(self.rules)
        self.rules.append(rule)
        self.insertRow(row)
        for column, control in enumerate(
            (rule.target, rule.layer, rule.parameter, rule.method, rule, rule.remove)
        ):
            self.set_control(row, column, control)
            control.installEventFilter(self)
        rule.changed.connect(self.fit_rules)
        self.show()
        self.fit_rules()

    def remove_rule(self, rule: BatchVariationRow) -> None:
        row = self.rules.index(rule)
        self.rules.pop(row)
        self.removeRow(row)
        self.setVisible(bool(self.rules))
        self.fit_rules()

    def fit_rules(self) -> None:
        header, viewport, bar = (
            self.horizontalHeader(),
            self.viewport(),
            self.horizontalScrollBar(),
        )
        assert header is not None and viewport is not None and bar is not None
        self.setColumnWidth(
            4,
            max(
                300,
                viewport.width() - sum(self.columnWidth(c) for c in (0, 1, 2, 3, 5)),
            ),
        )
        extra = bar.sizeHint().height() if header.length() > viewport.width() else 0
        self.fit_rows(hide_empty_header=True, extra_height=extra)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        if hasattr(self, "rules"):
            self.fit_rules()

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        if event is not None and event.type() == QEvent.Type.Enter:
            self.hover_timer.start()
        return super().eventFilter(watched, event)

    def leaveEvent(self, event: QEvent | None) -> None:
        self.hover_timer.start()
        super().leaveEvent(event)

    @pyqtSlot()
    def refresh_hover(self) -> None:
        """Visibility changes can synthesize mouse events; finish dispatch first."""
        viewport = self.viewport()
        assert viewport is not None
        position = viewport.mapFromGlobal(QCursor.pos())
        hovered = (
            self.rowAt(position.y())
            if self.isVisible() and viewport.rect().contains(position)
            else -1
        )
        for index, rule in enumerate(self.rules):
            visible = index == hovered
            if rule.remove.isHidden() == visible:
                rule.remove.setVisible(visible)
