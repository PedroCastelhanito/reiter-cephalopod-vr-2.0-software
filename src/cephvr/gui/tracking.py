"""Controller-managed Tracking configuration and live diagnostic controls."""

import json
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QIODevice, QSaveFile, pyqtSignal
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QStackedWidget, QTabBar

from cephvr.acquisition.v1 import camera_pb2
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.cameras import CamerasPanel
from cephvr.gui.components import Card, StatusColumn, button, combo, field
from cephvr.gui.layouts import ResponsiveColumns, column
from cephvr.gui.notices import FormNotice
from cephvr.gui.tracking_annotation import TrackingAnnotation
from cephvr.gui.tracking_codec import (
    decode_tracking_settings,
    encode_diagnostic_draft,
    encode_tracking_draft,
)
from cephvr.gui.tracking_draft import validated_draft
from cephvr.gui.tracking_forms import TrackingForms
from cephvr.gui.tracking_live import TrackingDiagnosticPresentation
from cephvr.gui.view import DashboardView
from cephvr.tracking.v1 import services_pb2 as tracking_rpc


class TrackingPage(ResponsiveColumns):
    diagnostic_requested = pyqtSignal()
    diagnostic_close_requested = pyqtSignal()
    diagnostic_viewer_requested = pyqtSignal()

    def __init__(self, cameras: CamerasPanel) -> None:
        left, layout = column()
        self.status = StatusColumn("Tracking HUD")
        super().__init__(left, self.status)
        self.cameras = cameras
        self.view = DashboardView()
        self.can_edit = False
        self._diagnostic_locked = False
        self.notice = FormNotice()
        self.notice.setParent(self)
        self.configuration = Card("Tracking configuration")
        row = QHBoxLayout()
        self.source_serial = ""
        self.source_description = "Tracking cam · not assigned"
        self.pipeline = combo(("Water flow", "Fin flow"))
        row.addWidget(field("Pipeline", self.pipeline), 1)
        self.configuration.body.addLayout(row)
        actions = QHBoxLayout()
        self.load_button = button("Load")
        self.save_button = button("Save as")
        self.preview_button = button("Preview")
        self.preview_button.setToolTip(
            "Open the local reference-frame annotation window."
        )
        self.diagnostic_button = button("Live diagnostic")
        self.diagnostic_viewer_button = button("Open viewer")
        self.diagnostic_viewer_button.setEnabled(False)
        self.diagnostic_button.setToolTip(
            "Run selected Tracking diagnostics over the assigned camera preview."
        )
        actions.addWidget(self.load_button)
        actions.addWidget(self.save_button)
        actions.addStretch()
        actions.addWidget(self.diagnostic_button)
        actions.addWidget(self.diagnostic_viewer_button)
        actions.addWidget(self.preview_button)
        self.configuration.body.addLayout(actions)
        layout.addWidget(self.configuration)
        self.tabs = QTabBar()
        for name in ("Preprocessing", "Calibration", "Pose", "Motion"):
            self.tabs.addTab(name)
        self.tabs.setExpanding(True)
        self.tabs.setDrawBase(False)
        layout.addWidget(self.tabs)
        self.forms = TrackingForms()
        self.pages = QStackedWidget()
        self.pages.addWidget(self.forms.preprocessing)
        self.pages.addWidget(self.forms.calibration)
        self.pages.addWidget(self.forms.subject)
        self.pages.addWidget(self.forms.analysis)
        layout.addWidget(self.pages)
        layout.addStretch()
        self.annotation = TrackingAnnotation(self)
        self.annotation.changed.connect(self.update_annotations)
        self.tabs.currentChanged.connect(self.select_tab)
        for toggle in self.forms.stages.values():
            toggle.toggled.connect(lambda _checked: self.annotation.close())
        self.forms.set_reference.clicked.connect(
            lambda: self.open_annotation("Reference points")
        )
        self.forms.clear_reference.clicked.connect(self.clear_reference)
        self.forms.set_manual.clicked.connect(
            lambda: self.open_annotation("Manual pose")
        )
        self.forms.distance_calibration.draw.clicked.connect(
            lambda: self.open_annotation("Distance reference")
        )
        self.forms.distance_calibration.clear.clicked.connect(self.clear_distance)
        self.forms.search_region.changed.connect(
            lambda: self.region_edited("Search region")
        )
        self.forms.preprocessing.region.changed.connect(
            lambda: self.region_edited("Input crop")
        )
        self.forms.distance_calibration.point_editor.changed.connect(
            self.distance_edited
        )
        self.forms.reference_points.changed.connect(
            lambda: self.points_edited("Reference points")
        )
        self.forms.manual_points.changed.connect(
            lambda: self.points_edited("Manual pose")
        )
        self.forms.distance_calibration.distance.setValidator(
            QDoubleValidator(0, 100_000, 4, self)
        )
        self.forms.distance_calibration.distance.textChanged.connect(
            self.forms.distance_calibration.update_scale
        )
        self.preview_button.clicked.connect(self.toggle_preview)
        self.diagnostic_button.clicked.connect(self.request_diagnostic)
        self.diagnostic_viewer_button.clicked.connect(
            self.diagnostic_viewer_requested.emit
        )
        self.forms.method.currentIndexChanged.connect(lambda: self.refit())
        self.forms.quality_button.toggled.connect(lambda: self.refit())
        self.pipeline.currentIndexChanged.connect(self.select_pipeline)
        self.cameras.drafts_changed.connect(self.sync_sources)
        self.load_button.clicked.connect(self.load_settings)
        self.save_button.clicked.connect(self.save_settings)
        self.forms.browse_model.clicked.connect(self.browse_model)
        for key, editor in self.forms.fields.items():
            if key != "model_manifest":
                validator = QDoubleValidator(editor)
                validator.setNotation(QDoubleValidator.Notation.StandardNotation)
                editor.setValidator(validator)
        self.status.console.setPlainText(
            "Waiting for controller Tracking status. Live diagnostics use the assigned camera preview."
        )
        self.sync_sources()
        self.select_tab(0)
        self.pipeline_key = self.pipeline.currentText()
        self.analysis_keys = tuple(
            key
            for key in self.forms.fields
            if key
            not in {
                "threshold",
                "minimum_area",
                "maximum_area",
                "model_manifest",
                "candidate_score",
                "landmark_score",
                "anisotropy",
                "axis_length",
                "base_width",
                "triangle_area",
            }
        )
        self.analysis_drafts = {
            name: {key: self.forms.fields[key].text() for key in self.analysis_keys}
            for name in ("Water flow", "Fin flow")
        }

    def sync_sources(self) -> None:
        assigned = [
            camera for camera in self.cameras.drafts if camera.role == "Tracking cam"
        ]
        serial = assigned[0].serial if len(assigned) == 1 else ""
        self.source_description = (
            f"Tracking cam · {serial}"
            + (" · disabled" if not assigned[0].enabled else "")
            if serial
            else "Tracking cam · not uniquely assigned"
        )
        if serial != self.source_serial:
            self.source_serial = serial
            self.annotation.reset()
            self.clear_spatial()
            self.status.console.appendPlainText(
                "Tracking camera changed; spatial calibration and regions cleared."
            )
        if hasattr(self, "view"):
            self.apply_view(self.view)

    def clear_spatial(self) -> None:
        self.forms.distance_calibration.distance.clear()
        self.forms.distance_calibration.set_points([])
        self.forms.search_region.set_values([0, 0, 0, 0])
        self.forms.preprocessing.region.set_values([0, 0, 0, 0])

    def region_edited(self, mode: str) -> None:
        editor = (
            self.forms.search_region
            if mode == "Search region"
            else self.forms.preprocessing.region
        )
        self.annotation.canvas.points[mode] = editor.corners()
        self.annotation.canvas.update()

    def distance_edited(self) -> None:
        points = self.forms.distance_calibration.point_editor.points()
        if points is not None:
            self.annotation.canvas.points["Distance reference"] = points
        self.forms.distance_calibration.update_scale()
        self.annotation.canvas.update()

    def points_edited(self, mode: str) -> None:
        editor = (
            self.forms.reference_points
            if mode == "Reference points"
            else self.forms.manual_points
        )
        points = editor.points()
        if points is not None:
            self.annotation.canvas.points[mode] = points
            self.annotation.canvas.update()
            self.update_annotations()

    def clear_reference(self) -> None:
        self.annotation.canvas.points["Reference points"] = []
        if self.annotation.canvas.mode == "Reference points":
            self.annotation.canvas.index = 0
            self.annotation.point.setCurrentIndex(0)
        self.update_annotations()
        self.annotation.canvas.update()

    def clear_distance(self) -> None:
        self.annotation.canvas.points["Distance reference"] = []
        self.forms.distance_calibration.set_points([])
        self.annotation.canvas.update()

    def select_pipeline(self, index: int) -> None:
        if hasattr(self, "analysis_drafts"):
            self.analysis_drafts[self.pipeline_key] = {
                key: self.forms.fields[key].text() for key in self.analysis_keys
            }
            self.pipeline_key = self.pipeline.currentText()
            for key, value in self.analysis_drafts[self.pipeline_key].items():
                self.forms.fields[key].setText(value)
        self.forms.fin.setVisible(index == 1)
        self.refit()

    def select_tab(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.refit()

    def refit(self) -> None:
        page = self.pages.currentWidget()
        if page is not None:
            layout = page.layout()
            assert layout is not None
            layout.activate()
            self.pages.setMinimumHeight(page.minimumSizeHint().height())
            self.pages.setMaximumHeight(page.sizeHint().height())

    def open_annotation(self, mode: str) -> None:
        if self.can_edit and not self._diagnostic_locked:
            self.annotation.open_mode(mode)

    def freeze_diagnostic_frame(
        self, presentation: TrackingDiagnosticPresentation, *, camera_serial: str
    ) -> None:
        """Install an explicitly selected exact-source image into local annotations."""
        if (
            not self.can_edit
            or not camera_serial
            or camera_serial != self.source_serial
        ):
            raise ValueError(
                "The assigned Tracking camera changed; refresh the diagnostic."
            )
        self.annotation.install_acquired_source(
            presentation.image,
            camera_serial=camera_serial,
            configuration_revision=presentation.configuration_revision,
            preview_run_id=presentation.preview_run_id,
            source_frame_id=presentation.source_frame_id,
            source_host_receipt_ns=presentation.source_host_receipt_ns,
        )
        if not self._diagnostic_locked:
            self.annotation.open_mode("Reference points")

    def request_diagnostic(self) -> None:
        if not self.diagnostic_button.isEnabled():
            return
        if self.diagnostic_button.text() == "Stop diagnostic":
            self.diagnostic_close_requested.emit()
        else:
            self.diagnostic_requested.emit()

    def install_diagnostic_status(
        self,
        *,
        active: bool,
        pending: bool,
        message: str,
        last_duration_ns: int | None = None,
        maximum_duration_ns: int | None = None,
        can_begin: bool = True,
        can_close: bool = False,
        viewer_available: bool = False,
        pending_label: str = "Starting diagnostic…",
    ) -> None:
        self.diagnostic_button.setText(
            "Stop diagnostic" if active else "Live diagnostic"
        )
        if pending:
            self.diagnostic_button.setText(pending_label)
        if active and not can_close:
            self.diagnostic_button.setText("Diagnostic active")
        self.diagnostic_button.setEnabled(
            (active and can_close and not pending) or can_begin
        )
        self._diagnostic_locked = active or pending
        self.configuration.setEnabled(self.can_edit)
        for control in (
            self.pipeline,
            self.load_button,
            self.save_button,
            self.preview_button,
        ):
            control.setEnabled(self.can_edit and not self._diagnostic_locked)
        self.pages.setEnabled(self.can_edit and not self._diagnostic_locked)
        self.annotation.setEnabled(self.can_edit and not self._diagnostic_locked)
        self.diagnostic_viewer_button.setEnabled(viewer_available)
        timings = ""
        if last_duration_ns is not None and maximum_duration_ns is not None:
            timings = (
                f"\nLAST      {last_duration_ns / 1_000_000:.2f} ms"
                f"\nMAX       {maximum_duration_ns / 1_000_000:.2f} ms"
            )
        self.status.hud.setPlainText(
            f"INPUT     {self.source_description}\n"
            f"TRACKING  {self.view.tracking_status}\n"
            f"DIAGNOSTIC {message}{timings}"
        )

    def toggle_preview(self) -> None:
        if self.annotation.isVisible():
            self.annotation.close()
        else:
            self.open_annotation("Reference points")

    def update_annotations(self) -> None:
        points = self.annotation.canvas.points
        self.forms.reference_points.set_points(points["Reference points"])
        self.forms.manual_points.set_points(points["Manual pose"])
        self.forms.manual_status.setText(
            f"{len(points['Manual pose'])} / 3 mantle landmarks"
        )
        self.forms.search_region.set_corners(points["Search region"])
        self.forms.preprocessing.region.set_corners(points["Input crop"])
        self.forms.distance_calibration.set_points(points["Distance reference"])
        region = points["Search region"]
        self.forms.search_status.setText(
            f"{region[1][0] - region[0][0]:g} × {region[1][1] - region[0][1]:g} px"
            if len(region) == 2
            else "Not set"
        )
        self.refit()

    def apply_view(self, view: DashboardView) -> None:
        self.view = view
        self.can_edit = view.can_edit
        self.configuration.setEnabled(self.can_edit)
        self.pages.setEnabled(self.can_edit and not self._diagnostic_locked)
        self.status.hud.setPlainText(
            f"INPUT     {self.source_description}\nTRACKING  {view.tracking_status}\nPOSE      —\nCOVERAGE  —\nRESULT AGE  —"
        )
        if not self.can_edit:
            self.annotation.close()
        self.diagnostic_button.setEnabled(view.can_edit and bool(self.source_serial))
        for control in (
            self.pipeline,
            self.load_button,
            self.save_button,
            self.preview_button,
        ):
            control.setEnabled(self.can_edit and not self._diagnostic_locked)
        self.annotation.setEnabled(self.can_edit and not self._diagnostic_locked)
        self.notice.setEnabled(self.can_edit)

    def browse_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Model manifest", "", "Model manifest (*.json)"
        )
        if path and self.can_edit:
            self.forms.model_path.setText(path)

    def snapshot(self) -> dict[str, Any]:
        self.analysis_drafts[self.pipeline_key] = {
            key: self.forms.fields[key].text() for key in self.analysis_keys
        }
        return {
            "format": "cephvr-tracking-ui-draft",
            "version": 4,
            "diagnostics": {
                key: toggle.isChecked() for key, toggle in self.forms.stages.items()
            },
            "camera": self.source_serial,
            "preprocessing": {
                "crop_enabled": self.forms.preprocessing.enabled.isChecked(),
                "scale_percent": self.forms.preprocessing.scale.value(),
                "region": self.forms.preprocessing.region.values(),
            },
            "distance_mm": self.forms.distance_calibration.distance.text(),
            "pipeline": self.pipeline.currentText(),
            "fields": {key: editor.text() for key, editor in self.forms.fields.items()},
            "choices": {
                key: editor.currentText() for key, editor in self.forms.choices.items()
            },
            "analysis_drafts": json.loads(json.dumps(self.analysis_drafts)),
            "annotations": json.loads(json.dumps(self.annotation.canvas.points)),
            "image_size": list(self.annotation.image_size),
            "annotation_source": (
                None
                if self.annotation.source_lineage is None
                else dict(self.annotation.source_lineage)
            ),
        }

    def configuration_for_submit(
        self, current: pb.TrackingSettings, *, asset_root: str = ""
    ) -> pb.TrackingSettings:
        """Build typed experiment settings without applying diagnostic switches."""
        return encode_tracking_draft(current, self.snapshot(), asset_root=asset_root)

    def diagnostic_configuration(
        self, current: pb.TrackingSettings, *, asset_root: str = ""
    ) -> tuple[pb.TrackingSettings, tuple[int, ...]]:
        """Freeze the visible draft and independent diagnostic stage mask."""
        names = (
            "pose",
            "sampling_region",
            "optical_flow",
            "flow_quality",
            "locomotion",
        )
        stage_values = (
            tracking_rpc.TRACKING_DIAGNOSTIC_STAGE_POSE,
            tracking_rpc.TRACKING_DIAGNOSTIC_STAGE_SAMPLING_REGION,
            tracking_rpc.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW,
            tracking_rpc.TRACKING_DIAGNOSTIC_STAGE_FLOW_QUALITY,
            tracking_rpc.TRACKING_DIAGNOSTIC_STAGE_LOCOMOTION,
        )
        selected = tuple(
            stage
            for name, stage in zip(names, stage_values, strict=True)
            if self.forms.stages[name].isChecked()
        )
        return (
            encode_diagnostic_draft(
                current, self.snapshot(), selected, asset_root=asset_root
            ),
            selected,
        )

    def install_configuration(
        self, settings: pb.TrackingSettings, *, source_serial: str
    ) -> None:
        """Install authoritative settings only for the currently assigned source."""
        self.restore(self.configuration_draft(settings, source_serial=source_serial))

    def configuration_draft(
        self, settings: pb.TrackingSettings, *, source_serial: str
    ) -> dict[str, Any]:
        """Validate a saved submessage before any other page is changed."""
        if not source_serial or source_serial != self.source_serial:
            raise ValueError(
                "Tracking source changed; refresh before loading settings."
            )
        if (
            settings.HasField("input_camera_role")
            and settings.input_camera_role != camera_pb2.CAMERA_ROLE_TRACKING
        ):
            raise ValueError(
                "These Tracking controls require the assigned Tracking camera."
            )
        return decode_tracking_settings(settings, camera_serial=source_serial)

    def restore(self, data: dict[str, Any]) -> None:
        """Validate the entire draft before changing any visible value."""
        data = validated_draft(
            data,
            set(self.forms.fields),
            {
                key: tuple(editor.itemText(index) for index in range(editor.count()))
                for key, editor in self.forms.choices.items()
            },
            self.analysis_keys,
        )
        fields, choices, points = data["fields"], data["choices"], data["annotations"]
        analysis, size = data["analysis_drafts"], data["image_size"]
        self.pipeline.setCurrentText(data["pipeline"])
        for key, value in fields.items():
            self.forms.fields[key].setText(value)
        for key, value in choices.items():
            self.forms.choices[key].setCurrentText(value)
        self.analysis_drafts = json.loads(json.dumps(analysis))
        self.annotation.reset()
        # Image pixels are not embedded in settings; annotations retain their source size.
        self.annotation.canvas.points = json.loads(json.dumps(points))
        self.annotation.image_size = size
        self.annotation.source_lineage = data["annotation_source"]
        self.forms.preprocessing.enabled.setChecked(
            data["preprocessing"]["crop_enabled"]
        )
        self.forms.preprocessing.scale.setValue(data["preprocessing"]["scale_percent"])
        self.forms.distance_calibration.distance.setText(data["distance_mm"])
        for key, enabled in data["diagnostics"].items():
            self.forms.stages[key].setChecked(enabled)
        self.update_annotations()
        if data["camera"] and data["camera"] != self.source_serial:
            self.annotation.reset()
            self.clear_spatial()
            self.status.console.appendPlainText(
                "Loaded settings; spatial annotations cleared because the Tracking camera differs."
            )

    def save_settings(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Tracking draft", "tracking.json", "Tracking draft (*.json)"
        )
        if not path or not self.can_edit:
            return
        try:
            data = self.snapshot()
            output = QSaveFile(path)
            if not output.open(QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(output.errorString())
            payload = json.dumps(data, indent=2).encode()
            if output.write(payload) != len(payload) or not output.commit():
                raise OSError(output.errorString())
            self.status.console.appendPlainText(f"Saved Tracking draft: {path}")
        except (OSError, ValueError) as error:
            self.notice.warn(error, "Tracking settings")

    def load_settings(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Tracking draft", "", "Tracking draft (*.json)"
        )
        if not path or not self.can_edit:
            return
        try:
            if Path(path).stat().st_size > 1_000_000:
                raise ValueError("Tracking draft exceeds 1 MB.")
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Expected a Tracking draft object.")
            self.restore(data)
            self.status.console.appendPlainText(f"Loaded Tracking draft: {path}")
        except (OSError, ValueError) as error:
            self.notice.warn(error, "Tracking settings")
