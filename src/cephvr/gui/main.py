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

from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.camera_viewer import CameraViewer, PreviewReader
from cephvr.gui.controller_bridge import ControllerBridge
from cephvr.gui.layouts import fit_window_to_screen
from cephvr.gui.managed_mcu import ManagedMcu, signal_name
from cephvr.gui.managed_window import ManagedDashboardWindow
from cephvr.gui.theme import apply_theme
from cephvr.gui.view import DashboardView, Phase, PreviewView
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
_CAMERAS = {"Behavior cam": 1, "Tracking cam": 2}


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
        self._mcu_revision = -1
        self._camera_revision = -1
        self._mcu_observed_ns = -1
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
        cameras.connection_requested.connect(self.camera_connection)
        cameras.enable_requested.connect(self.set_camera_enabled)
        cameras.settings_requested.connect(self.save_camera_settings)
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
        self.window.devices.cameras.pending_enable.clear()
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
        cameras = self.window.devices.cameras
        current = state.configuration_values.current
        mcu_settings = next(
            (
                entry.acquisition
                for entry in current.backends
                if entry.backend_name == "acquisition"
            ),
            None,
        )
        mcu_panel = self.window.devices.microcontroller
        pins_changed = (
            mcu_settings is not None
            and state.configuration.revision != self._mcu_revision
        )
        if pins_changed:
            assert mcu_settings is not None
            pulses = mcu_settings.pulses
            mcu_panel.set_saved_pins(
                pulses.port if pulses.HasField("port") else "",
                pulses.trial_state_pin if pulses.HasField("trial_state_pin") else "",
                pulses.trial_state_enabled,
                pulses.projector_flip_pin
                if pulses.HasField("projector_flip_pin")
                else "",
                pulses.projector_flip_enabled,
            )
            self._mcu_revision = state.configuration.revision
        camera_settings = next(
            (
                entry.acquisition
                for entry in current.backends
                if entry.backend_name == "acquisition" and entry.enabled
            ),
            None,
        )
        camera_config_changed = state.configuration.revision != self._camera_revision
        if mcu_settings is not None:
            assignments = {
                mcu_settings.behavioral.device.device_id: "Behavior cam",
                mcu_settings.tracking.device.device_id: "Tracking cam",
            }
            for draft in cameras.drafts:
                expected_role = assignments.get(draft.serial, "Unassigned")
                role_changed = draft.role != expected_role
                if role_changed:
                    draft.role = expected_role
                    row = cameras.drafts.index(draft)
                    item = cameras.table.item(row, 2)
                    if item is not None:
                        item.setText(expected_role)
                if expected_role in _CAMERAS and (
                    camera_config_changed
                    or role_changed
                    or draft.key not in mcu_panel.pins
                ):
                    assigned_camera = (
                        mcu_settings.behavioral
                        if expected_role == "Behavior cam"
                        else mcu_settings.tracking
                    )
                    pulse = (
                        mcu_settings.pulses.behavioral
                        if expected_role == "Behavior cam"
                        else mcu_settings.pulses.tracking
                    )
                    mcu_panel.pins[draft.key] = (
                        pulse.pin if pulse.HasField("pin") else ""
                    )
                    timing = assigned_camera.device.frame_timing
                    draft.values["trigger_clock"] = (
                        "External controller"
                        if timing == camera.FRAME_TIMING_EXTERNAL_TRIGGER
                        else "Internal clock"
                        if timing == camera.FRAME_TIMING_FREE_RUNNING
                        else ""
                    )
                    draft.values["trigger_source"] = (
                        assigned_camera.device.settings.trigger_source
                        if assigned_camera.device.settings.HasField("trigger_source")
                        else ""
                    )
                    draft.values["preset"] = (
                        assigned_camera.device.pfs_source_filename
                        if assigned_camera.device.HasField("pfs_source_filename")
                        else ""
                    )
                    if pulse.HasField("requested_frequency_hz"):
                        draft.values["trigger_frequency_hz"] = (
                            f"{pulse.requested_frequency_hz:g}"
                        )
        self._camera_revision = state.configuration.revision
        if camera_config_changed:
            cameras.load_selected()
        preview_views: list[PreviewView] = []
        for draft in cameras.drafts:
            role = _CAMERAS.get(draft.role)
            if role is None:
                continue
            configured = (
                (camera_settings.behavioral if role == 1 else camera_settings.tracking)
                if camera_settings is not None
                else None
            )
            assigned = bool(configured and configured.device.device_id == draft.serial)
            draft.enabled = bool(assigned and configured and configured.enabled)
            if cameras.pending_enable.get(draft.serial) == draft.enabled:
                cameras.pending_enable.pop(draft.serial, None)
            device = (
                state.acquisition_devices.behavioral
                if role == 1
                else state.acquisition_devices.tracking
            )
            draft.connected = bool(assigned and device.device_open)
            old = self.viewers.get(role)
            visible = old is not None and old[0].isVisible()
            if old is not None and (
                not device.preview_running or device.preview_run_id != old[3]
            ):
                old[0].close()
                visible = False
            preview_views.append(
                PreviewView(
                    draft.key,
                    draft.role,
                    visible=visible,
                    available=assigned and bool(device.preview_running),
                    active=assigned and draft.enabled,
                    reason="Assign this camera in controller configuration"
                    if not assigned
                    else "",
                )
            )
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
        observation = state.acquisition_devices.pulses
        if observation.HasField("capabilities"):
            mcu_panel.status_column.hud.setPlainText(
                f"CONNECTION  Verified\nPORT        {observation.port}\n"
                f"FIRMWARE    {observation.capabilities.firmware}\n"
                f"PROTOCOL    {observation.capabilities.protocol_version}\n"
                f"OUTPUTS     {'Running' if observation.state.behavioral.running or observation.state.tracking.running else 'Stopped'}"
            )
        diagnostic = state.acquisition_devices.diagnostic
        if (
            diagnostic.HasField("observed_monotonic_ns")
            and diagnostic.observed_monotonic_ns != self._mcu_observed_ns
        ):
            self._mcu_observed_ns = diagnostic.observed_monotonic_ns
            diagnostic_key = signal_name(diagnostic.signal)
            if diagnostic_key in {"behavioral", "tracking"}:
                diagnostic_role = (
                    "Behavior cam" if diagnostic_key == "behavioral" else "Tracking cam"
                )
                diagnostic_key = next(
                    (
                        draft.key
                        for draft in cameras.drafts
                        if draft.role == diagnostic_role
                    ),
                    "",
                )
            mcu_panel.set_diagnostic(
                diagnostic_key, diagnostic.active, diagnostic.rising_edges
            )

    def camera_connection(self, key: str, start: bool) -> None:
        role = self._role(key)
        if role is None:
            return
        self.bridge.request(
            "camera",
            role=role,
            kind=rpc.CAMERA_COMMAND_KIND_START_PREVIEW
            if start
            else rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW,
        )

    def set_camera_enabled(self, serial: str, enabled: bool) -> None:
        if not self.bridge.request(
            "set_camera_enabled", serial=serial, enabled=enabled
        ):
            cameras = self.window.devices.cameras
            cameras.pending_enable.pop(serial, None)
            cameras.refresh_controls()
            cameras.console.appendPlainText(
                "Camera setting was not sent; controller connection is unavailable."
            )

    def save_camera_settings(
        self, serial: str, clock: str, source: str, preset: str, rate: str
    ) -> None:
        if not self.bridge.request(
            "save_camera_settings",
            serial=serial,
            clock=clock,
            source=source,
            preset=preset,
            rate=rate,
        ):
            self.window.devices.cameras.console.appendPlainText(
                "Camera settings were not sent; controller connection is unavailable."
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

    def preview_visibility(self, key: str, visible: bool) -> None:
        role = self._role(key)
        if role is None:
            return
        if visible:
            if role in self.viewers:
                self.viewers[role][0].show()
            else:
                self.bridge.request(
                    "camera",
                    role=role,
                    kind=rpc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER,
                )
        elif role in self.viewers:
            self.viewers[role][0].close()

    def _role(self, key: str) -> int | None:
        return next(
            (
                _CAMERAS.get(draft.role)
                for draft in self.window.devices.cameras.drafts
                if draft.key == key
            ),
            None,
        )

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
        reader.finished.connect(lambda: self.viewers.pop(role, None))
        reader.start()
        viewer.show()

    def command_finished(self, action: str, success: bool, message: str) -> None:
        rendered = f"{action}: {message}" if success else f"{action} failed: {message}"
        self.window.dashboard.log_console.appendPlainText(rendered)
        if action in {"mcu", "save_mcu_pins"}:
            self.window.devices.microcontroller.console.appendPlainText(rendered)
        if action in {"set_camera_enabled", "save_camera_settings"}:
            cameras = self.window.devices.cameras
            if not success:
                cameras.pending_enable.clear()
                cameras.refresh_controls()
            cameras.console.appendPlainText(rendered)
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
