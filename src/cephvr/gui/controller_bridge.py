"""Managed GUI observer and command transport (E03/E08)."""

from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from PyQt6.QtCore import QThread, pyqtSignal

from cephvr.acquisition.v1 import camera_pb2 as camera_pb
from cephvr.client.session import ClientError, HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.auth import Principal


class ControllerBridge(QThread):
    """Keep gRPC and WatchState on one asyncio loop outside Qt's UI thread."""

    snapshot_received = pyqtSignal(bytes)
    connection_changed = pyqtSignal(bool, str)
    command_finished = pyqtSignal(str, bool, str)
    attachment_received = pyqtSignal(int, bytes, bool)

    def __init__(
        self,
        principal: Principal,
        port: int,
        max_message_bytes: int,
        retry_delays_s: tuple[int, ...],
    ) -> None:
        super().__init__()
        self.principal = principal
        self.port = port
        self.max_message_bytes = max_message_bytes
        self.retry_delays_s = retry_delays_s
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[tuple[str, dict[str, Any]]] | None = None
        self._stopping = False

    def request(self, action: str, **kwargs: Any) -> bool:
        loop, queue = self._loop, self._queue
        if (
            loop is not None
            and queue is not None
            and (not self._stopping or action == "quit")
        ):
            loop.call_soon_threadsafe(queue.put_nowait, (action, kwargs))
            return True
        return False

    def stop(self) -> None:
        self._stopping = True
        self.request("quit")

    def run(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        attempt = 0
        while not self._stopping:
            await asyncio.sleep(
                self.retry_delays_s[min(attempt, len(self.retry_delays_s) - 1)]
            )
            if self._stopping:
                break
            try:
                async with loopback_channel(
                    self.port, self.max_message_bytes
                ) as channel:
                    client = HeadlessClient(
                        channel,
                        self.principal,
                        on_snapshot=lambda state: self.snapshot_received.emit(
                            state.SerializeToString()
                        ),
                    )
                    async with client.observe():
                        self.connection_changed.emit(True, "")
                        attempt = 0
                        await self._commands(client)
            except Exception as exc:
                self.connection_changed.emit(False, str(exc))
                attempt += 1
        self._loop = None
        self._queue = None

    async def _commands(self, client: HeadlessClient) -> None:
        assert self._queue is not None
        while not self._stopping:
            queued = asyncio.create_task(self._queue.get())
            assert client._reader is not None
            done, _ = await asyncio.wait(
                (queued, client._reader), return_when=asyncio.FIRST_COMPLETED
            )
            if client._reader in done:
                queued.cancel()
                raise ClientError("Controller state stream closed.")
            action, options = queued.result()
            if action == "quit":
                return
            try:
                await self._dispatch(client, action, options)
            except (ClientError, ValueError, TimeoutError) as exc:
                self.command_finished.emit(action, False, str(exc))
            except Exception as exc:
                self.command_finished.emit(action, False, f"Transport error: {exc}")

    async def _dispatch(
        self, client: HeadlessClient, action: str, options: dict[str, Any]
    ) -> None:
        if action == "take_control":
            await client.claim_control(takeover=bool(options.get("takeover")))
        elif action == "release_control":
            if client.snapshot.control.holder_client_id == self.principal.generation:
                await client.execute("ReleaseControl", wait=False)
        elif action == "save_configuration_history":
            holder = client.snapshot.control.holder_client_id
            if not holder:
                await client.claim_control()
            elif holder != self.principal.generation:
                raise ClientError(
                    "Another operator holds control of this configuration."
                )
            outcome = await client.execute("SaveConfigurationHistory")
            if not outcome.succeeded:
                raise ClientError(
                    outcome.failure or "Configuration history was not saved."
                )
        elif action == "camera":
            kind = int(options["kind"])
            role = int(options["role"])
            state = client.snapshot
            request = rpc.CameraCommandRequest(
                command=client.operator_command(),
                expected_configuration_revision=state.configuration.revision,
            )
            request.camera = cast(Any, role)
            request.kind = cast(Any, kind)
            if kind in (
                rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW,
                rpc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER,
            ):
                camera = (
                    state.acquisition_devices.behavioral
                    if role == 1
                    else state.acquisition_devices.tracking
                )
                if not camera.preview_run_id:
                    raise ClientError("No current preview run for this camera.")
                request.preview_run_id = camera.preview_run_id
            if kind == rpc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER:
                request.preview_consumer.role = "gui"
                request.preview_consumer.generation = self.principal.generation
            if kind == rpc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER:
                await client.execute("ExecuteCameraCommand", request, wait=False)
                query = rpc.PreviewAttachmentQuery(
                    client_id=self.principal.generation,
                    controller_generation=state.controller_generation,
                    consumer=request.preview_consumer,
                    preview_run_id=request.preview_run_id,
                )
                deadline = asyncio.get_running_loop().time() + client.rpc_timeout_s
                while True:
                    response = await client.stub.GetPreviewAttachment(
                        query,
                        metadata=self.principal.metadata(),
                        timeout=client.rpc_timeout_s,
                    )
                    if response.available:
                        break
                    if asyncio.get_running_loop().time() >= deadline:
                        raise ClientError(
                            response.failure.message or "Viewer transfer unavailable."
                        )
                    await asyncio.sleep(0.05)
                self.attachment_received.emit(
                    role, response.attachment.SerializeToString(), response.release_only
                )
            else:
                outcome = await client.execute("ExecuteCameraCommand", request)
                if not outcome.succeeded:
                    raise ClientError(
                        outcome.failure or "Camera operation did not succeed."
                    )
        elif action == "mcu":
            state = client.snapshot
            mcu_request = rpc.MicrocontrollerCommandRequest(
                command=client.operator_command(),
                expected_configuration_revision=state.configuration.revision,
                kind=cast(Any, options["kind"]),
                signal=cast(Any, options.get("signal", 0)),
            )
            outcome = await client.execute("ExecuteMicrocontrollerCommand", mcu_request)
            if not outcome.succeeded:
                raise ClientError(outcome.failure or "MCU operation did not succeed.")
        elif action == "spikeglx_connection":
            result = await client.stub.CheckSpikeGLXConnection(
                rpc.SpikeGLXConnectionQuery(client_id=self.principal.generation),
                metadata=self.principal.metadata(),
                timeout=6,
            )
            if result.error:
                raise ClientError(result.error)
            message = (
                f"{result.address}:{result.port} · {result.version} · "
                f"running={result.running} · saving={result.saving} · "
                f"run={result.run_name or 'unvalidated'} · data={result.data_directory}"
            )
            self.command_finished.emit(action, True, message)
            return
        elif action == "save_mcu_pins":
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
            update_request = rpc.UpdateConfigurationRequest(
                command=client.operator_command(),
                expected_revision=state.configuration.revision,
                proposed=proposed,
            )
            outcome = await client.execute("UpdateConfiguration", update_request)
            if not outcome.succeeded:
                raise ClientError(outcome.failure or "MCU pin settings were rejected.")
        elif action == "set_camera_enabled":
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
            outcome = await client.execute(
                "UpdateConfiguration",
                rpc.UpdateConfigurationRequest(
                    command=client.operator_command(),
                    expected_revision=state.configuration.revision,
                    proposed=proposed,
                ),
            )
            if not outcome.succeeded:
                raise ClientError(outcome.failure or "Camera enablement was rejected.")
        elif action == "save_camera_settings":
            state = client.snapshot
            proposed = type(state.configuration_values.current)()
            proposed.CopyFrom(state.configuration_values.current)
            _, selected, pulse = _assigned_camera(proposed, str(options["serial"]))
            clock = str(options["clock"])
            if clock == "External controller":
                source = str(options["source"]).strip()
                if not source:
                    raise ClientError(
                        "Select a PFS file with an explicit FrameStart line source."
                    )
                selected.device.frame_timing = camera_pb.FRAME_TIMING_EXTERNAL_TRIGGER
                selected.device.unaligned_free_running = False
                selected.device.settings.trigger_source = source
            elif clock == "Internal clock":
                selected.device.frame_timing = camera_pb.FRAME_TIMING_FREE_RUNNING
                selected.device.unaligned_free_running = True
                selected.device.settings.ClearField("trigger_source")
            else:
                raise ClientError("Select a camera trigger source before saving.")
            preset = str(options["preset"]).strip()
            if preset:
                selected.device.pfs_source_filename = preset
            else:
                selected.device.ClearField("pfs_source_filename")
            rate = str(options["rate"]).strip()
            if rate:
                try:
                    frequency = Decimal(rate)
                except InvalidOperation as exc:
                    raise ClientError("Camera trigger rate is not a number.") from exc
                if (
                    not frequency.is_finite()
                    or frequency <= 0
                    or frequency % Decimal("0.1")
                ):
                    raise ClientError(
                        "Camera trigger rate must use a positive 0.1 Hz grid."
                    )
                pulse.requested_frequency_hz = float(frequency)
            outcome = await client.execute(
                "UpdateConfiguration",
                rpc.UpdateConfigurationRequest(
                    command=client.operator_command(),
                    expected_revision=state.configuration.revision,
                    proposed=proposed,
                ),
            )
            if not outcome.succeeded:
                raise ClientError(outcome.failure or "Camera settings were rejected.")
        elif action == "viewer_state":
            attachment = options["attachment"]
            descriptor = attachment.buffer
            scope = descriptor.WhichOneof("scope")
            if scope == "preview":
                run_id = descriptor.preview.acquisition_run_id
            elif scope == "session":
                run_id = options["run_id"]
            else:
                raise ClientError("Viewer attachment has no run scope.")
            result = await client.stub.ReportPreviewConsumerState(
                rpc.PreviewConsumerReport(
                    client_id=self.principal.generation,
                    controller_generation=client.snapshot.controller_generation,
                    consumer=attachment.sync.target,
                    preview_run_id=run_id,
                    allocation_id=descriptor.allocation_id,
                    transfer_id=attachment.sync.transfer_id,
                    result=options["result"],
                ),
                metadata=self.principal.metadata(),
                timeout=client.rpc_timeout_s,
            )
            if result.result != 1:
                raise ClientError(
                    result.failure.message or "Viewer state was rejected."
                )
        else:
            methods = {
                "Setup": "Setup",
                "Cancel Setup": "CancelSetup",
                "Start": "StartSession",
                "Stop after trial": "StopAfterTrial",
                "Abort now": "AbortNow",
                "New session": "NewSession",
            }
            method = methods.get(action)
            if method is None:
                raise ValueError(f"Unknown operator action: {action}")
            outcome = await client.execute(method)
            if not outcome.succeeded:
                raise ClientError(outcome.failure or "Operation did not succeed.")
        self.command_finished.emit(action, True, "Completed")


def _assigned_camera(
    proposed: pb.ExperimentConfiguration, serial: str
) -> tuple[
    pb.BackendSettings, camera_pb.CameraSessionSettings, camera_pb.CameraPulseSettings
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
