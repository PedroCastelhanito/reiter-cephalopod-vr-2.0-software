"""Inline output templates for Review; fixed signal/pin owners remain authoritative."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWidgets import (
    QComboBox,
    QHeaderView,
    QPushButton,
    QTableWidgetItem,
    QWidget,
)

from cephvr.gui.components import button, combo, equal_row_height
from cephvr.gui.microcontroller_signals import ROLE_OUTPUTS, MicrocontrollerSignals
from cephvr.gui.pin_numbers import PinNumber

if TYPE_CHECKING:
    from cephvr.gui.microcontroller import MicrocontrollerPanel


@dataclass
class OutputTemplate:
    row: int
    selector: QComboBox
    pin: PinNumber
    remove: QPushButton


class ReviewMicrocontrollerSignals(MicrocontrollerSignals):
    def __init__(self, panel: MicrocontrollerPanel) -> None:
        super().__init__(panel)
        self.draft_keys: set[str] = set()
        self.templates: list[OutputTemplate] = []
        self.selectors: dict[str, QComboBox] = {}
        for table in (panel.output_table, panel.input_table):
            header = table.horizontalHeader()
            assert header is not None
            for column, width in ((2, 96), (3, 100), (4, 52)):
                header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
                header.resizeSection(column, width)
        for remove in panel.output_remove.values():
            remove.setProperty("role", "icon")
            remove.setFixedSize(26, 26)
        for key, (table, row) in self.rows.items():
            selector = combo(())
            selector.setAccessibleName(
                f"{panel.test_buttons[key].property('signal_name')} output type"
            )
            self.selectors[key] = selector
            table.setItem(row, 1, QTableWidgetItem())
            table.set_control(row, 1, selector)
            selector.currentIndexChanged.connect(
                lambda _index, old=key: self.change_role(old)
            )
        for control, _keys in self.add_buttons:
            control.setMenu(None)
            control.clicked.connect(lambda: self.add())

    def used(self) -> set[str]:
        return self.draft_keys | {
            key for key, editor in self.editors.items() if editor.text().strip()
        }

    def choices(self, selector: QComboBox, current: str = "") -> None:
        with QSignalBlocker(selector):
            selector.clear()
            for key in self.editors:
                if key == current or key not in self.used():
                    selector.addItem(
                        str(self.panel.test_buttons[key].property("signal_name")), key
                    )
            selector.setPlaceholderText("Select output")
            selector.setCurrentIndex(selector.findData(current) if current else -1)

    def refresh(self, editable: bool) -> None:
        self.draft_keys.update(
            key for key, editor in self.editors.items() if editor.text().strip()
        )
        super().refresh(editable)
        for key, selector in self.selectors.items():
            self.choices(selector, key)
            selector.setEnabled(editable)
            if key in self.draft_keys:
                table, row = self.rows[key]
                table.setRowHidden(row, False)
        for template in self.templates:
            self.choices(template.selector)
            template.selector.setEnabled(editable)
            template.pin.setEnabled(editable)
            template.remove.setEnabled(editable)
        for control, _keys in self.add_buttons:
            control.setEnabled(
                editable and len(self.used()) + len(self.templates) < len(self.editors)
            )
        self.panel.output_table.fit_rows(hide_empty_header=True)

    def add(self, key: str | None = None) -> None:
        if not self.editable():
            return
        if key is not None:
            if key not in self.editors or key in self.used():
                return
            self.draft_keys.add(key)
            if key in self.panel.enable_controls:
                self.panel.enable_controls[key].setChecked(True)
            self.panel.refresh_tests()
            self.editors[key].setFocus()
            self.panel.mark_draft_changed()
            return
        if len(self.used()) + len(self.templates) >= len(self.editors):
            return
        template = self.append_template()
        template.selector.setFocus()
        self.panel.mark_draft_changed()

    def append_template(self, pin_text: str = "") -> OutputTemplate:
        table = self.panel.output_table
        index = table.rowCount()
        table.setRowCount(index + 1)
        selector, pin = combo(()), PinNumber()
        selector.setAccessibleName("Output type")
        pin.setAccessibleName("Unassigned output pin")
        pin.setPlaceholderText("2–13")
        remove = button("×", "icon", hint="Remove output template")
        remove.setFixedSize(26, 26)
        remove.setAccessibleName("Remove output template")
        test = button("Test", "compact")
        test.setEnabled(False)
        template = OutputTemplate(index, selector, pin, remove)
        self.templates.append(template)
        equal_row_height(selector, pin, test)
        for column, control in enumerate((QWidget(), selector, pin, test, remove)):
            table.set_control(index, column, control)
        selector.currentIndexChanged.connect(lambda: self.assign(template))
        pin.textChanged.connect(self.panel.mark_draft_changed)
        remove.clicked.connect(lambda: self.remove_template(template))
        self.panel.refresh_tests()
        pin.setText(pin_text)
        return template

    def remove_template(self, template: OutputTemplate) -> None:
        if not self.editable() or template not in self.templates:
            return
        self.templates.remove(template)
        self.panel.output_table.removeRow(template.row)
        for other in self.templates:
            if other.row > template.row:
                other.row -= 1
        self.panel.refresh_tests()
        self.panel.mark_draft_changed()

    def assign(self, template: OutputTemplate) -> None:
        key = template.selector.currentData()
        if not self.editable() or not key or key in self.used():
            return
        value = template.pin.text()
        self.remove_template(template)
        self.add(key)
        self.editors[key].setText(value)
        self.panel.save_pins()
        self.panel.refresh_tests()

    def change_role(self, old: str) -> None:
        key = self.selectors[old].currentData()
        if not self.editable() or not key or key == old or key in self.used():
            return
        value = self.editors[old].text()
        self.remove(old)
        self.add(key)
        self.editors[key].setText(value)
        self.panel.save_pins()
        self.panel.refresh_tests()

    def remove(self, key: str) -> None:
        if not self.editable():
            return
        super().remove(key)
        self.draft_keys.discard(key)
        self.panel.refresh_tests()

    def snapshot(self) -> dict[str, Any]:
        return dict(
            selected=sorted(self.used()),
            templates=[row.pin.text() for row in self.templates],
        )

    def restore(self, value: object) -> None:
        data = validate_outputs(
            value,
            {key for key, editor in self.editors.items() if editor.text().strip()},
        )
        self.draft_keys = set(data["selected"])
        for template in reversed(self.templates):
            self.panel.output_table.removeRow(template.row)
        self.templates.clear()
        for pin in data["templates"]:
            self.append_template(pin)
        self.panel.refresh_tests()


def validate_outputs(value: object, occupied: set[str] | None = None) -> dict[str, Any]:
    keys = {"trial-state", *(key for key, _ in ROLE_OUTPUTS)}
    if not isinstance(value, dict) or set(value) != {"selected", "templates"}:
        raise ValueError("Expected review output templates")
    selected, templates = value["selected"], value["templates"]
    if (
        not isinstance(selected, list)
        or any(not isinstance(k, str) or k not in keys for k in selected)
        or len(set(selected)) != len(selected)
        or not isinstance(templates, list)
        or any(not isinstance(pin, str) for pin in templates)
        or len(selected) + len(templates) > len(keys)
    ):
        raise ValueError("Invalid review output templates")
    if len(set(selected) | (occupied or set())) + len(templates) > len(keys):
        raise ValueError("Too many review output templates")
    return value
