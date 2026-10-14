"""Devices presentation draft; edits stay local and actions never call hardware."""

from PyQt6.QtCore import QSettings, QSignalBlocker, QSize, Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.cameras import CamerasPanel
from cephvr.gui.components import Card
from cephvr.gui.icons import device_icon
from cephvr.gui.layouts import column
from cephvr.gui.mcu_wiring_editor import McuWiringEditor
from cephvr.gui.microcontroller import CameraTrigger, MicrocontrollerPanel
from cephvr.gui.microcontroller_signals import ROLE_OUTPUTS
from cephvr.gui.projectors import ProjectorsPanel
from cephvr.gui.spikeglx import SpikeGLXPanel
from cephvr.gui.theme import SIZES
from cephvr.gui.view import DashboardView


class DevicesPage(QWidget):
    def __init__(
        self, *, sample: bool = False, settings: QSettings | None = None
    ) -> None:
        super().__init__()
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(SIZES.card_gap)
        self.tabs = QStackedWidget()
        self.tab_bar = QTabBar()
        self.tab_bar.setIconSize(QSize(20, 20))
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setExpanding(True)
        self.tab_bar.setUsesScrollButtons(False)
        self.tab_bar.setElideMode(Qt.TextElideMode.ElideRight)
        self.tab_bar.currentChanged.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(self.tab_bar.setCurrentIndex)
        body.addWidget(self.tabs, 1)
        self.cameras = CamerasPanel(sample=sample)
        self.microcontroller = MicrocontrollerPanel(settings=settings)
        self.wiring_dialog: McuWiringEditor | None = None
        self.wiring_identity: tuple[object, ...] | None = None
        self.cameras.drafts_changed.connect(self.sync_cameras)
        self.cameras.drafts_changed.connect(self.sync_wiring_status)
        self.cameras.table.currentCellChanged.connect(
            lambda *_: self.sync_wiring_status()
        )
        self.cameras.drafts_changed.connect(self.invalidate_wiring_editor)
        self.cameras.inventory_refreshed.connect(self.invalidate_wiring_editor)
        self.cameras.table.currentCellChanged.connect(
            lambda *_: self.invalidate_wiring_editor()
        )
        self.cameras.wiring_requested.connect(self.edit_camera_wiring)
        self.microcontroller.snapshots.camera_available = (
            self.cameras.snapshots.available
        )
        self.microcontroller.connection_requested.connect(self.invalidate_wiring_editor)
        self.microcontroller.pin_test_requested.connect(
            lambda *_: self.invalidate_wiring_editor()
        )
        self.microcontroller.firmware_requested.connect(
            lambda *_: self.invalidate_wiring_editor()
        )
        self.sync_cameras()
        self.projectors = ProjectorsPanel(settings=settings)
        self.microcontroller.port.currentIndexChanged.connect(self.sync_wiring_status)
        for editor in self.microcontroller.pin_editors.values():
            editor.textChanged.connect(self.sync_wiring_status)
        self.sync_wiring_status()
        self.spikeglx = SpikeGLXPanel()
        self.panels = (
            self.cameras,
            self.microcontroller,
            self.projectors,
            self.spikeglx,
        )
        self.cameras.drafts_changed.connect(self.sync_inputs)
        self.projectors.timing.pulse.toggled.connect(self.sync_inputs)
        for key in ("trial-state", "projector-flip"):
            self.microcontroller.enable_controls[key].toggled.connect(self.sync_inputs)
        self.sync_inputs()
        self.microcontroller.config_files.loaded.connect(self.sync_inputs)
        self.spikeglx.config_files.loaded.connect(self.sync_inputs)
        self.config_cards: list[Card] = []
        for name, icon, panel in zip(
            ("Cameras", "Microcontroller", "Projectors", "SpikeGLX"),
            ("camera", "board", "projector", "signal"),
            self.panels,
            strict=True,
        ):
            config_card = Card("Configuration file")
            self.config_cards.append(config_card)
            if isinstance(panel, ProjectorsPanel):
                config_card.body.addWidget(panel.calibration_files)
            else:
                assert isinstance(
                    panel, (CamerasPanel, MicrocontrollerPanel, SpikeGLXPanel)
                )
                files = panel.config_files
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(SIZES.field_x_gap)
                row.addWidget(files.load_button, 1)
                row.addWidget(files.save_button, 1)
                config_card.body.addLayout(row)
            left = panel.columns[0].layout()
            assert isinstance(left, QVBoxLayout)
            left.insertWidget(0, config_card)
            self.tabs.addWidget(panel)
            self.tab_bar.addTab(device_icon(icon), name)
        self.navigation, navigation_layout = column()
        caption = self.cameras.status_column.hud_card.caption
        navigation_layout.setContentsMargins(0, caption.sizeHint().height() // 2, 0, 0)
        navigation_layout.addWidget(self.tab_bar)
        self.tabs.currentChanged.connect(self.place_navigation)
        self.place_navigation(self.tabs.currentIndex())

    def place_navigation(self, index: int) -> None:
        layout = self.panels[index].columns[0].layout()
        assert isinstance(layout, QVBoxLayout)
        layout.insertWidget(0, self.navigation)
        self.navigation.show()

    def _port_options(self) -> tuple[tuple[str, str], ...]:
        panel = self.microcontroller
        return tuple(
            (panel.port.itemText(index), str(panel.port.itemData(index) or ""))
            for index in range(panel.port.count())
        )

    def _mcu_wiring_editable(self) -> bool:
        panel = self.microcontroller
        return panel.can_review and not (
            panel.review_tests
            or panel.managed_test_key
            or panel.pending_test_key
            or panel.connection_pending
            or panel.upload_pending
        )

    def invalidate_wiring_editor(self) -> None:
        if self.wiring_dialog is not None:
            self.wiring_dialog.reject()

    def edit_camera_wiring(self) -> None:
        camera = self.cameras.selected
        if (
            camera is None
            or camera.connected
            or not self.cameras.can_edit_camera_settings
            or not self._mcu_wiring_editable()
        ):
            return
        role_key = self.microcontroller.role_key(camera.role)
        if not role_key:
            return
        camera_key, camera_role = camera.key, camera.role
        inventory = tuple(
            (item.key, item.serial, item.role) for item in self.cameras.drafts
        )
        editor = McuWiringEditor(
            parent=self,
            title=f"{camera_role} MCU wiring",
            port_values=self._port_options(),
            port=str(self.microcontroller.port.currentData() or ""),
            pin=self.microcontroller.pin_editors[role_key].text(),
            pin_label=f"{dict(ROLE_OUTPUTS)[role_key]} output pin (2–13)",
            role=role_key,
            save=lambda port, pin, selected_role, _enabled: self._apply_wiring(
                port, pin, selected_role, camera_key, camera_role, inventory
            ),
        )
        self.wiring_dialog = editor
        self.wiring_identity = ("camera", camera_key, camera_role, inventory)
        try:
            editor.exec()
        finally:
            self.wiring_dialog = None
            self.wiring_identity = None
            editor.deleteLater()

    def _apply_wiring(
        self,
        port: str,
        pin: str,
        role_key: str,
        camera_key: str = "",
        camera_role: str = "",
        inventory: tuple[tuple[str, str, str], ...] = (),
    ) -> None:
        panel = self.microcontroller
        if not self._mcu_wiring_editable():
            return
        camera = self.cameras.selected
        current_inventory = tuple(
            (item.key, item.serial, item.role) for item in self.cameras.drafts
        )
        if (
            camera is None
            or camera.key != camera_key
            or camera.role != camera_role
            or current_inventory != inventory
            or self.wiring_identity != ("camera", camera_key, camera_role, inventory)
            or camera.connected
            or not self.cameras.can_edit_camera_settings
        ):
            return
        if role_key not in panel.pin_editors:
            return
        blocker = QSignalBlocker(panel.port)
        try:
            if port and panel.port.findData(port) < 0:
                panel.port.addItem(port, port)
            panel.port.setCurrentIndex(panel.port.findData(port) if port else -1)
        finally:
            del blocker
        panel.pin_editors[role_key].setText(pin)
        panel.pins[role_key] = pin
        panel.snapshots.draft_loaded = True
        panel.draft_changed.emit()
        panel.refresh_tests()
        self.sync_wiring_status()

    def sync_wiring_status(self) -> None:
        panel = self.microcontroller
        port = str(panel.port.currentData() or "").strip()
        role = self.microcontroller.role_key(
            self.cameras.selected.role if self.cameras.selected else ""
        )
        role_pin = panel.pin_editors[role].text().strip() if role else ""
        camera_missing = []
        if not role:
            camera_missing.append("assign a camera role")
        if not port:
            camera_missing.append("select MCU COM port")
        if not role_pin:
            camera_missing.append("assign this role's MCU output pin")
        self.cameras.wiring_button.setToolTip(
            "Camera trigger wiring prerequisite: "
            + (
                "; ".join(camera_missing)
                if camera_missing
                else f"{port}, pin {role_pin}"
            )
        )

    def sync_cameras(self) -> None:
        if self.cameras.snapshot_draft:
            self.microcontroller.snapshots.draft_loaded = True
        self.microcontroller.set_cameras(
            tuple(
                CameraTrigger(
                    c.key,
                    c.role,
                    c.values.get("trigger_clock", ""),
                    c.values.get("trigger_frequency_hz", ""),
                    c.enabled,
                )
                for c in self.cameras.drafts
            )
        )

    def sync_inputs(self) -> None:
        sources = [(c.key, c.role, c.enabled) for c in self.cameras.drafts]
        sources.extend(
            (key, name, self.microcontroller.enable_controls[key].isChecked())
            for key, name in (("trial-state", "Trial state"),)
        )
        if self.projectors.timing.pulse.isChecked():
            sources.append(("photodiode", "Photodiode", True))
        self.spikeglx.set_sources(
            tuple(sources), frozenset(c.key for c in self.cameras.drafts)
        )

    def apply_view(self, view: DashboardView) -> None:
        for panel in self.panels:
            panel.apply_view(view)
        if not self._mcu_wiring_editable():
            self.invalidate_wiring_editor()
        self.sync_wiring_status()
