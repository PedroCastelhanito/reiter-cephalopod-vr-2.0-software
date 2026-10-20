"""Focused access to acquisition entries; validation remains with each owner."""

from cephvr.acquisition.identity import CAMERA_NAMES
from cephvr.control.v1 import types_pb2 as pb


def acquisition_backends(
    configuration: pb.ExperimentConfiguration,
) -> list[pb.BackendSettings]:
    """Preserve order, duplicate entries and dormant/malformed settings for validation."""
    return [
        item for item in configuration.backends if item.backend_name == "acquisition"
    ]


def session_camera_configuration(
    configuration: pb.ExperimentConfiguration,
) -> pb.ExperimentConfiguration:
    """Resolve camera demand on a session copy, preserving operator selections."""
    effective = pb.ExperimentConfiguration.FromString(configuration.SerializeToString())
    tracking_required = any(
        item.backend_name == "tracking" and item.enabled for item in effective.backends
    )
    for backend in acquisition_backends(effective):
        if not backend.enabled or not backend.HasField("acquisition"):
            continue
        for role in CAMERA_NAMES:
            camera = getattr(backend.acquisition, role)
            if camera.enabled and camera.HasField("save_video"):
                camera.enabled = camera.save_video or (
                    role == "tracking" and tracking_required
                )
        if (
            not any(getattr(backend.acquisition, role).enabled for role in CAMERA_NAMES)
            and not backend.acquisition.pulses.trial_state_enabled
        ):
            backend.enabled = False
    return effective


def preserve_camera_selections(
    effective: pb.ExperimentConfiguration, requested: pb.ExperimentConfiguration
) -> pb.ExperimentConfiguration:
    """Adopt device readback without persisting the session-only demand filter."""
    accepted = pb.ExperimentConfiguration.FromString(effective.SerializeToString())
    original = acquisition_backends(requested)
    targets = acquisition_backends(accepted)
    if len(original) == len(targets) == 1:
        targets[0].enabled = original[0].enabled
        for role in CAMERA_NAMES:
            source = getattr(original[0].acquisition, role)
            target = getattr(targets[0].acquisition, role)
            if source.HasField("enabled"):
                target.enabled = source.enabled
            else:
                target.ClearField("enabled")
    return accepted
