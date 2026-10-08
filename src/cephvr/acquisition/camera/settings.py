"""Explicit Basler standard-setting mapping and live capability readback (A10)."""

from __future__ import annotations

import math
from typing import Any

from cephvr.acquisition.camera.errors import CameraAdapterError
from cephvr.acquisition.camera.features import (
    capability,
    enum_capability,
    get_node,
    read_value,
    set_enum,
    write_value,
)
from cephvr.acquisition.camera.native_formats import device_pixel_type
from cephvr.acquisition.camera.records import (
    SettingAdjustmentRecord,
    SettingsReadbackRecord,
)
from cephvr.acquisition.camera.roi import apply_roi, roi_integer_capability
from cephvr.acquisition.camera.types import (
    CameraCapabilities,
    CameraGain,
    CameraRoi,
    CameraSettings,
    EnumCapability,
    EnumChoice,
    GainCapability,
    IntegerCapability,
    RoiCapabilities,
    TriggerRateLimit,
)

_FLOAT_FEATURES = ("ExposureTime", "ExposureTimeAbs")
_GAIN_FEATURES = ("Gain", "GainRaw")
_RATE_FEATURES = ("AcquisitionFrameRate", "AcquisitionFrameRateAbs")
_TRIGGER_SELECTOR = {"FrameStart": "frame_start"}
_TRIGGER_ACTIVATION = {"RisingEdge": "rising_edge", "FallingEdge": "falling_edge"}
_EXPOSURE_MODE = {"Timed": "timed"}


def read_settings(camera: Any) -> CameraSettings:
    nodes = camera.GetNodeMap()
    exposure_name, exposure = _first_value(nodes, _FLOAT_FEATURES)
    gain_name, gain_value = _first_value(nodes, _GAIN_FEATURES)
    selector = read_value(nodes, "GainSelector")
    gain: CameraGain | None = None
    if (
        gain_name is not None
        and isinstance(gain_value, (int, float))
        and not isinstance(gain_value, bool)
    ):
        unit = "raw" if gain_name == "GainRaw" else _unit(nodes, gain_name)
        gain = CameraGain(
            gain_value, unit, str(selector) if selector is not None else None
        )
    width = _integer(read_value(nodes, "Width"))
    height = _integer(read_value(nodes, "Height"))
    offset_x = _integer(read_value(nodes, "OffsetX"))
    offset_y = _integer(read_value(nodes, "OffsetY"))
    roi = (
        None
        if all(item is None for item in (width, height, offset_x, offset_y))
        else CameraRoi(width, height, offset_x, offset_y)
    )
    pixel_format = read_value(nodes, "PixelFormat")
    trigger_selector = _read_enum(nodes, "TriggerSelector", _TRIGGER_SELECTOR)
    trigger_source = read_value(nodes, "TriggerSource")
    trigger_activation = _read_enum(nodes, "TriggerActivation", _TRIGGER_ACTIVATION)
    exposure_mode = _read_enum(nodes, "ExposureMode", _EXPOSURE_MODE)
    rate_name, rate_value = _first_value(nodes, _RATE_FEATURES)
    _ = exposure_name, rate_name
    return CameraSettings(
        float(exposure) if exposure is not None else None,
        gain,
        float(rate_value) if rate_value is not None else None,
        roi,
        str(pixel_format) if pixel_format is not None else None,
        trigger_selector,
        str(trigger_source) if trigger_source is not None else None,
        trigger_activation,
        exposure_mode,
    )


def apply_settings(
    camera: Any, requested: CameraSettings, pylon: Any
) -> SettingsReadbackRecord:
    nodes = camera.GetNodeMap()
    _disable_supported_auto(nodes, "ExposureAuto")
    _disable_supported_auto(nodes, "GainAuto")
    if requested.pixel_format is not None:
        try:
            device_pixel_type(pylon, requested.pixel_format)
        except ValueError as exc:
            raise CameraAdapterError(
                "UNSUPPORTED_FEATURE", str(exc), field_path="settings.pixel_format"
            ) from exc
        _set_first(
            nodes, ("PixelFormat",), requested.pixel_format, "settings.pixel_format"
        )
    _apply_float(nodes, _FLOAT_FEATURES, requested.exposure_us, "settings.exposure_us")
    if requested.gain is not None:
        if requested.gain.selector is not None:
            set_enum(nodes, "GainSelector", requested.gain.selector)
        gain_name, current = _first_value(nodes, _GAIN_FEATURES)
        if gain_name is None:
            raise CameraAdapterError(
                "UNSUPPORTED_FEATURE",
                "camera exposes no mapped gain feature",
                field_path="settings.gain",
            )
        _validate_gain_type(requested.gain, current, gain_name, nodes)
        _write_numeric(
            nodes,
            gain_name,
            requested.gain.value,
            "raw" if gain_name == "GainRaw" else _unit(nodes, gain_name),
            "settings.gain",
        )
    apply_roi(nodes, requested.roi)
    if (
        requested.frame_rate_hz is not None
        and read_value(nodes, "TriggerMode") == "Off"
    ):
        _enable_supported_rate(nodes)
    _apply_float(
        nodes, _RATE_FEATURES, requested.frame_rate_hz, "settings.frame_rate_hz"
    )
    for _field, node_name, value, mapping in (
        (
            "trigger_selector",
            "TriggerSelector",
            requested.trigger_selector,
            _TRIGGER_SELECTOR,
        ),
        ("trigger_source", "TriggerSource", requested.trigger_source, None),
        (
            "trigger_activation",
            "TriggerActivation",
            requested.trigger_activation,
            _TRIGGER_ACTIVATION,
        ),
        (
            "exposure_duration_mode",
            "ExposureMode",
            requested.exposure_duration_mode,
            _EXPOSURE_MODE,
        ),
    ):
        if value is not None:
            if mapping is None:
                write_value(nodes, node_name, value)
            else:
                set_enum(nodes, node_name, value, canonical=mapping)
    actual = read_settings(camera)
    adjustments = tuple(
        SettingAdjustmentRecord(field, str(wanted), str(found))
        for field, wanted, found in _requested_values(requested, actual)
        if wanted is not None and found != wanted
    )
    effective = _numeric(read_value(nodes, "BslEffectiveExposureTime"))
    if effective is None:
        effective = _numeric(read_value(nodes, "EffectiveExposureTime"))
    return SettingsReadbackRecord(actual, adjustments, effective)


def capabilities(camera: Any, pylon: Any) -> CameraCapabilities:
    nodes = camera.GetNodeMap()
    gain_name = _first_available(nodes, _GAIN_FEATURES)
    gain_value = None if gain_name is None else read_value(nodes, gain_name)
    gain_unit = "raw" if gain_name == "GainRaw" else _unit(nodes, gain_name)
    pixel_cap = enum_capability(nodes, "PixelFormat")
    pixel_choices: list[EnumChoice] = []
    for choice in pixel_cap.choices:
        try:
            device_pixel_type(pylon, choice.sdk_symbol)
        except ValueError:
            continue
        pixel_choices.append(choice)
    return CameraCapabilities(
        _numeric_capability(nodes, _FLOAT_FEATURES, "us"),
        GainCapability(
            None
            if gain_name is None or gain_value is None
            else capability(nodes, gain_name, unit=gain_unit),
            enum_capability(nodes, "GainSelector"),
        ),
        _numeric_capability(nodes, _RATE_FEATURES, "Hz"),
        RoiCapabilities(
            _integer_capability(nodes, "Width", "pixels"),
            _integer_capability(nodes, "Height", "pixels"),
            roi_integer_capability(nodes, "OffsetX"),
            roi_integer_capability(nodes, "OffsetY"),
        ),
        EnumCapability(pixel_cap.access, tuple(pixel_choices)),
        enum_capability(nodes, "TriggerSelector", canonical=_TRIGGER_SELECTOR),
        enum_capability(nodes, "TriggerSource"),
        enum_capability(nodes, "TriggerActivation", canonical=_TRIGGER_ACTIVATION),
        enum_capability(nodes, "ExposureMode", canonical=_EXPOSURE_MODE),
        TriggerRateLimit(*_trigger_rate_limit(nodes)),
    )


def _enable_supported_rate(nodes: Any) -> None:
    name = "AcquisitionFrameRateEnable"
    node = get_node(nodes, name)
    if node is None:
        return
    write_value(nodes, name, True)
    if read_value(nodes, name) is not True:
        raise CameraAdapterError(
            "SDK_STATE", "AcquisitionFrameRateEnable readback differs"
        )


def _trigger_rate_limit(nodes: Any) -> tuple[float | None, str]:
    for name in (
        "BslResultingAcquisitionFrameRate",
        "ResultingFrameRate",
        "ResultingFrameRateAbs",
    ):
        node = get_node(nodes, name)
        value = _numeric(read_value(nodes, name)) if node is not None else None
        if value is None or not math.isfinite(value) or value <= 0:
            continue
        unit = _unit(nodes, name)
        if unit not in ("Hz", "Hz "):
            continue
        return value, f"connected SDK estimate from readable {name} ({unit.strip()})"
    return None, "connected model exposes no readable documented resulting-rate node"


def _apply_float(
    nodes: Any, names: tuple[str, ...], value: float | None, field: str
) -> None:
    if value is None:
        return
    if not math.isfinite(value) or value <= 0:
        raise CameraAdapterError(
            "INVALID_SETTING", "value must be finite and positive", field_path=field
        )
    name = _first_available(nodes, names)
    if name is None:
        raise CameraAdapterError(
            "UNSUPPORTED_FEATURE", f"no mapped feature for {field}", field_path=field
        )
    unit = "us" if names == _FLOAT_FEATURES else "Hz"
    _write_numeric(nodes, name, value, unit, field)


def _write_numeric(
    nodes: Any,
    name: str,
    value: int | float,
    unit: str,
    field: str,
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CameraAdapterError(
            "INVALID_SETTING", "numeric value required", field_path=field
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise CameraAdapterError(
            "INVALID_SETTING", "numeric value must be finite", field_path=field
        )
    limits = capability(nodes, name, unit=unit)
    if isinstance(limits, IntegerCapability):
        if not isinstance(value, int):
            raise CameraAdapterError(
                "INVALID_SETTING", f"{name} requires an integer", field_path=field
            )
        if limits.minimum is None or limits.maximum is None or limits.increment is None:
            raise CameraAdapterError(
                "UNSUPPORTED_FEATURE",
                f"{name} has incomplete live limits",
                field_path=field,
            )
        if (
            value < limits.minimum
            or value > limits.maximum
            or (value - limits.minimum) % limits.increment
        ):
            raise CameraAdapterError(
                "INVALID_SETTING",
                f"{name} violates current SDK range/increment",
                field_path=field,
            )
    else:
        if limits.minimum is None or limits.maximum is None:
            raise CameraAdapterError(
                "UNSUPPORTED_FEATURE",
                f"{name} has incomplete live range",
                field_path=field,
            )
        if not limits.minimum <= float(value) <= limits.maximum:
            raise CameraAdapterError(
                "INVALID_SETTING",
                f"{name} violates current SDK range",
                field_path=field,
            )
        if limits.increment is not None and limits.increment > 0:
            steps = (float(value) - limits.minimum) / limits.increment
            if not math.isclose(steps, round(steps), rel_tol=1e-9, abs_tol=1e-9):
                raise CameraAdapterError(
                    "INVALID_SETTING",
                    f"{name} violates current SDK increment",
                    field_path=field,
                )
    write_value(nodes, name, value)


def _set_first(
    nodes: Any, names: tuple[str, ...], value: bool | int | float | str, field: str
) -> None:
    name = _first_available(nodes, names)
    if name is None:
        raise CameraAdapterError(
            "UNSUPPORTED_FEATURE", f"no mapped feature for {field}", field_path=field
        )
    write_value(nodes, name, value)


def _disable_supported_auto(nodes: Any, name: str) -> None:
    node = get_node(nodes, name)
    if node is None:
        return
    set_enum(nodes, name, "Off")
    if read_value(nodes, name) != "Off":
        raise CameraAdapterError("SDK_STATE", f"{name} did not read back Off")


def _first_available(nodes: Any, names: tuple[str, ...]) -> str | None:
    return next((name for name in names if get_node(nodes, name) is not None), None)


def _first_value(nodes: Any, names: tuple[str, ...]) -> tuple[str | None, Any | None]:
    name = _first_available(nodes, names)
    return (name, None) if name is None else (name, read_value(nodes, name))


def _read_enum(nodes: Any, name: str, mapping: dict[str, str]) -> str | None:
    raw = read_value(nodes, name)
    if raw is None:
        return None
    symbol = str(raw)
    return mapping.get(symbol, symbol)


def _requested_values(
    requested: CameraSettings, actual: CameraSettings
) -> tuple[tuple[str, Any, Any], ...]:
    return (
        ("settings.exposure_us", requested.exposure_us, actual.exposure_us),
        ("settings.gain", requested.gain, actual.gain),
        ("settings.frame_rate_hz", requested.frame_rate_hz, actual.frame_rate_hz),
        (
            "settings.roi.width",
            requested.roi.width if requested.roi is not None else None,
            actual.roi.width if actual.roi is not None else None,
        ),
        (
            "settings.roi.height",
            requested.roi.height if requested.roi is not None else None,
            actual.roi.height if actual.roi is not None else None,
        ),
        (
            "settings.roi.offset_x",
            requested.roi.offset_x if requested.roi is not None else None,
            actual.roi.offset_x if actual.roi is not None else None,
        ),
        (
            "settings.roi.offset_y",
            requested.roi.offset_y if requested.roi is not None else None,
            actual.roi.offset_y if actual.roi is not None else None,
        ),
        ("settings.pixel_format", requested.pixel_format, actual.pixel_format),
        (
            "settings.trigger_selector",
            requested.trigger_selector,
            actual.trigger_selector,
        ),
        ("settings.trigger_source", requested.trigger_source, actual.trigger_source),
        (
            "settings.trigger_activation",
            requested.trigger_activation,
            actual.trigger_activation,
        ),
        (
            "settings.exposure_duration_mode",
            requested.exposure_duration_mode,
            actual.exposure_duration_mode,
        ),
    )


def _numeric(value: Any) -> float | None:
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else None
    )


def _integer(value: Any) -> int | None:
    return (
        int(value) if isinstance(value, int) and not isinstance(value, bool) else None
    )


def _validate_gain_type(
    requested: CameraGain, current: Any, feature: str, nodes: Any
) -> None:
    if isinstance(current, bool) or not isinstance(current, (int, float)):
        raise CameraAdapterError(
            "SDK_STATE",
            "mapped gain feature is not numeric",
            field_path="settings.gain",
        )
    if (isinstance(current, int) and not isinstance(requested.value, int)) or (
        isinstance(current, float) and not isinstance(requested.value, float)
    ):
        raise CameraAdapterError(
            "INVALID_SETTING",
            f"gain value type does not match {feature}",
            field_path="settings.gain",
        )
    actual_unit = "raw" if feature == "GainRaw" else _unit(nodes, feature)
    if not actual_unit or actual_unit == "unknown":
        raise CameraAdapterError(
            "UNSUPPORTED_FEATURE",
            f"{feature} does not expose its actual gain unit",
            field_path="settings.gain.unit",
        )
    if requested.unit != actual_unit:
        raise CameraAdapterError(
            "INVALID_SETTING",
            f"requested gain unit {requested.unit!r} differs from connected unit {actual_unit!r}",
            field_path="settings.gain.unit",
        )


def _numeric_capability(nodes: Any, names: tuple[str, ...], unit: str) -> Any:
    name = _first_available(nodes, names)
    return (
        IntegerCapability("unavailable", None, None, None, unit)
        if name is None
        else capability(nodes, name, unit=unit)
    )


def _integer_capability(nodes: Any, name: str, unit: str) -> IntegerCapability:
    node = get_node(nodes, name)
    if node is None:
        return IntegerCapability("unavailable", None, None, None, unit)
    result = capability(nodes, name, unit=unit)
    if not isinstance(result, IntegerCapability):
        raise CameraAdapterError(
            "SDK_STATE", f"mapped ROI feature {name} is not an integer node"
        )
    return result


def _unit(nodes: Any, name: str | None) -> str:
    if name is None:
        return "unknown"
    node = get_node(nodes, name)
    getter = getattr(node, "GetUnit", None) if node is not None else None
    return str(getter()) if callable(getter) else "unknown"
