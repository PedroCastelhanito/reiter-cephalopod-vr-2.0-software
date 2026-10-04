"""Speed/direction authoring over existing Cartesian and image-tile motion fields."""

from math import atan2, cos, degrees, hypot, isfinite, radians, sin
from typing import Any, cast

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from cephvr.gui.components import field, label
from cephvr.gui.stimulus_form import ValueEditor


def constant_rate(value: dict[str, Any]) -> float | None:
    if value["kind"] == "hold":
        return 0.0
    if (
        value["kind"] == "rate"
        and value["function"]["kind"] == "constant"
        and isinstance(value["function"]["value"], (float, int))
    ):
        return float(value["function"]["value"])
    return None


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
        self.periods: tuple[float, float] | None = None
        texture = values["kind"] == "texture"
        supported = True
        if texture:
            pattern = values["pattern"]
            supported = pattern["kind"] == "image_tile" and all(
                pattern[key]["kind"] == "constant"
                and isinstance(pattern[key]["value"], (float, int))
                for key in ("period_x", "period_y")
            )
            if supported:
                self.periods = (
                    pattern["period_x"]["value"],
                    pattern["period_y"]["value"],
                )
            x, y = (constant_rate(values[key]) for key in ("phase_x", "phase_y"))
            supported = (
                supported
                and values["motion"]["x"]["kind"] == "hold"
                and values["motion"]["y"]["kind"] == "hold"
            )
        else:
            x, y = (constant_rate(values["motion"][key]) for key in ("x", "y"))
        self.rotation_key = "yaw" if values["kind"] == "arena" else "rotation"
        angular = constant_rate(values["motion"][self.rotation_key])
        supported = supported and all(value is not None for value in (x, y, angular))
        if self.periods and x is not None and y is not None:
            x, y = -x * self.periods[0], -y * self.periods[1]
        self.speed = QLineEdit(f"{hypot(x or 0, y or 0):g}")
        self.direction = QLineEdit(f"{degrees(atan2(y or 0, x or 0)):g}")
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
        self.direction.setToolTip("0° = local +X; 90° = local +Y")
        self.extra = QWidget()
        details = QVBoxLayout(self.extra)
        details.setContentsMargins(0, 0, 0, 0)
        details.addWidget(field("Angular speed (°/s)", self.angular))
        self.angular.textEdited.connect(self.changed)
        layout.addWidget(self.extra)
        self.summary = label("Custom motion · available in More settings", wrap=True)
        layout.addWidget(self.summary)
        self.custom = QCheckBox("Custom motion functions")
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
        self.summary.setVisible(self.custom.isChecked())
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
        x, y = speed * cos(radians(angle)), speed * sin(radians(angle))
        result = cast(dict[str, Any], self.advanced.read())

        def rate(value: float) -> dict[str, Any]:
            return {"kind": "rate", "function": {"kind": "constant", "value": value}}

        if self.periods:
            result["phase_x"], result["phase_y"] = (
                rate(-x / self.periods[0]),
                rate(-y / self.periods[1]),
            )
        else:
            result["motion"]["x"], result["motion"]["y"] = rate(x), rate(y)
        result["motion"][self.rotation_key] = rate(angular)
        return result
