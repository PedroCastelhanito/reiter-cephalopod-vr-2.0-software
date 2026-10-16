"""Selected-camera Configuration validation without changing experiment Use."""

from collections.abc import Callable

from google.protobuf.message import Message

from cephvr.acquisition.config.validation import validate_configuration
from cephvr.acquisition.identity import CAMERA_NAMES
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.configuration_access import acquisition_backends
from cephvr.controller.control.connection_edits import validate_connections


def validate_configuration_edit(
    current: pb.ExperimentConfiguration,
    proposed: pb.ExperimentConfiguration,
    validator: Callable[[pb.ExperimentConfiguration], pb.ValidationResult],
) -> pb.ValidationResult:
    """Apply action scoping only to an exact diff; otherwise use full validation."""
    scoped = camera_edit_validation(current, proposed, validator=validator)
    return validator(proposed) if scoped is None else scoped


def camera_edit_validation(
    current: pb.ExperimentConfiguration,
    proposed: pb.ExperimentConfiguration,
    *,
    validator: Callable[
        [pb.ExperimentConfiguration], pb.ValidationResult
    ] = validate_configuration,
) -> pb.ValidationResult | None:
    """Recognize one camera's parameter/pulse edit, preserving every other field."""
    old_entries = acquisition_backends(current)
    new_entries = acquisition_backends(proposed)
    if len(old_entries) != 1 or len(new_entries) != 1:
        return None
    if not old_entries[0].HasField("acquisition") or not new_entries[0].HasField(
        "acquisition"
    ):
        return None
    for role in CAMERA_NAMES:
        expected = pb.ExperimentConfiguration.FromString(current.SerializeToString())
        target = next(item.acquisition for item in acquisition_backends(expected))
        source = new_entries[0].acquisition
        _known_fields(getattr(target, role).device, getattr(source, role).device)
        _known_fields(getattr(target.pulses, role), getattr(source.pulses, role))
        if (
            not source.pulses.HasField(role)
            and not getattr(target.pulses, role).ByteSize()
        ):
            target.pulses.ClearField(role)
        if source.pulses.HasField("port"):
            target.pulses.port = source.pulses.port
        else:
            target.pulses.ClearField("port")
        if not source.HasField("pulses") and not target.pulses.ByteSize():
            target.ClearField("pulses")
        if expected == proposed and expected != current:
            return validate_selected_camera(proposed, role, validator)
    return None


def validate_selected_camera(
    candidate: pb.ExperimentConfiguration,
    role: str,
    validator: Callable[
        [pb.ExperimentConfiguration], pb.ValidationResult
    ] = validate_configuration,
) -> pb.ValidationResult:
    """Validate action inputs in a copy; retain the candidate's actual flags."""
    projection = pb.ExperimentConfiguration.FromString(candidate.SerializeToString())
    backend = next(item for item in acquisition_backends(projection))
    backend.enabled = True
    for name in CAMERA_NAMES:
        getattr(backend.acquisition, name).enabled = name == role
    # Manual preview does not create a recording path.
    getattr(backend.acquisition, role).save_video = False
    result = validator(projection)
    actual = next(item for item in acquisition_backends(candidate))
    connection = validate_connections(actual, selected_role=role)
    result.issues.extend(connection.issues)
    result.valid = result.valid and connection.valid
    return result


def _known_fields(target: Message, source: Message) -> None:
    """Copy declared fields while retaining unknown data for exact-diff comparison."""
    for field in source.DESCRIPTOR.fields:
        if field.message_type is not None:
            _known_fields(getattr(target, field.name), getattr(source, field.name))
            if source.HasField(field.name):
                getattr(target, field.name).SetInParent()
            elif not getattr(target, field.name).ByteSize():
                target.ClearField(field.name)
        elif not field.has_presence or source.HasField(field.name):
            setattr(target, field.name, getattr(source, field.name))
        else:
            target.ClearField(field.name)
