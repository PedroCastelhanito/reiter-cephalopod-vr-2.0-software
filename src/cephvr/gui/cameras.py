"""Camera inventory, editable drafts and controller-backed operator intents."""

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cephvr.acquisition.camera.basler import BaslerCameraAdapter
from cephvr.gui.camera_inventory import CameraDraft, discover_drafts
from cephvr.gui.components import ActionHeader, Card, StatusColumn, button, combo, field
from cephvr.gui.formatting import metrics_text
from cephvr.gui.icons import device_icon
from cephvr.gui.layouts import ResponsiveColumns, column
from cephvr.gui.paths import PresetField
from cephvr.gui.presets import trigger_hint
from cephvr.gui.tables import DataTable
from cephvr.gui.theme import SIZES
from cephvr.gui.view import DashboardView, Phase


class CamerasPanel(ResponsiveColumns):
    test_requested = pyqtSignal()
    inventory_refreshed = pyqtSignal()
    role_requested = pyqtSignal(str, str)
    participation_changed = pyqtSignal()
    drafts_changed = pyqtSignal()
    preview_requested = pyqtSignal(str, bool)
    connection_requested = pyqtSignal(str, bool)
    enable_requested = pyqtSignal(str, bool)
    settings_requested = pyqtSignal(str, str, str, str, str)
    preset_import_requested = pyqtSignal(str, str, str, str, str)

    def __init__(self, *, sample: bool = False) -> None:
        left, left_layout = column()
        right = StatusColumn("Camera HUD")
        self.status_column = right
        self.console = right.console
        self.console.setPlainText(
            "Camera inventory uses local review samples."
            if sample
            else "No camera inventory received."
        )
        super().__init__(left, right)
        self.drafts = (
            [
                CameraDraft(
                    "camera-1", "Behavior cam", "REVIEW-001", "Basler · sample"
                ),
                CameraDraft(
                    "camera-2", "Tracking cam", "REVIEW-002", "Basler · sample"
                ),
            ]
            if sample
            else []
        )
        self.view = DashboardView()
        self.real_devices = False
        self.managed = False
        self.operation_pending = False
        self.has_configured_tests = False
        self.pending_enable: dict[str, bool] = {}
        self.loading = False
        inventory = Card("Available devices")
        self.table = DataTable(len(self.drafts), 4)
        self.refresh_button = button("", "icon", hint="Refresh available cameras")
        self.refresh_button.setAccessibleName("Refresh available cameras")
        self.refresh_button.setIcon(device_icon("refresh"))
        self.refresh_button.setIconSize(QSize(16, 16))
        self.refresh_button.setFixedSize(26, 26)
        self.table.setHorizontalHeader(ActionHeader(self.refresh_button))
        self.table.setHorizontalHeaderLabels(["Use", "Camera", "Role", ""])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        vertical = self.table.verticalHeader()
        header = self.table.horizontalHeader()
        assert vertical is not None and header is not None
        vertical.hide()
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(3, 36)
        self.enable_controls: list[QCheckBox] = []
        self.populate_inventory()
        inventory.body.addWidget(self.table)
        actions = QHBoxLayout()
        self.test_button = button(
            "Test enabled", hint="Check connections for cameras enabled for experiment"
        )
        self.test_button.clicked.connect(self.test_enabled)
        self.connect_button = button(
            "Connect", "primary", hint="Start capture and open the external preview"
        )
        self.refresh_button.clicked.connect(self.refresh_inventory)
        self.connect_button.clicked.connect(self.toggle_connection)
        for control in (self.test_button, self.connect_button):
            actions.addWidget(control)
        inventory.body.addLayout(actions)
        left_layout.addWidget(inventory)
        self.configuration = Card("Camera config")
        self.role = combo(("Behavior cam", "Tracking cam", "Unassigned"))
        self.role.currentTextChanged.connect(self.assign_role)
        self.configuration.body.addWidget(field("ROLE", self.role))
        form = QGridLayout()
        self._finish_configuration(form, left_layout)

    def populate_inventory(self) -> None:
        self.enable_controls.clear()
        self.table.setRowCount(len(self.drafts))
        header = self.table.horizontalHeader()
        assert header is not None
        for row, draft in enumerate(self.drafts):
            enabled = QCheckBox()
            enabled.setChecked(draft.enabled)
            enabled.setAccessibleName(f"Enable {draft.role} for experiment")
            enabled.setToolTip("Enable for experiment")
            enabled.toggled.connect(
                lambda checked, index=row: self.set_participation(index, checked)
            )
            self.enable_controls.append(enabled)
            check_host = QWidget()
            check_layout = QHBoxLayout(check_host)
            check_layout.setContentsMargins(0, 0, 0, 0)
            check_layout.addWidget(enabled, 0, Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 0, check_host)
            self.table.setItem(
                row, 1, QTableWidgetItem(f"{draft.model}\n{draft.serial}")
            )
            self.table.setItem(row, 2, QTableWidgetItem(draft.role))
            self.table.setRowHeight(row, 58)
        self.table.setFixedHeight(
            header.sizeHint().height()
            + max(1, len(self.drafts)) * 58
            + 2 * self.table.frameWidth()
        )

    def _finish_configuration(
        self, form: QGridLayout, left_layout: QVBoxLayout
    ) -> None:
        form.setHorizontalSpacing(SIZES.field_x_gap)
        form.setVerticalSpacing(SIZES.field_y_gap)
        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 1)
        self.fields: dict[str, QLineEdit] = {}
        self.trigger_source = combo(("Internal clock", "External controller"))
        self.trigger_source.setPlaceholderText("Select trigger source")
        self.trigger_source.setCurrentIndex(-1)
        self.trigger_source.currentTextChanged.connect(
            lambda value: self.edit("trigger_clock", value)
        )
        self.trigger_source.currentTextChanged.connect(self.save_settings)
        form.addWidget(field("TRIGGER SOURCE", self.trigger_source), 0, 0)
        specs = (("trigger_frequency_hz", "TRIGGER RATE (Hz)"),)
        for index, (key, title) in enumerate(specs):
            editor = QLineEdit()
            editor.setPlaceholderText("Not set")
            editor.textChanged.connect(lambda value, name=key: self.edit(name, value))
            self.fields[key] = editor
            form.addWidget(field(title, editor), 0, index + 1)
        rate = self.fields["trigger_frequency_hz"]
        validator = QDoubleValidator(rate)
        validator.setBottom(0.1)
        validator.setDecimals(1)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        rate.setValidator(validator)
        rate.editingFinished.connect(self.save_settings)
        rate.setToolTip("Requested external trigger frequency generated by Arduino.")
        self.configuration.body.addLayout(form)
        self.preset_field = PresetField()
        self.preset = self.preset_field.editor
        self.preset.textChanged.connect(lambda value: self.edit("preset", value))
        self.preset.editingFinished.connect(self.inspect_preset)
        self.preset_field.path_selected.connect(lambda _: self.inspect_preset())
        self.configuration.body.addWidget(field("PARAMETER FILE", self.preset_field))
        left_layout.addWidget(self.configuration)
        left_layout.addStretch()
        self.table.currentCellChanged.connect(lambda *_: self.load_selected())
        if self.drafts:
            self.table.selectRow(0)
        self.refresh_controls()

    def refresh_inventory(self) -> None:
        if not self.can_operate and not self.managed:
            return
        if not self.real_devices:
            self.report("Refresh inventory")
            return
        selected_serial = self.selected.serial if self.selected else None
        try:
            self.drafts = discover_drafts(
                BaslerCameraAdapter(), self.drafts, managed=self.managed
            )
        except Exception as exc:
            self.console.appendPlainText(f"Camera discovery failed: {exc}")
            return
        self.populate_inventory()
        row = next(
            (
                i
                for i, draft in enumerate(self.drafts)
                if draft.serial == selected_serial
            ),
            0,
        )
        if self.drafts:
            self.table.selectRow(row)
        else:
            self.load_selected()
        self.participation_changed.emit()
        self.drafts_changed.emit()
        self.console.appendPlainText(
            f"{len(self.drafts)} Basler cameras discovered; no camera opened."
        )
        self.inventory_refreshed.emit()

    @property
    def selected(self) -> CameraDraft | None:
        row = self.table.currentRow()
        return self.drafts[row] if 0 <= row < len(self.drafts) else None

    @property
    def can_edit(self) -> bool:
        return self.view.can_edit

    @property
    def can_operate(self) -> bool:
        return (
            not self.operation_pending
            and self.view.phase == Phase.CONFIGURATION
            and (
                self.can_edit
                or self.managed
                and self.view.connected
                and self.view.has_control
            )
        )

    @property
    def can_edit_camera_settings(self) -> bool:
        return (
            self.can_edit
            or self.managed
            and self.can_operate
            and not any(c.connected for c in self.drafts)
        )

    def load_selected(self) -> None:
        draft = self.selected
        if self.preset_field.dialog is not None:
            self.preset_field.dialog.reject()
        self.loading = True
        for key, editor in self.fields.items():
            editor.setText(draft.values.get(key, "") if draft else "")
        self.preset.setText(draft.values.get("preset", "") if draft else "")
        self.role.setCurrentText(draft.role if draft else "Unassigned")
        self.trigger_source.setCurrentIndex(
            self.trigger_source.findText(draft.values.get("trigger_clock", ""))
            if draft
            else -1
        )
        self.loading = False
        self.refresh_controls()

    def edit(self, key: str, value: str) -> None:
        if (
            not self.loading
            and self.can_edit_camera_settings
            and (draft := self.selected)
        ):
            draft.values[key] = value
            if key == "preset":
                draft.values["pfs_imported"] = "no"
                draft.values.pop("trigger_clock", None)
                draft.values.pop("trigger_source", None)
                self.trigger_source.blockSignals(True)
                self.trigger_source.setCurrentIndex(-1)
                self.trigger_source.blockSignals(False)
            self.refresh_controls()
            self.drafts_changed.emit()

    def inspect_preset(self) -> None:
        draft = self.selected
        if not self.can_edit_camera_settings or not draft:
            return
        try:
            clock, source = trigger_hint(self.preset.text())
        except (OSError, UnicodeError, ValueError) as error:
            draft.values.pop("trigger_clock", None)
            draft.values.pop("trigger_source", None)
            self.trigger_source.setCurrentIndex(-1)
            self.console.appendPlainText(
                f"PFS trigger hint unavailable: {error}; camera settings not applied."
            )
        else:
            draft.values["trigger_source"] = source
            draft.values["trigger_clock"] = clock
            self.trigger_source.blockSignals(True)
            self.trigger_source.setCurrentText(clock)
            self.trigger_source.blockSignals(False)
            self.console.appendPlainText(
                f"PFS snapshot: {clock}, {source or 'source unspecified'}; not applied or verified on camera."
            )
            self.save_settings(import_preset=True)
        self.refresh_controls()
        self.drafts_changed.emit()

    def save_settings(self, *, import_preset: bool = False) -> None:
        draft = self.selected
        if self.loading or not self.managed or not self.can_operate or draft is None:
            return
        if draft.role == "Unassigned":
            return
        clock = draft.values.get("trigger_clock", "")
        if clock not in ("Internal clock", "External controller"):
            return
        if clock == "External controller" and not draft.values.get("trigger_source"):
            self.console.appendPlainText(
                "Select a PFS file with an explicit FrameStart line source to apply settings."
            )
            return
        rate = self.fields["trigger_frequency_hz"]
        if rate.text() and not rate.hasAcceptableInput():
            return
        signal = (
            self.preset_import_requested if import_preset else self.settings_requested
        )
        signal.emit(
            draft.serial,
            draft.values.get("trigger_clock", ""),
            draft.values.get("trigger_source", ""),
            draft.values.get("preset", ""),
            draft.values.get("trigger_frequency_hz", ""),
        )
        self.console.appendPlainText(
            f"Requested {draft.role} settings update; awaiting controller confirmation."
        )

    def set_participation(self, row: int, enabled: bool) -> None:
        draft = self.drafts[row]
        if self.managed and self.can_operate and draft.role != "Unassigned":
            self.pending_enable[draft.serial] = enabled
            self.enable_requested.emit(draft.serial, enabled)
            self.console.appendPlainText(
                f"Requested {draft.role} {'enable' if enabled else 'disable'}; awaiting controller confirmation."
            )
        elif self.can_edit:
            draft.enabled = enabled
            self.participation_changed.emit()
            self.drafts_changed.emit()
        self.refresh_controls()

    def assign_role(self, role: str) -> None:
        draft = self.selected
        if self.loading or not self.can_edit_camera_settings or draft is None:
            return
        if role != "Unassigned" and any(
            c is not draft and c.role == role for c in self.drafts
        ):
            self.role.blockSignals(True)
            self.role.setCurrentText(draft.role)
            self.role.blockSignals(False)
            self.console.appendPlainText(
                "Role unchanged: already assigned to another camera."
            )
            return
        if self.managed:
            self.role_requested.emit(draft.serial, role)
            return
        draft.role = role
        item = self.table.item(self.table.currentRow(), 2)
        assert item is not None
        item.setText(role)
        self.participation_changed.emit()
        self.drafts_changed.emit()
        self.refresh_controls()

    def toggle_connection(self) -> None:
        if self.can_operate and (draft := self.selected):
            if self.managed:
                self.connection_requested.emit(draft.key, not draft.connected)
                return
            draft.connected = not draft.connected
            draft.capture_running = draft.connected
            self.report("Connect" if draft.connected else "Disconnect")
            self.refresh_controls()
            self.preview_requested.emit(draft.key, draft.connected)

    def test_enabled(self) -> None:
        if not self.can_operate:
            return
        if self.managed:
            self.test_requested.emit()
            return
        for draft in self.drafts:
            if draft.enabled:
                if self.real_devices:
                    adapter = BaslerCameraAdapter()
                    try:
                        adapter.open(draft.serial)
                        identity = adapter.read_device_identity()
                        self.console.appendPlainText(
                            f"{draft.role} ({identity.physical_id}): opened and identified {identity.model}."
                        )
                    except Exception as exc:
                        self.console.appendPlainText(
                            f"{draft.role} ({draft.serial}): connection test failed: {exc}"
                        )
                    finally:
                        try:
                            adapter.close()
                        except Exception as exc:
                            self.console.appendPlainText(
                                f"{draft.role} ({draft.serial}): close unconfirmed: {exc}"
                            )
                    continue
                self.console.appendPlainText(
                    f"Review · Test connection requested for {draft.role} ({draft.serial}); "
                    "not tested — hardware checks are not integrated."
                )

    def report(self, action: str) -> None:
        draft = self.selected
        if not self.can_operate:
            return
        if action != "Refresh inventory" and (not draft or not draft.connected):
            if action not in {"Disconnect", "Stop capture"}:
                return
        self.console.appendPlainText(f"Review · {action}; no hardware command sent.")

    def apply_view(self, view: DashboardView) -> None:
        self.view = view
        self.refresh_controls()

    def refresh_controls(self) -> None:
        draft = self.selected
        self.refresh_button.setEnabled(
            not self.operation_pending and (self.can_operate or self.managed)
        )
        self.test_button.setEnabled(
            self.can_operate
            and (
                self.has_configured_tests
                if self.managed
                else any(c.enabled for c in self.drafts)
            )
        )
        preview = next(
            (p for p in self.view.previews if draft and p.key == draft.key), None
        )
        self.connect_button.setEnabled(
            self.can_operate
            and draft is not None
            and (not self.managed or bool(preview and preview.active))
        )
        self.connect_button.setText(
            "Disconnect" if draft and draft.connected else "Connect"
        )
        self.connect_button.setToolTip(
            "Stop capture and close the external preview"
            if draft and draft.connected
            else "Start capture and open the external preview"
        )
        for index, control in enumerate(self.enable_controls):
            camera = self.drafts[index]
            control.blockSignals(True)
            control.setChecked(self.pending_enable.get(camera.serial, camera.enabled))
            control.blockSignals(False)
            control.setAccessibleName(f"Enable {camera.role} for experiment")
            control.setEnabled(
                not self.pending_enable
                and (
                    self.can_edit
                    or self.managed
                    and self.can_edit_camera_settings
                    and camera.role != "Unassigned"
                )
            )
            control.setToolTip(
                "Awaiting controller confirmation"
                if camera.serial in self.pending_enable
                else "Assign this camera in controller configuration before enabling it"
                if self.managed and camera.role == "Unassigned"
                else "Enable for experiment"
            )
        for editor in (*self.fields.values(), self.preset_field, self.trigger_source):
            editor.setEnabled(self.can_edit_camera_settings and draft is not None)
        self.role.setEnabled(self.can_edit_camera_settings and draft is not None)
        self.status_column.hud.setPlainText(
            metrics_text(
                (
                    ("CAMERA", draft.serial if draft else "—"),
                    ("ROLE", draft.role if draft else "—"),
                    (
                        "EXPERIMENT",
                        "Enabled" if draft and draft.enabled else "Inactive",
                    ),
                    (
                        "CONNECTION",
                        "Open"
                        if self.managed and draft and draft.connected
                        else "Connected · review"
                        if draft and draft.connected
                        else "Not connected",
                    ),
                    (
                        "PREVIEW",
                        "Visible"
                        if self.managed and preview and preview.visible
                        else "Visible · review"
                        if preview and preview.visible
                        else "Hidden",
                    ),
                    (
                        "TRIGGER",
                        draft.values.get("trigger_clock", "") or "—" if draft else "—",
                    ),
                    (
                        "RATE (Hz)",
                        draft.values.get("trigger_frequency_hz", "") or "—"
                        if draft
                        else "—",
                    ),
                    (
                        "PFS",
                        "Imported · SDK readback"
                        if self.managed
                        and draft
                        and draft.values.get("pfs_imported") == "yes"
                        else "Selected · not applied"
                        if draft and draft.values.get("preset")
                        else "Not selected",
                    ),
                )
            )
        )
