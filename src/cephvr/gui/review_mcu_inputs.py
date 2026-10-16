"""Named input drafts for local review, without serial or diagnostic operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QCheckBox, QLineEdit, QPushButton

from cephvr.gui.components import button, equal_row_height
from cephvr.gui.pin_numbers import PinNumber

if TYPE_CHECKING:
    from cephvr.gui.microcontroller import MicrocontrollerPanel


@dataclass
class InputRow:
    enabled: QCheckBox
    name: QLineEdit
    pin: PinNumber
    test: QPushButton
    remove: QPushButton


def validate_inputs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(
        not isinstance(row, dict)
        or set(row) != {"name", "pin", "enabled"}
        or not isinstance(row["name"], str)
        or not isinstance(row["pin"], str)
        or type(row["enabled"]) is not bool
        for row in value
    ):
        raise ValueError("Expected named Microcontroller input drafts")
    return value


class ReviewMicrocontrollerInputs(QObject):
    def __init__(self, panel: MicrocontrollerPanel) -> None:
        super().__init__(panel)
        self.panel = panel
        self.rows: list[InputRow] = []
        self.add_button = button("Add input", "secondary")
        self.add_button.clicked.connect(lambda: self.add())
        panel.io.body.addWidget(self.add_button)
        panel.controls_changed.connect(self.refresh)
        self.refresh()

    def add(self) -> None:
        if not self.panel.signals.editable():
            return
        row = self.append(dict(name="", pin="", enabled=True))
        row.name.setFocus()
        self.panel.mark_draft_changed()

    def append(self, draft: dict[str, Any]) -> InputRow:
        row = InputRow(
            QCheckBox(),
            QLineEdit(),
            PinNumber(),
            button("Test", "compact"),
            button("×", "icon", hint="Remove input"),
        )
        row.remove.setFixedSize(26, 26)
        row.name.setPlaceholderText("Input name")
        row.name.setAccessibleName("Input name")
        row.name.setMinimumWidth(70)
        row.pin.setMinimumWidth(70)
        row.pin.setPlaceholderText("2–13")
        row.test.setMinimumWidth(70)
        row.test.setToolTip("Input diagnostics await runtime integration")
        row.enabled.setChecked(draft["enabled"])
        row.name.setText(draft["name"])
        row.pin.setText(draft["pin"])
        self.rows.append(row)
        table = self.panel.input_table
        index = table.rowCount()
        table.setRowCount(index + 1)
        equal_row_height(row.name, row.pin, row.test)
        for column, widget in enumerate(
            (row.enabled, row.name, row.pin, row.test, row.remove)
        ):
            table.set_control(index, column, widget)
        row.remove.clicked.connect(lambda: self.remove(row))
        row.name.textChanged.connect(self.changed)
        row.pin.textChanged.connect(self.changed)
        row.enabled.toggled.connect(self.changed)
        self.refresh()
        return row

    def remove(self, row: InputRow) -> None:
        if not self.panel.signals.editable() or row not in self.rows:
            return
        index = self.rows.index(row)
        self.rows.pop(index)
        # Row zero is the inert legacy projector-flip slot owned by the base panel.
        self.panel.input_table.removeRow(index + 1)
        self.changed()

    def changed(self) -> None:
        self.panel.mark_draft_changed()
        self.refresh()

    def refresh(self) -> None:
        editable = self.panel.signals.editable()
        self.add_button.setEnabled(editable)
        for row in self.rows:
            name = row.name.text().strip() or "input"
            row.enabled.setEnabled(editable)
            row.name.setEnabled(editable)
            row.pin.setEnabled(editable)
            row.remove.setEnabled(editable)
            row.remove.setAccessibleName(f"Remove {name}")
            row.enabled.setAccessibleName(f"Enable {name}")
            row.pin.setAccessibleName(f"{name} input pin")
            row.test.setAccessibleName(f"Test {name}")
            row.test.setEnabled(False)
        self.panel.input_table.fit_rows(hide_empty_header=True)
        self.panel.input_table.setVisible(bool(self.rows))

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            dict(
                name=row.name.text(),
                pin=row.pin.text(),
                enabled=row.enabled.isChecked(),
            )
            for row in self.rows
        ]

    def restore(self, value: object) -> None:
        drafts = validate_inputs(value)
        self.rows.clear()
        self.panel.input_table.setRowCount(1)
        for draft in drafts:
            self.append(draft)
        self.refresh()
