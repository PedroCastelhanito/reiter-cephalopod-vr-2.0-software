"""Managed GUI observer and command transport (E03/E08)."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, cast

from PyQt6.QtCore import QThread, pyqtSignal

from cephvr.client.session import ClientError, HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.managed_configuration_transport import submit_configuration
from cephvr.gui.managed_device_commands import dispatch_device_action
from cephvr.gui.managed_display_operations import (
    close_display_calibration_request,
    open_display_calibration_request,
    spikeglx_inventory_request,
    spikeglx_inventory_update_request,
    validate_inventory_snapshot,
)
from cephvr.gui.tracking_frame_transport import fetch_tracking_diagnostic_frame
from cephvr.shared.auth import Principal
from cephvr.synchronization.v1 import spikeglx_pb2


class ControllerBridge(QThread):
    """Keep gRPC and WatchState on one asyncio loop outside Qt's UI thread."""

    snapshot_received = pyqtSignal(int, str, bytes)
    connection_changed = pyqtSignal(bool, str, int, str)
    command_finished = pyqtSignal(str, bool, str)
    command_admitted = pyqtSignal(str, str)
    operation_finished = pyqtSignal(str, str, str, str)
    attachment_received = pyqtSignal(int, bytes, bool)
    spikeglx_inventory_received = pyqtSignal(int, str, bytes)
    tracking_frame_received = pyqtSignal(int, str, bytes)
    configuration_accepted = pyqtSignal(int, int)
    _MAX_PENDING = 32
    _ORDINARY_PENDING = 24

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
        self._queue: (
            asyncio.PriorityQueue[tuple[int, int, int, str, str, dict[str, Any]]] | None
        ) = None
        self._stopping = False
        self._connected = False
        self._pending_lock = threading.Lock()
        self._pending_count = 0
        self._request_sequence = 0
        self._connection_epoch = 0
        self._controller_generation = ""
        self._dispatch_tasks: set[asyncio.Task[None]] = set()
        self._configuration_lock: asyncio.Lock | None = None

    @property
    def connection_epoch(self) -> int:
        return self._connection_epoch

    def request(self, action: str, **kwargs: Any) -> bool:
        loop, queue = self._loop, self._queue
        safety = self._is_safety_request(action, kwargs)
        if (
            loop is not None
            and queue is not None
            and (self._connected or action == "quit")
            and (not self._stopping or action == "quit")
        ):
            with self._pending_lock:
                limit = self._MAX_PENDING if safety else self._ORDINARY_PENDING
                if action != "quit" and self._pending_count >= limit:
                    return False
                if action != "quit":
                    self._pending_count += 1
                self._request_sequence += 1
                sequence = self._request_sequence
                epoch = self._connection_epoch
                generation = self._controller_generation
            loop.call_soon_threadsafe(
                self._queue_request,
                action,
                kwargs,
                sequence,
                safety,
                epoch,
                generation,
            )
            return True
        return False

    @staticmethod
    def _is_safety_request(action: str, options: dict[str, Any]) -> bool:
        return action in {
            "Abort now",
            "Cancel Setup",
            "Stop after trial",
            "Cancel Stop after trial",
            "respond_prompt",
            "release_control",
            "close_display_calibration",
            "close_tracking_diagnostic",
            "quit",
        } or (
            action == "viewer_state"
            and options.get("result")
            in {
                rpc.PREVIEW_CONSUMER_RESULT_RELEASED,
                rpc.PREVIEW_CONSUMER_RESULT_FAILED,
            }
        )

    def _queue_request(
        self,
        action: str,
        options: dict[str, Any],
        sequence: int,
        safety: bool,
        epoch: int,
        generation: str,
    ) -> None:
        if self._queue is None:
            if action != "quit":
                self._release_pending()
            return
        with self._pending_lock:
            stale_connection = (
                epoch != self._connection_epoch
                or generation != self._controller_generation
            )
        if stale_connection:
            if action != "quit":
                self._release_pending()
            self.command_finished.emit(
                action,
                False,
                "Command discarded because its controller connection changed; it was not replayed.",
            )
            return
        try:
            self._queue.put_nowait(
                (0 if safety else 1, sequence, epoch, generation, action, options)
            )
        except asyncio.QueueFull:
            if action != "quit":
                self._release_pending()
            self.command_finished.emit(
                action, False, "Controller command queue is full."
            )

    def _release_pending(self) -> None:
        with self._pending_lock:
            self._pending_count = max(0, self._pending_count - 1)

    def stop(self) -> None:
        self._stopping = True
        self.request("quit")

    def run(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.PriorityQueue(maxsize=self._MAX_PENDING + 1)
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
                    with self._pending_lock:
                        self._connection_epoch += 1
                        epoch = self._connection_epoch
                        self._controller_generation = ""

                    def receive_snapshot(
                        state: pb.Snapshot, connection_epoch: int = epoch
                    ) -> None:
                        self._snapshot_received(connection_epoch, state)

                    client = HeadlessClient(
                        channel,
                        self.principal,
                        on_snapshot=receive_snapshot,
                    )
                    async with client.observe():
                        with self._pending_lock:
                            self._controller_generation = (
                                client.snapshot.controller_generation
                            )
                            self._connected = True
                            generation = self._controller_generation
                        self.connection_changed.emit(True, "", epoch, generation)
                        attempt = 0
                        await self._commands(client)
            except Exception as exc:
                self._connected = False
                with self._pending_lock:
                    self._connection_epoch += 1
                    epoch = self._connection_epoch
                    self._controller_generation = ""
                while self._queue is not None and not self._queue.empty():
                    _, _, _, _, action, _ = self._queue.get_nowait()
                    if action != "quit":
                        self._release_pending()
                        self.command_finished.emit(
                            action,
                            False,
                            "Controller connection lost; command discarded.",
                        )
                self.connection_changed.emit(False, str(exc), epoch, "")
                attempt += 1
        self._connected = False
        self._loop = None
        self._queue = None

    def _snapshot_received(self, epoch: int, state: pb.Snapshot) -> None:
        with self._pending_lock:
            if epoch != self._connection_epoch:
                return
            self._controller_generation = state.controller_generation
        self.snapshot_received.emit(
            epoch, state.controller_generation, state.SerializeToString()
        )

    async def _commands(self, client: HeadlessClient) -> None:
        assert self._queue is not None
        self._configuration_lock = asyncio.Lock()
        try:
            while not self._stopping:
                queued = asyncio.create_task(self._queue.get())
                assert client._reader is not None
                done, _ = await asyncio.wait(
                    (queued, client._reader), return_when=asyncio.FIRST_COMPLETED
                )
                if client._reader in done:
                    queued.cancel()
                    raise ClientError("Controller state stream closed.")
                _, _, epoch, generation, action, options = queued.result()
                if action == "quit":
                    return
                task = asyncio.create_task(
                    self._dispatch_guarded(client, action, options, epoch, generation)
                )
                self._dispatch_tasks.add(task)
                task.add_done_callback(self._dispatch_tasks.discard)
        finally:
            tasks = tuple(self._dispatch_tasks)
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            while not self._queue.empty():
                _, _, _, _, action, _ = self._queue.get_nowait()
                if action != "quit":
                    self._release_pending()
            self._configuration_lock = None

    async def _dispatch_guarded(
        self,
        client: HeadlessClient,
        action: str,
        options: dict[str, Any],
        epoch: int,
        generation: str,
    ) -> None:
        try:
            with self._pending_lock:
                current = (
                    epoch == self._connection_epoch
                    and generation == self._controller_generation
                    and generation == client.snapshot.controller_generation
                )
            if not current:
                self.command_finished.emit(
                    action,
                    False,
                    "Command discarded because its controller connection changed; it was not replayed.",
                )
                return
            options["dispatch_identity"] = (epoch, generation)
            if action in {
                "save_camera_settings",
                "save_mcu_pins",
                "set_camera_enabled",
                "assign_camera_role",
                "submit_configuration",
                "spikeglx_inventory_update",
                "get_spikeglx_inventory",
                "Setup",
            }:
                lock = self._configuration_lock
                if lock is None:
                    raise ClientError("Configuration dispatch is unavailable.")
                async with lock:
                    await self._dispatch(client, action, options)
            else:
                await self._dispatch(client, action, options)
        except asyncio.CancelledError:
            self.command_finished.emit(
                action,
                False,
                "Command outcome is unconfirmed after disconnect; it was not resent.",
            )
            raise
        except (ClientError, ValueError, TimeoutError) as exc:
            if action == "respond_prompt":
                self.operation_finished.emit(action, "", "rejected", str(exc))
            else:
                self.command_finished.emit(action, False, str(exc))
        except Exception as exc:
            self.command_finished.emit(action, False, f"Transport error: {exc}")
        finally:
            self._release_pending()

    async def _track_operation(
        self, client: HeadlessClient, action: str, method: str
    ) -> None:
        await self._track_request(client, action, method, client.operator_command())

    async def _tracking_diagnostic_frame(
        self, client: HeadlessClient, options: dict[str, Any]
    ) -> None:
        epoch, generation, frame_bytes = await fetch_tracking_diagnostic_frame(
            client,
            self.principal,
            options,
            connection_epoch=self._connection_epoch,
            max_message_bytes=self.max_message_bytes,
        )
        self.tracking_frame_received.emit(
            epoch,
            generation,
            frame_bytes,
        )

    async def _track_request(
        self, client: HeadlessClient, action: str, method: str, request: Any
    ) -> None:
        command_id = (
            request.operator.command_id
            if hasattr(request, "operator")
            else request.command.operator.command_id
        )
        try:
            outcome = await client.execute(method, request, wait=False)
        except asyncio.CancelledError:
            self.operation_finished.emit(
                action,
                command_id,
                "unconfirmed",
                "Connection ended during admission; this command ID will not be replayed.",
            )
            raise
        except ClientError as exc:
            status = "unconfirmed" if exc.admission_uncertain else "rejected"
            self.operation_finished.emit(action, command_id, status, str(exc))
            return
        command_id = outcome.command_id
        self.command_admitted.emit(action, command_id)
        try:
            result = await client.wait_result(command_id)
        except asyncio.CancelledError:
            self.operation_finished.emit(
                action,
                command_id,
                "unconfirmed",
                "Connection ended before completion evidence; this command ID will not be replayed.",
            )
            raise
        except ClientError as exc:
            self.operation_finished.emit(action, command_id, "unconfirmed", str(exc))
            return
        if result.needs_input:
            self.operation_finished.emit(
                action, command_id, "needs_input", "Operator input is required."
            )
        elif not result.complete or result.succeeded is None:
            self.operation_finished.emit(
                action, command_id, "unconfirmed", "Completion evidence is unavailable."
            )
        elif result.succeeded:
            self.operation_finished.emit(action, command_id, "completed", "Completed.")
        else:
            self.operation_finished.emit(
                action,
                command_id,
                "failed",
                result.failure or "Controller reported operation failure.",
            )

    async def _dispatch(
        self, client: HeadlessClient, action: str, options: dict[str, Any]
    ) -> None:
        device_result = await dispatch_device_action(
            client, action, options, self.principal, self.attachment_received.emit
        )
        if device_result is not None:
            success, message = device_result
            self.command_finished.emit(action, success, message)
            return
        if action == "take_control":
            await client.claim_control(takeover=bool(options.get("takeover")))
        elif action == "get_spikeglx_inventory":
            inventory_request = spikeglx_inventory_request(client)
            expected_revision = int(options.get("expected_revision", -1))
            if inventory_request.expected_configuration_revision != expected_revision:
                raise ClientError(
                    "SpikeGLX inventory request is for an older configuration."
                )
            result = await client.stub.GetSpikeGLXInventory(
                inventory_request,
                metadata=client.principal.metadata(),
                timeout=client.rpc_timeout_s,
            )
            validate_inventory_snapshot(result, expected_revision)
            identity = options.get("dispatch_identity")
            if not isinstance(identity, tuple) or len(identity) != 2:
                raise ClientError("Inventory response lost its connection identity.")
            self.spikeglx_inventory_received.emit(
                int(identity[0]), str(identity[1]), result.SerializeToString()
            )
        elif action == "spikeglx_inventory_update":
            update_request = spikeglx_inventory_update_request(
                client,
                expected_revision=int(options["expected_revision"]),
                expected_file_sha256=str(options["expected_file_sha256"]),
                pulse_channels=tuple(
                    spikeglx_pb2.PulseChannel.FromString(encoded)
                    for encoded in options["pulse_channels"]
                ),
            )
            await self._track_request(
                client, action, "UpdateSpikeGLXInventory", update_request
            )
        elif action == "open_display_calibration":
            open_request = open_display_calibration_request(
                client,
                arena_path=str(options["arena_path"]),
                expected_revision=int(options["expected_revision"]),
                expected_profile_sha256=str(options["expected_profile_sha256"]),
                expected_arena_sha256=str(options["expected_arena_sha256"]),
            )
            await self._track_request(
                client, action, "OpenDisplayCalibration", open_request
            )
        elif action == "close_display_calibration":
            close_request = close_display_calibration_request(
                client,
                expected_revision=int(options["expected_revision"]),
                diagnostic_id=str(options["diagnostic_id"]),
            )
            await self._track_request(
                client, action, "CloseDisplayCalibration", close_request
            )
        elif action == "begin_tracking_diagnostic":
            request: Any = rpc.BeginTrackingDiagnosticRequest(
                command=client.operator_command(),
                expected_configuration_revision=int(options["expected_revision"]),
                preview_run_id=str(options["preview_run_id"]),
                selected_stages=tuple(
                    cast(Any, int(value)) for value in options["selected_stages"]
                ),
                diagnostic_settings=pb.TrackingSettings.FromString(
                    bytes(options["diagnostic_settings"])
                ),
            )
            await self._track_request(
                client, action, "BeginTrackingDiagnostic", request
            )
        elif action == "close_tracking_diagnostic":
            request = rpc.CloseTrackingDiagnosticRequest(
                command=client.operator_command(),
                expected_configuration_revision=int(options["expected_revision"]),
                diagnostic_id=str(options["diagnostic_id"]),
                preview_run_id=str(options["preview_run_id"]),
            )
            await self._track_request(
                client, action, "CloseTrackingDiagnostic", request
            )
        elif action == "tracking_diagnostic_frame":
            await self._tracking_diagnostic_frame(client, options)
        elif action == "release_control":
            if client.snapshot.control.holder_client_id == self.principal.generation:
                await self._track_operation(client, action, "ReleaseControl")
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
        elif action == "submit_configuration":
            completed = await self._submit_configuration(client, options)
            if not completed:
                return
            after = options.get("after_action")
            if after in {"Setup", "New session"}:
                if after == "Setup":
                    self._validate_configuration_snapshot(
                        client,
                        int(options.get("accepted_revision", -1)),
                        bytes(options.get("proposal", b"")),
                    )
                await self._track_operation(
                    client, str(after), "Setup" if after == "Setup" else "NewSession"
                )
            elif after == "save_configuration_history":
                try:
                    holder = client.snapshot.control.holder_client_id
                    if holder != self.principal.generation:
                        raise ClientError(
                            "Control changed before configuration history could be saved."
                        )
                    history = await client.execute("SaveConfigurationHistory")
                    if not history.succeeded:
                        raise ClientError(
                            history.failure or "Configuration history was not saved."
                        )
                except ClientError as exc:
                    self.command_finished.emit(
                        "save_configuration_history", False, str(exc)
                    )
                else:
                    self.command_finished.emit(
                        "save_configuration_history", True, "Configuration saved."
                    )
            return
        elif action == "respond_prompt":
            stamped = pb.Prompt.FromString(options["prompt"])
            prompt = next(
                (
                    item
                    for item in client.snapshot.prompts
                    if item.prompt_id == stamped.prompt_id
                ),
                None,
            )
            if (
                prompt is None
                or prompt.SerializeToString(deterministic=True)
                != stamped.SerializeToString(deterministic=True)
                or options["choice"] not in stamped.permitted_choices
            ):
                raise ClientError(
                    "Prompt changed after display; review the current prompt."
                )
            response = rpc.PromptResponse(
                command=client.operator_command(),
                prompt_id=stamped.prompt_id,
                setup=stamped.setup,
                setup_operation=stamped.operation,
                choice=options["choice"],
            )
            if stamped.HasField("runtime_incident"):
                response.expected_incident_revision = stamped.runtime_incident.revision
            command_id = response.command.operator.command_id
            try:
                admission = await client._admit("RespondToPrompt", response)
            except asyncio.CancelledError:
                self.operation_finished.emit(
                    action,
                    command_id,
                    "unconfirmed",
                    "Connection ended during prompt admission; no response was replayed.",
                )
                raise
            except ClientError as exc:
                self.operation_finished.emit(
                    action,
                    exc.command_id or command_id,
                    "unconfirmed" if exc.admission_uncertain else "rejected",
                    str(exc),
                )
                return
            self.command_admitted.emit(action, admission.command_id)
            try:
                result = await client.wait_result(admission.command_id)
            except asyncio.CancelledError:
                self.operation_finished.emit(
                    action,
                    admission.command_id,
                    "unconfirmed",
                    "Connection ended before prompt completion evidence; no response was replayed.",
                )
                raise
            except ClientError as exc:
                self.operation_finished.emit(
                    action,
                    admission.command_id,
                    "unconfirmed",
                    str(exc),
                )
                return
            if result.needs_input:
                self.operation_finished.emit(
                    action,
                    admission.command_id,
                    "needs_input",
                    "The controller still requires operator input.",
                )
            elif result.complete and result.succeeded is True:
                self.operation_finished.emit(
                    action, admission.command_id, "completed", "Choice accepted."
                )
            elif result.complete and result.succeeded is False:
                self.operation_finished.emit(
                    action,
                    admission.command_id,
                    "failed",
                    result.failure or "The controller rejected the choice.",
                )
            else:
                self.operation_finished.emit(
                    action,
                    admission.command_id,
                    "unconfirmed",
                    "Choice completion is unconfirmed.",
                )
            return
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
            if action == "Setup":
                self._validate_configuration_snapshot(
                    client,
                    int(options.get("expected_revision", -1)),
                    bytes(options.get("expected_configuration", b"")),
                )
            await self._track_operation(client, action, method)
            return
        self.command_finished.emit(action, True, "Completed")

    async def _submit_configuration(
        self, client: HeadlessClient, options: dict[str, Any]
    ) -> bool:
        def accepted(revision: int) -> None:
            options["accepted_revision"] = revision
            self.configuration_accepted.emit(
                revision, int(options.get("edit_serial", -1))
            )

        return await submit_configuration(
            client,
            options,
            self._controller_generation,
            admitted=lambda command_id: self.command_admitted.emit(
                "submit_configuration", command_id
            ),
            accepted=accepted,
            finished=self.operation_finished.emit,
        )

    def _validate_configuration_snapshot(
        self, client: HeadlessClient, revision: int, payload: bytes
    ) -> None:
        snapshot = client.snapshot
        if (
            snapshot.controller_generation != self._controller_generation
            or not snapshot.HasField("configuration_values")
            or snapshot.configuration.revision != revision
            or snapshot.configuration_values.revision != revision
            or snapshot.configuration_values.current.SerializeToString(
                deterministic=True
            )
            != payload
        ):
            raise ClientError(
                "Setup was not sent because its captured configuration version changed."
            )
