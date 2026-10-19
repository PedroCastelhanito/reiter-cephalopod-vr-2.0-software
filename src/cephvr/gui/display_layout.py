"""Scaled desktop rectangle sketch for secondary displays."""

from PyQt6.QtCore import QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import QWidget

from cephvr.gui.theme import colors_for, retro_console


class DisplayLayout(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.outputs: list[tuple[str, QRect]] = []
        self.refreshed = False
        self.disabled_indices: set[int] = set()
        self.setMinimumHeight(80)
        self.setAccessibleName("Displays layout")

    def sizeHint(self) -> QSize:
        return QSize(260, 145)

    def paint_text(self) -> str:
        """Empty-state message: what to do, or what refreshing found."""
        if self.refreshed:
            return "No available projectors have been identified"
        return (
            "No displays listed yet. Use the refresh button in the Displays table "
            "to detect them."
        )

    def paintEvent(self, event: QPaintEvent | None) -> None:
        colors = colors_for(self)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(colors.muted))
        if not self.outputs:
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                self.paint_text(),
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
            painter.setBrush(QColor(colors.selection))
            painter.setPen(
                QColor(colors.muted if row in self.disabled_indices else colors.accent)
            )
            radius = 0 if retro_console(self) else 5
            painter.drawRoundedRect(box, radius, radius)
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, name)
