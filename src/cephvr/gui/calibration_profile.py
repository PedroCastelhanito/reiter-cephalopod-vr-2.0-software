"""Build diagnostic geometric mappings from assigned physical displays."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any, Literal

from cephvr.gui.calibration_arena import (
    Point,
    geometry_from_calibration,
    make_calibration_glb,
    make_seam_glb,
)
from cephvr.gui.projector_geometry import FACES
from cephvr.visual_stimulus.config.calibration_adjustments import (
    GUI_MESH_SIZE,
    projective_mesh,
)
from cephvr.visual_stimulus.config.calibration_bars import (
    reference_lengths,
    reference_scale,
)
from cephvr.visual_stimulus.config.models.artifact_models import GeometricProfile
from cephvr.visual_stimulus.config.models.display_profile import (
    DisplayProfile,
    PixelRect,
)

CalibrationView = Literal["reference_bars", "frame_grid", "seam_check"]


@dataclass(frozen=True)
class MonitorBinding:
    interface: str
    x: int
    y: int
    width: int
    height: int
    refresh_hz: int
    rgb_bits: int
    adapter: str = ""  # Windows device name, e.g. \\.\DISPLAY3; matches QScreen.name().


MARGIN_KEYS = ("margin_left", "margin_right", "margin_top", "margin_bottom")
KEYSTONE_KEYS = ("keystone_h", "keystone_v")


def screen_guide(
    values: dict[str, Any], face: str, width: int, height: int
) -> tuple[int, int] | None:
    """Largest centered rectangle with the screen's aspect ratio inside the output."""
    try:
        screen_w = float(values.get(f"screens.{face}.width"))  # type: ignore[arg-type]
        screen_h = float(values.get(f"screens.{face}.height"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) and v > 0 for v in (screen_w, screen_h)):
        return None
    aspect = screen_w / screen_h
    if aspect >= width / height:
        return width, max(1, min(height, round(width / aspect)))
    return max(1, min(width, round(height * aspect))), height


def reference_bar_config(
    calibration: dict[str, object], face: str, width: int, height: int
) -> dict[str, int]:
    values = calibration["values"]
    assert isinstance(values, dict)
    lengths = reference_lengths(
        width,
        height,
        values.get(f"screens.{face}.reference_x_px"),
        values.get(f"screens.{face}.reference_y_px"),
    )
    config = dict(x_length_px=int(lengths[0]), y_length_px=int(lengths[1]))
    guide = screen_guide(values, face, width, height)
    if guide is not None:
        config.update(guide_width_px=guide[0], guide_height_px=guide[1])
    return config


@dataclass(frozen=True)
class AssignedDisplay:
    face: str
    x: int
    y: int
    width: int
    height: int
    enabled: bool
    interface: str = ""  # Native identity; preferred over the desktop rectangle.


def active_monitor_bindings() -> tuple[MonitorBinding, ...]:
    """Read native interfaces and rectangles without opening projector windows."""
    import glfw

    from cephvr.platform.windows.display_identity import monitor_interface

    if not glfw.init():
        raise RuntimeError("GLFW could not enumerate active displays")
    try:
        result = []
        for monitor in glfw.get_monitors():
            mode = glfw.get_video_mode(monitor)
            if mode is None:
                continue
            x, y = glfw.get_monitor_pos(monitor)
            bits = (mode.bits.red, mode.bits.green, mode.bits.blue)
            if len(set(bits)) != 1:
                raise ValueError("Display RGB channel precision differs")
            result.append(
                MonitorBinding(
                    monitor_interface(
                        glfw.get_win32_adapter(monitor), glfw.get_win32_monitor(monitor)
                    ),
                    x,
                    y,
                    mode.size.width,
                    mode.size.height,
                    mode.refresh_rate,
                    bits[0],
                    str(glfw.get_win32_adapter(monitor)),
                )
            )
        return tuple(result)
    finally:
        glfw.terminate()


def _diagnostic_limits(
    rig_width: float,
    rig_depth: float,
    rig_height: float,
    subject: Point,
    screens: dict[str, list[Point]],
) -> tuple[float, float, float, float]:
    distances = [
        math.dist(subject, corner) for corners in screens.values() for corner in corners
    ]
    tank_corners = product((0.0, rig_width), (0.0, rig_depth), (0.0, rig_height))
    distances.extend(math.dist(subject, corner) for corner in tank_corners)
    shortest, longest = min(distances), max(distances)
    extent = max(rig_width, rig_depth, rig_height)
    return shortest / 100, longest * 2, extent * 1e-6, 1e-6


def _screen_number(
    values: dict[str, Any],
    face: str,
    key: str,
    default: float | None = None,
    *,
    positive: bool = False,
) -> float | None:
    value = values.get(f"screens.{face}.{key}")
    if value is None:
        return default
    if type(value) not in (float, int) or not math.isfinite(value):
        raise ValueError(f"{face} {key} must be finite")
    result = float(value)
    if positive and result <= 0:
        raise ValueError(f"{face} {key} must be positive")
    return result


def automatic_margins(
    calibration: dict[str, object], face: str, monitor: MonitorBinding
) -> tuple[float, float, float, float] | None:
    """Centered (left, right, top, bottom) pixel margins that fit the screen to the
    measured projection; negative when the projection is smaller than the screen.
    None without a reference measurement."""
    values = calibration.get("values")
    if not isinstance(values, dict):
        raise ValueError("Calibration has no screen values")
    if all(values.get(f"screens.{face}.reference_{a}_mm") is None for a in "xy"):
        return None

    def required(key: str) -> float:
        value = _screen_number(values, face, key, positive=True)
        if value is None:
            raise ValueError(f"{face}: set the {key.replace('_', ' ')} first")
        return value

    if (
        _screen_number(values, face, "reference_width_px", 0),
        _screen_number(values, face, "reference_height_px", 0),
    ) != (monitor.width, monitor.height):
        raise ValueError(
            f"{face}: reference bars do not match the assigned output mode"
        )
    measured = reference_scale(
        monitor.width,
        monitor.height,
        required("reference_x_mm"),
        required("reference_y_mm"),
        x_px=values.get(f"screens.{face}.reference_x_px"),
        y_px=values.get(f"screens.{face}.reference_y_px"),
    )
    across = (1 - required("width") / measured.projected_width_mm) / 2
    up = (1 - required("height") / measured.projected_height_mm) / 2
    return (
        across * monitor.width,
        across * monitor.width,
        up * monitor.height,
        up * monitor.height,
    )


def face_mapping(
    calibration: dict[str, object], face: str, monitor: MonitorBinding
) -> tuple[tuple[dict[str, tuple[float, float]], ...], bool]:
    """Map the screen onto the valid area: a quadrilateral inside the output.

    The four independent edge margins bound it. Each is explicit when entered, otherwise
    centered from the reference measurement, otherwise zero. Keystone H narrows the top
    edge (positive) or bottom edge (negative) by that many pixels in total, and keystone
    V shortens the right edge (positive) or left edge (negative) the same way. Inversion
    mirrors the image inside that area. The four vertices are the quad's corners; the
    projective mesh between them is built by `projective_mesh`.
    """
    values = calibration.get("values")
    if not isinstance(values, dict):
        raise ValueError("Calibration has no screen values")

    def flipped(key: str) -> bool:
        value = values.get(f"screens.{face}.{key}", False)
        if type(value) is not bool:
            raise ValueError(f"{face} {key} must be true or false")
        return value

    explicit = {key: _screen_number(values, face, key) for key in MARGIN_KEYS}
    if any(value is not None and value < 0 for value in explicit.values()):
        raise ValueError(f"{face} margins must not be negative")
    automatic = automatic_margins(calibration, face, monitor)
    margins: list[float] = []
    for index, key in enumerate(MARGIN_KEYS):
        chosen = explicit[key]
        if chosen is None:
            chosen = 0.0 if automatic is None else automatic[index]
            if chosen < -1e-9:
                raise ValueError(
                    f"{face}: the projection is smaller than the screen; move the "
                    f"projector back or enter the {key.removeprefix('margin_')} margin"
                )
            chosen = max(0.0, chosen)
        margins.append(chosen)
    left, right, top, bottom = margins
    x0, x1 = left / monitor.width, 1 - right / monitor.width
    y0, y1 = bottom / monitor.height, 1 - top / monitor.height
    if x1 - x0 < 1 / monitor.width or y1 - y0 < 1 / monitor.height:
        raise ValueError(f"{face} margins leave no visible area")
    keystone = [_screen_number(values, face, key, 0.0) or 0.0 for key in KEYSTONE_KEYS]
    shear_x, shear_y = keystone[0] / monitor.width, keystone[1] / monitor.height
    if abs(shear_x) >= x1 - x0 or abs(shear_y) >= y1 - y0:
        raise ValueError(f"{face} keystone is larger than its valid area")
    top, bottom = max(shear_x, 0.0) / 2, max(-shear_x, 0.0) / 2
    right, left = max(shear_y, 0.0) / 2, max(-shear_y, 0.0) / 2
    corners = {
        (0, 0): (x0 + bottom, y0 + left),
        (1, 0): (x1 - bottom, y0 + right),
        (0, 1): (x0 + top, y1 - left),
        (1, 1): (x1 - top, y1 - right),
    }
    flip_x, flip_y = flipped("flip_x"), flipped("flip_y")
    vertices = []
    for y, x in product((0, 1), (0, 1)):
        corner = corners[(1 - x) if flip_x else x, (1 - y) if flip_y else y]
        vertices.append(dict(uv=(float(x), float(y)), xy=corner))
    return tuple(vertices), flip_x != flip_y


def mesh_vertices(
    corners: tuple[tuple[float, float], ...],
) -> tuple[dict[str, tuple[float, float]], ...]:
    """Expand a quad's four corner vertices (uv order) into the full GUI mesh."""
    return tuple(
        dict(uv=(u, v), xy=(x, y))
        for u, v, x, y in projective_mesh(corners, GUI_MESH_SIZE, GUI_MESH_SIZE)
    )


def diagnostic_display_profile(
    calibration: dict[str, object],
    assignments: tuple[AssignedDisplay, ...],
    monitors: tuple[MonitorBinding, ...],
    *,
    view: CalibrationView | None = None,
    blackout_zones: list[dict[str, Any]] | None = None,
) -> tuple[DisplayProfile, dict[str, GeometricProfile]]:
    """Bind four assigned faces to native interfaces and per-face correction meshes.

    Every face needs an assigned display; only the enabled ones are shown, so a single
    projector can be positioned while the others stay dark.
    """
    rig, screens = geometry_from_calibration(calibration)
    assigned = [row for row in assignments if row.face in FACES]
    if len(assigned) != 4 or {row.face for row in assigned} != set(FACES):
        raise ValueError("Assign one display to each of the four faces")
    if not any(row.enabled for row in assigned):
        raise ValueError("Use at least one assigned display")
    enabled_faces = {row.face for row in assigned if row.enabled}
    near, far, position_tolerance, orthogonality_tolerance = _diagnostic_limits(
        rig.width, rig.depth, rig.height, rig.subject, screens
    )
    matched: dict[str, MonitorBinding] = {}
    for row in assigned:
        # The native interface is the stable identity; the desktop rectangle is only
        # a fallback because Qt reports it in scaled units.
        candidates = [
            monitor
            for monitor in monitors
            if (
                monitor.interface.casefold() == row.interface.casefold()
                if row.interface
                else (monitor.x, monitor.y, monitor.width, monitor.height)
                == (row.x, row.y, row.width, row.height)
            )
        ]
        if len(candidates) != 1:
            raise ValueError(
                f"{row.face}: assigned display is not an active native monitor"
            )
        matched[row.face] = candidates[0]
    if len({monitor.interface.casefold() for monitor in matched.values()}) != 4:
        raise ValueError(
            "Assigned faces do not resolve to four distinct native displays"
        )
    outputs = []
    mappings = []
    profiles: dict[str, GeometricProfile] = {}
    zones: dict[str, list[PixelRect]] = {face: [] for face in FACES}
    for zone in blackout_zones or []:
        if zone["face"] not in zones:
            raise ValueError("Blackout zone requires an assigned screen")
        zone_rect = PixelRect.model_validate(
            {key: zone[key] for key in ("x", "y", "width", "height")}
        )
        zones[zone["face"]].append(zone_rect)
    for face in FACES:
        monitor = matched[face]
        face_id = face.lower()
        output_id = f"calibration_{face_id}"
        mapping_id = f"diagnostic_{face_id}"
        rect = dict(x=0, y=0, width=monitor.width, height=monitor.height)
        outputs.append(
            dict(
                output_id=output_id,
                enabled=face in enabled_faces,
                device_identity=monitor.interface,
                width_px=monitor.width,
                height_px=monitor.height,
                refresh_numerator=monitor.refresh_hz,
                refresh_denominator=1,
                rgb_bits_per_channel=monitor.rgb_bits,
                blackout_zones=tuple(zones[face]),
                reference_bars=reference_bar_config(
                    calibration, face, monitor.width, monitor.height
                ),
            )
        )
        logical_path = f"calibration/{mapping_id}.json"
        mappings.append(
            dict(
                mapping_id=mapping_id,
                surface_id=face_id,
                output_id=output_id,
                viewport=rect,
                geometric_profile=dict(logical_path=logical_path),
            )
        )
        if view == "reference_bars" or face not in enabled_faces:
            # Bars ignore corrections; a dark face needs no valid correction.
            vertices = tuple(
                dict(uv=(x, y), xy=(x, y))
                for y, x in ((0.0, 0.0), (0.0, 1.0), (1.0, 0.0), (1.0, 1.0))
            )
            mirrored = False
        else:
            vertices, mirrored = face_mapping(calibration, face, monitor)
        quad = tuple(vertex["xy"] for vertex in vertices)
        corners = tuple(vertices[index]["xy"] for index in (0, 1, 3, 2))
        if mirrored:
            corners = tuple(reversed(corners))
        profiles[face_id] = GeometricProfile.model_validate(
            dict(
                format_version=1,
                calibration_id=f"diagnostic_{face_id}",
                mapping_id=mapping_id,
                surface_id=face_id,
                output_id=output_id,
                output_width=monitor.width,
                output_height=monitor.height,
                viewport=rect,
                rows=GUI_MESH_SIZE,
                columns=GUI_MESH_SIZE,
                vertices=mesh_vertices(quad),
                orientation="mirrored" if mirrored else "preserving",
                diagonal="bottom_left_to_top_right",
                mask=None,
                weight=None,
                overlap_group=None,
                intended_coverage=corners,
                coverage_tolerance=1e-6,
                triangle_area_tolerance=1e-9,
            )
        )
    surfaces = tuple(
        dict(
            surface_id=face.lower(),
            bottom_left_mm=corners[0],
            bottom_right_mm=corners[1],
            top_right_mm=corners[2],
            top_left_mm=corners[3],
        )
        for face, corners in screens.items()
    )
    profile = DisplayProfile.model_validate(
        dict(
            format_version=1,
            geometry=dict(
                frame_id="rig-mm",
                observer_mm=rig.subject,
                near_mm=near,
                far_mm=far,
                positional_tolerance_mm=position_tolerance,
                orthogonality_tolerance=orthogonality_tolerance,
                surfaces=surfaces,
            ),
            outputs=tuple(outputs),
            mappings=tuple(mappings),
            calibration_view=view or "frame_grid",
            presentation_mode="all_outputs_vsync",
            photometric_mode="uncalibrated",
            idle_linear_rgb=(0.0, 0.0, 0.0),
            photodiode_enabled=False,
        )
    )
    return profile, profiles


def _write_atomically(path: Path, data: bytes) -> None:
    """Replace a bundle file in one step so a reader never sees a partial write."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def write_diagnostic_bundle(
    asset_root: Path,
    calibration: dict[str, object],
    assignments: tuple[AssignedDisplay, ...],
    monitors: tuple[MonitorBinding, ...],
    *,
    view: CalibrationView | None = None,
    blackout_zones: list[dict[str, Any]] | None = None,
) -> Path:
    """Write the view's arena GLB and explicit diagnostic geometric profiles.

    The display profile is written last because it names the other files.
    """

    if not asset_root.is_dir():
        raise ValueError("Choose an existing Assets folder")
    profile, meshes = diagnostic_display_profile(
        calibration, assignments, monitors, view=view, blackout_zones=blackout_zones
    )
    rig, screens = geometry_from_calibration(calibration)
    if view == "seam_check":
        arena_name, glb = "rig_geometry_seam.glb", make_seam_glb(rig)
    else:
        arena_name, glb = "rig_geometry_grid.glb", make_calibration_glb(rig, screens)
    destination = asset_root / "calibration"
    destination.mkdir(exist_ok=True)
    arena_path = destination / arena_name
    _write_atomically(arena_path, glb)
    for face, mesh in meshes.items():
        _write_atomically(
            destination / f"diagnostic_{face}.json",
            (mesh.model_dump_json(indent=2) + "\n").encode("utf-8"),
        )
    _write_atomically(
        destination / "diagnostic_display_profile.json",
        (profile.model_dump_json(indent=2) + "\n").encode("utf-8"),
    )
    return arena_path
