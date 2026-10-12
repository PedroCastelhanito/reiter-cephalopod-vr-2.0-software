"""Camera-only draft files and shared full-GUI camera serialization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QSignalBlocker

from cephvr.gui.configuration_files import (
    JSON,
    ConfigurationFiles,
    boolean,
    envelope,
    fields,
    text,
)

if TYPE_CHECKING:
    from cephvr.gui.cameras import CamerasPanel


def capture_cameras(panel: CamerasPanel) -> list[JSON]:
    return [
        {
            "serial": camera.serial,
            "role": camera.role,
            "enabled": camera.enabled,
            "values": dict(camera.values),
        }
        for camera in panel.drafts
    ]


def validate_cameras(panel: CamerasPanel, value: Any) -> set[str]:
    if not isinstance(value, list):
        raise ValueError("Camera drafts must be a list")
    serials: set[str] = set()
    roles: set[str] = set()
    for raw in value:
        camera = fields(raw, {"serial", "role", "enabled", "values"}, "Camera")
        serial = text(camera["serial"], "Camera serial")
        if not serial or serial in serials:
            raise ValueError("Camera serials must be unique and nonempty")
        serials.add(serial)
        role = text(camera["role"], "Camera role")
        if (
            role not in ("Behavior cam", "Tracking cam", "Eye tracking", "Unassigned")
            or role != "Unassigned"
            and role in roles
        ):
            raise ValueError("Invalid or duplicate camera role")
        roles.add(role)
        boolean(camera["enabled"], "Camera enable")
        values = camera["values"]
        if not isinstance(values, dict):
            raise ValueError("Camera settings must be an object")
        for key, item in values.items():
            text(key, "Camera setting name")
            text(item, key)
    if serials != {camera.serial for camera in panel.drafts}:
        raise ValueError(
            "Saved camera serials differ from the current inventory; refresh/connect the matching rig first"
        )
    return serials


def restore_cameras(panel: CamerasPanel, cameras: list[JSON]) -> None:
    by_serial = {camera.serial: camera for camera in panel.drafts}
    with QSignalBlocker(panel):
        for raw in cameras:
            camera = by_serial[raw["serial"]]
            camera.role, camera.enabled, camera.values = (
                raw["role"],
                raw["enabled"],
                dict(raw["values"]),
            )
        panel.populate_inventory()
        panel.load_selected()
    panel.snapshot_draft = True
    panel.drafts_changed.emit()
    panel.participation_changed.emit()


class CameraSnapshot:
    def __init__(self, panel: CamerasPanel) -> None:
        self.panel = panel
        self.files = ConfigurationFiles(
            panel,
            "Cameras",
            "cameras.json",
            capture=self.capture,
            validate=self.validate,
            apply=lambda data: restore_cameras(panel, data["cameras"]),
            available=self.available,
        )
        self.files.message.connect(panel.console.appendPlainText)

    def available(self) -> bool:
        return (
            self.panel.view.can_edit
            and not self.panel.operation_pending
            and not any(c.connected or c.capture_running for c in self.panel.drafts)
        )

    def capture(self) -> JSON:
        return {
            "format": "cephvr-cameras-config",
            "version": 1,
            "cameras": capture_cameras(self.panel),
        }

    def validate(self, value: Any) -> JSON:
        data = envelope(value, "cephvr-cameras-config", {"cameras"})
        validate_cameras(self.panel, data["cameras"])
        return data
