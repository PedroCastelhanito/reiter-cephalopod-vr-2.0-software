"""Authoring angles in the rectangular rig's unfolded plane (right=0, back=-90)."""

from math import atan2, degrees, isclose
from typing import Any


def direction_frame(setting: dict[str, Any]) -> tuple[float, float]:
    """Return local +X in dial axes (down=0) and handedness, preserving saved rates."""
    if setting["kind"] == "arena":
        return 90.0, -1.0
    space = setting["space"]
    rotation = (
        float(setting["initial"]["rotation_deg"])
        if setting["kind"] == "texture"
        and any(setting[k]["kind"] != "hold" for k in ("phase_x", "phase_y"))
        else 0.0
    )
    if space["kind"] == "physical_surface":
        frames = []
        for mapping in space["mappings"]:
            a, b = mapping["matrix"]
            determinant = a[0] * b[1] - a[1] * b[0]
            if (
                determinant <= 0
                or not isclose(
                    a[0] ** 2 + b[0] ** 2, a[1] ** 2 + b[1] ** 2, rel_tol=1e-9
                )
                or not isclose(a[0] * a[1] + b[0] * b[1], 0, abs_tol=1e-9)
            ):
                raise ValueError(
                    "Rig directions require a uniform, orientation-preserving surface map"
                )
            # G01 screen axes: Bottom/Left +X back, Front +X left, Right +X front.
            offset = {"bottom": 0.0, "left": 0.0, "front": 270.0, "right": 180.0}[
                mapping["surface_id"]
            ]
            mapping_angle = degrees(atan2(b[0], a[0]))
            frames.append(((offset + mapping_angle - rotation) % 360, -1.0))
    else:
        # Visual-angle programs retain their angular frame; they are not mm/s rig flow.
        return 0.0, 1.0
    if not frames or any(frame != frames[0] for frame in frames[1:]):
        raise ValueError("Set rig direction separately for each projector")
    return frames[0]


def signed_degrees(angle: float) -> float:
    """Normalize to (-180, 180], avoiding negative zero at cardinal axes."""
    return 180.0 - (180.0 - round(angle, 9)) % 360


def rig_direction(setting: dict[str, Any], local: float) -> float:
    offset, sign = direction_frame(setting)
    angle = offset + sign * local
    if setting["kind"] == "arena" or setting["space"]["kind"] == "physical_surface":
        return signed_degrees(angle - 90)
    return round(angle % 360, 9) % 360


def local_direction(setting: dict[str, Any], rig: float) -> float:
    offset, sign = direction_frame(setting)
    if setting["kind"] == "arena" or setting["space"]["kind"] == "physical_surface":
        rig += 90
    return (rig - offset) / sign
