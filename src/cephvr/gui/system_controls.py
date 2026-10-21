"""Shared system-control presentation; the dashboard retains command admission."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from cephvr.gui.components import Card, button
from cephvr.gui.theme import SIZES


class SystemControls(Card):
    action_requested = pyqtSignal(str)

    def __init__(self, *, compact: bool = False) -> None:
        super().__init__("System controls", compact=compact)
        row_host = QWidget()
        row = QHBoxLayout(row_host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SIZES.field_x_gap)
        self.command_buttons: dict[str, QPushButton] = {}
        for name in ("Start", "Stop"):
            control = button(
                "Setup" if name == "Start" else name,
                "danger" if name == "Stop" else "primary",
            )
            control.setAutoDefault(False)
            control.clicked.connect(
                lambda _checked=False, action=name: self.action_requested.emit(action)
            )
            self.command_buttons[name] = control
            row.addWidget(control, 1)
        self.body.addWidget(row_host, 1)
