"""Coalesce settled preview layouts without waiting for placement polling."""

from collections.abc import Callable

from PyQt6.QtCore import QEvent, QObject, QTimer
from PyQt6.QtWidgets import QWidget


class PreviewLayoutUpdates(QObject):
    def __init__(
        self,
        parent: QWidget,
        areas: tuple[QWidget, ...],
        callbacks: tuple[Callable[[], None], ...],
    ) -> None:
        super().__init__(parent)
        self.callbacks = callbacks
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(0)
        self.timer.timeout.connect(self.flush)
        for area in areas:
            area.installEventFilter(self)

    def schedule(self, *_args: object) -> None:
        if not self.timer.isActive():
            self.timer.start()

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        if event is not None and event.type() in (
            QEvent.Type.LayoutRequest,
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.Hide,
        ):
            self.schedule()
        return super().eventFilter(watched, event)

    def flush(self) -> None:
        # Existing managers retain authority, pending-command and identity checks.
        for callback in self.callbacks:
            callback()
