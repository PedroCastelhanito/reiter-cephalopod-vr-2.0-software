"""Managed GUI observer and command transport (E03/E08)."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from cephvr.client.session import ClientError, HeadlessClient, loopback_channel
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.action_progress import requested_action
from cephvr.gui.managed_actions import ManagedActions
from cephvr.gui.managed_configuration_transport import submit_configuration
from cephvr.gui.tracking_frame_transport import fetch_tracking_diagnostic_frame
from cephvr.shared.auth import Principal


class ControllerBridge(QThread):
    """Keep gRPC and WatchState on one asyncio loop outside Qt's UI thread."""

    snapshot_received = pyqtSignal(int, str, bytes)
    connection_changed = pyqtSignal(bool, str, int, str)
    command_finished = pyqtSignal(str, bool, str)
    action_progress = pyqtSignal(str, str)
    command_admitted = pyqtSignal(str, str)
    operation_finished = pyqtSignal(str, str, str, str)
    spikeglx_inventory_received = pyqtSignal(int, str, bytes)
    tracking_frame_received = pyqtSignal(int, str, bytes)
    configuration_accepted = pyqtSignal(int, int)
    device_configuration_accepted = pyqtSignal(int, bytes)
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
        self._run_task: asyncio.Task[None] | None = None
        self._queue: (
            asyncio.PriorityQueue[tuple[int, int, int, str, str, dict[str, Any]]] | None
        ) = None
        self._stopping = False
        self._stop_lock = threading.Lock()
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
        }

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
        with self._stop_lock:
            if self._stopping:
                return
            self._stopping = True
            loop, task = self._loop, self._run_task
        if loop is not None and task is not None:
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass

    def run(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._run_task = asyncio.current_task()
        self._queue = asyncio.PriorityQueue(maxsize=self._MAX_PENDING + 1)
        attempt = 0
        try:
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
                except asyncio.CancelledError:
                    raise
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
        except asyncio.CancelledError:
            pass
        finally:
            self._connected = False
            self._loop = None
            self._run_task = None
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
        queued: asyncio.Task[tuple[int, int, int, str, str, dict[str, Any]]] | None = (
            None
        )
        try:
            while not self._stopping:
                queued = asyncio.create_task(self._queue.get())
                assert client._reader is not None
                done, _ = await asyncio.wait(
                    (queued, client._reader), return_when=asyncio.FIRST_COMPLETED
                )
                if client._reader in done:
                    queued.cancel()
                    await asyncio.gather(queued, return_exceptions=True)
                    queued = None
                    raise ClientError("Controller state stream closed.")
                _, _, epoch, generation, action, options = queued.result()
                queued = None
                if action == "quit":
                    return
                task = asyncio.create_task(
                    self._dispatch_guarded(client, action, options, epoch, generation)
                )
                self._dispatch_tasks.add(task)
                task.add_done_callback(self._dispatch_tasks.discard)
        finally:
            if queued is not None and not queued.done():
                queued.cancel()
                await asyncio.gather(queued, return_exceptions=True)
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
                "prepare_camera",
                "prepare_mcu_test",
                "prepare_mcu_connection",
                "save_mcu_pins",
                "add_mcu_output",
                "set_camera_enabled",
                "set_spikeglx_enabled",
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
        message = requested_action(action, options)
        if message:
            self.action_progress.emit(action, message)
        await ManagedActions(
            principal=self.principal,
            command_finished=self.command_finished.emit,
            action_progress=self.action_progress.emit,
            command_admitted=self.command_admitted.emit,
            operation_finished=self.operation_finished.emit,
            spikeglx_inventory_received=self.spikeglx_inventory_received.emit,
            device_configuration_accepted=self.device_configuration_accepted.emit,
            track_request=self._track_request,
            track_operation=self._track_operation,
            tracking_frame=self._tracking_diagnostic_frame,
            submit_configuration=self._submit_configuration,
            validate_configuration_snapshot=self._validate_configuration_snapshot,
        ).dispatch(client, action, options)

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
