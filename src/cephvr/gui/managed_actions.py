"""Managed feature requests and results; scheduling stays in ControllerBridge."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from cephvr.client.session import ClientError, HeadlessClient
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.action_cancellation import ActionCancelled, Cancellation, checkpoint
from cephvr.gui.camera_action_submission import prepare_camera
from cephvr.gui.cancel_cleanup import cleanup_cancelled_device
from cephvr.gui.managed_device_commands import dispatch_device_action
from cephvr.gui.managed_display_operations import (
    close_display_calibration_request,
    open_display_calibration_request,
    spikeglx_inventory_request,
    spikeglx_inventory_update_request,
    update_display_calibration_request,
    validate_inventory_snapshot,
)
from cephvr.gui.mcu_action_submission import prepare_mcu_connection, prepare_mcu_test
from cephvr.shared.auth import Principal
from cephvr.synchronization.v1 import spikeglx_pb2


@dataclass(frozen=True)
class ManagedActions:
    """Feature operations with explicit callbacks and no transport-owner state."""

    principal: Principal
    command_finished: Callable[[str, bool, str], None]
    command_admitted: Callable[[str, str], None]
    operation_finished: Callable[[str, str, str, str], None]
    spikeglx_inventory_received: Callable[[int, str, bytes], None]
    device_configuration_accepted: Callable[[int, bytes], None]
    track_request: Callable[[HeadlessClient, str, str, Any], Awaitable[None]]
    track_operation: Callable[[HeadlessClient, str, str], Awaitable[None]]
    tracking_frame: Callable[[HeadlessClient, dict[str, Any]], Awaitable[None]]
    submit_configuration: Callable[[HeadlessClient, dict[str, Any]], Awaitable[bool]]
    validate_configuration_snapshot: Callable[[HeadlessClient, int, bytes], None]

    async def dispatch(
        self, client: HeadlessClient, action: str, options: dict[str, Any]
    ) -> None:
        if await self._device(client, action, options):
            return
        if action in {"get_spikeglx_inventory", "spikeglx_inventory_update"}:
            await self._inventory(client, action, options)
            return
        if action in {
            "open_display_calibration",
            "update_display_calibration",
            "close_display_calibration",
        }:
            await self._display(client, action, options)
            return
        if action in {"begin_tracking_diagnostic", "close_tracking_diagnostic"}:
            await self._tracking(client, action, options)
            return
        if action == "take_control":
            await client.claim_control(takeover=bool(options.get("takeover")))
        elif action == "tracking_diagnostic_frame":
            await self.tracking_frame(client, options)
        elif action == "release_control":
            if client.snapshot.control.holder_client_id == self.principal.generation:
                await self.track_operation(client, action, "ReleaseControl")
                return
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
            await self._configuration(client, action, options)
            return
        elif action == "respond_prompt":
            await self._prompt(client, action, options)
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
                self.validate_configuration_snapshot(
                    client,
                    int(options.get("expected_revision", -1)),
                    bytes(options.get("expected_configuration", b"")),
                )
            await self.track_operation(client, action, method)
            return
        self.command_finished(action, True, "Completed")

    async def _device(
        self, client: HeadlessClient, action: str, options: dict[str, Any]
    ) -> bool:
        token = options.get("cancellation")
        if not isinstance(token, Cancellation):
            result = await self._device_result(client, action, options)
        else:
            if token.requested.is_set():
                self.command_finished(action, False, "Cancelled before dispatch")
                return True
            before = pb.Snapshot.FromString(client.snapshot.SerializeToString())
            try:
                result = await self._device_result(client, action, options)
                checkpoint(options)
            except ActionCancelled:
                await cleanup_cancelled_device(client, action, options, before)
                self.command_finished(
                    action,
                    False,
                    "Cancelled; cleanup confirmed. Applied settings are retained.",
                )
                return True
        if result is None:
            return False
        self.command_finished(action, *result)
        return True

    async def _device_result(
        self, client: HeadlessClient, action: str, options: dict[str, Any]
    ) -> tuple[bool, str] | None:
        if action in {"prepare_mcu_test", "prepare_mcu_connection"}:
            base_revision = int(options["base_revision"])
            if action == "prepare_mcu_connection":
                await prepare_mcu_connection(client, options)
            else:
                await prepare_mcu_test(client, options)
            confirmed_revision = client.snapshot.configuration.revision
            self.device_configuration_accepted(
                base_revision, client.snapshot.SerializeToString()
            )
            checkpoint(options)
            mcu_result = await dispatch_device_action(
                client,
                "mcu",
                dict(options, confirmed_revision=confirmed_revision),
                self.principal,
            )
            assert mcu_result is not None
            return mcu_result
        if action == "prepare_camera":
            base_revision = int(options["base_revision"])

            def camera_accepted(state: pb.Snapshot) -> None:
                nonlocal base_revision
                if (
                    state.controller_generation == options["generation"]
                    and state.configuration.revision != base_revision
                ):
                    self.device_configuration_accepted(
                        base_revision, state.SerializeToString()
                    )
                    base_revision = state.configuration.revision

            await prepare_camera(client, options, camera_accepted)
            checkpoint(options)
            try:
                camera_result = await dispatch_device_action(
                    client,
                    "camera",
                    dict(options, role=options["camera_role"]),
                    self.principal,
                )
            finally:
                camera_accepted(client.snapshot)
            assert camera_result is not None
            return camera_result
        base_revision = client.snapshot.configuration.revision
        device_result = await dispatch_device_action(
            client, action, options, self.principal
        )
        if device_result is not None:
            success, message = device_result
            if (
                action == "set_spikeglx_enabled"
                and success
                and (client.snapshot.configuration.revision != base_revision)
            ):
                self.device_configuration_accepted(
                    base_revision, client.snapshot.SerializeToString()
                )
            return success, message
        return None

    async def _inventory(
        self, client: HeadlessClient, action: str, options: dict[str, Any]
    ) -> None:
        if action == "get_spikeglx_inventory":
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
            self.spikeglx_inventory_received(
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
            await self.track_request(
                client, action, "UpdateSpikeGLXInventory", update_request
            )
            return
        self.command_finished(action, True, "Completed")

    async def _display(
        self, client: HeadlessClient, action: str, options: dict[str, Any]
    ) -> None:
        if action == "open_display_calibration":
            open_request = open_display_calibration_request(
                client,
                arena_path=str(options["arena_path"]),
                expected_revision=int(options["expected_revision"]),
                expected_profile_sha256=str(options["expected_profile_sha256"]),
                expected_arena_sha256=str(options["expected_arena_sha256"]),
            )
            await self.track_request(
                client, action, "OpenDisplayCalibration", open_request
            )
            return
        elif action == "update_display_calibration":
            calibration_update_request = update_display_calibration_request(
                client,
                expected_revision=int(options["expected_revision"]),
                diagnostic_id=str(options["diagnostic_id"]),
                adjustment_sequence=int(options["adjustment_sequence"]),
                adjustments=tuple(options.get("adjustments", ())),
                placement_json=str(options.get("placement_json", "")),
            )
            await self.track_request(
                client, action, "UpdateDisplayCalibration", calibration_update_request
            )
            return
        elif action == "close_display_calibration":
            close_request = close_display_calibration_request(
                client,
                expected_revision=int(options["expected_revision"]),
                diagnostic_id=str(options["diagnostic_id"]),
            )
            await self.track_request(
                client, action, "CloseDisplayCalibration", close_request
            )
            return

    async def _tracking(
        self, client: HeadlessClient, action: str, options: dict[str, Any]
    ) -> None:
        if action == "begin_tracking_diagnostic":
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
            await self.track_request(client, action, "BeginTrackingDiagnostic", request)
            return
        elif action == "close_tracking_diagnostic":
            request = rpc.CloseTrackingDiagnosticRequest(
                command=client.operator_command(),
                expected_configuration_revision=int(options["expected_revision"]),
                diagnostic_id=str(options["diagnostic_id"]),
                preview_run_id=str(options["preview_run_id"]),
            )
            await self.track_request(client, action, "CloseTrackingDiagnostic", request)
            return

    async def _configuration(
        self, client: HeadlessClient, action: str, options: dict[str, Any]
    ) -> None:
        completed = await self.submit_configuration(client, options)
        if not completed:
            return
        after = options.get("after_action")
        if after in {"Setup", "New session"}:
            if after == "Setup":
                self.validate_configuration_snapshot(
                    client,
                    int(options.get("accepted_revision", -1)),
                    bytes(options.get("proposal", b"")),
                )
            await self.track_operation(
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
                self.command_finished("save_configuration_history", False, str(exc))
            else:
                self.command_finished(
                    "save_configuration_history", True, "Configuration saved."
                )
        return

    async def _prompt(
        self, client: HeadlessClient, action: str, options: dict[str, Any]
    ) -> None:
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
            self.operation_finished(
                action,
                command_id,
                "unconfirmed",
                "Connection ended during prompt admission; no response was replayed.",
            )
            raise
        except ClientError as exc:
            self.operation_finished(
                action,
                exc.command_id or command_id,
                "unconfirmed" if exc.admission_uncertain else "rejected",
                str(exc),
            )
            return
        self.command_admitted(action, admission.command_id)
        try:
            result = await client.wait_result(admission.command_id)
        except asyncio.CancelledError:
            self.operation_finished(
                action,
                admission.command_id,
                "unconfirmed",
                "Connection ended before prompt completion evidence; no response was replayed.",
            )
            raise
        except ClientError as exc:
            self.operation_finished(
                action, admission.command_id, "unconfirmed", str(exc)
            )
            return
        if result.needs_input:
            self.operation_finished(
                action,
                admission.command_id,
                "needs_input",
                "The controller still requires operator input.",
            )
        elif result.complete and result.succeeded is True:
            self.operation_finished(
                action, admission.command_id, "completed", "Choice accepted."
            )
        elif result.complete and result.succeeded is False:
            self.operation_finished(
                action,
                admission.command_id,
                "failed",
                result.failure or "The controller rejected the choice.",
            )
        else:
            self.operation_finished(
                action,
                admission.command_id,
                "unconfirmed",
                "Choice completion is unconfirmed.",
            )
        return
