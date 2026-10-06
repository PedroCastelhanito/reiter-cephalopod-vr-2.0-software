"""Focused controller requests for camera assignment and sequential connection checks."""

from typing import Any, cast

from cephvr.client.session import ClientError, HeadlessClient
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb


async def test_camera_connections(
    client: HeadlessClient, cameras: list[tuple[int, str]]
) -> tuple[bool, str]:
    results = []
    succeeded = True
    for role, serial in cameras:
        state = client.snapshot
        selected = next(
            (
                item.acquisition
                for item in state.configuration_values.current.backends
                if item.backend_name == "acquisition" and item.enabled
            ),
            None,
        )
        configured = (
            (selected.behavioral if role == 1 else selected.tracking)
            if selected
            else None
        )
        if (
            configured is None
            or not configured.enabled
            or configured.device.device_id != serial
        ):
            results.append(f"{serial}: skipped; assignment or enablement changed")
            succeeded = False
            continue
        device = (
            state.acquisition_devices.behavioral
            if role == 1
            else state.acquisition_devices.tracking
        )
        if device.preview_running:
            results.append(
                f"{serial}: capture already running; connection check skipped"
            )
            continue
        try:
            outcome = await client.execute(
                "ExecuteCameraCommand",
                rpc.CameraCommandRequest(
                    command=client.operator_command(),
                    expected_configuration_revision=state.configuration.revision,
                    camera=cast(Any, role),
                    kind=rpc.CAMERA_COMMAND_KIND_TEST_CONNECTION,
                ),
            )
            if not outcome.succeeded:
                raise ClientError(outcome.failure or "Connection check failed")
            results.append(f"{serial}: connection and identity verified")
        except (ClientError, TimeoutError) as exc:
            results.append(f"{serial}: {exc}")
            succeeded = False
    return succeeded, "\n".join(results)


async def assign_camera_role(client: HeadlessClient, options: dict[str, Any]) -> None:
    state = client.snapshot
    proposed = pb.ExperimentConfiguration()
    proposed.CopyFrom(state.configuration_values.current)
    acquisition = next(
        (
            item.acquisition
            for item in proposed.backends
            if item.backend_name == "acquisition"
        ),
        None,
    )
    if acquisition is None:
        raise ClientError("Acquisition settings are unavailable.")
    serial, role = str(options["serial"]), str(options["role"])
    roles = {
        "Behavior cam": acquisition.behavioral,
        "Tracking cam": acquisition.tracking,
    }
    if not serial or role not in (*roles, "Unassigned"):
        raise ClientError("Select a supported camera role.")
    for selected in roles.values():
        if selected.device.device_id == serial:
            selected.enabled = False
            selected.device.device_id = ""
    if role in roles:
        roles[role].device.device_id = serial
        roles[role].enabled = False
    outcome = await client.execute(
        "UpdateConfiguration",
        rpc.UpdateConfigurationRequest(
            command=client.operator_command(),
            expected_revision=state.configuration.revision,
            proposed=proposed,
        ),
    )
    if not outcome.succeeded:
        raise ClientError(outcome.failure or "Camera role assignment was rejected.")


async def import_camera_preset(client: HeadlessClient, role: int, path: str) -> None:
    """Import through the SDK owner and explicitly finish this GUI editing operation."""
    failure = ""
    for kind in (
        rpc.CAMERA_COMMAND_KIND_IMPORT_PFS,
        rpc.CAMERA_COMMAND_KIND_FINISH_EDITING,
    ):
        request = rpc.CameraCommandRequest(
            command=client.operator_command(),
            expected_configuration_revision=client.snapshot.configuration.revision,
            camera=cast(Any, role),
            kind=cast(Any, kind),
        )
        if kind == rpc.CAMERA_COMMAND_KIND_IMPORT_PFS:
            request.path = path
        try:
            outcome = await client.execute("ExecuteCameraCommand", request)
            if not outcome.succeeded:
                raise ClientError(outcome.failure or "PFS operation failed")
        except (ClientError, TimeoutError) as exc:
            failure += ("; " if failure else "") + str(exc)
    if failure:
        raise ClientError(failure)
