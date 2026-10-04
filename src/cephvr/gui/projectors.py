"""Compact display assignments and desktop geometry; no rendering ownership."""

from dataclasses import dataclass

from PyQt6.QtCore import QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPaintEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QStackedWidget,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.calibration_files import CalibrationFiles
from cephvr.gui.components import Card, button, combo
from cephvr.gui.device_panel import DevicePanel
from cephvr.gui.display_indices import windows_display_indices
from cephvr.gui.projector_calibration import CalibrationTable
from cephvr.gui.projector_geometry import (
    RigGeometryEditor,
    ScreenGeometryEditor,
    resolved_screens,
)
from cephvr.gui.projector_timing import ProjectorTiming
from cephvr.gui.tank_diagram import TankDiagram
from cephvr.gui.theme import COLORS, SIZES
from cephvr.gui.view import DashboardView


@dataclass(frozen=True)
class DisplayInfo:
    identity: str
    name: str
    index: str
    geometry: QRect
    pixel_ratio: float = 1.0


class DisplayLayout(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.outputs: list[tuple[str, QRect]] = []
        self.refreshed = False
        self.disabled_indices: set[int] = set()
        self.setMinimumHeight(80)
        self.setAccessibleName("Displays layout")

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(260, 145)

    def paintEvent(self, event: QPaintEvent | None) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(COLORS.muted))
        if not self.outputs:
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "No secondary displays found" if self.refreshed else "Refresh displays",
            )
            return
        bounds = QRect()
        for _, rect in self.outputs:
            bounds = bounds.united(rect)
        scale = min(
            (self.width() - 20) / max(1, bounds.width()),
            (self.height() - 20) / max(1, bounds.height()),
        )
        for row, (name, rect) in enumerate(self.outputs):
            box = QRectF(
                (rect.x() - bounds.x()) * scale
                + (self.width() - bounds.width() * scale) / 2,
                (rect.y() - bounds.y()) * scale
                + (self.height() - bounds.height() * scale) / 2,
                rect.width() * scale,
                rect.height() * scale,
            ).adjusted(2, 2, -2, -2)
            painter.setBrush(QColor(COLORS.selection))
            painter.setPen(
                QColor(COLORS.muted if row in self.disabled_indices else COLORS.accent)
            )
            painter.drawRoundedRect(box, 5, 5)
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, name)


class ProjectorsPanel(DevicePanel):
    outputs_changed = pyqtSignal()

    @property
    def enabled_screens(self) -> tuple[str, ...]:
        enabled = {
            self.assignments.get(key)
            for key in self.keys
            if self.participation.get(key, True)
        }
        return tuple(
            face for face in ("Front", "Left", "Right", "Bottom") if face in enabled
        )

    def __init__(self) -> None:
        super().__init__(
            "Displays",
            "DISPLAY     —\nPROJECTOR   Unassigned\nOUTPUT      Not tested",
            ("Refresh displays",),
        )
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Display", "Projector", "Resolution (px)", "Use"]
        )
        vertical = self.table.verticalHeader()
        header = self.table.horizontalHeader()
        assert vertical is not None and header is not None
        vertical.hide()
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setFixedHeight(180)
        self.configuration.body.insertWidget(1, self.table)
        self.assignments: dict[str, str] = {}
        self.participation: dict[str, bool] = {}
        self.enable_controls: dict[str, QCheckBox] = {}
        self.keys: list[str] = []
        self.projectors: dict[str, QComboBox] = {}
        self.display_aspects: dict[str, float] = {}
        self.loading = False
        self.review_displays: tuple[DisplayInfo, ...] | None = None
        self.layout_card = Card("Displays layout")
        self.diagram = DisplayLayout()
        self.layout_card.body.addWidget(self.diagram)
        layout = self.columns[0].layout()
        assert isinstance(layout, QVBoxLayout)
        self.rig_editor = RigGeometryEditor()
        self.screen_editor = ScreenGeometryEditor()
        for face, distance_editor in self.rig_editor.screen_distances.items():
            distance_editor.textChanged.connect(
                lambda value, f=face: self.screen_editor.save_value(
                    f, "subject_distance", value
                )
            )
        self.timing = ProjectorTiming()
        self.calibration = CalibrationTable(self.screen_editor.drafts)
        calibration_fields: dict[str, QLineEdit | QCheckBox] = {
            **{f"rig.{key}": editor for key, editor in self.rig_editor.fields.items()},
            **{
                f"projection.{key}": editor
                for key, editor in self.rig_editor.projection_fields.items()
            },
            **{
                f"screens.{face}.{key}": editor
                for (face, key), editor in self.screen_editor.fields.items()
            },
        }
        calibration_fields.update(
            {
                f"screens.{face}.subject_distance": editor
                for face, editor in self.rig_editor.screen_distances.items()
            }
        )
        for (face, key), editor in self.calibration.controls.items():
            assert isinstance(editor, (QLineEdit, QCheckBox))
            calibration_fields[f"screens.{face}.{key}"] = editor
        self.calibration_files = CalibrationFiles(calibration_fields)
        self.calibration_files.message.connect(self.console.appendPlainText)
        self.calibration_files.loaded.connect(self.update_geometry)
        layout.insertWidget(1, self.calibration_files)
        self.rig_page = QWidget()
        rig_layout = QVBoxLayout(self.rig_page)
        rig_layout.setContentsMargins(0, 0, 0, 0)
        rig_layout.addWidget(self.rig_editor)
        rig_layout.addWidget(self.screen_editor)
        rig_layout.addStretch()
        self.setup_tabs = QTabBar()
        self.setup_tabs.setExpanding(True)
        self.setup_tabs.setDrawBase(False)
        self.setup_pages = QStackedWidget()
        for title, card in (
            ("Screen calibration", self.calibration),
            ("Synchronization", self.timing),
            ("Rig geometry", self.rig_page),
        ):
            self.setup_tabs.addTab(title)
            self.setup_pages.addWidget(card)
        self.setup_tabs.currentChanged.connect(self.select_setup_page)
        self.select_setup_page(0)
        layout.insertWidget(2, self.setup_tabs)
        layout.insertWidget(3, self.setup_pages)
        right = self.status_column.layout()
        assert isinstance(right, QVBoxLayout)
        self.status_column.hud_card.hide()
        right.insertWidget(0, self.layout_card)
        self.tank_card = Card("Tank & screens")
        self.tank = TankDiagram()
        self.plot_toggles = {}
        plot_controls = QGridLayout()
        plot_controls.setSpacing(6)
        for i, (key, title) in enumerate(
            (
                ("tank", "Tank"),
                ("screens", "Screens"),
                ("projection", "Projection"),
                ("subject", "Subject"),
                ("labels", "Labels"),
            )
        ):
            control = button(
                title, "plot-toggle", hint=f"Show or hide {title.lower()} in the plot"
            )
            control.setCheckable(True)
            if key == "projection":
                control.setToolTip(
                    "Show or hide projectors, rays, footprints and mirror together"
                )
            control.setChecked(True)
            control.toggled.connect(
                lambda visible, k=key: self.tank.set_element_visible(k, visible)
            )
            self.plot_toggles[key] = control
            plot_controls.addWidget(
                control, i // 3, i % 3, 1, 2 if key == "labels" else 1
            )
            plot_controls.setColumnStretch(i % 3, 1)
        self.tank_card.body.addLayout(plot_controls)
        self.tank_card.body.addWidget(self.tank)
        right.insertWidget(1, self.tank_card)
        self.rig_editor.changed.connect(self.update_geometry)
        self.screen_editor.changed.connect(self.update_geometry)
        self.table.currentCellChanged.connect(lambda *_: self.show_selected())

    def request(self, name: str) -> None:
        if not self.can_review:
            return
        if name != "Refresh displays":
            super().request(name)
            return
        current = (
            self.keys[self.table.currentRow()]
            if 0 <= self.table.currentRow() < len(self.keys)
            else ""
        )
        if self.review_displays is None:
            indices, issue = windows_display_indices()
            primary = QGuiApplication.primaryScreen()
            displays = tuple(
                DisplayInfo(
                    f"{screen.name()}|{screen.manufacturer()}|{screen.model()}|{screen.serialNumber()}",
                    screen.name(),
                    indices.get(screen.name().casefold(), "—"),
                    screen.geometry(),
                    screen.devicePixelRatio(),
                )
                for screen in QGuiApplication.screens()
                if screen != primary
            )
        else:
            displays = self.review_displays
            issue = "LOCAL REVIEW · Simulated displays; no hardware connected."
        self.loading = True
        self.table.setRowCount(0)
        self.keys.clear()
        self.projectors.clear()
        self.display_aspects.clear()
        self.enable_controls.clear()
        self.diagram.outputs.clear()
        self.diagram.refreshed = True
        for display in displays:
            key = display.identity
            if key in self.keys:
                self.console.appendPlainText(
                    "Duplicate display identity omitted; cannot assign it safely."
                )
                continue
            row = len(self.keys)
            self.keys.append(key)
            self.table.insertRow(row)
            geometry = display.geometry
            if geometry.width() > 0 and geometry.height() > 0:
                self.display_aspects[key] = geometry.width() / geometry.height()
            ratio = display.pixel_ratio
            index = display.index
            for col, value in (
                (0, index),
                (
                    2,
                    f"{round(geometry.width() * ratio)} × {round(geometry.height() * ratio)}",
                ),
            ):
                item = QTableWidgetItem(value)
                item.setToolTip(
                    f"{display.name}\nDesktop position: {geometry.x()}, {geometry.y()}\n{issue}"
                )
                self.table.setItem(row, col, item)
            editor = combo(("Unassigned", "Front", "Left", "Right", "Bottom"))
            editor.setEditable(False)
            editor.setMinimumWidth(0)
            editor.setCurrentText(self.assignments.get(key, "Unassigned"))
            editor.currentTextChanged.connect(
                lambda text, identity=key: self.assign(identity, text)
            )
            self.table.setCellWidget(row, 1, editor)
            self.projectors[key] = editor
            enabled = QCheckBox()
            enabled.setAccessibleName(f"Use display {index}")
            enabled.setChecked(self.participation.get(key, True))
            enabled.toggled.connect(
                lambda checked, identity=key: self.set_participation(identity, checked)
            )
            cell = QWidget()
            layout = QHBoxLayout(cell)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(enabled)
            self.table.setCellWidget(row, 3, cell)
            self.enable_controls[key] = enabled
            self.table.setRowHeight(row, 54)
            self.diagram.outputs.append((index, geometry))
        self.loading = False
        header = self.table.horizontalHeader()
        assert header is not None
        self.table.setFixedHeight(
            header.sizeHint().height()
            + max(1, min(5, len(self.keys))) * 54
            + SIZES.field_radius
            + 4
        )
        self.table.selectRow(self.keys.index(current) if current in self.keys else 0)
        self.update_participation()
        self.show_selected()
        self.console.appendPlainText(
            f"{len(self.keys)} simulated projector displays loaded."
            if self.review_displays is not None
            else f"{len(self.keys)} secondary displays discovered; primary display excluded; no hardware command sent."
        )
        if issue:
            self.console.appendPlainText(issue)
        missing = [
            name
            for key, name in self.assignments.items()
            if name != "Unassigned" and key not in self.keys
        ]
        if missing:
            self.console.appendPlainText(
                "Assigned displays unavailable: " + ", ".join(missing)
            )

    def set_participation(self, key: str, enabled: bool) -> None:
        if not self.can_review or key not in self.keys:
            return
        self.participation[key] = enabled
        self.update_participation()

    def update_participation(self) -> None:
        self.diagram.disabled_indices = {
            row
            for row, key in enumerate(self.keys)
            if not self.participation.get(key, True)
        }
        self.diagram.update()
        self.timing.set_displays(
            [
                (
                    key,
                    f"Display {self.diagram.outputs[row][0]} · {self.assignments.get(key, 'Unassigned')}",
                    self.participation.get(key, True),
                )
                for row, key in enumerate(self.keys)
            ]
        )
        self.update_geometry()
        self.outputs_changed.emit()

    def select_setup_page(self, index: int) -> None:
        self.setup_pages.setCurrentIndex(index)
        card = self.setup_pages.currentWidget()
        if card is not None:
            card.ensurePolished()
            self.setup_pages.setFixedHeight(card.sizeHint().height())

    def update_geometry(self) -> None:
        self.tank.rig = self.rig_editor.dimensions()
        self.tank.screens = resolved_screens(self.tank.rig, self.screen_editor.drafts)
        self.tank.identifiers = {
            self.assignments[key]: self.diagram.outputs[row][0]
            + (" (off)" if not self.participation.get(key, True) else "")
            for row, key in enumerate(self.keys)
            if self.assignments.get(key, "Unassigned") != "Unassigned"
        }
        self.tank.aspects = {
            self.assignments[key]: aspect
            for key, aspect in self.display_aspects.items()
            if self.assignments.get(key, "Unassigned") != "Unassigned"
        }
        self.tank.enabled_faces = self.enabled_screens
        self.tank.refresh()

    def assign(self, key: str, name: str) -> None:
        if self.loading or not self.can_review:
            return
        if (
            name
            and name != "Unassigned"
            and any(k != key and value == name for k, value in self.assignments.items())
        ):
            self.console.appendPlainText(
                "Projector label already assigned to another display."
            )
            editor = self.projectors[key]
            editor.blockSignals(True)
            editor.setCurrentText(self.assignments.get(key, "Unassigned"))
            editor.blockSignals(False)
            return
        self.assignments[key] = name
        self.update_participation()
        self.show_selected()

    def show_selected(self) -> None:
        if self.loading:
            return
        row = self.table.currentRow()
        key = self.keys[row] if 0 <= row < len(self.keys) else ""
        item = self.table.item(row, 0)
        self.status_column.hud.setPlainText(
            f"DISPLAY    {item.text() if item else '—'}\nPROJECTOR  {self.assignments.get(key, 'Unassigned')}\nOUTPUT     Not tested"
        )

    def apply_view(self, view: DashboardView) -> None:
        super().apply_view(view)
        self.calibration_files.setEnabled(self.can_review)
        self.calibration.setEnabled(self.can_review)
        self.rig_editor.setEnabled(self.can_review)
        self.screen_editor.setEnabled(self.can_review)
        self.timing.can_edit = self.can_review
        self.timing.refresh_controls()
        for control in self.enable_controls.values():
            control.setEnabled(self.can_review)
        for editor in self.projectors.values():
            editor.setEnabled(self.can_review)
