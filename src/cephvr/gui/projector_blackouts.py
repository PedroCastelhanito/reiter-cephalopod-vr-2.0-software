"""Editable output-space blackout rectangles, retained by logical screen face."""

from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QHeaderView, QLineEdit

from cephvr.gui.components import Card, button, combo
from cephvr.gui.device_panel import entry
from cephvr.gui.projector_geometry import FACES
from cephvr.gui.tables import DataTable


class BlackoutZones(Card):
    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__("Blackout zones")
        self.table = DataTable(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Screen", "X", "Y", "Width", "Height", ""]
        )
        header = self.table.horizontalHeader()
        assert header is not None
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.placement_button = button("Launch blackout placement")
        self.body.addWidget(self.placement_button)
        self.body.addWidget(self.table)
        self.rows: list[tuple[QComboBox, list[QLineEdit]]] = []
        self.add_button = button("Add zone")
        self.add_button.clicked.connect(lambda: self.add())
        self.body.addWidget(self.add_button)
        self.table.fit_rows(hide_empty_header=True)

    def add(self, data: dict[str, Any] | None = None) -> None:
        if data is None and not self.isEnabled():
            return
        face = combo(tuple(FACES))
        face.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        fields = [entry("px") for _ in range(4)]
        for name, editor in zip(("X", "Y", "Width", "Height"), fields, strict=True):
            editor.setMinimumWidth(0)
            editor.setAccessibleName(f"Blackout {name}")
            editor.setToolTip("Output pixels; X from left and Y from bottom")
            editor.textEdited.connect(self.changed)
        face.currentIndexChanged.connect(self.changed)
        record = (face, fields)
        self.rows.append(record)
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.set_control(row, 0, face)
        for column, editor in enumerate(fields, 1):
            self.table.set_control(row, column, editor)
        remove = button("×", "compact", hint="Remove blackout zone")
        remove.clicked.connect(lambda: self.remove(record))
        self.table.set_control(row, 5, remove)
        if data is not None:
            face.setCurrentText(data["face"])
            for key, editor in zip(("x", "y", "width", "height"), fields, strict=True):
                value = data[key]
                editor.setText("" if value is None else str(value))
        self.table.fit_rows(hide_empty_header=True)
        self.changed.emit()

    def remove(self, record: tuple[QComboBox, list[QLineEdit]]) -> None:
        if self.isEnabled():
            self.table.removeRow(self.rows.index(record))
            self.rows.remove(record)
            self.table.fit_rows(hide_empty_header=True)
            self.changed.emit()

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            {"face": face.currentText()}
            | {
                key: int(editor.text()) if editor.text().strip() else None
                for key, editor in zip(
                    ("x", "y", "width", "height"), fields, strict=True
                )
            }
            for face, fields in self.rows
        ]

    @staticmethod
    def validate(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise ValueError("Blackout zones must be a list")
        for row in value:
            if (
                not isinstance(row, dict)
                or set(row) != {"face", "x", "y", "width", "height"}
                or row["face"] not in FACES
            ):
                raise ValueError("Blackout zone requires a screen and pixel rectangle")
            for key in ("x", "y", "width", "height"):
                v = row[key]
                if v is not None and (
                    type(v) is not int or v < 0 or key in ("width", "height") and v == 0
                ):
                    raise ValueError(
                        "Blackout rectangle requires nonnegative coordinates and positive dimensions"
                    )
        return value

    def restore(self, rows: list[dict[str, Any]]) -> None:
        self.table.setRowCount(0)
        self.rows.clear()
        for row in rows:
            self.add(row)
        self.table.fit_rows(hide_empty_header=True)
