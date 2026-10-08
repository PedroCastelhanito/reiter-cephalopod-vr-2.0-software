"""Per-face raw-pixel bar measurements and derived ideal projector scale."""

from collections.abc import Mapping

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLabel, QLineEdit, QTableWidgetItem

from cephvr.gui.components import Card, label
from cephvr.gui.device_panel import entry
from cephvr.gui.projector_geometry import FACES
from cephvr.gui.tables import DataTable
from cephvr.visual_stimulus.config.calibration_bars import (
    reference_lengths,
    reference_scale,
)


class ProjectorMeasurements(Card):
    changed = pyqtSignal()

    def __init__(self, drafts: dict[str, dict[str, str]]) -> None:
        super().__init__("Projected reference bars")
        self.drafts = drafts
        self.fields: dict[tuple[str, str], QLineEdit] = {}
        self.spans: dict[str, QLabel] = {}
        self.scales: dict[str, QLabel] = {}
        self.body.addWidget(
            label(
                "Launch calibration and measure the orange horizontal and green vertical bars. "
                "Enter their lengths in mm. Distance is an ideal throw estimate; subject distance stays separate.",
                wrap=True,
            )
        )
        self.table = DataTable(len(FACES), 5)
        self.table.setHorizontalHeaderLabels(
            [
                "Screen",
                "Bar X / Y (px)",
                "Measured X (mm)",
                "Measured Y (mm)",
                "X / Y (mm/px)",
            ]
        )
        for row, face in enumerate(FACES):
            self.table.setItem(row, 0, QTableWidgetItem(face))
            self.spans[face], self.scales[face] = label("—"), label("—")
            self.table.set_control(row, 1, self.spans[face])
            self.table.set_control(row, 4, self.scales[face])
            for axis, col in (("x", 2), ("y", 3)):
                key = f"reference_{axis}_mm"
                editor = entry("Measure")
                editor.setAccessibleName(
                    f"{face} measured reference bar {axis.upper()} (mm)"
                )
                editor.textChanged.connect(
                    lambda value, f=face, k=key: self.save(f, k, value)
                )
                self.fields[face, key] = editor
                self.table.set_control(row, col, editor)
            # Retain the actual output mode with each measurement in portable files.
            for axis in ("width", "height"):
                key = f"reference_{axis}_px"
                editor = QLineEdit(self)
                editor.setReadOnly(True)
                editor.hide()
                editor.textChanged.connect(
                    lambda value, f=face, k=key: self.save(f, k, value)
                )
                self.fields[face, key] = editor
        self.table.fit_rows()
        self.body.addWidget(self.table)

    def save(self, face: str, key: str, value: str) -> None:
        self.drafts[face][key] = value
        self.changed.emit()

    def clear_measurements(self, face: str) -> None:
        for axis in ("x", "y"):
            self.fields[face, f"reference_{axis}_mm"].clear()

    def refresh(
        self,
        outputs: Mapping[str, tuple[int, int]],
        distances: Mapping[tuple[str, str], QLineEdit],
    ) -> None:
        for face in FACES:
            draft = self.drafts[face]
            self.spans[face].setText("—")
            dimensions = outputs.get(face)
            measured = any(draft.get(f"reference_{a}_mm", "") for a in ("x", "y"))
            if dimensions is not None and not measured:
                for axis, value in zip(("width", "height"), dimensions, strict=True):
                    key = f"reference_{axis}_px"
                    text = str(value)
                    editor = self.fields[face, key]
                    editor.blockSignals(True)
                    editor.setText(text)
                    editor.blockSignals(False)
                    draft[key] = text
            try:
                width = float(draft.get("reference_width_px", ""))
                height = float(draft.get("reference_height_px", ""))
                x, y = reference_lengths(width, height)
                self.spans[face].setText(f"{x:g} / {y:g}")
                if dimensions is not None and dimensions != (width, height):
                    raise ValueError(
                        "Reference measurements require their original output mode"
                    )
                scale = reference_scale(
                    width,
                    height,
                    float(draft.get("reference_x_mm", "")),
                    float(draft.get("reference_y_mm", "")),
                    float(draft.get("throw", "")),
                )
                self.scales[face].setText(
                    f"{scale.mm_per_pixel_x:.6g} / {scale.mm_per_pixel_y:.6g}"
                )
                distance = f"{scale.projector_distance_mm:.17g}"
            except ValueError:
                self.scales[face].setText("—")
                # Preserve an imported historical distance until measurements are supplied.
                distance = "" if measured else draft.get("distance", "")
            editor = distances[face, "distance"]
            editor.blockSignals(True)
            editor.setText(distance)
            editor.blockSignals(False)
            draft["distance"] = distance
