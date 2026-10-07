"""Action-time warnings and log-only status, without inline form messages."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox, QWidget

WARNINGS_ENABLED = ContextVar("gui_action_warnings", default=True)


@contextmanager
def passive_validation() -> Iterator[None]:
    token = WARNINGS_ENABLED.set(False)
    try:
        yield
    finally:
        WARNINGS_ENABLED.reset(token)


STATUS_EVENT = QEvent.Type(QEvent.registerEventType())


class StatusEvent(QEvent):
    def __init__(self, text: str) -> None:
        super().__init__(STATUS_EVENT)
        self.text = text


class FormNotice(QWidget):
    """Keep passive diagnostics private; warn only at an explicit action boundary."""

    def __init__(self) -> None:
        super().__init__()
        self._text = ""
        self.dialog: QMessageBox | None = None
        self.hide()

    def setVisible(self, visible: bool) -> None:  # noqa: N802
        super().setVisible(False)

    def text(self) -> str:
        return self._text

    def setText(self, text: str | None) -> None:  # noqa: N802
        self._text = text or ""

    def clear(self) -> None:
        self._text = ""
        if self.dialog is not None:
            self.dialog.reject()

    def warn(self, text: object, title: str = "Cannot complete action") -> None:
        self.setText(str(text))
        if not WARNINGS_ENABLED.get():
            return
        if self.dialog is not None:
            self.dialog.setText(self._text)
            self.dialog.raise_()
            return
        dialog = QMessageBox(
            QMessageBox.Icon.Warning,
            title,
            self._text,
            QMessageBox.StandardButton.Ok,
            self.window(),
        )
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.dialog = dialog
        dialog.finished.connect(lambda: setattr(self, "dialog", None))
        dialog.finished.connect(dialog.deleteLater)
        dialog.open()

    def status(self, text: str) -> None:
        self._text = ""
        if not text:
            return
        logging.getLogger("cephvr.gui").info(text)
        owner = self.parentWidget()
        while owner is not None and not isinstance(owner, QMainWindow):
            owner = owner.parentWidget()
        if owner is not None:
            QApplication.sendEvent(owner, StatusEvent(text))

    def changeEvent(self, event: QEvent | None) -> None:  # noqa: N802
        super().changeEvent(event)
        if not self.isEnabled() and self.dialog is not None:
            self.dialog.reject()
