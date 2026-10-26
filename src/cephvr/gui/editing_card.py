"""Contrasting editing surfaces with a shared keyboard-focus treatment."""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import label
from cephvr.gui.theme import SIZES, Palette, colors_for


def paint_editing_surface(
    painter: QPainter, rect: QRectF, colors: Palette, editing: bool
) -> None:
    """One fill, radius and focus accent for widget and table row surfaces."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(colors.projector_edit if editing else colors.projector))
    painter.drawRoundedRect(rect, 4, 4)
    if editing:
        painter.fillRect(
            QRectF(rect.left(), rect.top() + 4, 3, rect.height() - 8),
            QColor(colors.focus),
        )


class EditingSurface(QWidget):
    def __init__(self, *, filled: bool = True) -> None:
        super().__init__()
        self.filled = filled
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.editing = False
        self.editing_label = label("", "muted")
        self.editing_label.setParent(self)
        app = QApplication.instance()
        if filled and isinstance(app, QApplication):
            app.focusChanged.connect(self.focus_changed)

    def focus_changed(self, old: QWidget | None, new: QWidget | None) -> None:
        # Qt's isAncestorOf stops at popup windows; their parent chain retains ownership.
        owner = new
        while owner is not None and owner is not self:
            owner = owner.parentWidget()
        editing = owner is self
        if editing != self.editing:
            self.editing = editing
            self.editing_label.setText("Editing" if editing else "")
            self.update()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        super().paintEvent(event)
        if not self.filled:
            return
        painter = QPainter(self)
        paint_editing_surface(
            painter, QRectF(self.rect()), colors_for(self), self.editing
        )


class EditingCard(EditingSurface):
    def __init__(self, title: str, *, filled: bool = False) -> None:
        super().__init__(filled=filled)
        self.body = QVBoxLayout(self)
        padding = SIZES.card_padding
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(SIZES.body_gap)
        self.header = QHBoxLayout()
        self.caption = label(title, "projector-title")
        self.caption.setWordWrap(True)
        policy = self.caption.sizePolicy()
        policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
        self.caption.setSizePolicy(policy)
        self.header.addWidget(self.caption, 1)
        self.header.addWidget(self.editing_label)
        self.body.addLayout(self.header)


class EditingRow(EditingCard):
    """Screen-dimensions layout: identity at left, controls in one compact row."""

    def __init__(self, title: str) -> None:
        super().__init__(title, filled=True)
        self.body.setDirection(QBoxLayout.Direction.LeftToRight)
        self.body.setContentsMargins(12, 10, 12, 10)
        self.body.setSpacing(12)
        self.header.setDirection(QBoxLayout.Direction.TopToBottom)
        self.header.setSpacing(0)
        self.caption.setFixedWidth(84)
