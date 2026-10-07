"""Compact display assignments and desktop geometry; no rendering ownership."""

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QRect, Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QScreen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QStackedWidget,
    QTabBar,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.calibration_files import CalibrationFiles
from cephvr.gui.calibration_profile import (
    AssignedDisplay,
    MonitorBinding,
    active_monitor_bindings,
    write_diagnostic_bundle,
)
from cephvr.gui.components import Card, button, combo
from cephvr.gui.device_panel import DevicePanel
from cephvr.gui.display_layout import DisplayLayout
from cephvr.gui.projector_calibration import CalibrationTable
from cephvr.gui.projector_codec import display_document, merge_projector_draft
from cephvr.gui.projector_geometry import (
    RigGeometryEditor,
    ScreenGeometryEditor,
    resolved_screens,
)
from cephvr.gui.projector_timing import ProjectorTiming
from cephvr.gui.tables import DataTable
from cephvr.gui.tank_diagram import TankDiagram
from cephvr.gui.theme import SIZES
from cephvr.gui.view import DashboardView
from cephvr.visual_stimulus.v1 import runtime_pb2 as visual_stimulus_pb


@dataclass(frozen=True)
class DisplayInfo:
    identity: str
    name: str
    index: str
    geometry: QRect
    pixel_ratio: float = 1.0


def _stable_display_identity(
    screen: QScreen, bindings: tuple[MonitorBinding, ...]
) -> str:
    geometry = screen.geometry()
    ratio = screen.devicePixelRatio()
    matches = [
        binding
        for binding in bindings
        if (binding.x, binding.y, binding.width, binding.height)
        == (
            geometry.x(),
            geometry.y(),
            round(geometry.width() * ratio),
            round(geometry.height() * ratio),
        )
    ]
    if len(matches) == 1 and matches[0].interface:
        return matches[0].interface
    return "|".join(
        (screen.name(), screen.manufacturer(), screen.model(), screen.serialNumber())
    )


class ProjectorsPanel(DevicePanel):
    outputs_changed = pyqtSignal()
    calibration_launch_requested = pyqtSignal(str)
    calibration_close_requested = pyqtSignal()

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
        self.table = DataTable(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["CephVR ID", "Projector", "Resolution (px)", "Use"]
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
        self.import_profile = button("Import display profile…", "secondary")
        self.import_profile.clicked.connect(self.load_display_profile)
        self.configuration.body.insertWidget(2, self.import_profile)
        self.assignments: dict[str, str] = {}
        self.participation: dict[str, bool] = {}
        self.enable_controls: dict[str, QCheckBox] = {}
        self.keys: list[str] = []
        self.projectors: dict[str, QComboBox] = {}
        self.display_aspects: dict[str, float] = {}
        self.loading = False
        self.review_displays: tuple[DisplayInfo, ...] | None = None
        self.asset_root = ""
        self._imported_profile: visual_stimulus_pb.DisplayConfiguration | None = None
        self._configuration_error = ""
        self._geometry_dirty = False
        self.layout_card = Card("Displays layout · CephVR IDs")
        self.diagram = DisplayLayout()
        self.layout_card.body.addWidget(self.diagram)
        layout = self.columns[0].layout()
        assert isinstance(layout, QVBoxLayout)
        self.rig_editor = RigGeometryEditor()
        self.screen_editor = ScreenGeometryEditor()
        self.rig_editor.changed.connect(self._mark_geometry_dirty)
        self.screen_editor.changed.connect(self._mark_geometry_dirty)
        for face, distance_editor in self.rig_editor.screen_distances.items():
            distance_editor.textChanged.connect(
                lambda value, f=face: self.screen_editor.save_value(
                    f, "subject_distance", value
                )
            )
        self.timing = ProjectorTiming()
        self.calibration = CalibrationTable(self.screen_editor.drafts)
        self.calibration.launch_requested.connect(self.launch_calibration)
        self.calibration.close_requested.connect(self.calibration_close_requested.emit)
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
            plot_controls.addWidget(control, i // 2, i % 2)
            plot_controls.setColumnStretch(i % 2, 1)
        self.tank_card.body.addLayout(plot_controls)
        self.tank_card.body.addWidget(self.tank)
        right.insertWidget(1, self.tank_card)
        self.rig_editor.changed.connect(self.update_geometry)
        self.screen_editor.changed.connect(self.update_geometry)
        self.table.currentCellChanged.connect(lambda *_: self.show_selected())

    def _mark_geometry_dirty(self) -> None:
        self._geometry_dirty = True

    def install_configuration(
        self,
        display: visual_stimulus_pb.DisplayConfiguration,
        *,
        pacing_output_id: str | None = None,
    ) -> None:
        """Install a bounded draft; controller validation uses its file policy."""
        del pacing_output_id  # Pacing remains file-owned and absent from this draft.
        self._imported_profile = None
        self._configuration_error = ""
        try:
            profile = display_document(display)
            outputs = profile.get("outputs")
            mappings = profile.get("mappings")
            if not isinstance(outputs, list) or not isinstance(mappings, list):
                raise ValueError("Display profile requires output and mapping arrays")
            output_by_id = {
                item["output_id"]: item
                for item in outputs
                if isinstance(item, dict) and isinstance(item.get("output_id"), str)
            }
        except (ValueError, TypeError) as exc:
            self._configuration_error = str(exc)
            self.calibration.setToolTip(self._configuration_error)
            return
        self.assignments = {}
        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
            output = output_by_id.get(mapping.get("output_id"))
            face = mapping.get("surface_id")
            identity = output.get("device_identity") if output else None
            if isinstance(identity, str) and face in {
                "front",
                "left",
                "right",
                "bottom",
            }:
                self.assignments.setdefault(identity, face.title())
        self.participation = {
            item["device_identity"]: item.get("enabled", True)
            for item in outputs
            if isinstance(item, dict)
            and isinstance(item.get("device_identity"), str)
            and type(item.get("enabled", True)) is bool
        }
        self.loading = True
        self.timing.pulse.setChecked(profile.get("photodiode_enabled", True) is True)
        self.timing.mode.setCurrentText(
            "All displays VSync"
            if profile.get("presentation_mode") == "all_outputs_vsync"
            else "Selected display VSync"
        )
        output_by_identity = {
            item["device_identity"]: item
            for item in outputs
            if isinstance(item, dict) and isinstance(item.get("device_identity"), str)
        }
        photodiode_output_id = profile.get("photodiode_output_id")
        target_identity = next(
            (
                identity
                for identity, output in output_by_identity.items()
                if output.get("output_id") == photodiode_output_id
            ),
            None,
        )
        target_index = (
            self.timing.target.findData(target_identity)
            if target_identity is not None
            else -1
        )
        if target_identity is not None and target_index < 0:
            self.timing.target.addItem(
                f"Saved display {target_identity} (not connected)", target_identity
            )
            target_index = self.timing.target.findData(target_identity)
        self.timing.target.setCurrentIndex(target_index)
        patch = profile.get("photodiode_patch")
        if isinstance(patch, dict) and isinstance(patch.get("rect"), dict):
            rect = patch["rect"]
            for key, value in zip(
                ("X", "Y", "Width", "Height"),
                (rect.get("x"), rect.get("y"), rect.get("width"), rect.get("height")),
                strict=True,
            ):
                if type(value) is int:
                    self.timing.fields[key].setText(str(value))
        self.loading = False
        self._geometry_dirty = False
        self.calibration.setToolTip(
            "Imported geometric and photometric profile references are preserved."
        )
        self.update_participation()

    def load_display_profile(self) -> None:
        """Import one complete profile into the local draft without controller I/O."""
        if not self.can_review:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Import display profile", self.asset_root, "Display profile (*.json)"
        )
        if not path:
            return
        self.import_display_profile(path)

    def import_display_profile(self, path: str) -> None:
        """Validate a selected profile before replacing the local draft."""
        if not self.can_review:
            return
        try:
            source = Path(path)
            if source.stat().st_size > 16_777_216:
                raise ValueError(
                    "Display profile exceeds the 16 MiB configuration limit"
                )
            imported = visual_stimulus_pb.DisplayConfiguration(
                profile_json=source.read_text(encoding="utf-8")
            )
            profile = display_document(imported)
            outputs, mappings = profile.get("outputs"), profile.get("mappings")
            if not isinstance(outputs, list) or not isinstance(mappings, list):
                raise ValueError("Display profile requires output and mapping arrays")
            if any(
                not isinstance(item, dict)
                or not isinstance(item.get("device_identity"), str)
                or not isinstance(item.get("output_id"), str)
                for item in outputs
            ):
                raise ValueError(
                    "Each display output needs a stable identity and output ID"
                )
            self.install_configuration(imported)
            if self._configuration_error:
                raise ValueError(self._configuration_error)
            self._imported_profile = imported
            self.outputs_changed.emit()
            self.console.appendPlainText(f"Imported local display profile: {source}")
        except (OSError, UnicodeError, ValueError, TypeError) as error:
            self.console.appendPlainText(f"Display profile import failed: {error}")

    def configuration_for_submit(
        self, base_display: visual_stimulus_pb.DisplayConfiguration
    ) -> visual_stimulus_pb.DisplayConfiguration:
        """Collect projector-owned fields while retaining calibrated profile data."""
        if self._configuration_error and not (
            self._configuration_error.startswith("Import a display profile")
            and base_display.profile_json
        ):
            raise ValueError(self._configuration_error)
        source_display = base_display
        if not source_display.profile_json and self._imported_profile is not None:
            source_display = self._imported_profile
        if not source_display.profile_json:
            raise ValueError("Import a display profile before configuring projectors")
        pulse_output_identity = self.timing.target.currentData()
        pulse_patch: dict[str, object] | None = None
        values = [
            self.timing.fields[key].text().strip()
            for key in ("X", "Y", "Width", "Height")
        ]
        if any(values):
            if not all(value.isdecimal() for value in values):
                raise ValueError("Photodiode rectangle requires integer pixel values")
            x, y, width, height = (int(value) for value in values)
            pulse_patch = {"rect": {"x": x, "y": y, "width": width, "height": height}}
        geometry = None
        if self._geometry_dirty:
            geometry = self.rig_editor.geometry_payload(self.screen_editor.drafts)
        return merge_projector_draft(
            source_display,
            assignments=self.assignments,
            participation=self.participation,
            pulse_enabled=self.timing.pulse.isChecked(),
            pulse_output_identity=(
                str(pulse_output_identity)
                if pulse_output_identity is not None
                else None
            ),
            presentation_mode=(
                "all_outputs_vsync"
                if self.timing.mode.currentText() == "All displays VSync"
                else "photodiode_only_vsync"
            ),
            pulse_patch=pulse_patch,
            geometry=geometry,
        )

    def request(self, name: str) -> None:
        if not self.can_review:
            return
        if name != "Refresh displays":
            super().request(name)
            return
        self.discover_displays()

    def discover_displays(self) -> None:
        """Inventory OS displays without assigning or opening projector outputs."""
        current = (
            self.keys[self.table.currentRow()]
            if 0 <= self.table.currentRow() < len(self.keys)
            else ""
        )
        if self.review_displays is None:
            primary = QGuiApplication.primaryScreen()
            secondary = sorted(
                (screen for screen in QGuiApplication.screens() if screen != primary),
                key=lambda screen: (
                    screen.geometry().x(),
                    screen.geometry().y(),
                    screen.name(),
                    screen.serialNumber(),
                ),
            )
            native_bindings: tuple[MonitorBinding, ...] = ()
            issue = (
                "Stable native display identities are unavailable; assignments "
                "cannot be submitted until refreshed. CephVR numbers are independent "
                "of Windows Settings."
            )
            try:
                native_bindings = active_monitor_bindings()
            except (AttributeError, ImportError, OSError, RuntimeError, ValueError):
                issue = (
                    "Stable native display identities are unavailable; "
                    "assignments cannot be submitted until refreshed. CephVR numbers "
                    "are independent of Windows Settings."
                )
            display_rows = tuple(
                DisplayInfo(
                    _stable_display_identity(screen, native_bindings),
                    screen.name(),
                    str(index),
                    screen.geometry(),
                    screen.devicePixelRatio(),
                )
                for index, screen in enumerate(secondary, 1)
            )
            displays = display_rows
            if native_bindings:
                issue = (
                    "CephVR IDs use native stable display identities. Compare "
                    "the layout with Windows Settings; numbers are independent."
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
            index = display.index if self.review_displays is not None else str(row + 1)
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
        for control in self.enable_controls.values():
            control.setEnabled(self.can_review)
        for editor in self.projectors.values():
            editor.setEnabled(self.can_review)

    def set_participation(self, key: str, enabled: bool) -> None:
        if not self.can_review or key not in self.keys:
            return
        self.participation[key] = enabled
        self.update_participation()

    def prepare_calibration(self) -> Path | None:
        if not self.can_review:
            return None
        if self.review_displays is not None:
            self.console.appendPlainText(
                "Calibration export requires actual secondary displays, not review fixtures."
            )
            return None
        try:
            if not self.asset_root:
                raise ValueError("Choose the Protocol Assets folder first")
            self.request("Refresh displays")
            rows = tuple(
                AssignedDisplay(
                    self.assignments.get(key, "Unassigned"),
                    geometry.x(),
                    geometry.y(),
                    geometry.width(),
                    geometry.height(),
                    self.participation.get(key, True),
                )
                for key, (_, geometry) in zip(
                    self.keys, self.diagram.outputs, strict=True
                )
            )
            path = write_diagnostic_bundle(
                Path(self.asset_root),
                self.calibration_files.snapshot(),
                rows,
                active_monitor_bindings(),
            )
            self.console.appendPlainText(
                f"Diagnostic calibration files prepared: {path}. No output command sent."
            )
            return path
        except (OSError, RuntimeError, ValueError) as exc:
            self.console.appendPlainText(f"Calibration export failed: {exc}")
            return None

    def launch_calibration(self) -> None:
        arena_path = self.prepare_calibration()
        if arena_path is not None:
            self.calibration_launch_requested.emit(str(arena_path))

    def set_calibration_presentation_state(
        self, *, active: bool, available: bool, pending: bool = False
    ) -> None:
        self.calibration.set_presentation_state(
            active=active, available=available, pending=pending
        )

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
            f"CEPHVR ID  {item.text() if item else '—'}\nPROJECTOR  {self.assignments.get(key, 'Unassigned')}\nOUTPUT     Not tested"
        )

    def apply_view(self, view: DashboardView) -> None:
        super().apply_view(view)
        self.import_profile.setEnabled(self.can_review)
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
