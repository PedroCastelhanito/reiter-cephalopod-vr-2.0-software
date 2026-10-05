"""Pure validation entry point for operator-owned acquisition settings (E07/E14)."""

from __future__ import annotations

from cephvr.control.v1 import types_pb2

from .validation_buffers import validate_shared_options
from .validation_camera import validate_camera_role
from .validation_pulse import (
    validate_pulse_io,
    validate_pulse_port,
    validate_pulse_role,
)
from .validation_values import issue


def validate_configuration(
    candidate: types_pb2.ExperimentConfiguration,
) -> types_pb2.ValidationResult:
    """Validate typed settings without opening cameras or the serial device."""
    result = types_pb2.ValidationResult(
        completed=True,
        valid=True,
        component="acquisition",
        configuration_module_version="acquisition-config-v1",
    )
    selected = [
        backend
        for backend in candidate.backends
        if backend.backend_name == "acquisition"
    ]
    if len(selected) > 1:
        issue(
            result,
            "backends.acquisition",
            "DUPLICATE_BACKEND",
            "acquisition settings appear more than once",
        )
        return result
    if not selected:
        return result
    backend = selected[0]
    if backend.WhichOneof("settings") != "acquisition":
        issue(
            result,
            "backends.acquisition",
            "MISSING_SETTINGS",
            "acquisition backend has no typed settings",
        )
        return result

    settings = backend.acquisition
    active_ids: dict[str, str] = {}
    active_pins: dict[str, str] = {}
    if not backend.enabled:
        validate_pulse_io(settings, result, active_pins)
        validate_pulse_port(settings, result, ())
        return result
    external_roles: list[str] = []
    for role in ("behavioral", "tracking"):
        device_id = validate_camera_role(settings, role, result)
        if device_id is not None:
            active_ids[device_id] = role
        if validate_pulse_role(settings, role, result, active_pins):
            external_roles.append(role)
    validate_pulse_io(settings, result, active_pins)
    validate_pulse_port(settings, result, tuple(external_roles))
    validate_shared_options(settings, result, active_ids)
    return result
