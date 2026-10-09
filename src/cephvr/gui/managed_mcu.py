"""Controller-backed MCU intents from the managed Devices panel."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, InvalidOperation

from PyQt6.QtCore import QObject, QTimer

from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.controller_bridge import ControllerBridge
from cephvr.gui.microcontroller import MicrocontrollerPanel

_SIGNALS = {
    "trial-state": pb.MICROCONTROLLER_SIGNAL_KIND_TRIAL_STATE,
    "projector-flip": pb.MICROCONTROLLER_SIGNAL_KIND_PROJECTOR_FLIP,
    "behavioral": pb.MICROCONTROLLER_SIGNAL_KIND_BEHAVIORAL,
    "tracking": pb.MICROCONTROLLER_SIGNAL_KIND_TRACKING,
}


class ManagedMcu(QObject):
    """Check saved selections before forwarding bounded MCU commands."""

    def __init__(
        self,
        panel: MicrocontrollerPanel,
        bridge: ControllerBridge,
        snapshot: Callable[[], pb.Snapshot | None],
    ) -> None:
        super().__init__(panel)
        self.panel = panel
        self.bridge = bridge
        self.snapshot = snapshot
        self.pending = False
        self.revision = -1
        self.observed_ns = -1
        self.settle = QTimer(self)
        self.settle.setSingleShot(True)
        self.settle.setInterval(2300)
        self.settle.timeout.connect(self.read_status)
        panel.connection_requested.connect(self.test_connection)
        panel.save_requested.connect(self.save_pins)
        panel.pin_test_requested.connect(self.test_pin)
        panel.firmware_requested.connect(self.upload_firmware)

    def upload_firmware(self, path: str) -> None:
        state = self.snapshot()
        if state is None or self.pending or not self.panel.upload.isEnabled():
            return
        settings = next(
            (
                item.acquisition
                for item in state.configuration_values.current.backends
                if item.backend_name == "acquisition"
            ),
            None,
        )
        if settings is None or self.panel.port.currentData() != settings.pulses.port:
            self.panel.console.appendPlainText(
                "Await confirmation of the selected COM port before uploading."
            )
            return
        if self.bridge.request("mcu_upload", path=path):
            self.pending = True
            self.panel.upload_pending = True
            self.panel.connection_pending = True
            self.panel.refresh_tests()
        else:
            self.panel.console.appendPlainText(
                "Upload was not sent: controller unavailable."
            )

    def test_connection(self) -> None:
        state = self.snapshot()
        if state is None:
            return
        settings = next(
            (
                item.acquisition
                for item in state.configuration_values.current.backends
                if item.backend_name == "acquisition"
            ),
            None,
        )
        selected = self.panel.port.currentData()
        if (
            settings is None
            or not settings.pulses.HasField("port")
            or selected != settings.pulses.port
        ):
            self.panel.console.appendPlainText(
                "Await controller confirmation of the selected COM port before testing the connection."
            )
            return
        self.send(rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT)

    def save_pins(
        self,
        port: str,
        trial_pin: str,
        trial_enabled: bool,
        flip_pin: str,
        flip_enabled: bool,
        behavioral_pin: str | None,
        tracking_pin: str | None,
    ) -> None:
        if self.pending:
            return
        if not self.bridge.request(
            "save_mcu_pins",
            port=port,
            trial_pin=trial_pin,
            trial_enabled=trial_enabled,
            flip_pin=flip_pin,
            flip_enabled=flip_enabled,
            behavioral_pin=behavioral_pin,
            tracking_pin=tracking_pin,
        ):
            self.panel.console.appendPlainText(
                "MCU settings were not sent: controller unavailable."
            )
        else:
            self.pending = True
            self.panel.connection_pending = True
            self.panel.refresh_tests()

    def test_pin(self, key: str, start: bool) -> None:
        state = self.snapshot()
        if state is None:
            return
        camera = next(
            (item for item in self.panel.camera_rows if item.key == key), None
        )
        if (
            start
            and camera is not None
            and (not camera.enabled or camera.source != "External controller")
        ):
            self.panel.console.appendPlainText(
                "Enable this camera with External controller before testing its output."
            )
            return
        role = (
            "behavioral"
            if camera is not None and camera.role == "Behavior cam"
            else "tracking"
            if camera is not None and camera.role == "Tracking cam"
            else key
        )
        signal = _SIGNALS.get(role)
        if signal is None:
            self.panel.console.appendPlainText(
                "Configure this camera's supported role and pin before testing it."
            )
            return
        settings = next(
            (
                item.acquisition
                for item in state.configuration_values.current.backends
                if item.backend_name == "acquisition"
            ),
            None,
        )
        if settings is None:
            return
        pulses = settings.pulses
        saved = (
            pulses.trial_state_pin
            if key == "trial-state"
            else pulses.projector_flip_pin
            if key == "projector-flip"
            else pulses.behavioral.pin
            if role == "behavioral"
            else pulses.tracking.pin
        )
        edited = (
            self.panel.trial_pin.text().strip()
            if key == "trial-state"
            else self.panel.flip_pin.text().strip()
            if key == "projector-flip"
            else self.panel.pin_editors[key].text().strip()
        )
        if start and edited != saved:
            self.panel.console.appendPlainText(
                "Await controller confirmation of this pin assignment before testing it."
            )
            return
        if start and self.panel.port.currentData() != pulses.port:
            self.panel.console.appendPlainText(
                "Await controller confirmation of the selected COM port before testing."
            )
            return
        if start and camera is not None:
            pulse = pulses.behavioral if role == "behavioral" else pulses.tracking
            try:
                confirmed = Decimal(camera.frequency) == Decimal(
                    str(pulse.requested_frequency_hz)
                )
            except InvalidOperation:
                confirmed = False
            if not confirmed:
                self.panel.console.appendPlainText(
                    "Await controller confirmation of the camera trigger rate before testing."
                )
                return
        self.send(
            rpc.MICROCONTROLLER_COMMAND_KIND_START
            if start
            else rpc.MICROCONTROLLER_COMMAND_KIND_STOP,
            signal if start else 0,
            key,
        )

    def send(self, kind: int, signal: int = 0, key: str = "") -> None:
        if self.pending:
            return
        options = {"kind": kind}
        if kind in (
            rpc.MICROCONTROLLER_COMMAND_KIND_START,
            rpc.MICROCONTROLLER_COMMAND_KIND_STOP,
        ):
            options["signal"] = signal
        if not self.bridge.request("mcu", **options):
            self.panel.set_test_failure(
                key or "MCU", "Controller connection is unavailable."
            )
            return
        self.pending = True
        self.panel.connection_pending = True
        self.panel.pending_test_key = key
        self.panel.refresh_tests()

    def read_status(self) -> None:
        if self.panel.can_test and self.panel.managed_test_key:
            self.send(rpc.MICROCONTROLLER_COMMAND_KIND_STATUS)

    def finished(self, action: str, success: bool, message: str) -> None:
        if action not in {"mcu", "mcu_upload", "save_mcu_pins"}:
            return
        self.pending = False
        self.panel.upload_pending = False
        self.panel.connection_pending = False
        self.panel.pending_test_key = ""
        if not success:
            self.panel.console.appendPlainText(f"MCU command failed: {message}")
        # The firmware bounds tests to two seconds. Query from confirmed command
        # completion, not from submission (which can include serial startup).
        if success and action == "mcu" and self.panel.managed_test_key:
            self.settle.start()
        self.panel.refresh_tests()

    def disconnected(self) -> None:
        self.settle.stop()
        self.pending = False
        self.revision = self.observed_ns = -1
        self.panel.upload_pending = False
        self.panel.connection_pending = False
        self.panel.pending_test_key = ""
        self.panel.set_diagnostic("", False, 0)

    def install(self, state: pb.Snapshot, held: bool) -> None:
        panel = self.panel
        settings = next(
            (
                entry.acquisition
                for entry in state.configuration_values.current.backends
                if entry.backend_name == "acquisition"
            ),
            None,
        )
        if settings is not None and state.configuration.revision != self.revision:
            if not panel.snapshots.draft_loaded or panel.snapshots.matches(settings):
                panel.snapshots.draft_loaded = False
                pulses = settings.pulses
                panel.set_saved_pins(
                    pulses.port,
                    pulses.trial_state_pin,
                    pulses.trial_state_enabled,
                    pulses.projector_flip_pin,
                    pulses.projector_flip_enabled,
                )
                for row in panel.camera_rows:
                    pulse = (
                        pulses.behavioral
                        if row.role == "Behavior cam"
                        else pulses.tracking
                        if row.role == "Tracking cam"
                        else pulses.eye_tracking
                        if row.role == "Eye tracking"
                        else None
                    )
                    pin = pulse.pin if pulse is not None else ""
                    panel.pins[row.key] = pin
                    if row.key in panel.pin_editors:
                        panel.pin_editors[row.key].setText(pin)
            self.revision = state.configuration.revision
        panel.upload_available = (
            held
            and state.session.phase == pb.SESSION_PHASE_CONFIGURATION
            and not state.microcontroller.diagnostic.active
            and not state.microcontroller.cleanup_pending
            and not any(
                view.device_open or view.preview_running or view.cleanup_pending
                for view in (
                    state.acquisition_devices.behavioral,
                    state.acquisition_devices.tracking,
                    state.acquisition_devices.eye_tracking,
                )
            )
        )
        panel.refresh_tests()
        observation = state.microcontroller.observation
        if state.microcontroller.failure:
            panel.status_column.hud.setPlainText(
                f"CONNECTION  Fault\n{state.microcontroller.failure}"
            )
        elif not observation.HasField("capabilities"):
            panel.status_column.hud.setPlainText("CONNECTION  Not connected")
        else:
            panel.status_column.hud.setPlainText(
                f"CONNECTION  Verified\nPORT        {observation.port}\n"
                f"FIRMWARE    {observation.capabilities.firmware}\n"
                f"PROTOCOL    {observation.capabilities.protocol_version}\n"
                f"OUTPUTS     {'Running' if observation.state.behavioral.running or observation.state.tracking.running else 'Stopped'}"
            )
        diagnostic = state.microcontroller.diagnostic
        if not state.microcontroller.HasField("diagnostic"):
            self.observed_ns = -1
            self.settle.stop()
            panel.set_diagnostic("", False, 0)
        elif (
            diagnostic.HasField("observed_monotonic_ns")
            and diagnostic.observed_monotonic_ns != self.observed_ns
        ):
            self.observed_ns = diagnostic.observed_monotonic_ns
            key = signal_name(diagnostic.signal)
            if key in {"behavioral", "tracking"}:
                role = "Behavior cam" if key == "behavioral" else "Tracking cam"
                key = next(
                    (row.key for row in panel.camera_rows if row.role == role), ""
                )
            panel.set_diagnostic(key, diagnostic.active, diagnostic.rising_edges)
            if diagnostic.active and held and not state.microcontroller.cleanup_pending:
                self.settle.start()
            else:
                self.settle.stop()
        if not held or state.session.phase != pb.SESSION_PHASE_CONFIGURATION:
            self.settle.stop()
        elif (
            diagnostic.active
            and not state.microcontroller.cleanup_pending
            and not self.pending
            and not self.settle.isActive()
        ):
            self.settle.start()
        if state.microcontroller.cleanup_pending or any(
            view.device_open or view.preview_running or view.cleanup_pending
            for view in (
                state.acquisition_devices.behavioral,
                state.acquisition_devices.tracking,
                state.acquisition_devices.eye_tracking,
            )
        ):
            panel.can_review = False
            panel.can_test = False
            panel.refresh_tests()

    def discard_snapshot_draft(self, state: pb.Snapshot, held: bool) -> None:
        """An explicit reload replaces pending local pins with controller values."""
        self.panel.snapshots.draft_loaded = False
        self.revision = -1
        self.install(state, held)


def signal_name(value: int) -> str:
    return next((name for name, kind in _SIGNALS.items() if kind == value), "")
