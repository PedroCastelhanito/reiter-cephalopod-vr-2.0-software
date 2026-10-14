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
from cephvr.gui.microcontroller_signals import ROLE_OUTPUTS
from cephvr.gui.pin_numbers import firmware_pin

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
            "version": 3,
            "port": str(panel.port.currentData() or ""),
            "firmware_path": panel.firmware.editor.text(),
            "trial_state": {
                "pin": firmware_pin(panel.trial_pin.text()),
                "enabled": panel.enable_controls["trial-state"].isChecked(),
            },
            "projector_flip": {
                "pin": firmware_pin(panel.flip_pin.text()),
                "enabled": False,
            },
            "camera_pins": {
                key: firmware_pin(panel.pin_editors[key].text())
                for key, _role in ROLE_OUTPUTS
            },
        }

    def validate(
        self, value: Any, *, legacy_roles: dict[str, str] | None = None
    ) -> JSON:
        if (
            not isinstance(value, dict)
            or value.get("format") != "cephvr-microcontroller-config"
            or type(value.get("version")) is not int
            or value["version"] not in (1, 2, 3)
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
        if data["version"] == 3:
            pin_keys = {key for key, _role in ROLE_OUTPUTS}
        else:
            pin_keys = {camera.key for camera in self.panel.camera_rows}
        pins = fields(data["camera_pins"], pin_keys, "Camera pin identities")
        for key, pin in pins.items():
            text(pin, key)
        if data["version"] == 2:
            enabled = fields(data["camera_enabled"], pin_keys, "Camera participation")
            for key, item in enabled.items():
                boolean(item, key)
        normalized = dict(data)
        if data["version"] < 3:
            role_by_identity = (
                legacy_roles
                if legacy_roles is not None
                else {
                    camera.key: self.panel.role_key(camera.role)
                    for camera in self.panel.camera_rows
                    if self.panel.role_key(camera.role)
                }
            )
            migrated = {key: "" for key, _role in ROLE_OUTPUTS}
            assigned_roles: set[str] = set()
            for camera_key, pin in pins.items():
                role_key = role_by_identity.get(camera_key)
                if not role_key:
                    if not pin:
                        continue
                    raise ValueError(
                        f"Cannot migrate MCU pin for unknown camera identity {camera_key!r}"
                    )
                if role_key in assigned_roles:
                    raise ValueError("Multiple legacy camera pins map to the same role")
                assigned_roles.add(role_key)
                migrated[role_key] = pin
            normalized["camera_pins"] = migrated
        normalized["version"] = 3
        normalized.pop("camera_enabled", None)
        return normalized

    def restore(self, data: JSON) -> None:
        self.draft_loaded = True
        panel = self.panel
        trial, flip = data["trial_state"], data["projector_flip"]
        panel.set_saved_pins(
            data["port"], trial["pin"], trial["enabled"], flip["pin"], flip["enabled"]
        )
        panel.firmware.editor.setText(data["firmware_path"])
        for key, _role in ROLE_OUTPUTS:
            pin = data["camera_pins"].get(key, "")
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
            pin = firmware_pin(editor.text())
            if pin:
                setattr(pulses, pin_name, pin)
            else:
                pulses.ClearField(pin_name)
            setattr(
                pulses,
                enable_name,
                key != "projector-flip" and panel.enable_controls[key].isChecked(),
            )
        for key, _role in ROLE_OUTPUTS:
            pulse = getattr(pulses, key)
            pin = firmware_pin(panel.pin_editors[key].text())
            if pin:
                pulse.pin = pin
            else:
                pulse.ClearField("pin")

    def matches(self, settings: pb.AcquisitionSettings) -> bool:
        candidate = pb.AcquisitionSettings.FromString(settings.SerializeToString())
        self.collect(candidate)
        return candidate == settings
