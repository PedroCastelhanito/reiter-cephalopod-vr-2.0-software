"""Optional CRT film and label glow for Review windows; presentation only."""

from math import hypot

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt
from PyQt6.QtGui import (
    QColor,
    QPainter,
    QPaintEvent,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QWidget

from cephvr.gui.theme import RETRO_COLORS

SCANLINE_PITCH = 3
SCANLINE_ALPHA = 13
VIGNETTE_ALPHA = 32


class CrtOverlay(QWidget):
    """Mouse-transparent scanlines and vignette over one host widget."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.host = host
        self.film: QPixmap | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        host.installEventFilter(self)
        self.hide()

    def set_active(self, active: bool) -> None:
        self.setGeometry(self.host.rect())
        self.setVisible(active)
        self.raise_()

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        if event is not None and event.type() == QEvent.Type.Resize:
            self.setGeometry(self.host.rect())
            self.raise_()
        return False

    def render_film(self, size: QSize, ratio: float) -> QPixmap:
        film = QPixmap(size * ratio)
        film.setDevicePixelRatio(ratio)
        film.fill(Qt.GlobalColor.transparent)
        painter = QPainter(film)
        painter.setPen(QColor(0, 0, 0, SCANLINE_ALPHA))
        for y in range(0, size.height(), SCANLINE_PITCH):
            painter.drawLine(0, y, size.width(), y)
        radius = hypot(size.width(), size.height()) / 2
        gradient = QRadialGradient(size.width() / 2, size.height() / 2, radius)
        gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
        gradient.setColorAt(0.65, QColor(0, 0, 0, 0))
        gradient.setColorAt(1.0, QColor(0, 0, 0, VIGNETTE_ALPHA))
        painter.fillRect(QRect(QPoint(0, 0), size), gradient)
        painter.end()
        return film

    def paintEvent(self, event: QPaintEvent | None) -> None:
        ratio = self.devicePixelRatioF()
        if (
            self.film is None
            or self.film.size() != self.size() * ratio
            or self.film.devicePixelRatio() != ratio
        ):
            self.film = self.render_film(self.size(), ratio)
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.film)


class CrtEffects:
    """Owns the CRT film and label glow so Standard mode never carries either."""

    def __init__(self, host: QWidget, glow_labels: list[QLabel]) -> None:
        self.overlay = CrtOverlay(host)
        self.glow_labels = glow_labels

    def apply(self, enabled: bool) -> None:
        self.overlay.set_active(enabled)
        for label in self.glow_labels:
            if not enabled:
                label.setGraphicsEffect(None)
                continue
            glow = QGraphicsDropShadowEffect(label)
            glow.setOffset(0, 0)
            glow.setBlurRadius(10)
            color = QColor(RETRO_COLORS.accent)
            color.setAlpha(110)
            glow.setColor(color)
            label.setGraphicsEffect(glow)
