"""Exact mapped Basler transport controls and boundary-counter reads (A10)."""

from __future__ import annotations

import math
from typing import Any

from cephvr.acquisition.camera.errors import CameraAdapterError
from cephvr.acquisition.camera.features import (
    get_node,
    read_value,
    set_enum,
    write_value,
)
from cephvr.acquisition.camera.types import (
    TransportCounters,
    TransportInterface,
    TransportOverride,
    TransportSettings,
    TransportValue,
)

# (node map, interface, native type, documented unit)
_TRANSPORT: dict[str, tuple[str, str, type, str]] = {
    "DeviceLinkThroughputLimitMode": ("camera", "usb3_gige", str, ""),
    "DeviceLinkThroughputLimit": ("camera", "usb3_gige", int, "B/s"),
    "MaxTransferSize": ("stream", "usb3", int, ""),
    "NumMaxQueuedUrbs": ("stream", "usb3", int, ""),
    "GevSCPSPacketSize": ("camera", "gige", int, ""),
    "GevSCPD": ("camera", "gige", int, "ticks"),
    "GevSCFTD": ("camera", "gige", int, "ticks"),
    "PacketTimeout": ("stream", "gige", int, ""),
    "FrameRetention": ("stream", "gige", int, ""),
    "EnableResend": ("stream", "gige", bool, ""),
}
_APPLY_ORDER = {
    "DeviceLinkThroughputLimitMode": 0,
    "GevSCPSPacketSize": 0,
    "MaxTransferSize": 0,
    "DeviceLinkThroughputLimit": 1,
    "GevSCPD": 2,
    "GevSCFTD": 3,
    "NumMaxQueuedUrbs": 4,
    "PacketTimeout": 4,
    "FrameRetention": 5,
    "EnableResend": 6,
}
_COUNTERS = {
    "buffer_underruns": "Statistic_Buffer_Underrun_Count",
    "failed_buffers": "Statistic_Failed_Buffer_Count",
    "missed_frames": "Statistic_Missed_Frame_Count",
    "resend_requests": "Statistic_Resend_Request_Count",
    "resend_packets": "Statistic_Resend_Packet_Count",
    "resynchronizations": "Statistic_Resynchronization_Count",
}


def apply_transport_settings(
    camera: Any,
    interface: TransportInterface,
    settings: TransportSettings,
    genicam: Any,
) -> TransportSettings:
    """Apply by dependent order, validate node type/range/unit, and return readback."""
    overrides = sorted(
        settings.overrides,
        key=lambda item: (_APPLY_ORDER.get(item.sdk_name, 99), item.sdk_name),
    )
    requested: set[str] = set()
    for item in overrides:
        mapping = _TRANSPORT.get(item.sdk_name)
        if mapping is None or item.sdk_name in requested:
            raise CameraAdapterError(
                "UNSUPPORTED_FEATURE",
                f"unmapped or repeated transport feature {item.sdk_name}",
            )
        requested.add(item.sdk_name)
        map_kind, applicability, expected, unit = mapping
        if applicability not in ("usb3_gige", interface):
            raise CameraAdapterError(
                "INVALID_SETTING", f"{item.sdk_name} does not apply to {interface}"
            )
        if type(item.value) is not expected:
            raise CameraAdapterError(
                "INVALID_SETTING", f"{item.sdk_name} requires {expected.__name__}"
            )
        node_map = _node_map(camera, map_kind)
        _validate_value(node_map, item.sdk_name, item.value, expected, unit, genicam)
        if expected is str:
            set_enum(node_map, item.sdk_name, str(item.value))
        else:
            write_value(node_map, item.sdk_name, item.value)
    resolved: dict[str, TransportOverride] = {}
    for name in (
        "DeviceLinkThroughputLimitMode",
        "DeviceLinkThroughputLimit",
        *sorted(requested),
    ):
        mapping = _TRANSPORT.get(name)
        if mapping is None:
            continue
        map_kind, applicability, _, _ = mapping
        if applicability not in ("usb3_gige", interface):
            continue
        node_map = _node_map(camera, map_kind)
        node = get_node(node_map, name)
        if node is None or not genicam.IsReadable(node):
            if name in requested:
                raise CameraAdapterError(
                    "UNSUPPORTED_FEATURE",
                    f"transport feature {name} has no readable readback",
                )
            continue
        value = read_value(node_map, name)
        if not isinstance(value, (bool, int, float, str)):
            raise CameraAdapterError(
                "SDK_STATE", f"transport feature {name} readback is not scalar"
            )
        resolved[name] = TransportOverride(name, value)
    return TransportSettings(tuple(resolved.values()))


def read_transport_counters(camera: Any) -> TransportCounters:
    node_map = camera.GetStreamGrabberNodeMap()
    values: dict[str, int | None] = {}
    for field, node_name in _COUNTERS.items():
        value = read_value(node_map, node_name)
        values[field] = (
            value
            if isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value < (1 << 64)
            else None
        )
    return TransportCounters(**values)


def _validate_value(
    node_map: Any,
    name: str,
    value: TransportValue,
    expected_type: type,
    expected_unit: str,
    genicam: Any,
) -> None:
    node = get_node(node_map, name)
    if node is None:
        raise CameraAdapterError(
            "UNSUPPORTED_FEATURE", f"transport feature {name} is unavailable"
        )
    if not genicam.IsWritable(node):
        actual = read_value(node_map, name)
        if actual == value:
            return
        raise CameraAdapterError(
            "INVALID_SETTING", f"transport feature {name} is read-only"
        )
    actual = read_value(node_map, name)
    if type(actual) is not expected_type:
        raise CameraAdapterError(
            "SDK_STATE", f"transport feature {name} has an unexpected native type"
        )
    if isinstance(value, str):
        choices = tuple(choice for choice in _enum_choices(node, genicam))
        if value not in choices:
            raise CameraAdapterError(
                "INVALID_SETTING", f"{value!r} is not an advertised {name} choice"
            )
        return
    if expected_type is bool:
        return
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise CameraAdapterError("INVALID_SETTING", f"{name} requires numeric input")
    if isinstance(value, float) and not math.isfinite(value):
        raise CameraAdapterError("INVALID_SETTING", f"{name} must be finite")
    unit_getter = getattr(node, "GetUnit", None)
    if expected_unit:
        if not callable(unit_getter):
            raise CameraAdapterError(
                "UNSUPPORTED_FEATURE", f"{name} does not expose its documented unit"
            )
        unit = str(unit_getter())
        if unit != expected_unit:
            raise CameraAdapterError(
                "SDK_STATE",
                f"{name} unit {unit!r} differs from mapped {expected_unit!r}",
            )
    bounds: list[Any] = []
    for method in ("GetMin", "GetMax"):
        getter = getattr(node, method, None)
        if not callable(getter):
            raise CameraAdapterError(
                "UNSUPPORTED_FEATURE", f"{name} lacks {method} range"
            )
        bounds.append(getter())
    minimum, maximum = bounds
    if not minimum <= value <= maximum:
        raise CameraAdapterError(
            "INVALID_SETTING", f"{name} is outside current SDK range"
        )
    inc_getter = getattr(node, "GetInc", None)
    if not callable(inc_getter):
        raise CameraAdapterError("UNSUPPORTED_FEATURE", f"{name} lacks GetInc range")
    increment = inc_getter()
    if isinstance(value, int) and (not isinstance(increment, int) or increment <= 0):
        raise CameraAdapterError(
            "SDK_STATE", f"{name} has an invalid integer increment"
        )
    if isinstance(value, int) and (value - int(node.GetMin())) % increment != 0:
        raise CameraAdapterError(
            "INVALID_SETTING", f"{name} does not match current increment"
        )


def _enum_choices(node: Any, genicam: Any) -> tuple[str, ...]:
    values: list[str] = []
    for entry in node.GetEntries():
        if not genicam.IsAvailable(entry) or not genicam.IsReadable(entry):
            continue
        values.append(str(entry.GetSymbolic()))
    return tuple(values)


def _node_map(camera: Any, kind: str) -> Any:
    return camera.GetNodeMap() if kind == "camera" else camera.GetStreamGrabberNodeMap()
