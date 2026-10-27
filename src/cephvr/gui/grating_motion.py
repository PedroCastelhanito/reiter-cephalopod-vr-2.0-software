"""Two-field grating control; orientation always determines across-bar drift."""

from copy import deepcopy
from math import isfinite
from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QWidget

from cephvr.gui.components import field
from cephvr.gui.rig_parameter_edits import motion_numbers, patch_setting


class GratingMotion(QWidget):
    changed = pyqtSignal()

    def __init__(self, values: dict[str, Any]) -> None:
        super().__init__()
        self.values = values
        speed, angle, _ = motion_numbers(values)
        self.orientation = QLineEdit(f"{angle:g}")
        self.speed = QLineEdit(f"{speed:g}")
        self.orientation.setToolTip(
            "Movement across the bars: Right 0°, Front 90°, Left 180°, Back −90°."
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for caption, edit in (
            ("Orientation (°)", self.orientation),
            ("Speed (mm/s)", self.speed),
        ):
            edit.setMinimumWidth(0)
            edit.setAccessibleName(caption)
            edit.textEdited.connect(self.changed)
            layout.addWidget(field(caption, edit), 1)

    def read(self) -> dict[str, Any]:
        angle, speed = float(self.orientation.text()), float(self.speed.text())
        if not all(isfinite(value) for value in (angle, speed)) or speed < 0:
            raise ValueError("Orientation must be finite and Speed must be nonnegative")
        result = deepcopy(self.values)
        patch_setting(result, {"Orientation": str(angle), "Speed": str(speed)})
        return {
            key: result[key] for key in ("motion", "phase_x", "phase_y", "assignments")
        }
