"""Trial selection with viewport-local actions and a scrollable trailing add button."""

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QMouseEvent, QPaintEvent
from PyQt6.QtWidgets import QAbstractItemView, QListWidget

from cephvr.gui.components import button


class TrialList(QListWidget):
    delete_requested = pyqtSignal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setProperty("role", "trials")
        self.setAccessibleName("Trials")
        self.setMinimumWidth(0)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        surface = self.viewport()
        scrollbar = self.verticalScrollBar()
        assert surface is not None and scrollbar is not None
        self.surface = surface
        self.list_scrollbar = scrollbar
        self.hover_row = -1
        self.add = button("+", hint="Add trial")
        self.add.setAccessibleName("Add trial")
        self.add.setParent(self.surface)
        self.add.setFixedHeight(36)
        self.removers = [button("×", "compact", hint="Delete trial")]
        for control in self.removers:
            control.setParent(self.surface)
            control.ensurePolished()
            control.setFixedSize(control.sizeHint())
            control.clicked.connect(
                lambda _checked=False, target=control: self.delete_requested.emit(
                    target.property("trial_row")
                )
            )
            control.hide()
        self.currentRowChanged.connect(self.position_actions)
        self.list_scrollbar.valueChanged.connect(self.position_actions)

    def updateGeometries(self) -> None:
        super().updateGeometries()
        if not hasattr(self, "add"):
            return
        last = self.item(self.count() - 1)
        bottom = (
            self.visualItemRect(last).bottom() + 1 + self.list_scrollbar.value()
            if last is not None
            else 0
        )
        height = self.visualItemRect(last).height() if last is not None else 40
        self.list_scrollbar.setMaximum(
            max(0, bottom + height + 12 - self.surface.height())
        )
        self.position_actions()

    def position_actions(self, _value: int = 0) -> None:
        if not hasattr(self, "add"):
            return
        viewport = self.surface
        last = self.item(self.count() - 1)
        bottom = self.visualItemRect(last).bottom() + 1 if last is not None else 0
        height = self.visualItemRect(last).height() if last is not None else 40
        self.add.setFixedHeight(height)
        self.add.setGeometry(2, bottom + 6, max(36, viewport.width() - 4), height)
        self.add.setVisible(bottom + 6 < viewport.height() and bottom + height + 6 > 0)
        rows = [self.hover_row] if self.hover_row >= 0 else []
        for slot, control in enumerate(self.removers):
            row = rows[slot] if slot < len(rows) else -1
            item = self.item(row)
            rect = self.visualItemRect(item) if item is not None else None
            if rect is None or not viewport.rect().intersects(rect):
                control.hide()
                continue
            assert item is not None
            control.setProperty("trial_row", row)
            control.setAccessibleName(f"Delete {item.text()}")
            control.move(
                rect.right() - control.width() - 4,
                rect.top() + (rect.height() - control.height()) // 2,
            )
            control.show()
            control.raise_()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        super().paintEvent(event)
        self.position_actions()

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is not None:
            self.hover_row = self.indexAt(event.position().toPoint()).row()
            self.position_actions()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent | None) -> None:
        if not self.rect().contains(self.mapFromGlobal(QCursor.pos())):
            self.hover_row = -1
            self.position_actions()
        super().leaveEvent(event)
