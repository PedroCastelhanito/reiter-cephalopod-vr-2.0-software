"""Apply one camera's local parameters before its explicit diagnostic action."""

from collections.abc import Callable
from typing import Any

from cephvr.acquisition.identity import camera_role_name
from cephvr.client.session import ClientError, HeadlessClient
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.device_requests import assign_camera_role
from cephvr.gui.managed_device_commands import _save_camera_settings


async def prepare_camera(
    client: HeadlessClient,
    options: dict[str, Any],
    accepted: Callable[[pb.Snapshot], None],
) -> None:
    """Reject a changed base; use existing configuration and SDK import owners."""
    state = client.snapshot
    if (
        state.controller_generation != options["generation"]
        or state.configuration.revision != options["base_revision"]
        or state.configuration_values.revision != state.configuration.revision
        or state.configuration_values.current.SerializeToString(deterministic=True)
        != options["base_configuration"]
    ):
        raise ClientError("Camera configuration changed; refresh before retrying.")
    if state.session.phase not in (
        pb.SESSION_PHASE_CONFIGURATION,
        pb.SESSION_PHASE_READY,
    ):
        raise ClientError("Camera parameters can only change before the experiment.")
    role = int(options["camera_role"])
    backend = next(
        (
            item
            for item in state.configuration_values.current.backends
            if item.backend_name == "acquisition"
        ),
        None,
    )
    if backend is None:
        raise ClientError("Acquisition settings are unavailable.")
    selected = getattr(backend.acquisition, camera_role_name(role))
    assignment_changed = selected.device.device_id != options["serial"]
    if assignment_changed:
        await assign_camera_role(client, options)
        accepted(client.snapshot)
    await _save_camera_settings(
        client,
        dict(options, prepare_action=True, import_preset=assignment_changed),
        accepted=accepted,
    )
