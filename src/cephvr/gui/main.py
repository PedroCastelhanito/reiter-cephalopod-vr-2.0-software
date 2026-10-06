"""Managed Windows GUI entry point and controller-backed camera controls."""

from __future__ import annotations

import argparse
import secrets
import sys
import tomllib
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMessageBox

from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.camera_viewer import CameraViewer, PreviewReader
from cephvr.gui.controller_bridge import ControllerBridge
from cephvr.gui.layouts import fit_window_to_screen
from cephvr.gui.managed_cameras import ManagedCameras
from cephvr.gui.managed_mcu import ManagedMcu
from cephvr.gui.managed_window import ManagedDashboardWindow
from cephvr.gui.theme import apply_theme
from cephvr.gui.view import DashboardView, Phase
from cephvr.platform.windows.bootstrap import read_bootstrap
from cephvr.platform.windows.guard import SingleInstanceGuard
from cephvr.shared.credentials import CredentialStore, default_runtime_root

_PHASES = {
    pb.SESSION_PHASE_CONFIGURATION: Phase.CONFIGURATION,
    pb.SESSION_PHASE_SETTING_UP: Phase.SETTING_UP,
    pb.SESSION_PHASE_READY: Phase.READY,
    pb.SESSION_PHASE_STARTING: Phase.STARTING,
    pb.SESSION_PHASE_RUNNING: Phase.RUNNING,
    pb.SESSION_PHASE_FINALIZING: Phase.FINALIZING,
    pb.SESSION_PHASE_ENDED: Phase.ENDED,
}


class ManagedGui(QObject):
    """Project authoritative state and forward explicit user intents."""

    def __init__(
        self, window: ManagedDashboardWindow, bridge: ControllerBridge
    ) -> None:
        super().__init__(window)
        self.window = window
        self.bridge = bridge
        self.connected_once = False
        self.close_pending = False
        self.state: pb.Snapshot | None = None
        self.viewers: dict[
            int, tuple[CameraViewer, PreviewReader, acq.FrameBufferAttachment, str]
        ] = {}
        menu_bar = window.menuBar()
        assert menu_bar is not None
        menu = menu_bar.addMenu("Control")
        assert menu is not None
        self.take = QAction("Take control", self)
        self.takeover = QAction("Take over control…", self)
        self.release = QAction("Release control", self)
        menu.addActions((self.take, self.takeover, self.release))
        self.take.triggered.connect(lambda: bridge.request("take_control"))
        self.takeover.triggered.connect(self.confirm_takeover)
        self.release.triggered.connect(lambda: bridge.request("release_control"))
        self.take.setEnabled(False)
        self.takeover.setEnabled(False)
        self.release.setEnabled(False)
        cameras = window.devices.cameras
        cameras.managed = True
        cameras.real_devices = True
        cameras.refresh_inventory()
        self.cameras = ManagedCameras(cameras, bridge, self.viewer_state)
        cameras.inventory_refreshed.connect(self.refresh_camera_state)
        cameras.preview_requested.connect(self.preview_visibility)
        mcu = window.devices.microcontroller
        mcu.managed = True
        mcu.scan_ports()
        window.devices.projectors.discover_displays()
        self.mcu = ManagedMcu(mcu, bridge, lambda: self.state)
        window.devices.spikeglx.connection_requested.connect(
            lambda: bridge.request("spikeglx_connection")
        )
        window.dashboard.preview_requested.connect(self.preview_visibility)
        window.dashboard.control_requested.connect(self.request_control)
        window.dashboard.action_requested.connect(lambda action: bridge.request(action))
        bridge.snapshot_received.connect(self.install_snapshot)
        bridge.connection_changed.connect(self.connection_changed)
        bridge.command_finished.connect(self.command_finished)
        bridge.attachment_received.connect(self.attach_viewer)
        window.close_requested.connect(self.request_close)
        bridge.start()

    def connection_changed(self, connected: bool, reason: str) -> None:
        if connected:
            self.connected_once = True
            self.window.dashboard.log_console.appendPlainText("Controller connected.")
            return
        self.state = None
        self.mcu.disconnected()
        self.cameras.disconnected()
        self.take.setEnabled(False)
        self.takeover.setEnabled(False)
        self.release.setEnabled(False)
        for viewer, _, _, _ in tuple(self.viewers.values()):
            viewer.close()
        self.window.apply_view(DashboardView())
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

    def install_snapshot(self, raw: bytes) -> None:
        state = pb.Snapshot.FromString(raw)
        self.state = state
        held = state.control.holder_client_id == self.bridge.principal.generation
        self.take.setEnabled(not held and not state.control.holder_client_id)
        self.takeover.setEnabled(not held and bool(state.control.holder_client_id))
        self.release.setEnabled(held)
        preview_views = self.cameras.install(state)
        self.window.devices.sync_cameras()
        phase = _PHASES.get(state.session.phase, Phase.CONFIGURATION)
        self.window.apply_view(
            DashboardView(
                phase=phase,
                connected=True,
                has_control=held,
                configuration_wired=False,
                camera_status="Preview running"
                if any(v.available for v in preview_views)
                else "Idle",
                previews=tuple(preview_views),
            )
        )
        self.mcu.install(state, held)

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

    def preview_visibility(self, key: str, visible: bool) -> None:
        role = self._role(key)
        if role is None:
            return
        if visible:
            if role in self.viewers:
                self.viewers[role][0].show()
            else:
                self.cameras.queue(
                    "camera",
                    role=role,
                    kind=rpc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER,
                )
        elif role in self.viewers:
            self.viewers[role][0].close()

    def _role(self, key: str) -> int | None:
        return self.cameras.role(key)

    def viewer_state(self, role: int, running: bool, run_id: str) -> bool:
        old = self.viewers.get(role)
        if old is not None and (not running or run_id != old[3]):
            old[0].close()
            return False
        return old is not None and old[0].isVisible()

    def refresh_camera_state(self) -> None:
        if self.state is not None:
            self.cameras._camera_revision = -1
            self.mcu.revision = -1
            self.install_snapshot(self.state.SerializeToString())

    def attach_viewer(self, role: int, raw: bytes, release_only: bool) -> None:
        attachment = acq.FrameBufferAttachment.FromString(raw)
        state = self.state
        if state is None:
            return
        device = (
            state.acquisition_devices.behavioral
            if role == 1
            else state.acquisition_devices.tracking
        )
        run_id = device.preview_run_id
        if release_only:
            self.bridge.request(
                "viewer_state",
                attachment=attachment,
                run_id=run_id,
                result=rpc.PREVIEW_CONSUMER_RESULT_RELEASED,
            )
            return
        settings = next(
            (
                entry.acquisition
                for entry in state.configuration_values.current.backends
                if entry.backend_name == "acquisition" and entry.enabled
            ),
            None,
        )
        bits = (
            settings.preview_output_bit_depth
            if settings is not None and settings.HasField("preview_output_bit_depth")
            else 8
        )
        reader = PreviewReader(attachment, bits, run_id)
        viewer = CameraViewer(
            reader, "Behavior camera" if role == 1 else "Tracking camera"
        )
        self.viewers[role] = (viewer, reader, attachment, run_id)
        reader.attached.connect(
            lambda: self.bridge.request(
                "viewer_state",
                attachment=attachment,
                run_id=run_id,
                result=rpc.PREVIEW_CONSUMER_RESULT_ATTACHED,
            )
        )
        reader.released.connect(
            lambda: self.bridge.request(
                "viewer_state",
                attachment=attachment,
                run_id=run_id,
                result=rpc.PREVIEW_CONSUMER_RESULT_RELEASED,
            )
        )
        reader.failed.connect(
            lambda message: self.command_finished("viewer", False, message)
        )
        reader.failed.connect(
            lambda _message: self.bridge.request(
                "viewer_state",
                attachment=attachment,
                run_id=run_id,
                result=rpc.PREVIEW_CONSUMER_RESULT_FAILED,
            )
        )
        reader.finished.connect(lambda: self.viewer_finished(role, reader))
        reader.start()
        viewer.show()

    def viewer_finished(self, role: int, reader: PreviewReader) -> None:
        current = self.viewers.get(role)
        if current is not None and current[1] is reader:
            self.viewers.pop(role)
            self.refresh_camera_state()

    def command_finished(self, action: str, success: bool, message: str) -> None:
        rendered = f"{action}: {message}" if success else f"{action} failed: {message}"
        self.window.dashboard.log_console.appendPlainText(rendered)
        if action in {"mcu", "save_mcu_pins"}:
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
        if action == "save_configuration_history" and self.close_pending:
            self.close_pending = False
            if success:
                self.window.finish_close()
            else:
                self._save_failed(message)

    def request_close(self) -> None:
        if self.close_pending:
            return
        if self.state is None or not self.bridge.request("save_configuration_history"):
            self._save_failed("Controller connection is unavailable.")
            return
        self.close_pending = True

    def _save_failed(self, reason: str) -> None:
        dialog = QMessageBox(self.window)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Configuration not saved")
        dialog.setText("The last configuration could not be saved.")
        dialog.setInformativeText(reason)
        retry = dialog.addButton("Retry", QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton("Close without saving", QMessageBox.ButtonRole.DestructiveRole)
        dialog.exec()
        if dialog.clickedButton() is retry:
            self.request_close()
        else:
            self.window.finish_close()

    def shutdown(self) -> None:
        for viewer, reader, _, _ in tuple(self.viewers.values()):
            viewer.close()
            reader.wait(2000)
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
