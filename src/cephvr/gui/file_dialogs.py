"""Native file selection with cancelable queued modal startup."""

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QFileDialog, QWidget


def file_dialog(parent: QWidget, title: str, directory: str = "") -> QFileDialog:
    return QFileDialog(parent, title, directory)


def open_file_dialog(dialog: QFileDialog) -> None:
    # exec() stops Qt's Windows helper launch timer. Queue it on an owned
    # timer so immediate cancellation can prevent native startup entirely.
    launch = QTimer(dialog)
    launch.setSingleShot(True)
    launch.timeout.connect(dialog.exec)
    dialog.finished.connect(launch.stop)
    launch.start(0)
