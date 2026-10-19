"""Per-screen pulse authoring shared by runtime and local review."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWidgets import QLabel, QMessageBox

from cephvr.gui.projector_geometry import FACES
from cephvr.gui.projector_timing import ProjectorTiming, parse_patch
from cephvr.visual_stimulus.config.models.display_profile import (
    PhotodiodePatch,
    PixelRect,
)

if TYPE_CHECKING:
    from cephvr.gui.projectors import ProjectorsPanel
    from cephvr.gui.review_placement import ReviewPlacement

Rect = tuple[float, float, float, float]
Overlay = tuple[list[Rect], Rect | None]


def normalized(face: str, rect: PixelRect, size: tuple[int, int]) -> Rect:
    width, height = size
    if min(size) <= 0 or rect.x + rect.width > width or rect.y + rect.height > height:
        raise ValueError(f"Placement exceeds the {face} display")
    return rect.x / width, rect.y / height, rect.width / width, rect.height / height


KEYS = ("X", "Y", "Width", "Height")


def profile_pulse_drafts(
    profile: dict[str, Any], faces: Mapping[str, str]
) -> dict[str, dict[str, list[str]]]:
    patches = profile.get("photodiode_patches")
    if patches is None:
        patches = {profile.get("photodiode_output_id"): profile.get("photodiode_patch")}
    if not isinstance(patches, dict):
        raise ValueError("Expected per-output photodiode patches")
    if any(
        patch is not None and output_id is not None and output_id not in faces
        for output_id, patch in patches.items()
    ):
        raise ValueError("Photodiode patch has no assigned screen")
    drafts = {}
    for output_id, face in faces.items():
        patch = patches.get(output_id)
        if face not in FACES or patch is None:
            continue
        parsed = PhotodiodePatch.model_validate_json(json.dumps(patch))
        frame, pulse = parsed.background_rect or parsed.rect, parsed.rect
        drafts[face] = dict(
            frame=[str(v) for v in (frame.x, frame.y, frame.width, frame.height)],
            pulse=[
                str(v)
                for v in (
                    pulse.x - frame.x,
                    pulse.y - frame.y,
                    pulse.width,
                    pulse.height,
                )
            ]
            if parsed.background_rect
            else [""] * 4,
        )
    return drafts


class ProjectorPulses(ProjectorTiming):
    def __init__(self, panel: ProjectorsPanel, *, local_preview: bool = False) -> None:
        super().__init__()
        self.panel = panel
        self.drafts: dict[str, dict[str, list[str]]] = {}
        self.face: str | None = None
        self.preview: ReviewPlacement | None = None
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.body.addWidget(self.summary)
        self.mode.setItemText(1, "VSync on pulse displays")
        self.target.currentIndexChanged.connect(self.select_screen)
        for edit in (*self.fields.values(), *self.pulse_fields.values()):
            edit.textChanged.connect(self.edited)
        self.pulse.toggled.connect(self.refresh_summary)
        self.mode.currentIndexChanged.connect(self.refresh_summary)
        if local_preview:
            self.placement_button.clicked.connect(self.open_preview)
        panel.outputs_changed.connect(self.refresh_summary)
        self.refresh_summary()

    @property
    def presentation_mode(self) -> str:
        return ("free_run", "photodiode_only_vsync", "all_outputs_vsync")[
            self.mode.currentIndex()
        ]

    def set_presentation_mode(self, mode: str) -> None:
        self.mode.setCurrentIndex(
            ("free_run", "photodiode_only_vsync", "all_outputs_vsync").index(mode)
        )

    def restore_mode_label(self, name: str) -> None:
        if name in (
            "VSync on pulse display",
            "Selected display VSync",
            "VSync on pulse displays",
        ):
            self.mode.setCurrentIndex(1)
        else:
            super().restore_mode_label(name)

    def refresh_controls(self) -> None:
        super().refresh_controls()
        if not self.can_edit and getattr(self, "preview", None) is not None:
            assert self.preview is not None
            self.preview.close()

    def restore_drafts(self, value: object) -> None:
        validate_drafts(value)
        assert isinstance(value, dict)
        self.drafts = {
            face: {key: list(items) for key, items in draft.items()}
            for face, draft in value.items()
        }
        if self.panel.pulse_face() is None:
            self.face = None
            self.refresh_summary()
        else:
            self.select_screen()

    def select_screen(self) -> None:
        try:
            self.face = self.panel.pulse_face()
        except ValueError:
            self.face = None
        draft = self.drafts.get(self.face or "", {})
        for name, fields in (("frame", self.fields), ("pulse", self.pulse_fields)):
            for key, value in zip(KEYS, draft.get(name, [""] * 4), strict=True):
                with QSignalBlocker(fields[key]):
                    fields[key].setText(value)
        self.refresh_summary()

    def edited(self) -> None:
        if self.panel.loading:
            return
        if self.face in FACES:
            self.drafts[self.face] = {
                "frame": [self.fields[key].text() for key in KEYS],
                "pulse": [self.pulse_fields[key].text() for key in KEYS],
            }
        self.refresh_summary()

    def patches(
        self, *, strict: bool = True, enabled_only: bool = True
    ) -> dict[str, PhotodiodePatch]:
        patches: dict[str, PhotodiodePatch] = {}
        if enabled_only and not self.pulse.isChecked():
            return patches
        for face, draft in self.drafts.items():
            try:
                patch = parse_patch(
                    [v.strip() for v in draft["frame"]],
                    [v.strip() for v in draft["pulse"]],
                )
                if patch is not None:
                    patches[face] = PhotodiodePatch.model_validate(
                        dict(
                            **patch, high_linear_rgb=(1, 1, 1), low_linear_rgb=(0, 0, 0)
                        )
                    )
            except ValueError:
                if strict:
                    raise
        return patches

    def install_overlays(
        self,
        profile: dict[str, Any],
        assignments: Mapping[str, str],
        output_by_identity: Mapping[str, dict[str, Any]],
    ) -> None:
        from contextlib import ExitStack

        with ExitStack() as stack:
            for edit in (*self.fields.values(), *self.pulse_fields.values()):
                stack.enter_context(QSignalBlocker(edit))
            super().install_overlays(profile, assignments, output_by_identity)
        self.restore_drafts(
            profile_pulse_drafts(
                profile,
                {
                    output["output_id"]: assignments.get(identity, "")
                    for identity, output in output_by_identity.items()
                },
            )
        )

    def vsync_faces(self) -> tuple[str, ...]:
        enabled = self.panel.enabled_screens
        if self.presentation_mode == "all_outputs_vsync":
            return enabled
        if self.presentation_mode == "free_run":
            return ()
        return tuple(face for face in enabled if face in self.patches(strict=False))

    def refresh_summary(self) -> None:
        faces = tuple(face for face in FACES if face in self.patches(strict=False))
        self.summary.setText(
            "Pulses: "
            + (", ".join(faces) or "None")
            + " · VSync: "
            + (", ".join(self.vsync_faces()) or "None")
        )
        if self.preview is not None:
            self.preview.update_patches()

    def open_preview(self) -> None:
        if not self.panel.can_review:
            return
        if self.preview is not None:
            self.preview.close()
            return
        from cephvr.gui.review_placement import ReviewPlacement

        try:
            self.preview_overlays(self.resolutions(), self.face)
        except ValueError as exc:
            QMessageBox.warning(self, "Photodiode placement", str(exc))
            return
        self.preview = ReviewPlacement(self)
        self.preview.finished.connect(self.close_preview)
        self.placement_button.setText("Close")
        self.preview.show()

    def close_preview(self) -> None:
        self.preview = None
        self.placement_button.setText("Launch photodiode placement")

    def resolutions(self) -> dict[str, tuple[int, int]]:
        return {
            self.panel.assignments[key]: size
            for key, size in self.panel.display_pixels.items()
            if self.panel.assignments.get(key) in self.panel.enabled_screens
        }

    def preview_overlays(
        self, resolutions: dict[str, tuple[int, int]], target_face: str | None
    ) -> dict[str, Overlay]:
        result = super().preview_overlays(
            resolutions, target_face if self.face is None else None
        )
        for face, patch in self.patches().items():
            if face not in resolutions:
                raise ValueError(f"Assign and enable a display for {face}")
            size = resolutions[face]
            masks = result.setdefault(face, ([], None))[0]
            if patch.background_rect is not None:
                masks.append(normalized(face, patch.background_rect, size))
            result[face] = masks, normalized(face, patch.rect, size)
        return result


def validate_drafts(value: object) -> None:
    if not isinstance(value, dict) or any(
        face not in FACES
        or not isinstance(draft, dict)
        or set(draft) != {"frame", "pulse"}
        or any(
            not isinstance(items, list)
            or len(items) != 4
            or any(not isinstance(text, str) for text in items)
            for items in draft.values()
        )
        for face, draft in value.items()
    ):
        raise ValueError("Expected per-screen photodiode Frame/Pulse drafts")
