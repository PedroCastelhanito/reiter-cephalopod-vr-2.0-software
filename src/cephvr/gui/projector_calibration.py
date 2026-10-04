"""Compact per-face correction table, sharing the rig's retained drafts."""

from PyQt6.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QLineEdit, QWidget

from cephvr.gui.components import Card, label
from cephvr.gui.device_panel import entry
from cephvr.gui.projector_geometry import FACES


class CalibrationTable(Card):
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
