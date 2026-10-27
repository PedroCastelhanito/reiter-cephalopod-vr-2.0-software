"""Managed dashboard closure waits for controller-owned configuration history."""

from __future__ import annotations

from PyQt6.QtCore import QSettings, pyqtSignal
from PyQt6.QtGui import QCloseEvent

from cephvr.gui.window import DashboardWindow


class ManagedDashboardWindow(DashboardWindow):
    close_requested = pyqtSignal()

    def __init__(
        self,
        *,
        sample: bool = False,
        settings: QSettings | None = None,
        tracking_available: bool = True,
    ) -> None:
        super().__init__(
            sample=sample, settings=settings, tracking_available=tracking_available
        )
        self._close_after_save = False

    def closeEvent(self, event: QCloseEvent | None) -> None:
        if event is None:
            return
        if not self.confirm_authoring_close():
            event.ignore()
            return
        if self._close_after_save:
            super().closeEvent(event)
            return
        event.ignore()
        self.close_requested.emit()
        if self._close_after_save:
            event.accept()
            super().closeEvent(event)

    def finish_close(self) -> None:
        self._close_after_save = True
        self.close()
