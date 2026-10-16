"""Compensate only confirmed device resources created by a cancelled GUI intent."""

from typing import Any, cast

from cephvr.acquisition.identity import camera_role_name
from cephvr.client.session import ClientError, HeadlessClient
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb


async def cleanup_cancelled_device(
    client: HeadlessClient, action: str, options: dict[str, Any], before: pb.Snapshot
) -> None:
    request: Any
    state = client.snapshot
    if state.controller_generation != before.controller_generation:
        raise ClientError(
            "Cancellation cleanup unconfirmed: controller generation changed"
        )
    if action in {"camera", "prepare_camera"}:
        role = int(options.get("camera_role", options.get("role", 0)))
        name = camera_role_name(role)
        prior = getattr(before.acquisition_devices, name)
        current = getattr(state.acquisition_devices, name)
        if prior.device_open or prior.preview_running or prior.cleanup_pending:
            return
        if not (
            current.device_open or current.preview_running or current.cleanup_pending
        ):
            return
        expected_serial = options.get("serial")
        if expected_serial and current.device.configured_id != expected_serial:
            raise ClientError(
                "Cancellation cleanup unconfirmed: camera identity changed"
            )
        source = before.acquisition_devices.source.backend_generation
        if source and state.acquisition_devices.source.backend_generation != source:
            raise ClientError(
                "Cancellation cleanup unconfirmed: acquisition generation changed"
            )
        request = rpc.CameraCommandRequest(
            command=client.operator_command(),
            expected_configuration_revision=state.configuration.revision,
            camera=cast(Any, role),
            kind=rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW
            if current.preview_run_id
            else rpc.CAMERA_COMMAND_KIND_FINISH_EDITING,
            preview_run_id=current.preview_run_id,
        )
        await _complete(client, "ExecuteCameraCommand", request)
        closed = getattr(client.snapshot.acquisition_devices, name)
        if closed.device_open or closed.preview_running or closed.cleanup_pending:
            raise ClientError("Cancellation cleanup unconfirmed: camera is still owned")
    elif action in {"mcu", "prepare_mcu_connection", "prepare_mcu_test"}:
        prior = before.microcontroller
        current = state.microcontroller
        if not prior.observation.connection_id and current.observation.connection_id:
            request = rpc.MicrocontrollerCommandRequest(
                command=client.operator_command(),
                expected_configuration_revision=state.configuration.revision,
                kind=rpc.MICROCONTROLLER_COMMAND_KIND_DISCONNECT,
                expected_connection_id=current.observation.connection_id,
            )
            await _complete(client, "ExecuteMicrocontrollerCommand", request)
            if (
                client.snapshot.microcontroller.observation.connection_id
                or client.snapshot.microcontroller.cleanup_pending
            ):
                raise ClientError(
                    "Cancellation cleanup unconfirmed: MCU is still owned"
                )
        elif not prior.diagnostic.active and current.diagnostic.active:
            if current.observation.connection_id != prior.observation.connection_id:
                raise ClientError(
                    "Cancellation cleanup unconfirmed: MCU connection changed"
                )
            if current.diagnostic.signal != options.get("signal"):
                raise ClientError(
                    "Cancellation cleanup unconfirmed: MCU diagnostic identity changed"
                )
            request = rpc.MicrocontrollerCommandRequest(
                command=client.operator_command(),
                expected_configuration_revision=state.configuration.revision,
                kind=rpc.MICROCONTROLLER_COMMAND_KIND_STOP,
            )
            await _complete(client, "ExecuteMicrocontrollerCommand", request)
            if client.snapshot.microcontroller.diagnostic.active:
                raise ClientError(
                    "Cancellation cleanup unconfirmed: MCU diagnostic is still active"
                )

        if client.snapshot.microcontroller.cleanup_pending:
            raise ClientError("Cancellation cleanup unconfirmed: MCU cleanup pending")


async def _complete(client: HeadlessClient, method: str, request: Any) -> None:
    generation = client.snapshot.controller_generation
    result = await client.execute(method, request)
    if client.snapshot.controller_generation != generation:
        raise ClientError(
            "Cancellation cleanup unconfirmed: controller generation changed"
        )
    if not result.succeeded:
        raise ClientError(f"Cancellation cleanup unconfirmed: {result.failure}")
