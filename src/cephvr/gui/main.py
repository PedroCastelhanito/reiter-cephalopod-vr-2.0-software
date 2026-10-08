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
from cephvr.gui.controller_bridge import ControllerBridge
from cephvr.gui.layouts import fit_window_to_screen
from cephvr.gui.managed_cameras import ManagedCameras
from cephvr.gui.managed_close import request_managed_close, save_failure_choice
from cephvr.gui.managed_configuration import ConfigurationPages, ManagedConfiguration
from cephvr.gui.managed_configuration_transport import configuration_update_plan
from cephvr.gui.managed_display import ManagedDisplayOperations
from cephvr.gui.managed_mcu import ManagedMcu
from cephvr.gui.managed_preview_viewers import ManagedPreviewViewers
from cephvr.gui.managed_prompts import ManagedPrompts
from cephvr.gui.managed_status import dashboard_view, retained_ack_required_for
from cephvr.gui.managed_tracking_diagnostics import ManagedTrackingDiagnostics
from cephvr.gui.managed_window import ManagedDashboardWindow
from cephvr.gui.preview_placement import preview_window_placement
from cephvr.gui.theme import apply_theme
from cephvr.gui.view import DashboardView
from cephvr.platform.windows.bootstrap import read_bootstrap
from cephvr.platform.windows.guard import SingleInstanceGuard
from cephvr.shared.credentials import CredentialStore, default_runtime_root


class ManagedGui(QObject):
    """Project authoritative state and forward explicit user intents."""

    def __init__(
        self, window: ManagedDashboardWindow, bridge: ControllerBridge
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
        self.state: pb.Snapshot | None = None
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
        self.review_retained = QAction("Review reconnect status…", self)
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
            lambda: preview_window_placement(window).SerializeToString(),
        )
        self.cameras = ManagedCameras(
            cameras,
            bridge,
            self.preview_viewers.viewer_state,
            lambda: preview_window_placement(window).SerializeToString(),
        )
        cameras.inventory_refreshed.connect(self.refresh_camera_state)
        cameras.preview_requested.connect(self.preview_viewers.preview_visibility)
        mcu = window.devices.microcontroller
        mcu.managed = True
        mcu.scan_ports()
        window.devices.projectors.discover_displays()
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
            lambda: bridge.request("spikeglx_connection")
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
        window.dashboard.control_requested.connect(self.request_control)
        window.dashboard.action_requested.connect(self.request_dashboard_action)
        bridge.snapshot_received.connect(self.install_snapshot)
        bridge.connection_changed.connect(self.connection_changed)
        bridge.command_finished.connect(self.command_finished)
        bridge.command_admitted.connect(self.command_admitted)
        bridge.operation_finished.connect(self.operation_finished)
        bridge.configuration_accepted.connect(self.configuration_accepted)
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
            self.window.dashboard.log_console.appendPlainText("Controller connected.")
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
        self.tracking_diagnostics.install_snapshot(None)
        self._inventory_identity = None
        self.prompts.hide_prompt()
        self.prompts.invalidate_retained_summary()
        self.mcu.disconnected()
        self.cameras.disconnected()
        self.take.setEnabled(False)
        self.takeover.setEnabled(False)
        self.release.setEnabled(False)
        self.review_retained.setEnabled(self._retained_ack_required)
        self.review_prompt.setEnabled(False)
        self.preview_viewers.disconnected()
        self.window.apply_view(DashboardView())
        self.tracking_diagnostics.install_snapshot(None)
        if self.close_pending:
            self.close_pending = False
            self._save_failed(reason or "Controller connection lost during save.")
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
        if self._awaiting_reconnect_review or (
            self._retained_ack_required and self._retained_ack_identity != identity
        ):
            self._retained_ack_required = True
            self._retained_ack_identity = identity
            self._awaiting_reconnect_review = False
        if retained_ack_required_for(state, identity, self._acknowledged_identity):
            self._retained_ack_required = True
            self._retained_ack_identity = identity
        self.state = state
        held = state.control.holder_client_id == self.bridge.principal.generation
        permitted = not self._retained_ack_required
        self.review_retained.setEnabled(self._retained_ack_required)
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
            self.configuration._installing = False
        self.reload_configuration.setEnabled(permitted and self.configuration.stale)
        view = dashboard_view(
            state,
            self.bridge.principal.generation,
            tuple(preview_views),
            configuration_wired=configuration_wired,
        )
        if not permitted:
            view = replace(view, has_control=False)
        self.window.apply_view(view)
        self.tracking_diagnostics.install_snapshot(state)
        self.mcu.install(state, held and permitted)
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
        if self._retained_ack_required:
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
            "Retained controller summary acknowledged."
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

    def command_admitted(self, action: str, command_id: str) -> None:
        self.window.dashboard.log_console.appendPlainText(
            f"{action}: admitted as {command_id}; awaiting completion evidence."
        )

    def operation_finished(
        self, action: str, command_id: str, status: str, message: str
    ) -> None:
        self.window.dashboard.log_console.appendPlainText(
            f"{action} [{command_id}] {status}: {message}"
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
        if (
            action == "submit_configuration"
            and self.close_pending
            and status != "completed"
        ):
            self.close_pending = False
            self._save_failed(message)

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
                    "New session will use the last accepted configuration. Your local draft remains in the editor for review."
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
        self.configuration.last_error = ""
        self.reload_configuration.setEnabled(False)
        self.window.dashboard.log_console.appendPlainText(
            f"Controller accepted configuration revision {revision}."
        )
        self.install_snapshot(
            self._connection_epoch,
            state.controller_generation,
            state.SerializeToString(),
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

    def request_control(self) -> None:
        state = self.state
        if state is None:
            return
        if state.control.holder_client_id:
            self.confirm_takeover()
        else:
            self.bridge.request("take_control")

    def refresh_camera_state(self) -> None:
        if self.state is not None:
            self.cameras._camera_revision = -1
            self.mcu.revision = -1
            self.install_snapshot(
                self._connection_epoch,
                self.state.controller_generation,
                self.state.SerializeToString(),
            )

    def command_finished(self, action: str, success: bool, message: str) -> None:
        rendered = f"{action}: {message}" if success else f"{action} failed: {message}"
        self.window.dashboard.log_console.appendPlainText(rendered)
        if action in {"mcu", "mcu_upload", "save_mcu_pins"}:
            self.mcu.finished(action, success, message)
            if action == "save_mcu_pins" and self.state is not None:
                self.mcu.revision = -1
                self.mcu.install(
                    self.state,
                    self.state.control.holder_client_id
                    == self.bridge.principal.generation,
                )
            self.window.devices.microcontroller.console.appendPlainText(rendered)
        self.cameras.finished(action, success, message)
        if action in {
            "camera",
            "test_cameras",
            "save_camera_settings",
            "set_camera_enabled",
            "assign_camera_role",
        }:
            self.refresh_camera_state()
        if action == "spikeglx_connection":
            panel = self.window.devices.spikeglx
            panel.console.appendPlainText(rendered)
            panel.status_column.hud.setPlainText(
                "CONNECTION  Verified\n" + message.replace(" · ", "\n")
                if success
                else "CONNECTION  Unavailable\n" + message
            )
        if action == "get_spikeglx_inventory" and not success:
            self._inventory_identity = None
        if action == "save_configuration_history" and self.close_pending:
            self.close_pending = False
            if success:
                self.window.finish_close()
            else:
                self._save_failed(message)

    def request_close(self) -> None:
        if self.close_pending:
            return
        result = request_managed_close(
            self.state,
            self.configuration,
            send=self.bridge.request,
            confirm_discard=self.confirm_discard_local_draft,
            log=self.window.dashboard.log_console.appendPlainText,
        )
        if result.kind == "failed":
            self._save_failed(result.message)
            return
        if result.kind == "cancelled":
            return
        self.close_pending = True

    def confirm_discard_local_draft(self) -> bool:
        dialog = QMessageBox(self.window)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Unsent configuration draft")
        dialog.setText("Closing now discards the local configuration draft.")
        dialog.setInformativeText(
            "The controller history will contain only its last accepted configuration."
        )
        discard = dialog.addButton(
            "Close and discard draft", QMessageBox.ButtonRole.DestructiveRole
        )
        dialog.addButton("Keep editing", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        return dialog.clickedButton() is discard

    def _save_failed(self, reason: str) -> None:
        choice = save_failure_choice(self.window, reason)
        if choice == "retry":
            self.request_close()
        elif choice == "discard":
            self.window.finish_close()

    def shutdown(self) -> None:
        self.bridge.stop()
        self.bridge.wait(3000)


def main(argv: list[str] | None = None) -> int:
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
            app = QApplication(sys.argv[:1])
            app.setApplicationName("CephVR2.0 Dashboard")
            apply_theme(app)
            window = ManagedDashboardWindow(settings=QSettings("CephVR", "Frontend"))
            bridge = ControllerBridge(
                principal,
                int(bootstrap["controller_port"]),
                int(bootstrap["max_message_bytes"]),
                tuple(delays),
            )
            manager = ManagedGui(window, bridge)
            app.aboutToQuit.connect(manager.shutdown)
            fit_window_to_screen(window)
            window.show()
            return app.exec()
        finally:
            store.remove_client(principal)


if __name__ == "__main__":
    raise SystemExit(main())
