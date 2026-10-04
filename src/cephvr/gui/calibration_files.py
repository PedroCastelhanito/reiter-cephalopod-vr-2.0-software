"""Versioned all-screen GUI calibration snapshots, separate from runtime mesh profiles."""

import json
import math
from pathlib import Path

from PyQt6.QtCore import QEvent, QIODevice, QSaveFile, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QFileDialog, QHBoxLayout, QLineEdit, QWidget

from cephvr.gui.components import button


class CalibrationFiles(QWidget):
    message = pyqtSignal(str)
    loaded = pyqtSignal()

    def __init__(self, fields: dict[str, QLineEdit | QCheckBox]) -> None:
        super().__init__()
        self.fields = fields
        self.dialog: QFileDialog | None = None
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.load_button = button("Load JSON…")
        self.save_button = button("Save as…")
        row.addWidget(self.load_button)
        row.addWidget(self.save_button)
        self.load_button.clicked.connect(lambda: self.choose(save=False))
        self.save_button.clicked.connect(lambda: self.choose(save=True))

    def snapshot(self) -> dict[str, object]:
        values: dict[str, object] = {}
        for key, editor in self.fields.items():
            if isinstance(editor, QCheckBox):
                values[key] = editor.isChecked()
            else:
                text = editor.text().strip()
                values[key] = float(text) if text else None
        result = {"format": "cephvr-rig-calibration", "version": 2, "values": values}
        self.validate(result)
        return result

    def validate(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict) or set(payload) != {
            "format",
            "version",
            "values",
        }:
            raise ValueError("Expected a CephVR rig calibration JSON")
        if (
            payload["format"] != "cephvr-rig-calibration"
            or type(payload["version"]) is not int
            or payload["version"] not in (1, 2)
        ):
            raise ValueError("Unsupported calibration format/version")
        values = payload["values"]
        if payload["version"] == 1 and isinstance(values, dict):
            values = dict(values)
            old_right = values.pop("screens.Right.subject_distance", None)
            if old_right is not None:
                inputs = [
                    values.get(key)
                    for key in (
                        "rig.width",
                        "rig.subject_x",
                        "screens.Left.subject_distance",
                    )
                ]
                if any(type(v) not in (int, float) for v in (*inputs, old_right)):
                    raise ValueError(
                        "Legacy right distance cannot be checked without width, subject position and left distance"
                    )
                width, subject_x, left = (
                    float(v) for v in inputs if isinstance(v, (int, float))
                )
                if not math.isclose(
                    old_right, width + left - 2 * subject_x, rel_tol=1e-9, abs_tol=1e-9
                ):
                    raise ValueError(
                        "Legacy calibration has unequal left/right wall offsets; current geometry requires equal offsets"
                    )
        if not isinstance(values, dict) or set(values) != set(self.fields):
            raise ValueError(
                "Calibration must contain every rig, projection and screen field"
            )
        for key, value in values.items():
            if isinstance(self.fields[key], QCheckBox):
                if type(value) is not bool:
                    raise ValueError(f"{key}: expected true or false")
            elif value is not None:
                if type(value) not in (float, int) or not math.isfinite(value):
                    raise ValueError(f"{key}: expected a finite number or null")
                name = key.rsplit(".", 1)[-1]
                if (
                    name
                    not in (
                        "offset_x",
                        "offset_y",
                        "subject_x",
                        "subject_y",
                        "subject_z",
                    )
                    and value <= 0
                ):
                    raise ValueError(f"{key}: must be positive")
        return values

    def load_path(self, path: str) -> None:
        if not self.isEnabled():
            return
        try:
            with Path(path).open("rb") as stream:
                data = stream.read(1_048_577)
            if len(data) > 1_048_576:
                raise ValueError("Calibration JSON exceeds 1 MiB")
            values = self.validate(json.loads(data))
            # Validate the complete document before changing any draft.
            for key, value in values.items():
                editor = self.fields[key]
                if isinstance(editor, QCheckBox):
                    editor.setChecked(bool(value))
                else:
                    editor.setText("" if value is None else str(value))
            self.loaded.emit()
            self.message.emit(f"Loaded all-screen calibration: {path}")
        except (
            OSError,
            ValueError,
            UnicodeError,
            RecursionError,
            OverflowError,
        ) as exc:
            self.message.emit(f"Calibration load failed: {exc}")

    def save_path(self, path: str) -> None:
        if not self.isEnabled():
            return
        try:
            data = (
                json.dumps(self.snapshot(), indent=2, allow_nan=False) + "\n"
            ).encode()
            output = QSaveFile(path)
            if not output.open(QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(output.errorString())
            if output.write(data) != len(data):
                output.cancelWriting()
                raise OSError(output.errorString())
            if not output.commit():
                raise OSError(output.errorString())
            self.message.emit(f"Saved all-screen calibration: {path}")
        except (OSError, ValueError, OverflowError) as exc:
            self.message.emit(f"Calibration save failed: {exc}")

    def choose(self, *, save: bool) -> None:
        if not self.isEnabled():
            return
        if self.dialog is not None:
            self.dialog.raise_()
            return
        dialog = QFileDialog(
            self, "Save rig calibration" if save else "Load rig calibration"
        )
        dialog.setNameFilter("CephVR calibration (*.json)")
        dialog.setDefaultSuffix("json")
        dialog.setAcceptMode(
            QFileDialog.AcceptMode.AcceptSave
            if save
            else QFileDialog.AcceptMode.AcceptOpen
        )
        dialog.setFileMode(
            QFileDialog.FileMode.AnyFile if save else QFileDialog.FileMode.ExistingFile
        )
        dialog.fileSelected.connect(
            lambda path: (
                (self.save_path(path) if save else self.load_path(path))
                if self.dialog is dialog
                else None
            )
        )
        dialog.finished.connect(lambda _: self.finish(dialog))
        self.dialog = dialog
        dialog.open()

    def finish(self, dialog: QFileDialog) -> None:
        if self.dialog is dialog:
            self.dialog = None
        dialog.deleteLater()

    def changeEvent(self, event: QEvent | None) -> None:  # noqa: N802
        super().changeEvent(event)
        if (
            event is not None
            and event.type() == QEvent.Type.EnabledChange
            and not self.isEnabled()
            and self.dialog is not None
        ):
            self.dialog.reject()
