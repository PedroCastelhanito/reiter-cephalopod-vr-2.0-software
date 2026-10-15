"""Independent pulse-placement and presentation-pacing drafts."""

from collections.abc import Mapping
from typing import Any

from PyQt6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHeaderView,
    QLineEdit,
    QSizePolicy,
    QTableWidgetItem,
    QWidget,
)

from cephvr.gui.components import Card, button, combo, field
from cephvr.gui.device_panel import entry
from cephvr.gui.projector_blackouts import BlackoutZones
from cephvr.gui.projector_geometry import FACES
from cephvr.gui.tables import DataTable
from cephvr.gui.theme import SIZES

MODE_LABELS = {
    "free_run": "Free run (no VSync)",
    "photodiode_only_vsync": "VSync on pulse display",
    "all_outputs_vsync": "VSync on all displays",
}
LEGACY_MODE_LABELS = {
    "Selected display VSync": "VSync on pulse display",
    "All displays VSync": "VSync on all displays",
}


class ProjectorTiming(Card):
    def __init__(self) -> None:
        super().__init__("Photodiode & synchronization")
        self.pulse = QCheckBox("Enable photodiode pulse")
        self.caption.setWordWrap(True)
        caption_policy = self.caption.sizePolicy()
        caption_policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
        caption_policy.setVerticalPolicy(QSizePolicy.Policy.Preferred)
        caption_policy.setHeightForWidth(True)
        self.caption.setSizePolicy(caption_policy)
        self.header.setStretch(0, 1)
        self.body.addWidget(self.pulse)
        self.target = combo(())
        self.target.setPlaceholderText("Select display")
        self.mode = combo(tuple(MODE_LABELS.values()))
        self.set_presentation_mode("photodiode_only_vsync")
        self.fields: dict[str, QLineEdit] = {}
        self.options = QWidget()
        grid = QGridLayout(self.options)
        grid.setContentsMargins(0, SIZES.section_toggle_gap, 0, 0)
        grid.addWidget(field("PULSE DISPLAY", self.target), 0, 0, 1, 2)
        self.body.insertWidget(0, field("VSYNC MODE", self.mode))
        self.pulse_fields: dict[str, QLineEdit] = {}
        self.definition = DataTable(2, 5)
        self.definition.setAccessibleName("Photodiode pulse definition")
        self.definition.setHorizontalHeaderLabels(
            ["", "Origin X", "Origin Y", "Width", "Height"]
        )
        header = self.definition.horizontalHeader()
        assert header is not None
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for row, (title, fields) in enumerate(
            (("Frame", self.fields), ("Pulse", self.pulse_fields))
        ):
            self.definition.setItem(row, 0, QTableWidgetItem(title))
            for column, name in enumerate(("X", "Y", "Width", "Height"), 1):
                edit = entry("px")
                edit.setMinimumWidth(0)
                edit.setAccessibleName(f"Photodiode {title} {name}")
                edit.setToolTip(
                    "Output pixels, origin bottom-left"
                    if title == "Frame"
                    else "Pixels inside the Frame; origin relative to its bottom-left corner"
                )
                fields[name] = edit
                self.definition.set_control(row, column, edit)
        self.definition.fit_rows()
        grid.addWidget(self.definition, 1, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.placement_button = button("Launch photodiode placement")
        self.body.addWidget(self.placement_button)
        self.body.addWidget(self.options)
        self.blackouts = BlackoutZones()
        self.pulse.toggled.connect(self.refresh_controls)
        self.can_edit = False
        self.refresh_controls()

    @property
    def presentation_mode(self) -> str:
        return next(
            key for key, name in MODE_LABELS.items() if name == self.mode.currentText()
        )

    def set_presentation_mode(self, mode: str) -> None:
        self.mode.setCurrentText(MODE_LABELS[mode])

    def restore_mode_label(self, name: str) -> None:
        self.mode.setCurrentText(LEGACY_MODE_LABELS.get(name, name))

    def set_displays(self, displays: list[tuple[str, str, bool]]) -> None:
        selected, text = self.target.currentData(), self.target.currentText()
        self.target.blockSignals(True)
        self.target.clear()
        for key, name, _enabled in displays:
            self.target.addItem(name, key)
        if selected is not None and self.target.findData(selected) < 0:
            self.target.addItem(
                f"{text.removesuffix(' (unavailable)')} (unavailable)", selected
            )
        self.target.setCurrentIndex(
            self.target.findData(selected) if selected is not None else -1
        )
        self.target.blockSignals(False)

    def refresh_controls(self) -> None:
        self.mode.setEnabled(self.can_edit)
        self.pulse.setEnabled(self.can_edit)
        self.options.setEnabled(self.can_edit and self.pulse.isChecked())
        self.blackouts.setEnabled(self.can_edit)

    def patch_draft(self) -> dict[str, object] | None:
        raw = [self.fields[k].text().strip() for k in ("X", "Y", "Width", "Height")]
        pulse = [
            self.pulse_fields[k].text().strip() for k in ("X", "Y", "Width", "Height")
        ]
        if not any(raw + pulse):
            return None
        if not all(v.isdecimal() for v in raw):
            raise ValueError(
                "Photodiode Frame requires integer pixel coordinates and dimensions"
            )
        x, y, width, height = map(int, raw)
        area = dict(x=x, y=y, width=width, height=height)
        if not any(pulse):
            return {"rect": area, "background_rect": None}
        if not all(v.isdecimal() for v in pulse):
            raise ValueError(
                "Photodiode Pulse requires X, Y, Width and Height in integer pixels"
            )
        px, py, pw, ph = map(int, pulse)
        if min(pw, ph) <= 0 or px + pw > width or py + ph > height:
            raise ValueError("Photodiode Pulse must fit inside its Frame")
        return {
            "background_rect": area,
            "rect": dict(x=x + px, y=y + py, width=pw, height=ph),
        }

    def preview_overlays(
        self, resolutions: dict[str, tuple[int, int]], target_face: str | None
    ) -> dict[
        str,
        tuple[
            list[tuple[float, float, float, float]],
            tuple[float, float, float, float] | None,
        ],
    ]:
        from cephvr.visual_stimulus.config.models.display_profile import PixelRect

        result: dict[
            str,
            tuple[
                list[tuple[float, float, float, float]],
                tuple[float, float, float, float] | None,
            ],
        ] = {}

        def normalized(face: str, raw: object) -> tuple[float, float, float, float]:
            rect = PixelRect.model_validate(raw)
            if face not in resolutions:
                raise ValueError(f"Assign a display to {face} to preview output masks")
            width, height = resolutions[face]
            if min(width, height) <= 0:
                raise ValueError(f"{face} output dimensions must be positive")
            if rect.x + rect.width > width or rect.y + rect.height > height:
                raise ValueError(f"Output mask exceeds the {face} display")
            return (
                rect.x / width,
                rect.y / height,
                rect.width / width,
                rect.height / height,
            )

        for zone in self.blackouts.snapshot():
            face = zone["face"]
            masks, square = result.setdefault(face, ([], None))
            masks.append(
                normalized(face, {k: zone[k] for k in ("x", "y", "width", "height")})
            )
        if self.pulse.isChecked() and target_face is not None:
            patch = self.patch_draft()
            if patch is not None:
                masks = result.setdefault(target_face, ([], None))[0]
                if patch.get("background_rect") is not None:
                    masks.append(normalized(target_face, patch["background_rect"]))
                result[target_face] = (masks, normalized(target_face, patch["rect"]))
        return result

    def install_overlays(
        self,
        profile: dict[str, Any],
        assignments: Mapping[str, str],
        output_by_identity: Mapping[str, dict[str, Any]],
    ) -> None:
        patch = profile.get("photodiode_patch")
        if isinstance(patch, dict) and isinstance(patch.get("rect"), dict):
            rect = patch.get("background_rect") or patch["rect"]
            for key, value in zip(
                ("X", "Y", "Width", "Height"),
                (rect.get("x"), rect.get("y"), rect.get("width"), rect.get("height")),
                strict=True,
            ):
                if type(value) is int:
                    self.fields[key].setText(str(value))
            pulse = patch["rect"]
            values = (
                (
                    pulse["x"] - rect["x"],
                    pulse["y"] - rect["y"],
                    pulse["width"],
                    pulse["height"],
                )
                if patch.get("background_rect")
                else (None, None, None, None)
            )
            for key, value in zip(("X", "Y", "Width", "Height"), values, strict=True):
                self.pulse_fields[key].setText("" if value is None else str(value))
        self.blackouts.restore(
            [
                dict(face=assignments[identity], **rect)
                for identity, output in output_by_identity.items()
                if assignments.get(identity) in FACES
                for rect in output.get("blackout_zones", [])
            ]
        )
