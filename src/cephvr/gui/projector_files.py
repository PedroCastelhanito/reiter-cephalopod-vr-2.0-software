"""Portable projector settings and calibration references, without monitor assignments."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from PyQt6.QtWidgets import QCheckBox, QLineEdit

from cephvr.gui.calibration_files import CalibrationFiles
from cephvr.gui.projector_geometry import FACES
from cephvr.gui.projector_profile import portable_profile
from cephvr.gui.projector_timing import ProjectorTiming


class ProjectorFiles(CalibrationFiles):
    def __init__(
        self,
        fields: dict[str, QLineEdit | QCheckBox],
        timing: ProjectorTiming,
        participation: Callable[[], dict[str, bool]],
        apply_participation: Callable[[dict[str, bool]], None],
        target_face: Callable[[], str | None],
        select_target: Callable[[str | None], None],
    ) -> None:
        super().__init__(fields)
        self.timing = timing
        self.read_participation = participation
        self.apply_participation = apply_participation
        self.target_face = target_face
        self.select_target = select_target
        self.profile: dict[str, Any] | None = None

    def calibration_snapshot(self) -> dict[str, object]:
        return super().snapshot()

    def snapshot(self) -> dict[str, object]:
        result = self.calibration_snapshot()
        result.update(
            version=4,
            settings={
                "enabled_screens": self.read_participation(),
                "photodiode_enabled": self.timing.pulse.isChecked(),
                "pulse_screen": self.target_face(),
                "vsync_mode": self.timing.mode.currentText(),
                "pulse_rect": {
                    key: int(edit.text()) if edit.text().strip() else None
                    for key, edit in self.timing.fields.items()
                },
            },
            screen_profile=copy.deepcopy(self.profile),
        )
        self.validate(result)
        return result

    def validate(self, payload: object) -> dict[str, object]:
        if (
            isinstance(payload, dict)
            and payload.get("version") in (3, 4)
            and "settings" in payload
        ):
            if type(payload["version"]) is not int or set(payload) != {
                "format",
                "version",
                "values",
                "settings",
                "screen_profile",
            }:
                raise ValueError("Expected complete projector configuration")
            values = super().validate(
                {
                    "format": payload["format"],
                    "version": payload["version"] - 1,
                    "values": payload["values"],
                }
            )
            settings = payload["settings"]
            if not isinstance(settings, dict) or set(settings) != {
                "enabled_screens",
                "photodiode_enabled",
                "pulse_screen",
                "vsync_mode",
                "pulse_rect",
            }:
                raise ValueError("Expected all projector synchronization settings")
            enabled = settings["enabled_screens"]
            if not isinstance(enabled, dict) or any(
                face not in FACES or type(value) is not bool
                for face, value in enabled.items()
            ):
                raise ValueError(
                    "Screen participation requires known faces and booleans"
                )
            if type(settings["photodiode_enabled"]) is not bool:
                raise ValueError("Photodiode enable must be boolean")
            if settings["pulse_screen"] not in (*FACES, None):
                raise ValueError("Pulse screen must be a rig face or null")
            if settings["vsync_mode"] not in (
                "Selected display VSync",
                "All displays VSync",
            ):
                raise ValueError("Unsupported VSync mode")
            rect = settings["pulse_rect"]
            if not isinstance(rect, dict) or set(rect) != set(self.timing.fields):
                raise ValueError("Expected all pulse rectangle fields")
            for key, value in rect.items():
                if value is not None and (
                    type(value) is not int
                    or value < 0
                    or (key in ("Width", "Height") and value == 0)
                ):
                    raise ValueError(
                        f"Pulse {key}: expected valid integer pixels or null"
                    )
            profile = payload["screen_profile"]
            if profile is not None:
                if (
                    not isinstance(profile, dict)
                    or portable_profile(profile) != profile
                ):
                    raise ValueError(
                        "Screen profile must exclude physical display bindings"
                    )
            return values
        return super().validate(payload)

    def apply_snapshot(self, payload: object) -> None:
        # Legacy runtime profiles remain loadable through the same file action.
        if isinstance(payload, dict) and "outputs" in payload and "mappings" in payload:
            profile = portable_profile(payload)
            converted = super().snapshot()
            converted.update(version=4, screen_profile=profile)
            outputs = payload["outputs"]
            if not isinstance(outputs, list) or any(
                not isinstance(o, dict) for o in outputs
            ):
                raise ValueError("Display profile requires output objects")
            ids = [output.get("output_id") for output in outputs]
            if any(not isinstance(oid, str) or not oid for oid in ids) or len(
                set(ids)
            ) != len(ids):
                raise ValueError("Display profile requires unique nonempty output IDs")
            if any(
                mapping.get("output_id") not in ids for mapping in payload["mappings"]
            ):
                raise ValueError("Screen mapping references an unknown legacy output")
            face_outputs = {
                m["surface_id"].title(): m.get("output_id") for m in payload["mappings"]
            }
            target = payload.get("photodiode_output_id")
            patch_config = payload.get("photodiode_patch", {})
            if not isinstance(patch_config, dict) or not isinstance(
                patch_config.get("rect", {}), dict
            ):
                raise ValueError("Photodiode patch requires an object rectangle")
            patch = patch_config.get("rect", {})
            converted["settings"] = {
                "enabled_screens": {
                    face: next(
                        (
                            o.get("enabled", True)
                            for o in outputs
                            if o.get("output_id") == oid
                        ),
                        True,
                    )
                    for face, oid in face_outputs.items()
                },
                "photodiode_enabled": payload.get("photodiode_enabled", True),
                "pulse_screen": next(
                    (f for f, oid in face_outputs.items() if oid == target), None
                ),
                "vsync_mode": "All displays VSync"
                if payload.get("presentation_mode") == "all_outputs_vsync"
                else "Selected display VSync",
                "pulse_rect": {
                    key: patch.get(key.lower()) for key in self.timing.fields
                },
            }
            payload = converted
        self.validate(payload)
        assert isinstance(payload, dict)
        numeric = {key: payload[key] for key in ("format", "version", "values")}
        numeric["version"] = (
            payload["version"] - 1 if "settings" in payload else payload["version"]
        )
        super().apply_snapshot(numeric)
        if "settings" in payload:
            settings = payload["settings"]
            self.profile = copy.deepcopy(payload["screen_profile"])
            self.apply_participation(settings["enabled_screens"])
            self.timing.pulse.setChecked(settings["photodiode_enabled"])
            self.timing.mode.setCurrentText(settings["vsync_mode"])
            for key, value in settings["pulse_rect"].items():
                self.timing.fields[key].setText("" if value is None else str(value))
            self.select_target(settings["pulse_screen"])
