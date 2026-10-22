"""Managed Windows GUI entry point and controller-backed camera controls."""

from __future__ import annotations

import argparse
import secrets
import sys
import tomllib
from dataclasses import replace
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMessageBox

from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.action_progress import ActionProgress
from cephvr.gui.controller_bridge import ControllerBridge
from cephvr.gui.gui_history import GuiHistory, history_path
from cephvr.gui.managed_cameras import ManagedCameras
from cephvr.gui.managed_close import save_failure_choice
from cephvr.gui.managed_configuration import ConfigurationPages, ManagedConfiguration
from cephvr.gui.managed_configuration_transport import configuration_update_plan
from cephvr.gui.managed_display import ManagedDisplayOperations
from cephvr.gui.managed_mcu import ManagedMcu
from cephvr.gui.managed_preview_viewers import ManagedPreviewViewers
from cephvr.gui.managed_prompts import ManagedPrompts
from cephvr.gui.managed_status import (
    action_label,
    dashboard_view,
    has_retained_history,
    retained_ack_required_for,
)
from cephvr.gui.managed_stimulus_preview import (
    ManagedStimulusPreview,
    stimulus_preview_view,
)
from cephvr.gui.managed_tracking_diagnostics import ManagedTrackingDiagnostics
from cephvr.gui.managed_window import ManagedDashboardWindow
from cephvr.gui.preview_placement import preview_window_placement
from cephvr.gui.projector_prerequisites import NO_PROJECTORS_MESSAGE
from cephvr.gui.splash import StartupSplash
from cephvr.gui.theme import apply_theme
from cephvr.gui.view import DashboardView
from cephvr.platform.windows.bootstrap import read_bootstrap
from cephvr.platform.windows.guard import SingleInstanceGuard
from cephvr.shared.credentials import CredentialStore, default_runtime_root


class ManagedGui(QObject):
    """Project authoritative state and forward explicit user intents."""

    def __init__(
        self,
        window: ManagedDashboardWindow,
        bridge: ControllerBridge,
        *,
        gui_history_path: Path | None = None,
    ) -> None:
        super().__init__(window)
        self.window = window
        self.bridge = bridge
        self.connected_once = False
        self._retained_ack_required = False
        self._connection_epoch = 0
        self._connection_identity: tuple[int, str] | None = None
        self._retained_ack_identity: tuple[int, str] | None = None
        self._acknowledged_identity: tuple[int, str] | None = None
        self._awaiting_reconnect_review = False
        self.control_ready = False
        self.auto_control_attempted = False
        self.close_pending = False
        self.history = GuiHistory(window.snapshots, gui_history_path or history_path())
        self.state: pb.Snapshot | None = None
        self.action_progress = ActionProgress(self.log_action, self.update_action)
        self._inventory_identity: tuple[str, int] | None = None
        self.display_operations = ManagedDisplayOperations(
            window.devices.projectors,
            window.devices.spikeglx,
            snapshot=lambda: self.state,
            connection_identity=lambda: self._connection_identity,
            send=bridge.request,
        )
        menu_bar = window.menuBar()
        assert menu_bar is not None
        menu = menu_bar.addMenu("Control")
        assert menu is not None
        self.take = QAction("Take control", self)
        self.takeover = QAction("Take over control…", self)
        self.release = QAction("Release control", self)
        self.review_retained = QAction("Review controller history…", self)
        self.review_prompt = QAction("Review pending prompt…", self)
        self.reload_configuration = QAction("Reload controller configuration…", self)
        menu.addActions(
            (
                self.take,
                self.takeover,
                self.release,
                self.review_retained,
                self.review_prompt,
                self.reload_configuration,
            )
        )
        self.take.triggered.connect(lambda: bridge.request("take_control"))
        self.takeover.triggered.connect(self.confirm_takeover)
        self.release.triggered.connect(lambda: bridge.request("release_control"))
        self.take.setEnabled(False)
        self.takeover.setEnabled(False)
        self.release.setEnabled(False)
        self.review_retained.setEnabled(False)
        self.review_retained.triggered.connect(self.review_retained_state)
        self.review_prompt.setEnabled(False)
        self.review_prompt.triggered.connect(self.review_pending_prompts)
        self.reload_configuration.setEnabled(False)
        self.reload_configuration.triggered.connect(
            self.reload_controller_configuration
        )
        self.prompts = ManagedPrompts(
            window,
            queue_response=self.queue_prompt_response,
            acknowledged=self.retained_state_acknowledged,
            log=window.dashboard.log_console.appendPlainText,
        )
        self.configuration = ManagedConfiguration(
            ConfigurationPages(
                window.dashboard,
                window.protocol,
                window.recordings,
                window.devices.cameras,
                window.devices.projectors,
                window.tracking,
                window.devices.microcontroller,
            )
        )
        cameras = window.devices.cameras
        cameras.managed = True
        cameras.real_devices = True
        cameras.refresh_inventory()
        self.preview_viewers = ManagedPreviewViewers(
            lambda: self.state,
            cameras,
            lambda role, kind, **options: self.cameras.queue(
                "camera", role=role, kind=kind, **options
            ),
            lambda key: preview_window_placement(window, key).SerializeToString(),
        )
        self.stimulus_preview = ManagedStimulusPreview(
            window,
            lambda: self.state,
            bridge.request,
            lambda: preview_window_placement(window, "stimulus").SerializeToString(),
            lambda: self.control_ready and window.dashboard.view.has_control,
        )
        window.preview_slot.snap_requested.connect(
            lambda key: self.stimulus_preview.request(key, True, snap=True)
        )
        bridge.command_finished.connect(self.stimulus_preview_finished)
        bridge.operation_finished.connect(self.stimulus_preview_finished)
        window.preview_slot.snap_requested.connect(self.preview_viewers.snap)
        self.cameras = ManagedCameras(
            cameras,
            bridge,
            self.preview_viewers.viewer_state,
            lambda key: preview_window_placement(window, key).SerializeToString(),
            self.camera_submission_options,
        )
        cameras.inventory_refreshed.connect(self.refresh_camera_state)
        cameras.preview_requested.connect(self.preview_viewers.preview_visibility)
        mcu = window.devices.microcontroller
        mcu.managed = True
        mcu.scan_ports()
        window.devices.projectors.discover_displays()
        window.devices.projectors.brightness.requested.connect(
            self.adjust_projector_brightness
        )
        self.mcu = ManagedMcu(mcu, bridge, lambda: self.state)
        self.tracking_diagnostics = ManagedTrackingDiagnostics(
            window,
            bridge,
            window.tracking,
            lambda: self.state,
            lambda: (
                self.state.configuration_values.current.asset_root
                if self.state is not None
                and self.state.HasField("configuration_values")
                and self.state.configuration_values.current.HasField("asset_root")
                else ""
            ),
            lambda: (
                self.control_ready
                and not self._retained_ack_required
                and self.state is not None
                and self.state.control.holder_client_id
                == self.bridge.principal.generation
            ),
        )
        window.devices.spikeglx.connection_requested.connect(
            lambda: window.devices.spikeglx.start_connection_check(bridge.request)
        )
        window.devices.spikeglx.pairing_requested.connect(
            self.display_operations.submit_pairing
        )
        window.devices.spikeglx.inventory_update_requested.connect(
            self.display_operations.submit_inventory
        )
        window.devices.projectors.calibration_launch_requested.connect(
            self.display_operations.open_calibration
        )
        window.devices.projectors.calibration_close_requested.connect(
            self.display_operations.close_calibration
        )
        window.dashboard.preview_requested.connect(
            self.preview_viewers.preview_visibility
        )
        window.dashboard.preview_requested.connect(self.stimulus_preview.request)
        window.dashboard.action_requested.connect(self.request_dashboard_action)
        bridge.snapshot_received.connect(self.install_snapshot)
        bridge.connection_changed.connect(self.connection_changed)
        bridge.command_finished.connect(self.command_finished)
        bridge.action_progress.connect(self.action_progress.requested)
        bridge.operation_finished.connect(self.operation_finished)
        bridge.operation_finished.connect(self.display_operations.live.finished)
        bridge.command_finished.connect(self.display_operations.live.command_finished)
        bridge.connection_changed.connect(self.display_operations.live.disconnected)
        bridge.configuration_accepted.connect(self.configuration_accepted)
        bridge.device_configuration_accepted.connect(self.device_configuration_accepted)
        bridge.spikeglx_inventory_received.connect(
            self.display_operations.install_inventory
        )
        window.close_requested.connect(self.request_close)
        bridge.start()

    def connection_changed(
        self, connected: bool, reason: str, epoch: int, generation: str
    ) -> None:
        self._connection_epoch = epoch
        if connected:
            self.connected_once = True
            self.control_ready = True
            self._connection_identity = (epoch, generation)
            self.window.dashboard.log_console.appendPlainText(
                "Controller · Controller connected."
            )
            self.claim_unheld_control()
            return
        if self.connected_once:
            self._retained_ack_required = True
            self._retained_ack_identity = self._connection_identity
            self._awaiting_reconnect_review = True
        self._connection_identity = None
        self.control_ready = False
        self.auto_control_attempted = False
        self.state = None
        self.window.devices.spikeglx.pending_action.finish()
        self.window.devices.spikeglx.pairing_pending = False
        self.tracking_diagnostics.install_snapshot(None)
        self._inventory_identity = None
        self.prompts.hide_prompt()
        self.prompts.invalidate_retained_summary()
        self.mcu.disconnected()
        self.cameras.disconnected()
        self.take.setEnabled(False)
        self.takeover.setEnabled(False)
        self.release.setEnabled(False)
        self.review_retained.setEnabled(False)
        self.review_prompt.setEnabled(False)
        self.preview_viewers.disconnected()
        self.stimulus_preview.disconnected()
        self.window.apply_view(DashboardView())
        self.tracking_diagnostics.install_snapshot(None)
        if self.close_pending:
            self.close_pending = False
            self.window.dashboard.log_console.appendPlainText(
                "GUI configuration saved; controller disconnected during history save."
            )
            self.window.finish_close()
            return
        if self.connected_once:
            QMessageBox.warning(
                self.window,
                "Controller connection lost",
                "The controller connection was lost. Commands are disabled; reconnecting.\n"
                + reason,
            )

    def install_snapshot(self, epoch: int, generation: str, raw: bytes) -> None:
        state = pb.Snapshot.FromString(raw)
        if generation != state.controller_generation:
            return
        identity = (epoch, generation)
        self._connection_epoch = epoch
        self._connection_identity = identity
        fresh_identity = self._awaiting_reconnect_review or (
            self._retained_ack_required and self._retained_ack_identity != identity
        )
        if fresh_identity:
            self._retained_ack_required = False
            self._retained_ack_identity = None
            self._awaiting_reconnect_review = False
        if retained_ack_required_for(state, identity, self._acknowledged_identity):
            self._retained_ack_required = True
            self._retained_ack_identity = identity
        self.state = state
        self.action_progress.install(epoch, state)
        held = state.control.holder_client_id == self.bridge.principal.generation
        permitted = not self._retained_ack_required
        self.review_retained.setEnabled(
            self._retained_ack_required or has_retained_history(state)
        )
        self.take.setEnabled(
            permitted and not held and not state.control.holder_client_id
        )
        self.takeover.setEnabled(
            permitted and not held and bool(state.control.holder_client_id)
        )
        self.release.setEnabled(held)
        with self.configuration.installing_projection():
            preview_views = self.cameras.install(state)
            self.window.devices.sync_cameras()
        try:
            configuration_wired = self.configuration.install(state)
        except (ValueError, TypeError, AttributeError) as error:
            configuration_wired = False
            self.configuration.last_error = str(error)
        self.reload_configuration.setEnabled(permitted and self.configuration.stale)
        view = dashboard_view(
            state,
            self.bridge.principal.generation,
            (
                *preview_views,
                stimulus_preview_view(state, self.stimulus_preview.pending),
            ),
            configuration_wired=configuration_wired,
        )
        if not permitted:
            view = replace(view, has_control=False)
        self.window.apply_view(view)
        self.display_operations.install_pairing()
        self.tracking_diagnostics.install_snapshot(state)
        self.mcu.install(state, held and permitted)
        if configuration_wired and not self.history.restore_attempted:
            if state.session.phase in (
                pb.SESSION_PHASE_CONFIGURATION,
                pb.SESSION_PHASE_READY,
            ):
                try:
                    restored = self.history.restore()
                except (
                    OSError,
                    ValueError,
                    TypeError,
                    KeyError,
                    IndexError,
                    AttributeError,
                ) as error:
                    QMessageBox.warning(
                        self.window,
                        "GUI configuration not restored",
                        f"Previous GUI configuration was preserved at {self.history.path}: {error}",
                    )
                else:
                    if restored:
                        self.configuration.dirty = True
                        self.configuration.tracking_dirty = True
                        self.configuration.edit_serial += 1
            else:
                self.history.restore_attempted = True
                self.history.restore_failed = self.history.path.exists()
                self.window.dashboard.log_console.appendPlainText(
                    "Controller session is active; previous GUI draft is preserved on disk."
                )
        self.display_operations.install_calibration_state(
            state, launch_eligible=self._calibration_launch_eligible(state)
        )
        if (
            held
            and permitted
            and state.configuration.revision
            and state.session.phase
            in (pb.SESSION_PHASE_CONFIGURATION, pb.SESSION_PHASE_READY)
            and self._inventory_identity
            != (state.controller_generation, state.configuration.revision)
        ):
            if self.bridge.request(
                "get_spikeglx_inventory",
                expected_revision=state.configuration.revision,
            ):
                self._inventory_identity = (
                    state.controller_generation,
                    state.configuration.revision,
                )
        self.prompts.update(
            state,
            require_acknowledgement=self._retained_ack_required,
            can_respond=held and permitted,
            connection_epoch=epoch,
        )
        self.review_prompt.setEnabled(bool(state.prompts))
        self.claim_unheld_control()

    def claim_unheld_control(self) -> None:
        """Try once per synchronized connection; never replace another holder."""
        if (
            not self.control_ready
            or self.state is None
            or self._retained_ack_required
            or self.auto_control_attempted
        ):
            return
        self.auto_control_attempted = True
        if not self.state.control.holder_client_id:
            self.bridge.request("take_control")

    def review_retained_state(self) -> None:
        if self.state is not None and (
            self._retained_ack_required or has_retained_history(self.state)
        ):
            self.prompts.review_retained_summary()

    def retained_state_acknowledged(self, epoch: int, generation: str) -> None:
        identity = (epoch, generation)
        if (
            not self._retained_ack_required
            or self.state is None
            or identity != self._connection_identity
            or identity != self._retained_ack_identity
            or self.state.controller_generation != generation
        ):
            return
        self._retained_ack_required = False
        self._retained_ack_identity = None
        self._acknowledged_identity = identity
        self.review_retained.setEnabled(False)
        self.window.dashboard.log_console.appendPlainText(
            "Controller · Retained controller summary acknowledged."
        )
        if self.state is not None:
            self.install_snapshot(epoch, generation, self.state.SerializeToString())
        self.claim_unheld_control()

    def queue_prompt_response(self, encoded_prompt: bytes, choice: str) -> bool:
        if (
            self._retained_ack_required
            or self.state is None
            or not self.control_ready
            or self.state.control.holder_client_id != self.bridge.principal.generation
        ):
            return False
        return self.bridge.request(
            "respond_prompt", prompt=encoded_prompt, choice=choice
        )

    def review_pending_prompts(self) -> None:
        state = self.state
        self.prompts.review_prompt(
            can_respond=bool(
                state is not None
                and not self._retained_ack_required
                and state.control.holder_client_id == self.bridge.principal.generation
            )
        )

    def log_action(self, target: str, message: str) -> None:
        self.window.dashboard.log_console.appendPlainText(message)
        if target == "tracking":
            self.window.tracking.status.console.appendPlainText(message)
        elif target:
            getattr(self.window.devices, target).console.appendPlainText(message)

    def update_action(
        self,
        target: str,
        key: tuple[str, ...],
        message: str,
        result: str,
        details: str,
    ) -> None:
        self.window.dashboard.log_console.action_entry(key, message, result, details)
        if target == "tracking":
            console = self.window.tracking.status.console
        elif target:
            console = getattr(self.window.devices, target).console
        else:
            return
        console.action_entry(key, message, result, details)

    def stimulus_preview_finished(self, action: str, *_: object) -> None:
        if action != "set_stimulus_preview":
            return
        self.stimulus_preview.finished(action)
        if self.state is not None:
            self.install_snapshot(
                self._connection_epoch,
                self.state.controller_generation,
                self.state.SerializeToString(),
            )

    def operation_finished(
        self, action: str, command_id: str, status: str, message: str
    ) -> None:
        label = action_label(action)
        normalized = status.replace("_", " ").capitalize()
        inline = self.action_progress.finished(
            action,
            status,
            f"Action: {action}\nCommand ID: {command_id}\nStatus: {status}\nMessage: {message}",
        )
        if status != "completed" and not inline:
            summary = (
                f"{label} · Waiting for operator input…"
                if status == "needs_input"
                else f"{label} · {normalized.lower()}"
                + (f" — {message}" if message else "")
            )
            self.window.dashboard.log_console.append_entry(
                summary,
                f"Action: {action}\nCommand ID: {command_id}\nStatus: {status}\nMessage: {message}",
                error=status in {"failed", "rejected", "unconfirmed"},
            )
        self.prompts.operation_finished(action)
        if action == "spikeglx_inventory_update" and status == "completed":
            self._inventory_identity = None
            if self.state is not None:
                self.install_snapshot(
                    self._connection_epoch,
                    self.state.controller_generation,
                    self.state.SerializeToString(),
                )

    def _calibration_launch_eligible(self, state: pb.Snapshot) -> bool:
        """Allow first-use calibration from accepted Configuration without renderer state."""
        if (
            not state.HasField("configuration_values")
            or state.configuration_values.revision != state.configuration.revision
            or not state.configuration.revision
            or state.session.phase != pb.SESSION_PHASE_CONFIGURATION
            or not self.control_ready
            or self.close_pending
            or self._retained_ack_required
            or state.control.holder_client_id != self.bridge.principal.generation
        ):
            return False
        return any(
            backend.backend_name == "visual_stimulus" and backend.enabled
            for backend in state.configuration_values.current.backends
        )

    def request_dashboard_action(self, action: str) -> None:
        if action == "Setup":
            projectors = self.window.devices.projectors
            projectors.discover_displays()
            if not projectors.keys:
                self.window.dashboard.log_console.appendPlainText(
                    "Setup not submitted. " + NO_PROJECTORS_MESSAGE
                )
                return
        if action not in {"Setup", "New session"}:
            self.bridge.request(action)
            return
        if self.state is None:
            QMessageBox.warning(
                self.window,
                "Configuration needs review",
                "Wait for a synchronized controller configuration before continuing.",
            )
            return
        if (
            action == "New session"
            and self.state.session.phase == pb.SESSION_PHASE_ENDED
        ):
            if self.configuration.dirty or self.configuration.stale:
                self.window.dashboard.log_console.appendPlainText(
                    "Configuration · Returning; edits kept for next Setup"
                )
            self.bridge.request("New session")
            return
        if self.configuration.stale:
            QMessageBox.warning(
                self.window,
                "Configuration needs review",
                self.configuration.last_error
                or "Wait for a synchronized controller configuration before Setup.",
            )
            return
        try:
            proposal = self.configuration.collect(
                self.state.configuration_values.current
            )
        except (ValueError, TypeError, AttributeError) as error:
            QMessageBox.warning(self.window, "Configuration is incomplete", str(error))
            return
        if self.configuration.revision != self.state.configuration.revision:
            self.configuration.stale = True
            self.configuration.last_error = "The controller configuration changed. Reload it before submitting this draft."
            self.install_snapshot(
                self._connection_epoch,
                self.state.controller_generation,
                self.state.SerializeToString(),
            )
            return
        current = self.state.configuration_values.current
        plan = configuration_update_plan(
            proposal, current, self.state.session.phase, action
        )
        if plan == "direct":
            if action == "Setup":
                self.bridge.request(
                    "Setup",
                    expected_revision=self.state.configuration.revision,
                    expected_configuration=current.SerializeToString(
                        deterministic=True
                    ),
                )
            else:
                self.bridge.request(action)
            return
        if plan == "direct_preserve":
            self.window.dashboard.log_console.appendPlainText(
                "Local edits remain unsent because the ended session must be reopened before configuration can change."
            )
            self.bridge.request(action)
            return
        if plan == "preserve":
            QMessageBox.warning(
                self.window,
                "Configuration is locked",
                "The controller only accepts configuration changes before Setup. Your local draft is preserved.",
            )
            return
        if not self.bridge.request(
            "submit_configuration",
            base_revision=self.configuration.revision,
            proposal=proposal.SerializeToString(deterministic=True),
            edit_serial=self.configuration.edit_serial,
            after_action=action,
        ):
            QMessageBox.warning(
                self.window,
                "Command queue full",
                "The configuration proposal was not sent. Retry when the controller is ready.",
            )

    def configuration_accepted(self, revision: int, submitted_edit_serial: int) -> None:
        state = self.state
        if state is None or state.configuration.revision != revision:
            return
        self.configuration.note_installed_revision(
            state, submitted_edit_serial=submitted_edit_serial
        )
        self.reload_configuration.setEnabled(self.configuration.stale)
        self.install_snapshot(
            self._connection_epoch,
            state.controller_generation,
            state.SerializeToString(),
        )

    def camera_submission_options(self, key: str) -> dict[str, object]:
        state = self.state
        if (
            state is None
            or self.configuration.stale
            or self.configuration.revision != state.configuration.revision
        ):
            raise ValueError("Camera configuration changed; reload before retrying.")
        panel = self.window.devices.microcontroller
        camera = next(
            (draft for draft in self.window.devices.cameras.drafts if draft.key == key),
            None,
        )
        role = {
            "Behavior cam": "behavioral",
            "Tracking cam": "tracking",
            "Eye tracking": "eye_tracking",
        }.get(camera.role if camera is not None else "")
        return {
            "generation": state.controller_generation,
            "base_revision": state.configuration.revision,
            "base_configuration": state.configuration_values.current.SerializeToString(
                deterministic=True
            ),
            "pin": panel.pin_editors[role].text().strip()
            if role in panel.pin_editors
            else "",
            "port": str(panel.port.currentData() or ""),
        }

    def device_configuration_accepted(self, base_revision: int, payload: bytes) -> None:
        state = pb.Snapshot.FromString(payload)
        if self.state is None or (
            self.state.controller_generation != state.controller_generation
            or self.state.configuration.revision > state.configuration.revision
        ):
            return
        if not self.configuration.note_device_revision(state, base_revision):
            return
        if (
            self.state.configuration.revision == state.configuration.revision
            and self.state.state_revision >= state.state_revision
        ):
            state = self.state
            payload = state.SerializeToString()
        self.install_snapshot(
            self._connection_epoch, state.controller_generation, payload
        )

    def reload_controller_configuration(self) -> None:
        if self.state is None or not self.configuration.stale:
            return
        self.cameras.discard_snapshot_draft(self.state)
        self.mcu.discard_snapshot_draft(
            self.state,
            self.state.control.holder_client_id == self.bridge.principal.generation,
        )
        if not self.configuration.reload(self.state):
            QMessageBox.warning(
                self.window,
                "Configuration not loaded",
                self.configuration.last_error
                or "The authoritative configuration could not be installed.",
            )
            return
        self.reload_configuration.setEnabled(False)
        self.window.devices.spikeglx.snapshots.draft_loaded = False
        self._inventory_identity = None
        self.install_snapshot(
            self._connection_epoch,
            self.state.controller_generation,
            self.state.SerializeToString(),
        )

    def confirm_takeover(self) -> None:
        if (
            QMessageBox.question(
                self.window,
                "Take over control",
                "Another operator holds control. Take it over?",
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.bridge.request("take_control", takeover=True)

    def refresh_camera_state(self) -> None:
        if self.state is not None:
            self.cameras._camera_revision = -1
            self.mcu.revision = -1
            self.install_snapshot(
                self._connection_epoch,
                self.state.controller_generation,
                self.state.SerializeToString(),
            )

    def adjust_projector_brightness(self, current_ma: int) -> None:
        if not self.bridge.request("projector_brightness", current_ma=current_ma):
            panel = self.window.devices.projectors
            panel.brightness.finish()
            panel.console.appendPlainText(
                "Brightness adjustment was not sent: controller unavailable."
            )

    def command_finished(self, action: str, success: bool, message: str) -> None:
        if action == "projector_brightness":
            projector_panel = self.window.devices.projectors
            projector_panel.brightness.finish()
            if not success:
                projector_panel.console.appendPlainText(
                    f"Brightness adjustment failed: {message}"
                )
        if action == "set_spikeglx_enabled":
            self.display_operations.pairing_finished()
            self.window.devices.spikeglx.apply_view(self.window.dashboard.view)
            if not success:
                self.window.devices.spikeglx.console.appendPlainText(message)
        label = action_label(action)
        rendered = (
            f"{label}: {message}"
            if success or message.startswith("Cancelled")
            else f"{label} failed: {message}"
        )
        inline = self.action_progress.finished(
            action,
            "completed"
            if success
            else "cancelled"
            if message.startswith("Cancelled")
            else "failed",
            f"Action: {action}\nSuccess: {success}\nMessage: {message}",
        )
        if not success and not inline:
            self.window.dashboard.log_console.append_entry(
                rendered,
                f"Action: {action}\nSuccess: {success}\nMessage: {message}",
                error=not success and not message.startswith("Cancelled"),
            )
        mcu_actions = {
            "mcu",
            "prepare_mcu_test",
            "prepare_mcu_connection",
            "mcu_upload",
            "save_mcu_pins",
            "add_mcu_output",
        }
        if action in mcu_actions:
            self.mcu.finished(action, success, message)
            if action == "save_mcu_pins" and self.state is not None:
                self.mcu.revision = -1
                self.mcu.install(
                    self.state,
                    self.state.control.holder_client_id
                    == self.bridge.principal.generation,
                )
        self.cameras.finished(action, success, message)
        if action in {
            "camera",
            "test_cameras",
            "save_camera_settings",
            "set_camera_enabled",
            "assign_camera_role",
            "prepare_camera",
            "add_mcu_output",
        }:
            self.refresh_camera_state()
        if action == "spikeglx_connection":
            panel = self.window.devices.spikeglx
            panel.pending_action.finish()
            panel.apply_view(self.window.dashboard.view)
            if success:
                self.log_action("spikeglx", "SpikeGLX · Ready")
            else:
                panel.console.appendPlainText(rendered)
            panel.status_column.set_rows(
                (
                    (
                        "CONNECTION",
                        "Verified"
                        if success
                        else "Cancelled"
                        if message.startswith("Cancelled")
                        else "Unavailable",
                    ),
                    None,
                    ("", message.replace(" · ", "\n") if success else message),
                )
            )
        if action == "get_spikeglx_inventory" and not success:
            self._inventory_identity = None
        if action == "save_configuration_history" and self.close_pending:
            self.close_pending = False
            if success:
                self.window.finish_close()
            else:
                self.window.dashboard.log_console.appendPlainText(
                    f"GUI configuration saved; controller history save failed: {message}"
                )
                self.window.finish_close()

    def request_close(self) -> None:
        if self.close_pending:
            return
        while True:
            try:
                self.history.save()
                break
            except (
                OSError,
                ValueError,
                TypeError,
                KeyError,
                IndexError,
                AttributeError,
            ) as error:
                choice = save_failure_choice(self.window, str(error))
                if choice == "retry":
                    continue
                if choice == "discard":
                    self.window.finish_close()
                return
        if self.state is not None and self.bridge.request("save_configuration_history"):
            self.close_pending = True
        else:
            self.window.finish_close()

    def shutdown(self) -> None:
        self.bridge.stop()
        self.bridge.wait(3000)


def main(argv: list[str] | None = None, *, splash: StartupSplash | None = None) -> int:
    parser = argparse.ArgumentParser(description="CephVR managed GUI")
    parser.add_argument("--bootstrap-handle", type=int, required=True)
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        parser.error("managed GUI requires Windows")
    with SingleInstanceGuard("gui"):
        bootstrap = read_bootstrap(args.bootstrap_handle)
        if bootstrap.get("role") != "gui":
            raise ValueError("managed GUI bootstrap has the wrong role")
        store = CredentialStore(
            default_runtime_root(), str(bootstrap["controller_generation"])
        )
        principal = store.provision_client(
            "gui",
            generation=str(bootstrap["generation"]),
            token=secrets.token_urlsafe(32),
        )
        try:
            root = Path(str(bootstrap["software_root"]))
            with (root / "config/backends/gui_config.toml").open("rb") as stream:
                gui_settings = tomllib.load(stream)
            with (root / "contracts/policy/gui_policy.toml").open("rb") as stream:
                gui_policy = tomllib.load(stream)
            if type(gui_settings.get("policy_version")) is not int or gui_settings[
                "policy_version"
            ] != gui_policy.get("policy_version"):
                raise ValueError("GUI config/policy version mismatch")
            delays = gui_settings["controller_reconnect"]["retry_delays_s"]
            if (
                not isinstance(delays, list)
                or not delays
                or any(type(delay) is not int or delay < 0 for delay in delays)
            ):
                raise ValueError("GUI reconnect delays must be nonnegative integers")
            app = QApplication.instance() or QApplication(sys.argv[:1])
            assert isinstance(app, QApplication)
            app.setApplicationName("CephVR2.0 Dashboard")
            settings = QSettings("CephVR", "Frontend")
            if splash is None:
                splash = StartupSplash(settings)
                splash.begin()
            apply_theme(app)
            window = ManagedDashboardWindow(settings=settings)
            bridge = ControllerBridge(
                principal,
                int(bootstrap["controller_port"]),
                int(bootstrap["max_message_bytes"]),
                tuple(delays),
            )
            manager = ManagedGui(window, bridge)
            app.aboutToQuit.connect(manager.shutdown)
            splash.reveal(window)
            return app.exec()
        finally:
            if splash is not None:
                splash.timer.stop()
                splash.close()
            store.remove_client(principal)


if __name__ == "__main__":
    raise SystemExit(main())
