"""Style-owned CRT film and label glow; presentation only."""

from math import hypot

from PyQt6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QRect,
    QRegularExpression,
    QSize,
    Qt,
)
from PyQt6.QtGui import (
    QColor,
    QPainter,
    QPaintEvent,
    QPixmap,
    QRadialGradient,
    QRegion,
)
from PyQt6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QLabel, QWidget

from cephvr.gui.theme import retro_colors, retro_console

SCANLINE_PITCH = 3
SCANLINE_ALPHA = 18
# Amber phosphor scanlines read as stripes on bright fills, like a CRT terminal.
PHOSPHOR_SCANLINE_ALPHA = 28
VIGNETTE_ALPHA = 55
GLOW_ALPHA = 140


class CrtOverlay(QWidget):
    """Mouse-transparent scanlines and vignette over one host widget."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.host = host
        self.film: QPixmap | None = None
        self.scanline_alpha = SCANLINE_ALPHA
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # Native preview hosts can promote sibling overlays to HWNDs.
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        host.installEventFilter(self)
        self.hide()

    def set_active(self, active: bool) -> None:
        self.setGeometry(self.host.rect())
        self.setVisible(active)
        self.raise_()
        self.update()

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
        painter.setPen(QColor(0, 0, 0, self.scanline_alpha))
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
        region = QRegion(self.rect())
        for preview in self.host.findChildren(
            QWidget,
            QRegularExpression(
                "^(ExternalPreviewSlot|TrialPreviewPixels|AssetPreviewPixels)$"
            ),
        ):
            if preview.window() is self.host.window() and preview.isVisibleTo(
                self.host
            ):
                region -= QRegion(
                    QRect(preview.mapTo(self.host, QPoint()), preview.size())
                )
        painter.setClipRegion(region)
        painter.drawPixmap(0, 0, self.film)


def set_glow(label: QLabel, enabled: bool) -> None:
    """Phosphor glow behind one heading; removed when CRT effects are off."""
    if not enabled:
        label.setGraphicsEffect(None)
        return
    glow = QGraphicsDropShadowEffect(label)
    glow.setOffset(0, 0)
    glow.setBlurRadius(12)
    color = QColor(retro_colors(label).accent)
    color.setAlpha(GLOW_ALPHA)
    glow.setColor(color)
    label.setGraphicsEffect(glow)


class WindowFilms(QObject):
    """Scanline film on Retro-family popups, menus and owned windows of `host`.

    Top-level windows do not inherit the host overlay, so each gets its own film when
    shown; native file pickers are not Qt widgets and keep the platform look."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.host = host
        self.enabled = False
        self.scanline_alpha = SCANLINE_ALPHA
        self.films: list[CrtOverlay] = []
        app = QApplication.instance()
        assert app is not None
        app.installEventFilter(self)

    def set(self, enabled: bool, scanline_alpha: int) -> None:
        self.enabled, self.scanline_alpha = enabled, scanline_alpha
        alive = []
        for film in self.films:
            try:
                self.refresh(film)
            except RuntimeError:  # the popup or window was deleted
                continue
            alive.append(film)
        self.films = alive

    def refresh(self, film: CrtOverlay) -> None:
        if film.scanline_alpha != self.scanline_alpha:
            film.scanline_alpha = self.scanline_alpha
            film.film = None
        film.set_active(self.enabled and film.host.isVisible())

    def owned(self, window: QWidget) -> bool:
        owner = window.parentWidget()
        while owner is not None:
            if owner is self.host:
                return True
            owner = owner.parentWidget()
        return False

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        if (
            event is not None
            and event.type() == QEvent.Type.Show
            and isinstance(watched, QWidget)
            and watched.isWindow()
            and watched is not self.host
            and self.owned(watched)
            and retro_console(watched)
        ):
            film = next(
                (
                    child
                    for child in watched.children()
                    if isinstance(child, CrtOverlay)
                ),
                None,
            )
            if film is None:
                film = CrtOverlay(watched)
                self.films.append(film)
            self.refresh(film)
        return False


class CrtEffects:
    """Owns the CRT film and label glow so Standard mode never carries either."""

    def __init__(self, host: QWidget, glow_labels: list[QLabel]) -> None:
        self.overlay = CrtOverlay(host)
        self.glow_labels = glow_labels

    def apply(self, enabled: bool, *, scanline_alpha: int = SCANLINE_ALPHA) -> None:
        if scanline_alpha != self.overlay.scanline_alpha:
            self.overlay.scanline_alpha = scanline_alpha
            self.overlay.film = None
        self.overlay.set_active(enabled)
        for label in self.glow_labels:
            set_glow(label, enabled)
