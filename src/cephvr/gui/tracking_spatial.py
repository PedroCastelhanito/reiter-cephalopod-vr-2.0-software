"""Source-pixel rectangles, image-plane scale and preprocessing draft controls."""

from math import hypot, isfinite

from PyQt6.QtCore import QLocale, Qt, pyqtSignal
from PyQt6.QtGui import QDoubleValidator, QResizeEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QSizePolicy,
    QSpinBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import Card, button, field, label
from cephvr.gui.tables import DataTable
from cephvr.gui.theme import SIZES


class PointEditor(DataTable):
    """Named source-pixel rows shared by anatomical and distance references."""

    changed = pyqtSignal()

    def __init__(self, names: tuple[str, ...]) -> None:
        super().__init__(len(names), 3)
        self.setHorizontalHeaderLabels(["Point", "X (px)", "Y (px)"])
        self.setShowGrid(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        vertical = self.verticalHeader()
        header = self.horizontalHeader()
        assert vertical is not None and header is not None
        vertical.hide()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        first = self.horizontalHeaderItem(0)
        assert first is not None
        first.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.coordinates: list[QLineEdit] = []
        for row, name in enumerate(names):
            caption = QTableWidgetItem(name)
            caption.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            self.setItem(row, 0, caption)
            for column, axis in enumerate(("X", "Y"), 1):
                editor = QLineEdit()
                editor.setProperty("role", "point-coordinate")
                editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
                editor.setSizePolicy(
                    QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
                )
                editor.setMinimumWidth(0)
                editor.setPlaceholderText("—")
                editor.setAccessibleName(f"{name} {axis}")
                editor.setToolTip("Original camera pixels, before crop or downscale.")
                validator = QDoubleValidator(0, 100_000, 3, editor)
                validator.setNotation(QDoubleValidator.Notation.StandardNotation)
                validator.setLocale(QLocale.c())
                editor.setValidator(validator)
                editor.editingFinished.connect(self.changed.emit)
                self.setCellWidget(row, column, editor)
                self.coordinates.append(editor)

        self.fit_rows()

    def resizeEvent(self, event: QResizeEvent | None) -> None:  # noqa: N802
        super().resizeEvent(event)
        viewport = self.viewport()
        assert viewport is not None
        width = viewport.width()
        self.setColumnWidth(0, width // 2)
        self.setColumnWidth(1, width // 4)
        self.setColumnWidth(2, width - width // 2 - width // 4)

    def points(self) -> list[list[float]] | None:
        """Keep the committed annotation unchanged while any row is incomplete."""
        points = []
        gap = False
        for index in range(0, len(self.coordinates), 2):
            pair = self.coordinates[index : index + 2]
            if all(not editor.text() for editor in pair):
                gap = True
            elif gap or not all(editor.hasAcceptableInput() for editor in pair):
                return None
            else:
                points.append([float(editor.text()) for editor in pair])
        return points

    def set_points(self, points: list[list[float]]) -> None:
        values = [value for point in points for value in point]
        for index, editor in enumerate(self.coordinates):
            editor.blockSignals(True)
            editor.setText(f"{values[index]:g}" if index < len(values) else "")
            editor.blockSignals(False)


class RegionEditor(QWidget):
    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(SIZES.field_x_gap)
        self.fields: list[QSpinBox] = []
        for index, name in enumerate(("X", "Y", "Width", "Height")):
            editor = QSpinBox()
            editor.setRange(0, 100_000)
            editor.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            if index >= 2:
                editor.setSpecialValueText("Not set")
            editor.setToolTip(
                "Original camera pixels, before crop or downscale. Width and height must be positive."
            )
            editor.valueChanged.connect(lambda: self.changed.emit())
            layout.addWidget(field(name, editor), 0, index)
            layout.setColumnStretch(index, 1)
            self.fields.append(editor)

    def values(self) -> list[int]:
        return [editor.value() for editor in self.fields]

    def set_values(self, values: list[int]) -> None:
        for editor, value in zip(self.fields, values, strict=True):
            editor.blockSignals(True)
            editor.setValue(value)
            editor.blockSignals(False)

    def corners(self) -> list[list[float]]:
        x, y, width, height = self.values()
        return [[x, y], [x + width, y + height]] if width and height else []

    def set_corners(self, points: list[list[float]]) -> None:
        if len(points) == 2:
            (x, y), (right, bottom) = points
            self.set_values([round(x), round(y), round(right - x), round(bottom - y)])
        else:
            self.set_values([0, 0, 0, 0])


class PreprocessingPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(SIZES.card_gap)
        self.crop = Card("Input crop")
        self.enabled = QCheckBox("Enable crop")
        row = QHBoxLayout()
        row.addWidget(self.enabled)
        row.addStretch()
        self.crop.body.addLayout(row)
        self.region = RegionEditor()
        region_layout = self.region.layout()
        assert region_layout is not None
        region_layout.setContentsMargins(0, SIZES.section_toggle_gap, 0, 0)
        self.crop.body.addWidget(self.region)
        self.region.setEnabled(False)
        self.enabled.toggled.connect(self.region.setEnabled)
        body.addWidget(self.crop)
        self.resize_card = Card("Processing resolution")
        self.scale = QSpinBox()
        self.scale.setRange(10, 100)
        self.scale.setValue(100)
        self.scale.setSingleStep(5)
        self.scale.setSuffix(" %")
        self.scale.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.resize_card.body.addWidget(field("Downscale", self.scale))
        body.addWidget(self.resize_card)
        body.addStretch()


class DistanceCalibration(Card):
    def __init__(self) -> None:
        super().__init__("Pixel-to-mm calibration")
        self.draw = button("Set endpoints")
        self.clear = button("Clear")
        row = QHBoxLayout()
        row.addWidget(self.draw)
        row.addWidget(self.clear)
        row.addStretch()
        self.body.addLayout(row)
        self.point_editor = PointEditor(("A", "B"))
        self.coordinates = self.point_editor.coordinates
        self.body.addWidget(self.point_editor)
        self.distance = QLineEdit()
        self.distance.setPlaceholderText("Known distance")
        self.body.addWidget(field("Reference length (mm)", self.distance))
        self.summary = label("", wrap=True)
        self.summary.hide()
        self.summary.setToolTip(
            "Image-plane scale at the calibration plane. Does not calibrate physical swimming speed."
        )
        self.body.addWidget(self.summary)

    def points(self) -> list[list[float]]:
        return self.point_editor.points() or []

    def set_points(self, points: list[list[float]]) -> None:
        self.point_editor.set_points(points)
        self.update_scale()

    def update_scale(self) -> None:
        points = self.points()
        try:
            mm = float(self.distance.text())
            pixels = hypot(points[1][0] - points[0][0], points[1][1] - points[0][1])
            if not isfinite(mm) or not isfinite(pixels) or mm <= 0 or pixels <= 0:
                raise ValueError
            self.summary.setText(
                f"{pixels / mm:.4g} px/mm   ·   {mm / pixels:.4g} mm/px"
            )
            self.summary.show()
        except (ValueError, IndexError):
            self.summary.clear()
            self.summary.hide()
