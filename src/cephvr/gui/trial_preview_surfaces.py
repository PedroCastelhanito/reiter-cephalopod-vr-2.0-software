"""Focused snapshot of configured screen planes for planning, without output ownership."""

import math
from dataclasses import dataclass
from functools import cached_property
from types import SimpleNamespace
from typing import Any

from cephvr.gui.calibration_profile import MonitorBinding, face_mapping, face_valid_area
from cephvr.gui.projector_geometry import (
    RigDimensions,
    resolved_screens,
    screen_corners,
)


@dataclass(frozen=True)
class PreviewCorrection:
    corners: tuple[tuple[float, float], ...] = ()
    error: str = ""
    valid_area: tuple[float, float, float, float] | None = None
    source_uv: tuple[tuple[float, float], ...] = ()

    @classmethod
    def from_draft(
        cls, face: str, draft: dict[str, str], resolution: tuple[int, int] | None
    ) -> "PreviewCorrection":
        try:
            values: dict[str, object] = {}
            for key in (
                "valid_width_px",
                "valid_height_px",
                "offset_x_px",
                "offset_y_px",
                "width",
                "height",
                "throw",
                "reference_width_px",
                "reference_height_px",
                "reference_x_px",
                "reference_y_px",
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
            if resolution is None and any(
                values[f"screens.{face}.reference_{axis}_mm"] is not None
                for axis in ("x", "y")
            ):
                raise ValueError(
                    f"Assign a display to {face} to resolve reference bars"
                )
            if resolution is None and any(
                values.get(f"screens.{face}.{key}") is not None
                for key in ("valid_width_px", "valid_height_px")
            ):
                raise ValueError(f"Assign a display to {face} to resolve pixel sizes")
            if resolution is None and any(
                values[f"screens.{face}.offset_{axis}_px"] not in (None, 0.0)
                for axis in ("x", "y")
            ):
                raise ValueError(f"Assign a display to {face} to resolve pixel offsets")
            width, height = resolution or (1, 1)
            if min(width, height) <= 0:
                raise ValueError(f"{face} display resolution must be positive")
            vertices, _ = face_mapping(
                {"values": values}, face, MonitorBinding("", 0, 0, width, height, 0, 0)
            )
            return cls(
                tuple(vertices[i]["xy"] for i in (0, 1, 3, 2)),
                source_uv=tuple(vertices[i]["uv"] for i in (0, 1, 3, 2)),
                valid_area=face_valid_area(
                    {"values": values},
                    face,
                    MonitorBinding("", 0, 0, width, height, 0, 0),
                ),
            )
        except (ValueError, TypeError) as error:
            return cls(error=str(error))


@dataclass(frozen=True)
class PreviewSurface:
    width: float
    height: float
    corners: tuple[tuple[float, float, float], ...] = ()
    correction: PreviewCorrection | None = None
    blackout_zones: tuple[tuple[float, float, float, float], ...] = ()
    marker_rect: tuple[float, float, float, float] | None = None
    physical_corners: tuple[tuple[float, float, float], ...] = ()


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
        overlays: dict[
            str,
            tuple[
                list[tuple[float, float, float, float]],
                tuple[float, float, float, float] | None,
            ],
        ]
        | None = None,
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
                            bottom_distance=resolved["Bottom"].get(
                                "subject_distance", ""
                            ),
                        )
                    )
                    if rig
                    else ()
                )
                physical = corners
                resolution = (resolutions or {}).get(face)
                if resolution and any(
                    values.get(f"reference_{axis}_mm", "") for axis in ("x", "y")
                ):
                    from cephvr.gui.projector_extent import (
                        measured_pitch,
                        usable_corners,
                        valid_pixels,
                    )

                    numeric = {
                        f"screens.{face}.{key}": float(value) if value else None
                        for key, value in values.items()
                        if key not in ("flip_x", "flip_y")
                    }
                    pixels = valid_pixels(numeric, face, *resolution)
                    pitch = measured_pitch(numeric, face, *resolution)
                    width, height = pixels[0] * pitch[0], pixels[1] * pitch[1]
                    if face == "Bottom":
                        width, height = height, width
                    if corners:
                        corners = tuple(
                            usable_corners(corners, numeric, face, *resolution)
                        )
                result[face] = PreviewSurface(
                    width,
                    height,
                    corners,
                    PreviewCorrection.from_draft(
                        face, values, (resolutions or {}).get(face)
                    ),
                    tuple((overlays or {}).get(face, ([], None))[0]),
                    (overlays or {}).get(face, ([], None))[1],
                    physical,
                )
            except (KeyError, ValueError):
                continue
        return cls(result, rig.subject if rig else None, rig)

    @cached_property
    def projection_settings(self) -> dict[str, float]:
        from cephvr.visual_stimulus.configuration import load_projection_settings

        return load_projection_settings()

    def artifact(self) -> Any:

        surfaces = tuple(
            SimpleNamespace(
                surface_id=face.lower(),
                bottom_left_mm=s.corners[0],
                bottom_right_mm=s.corners[1],
                top_right_mm=s.corners[2],
                top_left_mm=s.corners[3],
            )
            for face, s in self.surfaces.items()
            if s.corners
        )
        return SimpleNamespace(
            display=SimpleNamespace(
                geometry=SimpleNamespace(
                    observer_mm=self.observer,
                    surfaces=surfaces,
                    **self.projection_settings,
                )
            )
        )
