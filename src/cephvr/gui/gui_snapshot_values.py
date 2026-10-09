"""Experiment metadata, camera drafts and recording choices in full GUI snapshots."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QSignalBlocker

from cephvr.gui.cameras import CamerasPanel
from cephvr.gui.configuration_files import JSON, boolean, fields, text
from cephvr.gui.dashboard import Dashboard
from cephvr.gui.recordings import RecordingsCard

DASHBOARD_FIELDS = (
    "subject_id",
    "species",
    "age",
    "subject_size",
    "experiment",
    "condition",
    "output_root",
)


class ExperimentSnapshot:
    def __init__(
        self, dashboard: Dashboard, cameras: CamerasPanel, recordings: RecordingsCard
    ) -> None:
        self.dashboard, self.cameras, self.recordings = dashboard, cameras, recordings

    def capture(self) -> JSON:
        return {
            "dashboard": {
                name: getattr(self.dashboard, name).text() for name in DASHBOARD_FIELDS
            }
            | {"sex": self.dashboard.sex.currentText()},
            "cameras": [
                {
                    "serial": camera.serial,
                    "role": camera.role,
                    "enabled": camera.enabled,
                    "values": dict(camera.values),
                }
                for camera in self.cameras.drafts
            ],
            "recordings": {
                "stimulus": self.recordings.record["stimulus"].isChecked(),
                "velocities": self.recordings.velocities.isChecked(),
                "cameras": {
                    camera.serial: self.recordings.record[camera.key].isChecked()
                    for camera in self.cameras.drafts
                },
            },
        }

    def validate(self, value: Any) -> JSON:
        data = fields(
            value, {"dashboard", "cameras", "recordings"}, "Experiment settings"
        )
        dashboard = fields(
            data["dashboard"], set(DASHBOARD_FIELDS) | {"sex"}, "Dashboard"
        )
        for key, raw in dashboard.items():
            text(raw, key)
        if dashboard["sex"] not in {
            self.dashboard.sex.itemText(index)
            for index in range(self.dashboard.sex.count())
        }:
            raise ValueError("Unknown subject sex choice")
        cameras = data["cameras"]
        if not isinstance(cameras, list):
            raise ValueError("Camera drafts must be a list")
        serials: set[str] = set()
        roles: set[str] = set()
        for raw in cameras:
            camera = fields(raw, {"serial", "role", "enabled", "values"}, "Camera")
            serial = text(camera["serial"], "Camera serial")
            if not serial or serial in serials:
                raise ValueError("Camera serials must be unique and nonempty")
            serials.add(serial)
            role = text(camera["role"], "Camera role")
            if (
                role
                not in ("Behavior cam", "Tracking cam", "Eye tracking", "Unassigned")
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
        if serials != {camera.serial for camera in self.cameras.drafts}:
            raise ValueError(
                "Saved camera serials differ from the current inventory; refresh/connect the matching rig first"
            )
        recordings = fields(
            data["recordings"], {"stimulus", "velocities", "cameras"}, "Recordings"
        )
        boolean(recordings["stimulus"], "Stimulus recording")
        boolean(recordings["velocities"], "Tracking recording")
        for key, item in fields(
            recordings["cameras"], serials, "Camera recordings"
        ).items():
            boolean(item, key)
        return data

    def restore(self, data: JSON) -> None:
        for name in DASHBOARD_FIELDS:
            getattr(self.dashboard, name).setText(data["dashboard"][name])
        self.dashboard.sex.setCurrentText(data["dashboard"]["sex"])
        by_serial = {camera.serial: camera for camera in self.cameras.drafts}
        with QSignalBlocker(self.cameras):
            for raw in data["cameras"]:
                camera = by_serial[raw["serial"]]
                camera.role, camera.enabled, camera.values = (
                    raw["role"],
                    raw["enabled"],
                    dict(raw["values"]),
                )
            self.cameras.populate_inventory()
            self.cameras.load_selected()
        self.cameras.snapshot_draft = True
        self.cameras.drafts_changed.emit()
        values = {
            "stimulus": data["recordings"]["stimulus"],
            "velocities": data["recordings"]["velocities"],
        }
        values.update(
            {
                by_serial[serial].key: enabled
                for serial, enabled in data["recordings"]["cameras"].items()
            }
        )
        self.recordings.install_values(values)
        self.recordings.touched.update(values)
        self.recordings.recording_changed()
