"""Versioned all-screen GUI calibration snapshots, separate from runtime mesh profiles."""

import json
import math
from pathlib import Path

from PyQt6.QtCore import QEvent, QIODevice, QSaveFile, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QFileDialog, QHBoxLayout, QLineEdit, QWidget

from cephvr.gui.components import button
from cephvr.gui.configuration_files import LOCKED_REASON
from cephvr.gui.file_dialogs import file_dialog, open_file_dialog
from cephvr.gui.theme import SIZES
from cephvr.visual_stimulus.config.calibration_bars import reference_lengths


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
        self.sync_hints()

    def sync_hints(self) -> None:
        """A disabled Load/Save explains why; the owner disables the whole widget."""
        suffix = "" if self.isEnabled() else f"\n{LOCKED_REASON}"
        self.load_button.setToolTip("Load a calibration configuration JSON" + suffix)
        self.save_button.setToolTip("Save a calibration configuration JSON" + suffix)

    def snapshot(self) -> dict[str, object]:
        values: dict[str, object] = {}
        for key, editor in self.fields.items():
            if isinstance(editor, QCheckBox):
                values[key] = editor.isChecked()
            else:
                text = editor.text().strip()
                values[key] = (
                    (
                        int(text)
                        if key.endswith(
                            (
                                "valid_width_px",
                                "valid_height_px",
                                "offset_x_px",
                                "offset_y_px",
                            )
                        )
                        else float(text)
                    )
                    if text
                    else None
                )
        result = {"format": "cephvr-rig-calibration", "version": 8, "values": values}
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
            or payload["version"] not in (1, 2, 3, 4, 5, 6, 7, 8)
        ):
            raise ValueError("Unsupported calibration format/version")
        values = payload["values"]
        if isinstance(values, dict):
            values = dict(values)
            for name in (
                "near_mm",
                "far_mm",
                "positional_tolerance_mm",
                "orthogonality_tolerance",
            ):
                values.pop(f"projection.{name}", None)
        if payload["version"] < 7 and isinstance(values, dict):
            for face in ("Front", "Left", "Right", "Bottom"):
                for key in ("offset_x", "offset_y"):
                    values.pop(f"screens.{face}.{key}", None)
                for key in ("valid_width_px", "valid_height_px"):
                    value = values.get(f"screens.{face}.{key}")
                    if (
                        isinstance(value, (int, float))
                        and not isinstance(value, bool)
                        and math.isfinite(value)
                    ):
                        values[f"screens.{face}.{key}"] = round(value)
        legacy_scales = {}
        if payload["version"] < 6 and isinstance(values, dict):
            for face in ("Front", "Left", "Right", "Bottom"):
                for old, new in (
                    ("scale_u", "valid_width_px"),
                    ("scale_v", "valid_height_px"),
                ):
                    prefix = f"screens.{face}."
                    if prefix + old not in values or prefix + new in values:
                        raise ValueError(
                            "Legacy calibration has an invalid field inventory"
                        )
                    scale = values.pop(prefix + old)
                    if scale is not None and (
                        type(scale) not in (int, float)
                        or not math.isfinite(scale)
                        or scale <= 0
                    ):
                        raise ValueError("Legacy scale must be positive and finite")
                    legacy_scales[face, new] = 1.0 if scale is None else float(scale)
                    values[prefix + new] = None
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
            offsets = {
                key
                for key in self.fields
                if key.endswith(("offset_x_px", "offset_y_px"))
            }
            if set(values) != set(self.fields) - references - offsets:
                raise ValueError("Legacy calibration has an invalid field inventory")
            values.update(dict.fromkeys(references))
        if payload["version"] == 3 and isinstance(values, dict):
            pixel_lengths = {
                key
                for key in self.fields
                if key.endswith(("reference_x_px", "reference_y_px"))
            }
            offsets = {
                key
                for key in self.fields
                if key.endswith(("offset_x_px", "offset_y_px"))
            }
            if set(values) != set(self.fields) - pixel_lengths - offsets:
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
        if payload["version"] < 8 and isinstance(values, dict):
            for key in self.fields:
                if key.endswith(("offset_x_px", "offset_y_px")):
                    values.setdefault(key, None)
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
                    in (
                        "reference_x_px",
                        "reference_y_px",
                        "valid_width_px",
                        "valid_height_px",
                        "offset_x_px",
                        "offset_y_px",
                    )
                    and not float(value).is_integer()
                ):
                    raise ValueError(f"{key}: must be a whole pixel length")
                if (
                    name
                    not in (
                        "subject_x",
                        "subject_y",
                        "subject_z",
                        "offset_x_px",
                        "offset_y_px",
                    )
                    and value <= 0
                ):
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
        if payload["version"] < 5:
            values["screens.Bottom.width"], values["screens.Bottom.height"] = (
                values["screens.Bottom.height"],
                values["screens.Bottom.width"],
            )
        if legacy_scales:
            from cephvr.gui.calibration_profile import MonitorBinding, face_valid_area

            for face in ("Front", "Left", "Right", "Bottom"):
                prefix = f"screens.{face}."
                output_width, output_height = (
                    values.get(prefix + "reference_width_px"),
                    values.get(prefix + "reference_height_px"),
                )
                if any(
                    legacy_scales[face, key] != 1
                    for key in ("valid_width_px", "valid_height_px")
                ):
                    if not isinstance(output_width, (int, float)) or not isinstance(
                        output_height, (int, float)
                    ):
                        raise ValueError(
                            "Legacy non-neutral scale requires reference output dimensions before migration"
                        )
                    # Resolve at neutral mm/pixel; retain old bounds as a crop, never a stretch.
                    base = dict(values)
                    base[prefix + "offset_x"] = base[prefix + "offset_y"] = 0
                    rect = face_valid_area(
                        {"version": 6, "values": base},
                        face,
                        MonitorBinding(
                            "", 0, 0, int(output_width), int(output_height), 0, 0
                        ),
                    )
                    values[prefix + "valid_width_px"] = (
                        (rect[2] - rect[0])
                        * output_width
                        * legacy_scales[face, "valid_width_px"]
                    )
                    values[prefix + "valid_height_px"] = (
                        (rect[3] - rect[1])
                        * output_height
                        * legacy_scales[face, "valid_height_px"]
                    )
        for key, value in values.items():
            if (
                key.endswith(("valid_width_px", "valid_height_px"))
                and value is not None
            ):
                values[key] = int(round(value))
        return values

    def apply_snapshot(self, payload: object) -> None:
        values = self.validate(payload)
        for key, value in values.items():
            editor = self.fields[key]
            if isinstance(editor, QCheckBox):
                editor.setChecked(bool(value))
            else:
                text = "" if value is None else str(value)
                if key.endswith(
                    ("valid_width_px", "valid_height_px", "offset_x_px", "offset_y_px")
                ) and isinstance(value, (int, float)):
                    text = str(int(value))
                editor.setText(text)

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
        if event is None or event.type() != QEvent.Type.EnabledChange:
            return
        self.sync_hints()
        if not self.isEnabled() and self.dialog is not None:
            self.dialog.reject()
