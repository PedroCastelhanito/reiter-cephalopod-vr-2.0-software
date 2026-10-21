"""Pure canonical numeric parameter edits shared by authoring and preparation."""

from copy import deepcopy
from decimal import Decimal
from math import atan2, cos, degrees, hypot, radians, sin
from typing import Any

from .rig_coordinates import local_direction, rig_direction

END_BEHAVIORS = {
    "loop": "loop",
    "hold": "hold_final_frame",
    "hold final frame": "hold_final_frame",
    "hold_final_frame": "hold_final_frame",
}


def constant_rate(value: dict[str, Any]) -> float | None:
    if value["kind"] == "hold":
        return 0.0
    if (
        value["kind"] == "rate"
        and value["function"]["kind"] == "constant"
        and isinstance(value["function"]["value"], (float, int))
    ):
        return float(value["function"]["value"])
    return None


def motion_numbers(
    setting: dict[str, Any], *, rig_coordinates: bool = False
) -> tuple[float, float, float]:
    texture = setting["kind"] == "texture"
    if texture:
        pattern = setting["pattern"]
        if pattern["kind"] != "image_tile" or any(
            pattern[k]["kind"] != "constant"
            or not isinstance(pattern[k]["value"], (int, float))
            for k in ("period_x", "period_y")
        ):
            raise ValueError(
                "Speed/direction variations need an image tile with constant dimensions"
            )
        translating = any(setting["motion"][k]["kind"] != "hold" for k in ("x", "y"))
        phased = any(setting[k]["kind"] != "hold" for k in ("phase_x", "phase_y"))
        if translating and phased:
            raise ValueError(
                "Speed variations cannot replace simultaneous texture translation"
            )
        x, y = [constant_rate(setting[f"phase_{axis}"]) for axis in ("x", "y")]
        if x is not None and y is not None:
            x, y = -x * pattern["period_x"]["value"], -y * pattern["period_y"]["value"]
        if translating:
            x, y = [constant_rate(setting["motion"][axis]) for axis in ("x", "y")]
    else:
        x, y = [constant_rate(setting["motion"][axis]) for axis in ("x", "y")]
    angular = constant_rate(
        setting["motion"]["yaw" if setting["kind"] == "arena" else "rotation"]
    )
    if x is None or y is None or angular is None:
        raise ValueError("Choose constant motion before varying speed/direction")
    angle = degrees(atan2(y, x)) if x or y else 0.0
    if rig_coordinates:
        angle = rig_direction(setting, angle) if x or y else 0.0
    return hypot(x, y), angle, angular


def varied_fields(
    setting: dict[str, Any], values: dict[str, float], *, rig_coordinates: bool = False
) -> dict[tuple[str, ...], tuple[float, str]]:
    rig_coordinates = rig_coordinates and (
        setting["kind"] == "arena" or setting["space"]["kind"] == "physical_surface"
    )
    result: dict[tuple[str, ...], tuple[float, str]] = {}
    length = (
        "mm"
        if setting["kind"] == "arena" or setting["space"]["kind"] == "physical_surface"
        else "deg"
    )
    if any(key in values for key in ("Speed", "Direction", "Angular speed")):
        speed, angle, angular = motion_numbers(setting, rig_coordinates=rig_coordinates)
        speed, angle, angular = (
            values.get("Speed", speed),
            values.get("Direction", angle),
            values.get("Angular speed", angular),
        )
        if speed < 0:
            raise ValueError("Speed must be nonnegative")
        if "Speed" in values or "Direction" in values:
            if rig_coordinates:
                frame = deepcopy(setting)
                if frame["kind"] == "texture":
                    frame["phase_x"] = frame["phase_y"] = {"kind": "hold"}
                angle = local_direction(frame, angle)
            x, y = speed * cos(radians(angle)), speed * sin(radians(angle))
            for axis, value in (("x", x), ("y", y)):
                if setting["kind"] == "texture" and not rig_coordinates:
                    result[(f"phase_{axis}", "function", "value")] = (
                        -value / setting["pattern"][f"period_{axis}"]["value"],
                        "cycle/s",
                    )
                else:
                    result[("motion", axis, "function", "value")] = (
                        value,
                        f"{length}/s",
                    )
        if "Angular speed" in values:
            result[
                (
                    "motion",
                    "yaw" if setting["kind"] == "arena" else "rotation",
                    "function",
                    "value",
                )
            ] = (angular, "deg/s")
    for name, key in (("Width", "width"), ("Height", "height"), ("Opacity", "opacity")):
        if name in values:
            if key not in setting:
                raise ValueError(f"{name} is not available for this stimulus")
            result[(key, "value")] = (values[name], "1" if key == "opacity" else length)
    return result


def assign_ref(
    setting: dict[str, Any], path: tuple[str, ...], ref: dict[str, str] | float
) -> None:
    if path[0] == "motion":
        if setting["kind"] == "texture" and path[1] in ("x", "y"):
            setting["phase_x"] = setting["phase_y"] = {"kind": "hold"}
        setting["motion"][path[1]] = {
            "kind": "rate",
            "function": {"kind": "constant", "value": ref},
        }
    elif path[0].startswith("phase_"):
        setting[path[0]] = {
            "kind": "rate",
            "function": {"kind": "constant", "value": ref},
        }
    else:
        setting[path[0]] = {"kind": "constant", "value": ref}


def parameter_value(
    setting: dict[str, Any], name: str, *, rig_coordinates: bool = False
) -> object:
    if name == "At end":
        return setting["end_behavior"]
    if name in ("Longitudinal", "Lateral", "Angular"):
        binding = next(
            (
                b
                for b in setting["feedback"]
                if (
                    b["operation"] == "movement_integration"
                    and b.get("target") == "yaw"
                    if name == "Angular"
                    else b["operation"] == "heading_relative_planar_integration"
                )
            ),
            None,
        )
        if binding is None:
            return 0
        value = binding["sideways_gain" if name == "Lateral" else "gain"]
        if value["kind"] != "constant":
            raise ValueError("Custom movement gain")
        return value["value"]
    if name == "Fit":
        return setting.get("fit", "stretch")
    if name == "Angular speed":
        value = constant_rate(
            setting["motion"]["yaw" if setting["kind"] == "arena" else "rotation"]
        )
        if value is None:
            raise ValueError("Custom angular motion")
        return value
    if name in ("Speed", "Direction"):
        return motion_numbers(setting, rig_coordinates=rig_coordinates)[
            ("Speed", "Direction", "Angular speed").index(name)
        ]
    if name in ("Start size", "End size", "Growth duration"):
        curve = setting["width"]
        knots = curve.get("knots", [])
        if (
            curve != setting["height"]
            or curve.get("interpolation") != "linear"
            or len(knots) != 2
            or Decimal(knots[0]["time"]["seconds"]) != 0
        ):
            raise ValueError("Custom size animation")
        return (
            knots[1]["time"]["seconds"]
            if name == "Growth duration"
            else knots[0 if name == "Start size" else 1]["value"]
        )
    if name == "Playback start":
        return setting["initial_playback"]["seconds"]
    key = {"Width": "width", "Height": "height", "Opacity": "opacity"}[name]
    value = setting[key]
    if value["kind"] != "constant" or not isinstance(value["value"], (float, int)):
        raise ValueError("Custom function")
    return value["value"]


def patch_setting(
    setting: dict[str, Any],
    changes: dict[str, str],
    *,
    rig_coordinates: bool = False,
    rig_angle_version: int = 2,
) -> None:
    for name in ("Longitudinal", "Lateral", "Angular"):
        if name not in changes:
            continue
        binding = next(
            (
                b
                for b in setting["feedback"]
                if (
                    b["operation"] == "movement_integration"
                    and b.get("target") == "yaw"
                    if name == "Angular"
                    else b["operation"] == "heading_relative_planar_integration"
                )
            ),
            None,
        )
        if binding is None:
            raise ValueError(
                "Prepare the arena movement binding before varying its gain"
            )
        key = "sideways_gain" if name == "Lateral" else "gain"
        if binding[key]["kind"] != "constant":
            raise ValueError("Custom movement gains cannot be replaced by a variation")
        binding[key] = dict(kind="constant", value=float(changes[name]))
    if "At end" in changes:
        choice = END_BEHAVIORS.get(changes["At end"].lower())
        if choice is None:
            raise ValueError("Choose Loop or Hold final frame")
        setting["end_behavior"] = choice
    if "Fit" in changes:
        fit_choice = changes["Fit"].lower()
        if fit_choice not in {"contain", "cover", "stretch"}:
            raise ValueError("Choose Contain, Cover or Stretch")
        setting["fit"] = fit_choice
    numeric = {
        k: float(v)
        for k, v in changes.items()
        if k in ("Speed", "Direction", "Angular speed", "Width", "Height", "Opacity")
    }
    if (
        rig_coordinates
        and rig_angle_version == 1
        and (
            setting["kind"] == "arena" or setting["space"]["kind"] == "physical_surface"
        )
    ):
        # Persisted v1 angles used Back=0; keep their physical movement unchanged.
        if "Direction" in numeric:
            numeric["Direction"] -= 90
        elif "Speed" in numeric and motion_numbers(setting)[0] == 0:
            numeric["Direction"] = -90
    angular = numeric.pop("Angular speed", None)
    if angular is not None:
        key = "yaw" if setting["kind"] == "arena" else "rotation"
        setting["motion"][key] = dict(
            kind="rate", function=dict(kind="constant", value=angular)
        )
    fields = varied_fields(setting, numeric, rig_coordinates=rig_coordinates)
    for path, (value, _) in fields.items():
        assign_ref(setting, path, value)
    size = {
        k: v
        for k, v in changes.items()
        if k in ("Start size", "End size", "Growth duration")
    }
    if size:
        values = {
            k: parameter_value(setting, k)
            for k in ("Start size", "End size", "Growth duration")
        }
        values.update(size)
        seconds = str(values["Growth duration"])
        if not Decimal(seconds).is_finite() or Decimal(seconds) <= 0:
            raise ValueError("Growth duration must be positive")
        curve = dict(
            kind="keyframes",
            interpolation="linear",
            knots=[
                dict(time={"seconds": "0"}, value=float(str(values["Start size"]))),
                dict(time={"seconds": seconds}, value=float(str(values["End size"]))),
            ],
        )
        setting.update(width=curve, height=deepcopy(curve))
    if "Playback start" in changes:
        setting["initial_playback"] = {"seconds": changes["Playback start"]}
