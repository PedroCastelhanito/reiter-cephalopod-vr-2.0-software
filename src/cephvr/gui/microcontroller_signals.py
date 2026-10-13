"""Supported MCU signal rows; enablement and pin ownership stay with the panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtGui import QStandardItemModel
from PyQt6.QtWidgets import QComboBox, QDialog, QHeaderView, QInputDialog, QPushButton

from cephvr.gui.components import button, combo

if TYPE_CHECKING:
    from cephvr.gui.microcontroller import MicrocontrollerPanel
    from cephvr.gui.tables import DataTable


class MicrocontrollerSignals:
    def __init__(self, panel: MicrocontrollerPanel) -> None:
        self.panel = panel
        self.selectors: dict[str, QComboBox] = {}
        self.remove_buttons: dict[str, QPushButton] = {}
        self.output_identity: tuple[tuple[str, str], ...] | None = None
        self.add_dialog: QInputDialog | None = None
        self.add_input = button("Add input", "secondary")
        self.add_output = button("Add output", "secondary")
        self.add_input.clicked.connect(lambda: self.add("input"))
        self.add_output.clicked.connect(lambda: self.add("output"))
        panel.io.body.addWidget(self.add_input)
        panel.triggers.body.addWidget(self.add_output)
        for table in (panel.input_table, panel.output_table):
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(["Use", "Signal", "Pin", "Test", ""])
            header = table.horizontalHeader()
            assert header is not None
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

    def supported(self, direction: str) -> tuple[tuple[str, str], ...]:
        if direction == "input":
            return (("projector-flip", "Projector flip"),)
        return (("trial-state", "Trial state"),) + tuple(
            (
                camera.key,
                "Eye camera trigger" if camera.role == "Eye tracking" else camera.role,
            )
            for camera in self.panel.camera_rows
            if camera.role in ("Behavior cam", "Tracking cam", "Eye tracking")
        )

    def invalidate(self) -> None:
        if self.add_dialog is not None:
            self.add_dialog.reject()
        self.output_identity = None

    def install(self, table: DataTable, row: int, key: str, direction: str) -> None:
        selector = combo(())
        selector.setMinimumWidth(0)
        selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        selector.setAccessibleName(f"{direction.title()} signal")
        selector.currentIndexChanged.connect(
            lambda: self.select(key, selector.currentData(), direction)
        )
        remove = button("×", "compact", hint="Remove this signal; retain its pin")
        remove.setAccessibleName(f"Remove {direction} signal")
        remove.clicked.connect(lambda: self.remove(key))
        self.selectors[key] = selector
        self.remove_buttons[key] = remove
        table.takeItem(row, 1)
        table.set_control(row, 1, selector)
        table.set_control(row, 4, remove)

    def refresh(self, editable: bool) -> None:
        panel = self.panel
        if not editable and self.add_dialog is not None:
            self.add_dialog.reject()
        if panel.output_table.rowCount() != len(panel.camera_rows) + 1:
            return
        keys = tuple(camera.key for camera in panel.camera_rows)
        identity = tuple((camera.key, camera.role) for camera in panel.camera_rows)
        if not self.selectors or identity != self.output_identity:
            self.selectors.clear()
            self.remove_buttons.clear()
            self.install(panel.input_table, 0, "projector-flip", "input")
            self.install(panel.output_table, 0, "trial-state", "output")
            for row, camera in enumerate(panel.camera_rows, 1):
                if camera.role in ("Behavior cam", "Tracking cam", "Eye tracking"):
                    self.install(panel.output_table, row, camera.key, "output")
            self.output_identity = identity
        for direction, table, add in (
            ("input", panel.input_table, self.add_input),
            ("output", panel.output_table, self.add_output),
        ):
            supported = self.supported(direction)
            missing = [
                key
                for key, _ in supported
                if not panel.enable_controls[key].isChecked()
            ]
            add.setEnabled(editable and bool(missing))
            add.setToolTip(
                "Add a supported signal"
                if missing
                else "All supported signals are added"
            )
            row_keys = (
                ("projector-flip",) if direction == "input" else ("trial-state",) + keys
            )
            for row, key in enumerate(row_keys):
                present = (
                    key in self.selectors and panel.enable_controls[key].isChecked()
                )
                table.setRowHidden(row, not present)
                if key not in self.selectors:
                    continue
                selector = self.selectors[key]
                with QSignalBlocker(selector):
                    selector.clear()
                    for candidate, name in supported:
                        selector.addItem(name, candidate)
                        model = selector.model()
                        assert isinstance(model, QStandardItemModel)
                        item = model.item(selector.count() - 1)
                        assert item is not None
                        needs_pin = (
                            panel.managed
                            and candidate in panel.pin_editors
                            and not panel.pin_editors[candidate].text().strip()
                        )
                        item.setEnabled(
                            candidate == key or (candidate in missing and not needs_pin)
                        )
                        if needs_pin:
                            item.setToolTip(
                                "Use Add output to assign this camera's pin first."
                            )
                    selector.setCurrentIndex(selector.findData(key))
                selector.setEnabled(editable)
                self.remove_buttons[key].setEnabled(editable)
            table.fit_rows(hide_empty_header=True)
        signal_width = max(
            selector.sizeHint().width() for selector in self.selectors.values()
        )
        for selector in self.selectors.values():
            selector.setMinimumWidth(signal_width)
        for table in (panel.input_table, panel.output_table):
            table.resizeColumnToContents(1)

    def editable(self) -> bool:
        panel = self.panel
        return panel.can_review and not (
            panel.review_tests
            or panel.managed_test_key
            or panel.pending_test_key
            or panel.connection_pending
            or panel.upload_pending
        )

    def add(self, direction: str) -> None:
        if not self.editable():
            return
        for key, _ in self.supported(direction):
            if not self.panel.enable_controls[key].isChecked():
                if self.panel.managed and key in self.panel.pin_editors:
                    self.add_camera(key)
                    return
                self.panel.enable_controls[key].setChecked(True)
                return

    def add_camera(self, key: str) -> None:
        if self.add_dialog is not None:
            return
        pin = self.panel.pin_editors[key].text().strip()
        if pin:
            self.panel.camera_output_requested.emit(key, pin)
            return
        dialog = QInputDialog(self.panel)
        dialog.setWindowTitle("Add camera trigger output")
        name = dict(self.supported("output"))[key]
        dialog.setLabelText(f"{name} output pin (2–13):")
        dialog.setTextValue("")
        self.add_dialog = dialog

        def finish(result: int) -> None:
            self.add_dialog = None
            value = dialog.textValue().strip()
            if result == QDialog.DialogCode.Accepted and self.editable():
                if (
                    len(value) <= 2
                    and value.isascii()
                    and value.isdecimal()
                    and 2 <= int(value) <= 13
                ):
                    self.panel.camera_output_requested.emit(key, str(int(value)))
                else:
                    self.panel.console.appendPlainText(
                        "Enter an output pin from 2 to 13."
                    )
            dialog.deleteLater()

        dialog.finished.connect(finish)
        dialog.open()

    def remove(self, key: str) -> None:
        if self.editable() and key in self.selectors:
            self.panel.enable_controls[key].setChecked(False)

    def select(self, old: str, new: object, direction: str) -> None:
        if (
            new == old
            or not isinstance(new, str)
            or not self.editable()
            or new not in dict(self.supported(direction))
            or self.panel.enable_controls[new].isChecked()
        ):
            return
        if (
            self.panel.managed
            and new in self.panel.pin_editors
            and not self.panel.pin_editors[new].text().strip()
        ):
            self.panel.console.appendPlainText(
                "Use Add output to assign the camera's pin first."
            )
            self.refresh(self.editable())
            return
        self.panel.enable_controls[old].setChecked(False)
        self.panel.enable_controls[new].setChecked(True)
