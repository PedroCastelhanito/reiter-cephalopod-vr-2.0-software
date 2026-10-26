"""Explicit all-projector brightness intent; hardware remains controller-owned."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QAbstractSpinBox, QHBoxLayout, QSpinBox

from cephvr.gui.components import button, field
from cephvr.gui.editing_card import EditingCard
from cephvr.gui.view import DashboardView, Phase


class ProjectorBrightnessCard(EditingCard):
    requested = pyqtSignal(int)

    def __init__(self) -> None:
        super().__init__("Projector brightness")
        self.current = QSpinBox()
        self.current.setRange(101, 2500)
        self.current.setValue(101)
        self.current.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.current.setAccessibleName("Projector RGB LED current (mA)")
        self.adjust = button(
            "Adjust",
            hint="Set equal RGB LED current on all USB-detected projectors. Close the TI GUI first. Readback may clamp to 1023 mA.",
        )
        row = QHBoxLayout()
        row.addWidget(field("RGB LED current (mA) · all projectors", self.current))
        row.addWidget(self.adjust, alignment=Qt.AlignmentFlag.AlignBottom)
        self.body.addLayout(row)
        self.pending = False
        self.available = False
        self.adjust.clicked.connect(self.submit)
        self.refresh()

    def submit(self) -> None:
        if not self.available or self.pending:
            return
        self.pending = True
        self.refresh()
        self.requested.emit(self.current.value())

    def finish(self) -> None:
        self.pending = False
        self.refresh()

    def apply_view(self, view: DashboardView) -> None:
        self.available = view.can_edit and view.phase == Phase.CONFIGURATION
        self.refresh()

    def refresh(self) -> None:
        self.current.setEnabled(self.available and not self.pending)
        self.adjust.setEnabled(self.available and not self.pending)
