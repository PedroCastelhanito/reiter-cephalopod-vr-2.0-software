"""Saved-style startup presentation; no device or runtime ownership."""

from PyQt6.QtCore import (
    QElapsedTimer,
    QEvent,
    QEventLoop,
    QObject,
    QRectF,
    QSettings,
    Qt,
    QTimer,
)
from PyQt6.QtGui import (
    QCloseEvent,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QApplication, QSplashScreen, QWidget

from cephvr.gui.theme import COLORS, RETRO_PALETTES, load_terminal_font


def saved_style(settings: QSettings | None) -> str:
    """Share the existing preference and legacy fallback with the main window."""
    name = str(
        settings.value(
            "appearance/style", settings.value("review/appearance", "standard")
        )
        if settings is not None
        else "standard"
    )
    return name if name in RETRO_PALETTES else "standard"


class StartupSplash(QSplashScreen):
    """Native text splash with an indeterminate indicator, never a fake percentage."""

    def __init__(self, settings: QSettings) -> None:
        self.style_name = saved_style(settings)
        self.colors = (
            RETRO_PALETTES[self.style_name][0]
            if self.style_name in RETRO_PALETTES
            else COLORS
        )
        self.crt = self.style_name in RETRO_PALETTES
        super().__init__()
        load_terminal_font()
        self.setWindowTitle("CephVR2.0 — Initializing")
        self.setAccessibleName("CephVR2.0 Initializing")
        self.phase = 0
        self.clock = QElapsedTimer()
        self.last_frame_ms = 0
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.advance)
        self.redraw()
        self.setPixmap(self.frame)

    def redraw(self) -> None:
        ratio = self.devicePixelRatioF()
        pixmap = QPixmap(round(600 * ratio), round(340 * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(QColor(self.colors.window))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(self.colors.border))
        painter.drawRect(0, 0, 599, 339)
        ink = (
            self.colors.focus
            if self.style_name == "amber_phosphor"
            else self.colors.coral
            if self.style_name == "retro_console"
            else self.colors.text
        )
        font = QFont("IBM Plex Mono")
        font.setPixelSize(58)
        font.setBold(True)
        path = QPainterPath()
        path.addText(0, 0, font, "CephVR2.0")
        bounds = path.boundingRect()
        path.translate(300 - bounds.center().x(), 140 - bounds.center().y())
        if self.crt:
            glow = QColor(ink)
            glow.setAlpha(20)
            for width in (6, 4, 2):
                painter.strokePath(path, QPen(glow, width))
        painter.fillPath(path, QColor(ink))
        if self.crt:
            painter.save()
            painter.setClipPath(path)
            painter.setPen(QColor(0, 0, 0, 65))
            for y in range(100, 180, 3):
                painter.drawLine(30, y, 570, y)
            painter.restore()
        font.setPixelSize(20)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(
            QColor(
                self.colors.label if self.style_name == "standard" else self.colors.text
            )
        )
        painter.drawText(
            QRectF(0, 205, 600, 30), Qt.AlignmentFlag.AlignCenter, "Initializing"
        )
        painter.fillRect(210, 264, 180, 2, QColor(self.colors.border))
        # Back-and-forth motion indicates activity, not completed work.
        offset = 144 - abs(144 - self.phase)
        painter.fillRect(210 + offset, 264, 36, 2, QColor(self.colors.accent))
        painter.end()
        self.frame = pixmap
        self.update()

    def pixmap(self) -> QPixmap:
        return self.frame

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.frame)
        painter.end()

    def advance(self) -> None:
        self.last_frame_ms = self.clock.elapsed()
        self.phase = (self.last_frame_ms * 150 // 1000) % 288
        self.redraw()

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        if (
            self.timer.isActive()
            and event is not None
            and event.type() == QEvent.Type.ChildAdded
            and self.clock.elapsed() - self.last_frame_ms >= self.timer.interval()
        ):
            # Constructors block timers. Paint only this splash, without dispatching
            # queued callbacks into partially constructed frontend owners.
            self.advance()
            QWidget.repaint(self)
        return False

    def closeEvent(self, event: QCloseEvent | None) -> None:
        self.timer.stop()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().closeEvent(event)

    def mousePressEvent(self, event: object) -> None:
        # QSplashScreen normally hides on click; startup must keep its cover.
        pass

    def begin(self) -> None:
        self.clock.start()
        app = QApplication.instance()
        assert app is not None
        app.installEventFilter(self)
        self.show()
        self.timer.start()
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

    def reveal(self, window: QWidget) -> None:
        """Paint the native maximized surface before making it opaque."""
        window.ensurePolished()
        opacity = window.windowOpacity()
        window.setWindowOpacity(0)
        try:
            window.showMaximized()
            # Constructors are complete: deliver native expose/layout events, then
            # flush the real backing store rather than rendering a discarded pixmap.
            QApplication.processEvents(
                QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
            )
            window.repaint()
        finally:
            window.setWindowOpacity(opacity)
        self.finish(window)
        self.timer.stop()
        self.close()
