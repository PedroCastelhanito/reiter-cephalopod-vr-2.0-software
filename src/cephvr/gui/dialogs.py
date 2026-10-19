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
        actions = QHBoxLayout()
        actions.setSpacing(SIZES.field_x_gap)
        self.choice_buttons = {}
        for action, text in (
            ("Abort now", "Stop now"),
            ("Stop after trial", "Stop after trial"),
        ):
            control = button(text, "danger" if action == "Abort now" else "primary")
            control.setToolTip(
                "Interrupt the active trial now"
                if action == "Abort now"
                else "Finish the active trial before ending the session"
            )
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


class SubjectReuseDialog(QDialog):
    """Same subject, same experiment, same day: likely a repeated run, so ask once."""

    confirmed = pyqtSignal()

    def __init__(
        self, subject: str, experiment: str, count: int, latest: str, parent: QWidget
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Subject already recorded today")
        self.setMinimumWidth(480)
        body = QVBoxLayout(self)
        body.setContentsMargins(*([SIZES.page_margin] * 4))
        body.setSpacing(SIZES.card_gap)
        body.addWidget(label("Subject already recorded today", "title"))
        body.addWidget(
            label(
                f"{subject} already has {count} session{'s' if count != 1 else ''} "
                f"in this output directory, including one for {experiment} today "
                f"(latest: {latest}). A new session is saved separately and nothing "
                "is overwritten. Continue only if this is a new run.",
                "hint",
                wrap=True,
            )
        )
        actions = QHBoxLayout()
        actions.setSpacing(SIZES.field_x_gap)
        self.change = button("Change Subject ID")
        self.change.setDefault(True)
        self.change.clicked.connect(self.reject)
        self.proceed = button("Continue setup", "primary")
        self.proceed.setAutoDefault(False)
        self.proceed.clicked.connect(self.confirm)
        actions.addWidget(self.change)
        actions.addWidget(self.proceed)
        body.addLayout(actions)

    def confirm(self) -> None:
        self.confirmed.emit()
        self.accept()
