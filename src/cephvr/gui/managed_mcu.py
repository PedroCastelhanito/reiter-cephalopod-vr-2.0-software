"""Controller-backed MCU intents from the managed Devices panel."""

from __future__ import annotations

from collections.abc import Callable

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
        panel.connection_requested.connect(self.test_connection)
        panel.save_requested.connect(self.save_pins)
        panel.pin_test_requested.connect(self.test_pin)

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
                "Save the selected COM port before testing the connection."
            )
            return
        self.bridge.request("mcu", kind=rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT)

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
        self.bridge.request(
            "save_mcu_pins",
            port=port,
            trial_pin=trial_pin,
            trial_enabled=trial_enabled,
            flip_pin=flip_pin,
            flip_enabled=flip_enabled,
            behavioral_pin=behavioral_pin,
            tracking_pin=tracking_pin,
        )

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
                "Save and configure camera pins before testing them."
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
                "Save this pin assignment before testing it."
            )
            return
        self.bridge.request(
            "mcu",
            kind=rpc.MICROCONTROLLER_COMMAND_KIND_START
            if start
            else rpc.MICROCONTROLLER_COMMAND_KIND_STOP,
            signal=signal if start else pb.MICROCONTROLLER_SIGNAL_KIND_UNSPECIFIED,
        )
        if start:
            QTimer.singleShot(
                2300,
                lambda: (
                    self.bridge.request(
                        "mcu", kind=rpc.MICROCONTROLLER_COMMAND_KIND_STATUS
                    )
                    if self.panel.managed_test_key == key
                    else None
                ),
            )


def signal_name(value: int) -> str:
    return next((name for name, kind in _SIGNALS.items() if kind == value), "")
