"""Pulse pin, frequency-grid and external-trigger validation stage."""

from __future__ import annotations

from cephvr.acquisition.v1 import camera_pb2
from cephvr.control.v1 import types_pb2

from .validation_values import firmware_token, issue, valid_frequency


def validate_pulse_role(
    settings: types_pb2.AcquisitionSettings,
    role: str,
    result: types_pb2.ValidationResult,
    active_pins: dict[str, str],
) -> bool:
    camera = getattr(settings, role)
    enabled = camera.HasField("enabled") and camera.enabled
    external = bool(
        enabled
        and camera.device.HasField("frame_timing")
        and camera.device.frame_timing == camera_pb2.FRAME_TIMING_EXTERNAL_TRIGGER
    )
    pulse = getattr(settings.pulses, role) if settings.HasField("pulses") else None
    if external:
        if (
            not camera.device.settings.HasField("trigger_source")
            or not camera.device.settings.trigger_source
        ):
            issue(
                result,
                f"backends.acquisition.{role}.device.settings.trigger_source",
                "TRIGGER_SOURCE_REQUIRED",
                "external trigger input must be explicit",
            )
        if pulse is None or not pulse.HasField("pin") or not firmware_token(pulse.pin):
            issue(
                result,
                f"backends.acquisition.pulses.{role}.pin",
                "PIN_REQUIRED",
                "externally triggered camera requires an explicit firmware pin",
            )
        if pulse is None or not pulse.HasField("requested_frequency_hz"):
            issue(
                result,
                f"backends.acquisition.pulses.{role}.requested_frequency_hz",
                "RATE_REQUIRED",
                "externally triggered camera requires an explicit pulse rate",
            )
        elif not valid_frequency(pulse.requested_frequency_hz):
            _rate_issue(result, role)
        if pulse is not None and pulse.HasField("pin") and firmware_token(pulse.pin):
            prior = active_pins.get(pulse.pin)
            if prior is not None:
                issue(
                    result,
                    f"backends.acquisition.pulses.{role}.pin",
                    "DUPLICATE_PIN",
                    f"pulse pin is already assigned to {prior}",
                )
            active_pins[pulse.pin] = role
    elif pulse is not None:
        if pulse.HasField("pin") and not firmware_token(pulse.pin):
            issue(
                result,
                f"backends.acquisition.pulses.{role}.pin",
                "INVALID_PIN",
                "pin must be a printable firmware token",
            )
        if pulse.HasField("requested_frequency_hz") and not valid_frequency(
            pulse.requested_frequency_hz
        ):
            _rate_issue(result, role)
    return external


def validate_pulse_port(
    settings: types_pb2.AcquisitionSettings,
    result: types_pb2.ValidationResult,
    external_roles: tuple[str, ...],
) -> None:
    has_port = settings.HasField("pulses") and settings.pulses.HasField("port")
    port = settings.pulses.port if has_port else ""
    if has_port and not port:
        issue(
            result,
            "backends.acquisition.pulses.port",
            "INVALID_PORT",
            "configured serial port cannot be empty",
        )
    if external_roles and not port:
        issue(
            result,
            "backends.acquisition.pulses.port",
            "PORT_REQUIRED",
            "externally triggered cameras require an explicit configured microcontroller port",
        )
    if port and not firmware_token(port):
        issue(
            result,
            "backends.acquisition.pulses.port",
            "INVALID_PORT",
            "microcontroller port must be a printable ASCII token",
        )


def _rate_issue(result: types_pb2.ValidationResult, role: str) -> None:
    issue(
        result,
        f"backends.acquisition.pulses.{role}.requested_frequency_hz",
        "INVALID_RATE",
        "requested pulse rate must be positive and use the exact 0.1 Hz grid",
    )
