"""Experiment metadata, camera drafts and recording choices in full GUI snapshots."""

from __future__ import annotations

from typing import Any

from cephvr.gui.camera_snapshot import (
    capture_cameras,
    restore_cameras,
    validate_cameras,
)
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
                name: (
                    self.dashboard.species.currentText()
                    if name == "species"
                    else getattr(self.dashboard, name).text()
                )
                for name in DASHBOARD_FIELDS
            }
            | {"sex": self.dashboard.sex.currentText()},
            "cameras": capture_cameras(self.cameras),
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
        serials = validate_cameras(self.cameras, data["cameras"])
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
            if name == "species":
                self.dashboard.set_species(data["dashboard"][name])
            else:
                getattr(self.dashboard, name).setText(data["dashboard"][name])
        self.dashboard.sex.setCurrentText(data["dashboard"]["sex"])
        by_serial = {camera.serial: camera for camera in self.cameras.drafts}
        restore_cameras(self.cameras, data["cameras"])
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
