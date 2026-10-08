"""Compose independently validated page snapshots without controller/runtime ownership."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PyQt6.QtWidgets import QWidget

from cephvr.gui.configuration_files import (
    JSON,
    ConfigurationFiles,
    boolean,
    envelope,
    fields,
)
from cephvr.gui.dashboard import Dashboard
from cephvr.gui.devices import DevicesPage
from cephvr.gui.gui_snapshot_values import ExperimentSnapshot
from cephvr.gui.projector_assignments import (
    sync_assignment_controls,
    validate_assignments,
)
from cephvr.gui.protocol import ProtocolPage
from cephvr.gui.protocol_snapshot import (
    capture_protocol,
    restore_protocol,
    validate_protocol,
)
from cephvr.gui.recordings import RecordingsCard
from cephvr.gui.tracking import TrackingPage


@dataclass(frozen=True)
class SnapshotPages:
    dashboard: Dashboard
    devices: DevicesPage
    protocol: ProtocolPage
    recordings: RecordingsCard
    tracking: TrackingPage


class GuiSnapshot:
    def __init__(self, pages: SnapshotPages) -> None:
        self.pages = pages
        self.experiment = ExperimentSnapshot(
            pages.dashboard, pages.devices.cameras, pages.recordings
        )

    def available(self) -> bool:
        pages = self.pages
        return (
            pages.protocol.can_edit
            and pages.tracking.can_edit
            and not pages.tracking._diagnostic_locked
            and pages.devices.microcontroller.snapshots.available()
            and not pages.devices.cameras.operation_pending
            and not any(
                camera.connected or camera.capture_running
                for camera in pages.devices.cameras.drafts
            )
            and not pages.devices.projectors.calibration.presentation_active
            and not pages.devices.projectors.calibration.presentation_pending
        )

    def capture(self) -> JSON:
        pages = self.pages
        protocol = capture_protocol(pages.protocol)
        projectors = pages.devices.projectors
        return {
            "format": "cephvr-gui-config",
            "version": 1,
            "experiment": self.experiment.capture(),
            "protocol": protocol,
            "microcontroller": pages.devices.microcontroller.snapshots.capture(),
            "projectors": {
                "configuration": projectors.calibration_files.snapshot(),
                "assignments": dict(projectors.assignments),
                "participation": dict(projectors.participation),
            },
            "spikeglx": pages.devices.spikeglx.snapshots.capture(),
            "tracking": pages.tracking.snapshot(),
        }

    def validate(self, value: Any) -> JSON:
        data = envelope(
            value,
            "cephvr-gui-config",
            {
                "experiment",
                "protocol",
                "microcontroller",
                "projectors",
                "spikeglx",
                "tracking",
            },
        )
        self.experiment.validate(data["experiment"])
        validate_protocol(data["protocol"])
        self.pages.devices.microcontroller.snapshots.validate(data["microcontroller"])
        self.pages.devices.spikeglx.snapshots.validate(data["spikeglx"])
        projectors = fields(
            data["projectors"],
            {"configuration", "assignments", "participation"},
            "Projectors",
        )
        self.pages.devices.projectors.calibration_files.validate(
            projectors["configuration"]
        )
        assignments = validate_assignments(projectors["assignments"])
        if any(
            key not in self.pages.devices.projectors.keys and face != "Unassigned"
            for key, face in assignments.items()
        ):
            raise ValueError(
                "Saved projector display identity is unavailable; refresh/connect the matching rig first"
            )
        participation = fields(
            projectors["participation"], set(assignments), "Display participation"
        )
        for key, item in participation.items():
            boolean(item, key)
        result = dict(data)
        result["tracking"] = self.pages.tracking.validate_snapshot(data["tracking"])
        return result

    def restore(self, data: JSON) -> None:
        pages = self.pages
        self.experiment.restore(data["experiment"])
        restore_protocol(pages.protocol, data["protocol"])
        pages.devices.microcontroller.snapshots.restore(data["microcontroller"])
        projectors = pages.devices.projectors
        projectors.assignments = dict(data["projectors"]["assignments"])
        projectors.participation = dict(data["projectors"]["participation"])
        sync_assignment_controls(projectors.assignments, projectors.projectors)
        projectors.calibration_files.apply_snapshot(data["projectors"]["configuration"])
        projectors.calibration_files.loaded.emit()
        projectors.update_participation()
        pages.devices.spikeglx.snapshots.restore(data["spikeglx"])
        pages.devices.sync_inputs()
        pages.tracking.restore(data["tracking"])
        pages.tracking.config_files.loaded.emit()

    def files(self, parent: QWidget) -> ConfigurationFiles:
        files = ConfigurationFiles(
            parent,
            "GUI",
            "gui-config.json",
            capture=self.capture,
            validate=self.validate,
            apply=self.restore,
            available=self.available,
        )
        files.message.connect(self.pages.dashboard.log_console.appendPlainText)
        return files
