"""Compact per-face correction table, sharing the rig's retained drafts."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QTableWidgetItem,
    QWidget,
)

from cephvr.gui.components import Card, button
from cephvr.gui.device_panel import entry
from cephvr.gui.projector_geometry import FACES
from cephvr.gui.tables import DataTable


class CalibrationTable(Card):
    launch_requested = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self, drafts: dict[str, dict[str, str]]) -> None:
        super().__init__("Screen calibration")
        self.drafts = drafts
        self.controls: dict[tuple[str, str], QWidget] = {}
        self.table = DataTable(len(FACES), 4)
        self.table.setHorizontalHeaderLabels(
            ["Screen", "Inverse", "Scale X / Y", "Offset X / Y (px)"]
        )
        header = self.table.horizontalHeader()
        assert header is not None
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        for row, face in enumerate(FACES):
            self.table.setItem(row, 0, QTableWidgetItem(face))
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
                self.table.set_control(row, col, cell)
        self.table.fit_rows()
        self.body.addWidget(self.table)
        self.presentation_button = button("Launch")
        self.presentation_button.setToolTip(
            "Prepare calibration files and launch with a connected managed Visual Stimulus renderer"
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
