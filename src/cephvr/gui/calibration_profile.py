"""Build diagnostic geometric mappings from assigned physical displays."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from cephvr.gui.calibration_arena import (
    geometry_from_calibration,
    make_calibration_glb,
    make_reference_bars_glb,
)
from cephvr.gui.projector_geometry import FACES
from cephvr.shared.calibration_assets import calibration_runtime_root
from cephvr.visual_stimulus.config.calibration_bars import (
    reference_lengths,
)
from cephvr.visual_stimulus.config.models.artifact_models import GeometricProfile
from cephvr.visual_stimulus.config.models.display_profile import (
    DisplayProfile,
    PixelRect,
)
from cephvr.visual_stimulus.configuration import load_projection_settings


@dataclass(frozen=True)
class MonitorBinding:
    interface: str
    x: int
    y: int
    width: int
    height: int
    refresh_hz: int
    rgb_bits: int
    adapter: str = ""


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
    return dict(x_length_px=int(lengths[0]), y_length_px=int(lengths[1]))


@dataclass(frozen=True)
class AssignedDisplay:
    face: str
    x: int
    y: int
    width: int
    height: int
    enabled: bool
    interface: str = ""


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


def face_mapping(
    calibration: dict[str, object], face: str, monitor: MonitorBinding
) -> tuple[tuple[dict[str, tuple[float, float]], ...], bool]:
    """Map physical millimetres at measured pixel pitch, independently of crop bounds."""
    values = calibration.get("values")
    if not isinstance(values, dict):
        raise ValueError("Calibration has no screen values")

    def flipped(key: str) -> bool:
        value = values.get(f"screens.{face}.{key}", False)
        if type(value) is not bool:
            raise ValueError(f"{face} {key} must be true or false")
        return value

    sx = sy = 1.0
    if any(
        values.get(f"screens.{face}.reference_{axis}_mm") is not None
        for axis in ("x", "y")
    ):
        from cephvr.gui.projector_extent import valid_pixels

        pixels = valid_pixels(values, face, monitor.width, monitor.height)
        sx = pixels[0] / monitor.width
        sy = pixels[1] / monitor.height
    from cephvr.gui.projector_extent import pixel_offsets
    from cephvr.visual_stimulus.config.calibration_adjustments import affine_vertices

    ox, oy = pixel_offsets(values, face, monitor.width, monitor.height)
    flip_x, flip_y = flipped("flip_x"), flipped("flip_y")
    vertices = affine_vertices(
        -sx if flip_x else sx,
        -sy if flip_y else sy,
        0.5 + ox / monitor.width,
        0.5 + oy / monitor.height,
        quarter_turn=face == "Bottom",
    )
    return vertices, flip_x != flip_y


def face_valid_area(
    calibration: dict[str, object], face: str, monitor: MonitorBinding
) -> tuple[float, float, float, float]:
    """Resolve a centered whole-pixel usable rectangle without changing pixel pitch."""
    values = calibration.get("values")
    if not isinstance(values, dict):
        raise ValueError("Calibration has no screen values")
    from cephvr.gui.projector_extent import valid_pixels

    width, height = valid_pixels(values, face, monitor.width, monitor.height)
    from cephvr.gui.projector_extent import pixel_offsets

    ox, oy = pixel_offsets(values, face, monitor.width, monitor.height)
    x = (monitor.width - width) / 2 + ox
    y = (monitor.height - height) / 2 + oy
    return (
        x / monitor.width,
        y / monitor.height,
        (x + width) / monitor.width,
        (y + height) / monitor.height,
    )


def diagnostic_display_profile(
    calibration: dict[str, object],
    assignments: tuple[AssignedDisplay, ...],
    monitors: tuple[MonitorBinding, ...],
    *,
    view: Literal[
        "reference_bars", "frame_grid", "photodiode_placement", "blackout_placement"
    ]
    | None = None,
    blackout_zones: list[dict[str, Any]] | None = None,
    photodiode_face: str | None = None,
    photodiode_patch: dict[str, Any] | None = None,
    photodiode_patches: dict[str, Any] | None = None,
) -> tuple[DisplayProfile, dict[str, GeometricProfile]]:
    """Bind four assigned faces to native interfaces and per-face correction meshes."""
    geometry_input = calibration
    if view in ("reference_bars", "photodiode_placement", "blackout_placement"):
        values = calibration["values"]
        assert isinstance(values, dict)
        geometry_input = dict(
            calibration,
            values={
                key: value
                for key, value in values.items()
                if not key.endswith(("reference_x_mm", "reference_y_mm"))
            },
        )
    rig, screens = geometry_from_calibration(geometry_input)
    enabled = [row for row in assignments if row.enabled and row.face in FACES]
    if len(enabled) != 4 or {row.face for row in enabled} != set(FACES):
        raise ValueError(
            "Assign and enable exactly one display for each of the four faces"
        )
    limits = load_projection_settings()
    matched: dict[str, MonitorBinding] = {}
    for row in enabled:
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
        if view in ("reference_bars", "photodiode_placement", "blackout_placement"):
            vertices = tuple(
                dict(uv=(x, y), xy=(x, y))
                for y, x in ((0.0, 0.0), (0.0, 1.0), (1.0, 0.0), (1.0, 1.0))
            )
            mirrored = False
        else:
            if view == "frame_grid":
                values = calibration["values"]
                assert isinstance(values, dict)
                if any(
                    values.get(f"screens.{face}.reference_{axis}_mm") is None
                    for axis in ("x", "y")
                ):
                    raise ValueError(
                        f"{face}: measure both reference bars before adjusting frame and grid"
                    )
            from cephvr.gui.projector_extent import usable_corners
            from cephvr.visual_stimulus.config.calibration_adjustments import (
                affine_vertices,
            )

            original_values = calibration["values"]
            assert isinstance(original_values, dict)
            full_values = dict(original_values)
            full_values[f"screens.{face}.valid_width_px"] = monitor.width
            full_values[f"screens.{face}.valid_height_px"] = monitor.height
            if any(
                original_values.get(f"screens.{face}.reference_{a}_mm") is not None
                for a in ("x", "y")
            ):
                screens[face] = usable_corners(
                    screens[face], full_values, face, monitor.width, monitor.height
                )
            vertices, mirrored = face_mapping(calibration, face, monitor)
            bounds = face_valid_area(calibration, face, monitor)
            vertices = affine_vertices(
                -1 if original_values.get(f"screens.{face}.flip_x") else 1,
                -1 if original_values.get(f"screens.{face}.flip_y") else 1,
                (bounds[0] + bounds[2]) / 2,
                (bounds[1] + bounds[3]) / 2,
                quarter_turn=face == "Bottom",
            )
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
                valid_area=None
                if view
                in ("reference_bars", "photodiode_placement", "blackout_placement")
                else face_valid_area(calibration, face, monitor),
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
                near_mm=limits["near_mm"],
                far_mm=limits["far_mm"],
                positional_tolerance_mm=limits["positional_tolerance_mm"],
                orthogonality_tolerance=limits["orthogonality_tolerance"],
                surfaces=surfaces,
            ),
            outputs=tuple(outputs),
            mappings=tuple(mappings),
            calibration_view=view or "frame_grid",
            presentation_mode="all_outputs_vsync",
            photometric_mode="uncalibrated",
            idle_linear_rgb=(0.0, 0.0, 0.0),
            photodiode_enabled=view == "photodiode_placement"
            and (photodiode_patch is not None or bool(photodiode_patches)),
            photodiode_output_id=f"calibration_{photodiode_face.lower()}"
            if view == "photodiode_placement"
            and photodiode_face
            and photodiode_patch is not None
            else None,
            photodiode_patch=(
                dict(
                    **photodiode_patch,
                    high_linear_rgb=(1, 1, 1),
                    low_linear_rgb=(0, 0, 0),
                )
                if view == "photodiode_placement" and photodiode_patch
                else None
            ),
            photodiode_patches=photodiode_patches
            if view == "photodiode_placement"
            else None,
        )
    )
    return profile, profiles


def write_diagnostic_bundle(
    asset_root: Path,
    calibration: dict[str, object],
    assignments: tuple[AssignedDisplay, ...],
    monitors: tuple[MonitorBinding, ...],
    *,
    view: Literal[
        "reference_bars", "frame_grid", "photodiode_placement", "blackout_placement"
    ]
    | None = None,
    runtime_root: Path | None = None,
    blackout_zones: list[dict[str, Any]] | None = None,
    photodiode_face: str | None = None,
    photodiode_patch: dict[str, Any] | None = None,
    photodiode_patches: dict[str, Any] | None = None,
) -> Path:
    """Refresh one repository pattern and stage its exact bytes with runtime mappings."""

    if not asset_root.is_dir():
        raise ValueError("Choose an existing Assets folder")
    profile, meshes = diagnostic_display_profile(
        calibration,
        assignments,
        monitors,
        view=view,
        blackout_zones=blackout_zones,
        photodiode_face=photodiode_face,
        photodiode_patch=photodiode_patch,
        photodiode_patches=photodiode_patches,
    )
    step = profile.calibration_view
    if step != "frame_grid":
        bar_outputs = {}
        for output in profile.outputs:
            assert output.reference_bars is not None
            bar_outputs[output.output_id] = (
                output.width_px,
                output.height_px,
                output.reference_bars.x_length_px,
                output.reference_bars.y_length_px,
            )
        glb = make_reference_bars_glb(bar_outputs)
    else:
        rig, _ = geometry_from_calibration(calibration)
        screens = {
            surface.surface_id.title(): [
                surface.bottom_left_mm,
                surface.bottom_right_mm,
                surface.top_right_mm,
                surface.top_left_mm,
            ]
            for surface in profile.geometry.surfaces
        }
        glb = make_calibration_glb(
            rig,
            screens,
            raster_sizes={
                mapping.surface_id.title(): (
                    mapping.viewport.width,
                    mapping.viewport.height,
                )
                for mapping in profile.mappings
            },
        )
    pattern_directory = asset_root / "calibration"
    pattern_directory.mkdir(exist_ok=True)
    arena_path = pattern_directory / f"{step}.glb"
    arena_path.write_bytes(glb)
    work_root = calibration_runtime_root(step) if runtime_root is None else runtime_root
    destination = work_root / "calibration"
    destination.mkdir(parents=True, exist_ok=True)
    for face, mesh in meshes.items():
        (destination / f"diagnostic_{face}.json").write_text(
            mesh.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
    (destination / "diagnostic_display_profile.json").write_text(
        profile.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (destination / arena_path.name).write_bytes(glb)
    return arena_path
