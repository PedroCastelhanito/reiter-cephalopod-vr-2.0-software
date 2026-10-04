"""Small operator dialogs with explicit choices and no runtime ownership."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QWidget

from cephvr.gui.components import button, label
from cephvr.gui.theme import SIZES


class StopDialog(QDialog):
    action_selected = pyqtSignal(str)

    def __init__(self, available: frozenset[str], parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Stop session")
        self.setMinimumWidth(440)
        body = QVBoxLayout(self)
        body.setContentsMargins(*([SIZES.page_margin] * 4))
        body.setSpacing(SIZES.card_gap)
        body.addWidget(label("Stop session", "title"))
        body.addWidget(
            label(
                "Stop now interrupts the active trial. Stop after trial lets it finish before ending the session.",
                wrap=True,
            )
        )
        actions = QHBoxLayout()
        actions.setSpacing(SIZES.field_x_gap)
        self.choice_buttons = {}
        for action, text in (
            ("Abort now", "Stop now"),
            ("Stop after trial", "Stop after trial"),
        ):
            control = button(text, "danger" if action == "Abort now" else "primary")
            control.setAutoDefault(False)
            control.clicked.connect(
                lambda checked=False, value=action: self.select(value)
            )
            self.choice_buttons[action] = control
            actions.addWidget(control)
        self.cancel = button("Cancel")
        self.cancel.setDefault(True)
        self.cancel.clicked.connect(self.reject)
        actions.addWidget(self.cancel)
        body.addLayout(actions)
        self.update_actions(available)

    def update_actions(self, available: frozenset[str]) -> None:
        for action, control in self.choice_buttons.items():
            control.setEnabled(action in available)
        if not available:
            self.reject()

    def select(self, action: str) -> None:
        if self.choice_buttons[action].isEnabled():
            self.action_selected.emit(action)
            self.accept()
