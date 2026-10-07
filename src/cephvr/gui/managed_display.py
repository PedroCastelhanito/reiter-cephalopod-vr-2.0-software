"""Focused calibration and saved SpikeGLX inventory operations for managed GUI."""

from __future__ import annotations

from collections.abc import Callable

from cephvr.client.session import ClientError
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.managed_display_operations import (
    capture_display_calibration_intent,
    required_inventory_roles,
    validate_inventory_snapshot,
)
from cephvr.gui.projectors import ProjectorsPanel
from cephvr.gui.spikeglx import SpikeGLXPanel
from cephvr.visual_stimulus.v1 import runtime_pb2 as visual_stimulus_pb


class ManagedDisplayOperations:
    """Own device-panel RPC actions with explicit snapshot and identity access."""

    def __init__(
        self,
        projectors: ProjectorsPanel,
        spikeglx: SpikeGLXPanel,
        *,
        snapshot: Callable[[], pb.Snapshot | None],
        connection_identity: Callable[[], tuple[int, str] | None],
        send: Callable[..., bool],
    ) -> None:
        self.projectors = projectors
        self.spikeglx = spikeglx
        self.snapshot = snapshot
        self.connection_identity = connection_identity
        self.send = send

    def submit_inventory(self, channels: object) -> None:
        state = self.snapshot()
        if state is None or not isinstance(channels, tuple):
            return
        try:
            payloads = tuple(
                channel.SerializeToString(deterministic=True) for channel in channels
            )
        except (AttributeError, TypeError):
            self.spikeglx.console.appendPlainText(
                "Pulse mapping was not sent: invalid channel draft."
            )
            return
        if not self.send(
            "spikeglx_inventory_update",
            expected_revision=state.configuration.revision,
            expected_file_sha256=self.spikeglx.inventory_file_sha256,
            pulse_channels=payloads,
        ):
            self.spikeglx.console.appendPlainText(
                "Pulse mapping was not sent: controller command queue is unavailable."
            )

    def open_calibration(self, arena_path: str) -> None:
        state = self.snapshot()
        if state is None:
            return
        try:
            intent = capture_display_calibration_intent(state, arena_path=arena_path)
        except (OSError, ValueError) as error:
            self.projectors.console.appendPlainText(
                f"Calibration was not sent: {error}"
            )
            return
        if not self.send("open_display_calibration", **intent):
            self.projectors.console.appendPlainText(
                "Calibration was not sent: controller command queue is unavailable."
            )

    def close_calibration(self) -> None:
        state = self.snapshot()
        if (
            state is None
            or not state.HasField("visual_stimulus_display")
            or not state.visual_stimulus_display.HasField("calibration")
        ):
            return
        evidence = state.visual_stimulus_display.calibration
        if not self.send(
            "close_display_calibration",
            expected_revision=state.configuration.revision,
            diagnostic_id=evidence.diagnostic_id,
        ):
            self.projectors.console.appendPlainText(
                "Calibration close was not sent: controller command queue is unavailable."
            )

    def install_inventory(self, epoch: int, generation: str, raw: bytes) -> None:
        try:
            inventory = rpc.SpikeGLXInventorySnapshot.FromString(raw)
            state = self.snapshot()
            if state is None or self.connection_identity() != (epoch, generation):
                return
            validate_inventory_snapshot(inventory, state.configuration.revision)
            self.spikeglx.install_inventory(
                tuple(inventory.pulse_channels),
                inventory.file_sha256,
                required_roles=required_inventory_roles(
                    state.configuration_values.current
                ),
                backend_enabled=inventory.backend_enabled,
                address=inventory.address,
                command_port=inventory.command_port,
            )
        except (ClientError, ValueError, TypeError) as error:
            self.spikeglx.console.appendPlainText(
                f"Saved pulse mapping could not be installed: {error}"
            )

    def install_calibration_state(
        self, state: pb.Snapshot, *, launch_eligible: bool
    ) -> None:
        if not state.HasField("visual_stimulus_display"):
            self.projectors.set_calibration_presentation_state(
                active=False, available=launch_eligible
            )
            return
        display = state.visual_stimulus_display
        evidence = display.calibration if display.HasField("calibration") else None
        if evidence is None:
            self.projectors.set_calibration_presentation_state(
                active=False, available=launch_eligible
            )
            return
        expected = (
            evidence.controller_generation == state.controller_generation
            and evidence.configuration_revision == state.configuration.revision
            and bool(evidence.diagnostic_id)
        )
        active = (
            expected
            and evidence.state == visual_stimulus_pb.DISPLAY_CALIBRATION_STATE_ACTIVE
        )
        pending = expected and evidence.state in (
            visual_stimulus_pb.DISPLAY_CALIBRATION_STATE_PREPARING,
            visual_stimulus_pb.DISPLAY_CALIBRATION_STATE_CLOSING,
        )
        available = expected and evidence.state in (
            visual_stimulus_pb.DISPLAY_CALIBRATION_STATE_ACTIVE,
            visual_stimulus_pb.DISPLAY_CALIBRATION_STATE_IDLE,
        )
        self.projectors.set_calibration_presentation_state(
            active=active, available=available, pending=pending
        )
