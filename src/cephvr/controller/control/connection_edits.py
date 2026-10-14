"""Exact E07 acquisition connection edits, distinct from capture readiness."""

from google.protobuf.message import Message

from cephvr.acquisition.config.validation_pulse import validate_pulse_port
from cephvr.acquisition.config.validation_values import (
    firmware_token,
    issue,
    valid_frequency,
)
from cephvr.acquisition.identity import CAMERA_NAMES
from cephvr.acquisition.v1 import camera_pb2
from cephvr.control.v1 import types_pb2 as pb


def connection_edit_validation(
    current: pb.ExperimentConfiguration, proposed: pb.ExperimentConfiguration
) -> pb.ValidationResult | None:
    """Validate only an exact identity/pulse-field diff; other edits use full validation."""
    expected = pb.ExperimentConfiguration.FromString(current.SerializeToString())
    before = [item for item in expected.backends if item.backend_name == "acquisition"]
    after = [item for item in proposed.backends if item.backend_name == "acquisition"]
    if len(before) != 1 or len(after) != 1:
        return None
    old, new = before[0], after[0]
    if not old.HasField("acquisition") or not new.HasField("acquisition"):
        return None
    for role in CAMERA_NAMES:
        camera, source_camera = (
            getattr(old.acquisition, role),
            getattr(new.acquisition, role),
        )
        camera.device.device_id = source_camera.device.device_id
        if not source_camera.HasField("device") and not camera.device.ByteSize():
            camera.ClearField("device")
        if not new.acquisition.HasField(role) and not camera.ByteSize():
            old.acquisition.ClearField(role)
    target, source = old.acquisition.pulses, new.acquisition.pulses
    for field in (
        "port",
        "trial_state_pin",
        "projector_flip_pin",
        "trial_state_enabled",
        "projector_flip_enabled",
    ):
        _copy_optional(target, source, field)
    for role in CAMERA_NAMES:
        for field in ("pin", "requested_frequency_hz"):
            _copy_optional(getattr(target, role), getattr(source, role), field)
        if not source.HasField(role) and not getattr(target, role).ByteSize():
            target.ClearField(role)
    if not new.acquisition.HasField("pulses") and not old.acquisition.pulses.ByteSize():
        old.acquisition.ClearField("pulses")
    if expected != proposed or expected == current:
        return None
    return validate_connections(new)


def validate_connections(
    backend: pb.BackendSettings, *, selected_role: str | None = None
) -> pb.ValidationResult:
    """Check supplied connection values and pins active for this exact action."""
    result = pb.ValidationResult(
        completed=True,
        valid=True,
        component="acquisition",
        configuration_module_version="acquisition-connection-v1",
    )
    settings = backend.acquisition
    validate_pulse_port(settings, result, ())
    identities: set[str] = set()
    active_pins: dict[str, str] = {}
    for role in CAMERA_NAMES:
        camera = getattr(settings, role)
        serial = camera.device.device_id
        if serial and (not firmware_token(serial) or serial in identities):
            issue(
                result,
                f"backends.acquisition.{role}.device.device_id",
                "INVALID_IDENTITY",
                "camera identities must be distinct printable tokens",
            )
        if serial:
            identities.add(serial)
        pulse = getattr(settings.pulses, role)
        active = (
            backend.enabled and camera.enabled or role == selected_role
        ) and camera.device.frame_timing == camera_pb2.FRAME_TIMING_EXTERNAL_TRIGGER
        _pin(result, pulse, "pin", role, active, active_pins)
        if pulse.HasField("requested_frequency_hz") and not valid_frequency(
            pulse.requested_frequency_hz
        ):
            issue(
                result,
                f"backends.acquisition.pulses.{role}.requested_frequency_hz",
                "INVALID_RATE",
                "pulse rate must be positive and use the exact 0.1 Hz grid",
            )
    if settings.pulses.projector_flip_enabled:
        issue(
            result,
            "backends.acquisition.pulses.projector_flip_enabled",
            "UNSUPPORTED_SIGNAL",
            "Projector flip input is deferred and cannot be enabled",
        )
    for role in ("trial_state",):
        _pin(
            result,
            settings.pulses,
            f"{role}_pin",
            role,
            getattr(settings.pulses, f"{role}_enabled"),
            active_pins,
        )
    return result


def _copy_optional(target: Message, source: Message, field: str) -> None:
    if source.HasField(field):
        setattr(target, field, getattr(source, field))
    else:
        target.ClearField(field)


def _pin(
    result: pb.ValidationResult,
    source: Message,
    field: str,
    role: str,
    active: bool,
    pins: dict[str, str],
) -> None:
    if not source.HasField(field):
        return
    value = getattr(source, field)
    path = (
        f"backends.acquisition.pulses.{role}.pin"
        if role in CAMERA_NAMES
        else f"backends.acquisition.pulses.{field}"
    )
    if not firmware_token(value):
        issue(result, path, "INVALID_PIN", "pin must be a printable firmware token")
    elif active:
        if value in pins:
            issue(
                result,
                path,
                "DUPLICATE_PIN",
                f"pin is already assigned to {pins[value]}",
            )
        pins[value] = role
