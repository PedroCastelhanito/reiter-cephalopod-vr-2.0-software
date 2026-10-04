"""Compact per-face correction table, sharing the rig's retained drafts."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QLineEdit, QWidget

from cephvr.gui.components import Card, button, label
from cephvr.gui.device_panel import entry
from cephvr.gui.projector_geometry import FACES


class CalibrationTable(Card):
    prepare_requested = pyqtSignal()
    launch_requested = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self, drafts: dict[str, dict[str, str]]) -> None:
        super().__init__("Screen calibration")
        self.drafts = drafts
        self.controls: dict[tuple[str, str], QWidget] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        for col, title in enumerate(
            ("SCREEN", "INVERSE", "SCALE X / Y", "OFFSET X / Y (px)")
        ):
            grid.addWidget(label(title, "label", wrap=True), 0, col)
        for row, face in enumerate(FACES, 1):
            grid.addWidget(label(face), row, 0)
            for col, keys in enumerate(
                (
                    ("flip_x", "flip_y"),
                    ("scale_u", "scale_v"),
                    ("offset_x", "offset_y"),
                ),
                1,
            ):
                cell = QWidget()
                layout = QHBoxLayout(cell)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(5)
                for axis, key in zip(("X", "Y"), keys, strict=True):
                    control: QCheckBox | QLineEdit
                    if col == 1:
                        control = QCheckBox(axis)
                        control.toggled.connect(
                            lambda value, f=face, k=key: self.drafts[f].__setitem__(
                                k, str(value)
                            )
                        )
                    else:
                        control = entry(axis)
                        control.setMinimumWidth(0)
                        control.setMaximumWidth(90)
                        control.textChanged.connect(
                            lambda value, f=face, k=key: self.drafts[f].__setitem__(
                                k, value
                            )
                        )
                    control.setAccessibleName(f"{face} {key}")
                    self.controls[face, key] = control
                    layout.addWidget(control)
                grid.addWidget(cell, row, col)
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(3, 1)
        self.body.addLayout(grid)
        self.prepare_button = button("Prepare calibration files")
        self.prepare_button.setToolTip(
            "Export the arena and diagnostic per-projector mappings to the Protocol Assets folder"
        )
        self.prepare_button.clicked.connect(lambda: self.prepare_requested.emit())
        self.body.addWidget(self.prepare_button)
        self.presentation_button = button("Launch")
        self.presentation_button.setToolTip(
            "Requires a connected managed Visual Stimulus renderer"
        )
        self.presentation_button.setEnabled(False)
        self.presentation_button.clicked.connect(self.request_presentation)
        self.body.addWidget(self.presentation_button)
        self.presentation_active = False
        self.presentation_available = False
        self.presentation_pending = False

    def request_presentation(self) -> None:
        if not self.presentation_available or self.presentation_pending:
            return
        if self.presentation_active:
            self.close_requested.emit()
        else:
            self.launch_requested.emit()

    def set_presentation_state(
        self, *, active: bool, available: bool, pending: bool = False
    ) -> None:
        """Show confirmed renderer state, never infer it from a button click."""
        self.presentation_active = active
        self.presentation_available = available
        self.presentation_pending = pending
        self.presentation_button.setText("Close" if active else "Launch")
        self.presentation_button.setEnabled(available and not pending)
