"""Typed GenApi feature access helpers; no arbitrary feature writes (A10)."""

from __future__ import annotations

import importlib
import math
from typing import Any

from cephvr.acquisition.camera.errors import CameraAdapterError
from cephvr.acquisition.camera.types import (
    EnumCapability,
    EnumChoice,
    FeatureAccess,
    FloatCapability,
    IntegerCapability,
)


def get_node(node_map: Any, name: str) -> Any | None:
    try:
        node = node_map.GetNode(name)
    except Exception as exc:
        # pypylon raises for absent names instead of returning a null node.
        if type(exc).__name__ == "LogicalErrorException" and str(exc).startswith(
            "Node not existing"
        ):
            return None
        raise sdk_failure("feature_lookup", exc, field_path=name) from exc
    return node if node is not None and available(node) else None


def available(node: Any) -> bool:
    try:
        return bool(_genicam().IsAvailable(node))
    except Exception as exc:
        raise sdk_failure("feature_availability", exc) from exc


def readable(node: Any) -> bool:
    if not available(node):
        return False
    try:
        return bool(_genicam().IsReadable(node))
    except Exception as exc:
        raise sdk_failure("feature_readability", exc) from exc


def writable(node: Any) -> bool:
    if not available(node):
        return False
    try:
        return bool(_genicam().IsWritable(node))
    except Exception as exc:
        raise sdk_failure("feature_writability", exc) from exc


def read_value(node_map: Any, name: str) -> Any | None:
    node = get_node(node_map, name)
    if node is None or not readable(node):
        return None
    try:
        return node.GetValue()
    except Exception as exc:
        raise sdk_failure("feature_read", exc, field_path=name) from exc


def write_value(node_map: Any, name: str, value: bool | int | float | str) -> Any:
    node = get_node(node_map, name)
    if node is None:
        raise CameraAdapterError(
            "UNSUPPORTED_FEATURE",
            f"required mapped feature {name} is unavailable",
            field_path=name,
        )
    if not writable(node):
        actual = read_value(node_map, name)
        if actual == value:
            return actual
        raise CameraAdapterError(
            "INVALID_SETTING",
            f"feature {name} is read-only and differs from request",
            field_path=name,
        )
    try:
        node.SetValue(value)
        return node.GetValue()
    except Exception as exc:
        raise sdk_failure("feature_write", exc, field_path=name) from exc


def capability(
    node_map: Any, name: str, *, unit: str
) -> FloatCapability | IntegerCapability:
    node = get_node(node_map, name)
    if node is None or not readable(node):
        return FloatCapability("unavailable", None, None, None, unit)
    value = read_value(node_map, name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CameraAdapterError(
            "SDK_STATE",
            f"mapped numeric feature {name} has a nonnumeric value",
            field_path=name,
        )
    if isinstance(value, float):
        return FloatCapability(
            _access(node),
            _finite_optional(node, "GetMin"),
            _finite_optional(node, "GetMax"),
            _finite_optional(node, "GetInc"),
            unit,
        )
    return IntegerCapability(
        _access(node),
        _integer_optional(node, "GetMin"),
        _integer_optional(node, "GetMax"),
        _integer_optional(node, "GetInc"),
        unit,
    )


def enum_capability(
    node_map: Any, name: str, *, canonical: dict[str, str] | None = None
) -> EnumCapability:
    node = get_node(node_map, name)
    if node is None or not readable(node):
        return EnumCapability("unavailable", ())
    try:
        entries = tuple(node.GetEntries())
    except Exception as exc:
        raise sdk_failure("feature_enum_entries", exc, field_path=name) from exc
    choices: list[EnumChoice] = []
    for entry in entries:
        try:
            if not bool(_genicam().IsAvailable(entry)):
                continue
            symbol = str(entry.GetSymbolic())
        except Exception as exc:
            raise sdk_failure("feature_enum_entry", exc, field_path=name) from exc
        value = _canonical_enum(symbol, canonical)
        choices.append(EnumChoice(value, symbol))
    return EnumCapability(_access(node), tuple(choices))


def set_enum(
    node_map: Any,
    name: str,
    value: str,
    *,
    canonical: dict[str, str] | None = None,
) -> str:
    capability_record = enum_capability(node_map, name, canonical=canonical)
    match = next(
        (choice for choice in capability_record.choices if choice.value == value), None
    )
    if match is None:
        raise CameraAdapterError(
            "INVALID_SETTING",
            f"value {value!r} is not an advertised {name} choice",
            field_path=name,
        )
    actual = write_value(node_map, name, match.sdk_symbol)
    return str(actual)


def sdk_failure(
    operation: str, exc: Exception, *, field_path: str | None = None
) -> CameraAdapterError:
    name = type(exc).__name__
    code = {
        "TimeoutException": "SDK_TIMEOUT",
        "DeviceRemovedException": "DEVICE_UNAVAILABLE",
        "AccessException": "SDK_ACCESS",
        "LogicalErrorException": "SDK_STATE",
    }.get(name, "SDK_FAILURE")
    sdk_code = getattr(exc, "GetErrorCode", None)
    detail = str(sdk_code()) if callable(sdk_code) else name
    message = f"Basler SDK {operation} failed ({detail}): {exc}"
    return CameraAdapterError(code, message, field_path=field_path)


def _access(node: Any) -> FeatureAccess:
    return "read_write" if writable(node) else "read_only"


def _finite_optional(node: Any, method: str) -> float | None:
    getter = getattr(node, method, None)
    if not callable(getter):
        return None
    try:
        if method == "GetInc":
            has_increment = getattr(node, "HasInc", None)
            if callable(has_increment) and not has_increment():
                return None
        value = float(getter())
    except Exception as exc:
        raise sdk_failure("feature_range", exc) from exc
    return value if math.isfinite(value) else None


def _integer_optional(node: Any, method: str) -> int | None:
    getter = getattr(node, method, None)
    if not callable(getter):
        return None
    try:
        value = int(getter())
    except Exception as exc:
        raise sdk_failure("feature_range", exc) from exc
    return value


def _canonical_enum(symbol: str, mapping: dict[str, str] | None) -> str:
    if mapping is None:
        return symbol
    return mapping.get(symbol, symbol)


def _genicam() -> Any:
    try:
        return importlib.import_module("pypylon.genicam")
    except ImportError as exc:
        raise CameraAdapterError(
            "SDK_UNAVAILABLE", "pypylon GenApi bindings are unavailable"
        ) from exc
