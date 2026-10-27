"""Grating orientation is the rig direction normal to its bars, even at zero speed."""

from math import cos, hypot, isfinite, radians, sin
from typing import Any

from .rig_coordinates import local_direction, rig_direction


def orientation(setting: dict[str, Any], *, rig_coordinates: bool) -> float:
    value = next(
        (a["value"] for a in setting["assignments"] if a["target"] == "rotation"),
        setting["initial"]["rotation_deg"],
    )
    if not isinstance(value, (int, float)):
        raise ValueError("Grating Orientation must be a fixed number")
    local = float(value)
    return rig_direction(setting, local) if rig_coordinates else local


def assign_orientation(
    setting: dict[str, Any], angle: float, *, rig_coordinates: bool
) -> None:
    local = local_direction(setting, angle) if rig_coordinates else angle
    setting["assignments"] = [
        a for a in setting["assignments"] if a["target"] != "rotation"
    ] + [dict(target="rotation", value=local)]


def validate_motion(setting: dict[str, Any]) -> None:
    """Keep hand-authored Grating declarations within the two-parameter interface."""
    angle = orientation(setting, rig_coordinates=False)
    values = []
    for axis in ("x", "y"):
        motion = setting["motion"][axis]
        if motion["kind"] == "hold":
            values.append(0.0)
        elif (
            motion["kind"] == "rate"
            and motion["function"]["kind"] == "constant"
            and isinstance(motion["function"]["value"], (float, int))
        ):
            values.append(float(motion["function"]["value"]))
        else:
            raise ValueError("Grating requires constant Speed and Orientation")
    x, y = values
    tolerance = max(1e-9, hypot(x, y) * 1e-9)
    if (
        not isfinite(angle)
        or abs(y * cos(radians(angle)) - x * sin(radians(angle))) > tolerance
        or x * cos(radians(angle)) + y * sin(radians(angle)) < -tolerance
    ):
        raise ValueError("Grating movement must follow Orientation across its bars")
    if setting["feedback"]:
        raise ValueError("Grating supports Asset, Orientation and Speed only")
