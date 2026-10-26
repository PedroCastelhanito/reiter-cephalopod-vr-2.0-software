"""Contrasting editing surfaces with a shared keyboard-focus treatment."""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from cephvr.gui.components import label
from cephvr.gui.theme import SIZES, colors_for


class EditingSurface(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.editing = False
        self.editing_label = label("", "muted")
        self.editing_label.setParent(self)
        app = QApplication.instance()
        if isinstance(app, QApplication):
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
        colors = colors_for(self)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(
            QColor(colors.projector_edit if self.editing else colors.projector)
        )
        painter.drawRoundedRect(QRectF(self.rect()), 4, 4)
        if self.editing:
            painter.fillRect(0, 4, 3, self.height() - 8, QColor(colors.focus))


class EditingCard(EditingSurface):
    def __init__(self, title: str) -> None:
        super().__init__()
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
