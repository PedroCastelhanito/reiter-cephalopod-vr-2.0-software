"""Per-face raw-pixel bar measurements and derived ideal projector scale."""

import math
from collections.abc import Mapping

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidgetItem,
    QWidget,
)

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
        super().__init__("Pixel-to-mm calibration")
        self.drafts = drafts
        self.fields: dict[tuple[str, str], QLineEdit] = {}
        self.scales: dict[str, QLabel] = {}
        self.table = DataTable(len(FACES), 3)
        self.table.setHorizontalHeaderLabels(
            [
                "Screen",
                "Measured X / Y (mm)",
                "X / Y (mm/px)",
            ]
        )
        header = self.table.horizontalHeader()
        assert header is not None
        for column in (0, 2):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        for row, face in enumerate(FACES):
            self.table.setItem(row, 0, QTableWidgetItem(face))
            self.scales[face] = label("—")
            self.table.set_control(row, 2, self.scales[face])
            measured = QWidget()
            measured_row = QHBoxLayout(measured)
            measured_row.setContentsMargins(0, 0, 0, 0)
            for axis in ("x", "y"):
                key = f"reference_{axis}_mm"
                editor = entry(axis.upper())
                editor.setAccessibleName(
                    f"{face} measured reference bar {axis.upper()} (mm)"
                )
                editor.textChanged.connect(
                    lambda value, f=face, k=key: self.save(f, k, value)
                )
                self.fields[face, key] = editor
                measured_row.addWidget(editor, 1)
            self.table.set_control(row, 1, measured)
            # Retain the actual output mode with each measurement in portable files.
            for axis in ("width", "height", "x", "y"):
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

    def _set(self, face: str, key: str, text: str) -> None:
        editor = self.fields[face, key]
        editor.blockSignals(True)
        editor.setText(text)
        editor.blockSignals(False)
        self.drafts[face][key] = text

    def refresh(
        self,
        outputs: Mapping[str, tuple[int, int]],
        distances: Mapping[tuple[str, str], QLineEdit],
    ) -> None:
        for face in FACES:
            draft = self.drafts[face]
            dimensions = outputs.get(face)
            measured = any(draft.get(f"reference_{a}_mm", "") for a in ("x", "y"))
            complete = all(draft.get(f"reference_{a}_mm", "") for a in ("x", "y"))
            if dimensions is not None and not measured:
                for axis, value in zip(("width", "height"), dimensions, strict=True):
                    self._set(face, f"reference_{axis}_px", str(value))
                # Bar lengths follow the output mode until a measurement fixes them.
                for axis in ("x", "y"):
                    self._set(face, f"reference_{axis}_px", "")
            elif measured:
                try:
                    lengths = reference_lengths(
                        float(draft.get("reference_width_px", "")),
                        float(draft.get("reference_height_px", "")),
                    )
                except ValueError:
                    lengths = None
                if lengths is not None:
                    for axis, length in zip(("x", "y"), lengths, strict=True):
                        if not draft.get(f"reference_{axis}_px", ""):
                            self._set(face, f"reference_{axis}_px", str(int(length)))
            try:
                width = float(draft.get("reference_width_px", ""))
                height = float(draft.get("reference_height_px", ""))
                if dimensions is not None and dimensions != (width, height):
                    raise ValueError(
                        "Reference measurements require their original output mode"
                    )
                scale = reference_scale(
                    width,
                    height,
                    float(draft.get("reference_x_mm", "")),
                    float(draft.get("reference_y_mm", "")),
                    x_px=float(draft["reference_x_px"])
                    if draft.get("reference_x_px")
                    else None,
                    y_px=float(draft["reference_y_px"])
                    if draft.get("reference_y_px")
                    else None,
                )
                self.scales[face].setText(
                    f"{scale.mm_per_pixel_x:.1f} / {scale.mm_per_pixel_y:.1f}"
                )
                try:
                    throw = float(draft.get("throw", ""))
                    estimate = scale.projected_width_mm * throw
                    if not math.isfinite(estimate) or estimate <= 0:
                        raise ValueError(
                            "Projected distance requires a positive throw ratio"
                        )
                    distance = f"{estimate:.1f}"
                except ValueError:
                    distance = ""
            except ValueError:
                self.scales[face].setText("—")
                # Keep an imported or earlier distance while a measurement is partial.
                distance = "" if complete else draft.get("distance", "")
            editor = distances[face, "distance"]
            editor.blockSignals(True)
            editor.setText(distance)
            editor.blockSignals(False)
            draft["distance"] = distance
