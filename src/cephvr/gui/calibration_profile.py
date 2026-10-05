"""Build diagnostic geometric mappings from assigned physical displays."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import product
from pathlib import Path

from cephvr.gui.calibration_arena import (
    Point,
    geometry_from_calibration,
    make_calibration_glb,
)
from cephvr.gui.projector_geometry import FACES
from cephvr.visual_stimulus.config.models.artifact_models import GeometricProfile
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile


@dataclass(frozen=True)
class MonitorBinding:
    interface: str
    x: int
    y: int
    width: int
    height: int
    refresh_hz: int
    rgb_bits: int


@dataclass(frozen=True)
class AssignedDisplay:
    face: str
    x: int
    y: int
    width: int
    height: int
    enabled: bool


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


def face_mapping(
    calibration: dict[str, object], face: str, monitor: MonitorBinding
) -> tuple[tuple[dict[str, tuple[float, float]], ...], bool]:
    """Apply per-face scale, pixel shift and inversion to the diagnostic grid."""
    values = calibration.get("values")
    if not isinstance(values, dict):
        raise ValueError("Calibration has no screen values")

    def number(key: str, default: float, *, positive: bool = False) -> float:
        value = values.get(f"screens.{face}.{key}")
        if value is None:
            return default
        if type(value) not in (float, int) or not math.isfinite(value):
            raise ValueError(f"{face} {key} must be finite")
        result = float(value)
        if positive and result <= 0:
            raise ValueError(f"{face} {key} must be positive")
        return result

    def flipped(key: str) -> bool:
        value = values.get(f"screens.{face}.{key}", False)
        if type(value) is not bool:
            raise ValueError(f"{face} {key} must be true or false")
        return value

    sx = number("scale_u", 1.0, positive=True)
    sy = number("scale_v", 1.0, positive=True)
    dx = number("offset_x", 0.0) / monitor.width
    dy = number("offset_y", 0.0) / monitor.height
    flip_x, flip_y = flipped("flip_x"), flipped("flip_y")
    vertices = []
    for y, x in product((0.0, 1.0), (0.0, 1.0)):
        output_x = 0.5 + ((1 - x if flip_x else x) - 0.5) * sx + dx
        output_y = 0.5 + ((1 - y if flip_y else y) - 0.5) * sy + dy
        if not (0 <= output_x <= 1 and 0 <= output_y <= 1):
            raise ValueError(f"{face} correction extends beyond its display")
        vertices.append(dict(uv=(x, y), xy=(output_x, output_y)))
    return tuple(vertices), flip_x != flip_y


def diagnostic_display_profile(
    calibration: dict[str, object],
    assignments: tuple[AssignedDisplay, ...],
    monitors: tuple[MonitorBinding, ...],
) -> tuple[DisplayProfile, dict[str, GeometricProfile]]:
    """Bind four assigned faces to native interfaces and per-face correction meshes."""
    rig, screens = geometry_from_calibration(calibration)
    enabled = [row for row in assignments if row.enabled and row.face in FACES]
    if len(enabled) != 4 or {row.face for row in enabled} != set(FACES):
        raise ValueError(
            "Assign and enable exactly one display for each of the four faces"
        )
    near, far, position_tolerance, orthogonality_tolerance = _diagnostic_limits(
        rig.width, rig.depth, rig.height, rig.subject, screens
    )
    matched: dict[str, MonitorBinding] = {}
    for row in enabled:
        candidates = [
            monitor
            for monitor in monitors
            if (monitor.x, monitor.y, monitor.width, monitor.height)
            == (row.x, row.y, row.width, row.height)
        ]
        if len(candidates) != 1:
            raise ValueError(
                f"{row.face}: display rectangle has no unique native monitor"
            )
        matched[row.face] = candidates[0]
    if len({monitor.interface.casefold() for monitor in matched.values()}) != 4:
        raise ValueError(
            "Assigned faces do not resolve to four distinct native displays"
        )
    outputs = []
    mappings = []
    profiles: dict[str, GeometricProfile] = {}
    for face in FACES:
        monitor = matched[face]
        face_id = face.lower()
        output_id = f"calibration_{face_id}"
        mapping_id = f"diagnostic_{face_id}"
        rect = dict(x=0, y=0, width=monitor.width, height=monitor.height)
        outputs.append(
            dict(
                output_id=output_id,
                device_identity=monitor.interface,
                width_px=monitor.width,
                height_px=monitor.height,
                refresh_numerator=monitor.refresh_hz,
                refresh_denominator=1,
                rgb_bits_per_channel=monitor.rgb_bits,
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
        vertices, mirrored = face_mapping(calibration, face, monitor)
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
                rows=2,
                columns=2,
                vertices=vertices,
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
            presentation_mode="all_outputs_vsync",
            photometric_mode="uncalibrated",
            idle_linear_rgb=(0.0, 0.0, 0.0),
            photodiode_enabled=False,
        )
    )
    return profile, profiles


def write_diagnostic_bundle(
    asset_root: Path,
    calibration: dict[str, object],
    assignments: tuple[AssignedDisplay, ...],
    monitors: tuple[MonitorBinding, ...],
) -> Path:
    """Write a calibration GLB and explicit diagnostic geometric profiles."""

    if not asset_root.is_dir():
        raise ValueError("Choose an existing Assets folder")
    profile, meshes = diagnostic_display_profile(calibration, assignments, monitors)
    rig, screens = geometry_from_calibration(calibration)
    glb = make_calibration_glb(rig, screens)
    destination = asset_root / "calibration"
    destination.mkdir(exist_ok=True)
    for face, mesh in meshes.items():
        (destination / f"diagnostic_{face}.json").write_text(
            mesh.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
    (destination / "diagnostic_display_profile.json").write_text(
        profile.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    arena_path = destination / "rig_geometry_grid.glb"
    arena_path.write_bytes(glb)
    return arena_path
