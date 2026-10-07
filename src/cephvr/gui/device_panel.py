"""Shared device draft cards; operations remain explicit presentation intents."""

from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLineEdit, QWidget

from cephvr.gui.components import Card, StatusColumn, button, field
from cephvr.gui.layouts import ResponsiveColumns, column
from cephvr.gui.theme import SIZES
from cephvr.gui.view import DashboardView


def entry(placeholder: str) -> QLineEdit:
    editor = QLineEdit()
    editor.setPlaceholderText(placeholder)
    return editor


class DevicePanel(ResponsiveColumns):
    def __init__(self, title: str, readbacks: str, actions: tuple[str, ...]) -> None:
        left, left_layout = column()
        right = StatusColumn("Device HUD")
        super().__init__(left, right)
        self.configuration = Card(title)
        self.form = QGridLayout()
        self.form.setHorizontalSpacing(SIZES.field_x_gap)
        self.form.setVerticalSpacing(SIZES.field_y_gap)
        self.form.setColumnStretch(0, 1)
        self.form.setColumnStretch(1, 1)
        self.configuration.body.addLayout(self.form)
        self.editors: list[QWidget] = []
        action_row = QHBoxLayout()
        self.action_buttons = []
        for text in actions:
            control = button(
                text, "primary" if text == "Test connection" else "secondary"
            )
            control.clicked.connect(lambda checked=False, name=text: self.request(name))
            action_row.addWidget(control)
            self.action_buttons.append(control)
        self.configuration.body.addLayout(action_row)
        left_layout.addWidget(self.configuration)
        left_layout.addStretch()
        self.status_column = right
        right.hud.setPlainText("CONNECTION  Not connected\n" + readbacks)
        self.console = right.console
        self.console.setPlainText("No connection checks performed.")
        self.can_review = False

    def add(self, title: str, editor: QWidget) -> None:
        index = len(self.editors)
        self.editors.append(editor)
        self.form.addWidget(field(title, editor), index // 2, index % 2)

    def request(self, name: str) -> None:
        if self.can_review:
            self.console.appendPlainText(
                f"REVIEW · {name} requested; no hardware command sent."
            )

    def apply_view(self, view: DashboardView) -> None:
        self.can_review = view.can_edit
        for control in (*self.editors, *self.action_buttons):
            control.setEnabled(self.can_review)
