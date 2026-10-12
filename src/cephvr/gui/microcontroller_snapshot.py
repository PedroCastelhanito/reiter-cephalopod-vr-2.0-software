"""Microcontroller draft snapshots; restoration never opens a port or uploads firmware."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.configuration_files import (
    JSON,
    ConfigurationFiles,
    boolean,
    fields,
    text,
)

if TYPE_CHECKING:
    from cephvr.gui.microcontroller import MicrocontrollerPanel


class MicrocontrollerSnapshot:
    def __init__(self, panel: MicrocontrollerPanel) -> None:
        self.panel = panel
        self.draft_loaded = False
        self.camera_available: Callable[[], bool] = lambda: True
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

    def available(self) -> bool:
        panel = self.panel
        return (
            panel.can_review
            and self.camera_available()
            and not (
                panel.review_tests
                or panel.managed_test_key
                or panel.pending_test_key
                or panel.connection_pending
                or panel.upload_pending
            )
        )

    def refresh(self) -> None:
        self.files.set_enabled(self.available())

    def capture(self) -> JSON:
        panel = self.panel
        return {
            "format": "cephvr-microcontroller-config",
            "version": 2,
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
            "camera_enabled": {
                camera.key: camera.enabled for camera in panel.camera_rows
            },
        }

    def validate(self, value: Any) -> JSON:
        if (
            not isinstance(value, dict)
            or value.get("format") != "cephvr-microcontroller-config"
            or type(value.get("version")) is not int
            or value["version"] not in (1, 2)
        ):
            raise ValueError("Unsupported cephvr-microcontroller-config format/version")
        keys = {
            "format",
            "version",
            "port",
            "firmware_path",
            "trial_state",
            "projector_flip",
            "camera_pins",
        }
        if value["version"] == 2:
            keys.add("camera_enabled")
        data = fields(value, keys, "Microcontroller settings")
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
        if data["version"] == 2:
            for key, enabled in fields(
                data["camera_enabled"], set(pins), "Camera output participation"
            ).items():
                boolean(enabled, key)
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
        if data["version"] == 2:
            panel.camera_draft_loaded.emit(data["camera_enabled"])
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
