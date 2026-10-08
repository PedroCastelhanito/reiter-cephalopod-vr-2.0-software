"""Focused snapshot of configured screen planes for planning, without output ownership."""

import math
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from cephvr.gui.calibration_profile import MonitorBinding, face_mapping
from cephvr.gui.projector_geometry import (
    RigDimensions,
    resolved_screens,
    screen_corners,
)


@dataclass(frozen=True)
class PreviewCorrection:
    corners: tuple[tuple[float, float], ...] = ()
    error: str = ""

    @classmethod
    def from_draft(
        cls, face: str, draft: dict[str, str], resolution: tuple[int, int] | None
    ) -> "PreviewCorrection":
        try:
            values: dict[str, object] = {}
            for key in (
                "scale_u",
                "scale_v",
                "offset_x",
                "offset_y",
                "width",
                "height",
                "throw",
                "reference_width_px",
                "reference_height_px",
                "reference_x_mm",
                "reference_y_mm",
            ):
                text = draft.get(key, "").strip()
                values[f"screens.{face}.{key}"] = float(text) if text else None
            for key in ("flip_x", "flip_y"):
                text = draft.get(key, "False").lower()
                if text not in ("true", "false"):
                    raise ValueError(f"{face} {key} must be true or false")
                values[f"screens.{face}.{key}"] = text == "true"
            if (
                any(
                    values[f"screens.{face}.{key}"] not in (None, 0.0)
                    for key in ("offset_x", "offset_y")
                )
                and resolution is None
            ):
                raise ValueError(f"Assign a display to {face} to resolve pixel offsets")
            if resolution is None and any(
                values[f"screens.{face}.reference_{axis}_mm"] is not None
                for axis in ("x", "y")
            ):
                raise ValueError(
                    f"Assign a display to {face} to resolve reference bars"
                )
            width, height = resolution or (1, 1)
            if min(width, height) <= 0:
                raise ValueError(f"{face} display resolution must be positive")
            vertices, _ = face_mapping(
                {"values": values}, face, MonitorBinding("", 0, 0, width, height, 0, 0)
            )
            return cls(tuple(vertices[i]["xy"] for i in (0, 1, 3, 2)))
        except (ValueError, TypeError) as error:
            return cls(error=str(error))


@dataclass(frozen=True)
class PreviewSurface:
    width: float
    height: float
    corners: tuple[tuple[float, float, float], ...] = ()
    correction: PreviewCorrection | None = None


@dataclass(frozen=True)
class PreviewGeometry:
    surfaces: dict[str, PreviewSurface]
    observer: tuple[float, float, float] | None
    rig: RigDimensions | None = None

    @classmethod
    def from_drafts(
        cls,
        rig: RigDimensions | None,
        drafts: dict[str, dict[str, str]],
        resolutions: dict[str, tuple[int, int]] | None = None,
    ) -> "PreviewGeometry":
        resolved = resolved_screens(rig, drafts)
        result = {}
        for face, values in resolved.items():
            try:
                width, height = float(values["width"]), float(values["height"])
                if not all(math.isfinite(v) and v > 0 for v in (width, height)):
                    continue
                corners = (
                    tuple(
                        screen_corners(
                            rig,
                            face,
                            values,
                            front_distance=resolved["Front"]["subject_distance"],
                        )
                    )
                    if rig
                    else ()
                )
                result[face] = PreviewSurface(
                    width,
                    height,
                    corners,
                    PreviewCorrection.from_draft(
                        face, values, (resolutions or {}).get(face)
                    ),
                )
            except (KeyError, ValueError):
                continue
        return cls(result, rig.subject if rig else None, rig)

    def artifact(self) -> Any:
        surfaces = tuple(
            SimpleNamespace(
                surface_id=face.lower(),
                bottom_left_mm=s.corners[0],
                bottom_right_mm=s.corners[1],
                top_left_mm=s.corners[3],
            )
            for face, s in self.surfaces.items()
            if s.corners
        )
        return SimpleNamespace(
            display=SimpleNamespace(
                geometry=SimpleNamespace(observer_mm=self.observer, surfaces=surfaces)
            )
        )
