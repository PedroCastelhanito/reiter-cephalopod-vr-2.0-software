"""Controller-backed MCU intents from the managed Devices panel."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, InvalidOperation

from PyQt6.QtCore import QObject, QSignalBlocker, QTimer

from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.controller_bridge import ControllerBridge
from cephvr.gui.microcontroller import MicrocontrollerPanel
from cephvr.gui.pin_numbers import firmware_pin

_SIGNALS = {
    "trial-state": pb.MICROCONTROLLER_SIGNAL_KIND_TRIAL_STATE,
    "projector-flip": pb.MICROCONTROLLER_SIGNAL_KIND_PROJECTOR_FLIP,
    "behavioral": pb.MICROCONTROLLER_SIGNAL_KIND_BEHAVIORAL,
    "tracking": pb.MICROCONTROLLER_SIGNAL_KIND_TRACKING,
    "eye_tracking": pb.MICROCONTROLLER_SIGNAL_KIND_EYE_TRACKING,
}
_CAMERA_ROLES = {
    "Behavior cam": "behavioral",
    "Tracking cam": "tracking",
    "Eye tracking": "eye_tracking",
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
        if settings is None or not selected:
            self.panel.console.appendPlainText(
                "Await controller confirmation of the selected COM port before testing the connection."
            )
            return
        if selected != settings.pulses.port:
            if self.bridge.request(
                "prepare_mcu_connection",
                generation=state.controller_generation,
                base_revision=state.configuration.revision,
                base_configuration=state.configuration_values.current.SerializeToString(
                    deterministic=True
                ),
                port=str(selected),
                kind=rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT,
            ):
                self.pending = True
                self.panel.connection_pending = True
                self.panel.refresh_tests()
            return
        self.send(rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT)

    def add_output(self, key: str, pin: str) -> None:
        if self.pending or not self.panel.can_review:
            return
        camera = next((row for row in self.panel.camera_rows if row.key == key), None)
        role = (
            key
            if key in _CAMERA_ROLES.values()
            else _CAMERA_ROLES.get(camera.role if camera else "")
        )
        if role is None:
            return
        if self.panel.snapshots.draft_loaded:
            self.panel.pin_editors[role].setText(pin)
            self.panel.draft_changed.emit()
            return
        if self.bridge.request("add_mcu_output", role=role, pin=pin):
            self.pending = True
            self.panel.connection_pending = True
            self.panel.refresh_tests()

    def save_pins(
        self,
        port: str,
        trial_pin: str,
        trial_enabled: bool,
        flip_pin: str,
        flip_enabled: bool,
        behavioral_pin: str | None,
        tracking_pin: str | None,
        eye_tracking_pin: str | None,
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
            eye_tracking_pin=eye_tracking_pin,
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
            (
                item
                for item in self.panel.camera_rows
                if item.key == key or _CAMERA_ROLES.get(item.role) == key
            ),
            None,
        )
        role = _CAMERA_ROLES.get(camera.role, key) if camera is not None else key
        key = role
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
            if role == "tracking"
            else pulses.eye_tracking.pin
        )
        edited = (
            self.panel.trial_pin.text().strip()
            if key == "trial-state"
            else self.panel.flip_pin.text().strip()
            if key == "projector-flip"
            else self.panel.pin_editors[key].text().strip()
        )
        changed = (
            firmware_pin(edited) != firmware_pin(saved)
            or self.panel.port.currentData() != pulses.port
        )
        frequency = (
            camera.frequency
            if camera is not None
            else (
                str(getattr(pulses, role).requested_frequency_hz)
                if role in _CAMERA_ROLES.values()
                and getattr(pulses, role).HasField("requested_frequency_hz")
                else ""
            )
        )
        if start and role in _CAMERA_ROLES.values():
            pulse = getattr(pulses, role)
            try:
                confirmed = Decimal(frequency) == Decimal(
                    str(pulse.requested_frequency_hz)
                )
            except InvalidOperation:
                confirmed = False
            changed = changed or not confirmed
        if start and changed:
            self.send(
                rpc.MICROCONTROLLER_COMMAND_KIND_START,
                signal,
                key,
                submission={
                    "generation": state.controller_generation,
                    "base_revision": state.configuration.revision,
                    "base_configuration": state.configuration_values.current.SerializeToString(
                        deterministic=True
                    ),
                    "port": str(self.panel.port.currentData() or ""),
                    "pin": edited,
                    "frequency": frequency,
                },
            )
            return
        self.send(
            rpc.MICROCONTROLLER_COMMAND_KIND_START
            if start
            else rpc.MICROCONTROLLER_COMMAND_KIND_STOP,
            signal if start else 0,
            key,
        )

    def send(
        self,
        kind: int,
        signal: int = 0,
        key: str = "",
        *,
        submission: dict[str, object] | None = None,
    ) -> None:
        if self.pending:
            return
        options: dict[str, object] = {"kind": kind}
        if kind in (
            rpc.MICROCONTROLLER_COMMAND_KIND_START,
            rpc.MICROCONTROLLER_COMMAND_KIND_STOP,
        ):
            options["signal"] = signal
        action = "mcu"
        if submission is not None:
            action = "prepare_mcu_test"
            options.update(submission)
        if not self.bridge.request(action, **options):
            self.panel.set_test_failure(
                key or "MCU", "Controller connection is unavailable."
            )
            return
        self.pending = True
        self.panel.connection_pending = True
        self.panel.pending_test_key = key
        self.panel.refresh_tests()
        if kind == rpc.MICROCONTROLLER_COMMAND_KIND_START:
            self.panel.console.appendPlainText(
                f"{key}: submitting diagnostic settings before test."
                if submission is not None
                else f"{key}: test queued for controller."
            )

    def read_status(self) -> None:
        if self.panel.can_test and self.panel.managed_test_key:
            self.send(rpc.MICROCONTROLLER_COMMAND_KIND_STATUS)

    def finished(self, action: str, success: bool, message: str) -> None:
        if action not in {
            "mcu",
            "prepare_mcu_test",
            "prepare_mcu_connection",
            "mcu_upload",
            "save_mcu_pins",
            "add_mcu_output",
        }:
            return
        self.pending = False
        self.panel.upload_pending = False
        self.panel.connection_pending = False
        self.panel.pending_test_key = ""
        if not success:
            self.panel.console.appendPlainText(f"MCU command failed: {message}")
        # The firmware bounds tests to two seconds. Query from confirmed command
        # completion, not from submission (which can include serial startup).
        if (
            success
            and action in {"mcu", "prepare_mcu_test"}
            and self.panel.managed_test_key
        ):
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
                pulses = settings.pulses
                with QSignalBlocker(panel):
                    panel.set_saved_pins(
                        pulses.port,
                        pulses.trial_state_pin,
                        pulses.trial_state_enabled,
                        pulses.projector_flip_pin,
                        pulses.projector_flip_enabled,
                    )
                    for role in _CAMERA_ROLES.values():
                        pin = getattr(pulses, role).pin
                        panel.pins[role] = pin
                        if role in panel.pin_editors:
                            panel.pin_editors[role].setText(pin)
                panel.snapshots.draft_loaded = False
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
                f"OUTPUTS     {'Running' if any(getattr(observation.state, role).running for role in ('behavioral', 'tracking', 'eye_tracking')) else 'Stopped'}"
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
