"""Simple looming controls over losslessly retained canonical size functions."""

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Any, cast

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QGridLayout, QLineEdit, QVBoxLayout, QWidget

from cephvr.gui.components import field, label
from cephvr.gui.stimulus_form import ValueEditor


class LoomingSize(QWidget):
    changed = pyqtSignal()

    def __init__(
        self,
        values: dict[str, Any],
        schema: dict[str, Any],
        definitions: dict[str, Any],
    ) -> None:
        super().__init__()
        self.original = {key: deepcopy(values[key]) for key in ("width", "height")}
        self.advanced = ValueEditor(
            {
                "type": "object",
                "properties": {k: schema["properties"][k] for k in self.original},
            },
            self.original,
            definitions,
        )
        self.advanced.changed.connect(self.changed)
        curve = values["width"]
        knots = curve.get("knots", [])
        supported = (
            curve == values["height"]
            and curve["kind"] == "keyframes"
            and curve["interpolation"] == "linear"
            and len(knots) == 2
            and all(
                isinstance(k["value"], (int, float)) and "seconds" in k["time"]
                for k in knots
            )
            and Decimal(knots[0]["time"]["seconds"]) == 0
        )
        self.start = QLineEdit(str(knots[0]["value"]) if supported else "")
        self.end = QLineEdit(str(knots[1]["value"]) if supported else "")
        self.duration = QLineEdit(knots[1]["time"]["seconds"] if supported else "")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.basic = QWidget()
        grid = QGridLayout(self.basic)
        grid.setContentsMargins(0, 0, 0, 0)
        unit = "mm" if values["space"]["kind"] == "physical_surface" else "°"
        grid.addWidget(field(f"Start size ({unit})", self.start), 0, 0)
        grid.addWidget(field(f"End size ({unit})", self.end), 0, 1)
        grid.addWidget(field("Growth duration (s)", self.duration), 1, 0, 1, 2)
        layout.addWidget(self.basic)
        self.summary = label(
            "Custom size animation · available in More settings", wrap=True
        )
        layout.addWidget(self.summary)
        self.extra = QWidget()
        details = QVBoxLayout(self.extra)
        details.setContentsMargins(0, 0, 0, 0)
        self.custom = QCheckBox("Custom size animation")
        self.custom.setChecked(not supported)
        self.custom.setEnabled(supported)
        self.custom.toggled.connect(self.arrange)
        self.custom.toggled.connect(self.changed)
        details.addWidget(self.custom)
        details.addWidget(self.advanced)
        layout.addWidget(self.extra)
        for control in (self.start, self.end, self.duration):
            control.textEdited.connect(self.changed)
        self.edited = False
        self.changed.connect(lambda: setattr(self, "edited", True))
        self.arrange()

    def accept(self, values: dict[str, Any]) -> None:
        old = self.advanced
        self.advanced = ValueEditor(
            old.schema, {k: values[k] for k in ("width", "height")}, old.definitions
        )
        self.advanced.changed.connect(self.changed)
        layout = self.extra.layout()
        assert layout is not None
        layout.replaceWidget(old, self.advanced)
        old.hide()
        old.deleteLater()
        curve = values["width"]
        knots = curve.get("knots", [])
        supported = (
            curve == values["height"]
            and curve["kind"] == "keyframes"
            and curve["interpolation"] == "linear"
            and len(knots) == 2
            and all(
                isinstance(k["value"], (int, float)) and "seconds" in k["time"]
                for k in knots
            )
            and Decimal(knots[0]["time"]["seconds"]) == 0
        )
        self.custom.setEnabled(supported)
        if supported:
            self.start.setText(str(knots[0]["value"]))
            self.end.setText(str(knots[1]["value"]))
            self.duration.setText(knots[1]["time"]["seconds"])
        self.edited = False
        self.arrange()

    def arrange(self) -> None:
        self.basic.setVisible(not self.custom.isChecked())
        self.summary.setVisible(self.custom.isChecked())
        self.advanced.setVisible(self.custom.isChecked())

    def read(self) -> dict[str, Any]:
        if self.custom.isChecked() or not self.edited:
            return cast(dict[str, Any], self.advanced.read())
        start, end = float(self.start.text()), float(self.end.text())
        try:
            seconds = Decimal(self.duration.text())
        except InvalidOperation as error:
            raise ValueError("Growth duration must be a positive number") from error
        if (
            not all(isfinite(v) and v > 0 for v in (start, end))
            or not seconds.is_finite()
            or seconds <= 0
        ):
            raise ValueError("Sizes and growth duration must be finite and positive")
        curve = dict(
            kind="keyframes",
            interpolation="linear",
            knots=[
                dict(time={"seconds": "0"}, value=start),
                dict(time={"seconds": str(seconds)}, value=end),
            ],
        )
        return dict(width=curve, height=deepcopy(curve))
