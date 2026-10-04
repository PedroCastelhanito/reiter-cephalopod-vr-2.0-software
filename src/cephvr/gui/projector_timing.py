"""Independent pulse-placement and presentation-pacing drafts."""

from PyQt6.QtWidgets import QCheckBox, QGridLayout, QLineEdit, QWidget

from cephvr.gui.components import Card, combo, field
from cephvr.gui.device_panel import entry


class ProjectorTiming(Card):
    def __init__(self) -> None:
        super().__init__("Photodiode & synchronization")
        self.pulse = QCheckBox("Enable photodiode pulse")
        self.body.addWidget(self.pulse)
        self.target = combo(())
        self.target.setPlaceholderText("Select display")
        self.mode = combo(("Selected display VSync", "All displays VSync"))
        self.fields: dict[str, QLineEdit] = {}
        self.options = QWidget()
        grid = QGridLayout(self.options)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(field("PULSE DISPLAY", self.target), 0, 0)
        grid.addWidget(field("VSYNC MODE", self.mode), 0, 1)
        for i, name in enumerate(("X", "Y", "Width", "Height")):
            edit = entry("px")
            edit.setAccessibleName(f"Photodiode {name}")
            self.fields[name] = edit
            grid.addWidget(field(f"{name.upper()} (px)", edit), 1 + i // 2, i % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.body.addWidget(self.options)
        self.pulse.toggled.connect(self.refresh_controls)
        self.can_edit = False
        self.refresh_controls()

    def set_displays(self, displays: list[tuple[str, str, bool]]) -> None:
        selected, text = self.target.currentData(), self.target.currentText()
        self.target.blockSignals(True)
        self.target.clear()
        for key, name, _enabled in displays:
            self.target.addItem(name, key)
        if selected is not None and self.target.findData(selected) < 0:
            self.target.addItem(
                f"{text.removesuffix(' (unavailable)')} (unavailable)", selected
            )
        self.target.setCurrentIndex(
            self.target.findData(selected) if selected is not None else -1
        )
        self.target.blockSignals(False)

    def refresh_controls(self) -> None:
        self.pulse.setEnabled(self.can_edit)
        self.options.setEnabled(self.can_edit and self.pulse.isChecked())
