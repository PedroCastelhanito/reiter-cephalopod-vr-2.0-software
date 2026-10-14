"""Versioned all-screen GUI calibration snapshots, separate from runtime mesh profiles."""

import json
import math
from pathlib import Path

from PyQt6.QtCore import QEvent, QIODevice, QSaveFile, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QFileDialog, QHBoxLayout, QLineEdit, QWidget

from cephvr.gui.calibration_profile import KEYSTONE_KEYS, MARGIN_KEYS
from cephvr.gui.components import button
from cephvr.gui.file_dialogs import file_dialog, open_file_dialog
from cephvr.gui.theme import SIZES
from cephvr.visual_stimulus.config.calibration_bars import (
    reference_lengths,
    reference_scale,
)

CURRENT_VERSION = 6
# Versions up to 4 stored a centered scale plus pixel offset instead of edge margins;
# versions up to 5 had no keystone.
LEGACY_CORRECTION_KEYS = ("scale_u", "scale_v", "offset_x", "offset_y")


def _unique_members(pairs: list[tuple[str, object]]) -> dict[str, object]:
    values: dict[str, object] = {}
    for key, value in pairs:
        if key in values:
            raise ValueError(f"Duplicate configuration key: {key}")
        values[key] = value
    return values


class CalibrationFiles(QWidget):
    message = pyqtSignal(str)
    loaded = pyqtSignal()

    def __init__(self, fields: dict[str, QLineEdit | QCheckBox]) -> None:
        super().__init__()
        self.fields = fields
        self.dialog: QFileDialog | None = None
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SIZES.field_x_gap)
        self.load_button = button("Load…")
        self.save_button = button("Save as…")
        row.addWidget(self.load_button, 1)
        row.addWidget(self.save_button, 1)
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
        result = {
            "format": "cephvr-rig-calibration",
            "version": CURRENT_VERSION,
            "values": values,
        }
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
            or payload["version"] not in range(1, CURRENT_VERSION + 1)
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
        if payload["version"] in (1, 2) and isinstance(values, dict):
            values = dict(values)
            references = {
                key
                for key in self.fields
                if key.rsplit(".", 1)[-1].startswith("reference_")
            }
            if set(values) != self._inventory(4) - references:
                raise ValueError("Legacy calibration has an invalid field inventory")
            values.update(dict.fromkeys(references))
        if payload["version"] == 3 and isinstance(values, dict):
            pixel_lengths = {
                key
                for key in self.fields
                if key.endswith(("reference_x_px", "reference_y_px"))
            }
            if set(values) != self._inventory(4) - pixel_lengths:
                raise ValueError("Legacy calibration has an invalid field inventory")
            values = dict(values)
            for face in ("Front", "Left", "Right", "Bottom"):
                ref_width = values.get(f"screens.{face}.reference_width_px")
                ref_height = values.get(f"screens.{face}.reference_height_px")
                lengths = (
                    reference_lengths(ref_width, ref_height)
                    if isinstance(ref_width, (int, float))
                    and isinstance(ref_height, (int, float))
                    else (None, None)
                )
                for axis, length in zip(("x", "y"), lengths, strict=True):
                    values[f"screens.{face}.reference_{axis}_px"] = length
        if payload["version"] < CURRENT_VERSION and isinstance(values, dict):
            if set(values) != self._inventory(payload["version"]):
                raise ValueError(
                    "Calibration must contain every rig, projection and screen field"
                )
            if payload["version"] <= 4:
                values = self._margins_from_legacy(values)
            values = {**values, **dict.fromkeys(self._keystone_fields())}
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
                    name in ("reference_x_px", "reference_y_px")
                    and not float(value).is_integer()
                ):
                    raise ValueError(f"{key}: must be a whole pixel length")
                if name in KEYSTONE_KEYS:
                    pass  # Signed: the sign says which edge is narrower.
                elif name in MARGIN_KEYS:
                    if value < 0:
                        raise ValueError(f"{key}: must not be negative")
                elif name not in ("subject_x", "subject_y", "subject_z") and value <= 0:
                    raise ValueError(f"{key}: must be positive")
        for face in ("Front", "Left", "Right", "Bottom"):
            ref_width = values.get(f"screens.{face}.reference_width_px")
            ref_height = values.get(f"screens.{face}.reference_height_px")
            if isinstance(ref_width, (int, float)) and isinstance(
                ref_height, (int, float)
            ):
                reference_lengths(
                    ref_width,
                    ref_height,
                    values.get(f"screens.{face}.reference_x_px"),
                    values.get(f"screens.{face}.reference_y_px"),
                )
        return values

    def _keystone_fields(self) -> set[str]:
        return {key for key in self.fields if key.rsplit(".", 1)[-1] in KEYSTONE_KEYS}

    def _inventory(self, version: int) -> set[str]:
        """Field names a file of this numeric version must contain."""
        names = set(self.fields)
        if version < 6:
            names -= self._keystone_fields()
        if version <= 4:
            faces = {
                key.rsplit(".", 1)[0]
                for key in self.fields
                if key.rsplit(".", 1)[-1] in MARGIN_KEYS
            }
            names = {key for key in names if key.rsplit(".", 1)[-1] not in MARGIN_KEYS}
            names |= {
                f"{face}.{key}" for face in faces for key in LEGACY_CORRECTION_KEYS
            }
        return names

    def _margins_from_legacy(self, values: dict[str, object]) -> dict[str, object]:
        """Convert a centered scale/offset correction to the equivalent edge margins.

        A file without the output size cannot be converted exactly, so its manual
        correction is dropped and the margins fall back to automatic.
        """
        values = dict(values)
        faces = {
            key.rsplit(".", 1)[0]
            for key in self.fields
            if key.rsplit(".", 1)[-1] in MARGIN_KEYS
        }
        for face in faces:
            scale_x, scale_y, shift_x, shift_y = (
                values.pop(f"{face}.{key}") for key in LEGACY_CORRECTION_KEYS
            )
            margins: tuple[float, ...] | None = None
            width, height = (
                values.get(f"{face}.reference_{a}_px") for a in ("width", "height")
            )
            customized = any(
                value is not None and value != default
                for value, default in (
                    (scale_x, 1),
                    (scale_y, 1),
                    (shift_x, 0),
                    (shift_y, 0),
                )
            )
            if (
                customized
                and isinstance(width, (int, float))
                and isinstance(height, (int, float))
                and width > 0
                and height > 0
            ):
                fraction_x = 1.0 if scale_x is None else float(scale_x)  # type: ignore[arg-type]
                fraction_y = 1.0 if scale_y is None else float(scale_y)  # type: ignore[arg-type]
                measured = [
                    values.get(f"{face}.{key}")
                    for key in ("reference_x_mm", "reference_y_mm", "width", "height")
                ]
                if all(isinstance(v, (int, float)) and v > 0 for v in measured):
                    try:
                        fit = reference_scale(
                            width,
                            height,
                            measured[0],  # type: ignore[arg-type]
                            measured[1],  # type: ignore[arg-type]
                            x_px=values.get(f"{face}.reference_x_px"),  # type: ignore[arg-type]
                            y_px=values.get(f"{face}.reference_y_px"),  # type: ignore[arg-type]
                        )
                        fraction_x *= measured[2] / fit.projected_width_mm  # type: ignore[operator]
                        fraction_y *= measured[3] / fit.projected_height_mm  # type: ignore[operator]
                    except ValueError:
                        pass
                center_x = 0.5 + float(shift_x or 0) / width  # type: ignore[arg-type]
                center_y = 0.5 + float(shift_y or 0) / height  # type: ignore[arg-type]
                candidate = (
                    (center_x - fraction_x / 2) * width,
                    (1 - center_x - fraction_x / 2) * width,
                    (1 - center_y - fraction_y / 2) * height,
                    (center_y - fraction_y / 2) * height,
                )
                if min(candidate) >= -1e-6 and (
                    candidate[0] + candidate[1] < width
                    and candidate[2] + candidate[3] < height
                ):
                    margins = tuple(round(max(0.0, v), 4) for v in candidate)
            for index, key in enumerate(MARGIN_KEYS):
                values[f"{face}.{key}"] = None if margins is None else margins[index]
        return values

    def apply_snapshot(self, payload: object) -> None:
        values = self.validate(payload)
        for key, value in values.items():
            editor = self.fields[key]
            if isinstance(editor, QCheckBox):
                editor.setChecked(bool(value))
            else:
                editor.setText("" if value is None else str(value))

    def load_path(self, path: str) -> None:
        if not self.isEnabled():
            return
        try:
            with Path(path).open("rb") as stream:
                data = stream.read(1_048_577)
            if len(data) > 1_048_576:
                raise ValueError("Projector configuration JSON exceeds 1 MiB")
            # Validate the complete document before changing any draft.
            self.apply_snapshot(json.loads(data, object_pairs_hook=_unique_members))
            self.loaded.emit()
            self.message.emit(f"Loaded projector configuration: {path}")
        except (
            OSError,
            ValueError,
            UnicodeError,
            RecursionError,
            OverflowError,
        ) as exc:
            self.message.emit(f"Configuration load failed: {exc}")

    def save_path(self, path: str) -> None:
        if not self.isEnabled():
            return
        try:
            data = (
                json.dumps(self.snapshot(), indent=2, allow_nan=False) + "\n"
            ).encode()
            if len(data) > 1_048_576:
                raise ValueError("Projector configuration JSON exceeds 1 MiB")
            output = QSaveFile(path)
            if not output.open(QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(output.errorString())
            if output.write(data) != len(data):
                output.cancelWriting()
                raise OSError(output.errorString())
            if not output.commit():
                raise OSError(output.errorString())
            self.message.emit(f"Saved projector configuration: {path}")
        except (OSError, ValueError, OverflowError) as exc:
            self.message.emit(f"Configuration save failed: {exc}")

    def choose(self, *, save: bool) -> None:
        if not self.isEnabled():
            return
        if self.dialog is not None:
            self.dialog.raise_()
            return
        dialog = file_dialog(
            self,
            "Save projector configuration" if save else "Load projector configuration",
        )
        dialog.setNameFilter("CephVR projector configuration (*.json)")
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
        open_file_dialog(dialog)

    def finish(self, dialog: QFileDialog) -> None:
        if self.dialog is dialog:
            self.dialog = None
        dialog.deleteLater()

    def changeEvent(self, event: QEvent | None) -> None:
        super().changeEvent(event)
        if (
            event is not None
            and event.type() == QEvent.Type.EnabledChange
            and not self.isEnabled()
            and self.dialog is not None
        ):
            self.dialog.reject()
