"""Compact display assignments and desktop geometry; no rendering ownership."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PyQt6.QtCore import QRect, QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QScreen
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.calibration_profile import (
    AssignedDisplay,
    MonitorBinding,
    active_monitor_bindings,
    write_diagnostic_bundle,
)
from cephvr.gui.components import Card, combo
from cephvr.gui.device_panel import DevicePanel
from cephvr.gui.display_layout import DisplayLayout
from cephvr.gui.projector_assignments import (
    AssignmentPreferences,
    sync_assignment_controls,
)
from cephvr.gui.projector_brightness import ProjectorBrightnessCard
from cephvr.gui.projector_calibration import CalibrationTable
from cephvr.gui.projector_codec import display_document, merge_projector_draft
from cephvr.gui.projector_geometry import (
    RigGeometryEditor,
    ScreenGeometryEditor,
    resolved_screens,
)
from cephvr.gui.projector_measured_profiles import measured_profiles
from cephvr.gui.projector_measurements import ProjectorMeasurements
from cephvr.gui.projector_prerequisites import NO_PROJECTORS_MESSAGE
from cephvr.gui.projector_profile import bind_profile, current_outputs, portable_profile
from cephvr.gui.tables import DataTable
from cephvr.gui.tank_diagram import TankDiagram
from cephvr.gui.theme import SIZES
from cephvr.gui.view import DashboardView
from cephvr.shared.calibration_assets import calibration_asset_root
from cephvr.visual_stimulus.configuration import load_projection_settings
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
    by_name = [
        binding
        for binding in bindings
        if binding.adapter and binding.adapter.casefold() == screen.name().casefold()
    ]
    if len(by_name) == 1 and by_name[0].interface:
        return by_name[0].interface
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
            for key in self.assignments
            if self.participation.get(key, True)
        }
        return tuple(
            face for face in ("Front", "Left", "Right", "Bottom") if face in enabled
        )

    def __init__(
        self, *, settings: QSettings | None = None, review: bool = False
    ) -> None:
        super().__init__(
            "Displays",
            (("DISPLAY", "—"), ("PROJECTOR", "Unassigned"), ("OUTPUT", "Not tested")),
            (),
        )
        self.table = DataTable(0, 5)
        self.refresh_button = self.table.add_refresh_action(
            "Refresh available displays"
        )
        self.refresh_button.clicked.connect(lambda: self.request("Refresh displays"))
        self.table.setHorizontalHeaderLabels(
            ["Use", "Display ID", "Projector", "Resolution (px)", ""]
        )
        vertical = self.table.verticalHeader()
        header = self.table.horizontalHeader()
        assert vertical is not None and header is not None
        vertical.hide()
        self.table.setShowGrid(False)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setFixedHeight(180)
        self.table.empty_text = (
            "No displays listed. Use the refresh button above to detect displays."
        )
        self.configuration.body.insertWidget(1, self.table)
        self.brightness = ProjectorBrightnessCard()
        self.configuration.body.addWidget(self.brightness)
        self.brightness.requested.connect(self.adjust_brightness)
        self.assignment_preferences = AssignmentPreferences(
            settings, self.console.appendPlainText
        )
        self.assignments = self.assignment_preferences.restore({})
        self.participation: dict[str, bool] = {}
        self.enable_controls: dict[str, QCheckBox] = {}
        self.keys: list[str] = []
        self.projectors: dict[str, QComboBox] = {}
        self.display_aspects: dict[str, float] = {}
        self.display_pixels: dict[str, tuple[int, int]] = {}
        self.loading = False
        self.review_displays: tuple[DisplayInfo, ...] | None = None
        self.asset_root = ""
        self._profile_outputs: list[dict[str, object]] = []
        self._pulse_face: str | None = None
        self._configuration_error = ""
        self._geometry_dirty = False
        self.layout_card = Card("Displays layout")
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
        self.review = review
        self.live_tuning_available = True
        from cephvr.gui.projector_pulses import ProjectorPulses

        self.timing = ProjectorPulses(self, local_preview=review)
        if not review:
            self.timing.placement_button.clicked.connect(
                lambda: self.request_placement("photodiode_placement")
            )
        self.timing.blackouts.placement_button.clicked.connect(
            lambda: self.request_placement("blackout_placement")
        )
        self.calibration = CalibrationTable(self.screen_editor.drafts)
        self.measurements = ProjectorMeasurements(self.screen_editor.drafts)
        self.measurements.body.insertWidget(1, self.calibration.measurement_button)
        self.measurements.changed.connect(self._mark_geometry_dirty)
        self.calibration.launch_requested.connect(self.launch_calibration)
        self.calibration.measurement_requested.connect(
            self.launch_reference_measurement
        )
        self.calibration.close_requested.connect(self.calibration_close_requested.emit)
        calibration_fields: dict[str, QLineEdit | QCheckBox] = {
            **{f"rig.{key}": editor for key, editor in self.rig_editor.fields.items()},
            **{
                f"screens.{face}.{key}": editor
                for (face, key), editor in self.screen_editor.fields.items()
            },
        }
        calibration_fields.update(
            {
                f"screens.{face}.{key}": editor
                for (face, key), editor in self.measurements.fields.items()
            }
        )
        calibration_fields.update(
            {
                f"screens.{face}.subject_distance": editor
                for face, editor in self.rig_editor.screen_distances.items()
            }
        )
        for (face, key), editor in self.calibration.controls.items():
            assert isinstance(editor, (QLineEdit, QCheckBox))
            calibration_fields[f"screens.{face}.{key}"] = editor
        from cephvr.gui.projector_pulse_files import ProjectorPulseFiles

        self.calibration_files = ProjectorPulseFiles(
            calibration_fields,
            self.timing,
            self.face_participation,
            self.apply_face_participation,
            self.pulse_face,
            self.select_pulse_face,
        )
        self.calibration_files.message.connect(self.console.appendPlainText)
        self.calibration_files.loaded.connect(self.configuration_loaded)
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
        self.setup_pages.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        synchronization = QWidget()
        synchronization_layout = QVBoxLayout(synchronization)
        synchronization_layout.setContentsMargins(0, 0, 0, 0)
        synchronization_layout.setSpacing(SIZES.card_gap)
        # VSync mode belongs to a card like the other synchronization controls.
        self.vsync_card = Card("Display synchronization")
        self.vsync_card.body.addWidget(self.timing.mode_field)
        synchronization_layout.addWidget(self.vsync_card)
        synchronization_layout.addWidget(self.timing)
        synchronization_layout.addWidget(self.timing.blackouts)
        synchronization_layout.addStretch()
        calibration_page = QWidget()
        calibration_layout = QVBoxLayout(calibration_page)
        calibration_layout.setContentsMargins(0, 0, 0, 0)
        calibration_layout.setSpacing(SIZES.card_gap)
        calibration_layout.addWidget(self.measurements)
        calibration_layout.addWidget(self.calibration)
        calibration_layout.addStretch()
        for title, card in (
            ("Rig geometry", self.rig_page),
            ("Projection calibration", calibration_page),
            ("Projection synchronization", synchronization),
        ):
            self.setup_tabs.addTab(title)
            self.setup_pages.addWidget(card)
        self.setup_tabs.currentChanged.connect(self.setup_pages.setCurrentIndex)
        layout.insertWidget(2, self.setup_tabs)
        layout.insertWidget(3, self.setup_pages)
        right = self.status_column.layout()
        assert isinstance(right, QVBoxLayout)
        self.status_column.hud_card.hide()
        right.insertWidget(0, self.layout_card)
        self.tank_card = Card("Setup geometry")
        self.tank = TankDiagram()
        self.tank_card.body.addWidget(self.tank)
        right.insertWidget(1, self.tank_card)
        self.rig_editor.changed.connect(self.update_geometry)
        self.screen_editor.changed.connect(self.update_geometry)
        self.measurements.changed.connect(self.update_geometry)
        self.table.currentCellChanged.connect(lambda *_: self.show_selected())

    def adjust_brightness(self, current_ma: int) -> None:
        if self.review:
            self.console.appendPlainText(
                f"REVIEW · Adjust all projector RGB LED currents to {current_ma} mA; no hardware command sent."
            )
            self.brightness.finish()

    def _mark_geometry_dirty(self) -> None:
        self._geometry_dirty = True

    def restore_assignment_draft(self) -> bool:
        restored = self.assignment_preferences.restore(self.assignments)
        changed = restored != self.assignments
        self.assignments = restored
        sync_assignment_controls(self.assignments, self.projectors)
        if changed:
            self.console.appendPlainText(
                "Last display assignments restored as a local draft; "
                "controller validation is still required."
            )
            self.update_participation()
        return changed

    def install_configuration(
        self,
        display: visual_stimulus_pb.DisplayConfiguration,
        *,
        pacing_output_id: str | None = None,
    ) -> None:
        """Install a bounded draft; controller validation uses its file policy."""
        del pacing_output_id  # Pacing remains file-owned and absent from this draft.
        self.calibration_files.profile = None
        self._profile_outputs = []
        self._pulse_face = None
        self._configuration_error = ""
        if not display.profile_json:
            self.assignments = {}
            sync_assignment_controls(self.assignments, self.projectors)
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
            portable = portable_profile(profile)
        except (ValueError, TypeError) as exc:
            self._configuration_error = str(exc)
            self.calibration.setToolTip(self._configuration_error)
            return
        self._profile_outputs = outputs
        self.calibration_files.profile = portable
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
        self.timing.set_presentation_mode(
            profile.get("presentation_mode", "photodiode_only_vsync")
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
        self.timing.install_overlays(profile, self.assignments, output_by_identity)
        self.loading = False
        self._geometry_dirty = False
        self.calibration.setToolTip(
            "Imported geometric and photometric profile references are preserved."
        )
        sync_assignment_controls(self.assignments, self.projectors)
        self.update_participation()

    def configuration_loaded(self) -> None:
        if self._configuration_error.startswith("Load a projector configuration"):
            self._configuration_error = ""
        self.update_geometry()
        self.outputs_changed.emit()

    def face_participation(self) -> dict[str, bool]:
        return {
            face: self.participation.get(key, True)
            for key, face in self.assignments.items()
            if face in ("Front", "Left", "Right", "Bottom")
        }

    def apply_face_participation(self, enabled: dict[str, bool]) -> None:
        for key, face in self.assignments.items():
            if face in enabled:
                self.participation[key] = enabled[face]
                if key in self.enable_controls:
                    self.enable_controls[key].setChecked(enabled[face])
        self.update_participation()

    def pulse_face(self) -> str | None:
        face = self.assignments.get(self.timing.target.currentData())
        if face in ("Front", "Left", "Right", "Bottom"):
            return face
        if self.timing.target.currentData() is not None:
            raise ValueError(
                "Assign a projector role to the selected pulse display before saving"
            )
        return self._pulse_face

    def select_pulse_face(self, face: str | None) -> None:
        self._pulse_face = face
        identity = next(
            (key for key, value in self.assignments.items() if value == face), None
        )
        self.timing.target.setCurrentIndex(
            self.timing.target.findData(identity) if identity is not None else -1
        )
        if not self.timing.target.signalsBlocked() and (
            face is not None or self.timing.face is not None
        ):
            self.timing.select_screen()

    def configuration_for_submit(
        self, base_display: visual_stimulus_pb.DisplayConfiguration
    ) -> visual_stimulus_pb.DisplayConfiguration:
        """Collect projector-owned fields while retaining calibrated profile data."""
        if self._configuration_error and not (
            self._configuration_error.startswith("Load a projector configuration")
            and base_display.profile_json
        ):
            raise ValueError(self._configuration_error)
        source_display = base_display
        if base_display.profile_json:
            self._profile_outputs = display_document(base_display).get("outputs", [])
        if self.calibration_files.profile is not None:
            document = bind_profile(
                self.calibration_files.profile,
                current_outputs(
                    self._profile_outputs,
                    self.assignments,
                    self.participation,
                    native=self.review_displays is None,
                ),
                self.assignments,
            )
            source_display = visual_stimulus_pb.DisplayConfiguration(
                profile_json=json.dumps(document, allow_nan=False)
            )
        if not source_display.profile_json:
            raise ValueError(
                "Load a projector configuration with screen-profile references first"
            )
        pulse_output_identity = self.timing.target.currentData()
        pulse_patch = self.timing.patch_draft()
        geometry = None
        if self._geometry_dirty:
            geometry = self.rig_editor.geometry_payload(self.screen_editor.drafts)
        result = merge_projector_draft(
            source_display,
            assignments=self.assignments,
            participation=self.participation,
            pulse_enabled=self.timing.pulse.isChecked(),
            pulse_output_identity=(
                str(pulse_output_identity)
                if pulse_output_identity is not None
                else None
            ),
            presentation_mode=self.timing.presentation_mode,
            pulse_patch=pulse_patch,
            pulse_patches={
                face: patch.model_dump(include={"rect", "background_rect"})
                for face, patch in self.timing.patches(enabled_only=False).items()
            }
            if self.timing.drafts
            else None,
            blackout_zones=self.timing.blackouts.snapshot(),
            geometry=geometry,
        )
        document = measured_profiles(
            display_document(result),
            self.calibration_files.calibration_snapshot(),
            self.asset_root,
        )
        document.setdefault("geometry", {}).update(load_projection_settings())
        result.profile_json = json.dumps(
            document, allow_nan=False, separators=(",", ":")
        )
        return result

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
                    "Display IDs use native stable display identities. Compare "
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
        self.display_pixels.clear()
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
            self.display_pixels[key] = (
                round(geometry.width() * ratio),
                round(geometry.height() * ratio),
            )
            index = display.index if self.review_displays is not None else str(row + 1)
            for col, value in (
                (1, index),
                (
                    3,
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
            self.table.setCellWidget(row, 2, editor)
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
            self.table.setCellWidget(row, 0, cell)
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
        if not self.keys:
            self.console.appendPlainText(NO_PROJECTORS_MESSAGE)
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

    def prepare_calibration(
        self,
        *,
        view: Literal[
            "reference_bars", "frame_grid", "photodiode_placement", "blackout_placement"
        ] = "frame_grid",
    ) -> Path | None:
        if not self.can_review:
            return None
        if self.review_displays is not None:
            self.console.appendPlainText(
                "Calibration export requires actual secondary displays, not review fixtures."
            )
            return None
        try:
            self.request("Refresh displays")
            monitors = active_monitor_bindings()
            native_interfaces = {monitor.interface for monitor in monitors}
            rows = tuple(
                AssignedDisplay(
                    self.assignments.get(key, "Unassigned"),
                    geometry.x(),
                    geometry.y(),
                    geometry.width(),
                    geometry.height(),
                    self.participation.get(key, True),
                    interface=key if key in native_interfaces else "",
                )
                for key, (_, geometry) in zip(
                    self.keys, self.diagram.outputs, strict=True
                )
            )
            from cephvr.gui.placement_calibration import initial_photodiode_patches

            path = write_diagnostic_bundle(
                calibration_asset_root(),
                self.calibration_files.calibration_snapshot(),
                rows,
                monitors,
                view=view,
                photodiode_patches=initial_photodiode_patches(self)
                if view == "photodiode_placement"
                else None,
                blackout_zones=(
                    self.timing.blackouts.snapshot()
                    if view in ("frame_grid", "blackout_placement")
                    else None
                ),
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

    def launch_reference_measurement(self) -> None:
        arena_path = self.prepare_calibration(view="reference_bars")
        if arena_path is not None:
            self.calibration_launch_requested.emit(str(arena_path))

    def set_calibration_presentation_state(
        self,
        *,
        active: bool,
        available: bool,
        pending: bool = False,
        view: str = "",
        tunable: bool = True,
    ) -> None:
        self.live_tuning_available = tunable
        self.calibration.set_presentation_state(
            active=active, available=available, pending=pending, view=view
        )
        self.refresh_calibration_editability()

    def request_placement(self, view: str) -> None:
        from cephvr.gui.placement_calibration import request_placement

        request_placement(self, view)

    def refresh_calibration_editability(self) -> None:
        active = self.calibration.presentation_active
        editable = (
            self.can_review and not active and not self.calibration.presentation_pending
        )
        live = (
            self.can_review
            and active
            and self.live_tuning_available
            and self.calibration.presentation_view == "frame_grid"
            and not self.calibration.presentation_pending
        )
        for (_, key), control in self.calibration.controls.items():
            control.setEnabled(
                editable
                or (
                    live
                    and key
                    in {
                        "valid_width_px",
                        "valid_height_px",
                        "offset_x_px",
                        "offset_y_px",
                    }
                )
            )
        measuring = (
            self.can_review
            and active
            and self.live_tuning_available
            and self.calibration.presentation_view == "reference_bars"
            and not self.calibration.presentation_pending
        )
        self.measurements.setEnabled(editable or measuring)
        for (_, key), control in self.measurements.fields.items():
            control.setEnabled(editable or (measuring and key.endswith("_mm")))
        self.rig_editor.setEnabled(editable)
        self.screen_editor.setEnabled(editable)
        self.calibration_files.setEnabled(editable)
        self.table.setEnabled(editable)
        from cephvr.gui.placement_calibration import refresh_placement_controls

        refresh_placement_controls(self, editable=editable)
        if self.review:
            self.timing.placement_button.setEnabled(self.can_review)

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
        if self._pulse_face is not None and self.timing.target.currentIndex() < 0:
            self.select_pulse_face(self._pulse_face)
        self.update_geometry()
        self.outputs_changed.emit()

    def update_geometry(self) -> None:
        outputs = {
            self.assignments[key]: dimensions
            for key, dimensions in self.display_pixels.items()
            if self.assignments.get(key, "Unassigned") != "Unassigned"
        }
        self.measurements.refresh(outputs, self.screen_editor.fields)
        self.calibration.refresh_dimensions(outputs)
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
        previous = self.assignments.get(key, "Unassigned")
        if previous != name:
            for face in (previous, name):
                if face in self.screen_editor.drafts:
                    self.measurements.clear_measurements(face)
        self.assignments[key] = name
        self.assignment_preferences.save(self.assignments)
        self.update_participation()
        self.show_selected()

    def show_selected(self) -> None:
        if self.loading:
            return
        if not self.keys:
            self.status_column.set_rows((("", NO_PROJECTORS_MESSAGE),))
            return
        row = self.table.currentRow()
        key = self.keys[row] if 0 <= row < len(self.keys) else ""
        item = self.table.item(row, 1)
        self.status_column.set_rows(
            (
                ("DISPLAY ID", item.text() if item else "—"),
                None,
                ("PROJECTOR", self.assignments.get(key, "Unassigned")),
                ("OUTPUT", "Not tested"),
            )
        )

    def apply_view(self, view: DashboardView) -> None:
        super().apply_view(view)
        self.brightness.apply_view(view)
        self.refresh_button.setEnabled(self.can_review)
        self.calibration_files.setEnabled(self.can_review)
        self.calibration.setEnabled(self.can_review)
        self.rig_editor.setEnabled(self.can_review)
        self.screen_editor.setEnabled(self.can_review)
        self.timing.can_edit = self.can_review
        self.timing.refresh_controls()
        self.refresh_calibration_editability()
        for control in self.enable_controls.values():
            control.setEnabled(self.can_review)
        for editor in self.projectors.values():
            editor.setEnabled(self.can_review)
