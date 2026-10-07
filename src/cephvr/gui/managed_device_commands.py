"""Controller-backed device requests kept separate from GUI transport scheduling."""

from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from cephvr.acquisition.v1 import camera_pb2
from cephvr.client.session import ClientError, HeadlessClient
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.microcontroller.firmware_source import read_firmware
from cephvr.gui.device_requests import (
    assign_camera_role,
    import_camera_preset,
    test_camera_connections,
)
from cephvr.shared.auth import Principal


async def dispatch_device_action(
    client: HeadlessClient,
    action: str,
    options: dict[str, Any],
    principal: Principal,
) -> tuple[bool, str] | None:
    """Dispatch one device request; return None when another owner handles it."""
    if action == "camera":
        await _camera(client, options)
        return True, "Completed"
    if action == "test_cameras":
        return await test_camera_connections(client, options["cameras"])
    if action in {"mcu", "mcu_upload"}:
        state = client.snapshot
        image = None
        if action == "mcu_upload":
            try:
                image = await asyncio.to_thread(read_firmware, str(options["path"]))
            except (OSError, UnicodeError, ValueError) as exc:
                raise ClientError(str(exc)) from exc
        request = rpc.MicrocontrollerCommandRequest(
            command=client.operator_command(),
            expected_configuration_revision=state.configuration.revision,
            kind=cast(
                Any,
                rpc.MICROCONTROLLER_COMMAND_KIND_UPLOAD_FIRMWARE
                if image
                else options["kind"],
            ),
            signal=cast(Any, options.get("signal", 0)),
        )
        if image is not None:
            request.firmware_path = str(image.path)
            request.firmware_sha256 = image.digest
        outcome = await client.execute("ExecuteMicrocontrollerCommand", request)
        if not outcome.succeeded:
            raise ClientError(outcome.failure or "MCU operation did not succeed.")
        return True, "Completed"
    if action == "spikeglx_connection":
        result = await client.stub.CheckSpikeGLXConnection(
            rpc.SpikeGLXConnectionQuery(client_id=principal.generation),
            metadata=principal.metadata(),
            timeout=6,
        )
        if result.error:
            raise ClientError(result.error)
        return True, (
            f"{result.address}:{result.port} · {result.version} · "
            f"running={result.running} · saving={result.saving} · "
            f"run={result.run_name or 'unvalidated'} · data={result.data_directory}"
        )
    if action == "save_mcu_pins":
        state = client.snapshot
        proposed = type(state.configuration_values.current)()
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
        pulses = acquisition.pulses
        pulses.port = options["port"]
        for field, value in (
            ("trial_state_pin", options["trial_pin"]),
            ("projector_flip_pin", options["flip_pin"]),
        ):
            if value:
                setattr(pulses, field, value)
            else:
                pulses.ClearField(field)
        pulses.trial_state_enabled = options["trial_enabled"]
        pulses.projector_flip_enabled = options["flip_enabled"]
        for pulse, value in (
            (pulses.behavioral, options["behavioral_pin"]),
            (pulses.tracking, options["tracking_pin"]),
        ):
            if value is None:
                continue
            if value:
                pulse.pin = value
            else:
                pulse.ClearField("pin")
        await _update_configuration(client, state, proposed, "MCU pin settings")
        return True, "Completed"
    if action == "assign_camera_role":
        await assign_camera_role(client, options)
        return True, "Completed"
    if action == "set_camera_enabled":
        state = client.snapshot
        proposed = type(state.configuration_values.current)()
        proposed.CopyFrom(state.configuration_values.current)
        acquisition_entry, selected, _ = _assigned_camera(
            proposed, str(options["serial"])
        )
        enabled = bool(options["enabled"])
        selected.enabled = enabled
        if enabled:
            acquisition_entry.enabled = True
        await _update_configuration(client, state, proposed, "Camera enablement")
        return True, "Completed"
    if action == "save_camera_settings":
        await _save_camera_settings(client, options)
        return True, "Completed"
    return None


async def _camera(
    client: HeadlessClient,
    options: dict[str, Any],
) -> None:
    kind = int(options["kind"])
    role = int(options["role"])
    state = client.snapshot
    request = rpc.CameraCommandRequest(
        command=client.operator_command(),
        expected_configuration_revision=state.configuration.revision,
    )
    request.camera = cast(Any, role)
    request.kind = cast(Any, kind)
    if kind == rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW and "placement" in options:
        request.preview_placement.ParseFromString(options["placement"])
    if kind in (
        rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW,
        rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW,
        rpc.CAMERA_COMMAND_KIND_HIDE_PREVIEW,
    ):
        camera = (
            state.acquisition_devices.behavioral
            if role == 1
            else state.acquisition_devices.tracking
        )
        if not camera.preview_run_id:
            raise ClientError("No current preview run for this camera.")
        request.preview_run_id = camera.preview_run_id
    outcome = await client.execute("ExecuteCameraCommand", request)
    if not outcome.succeeded:
        raise ClientError(outcome.failure or "Camera operation did not succeed.")
    if kind == rpc.CAMERA_COMMAND_KIND_START_PREVIEW and options.get("show_preview"):
        # Completion's current view supplies the exact new run; Show never starts capture.
        current = client.snapshot
        device = (
            current.acquisition_devices.behavioral
            if role == 1
            else current.acquisition_devices.tracking
        )
        if not device.preview_running or not device.preview_run_id:
            raise ClientError(
                "Capture completed without a confirmed preview run; refresh camera status."
            )
        show = rpc.CameraCommandRequest(
            command=client.operator_command(),
            expected_configuration_revision=current.configuration.revision,
            camera=cast(Any, role),
            kind=rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW,
            preview_run_id=device.preview_run_id,
        )
        if "placement" in options:
            show.preview_placement.ParseFromString(options["placement"])
        shown = await client.execute("ExecuteCameraCommand", show)
        if not shown.succeeded:
            raise ClientError(
                f"Capture started; preview could not open: {shown.failure or 'unconfirmed presentation'}. "
                "Disconnect to stop capture."
            )


async def _save_camera_settings(
    client: HeadlessClient, options: dict[str, Any]
) -> None:
    state = client.snapshot
    proposed = type(state.configuration_values.current)()
    proposed.CopyFrom(state.configuration_values.current)
    acquisition, selected, pulse = _assigned_camera(proposed, str(options["serial"]))
    clock = str(options["clock"])
    if clock == "External controller":
        source = str(options["source"]).strip()
        if not source:
            raise ClientError(
                "Select a PFS file with an explicit FrameStart line source."
            )
        selected.device.frame_timing = camera_pb2.FRAME_TIMING_EXTERNAL_TRIGGER
        selected.device.unaligned_free_running = False
        selected.device.settings.trigger_source = source
    elif clock == "Internal clock":
        selected.device.frame_timing = camera_pb2.FRAME_TIMING_FREE_RUNNING
        selected.device.unaligned_free_running = True
        selected.device.settings.ClearField("trigger_source")
    else:
        raise ClientError("Select a camera trigger source before saving.")
    preset = str(options["preset"]).strip()
    import_preset = bool(
        preset
        and (
            options.get("import_preset", False)
            or preset != selected.device.pfs_source_filename
            or not selected.device.HasField("pfs_baseline")
        )
    )
    if preset:
        if import_preset:
            if not acquisition.enabled:
                acquisition.acquisition.behavioral.enabled = False
                acquisition.acquisition.tracking.enabled = False
            acquisition.enabled = True
            selected.device.ClearField("pfs_baseline")
        selected.device.pfs_source_filename = preset
    else:
        selected.device.ClearField("pfs_source_filename")
    rate = str(options["rate"]).strip()
    if rate:
        try:
            frequency = Decimal(rate)
        except InvalidOperation as exc:
            raise ClientError("Camera trigger rate is not a number.") from exc
        if not frequency.is_finite() or frequency <= 0 or frequency % Decimal("0.1"):
            raise ClientError("Camera trigger rate must use a positive 0.1 Hz grid.")
        pulse.requested_frequency_hz = float(frequency)
    await _update_configuration(client, state, proposed, "Camera settings")
    if import_preset:
        role = (
            1
            if acquisition.acquisition.behavioral.device.device_id
            == str(options["serial"])
            else 2
        )
        await import_camera_preset(client, role, preset)


async def _update_configuration(
    client: HeadlessClient,
    state: pb.Snapshot,
    proposed: pb.ExperimentConfiguration,
    label: str,
) -> None:
    outcome = await client.execute(
        "UpdateConfiguration",
        rpc.UpdateConfigurationRequest(
            command=client.operator_command(),
            expected_revision=state.configuration.revision,
            proposed=proposed,
        ),
    )
    if not outcome.succeeded:
        raise ClientError(outcome.failure or f"{label} were rejected.")


def _assigned_camera(
    proposed: pb.ExperimentConfiguration, serial: str
) -> tuple[
    pb.BackendSettings,
    camera_pb2.CameraSessionSettings,
    camera_pb2.CameraPulseSettings,
]:
    acquisition = next(
        (item for item in proposed.backends if item.backend_name == "acquisition"),
        None,
    )
    if acquisition is None:
        raise ClientError("Acquisition settings are unavailable.")
    pairs = (
        (acquisition.acquisition.behavioral, acquisition.acquisition.pulses.behavioral),
        (acquisition.acquisition.tracking, acquisition.acquisition.pulses.tracking),
    )
    matches = [
        (settings, pulse)
        for settings, pulse in pairs
        if settings.device.device_id == serial
    ]
    if len(matches) != 1:
        raise ClientError(
            "Camera is not uniquely assigned in controller configuration."
        )
    return acquisition, *matches[0]
