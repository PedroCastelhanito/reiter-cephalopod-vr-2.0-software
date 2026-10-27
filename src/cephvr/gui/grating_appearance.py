"""Inline physical grating appearance over the existing canonical pattern fields."""

from copy import deepcopy
from math import isfinite
from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from cephvr.gui.components import field, label


class RgbEdit(QWidget):
    """One horizontal R/G/B row, so the control keeps a single-line height."""

    changed = pyqtSignal()

    def __init__(self, values: list[float]) -> None:
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.edits = [QLineEdit(str(value)) for value in values]
        for name, edit in zip("RGB", self.edits, strict=True):
            edit.setMinimumWidth(0)
            edit.setAccessibleName(name)
            edit.textEdited.connect(self.changed)
            row.addWidget(label(name, "label"))
            row.addWidget(edit, 1)

    def read(self) -> list[float]:
        return [float(edit.text()) for edit in self.edits]


class GratingAppearance(QWidget):
    changed = pyqtSignal()

    def __init__(self, values: dict[str, Any]) -> None:
        super().__init__()
        self.values = values
        self.period = QLineEdit(f"{1 / values['pattern']['frequency']['value']:g}")
        self.sharpness = QLineEdit(str(values["pattern"].get("feature_sharpness", 0)))
        self.sharpness.setToolTip(
            "0 = sinusoidal; 1 = square bars; intermediate values soften the edges."
        )
        colors = {
            "color_a": [
                a + b
                for a, b in zip(
                    values["mean_linear_rgb"],
                    values["modulation_linear_rgb"],
                    strict=True,
                )
            ],
            "color_b": [
                a - b
                for a, b in zip(
                    values["mean_linear_rgb"],
                    values["modulation_linear_rgb"],
                    strict=True,
                )
            ],
        }
        self.color_a, self.color_b = (
            RgbEdit(colors["color_a"]),
            RgbEdit(colors["color_b"]),
        )
        for edit in (self.color_a, self.color_b):
            edit.changed.connect(self.changed)
        self.period.textEdited.connect(self.changed)
        self.sharpness.textEdited.connect(self.changed)
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.addWidget(field("Spatial period (mm)", self.period))
        body.addWidget(field("Sharpness (0–1)", self.sharpness))
        body.addWidget(field("Color A (linear RGB)", self.color_a))
        body.addWidget(field("Color B (linear RGB)", self.color_b))

    def read(self) -> dict[str, Any]:
        period, sharpness = float(self.period.text()), float(self.sharpness.text())
        if (
            not isfinite(period)
            or period <= 0
            or not isfinite(sharpness)
            or not 0 <= sharpness <= 1
        ):
            raise ValueError(
                "Grating needs a positive finite period and sharpness in [0,1]"
            )
        a, b = self.color_a.read(), self.color_b.read()
        if any(not isfinite(c) or not 0 <= c <= 1 for c in (*a, *b)):
            raise ValueError("Grating colors must be finite linear RGB in [0,1]")
        pattern = deepcopy(self.values["pattern"])
        pattern.update(
            frequency=dict(kind="constant", value=1 / period),
            feature_sharpness=sharpness,
        )
        return dict(
            pattern=pattern,
            mean_linear_rgb=[(x + y) / 2 for x, y in zip(a, b, strict=True)],
            modulation_linear_rgb=[(x - y) / 2 for x, y in zip(a, b, strict=True)],
        )
