"""Shared strict value bindings for acquisition defaults and file policies."""

from __future__ import annotations

import math
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from cephvr.acquisition.v1 import camera_pb2
from cephvr.shared.config import ConfigurationError


def _required(values: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in values:
        raise ConfigurationError(f"missing required acquisition setting {path}")
    return values[key]


def _positive_int(value: object, path: str, maximum: int = (1 << 32) - 1) -> int:
    if type(value) is not int or value <= 0 or value > maximum:
        raise ConfigurationError(f"{path} must be an integer in 1..{maximum}")
    return value


def _duration_ns(value: object, path: str, scale: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise ConfigurationError(f"{path} must be a finite positive duration")
    decimal = Decimal(value) if isinstance(value, int) else value
    result = decimal * scale
    if not result.is_finite() or result <= 0 or result != result.to_integral_value():
        raise ConfigurationError(f"{path} must resolve to a positive whole nanosecond")
    if result > (1 << 63) - 1:
        raise ConfigurationError(f"{path} exceeds the int64 nanosecond limit")
    return int(result)


def _number(value: object, path: str, *, positive: bool = True) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ConfigurationError(f"{path} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise ConfigurationError(f"{path} must be finite and positive")
    return result


def _role(config: Mapping[str, Any], role: str) -> camera_pb2.CameraPulseSettings:
    values = config.get("cameras", {}).get(role, {})
    pulse = camera_pb2.CameraPulseSettings()
    if "microcontroller_pin" in values:
        pulse.pin = _token(
            values["microcontroller_pin"], f"cameras.{role}.microcontroller_pin"
        )
    if "pulse_frequency_hz" in values:
        frequency = _number(
            values["pulse_frequency_hz"], f"cameras.{role}.pulse_frequency_hz"
        )
        if Decimal(str(values["pulse_frequency_hz"])) % Decimal("0.1") != 0:
            raise ConfigurationError(
                f"cameras.{role}.pulse_frequency_hz must use 0.1 Hz steps"
            )
        pulse.requested_frequency_hz = frequency
    return pulse


def _token(value: object, path: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(ch.isspace() or ch in "=," for ch in value)
    ):
        raise ConfigurationError(f"{path} must be a nonempty firmware-safe token")
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ConfigurationError(f"{path} must contain printable ASCII") from exc
    if any(ord(ch) < 33 or ord(ch) > 126 for ch in value):
        raise ConfigurationError(f"{path} must contain printable ASCII")
    return value


def _load_transport(
    target: camera_pb2.CameraTransportSettings, values: dict[str, Any], role: str
) -> None:
    accepted: dict[str, tuple[str, type, set[str] | None]] = {
        "DeviceLinkThroughputLimitMode": ("enum_symbol", str, {"On", "Off"}),
        "DeviceLinkThroughputLimit": ("integer", int, None),
    }
    for name, value in values.items():
        spec = accepted.get(name)
        if spec is None:
            raise ConfigurationError(f"cameras.{role}.transport.{name} is unsupported")
        wire_field, expected_type, choices = spec
        if wire_field == "integer":
            if type(value) is not int or value <= 0:
                raise ConfigurationError(
                    f"cameras.{role}.transport.{name} must be positive bytes per second"
                )
        elif type(value) is not str or (choices is not None and value not in choices):
            raise ConfigurationError(
                f"cameras.{role}.transport.{name} has an invalid native type/value"
            )
        override = target.overrides.add(sdk_name=name)
        setattr(override, wire_field, value)


def _bool(value: object, path: str) -> bool:
    if type(value) is not bool:
        raise ConfigurationError(f"{path} must be a boolean")
    return value


def _validate_microcontroller_defaults(values: dict[str, Any]) -> None:
    _positive_int(
        _required(values, "baud_rate", "microcontroller.baud_rate"),
        "microcontroller.baud_rate",
    )
    ack = _required(values, "ack_timeout_ms", "microcontroller.ack_timeout_ms")
    margin = _required(
        values, "stop_completion_margin_ms", "microcontroller.stop_completion_margin_ms"
    )
    keepalive = _required(
        values, "keepalive_interval_s", "microcontroller.keepalive_interval_s"
    )
    communication = _required(
        values, "communication_timeout_s", "microcontroller.communication_timeout_s"
    )
    _positive_int(ack, "microcontroller.ack_timeout_ms")
    _positive_int(margin, "microcontroller.stop_completion_margin_ms")
    keepalive_ns = _duration_ns(
        keepalive, "microcontroller.keepalive_interval_s", 1_000_000_000
    )
    comm_ns = _duration_ns(
        communication, "microcontroller.communication_timeout_s", 1_000_000_000
    )
    if keepalive_ns >= comm_ns:
        raise ConfigurationError(
            "microcontroller keepalive must be shorter than communication timeout"
        )
    # E05's actual stop-report allowance and resolved camera drains are supplied by
    # Setup. The loader checks exact values here; the coordinator checks the whole path.
