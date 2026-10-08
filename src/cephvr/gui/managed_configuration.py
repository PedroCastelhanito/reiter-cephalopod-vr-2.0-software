"""Atomic managed-session configuration install and candidate collection."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDial,
    QLineEdit,
    QSlider,
)

from cephvr.acquisition.v1 import camera_pb2
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.camera_snapshot_settings import collect_camera_snapshot
from cephvr.gui.managed_config import (
    install_metadata,
    install_subject_metadata,
    subject_metadata_from_fields,
)
from cephvr.visual_stimulus.v1 import runtime_pb2 as visual_stimulus_pb


@dataclass(frozen=True)
class ConfigurationPages:
    dashboard: Any
    protocol: Any
    recordings: Any
    cameras: Any
    projectors: Any
    tracking: Any
    microcontroller: Any = None


class ManagedConfiguration:
    """Own UI/base identity; drafts are never silently rebased."""

    def __init__(self, pages: ConfigurationPages) -> None:
        self.pages = pages
        self.generation = ""
        self.revision: int | None = None
        self.stale = False
        self.last_error = ""
        self.dirty = False
        self.tracking_dirty = False
        self.edit_serial = 0
        self._installing = False
        self._installed_base = pb.ExperimentConfiguration()
        self._watch_edits()

    @contextmanager
    def installing_projection(self) -> Iterator[None]:
        """Authoritative device projection cannot masquerade as a local edit."""
        previous = self._installing
        self._installing = True
        try:
            yield
        finally:
            self._installing = previous

    def _watch_edits(self) -> None:
        def changed(*_args: Any) -> None:
            if not self._installing:
                self.edit_serial += 1
                self.dirty = True

        def tracking_changed(*_args: Any) -> None:
            if not self._installing:
                changed()
                self.tracking_dirty = True

        for page in (
            self.pages.dashboard,
            self.pages.protocol,
            self.pages.recordings,
            self.pages.projectors,
            self.pages.tracking,
        ):
            handler = tracking_changed if page is self.pages.tracking else changed
            for editor in page.findChildren(QLineEdit):
                editor.textEdited.connect(handler)
            for control in page.findChildren(QComboBox):
                control.currentTextChanged.connect(handler)
            for control in page.findChildren(QCheckBox):
                control.toggled.connect(handler)
            for control in page.findChildren(QAbstractSpinBox):
                control.valueChanged.connect(handler)
            for control_type in (QSlider, QDial):
                for control in page.findChildren(control_type):
                    control.valueChanged.connect(handler)
        self.pages.protocol.editor.changed.connect(changed)
        self.pages.recordings.changed.connect(changed)
        self.pages.projectors.outputs_changed.connect(changed)
        self.pages.protocol.config_files.loaded.connect(changed)
        self.pages.projectors.calibration_files.loaded.connect(changed)
        self.pages.tracking.config_files.loaded.connect(tracking_changed)
        if self.pages.microcontroller is not None:
            self.pages.microcontroller.config_files.loaded.connect(changed)
        for signal_name in (
            "points_changed",
            "distance_changed",
            "annotations_changed",
            "spatial_changed",
        ):
            signal = getattr(self.pages.tracking, signal_name, None)
            if signal is not None and hasattr(signal, "connect"):
                signal.connect(tracking_changed)
        self.pages.tracking.annotation.changed.connect(tracking_changed)
        self.pages.tracking.forms.search_region.changed.connect(tracking_changed)
        self.pages.tracking.forms.preprocessing.region.changed.connect(tracking_changed)
        self.pages.tracking.forms.reference_points.changed.connect(tracking_changed)
        self.pages.tracking.forms.manual_points.changed.connect(tracking_changed)
        self.pages.tracking.forms.distance_calibration.point_editor.changed.connect(
            tracking_changed
        )
        self.pages.tracking.forms.distance_calibration.distance.textChanged.connect(
            tracking_changed
        )

    @staticmethod
    def _base(snapshot: pb.Snapshot) -> pb.ExperimentConfiguration:
        if not snapshot.HasField("configuration_values"):
            raise ValueError(
                "Controller has not supplied an authoritative configuration"
            )
        values = snapshot.configuration_values
        if values.revision != snapshot.configuration.revision:
            raise ValueError("Controller configuration revision is not synchronized")
        return values.current

    @staticmethod
    def _backend(
        base: pb.ExperimentConfiguration, name: str
    ) -> pb.BackendSettings | None:
        matches = [item for item in base.backends if item.backend_name == name]
        if len(matches) > 1:
            raise ValueError(f"Configuration contains duplicate {name} backends")
        return matches[0] if matches else None

    def install(self, snapshot: pb.Snapshot, *, force: bool = False) -> bool:
        base = self._base(snapshot)
        generation = snapshot.controller_generation
        revision = snapshot.configuration.revision
        if self.generation == generation and self.revision == revision and not force:
            return not self.stale
        if self.generation and not force and self.dirty:
            self.stale = True
            self.last_error = (
                "Controller configuration changed while local edits existed. "
                "Reload the controller configuration before submitting."
            )
            return False

        stimulus_backend = self._backend(base, "visual_stimulus")
        acquisition_backend = self._backend(base, "acquisition")
        tracking_backend = self._backend(base, "tracking")
        tracking = (
            tracking_backend.tracking
            if tracking_backend is not None and tracking_backend.HasField("tracking")
            else None
        )
        serial = self._tracking_serial()
        if tracking is not None and serial:
            # Decode before touching any widget so an incomplete or invalid Tracking
            # submessage cannot leave the other pages half-installed.
            self.pages.tracking.configuration_draft(tracking, source_serial=serial)

        self._installing = True
        self.pages.cameras.snapshot_draft = False
        self.pages.tracking.snapshot_draft = False
        if self.pages.microcontroller is not None:
            self.pages.microcontroller.snapshots.draft_loaded = False
        dashboard = self.pages.dashboard
        self.pages.protocol.install_configuration(base)
        self.pages.projectors.asset_root = (
            base.asset_root if base.HasField("asset_root") else ""
        )
        install_subject_metadata(dashboard, base)
        stimulus = (
            stimulus_backend.visual_stimulus
            if stimulus_backend is not None
            and stimulus_backend.HasField("visual_stimulus")
            else None
        )
        acquisition = (
            acquisition_backend.acquisition
            if acquisition_backend is not None
            and acquisition_backend.HasField("acquisition")
            else None
        )
        tracking = (
            tracking_backend.tracking
            if tracking_backend is not None and tracking_backend.HasField("tracking")
            else None
        )
        recording_values: dict[str, bool | None] = {
            key: None for key in self.pages.recordings.record
        }
        if stimulus is not None and stimulus.HasField("save_visual_stimulus_data"):
            recording_values["stimulus"] = stimulus.save_visual_stimulus_data
        if acquisition is not None:
            for camera in self.pages.cameras.drafts:
                role = camera.role.casefold()
                target = (
                    acquisition.behavioral
                    if "behavior" in role
                    else acquisition.tracking
                    if "tracking" in role
                    else None
                )
                if target is not None and target.HasField("save_video"):
                    recording_values[camera.key] = target.save_video
        if tracking is not None and tracking.HasField("save_tracking_data"):
            recording_values["velocities"] = tracking.save_tracking_data
        self.pages.recordings.install_values(recording_values)
        display = (
            stimulus.display
            if stimulus is not None and stimulus.HasField("display")
            else None
        )
        self.pages.projectors.install_configuration(
            display
            if display is not None
            else visual_stimulus_pb.DisplayConfiguration()
        )
        restored_assignments = (
            not self.generation
            and snapshot.session.phase
            in (pb.SESSION_PHASE_CONFIGURATION, pb.SESSION_PHASE_READY)
            and self.pages.projectors.restore_assignment_draft()
        )
        if tracking is not None and serial:
            self.pages.tracking.install_configuration(tracking, source_serial=serial)
        self.generation, self.revision = generation, revision
        self._installed_base.CopyFrom(base)
        self.stale = False
        self.last_error = ""
        self.dirty = bool(restored_assignments)
        self.tracking_dirty = False
        self._installing = False
        return True

    def _tracking_serial(self) -> str:
        matches = [
            camera.serial
            for camera in self.pages.cameras.drafts
            if "tracking" in camera.role.casefold() and camera.serial
        ]
        return matches[0] if len(matches) == 1 else ""

    def collect(
        self, base: pb.ExperimentConfiguration, *, flush: bool = True
    ) -> pb.ExperimentConfiguration:
        candidate = pb.ExperimentConfiguration()
        candidate.CopyFrom(base)
        dashboard = self.pages.dashboard
        candidate.subject = dashboard.subject_id.text().strip()
        candidate.experiment = dashboard.experiment.text().strip()
        candidate.recording_root = dashboard.output_root.text().strip()
        install_metadata(candidate, subject_metadata_from_fields(dashboard))
        self.pages.protocol.apply_schedule(candidate, flush_parameters=flush)

        stimulus_backend = self._backend(candidate, "visual_stimulus")
        if stimulus_backend is None:
            stimulus_backend = candidate.backends.add(
                backend_name="visual_stimulus", enabled=True
            )
        elif stimulus_backend.WhichOneof("settings") not in (None, "visual_stimulus"):
            raise ValueError("Visual Stimulus backend has incompatible settings")
        stimulus_backend.enabled = True
        if not stimulus_backend.HasField("visual_stimulus"):
            stimulus_backend.visual_stimulus.SetInParent()
        settings = stimulus_backend.visual_stimulus
        if not settings.HasField("display"):
            settings.display.SetInParent()
        updated = self.pages.projectors.configuration_for_submit(settings.display)
        settings.display.CopyFrom(updated)
        if "stimulus" in self.pages.recordings.touched:
            settings.save_visual_stimulus_data = self.pages.recordings.record[
                "stimulus"
            ].isChecked()

        acquisition_backend = self._backend(candidate, "acquisition")
        if acquisition_backend is None and (
            self.pages.cameras.snapshot_draft
            or self.pages.microcontroller is not None
            and self.pages.microcontroller.snapshots.draft_loaded
        ):
            raise ValueError(
                "Acquisition settings are unavailable for the loaded device draft"
            )
        if acquisition_backend is not None:
            acquisition = acquisition_backend.acquisition
            collect_camera_snapshot(self.pages.cameras, acquisition)
            if self.pages.cameras.snapshot_draft and any(
                camera.enabled and camera.role != "Unassigned"
                for camera in self.pages.cameras.drafts
            ):
                acquisition_backend.enabled = True
            if self.pages.microcontroller is not None:
                self.pages.microcontroller.snapshots.collect(acquisition)
            for camera in self.pages.cameras.drafts:
                if camera.key not in self.pages.recordings.touched:
                    continue
                role = camera.role.casefold()
                target = (
                    acquisition.behavioral
                    if "behavior" in role
                    else acquisition.tracking
                    if "tracking" in role
                    else None
                )
                if target is not None:
                    target.save_video = self.pages.recordings.record[
                        camera.key
                    ].isChecked()

        tracking_backend = self._backend(candidate, "tracking")
        tracking_required = self.pages.protocol.tracking_active
        if tracking_backend is None and (
            tracking_required
            or self.tracking_dirty
            or "velocities" in self.pages.recordings.touched
        ):
            tracking_backend = candidate.backends.add(backend_name="tracking")
        elif tracking_backend is not None and tracking_backend.WhichOneof(
            "settings"
        ) not in (None, "tracking"):
            raise ValueError("Tracking backend has incompatible settings")
        if tracking_backend is not None and (
            tracking_backend.HasField("tracking")
            or tracking_required
            or self.tracking_dirty
            or "velocities" in self.pages.recordings.touched
        ):
            if not tracking_backend.HasField("tracking"):
                tracking_backend.tracking.SetInParent()
            tracking_settings = tracking_backend.tracking
            if "velocities" in self.pages.recordings.touched:
                tracking_settings.save_tracking_data = (
                    self.pages.recordings.velocities.isChecked()
                )
            serial = self._tracking_serial()
            tracking_participates = tracking_required or (
                tracking_settings.HasField("save_tracking_data")
                and tracking_settings.save_tracking_data
            )
            if tracking_participates:
                if not serial:
                    raise ValueError(
                        "Assign a Tracking camera before enabling Tracking participation"
                    )
                if not tracking_settings.HasField("input_camera_role"):
                    tracking_settings.input_camera_role = (
                        camera_pb2.CAMERA_ROLE_TRACKING
                    )
                elif (
                    tracking_settings.input_camera_role
                    != camera_pb2.CAMERA_ROLE_TRACKING
                ):
                    raise ValueError(
                        "Tracking settings must use the assigned Tracking camera role"
                    )
            submit_tracking = (
                (self.tracking_dirty or self.pages.tracking.snapshot_draft)
                and tracking_participates
                or self.tracking_dirty
                and not self.pages.tracking.snapshot_draft
            )
            if submit_tracking and not serial:
                raise ValueError(
                    "Assign a Tracking camera before submitting Tracking edits"
                )
            if submit_tracking:
                updated = self.pages.tracking.configuration_for_submit(
                    tracking_settings,
                    asset_root=(
                        candidate.asset_root if candidate.HasField("asset_root") else ""
                    ),
                )
                tracking_settings.CopyFrom(updated)
            tracking_backend.enabled = bool(
                tracking_required
                or (
                    tracking_settings.HasField("save_tracking_data")
                    and tracking_settings.save_tracking_data
                )
            )
        return candidate

    def note_installed_revision(
        self, snapshot: pb.Snapshot, *, submitted_edit_serial: int
    ) -> None:
        """Adopt the result while preserving every edit made after collection."""
        accepted = self._base(snapshot)
        matches = self.edit_serial == submitted_edit_serial
        self.generation = snapshot.controller_generation
        self.revision = snapshot.configuration.revision
        self._installed_base.CopyFrom(accepted)
        self.stale = not matches
        self.dirty = not matches
        if matches:
            self.tracking_dirty = False
            accepted_tracking = self._backend(accepted, "tracking")
            if accepted_tracking is not None and accepted_tracking.enabled:
                self.pages.tracking.snapshot_draft = False
            self.pages.cameras.snapshot_draft = False
            if self.pages.microcontroller is not None:
                self.pages.microcontroller.snapshots.draft_loaded = False
            self.pages.recordings.touched.clear()
        self.last_error = (
            ""
            if matches
            else (
                "The controller accepted an earlier draft while newer local edits remained. "
                "Reload before submitting again."
            )
        )

    def reload(self, snapshot: pb.Snapshot) -> bool:
        return self.install(snapshot, force=True)
