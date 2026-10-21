"""Speed/direction authoring over existing Cartesian and image-tile motion fields."""

from copy import deepcopy
from math import isfinite
from typing import Any, cast

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from cephvr.gui.components import field
from cephvr.gui.rig_parameter_edits import motion_numbers, patch_setting
from cephvr.gui.stimulus_form import ValueEditor
from cephvr.visual_stimulus.config.parameter_edits import constant_rate as constant_rate
from cephvr.visual_stimulus.config.rig_coordinates import local_direction


class EpochMotion(QWidget):
    changed = pyqtSignal()

    def __init__(
        self,
        values: dict[str, Any],
        schema: dict[str, Any],
        definitions: dict[str, Any],
    ) -> None:
        super().__init__()
        self.values = values
        keys = [key for key in ("motion", "phase_x", "phase_y") if key in values]
        self.advanced = ValueEditor(
            {
                "type": "object",
                "properties": {key: schema["properties"][key] for key in keys},
            },
            {key: values[key] for key in keys},
            definitions,
        )
        self.advanced.changed.connect(self.changed)
        self.rotation_key = "yaw" if values["kind"] == "arena" else "rotation"
        angular = constant_rate(values["motion"][self.rotation_key])
        reason = ""
        try:
            speed, angle, angular = motion_numbers(values)
            local_direction(values, angle)
            supported = True
        except (ValueError, TypeError) as error:
            speed, angle, supported = 0.0, 0.0, False
            reason = str(error)
        self.speed = QLineEdit(f"{speed:g}")
        self.direction = QLineEdit(f"{angle:g}")
        self.angular = QLineEdit(f"{angular or 0:.17g}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.basic = QWidget()
        row = QHBoxLayout(self.basic)
        row.setContentsMargins(0, 0, 0, 0)
        unit = (
            "mm/s"
            if values["kind"] == "arena"
            or values.get("space", {}).get("kind") == "physical_surface"
            else "deg/s"
        )
        for name, control in (
            (f"Speed ({unit})", self.speed),
            ("Direction (°)", self.direction),
        ):
            control.setMinimumWidth(0)
            control.textEdited.connect(self.changed)
            row.addWidget(field(name, control), 1)
        layout.addWidget(self.basic)
        self.direction.setToolTip(
            "0° = angular-frame +X; 90° = angular-frame +Y"
            if values.get("space", {}).get("kind") == "visual_angle"
            else "Rig coordinates: 0° Right; 90° Front; 180° Left; −90° Back."
        )
        if values.get("space", {}).get("kind") == "physical_surface":
            self.speed.setToolTip(
                "Physical speed on the screen in mm/s. Each projector's measured "
                "X/Y pixel-to-mm calibration determines its pixel speed, including "
                "linked textures. Save reference-bar measurements and run Setup "
                "again after changing calibration."
            )
        self.extra = QWidget()
        details = QVBoxLayout(self.extra)
        details.setContentsMargins(0, 0, 0, 0)
        details.addWidget(field("Angular speed (°/s)", self.angular))
        self.angular.textEdited.connect(self.changed)
        layout.addWidget(self.extra)
        self.custom = QCheckBox("Custom motion functions")
        self.custom.setToolTip(
            reason
            or "Custom motion functions are available in More settings; saved functions are preserved."
        )
        self.custom.setChecked(not supported)
        self.custom.setEnabled(supported)
        self.custom.toggled.connect(self.arrange)
        self.custom.toggled.connect(self.changed)
        details.addWidget(self.custom)
        details.addWidget(self.advanced)
        self.arrange()
        self.edited = False
        self.changed.connect(lambda: setattr(self, "edited", True))

    def arrange(self) -> None:
        self.basic.setVisible(not self.custom.isChecked())
        self.advanced.setVisible(self.custom.isChecked())

    def read(self) -> dict[str, Any]:
        if self.custom.isChecked() or not self.edited:
            return cast(dict[str, Any], self.advanced.read())
        speed, angle, angular = (
            float(self.speed.text()),
            float(self.direction.text()),
            float(self.angular.text()),
        )
        if not all(isfinite(value) for value in (speed, angle, angular)) or speed < 0:
            raise ValueError("Speed must be nonnegative and all motion values finite")
        result = deepcopy(self.values)
        patch_setting(
            result,
            {
                "Speed": str(speed),
                "Direction": str(angle),
                "Angular speed": str(angular),
            },
        )
        return {
            key: result[key]
            for key in ("motion", "phase_x", "phase_y")
            if key in result
        }
