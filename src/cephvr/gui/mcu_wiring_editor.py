"""Contextual editor for the canonical MCU wiring draft."""

from collections.abc import Callable

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QWidget,
)

from cephvr.gui.components import combo
from cephvr.gui.pin_numbers import PinNumber


class McuWiringEditor(QDialog):
    """Stage only the wiring fields relevant to the launching action."""

    def __init__(
        self,
        *,
        parent: QWidget,
        title: str,
        port_values: tuple[tuple[str, str], ...],
        port: str,
        pin: str,
        pin_label: str,
        save: Callable[[str, str, str, bool | None], None],
        role_values: tuple[tuple[str, str], ...] = (),
        role: str = "",
        enabled: bool | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self._save = save
        self._fixed_role = role if not role_values else ""
        self.port = combo(())
        self.port.setEditable(True)
        self.port.setAccessibleName("Microcontroller COM port")
        for label, value in port_values:
            self.port.addItem(label, value)
        if port and self.port.findData(port) < 0:
            self.port.addItem(port, port)
        if port:
            self.port.setCurrentIndex(self.port.findData(port))
            self.port.setEditText(port)
        else:
            self.port.setCurrentIndex(-1)
        self.pin = PinNumber()
        self.pin.setText(pin)
        self.pin.setAccessibleName(pin_label)
        self.pin.setPlaceholderText("Not set")
        form = QFormLayout(self)
        self.role = combo(())
        if role_values:
            for label, value in role_values:
                self.role.addItem(label, value)
            if role:
                self.role.setCurrentIndex(self.role.findData(role))
            form.addRow("Camera role", self.role)
        form.addRow("MCU COM port", self.port)
        form.addRow(pin_label, self.pin)
        self.enabled: QCheckBox | None = None
        if enabled is not None:
            self.enabled = QCheckBox("Enable MCU input for experiment configuration")
            self.enabled.setChecked(enabled)
            form.addRow(self.enabled)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)

    def accept(self) -> None:
        index = self.port.currentIndex()
        if index >= 0 and self.port.currentText() == self.port.itemText(index):
            raw = self.port.currentData()
        else:
            raw = self.port.currentText()
        port = str(raw or "").strip()
        self._save(
            port,
            self.pin.text().strip(),
            str(self.role.currentData() or "")
            if self.role.count()
            else self._fixed_role,
            self.enabled.isChecked() if self.enabled is not None else None,
        )
        super().accept()
