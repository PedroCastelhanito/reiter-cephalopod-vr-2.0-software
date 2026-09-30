"""Dependency-aware live ROI application and range validation (A10)."""

from __future__ import annotations

from typing import Any

from cephvr.acquisition.camera.errors import CameraAdapterError
from cephvr.acquisition.camera.features import capability, read_value, write_value
from cephvr.acquisition.camera.types import CameraRoi, IntegerCapability


def apply_roi(nodes: Any, roi: CameraRoi | None) -> None:
    if roi is None:
        return
    names = ("Width", "Height", "OffsetX", "OffsetY")
    desired = {
        "Width": roi.width,
        "Height": roi.height,
        "OffsetX": roi.offset_x,
        "OffsetY": roi.offset_y,
    }
    current = {name: _integer(read_value(nodes, name)) for name in names}
    if any(current[name] is None for name in names):
        raise CameraAdapterError(
            "UNSUPPORTED_FEATURE", "ROI extent and offsets must be readable"
        )
    resolved = {
        name: current[name] if desired[name] is None else desired[name]
        for name in names
    }
    for name, value in resolved.items():
        assert value is not None
        if value < 0 or (name in ("Width", "Height") and value == 0):
            raise CameraAdapterError(
                "INVALID_SETTING",
                "ROI value is out of range",
                field_path=f"settings.roi.{name}",
            )
    _disable_centering(nodes, roi)
    # Offsets depend on the active extents. Move them to valid minima, resize,
    # then apply final offsets against the newly reported SDK limits.
    for name in ("OffsetX", "OffsetY"):
        minimum = roi_integer_capability(nodes, name).minimum
        if minimum is None:
            raise CameraAdapterError(
                "UNSUPPORTED_FEATURE", f"{name} minimum is unavailable"
            )
        _write_value(nodes, name, minimum)
    for name in ("Width", "Height"):
        value = resolved[name]
        assert isinstance(value, int)
        _write_value(nodes, name, value)
    for name in ("OffsetX", "OffsetY"):
        value = resolved[name]
        assert isinstance(value, int)
        _write_value(nodes, name, value)
    for name in names:
        actual = _integer(read_value(nodes, name))
        if actual != resolved[name]:
            raise CameraAdapterError(
                "SDK_STATE", f"ROI {name} readback differs from resolved request"
            )


def roi_integer_capability(nodes: Any, name: str) -> IntegerCapability:
    value = capability(nodes, name, unit="coordinates")
    if not isinstance(value, IntegerCapability):
        raise CameraAdapterError(
            "UNSUPPORTED_FEATURE", f"{name} is not an integer feature"
        )
    if value.access == "unavailable":
        raise CameraAdapterError("UNSUPPORTED_FEATURE", f"{name} has no live bounds")
    return value


def _write_value(nodes: Any, name: str, value: int) -> None:
    cap = roi_integer_capability(nodes, name)
    if cap.minimum is None or cap.maximum is None or cap.increment is None:
        raise CameraAdapterError(
            "UNSUPPORTED_FEATURE", f"{name} range/increment is incomplete"
        )
    if (
        value < cap.minimum
        or value > cap.maximum
        or (value - cap.minimum) % cap.increment
    ):
        raise CameraAdapterError(
            "INVALID_SETTING", f"ROI {name} violates current SDK limits"
        )
    write_value(nodes, name, value)


def _disable_centering(nodes: Any, roi: CameraRoi) -> None:
    for name, explicit_offset in (
        ("CenterX", roi.offset_x is not None),
        ("CenterY", roi.offset_y is not None),
    ):
        if explicit_offset and read_value(nodes, name) is True:
            write_value(nodes, name, False)
            if read_value(nodes, name) is not False:
                raise CameraAdapterError(
                    "SDK_STATE", f"{name} could not be disabled for explicit offset"
                )


def _integer(value: object) -> int | None:
    return value if type(value) is int else None
