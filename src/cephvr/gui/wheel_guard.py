"""Wheel gestures navigate containers rather than mutate input values."""

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QScrollBar,
    QTabBar,
    QWidget,
)


class WheelGuard(QObject):
    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:  # noqa: N802
        if not isinstance(event, QWheelEvent) or not isinstance(watched, QWidget):
            return False
        target: QWidget | None = watched
        while target is not None:
            if isinstance(target, QScrollBar):
                return False
            if isinstance(target, QTabBar):
                event.ignore()
                return True
            if isinstance(target, (QComboBox, QAbstractSpinBox, QAbstractSlider)):
                container = target.parentWidget()
                while container is not None:
                    if isinstance(container, QAbstractScrollArea):
                        QApplication.sendEvent(container.viewport(), event)
                        return True
                    container = container.parentWidget()
                event.ignore()
                return True
            if isinstance(target, QAbstractScrollArea):
                break
            target = target.parentWidget()
        return False


def install_wheel_guard(app: QApplication) -> None:
    if app.findChild(WheelGuard) is None:
        guard = WheelGuard(app)
        app.installEventFilter(guard)
        app.aboutToQuit.connect(lambda: app.removeEventFilter(guard))
