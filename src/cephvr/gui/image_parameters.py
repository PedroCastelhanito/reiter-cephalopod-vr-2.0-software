"""Image fitting and whole-image movement over the existing 2D state fields."""

from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from cephvr.gui.components import combo, equal_row_height, field
from cephvr.gui.epoch_motion import EpochMotion


class ImageParameters(QWidget):
    changed = pyqtSignal()

    def __init__(
        self,
        values: dict[str, Any],
        schema: dict[str, Any],
        definitions: dict[str, Any],
    ) -> None:
        super().__init__()
        self.values = values
        self.fit = combo(("Resize", "Source", "Fold"))
        saved_fit = values.get("fit", "stretch")
        self.fit.setPlaceholderText(f"Legacy {saved_fit.title()}")
        self.fit.setCurrentIndex(self.fit.findText(saved_fit.title()))
        self.fit.setToolTip(
            "Resize: fill the valid screen area, changing proportions if needed. "
            "Source: center original pixels; crop larger axes and pad smaller axes "
            "with the scene background. Fold: use the unfolded preview layout with "
            "Front pixels as the physical scale reference; crop to valid areas. "
            "Projector calibration still applies."
        )
        self.motion = EpochMotion(values, schema, definitions)
        self.motion.hide()
        self.initial_x = QLineEdit(f"{values['initial']['x']:g}")
        self.initial_y = QLineEdit(f"{values['initial']['y']:g}")
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        position = QHBoxLayout()
        unit = "mm" if values["space"]["kind"] == "physical_surface" else "°"
        for caption, control in (
            (f"Initial X ({unit})", self.initial_x),
            (f"Initial Y ({unit})", self.initial_y),
            ("Rotation (°/s)", self.motion.angular),
        ):
            control.setMinimumWidth(0)
            position.addWidget(field(caption, control), 1)
        equal_row_height(self.initial_x, self.initial_y, self.motion.angular)
        body.addLayout(position)
        self.fit.currentIndexChanged.connect(self.update_controls)
        self.update_controls()
        self.fit.currentTextChanged.connect(self.changed)
        self.motion.changed.connect(self.changed)
        self.initial_x.textEdited.connect(self.changed)
        self.initial_y.textEdited.connect(self.changed)

    def read(self) -> dict[str, Any]:
        fit = self.fit.currentText().lower() or self.values.get("fit", "stretch")
        if fit in {"resize", "source", "fold"}:
            return {"fit": fit}
        initial = dict(self.values["initial"])
        initial.update(x=float(self.initial_x.text()), y=float(self.initial_y.text()))
        return {
            "fit": fit,
            "initial": initial,
            **self.motion.read(),
        }

    def update_controls(self) -> None:
        legacy = self.fit.currentIndex() < 0
        for control in (
            self.initial_x,
            self.initial_y,
            self.motion.speed,
            self.motion.direction,
            self.motion.angular,
        ):
            control.setEnabled(legacy and not self.motion.custom.isChecked())
