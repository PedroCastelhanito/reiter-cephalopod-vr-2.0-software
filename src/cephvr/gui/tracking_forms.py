"""Method-specific Tracking forms; values are frontend drafts until integrated."""

from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLayout,
    QLineEdit,
    QVBoxLayout,
)

from cephvr.gui.components import Card, button, combo, equal_row_height, field, label
from cephvr.gui.layouts import column
from cephvr.gui.paths import PathEdit
from cephvr.gui.theme import SIZES
from cephvr.gui.tracking_annotation import POINTS
from cephvr.gui.tracking_spatial import (
    DistanceCalibration,
    PointEditor,
    PreprocessingPage,
    RegionEditor,
)
from cephvr.gui.tracking_stages import StageCard


class TrackingForms:
    """Own stable controls so switching methods never discards their drafts."""

    def __init__(self) -> None:
        self.fields: dict[str, QLineEdit] = {}
        self.choices = {}
        self.subject, subject_layout = column()
        self.reference = Card("Subject reference")
        self.set_reference = button("Set points")
        row = QHBoxLayout()
        row.addWidget(self.set_reference)
        self.clear_reference = button("Clear")
        row.addWidget(self.clear_reference)
        row.addStretch()
        self.reference.body.addLayout(row)
        self.reference_points = PointEditor(POINTS["Reference points"])
        self.reference.body.addWidget(self.reference_points)
        subject_layout.addWidget(self.reference)
        self.pose = StageCard("Pose detection")
        self.method = combo(("Threshold + contour", "Keypoint model", "Manual"))
        self.choices["pose_method"] = self.method
        self.pose.body.addWidget(field("Method", self.method))
        self.pose_pages, pose_layout = column()
        self.method_pages = []
        self.threshold, _ = column()
        self.threshold_grid = self.grid(self.threshold.layout())
        self.add(self.threshold_grid, "threshold", "Threshold", "Required", 0, 0)
        self.polarity = combo(("Dark subject", "Bright subject"))
        self.choices["polarity"] = self.polarity
        self.threshold_grid.addWidget(field("Foreground", self.polarity), 0, 1)
        self.add(
            self.threshold_grid, "minimum_area", "Minimum area (px²)", "Required", 1, 0
        )
        self.add(
            self.threshold_grid, "maximum_area", "Maximum area (px²)", "Required", 1, 1
        )
        self.method_pages.append(self.threshold)
        pose_layout.addWidget(self.threshold)
        self.model, model_layout = column()
        self.model_path = PathEdit(filename_only=True)
        self.model_path.setPlaceholderText("Select model manifest")
        self.fields["model_manifest"] = self.model_path
        self.browse_model = button("Browse")
        path_row = QHBoxLayout()
        path_row.addWidget(self.model_path, 1)
        path_row.addWidget(self.browse_model)
        equal_row_height(self.model_path, self.browse_model)
        model_layout.addLayout(path_row)
        model_grid = self.grid(model_layout)
        self.add(
            model_grid, "candidate_score", "Candidate confidence", "Required", 0, 0
        )
        self.add(model_grid, "landmark_score", "Landmark confidence", "Required", 0, 1)
        self.method_pages.append(self.model)
        pose_layout.addWidget(self.model)
        manual, manual_layout = column()
        self.manual_status = label("0 / 3 mantle landmarks")
        self.set_manual = button("Set landmarks")
        row = QHBoxLayout()
        row.addWidget(self.set_manual)
        row.addStretch()
        row.addWidget(self.manual_status)
        manual_layout.addLayout(row)
        self.manual_points = PointEditor(POINTS["Manual pose"])
        manual_layout.addWidget(self.manual_points)
        self.method_pages.append(manual)
        pose_layout.addWidget(manual)
        self.pose.body.addWidget(self.pose_pages)
        self.quality_button = button("Pose quality settings")
        self.quality_button.setCheckable(True)
        self.quality, quality_layout = column()
        quality_grid = self.grid(quality_layout)
        for index, (key, title) in enumerate(
            (
                ("anisotropy", "Minimum axis anisotropy"),
                ("axis_length", "Minimum axis (px)"),
                ("base_width", "Minimum base width (px)"),
                ("triangle_area", "Minimum triangle area (px²)"),
            )
        ):
            self.add(quality_grid, key, title, "Required", index // 2, index % 2)
        self.quality.hide()
        self.quality_button.toggled.connect(self.quality.setVisible)
        self.pose.body.addWidget(self.quality_button)
        self.pose.body.addWidget(self.quality)
        subject_layout.addWidget(self.pose)
        self.search = Card("Search region")
        self.pose.enabled.toggled.connect(self.search.setEnabled)
        row = QHBoxLayout()
        self.search_status = label("Not set", wrap=True)
        row.addWidget(self.search_status, 1)
        self.search.body.addLayout(row)
        self.search_region = RegionEditor()
        self.search.body.addWidget(self.search_region)
        subject_layout.insertWidget(subject_layout.indexOf(self.pose), self.search)
        subject_layout.addStretch()
        self.method.currentIndexChanged.connect(self.select_method)
        self.method.setCurrentText("Manual")

        self.analysis, analysis_layout = column()
        self.region = StageCard("Sampling region")
        grid = self.grid(self.region.body)
        for index, (key, title, value) in enumerate(
            (
                ("front_fraction", "Front fraction", "0.60"),
                ("taper", "Taper", "0.4"),
                ("squareness", "Squareness", "3.5"),
                ("sections", "Sections", "12"),
                ("inner_clearance", "Inner clearance", "0.1"),
                ("outer_extent", "Outer extent", "0.75"),
            )
        ):
            self.add(grid, key, title, value, index // 2, index % 2, default=True)
        for key in ("inner_clearance", "outer_extent"):
            self.fields[key].setToolTip(
                "Fraction of the separation between the anterior mantle landmarks."
            )
        self.fin, fin_layout = column()
        fin_grid = self.grid(fin_layout)
        self.add(fin_grid, "fin_offset", "Fin angle (°)", "Required", 0, 0)
        self.add(fin_grid, "fin_span", "Fin span (°)", "Required", 0, 1)
        self.region.body.addWidget(self.fin)
        self.fin.hide()
        analysis_layout.addWidget(self.region)
        self.response = StageCard("Locomotion estimate")
        grid = self.grid(self.response.body)
        self.add(grid, "smoothing", "Smoothing (s)", "0.08", 0, 0, default=True)
        self.add(grid, "coverage", "Minimum coverage", "0.25", 0, 1, default=True)
        self.fields["coverage"].setToolTip(
            "Accepted flow area / intended area, required in every section (0–1)."
        )
        analysis_layout.addWidget(self.response)
        self.advanced = StageCard("Flow quality")
        self.advanced_body, advanced_layout = column()
        grid = self.grid(advanced_layout)
        self.flow_grid = combo(("1 px", "2 px", "4 px"))
        self.flow_grid.setCurrentIndex(2)
        self.preset = combo(("Slow", "Medium", "Fast"))
        self.choices.update(flow_grid=self.flow_grid, flow_preset=self.preset)
        self.optical_flow = StageCard("Optical flow")
        self.flow_method = QLineEdit("NVIDIA OF")
        self.flow_method.setReadOnly(True)
        self.flow_method.setToolTip(
            "NVIDIA Optical Flow is the supported flow backend."
        )
        self.optical_flow.body.addWidget(field("Method", self.flow_method))
        flow_grid = self.grid(self.optical_flow.body)
        flow_grid.addWidget(field("Flow grid", self.flow_grid), 0, 0)
        flow_grid.addWidget(field("Performance preset", self.preset), 0, 1)
        analysis_layout.insertWidget(0, self.optical_flow)
        for index, (key, title, value) in enumerate(
            (
                ("minimum_neighbors", "Minimum neighbours", "4"),
                ("radius", "Neighbour radius (cells)", "1"),
                ("noise_floor", "Noise floor (px)", "0.1"),
                ("residual", "Maximum residual", "2.0"),
            )
        ):
            self.add(
                grid,
                key,
                title,
                value or "Required",
                index // 2,
                index % 2,
                default=bool(value),
            )
        self.advanced.body.addWidget(self.advanced_body)
        analysis_layout.addWidget(self.advanced)
        analysis_layout.addStretch()

        self.preprocessing = PreprocessingPage()
        self.stages = {
            "pose": self.pose.enabled,
            "sampling_region": self.region.enabled,
            "optical_flow": self.optical_flow.enabled,
            "flow_quality": self.advanced.enabled,
            "locomotion": self.response.enabled,
        }
        self.calibration, calibration_layout = column()
        self.distance_calibration = DistanceCalibration()
        subject_layout.removeWidget(self.reference)
        calibration_layout.addWidget(self.reference)
        calibration_layout.addWidget(self.distance_calibration)
        calibration_layout.addStretch()
        analysis_layout.removeWidget(self.region)
        subject_layout.insertWidget(subject_layout.count() - 1, self.region)

    @staticmethod
    def grid(layout: QLayout | None) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(SIZES.field_x_gap)
        grid.setVerticalSpacing(SIZES.field_y_gap)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        assert isinstance(layout, QVBoxLayout)
        layout.addLayout(grid)
        return grid

    def add(
        self,
        grid: QGridLayout,
        key: str,
        title: str,
        value: str,
        row: int,
        col: int,
        *,
        default: bool = False,
    ) -> None:
        editor = QLineEdit()
        if default:
            editor.setText(value)
        else:
            editor.setPlaceholderText(value)
        self.fields[key] = editor
        grid.addWidget(field(title, editor), row, col)

    def select_method(self, index: int) -> None:
        for number, page in enumerate(self.method_pages):
            page.setVisible(number == index)
        self.search.setVisible(index != 2)
        self.quality_button.setVisible(index != 2)
        self.quality.setVisible(index != 2 and self.quality_button.isChecked())
        anisotropy = self.fields["anisotropy"].parentWidget()
        assert anisotropy is not None
        anisotropy.setVisible(index == 0)
