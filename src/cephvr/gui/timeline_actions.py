"""Visible-block action controls; canonical edits stay with the editor."""

from PyQt6.QtCore import QObject, QRectF, pyqtSignal
from PyQt6.QtWidgets import QPushButton, QWidget

from cephvr.gui.components import button


class TimelineActions(QObject):
    remove_requested = pyqtSignal(object)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.add = button("+", hint="Add group")
        self.add.setParent(parent)
        self.add.setAccessibleName("Add group")
        self.add.setFixedSize(36, 60)
        self.add.hide()
        self.removers: list[QPushButton] = []
        self.used = 0
        self.enabled = False

    def begin(self) -> None:
        self.used = 0

    def place(
        self, rect: QRectF, paths: tuple[tuple[int, ...], ...], *, enabled: bool
    ) -> None:
        if self.used == len(self.removers):
            control = button("×", "compact")
            control.setParent(self.add.parentWidget())
            control.ensurePolished()
            control.setFixedSize(control.sizeHint())
            control.clicked.connect(
                lambda _checked=False, target=control: self.remove_requested.emit(
                    target.property("paths")
                )
            )
            self.removers.append(control)
        control = self.removers[self.used]
        self.used += 1
        control.setProperty("paths", paths)
        name = "Delete subgroup" if len(paths[0]) > 1 else "Delete group"
        control.setAccessibleName(name)
        control.setToolTip(name if enabled else "Keep at least one " + name[7:])
        control.setEnabled(enabled)
        control.move(
            round(rect.right() - control.width() - 4),
            round(rect.top() + min(4, (rect.height() - control.height()) / 2)),
        )
        control.show()
        control.raise_()

    def finish(self, x: float, y: int, width: int) -> None:
        for control in self.removers[self.used :]:
            control.hide()
        self.add.move(round(x), y)
        self.add.setVisible(self.enabled and x < width and x + 36 > 0)
        self.add.raise_()
