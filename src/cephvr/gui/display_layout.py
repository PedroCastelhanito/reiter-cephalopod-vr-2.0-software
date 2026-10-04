"""Scaled desktop rectangle sketch for secondary displays."""

from PyQt6.QtCore import QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import QWidget

from cephvr.gui.theme import COLORS


class DisplayLayout(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.outputs: list[tuple[str, QRect]] = []
        self.refreshed = False
        self.disabled_indices: set[int] = set()
        self.setMinimumHeight(80)
        self.setAccessibleName("Displays layout")

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(260, 145)

    def paintEvent(self, event: QPaintEvent | None) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(COLORS.muted))
        if not self.outputs:
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "No secondary displays found" if self.refreshed else "Refresh displays",
            )
            return
        bounds = QRect()
        for _, rect in self.outputs:
            bounds = bounds.united(rect)
        scale = min(
            (self.width() - 20) / max(1, bounds.width()),
            (self.height() - 20) / max(1, bounds.height()),
        )
        for row, (name, rect) in enumerate(self.outputs):
            box = QRectF(
                (rect.x() - bounds.x()) * scale
                + (self.width() - bounds.width() * scale) / 2,
                (rect.y() - bounds.y()) * scale
                + (self.height() - bounds.height() * scale) / 2,
                rect.width() * scale,
                rect.height() * scale,
            ).adjusted(2, 2, -2, -2)
            painter.setBrush(QColor(COLORS.selection))
            painter.setPen(
                QColor(COLORS.muted if row in self.disabled_indices else COLORS.accent)
            )
            painter.drawRoundedRect(box, 5, 5)
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, name)
