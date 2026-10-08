"""Microcontroller draft snapshots; restoration never opens a port or uploads firmware."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtWidgets import QHBoxLayout

from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.components import button
from cephvr.gui.configuration_files import (
    JSON,
    ConfigurationFiles,
    boolean,
    envelope,
    fields,
    text,
)

if TYPE_CHECKING:
    from cephvr.gui.microcontroller import MicrocontrollerPanel


class MicrocontrollerSnapshot:
    def __init__(self, panel: MicrocontrollerPanel) -> None:
        self.panel = panel
        self.draft_loaded = False
        self.files = ConfigurationFiles(
            panel,
            "Microcontroller",
            "microcontroller.json",
            capture=self.capture,
            validate=self.validate,
            apply=self.restore,
            available=self.available,
        )
        self.files.message.connect(panel.console.appendPlainText)
        row = QHBoxLayout()
        row.addWidget(self.files.load_button)
        row.addWidget(self.files.save_button)
        panel.configuration.body.insertLayout(1, row)
        self.apply_button = button("Apply pin settings", "secondary")
        self.apply_button.setToolTip(
            "Submit the current pin draft through controller validation"
        )
        self.apply_button.clicked.connect(panel.save_pins)
        panel.configuration.body.addWidget(self.apply_button)

    def available(self) -> bool:
        panel = self.panel
        return panel.can_review and not (
            panel.review_tests
            or panel.managed_test_key
            or panel.pending_test_key
            or panel.connection_pending
            or panel.upload_pending
        )

    def refresh(self) -> None:
        self.files.set_enabled(self.available())
        self.apply_button.setEnabled(
            self.available()
            and self.panel.managed
            and bool(self.panel.port.currentData())
        )

    def capture(self) -> JSON:
        panel = self.panel
        return {
            "format": "cephvr-microcontroller-config",
            "version": 1,
            "port": str(panel.port.currentData() or ""),
            "firmware_path": panel.firmware.editor.text(),
            "trial_state": {
                "pin": panel.trial_pin.text(),
                "enabled": panel.enable_controls["trial-state"].isChecked(),
            },
            "projector_flip": {
                "pin": panel.flip_pin.text(),
                "enabled": panel.enable_controls["projector-flip"].isChecked(),
            },
            "camera_pins": {
                camera.key: panel.pin_editors[camera.key].text()
                for camera in panel.camera_rows
            },
        }

    def validate(self, value: Any) -> JSON:
        data = envelope(
            value,
            "cephvr-microcontroller-config",
            {"port", "firmware_path", "trial_state", "projector_flip", "camera_pins"},
        )
        for key in ("port", "firmware_path"):
            text(data[key], key)
        for key in ("trial_state", "projector_flip"):
            signal = fields(data[key], {"pin", "enabled"}, key)
            text(signal["pin"], key)
            boolean(signal["enabled"], key)
        pins = fields(
            data["camera_pins"],
            {camera.key for camera in self.panel.camera_rows},
            "Camera pin identities",
        )
        for key, pin in pins.items():
            text(pin, key)
        return data

    def restore(self, data: JSON) -> None:
        self.draft_loaded = True
        panel = self.panel
        trial, flip = data["trial_state"], data["projector_flip"]
        panel.set_saved_pins(
            data["port"], trial["pin"], trial["enabled"], flip["pin"], flip["enabled"]
        )
        panel.firmware.editor.setText(data["firmware_path"])
        for key, pin in data["camera_pins"].items():
            panel.pins[key] = pin
            panel.pin_editors[key].setText(pin)
        panel.refresh_tests()

    def collect(self, settings: pb.AcquisitionSettings) -> None:
        if not self.draft_loaded:
            return
        panel, pulses = self.panel, settings.pulses
        port = str(panel.port.currentData() or "")
        if port:
            pulses.port = port
        else:
            pulses.ClearField("port")
        for key, editor, pin_name, enable_name in (
            ("trial-state", panel.trial_pin, "trial_state_pin", "trial_state_enabled"),
            (
                "projector-flip",
                panel.flip_pin,
                "projector_flip_pin",
                "projector_flip_enabled",
            ),
        ):
            pin = editor.text().strip()
            if pin:
                setattr(pulses, pin_name, pin)
            else:
                pulses.ClearField(pin_name)
            setattr(pulses, enable_name, panel.enable_controls[key].isChecked())
        for camera in panel.camera_rows:
            if camera.role not in ("Behavior cam", "Tracking cam"):
                continue
            pulse = (
                pulses.behavioral if camera.role == "Behavior cam" else pulses.tracking
            )
            pin = panel.pin_editors[camera.key].text().strip()
            if pin:
                pulse.pin = pin
            else:
                pulse.ClearField("pin")

    def matches(self, settings: pb.AcquisitionSettings) -> bool:
        candidate = pb.AcquisitionSettings.FromString(settings.SerializeToString())
        self.collect(candidate)
        return candidate == settings
