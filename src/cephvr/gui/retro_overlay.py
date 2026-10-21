"""Optional CRT film and label glow for Review windows; presentation only."""

from math import hypot

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPaintEvent,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QWidget

from cephvr.gui.theme import RETRO_COLORS

SCANLINE_PITCH = 3
SCANLINE_ALPHA = 18
VIGNETTE_ALPHA = 55
GLOW_ALPHA = 140
BAND_HEIGHT = 90
BAND_SPEED = 70  # px per second; the band crosses a 900px window in about 13 s
BAND_INTERVAL_MS = 50


class CrtOverlay(QWidget):
    """Mouse-transparent scanlines and vignette over one host widget."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.host = host
        self.film: QPixmap | None = None
        self.band_y = -BAND_HEIGHT
        self.band_timer = QTimer(self)
        self.band_timer.setInterval(BAND_INTERVAL_MS)
        self.band_timer.timeout.connect(self.advance_band)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # Native preview hosts can promote sibling overlays to HWNDs.
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        host.installEventFilter(self)
        self.hide()

    def set_active(self, active: bool, *, band: bool = False) -> None:
        self.setGeometry(self.host.rect())
        self.setVisible(active)
        self.raise_()
        # The rolling band repaints continuously, so it runs only when requested.
        if active and band:
            self.band_timer.start()
        else:
            self.band_timer.stop()
            self.update()

    def band_rect(self) -> QRect:
        return QRect(0, self.band_y, self.width(), BAND_HEIGHT)

    def advance_band(self) -> None:
        before = self.band_rect()
        self.band_y += BAND_SPEED * BAND_INTERVAL_MS // 1000
        if self.band_y > self.height():
            self.band_y = -BAND_HEIGHT
        self.update(before.united(self.band_rect()))

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
        if self.band_timer.isActive():
            band = QLinearGradient(0, self.band_y, 0, self.band_y + BAND_HEIGHT)
            ink = QColor(RETRO_COLORS.accent)
            for position, alpha in ((0.0, 0), (0.7, 9), (1.0, 0)):
                ink.setAlpha(alpha)
                band.setColorAt(position, ink)
            painter.fillRect(self.band_rect(), band)


def set_glow(label: QLabel, enabled: bool) -> None:
    """Phosphor glow behind one heading; removed when CRT effects are off."""
    if not enabled:
        label.setGraphicsEffect(None)
        return
    glow = QGraphicsDropShadowEffect(label)
    glow.setOffset(0, 0)
    glow.setBlurRadius(12)
    color = QColor(RETRO_COLORS.accent)
    color.setAlpha(GLOW_ALPHA)
    glow.setColor(color)
    label.setGraphicsEffect(glow)


class CrtEffects:
    """Owns the CRT film and label glow so Standard mode never carries either."""

    def __init__(self, host: QWidget, glow_labels: list[QLabel]) -> None:
        self.overlay = CrtOverlay(host)
        self.glow_labels = glow_labels

    def apply(self, enabled: bool, *, band: bool = False) -> None:
        self.overlay.set_active(enabled, band=band)
        for label in self.glow_labels:
            set_glow(label, enabled)
