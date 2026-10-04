"""Devices presentation draft; edits stay local and actions never call hardware."""

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import (
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.cameras import CamerasPanel
from cephvr.gui.icons import device_icon
from cephvr.gui.layouts import column
from cephvr.gui.microcontroller import CameraTrigger, MicrocontrollerPanel
from cephvr.gui.projectors import ProjectorsPanel
from cephvr.gui.spikeglx import SpikeGLXPanel
from cephvr.gui.theme import SIZES
from cephvr.gui.view import DashboardView


class DevicesPage(QWidget):
    def __init__(self, *, sample: bool = False) -> None:
        super().__init__()
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(SIZES.card_gap)
        self.tabs = QStackedWidget()
        self.tab_bar = QTabBar()
        self.tab_bar.setIconSize(QSize(20, 20))
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setExpanding(True)
        self.tab_bar.setUsesScrollButtons(True)
        self.tab_bar.currentChanged.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(self.tab_bar.setCurrentIndex)
        body.addWidget(self.tabs, 1)
        self.cameras = CamerasPanel(sample=sample)
        self.microcontroller = MicrocontrollerPanel()
        self.cameras.drafts_changed.connect(self.sync_cameras)
        self.microcontroller.camera_enable_requested.connect(self.set_camera_enabled)
        self.sync_cameras()
        self.projectors = ProjectorsPanel()
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
        for name, icon, panel in zip(
            ("Cameras", "Microcontroller", "Projectors", "SpikeGLX"),
            ("camera", "board", "projector", "signal"),
            self.panels,
            strict=True,
        ):
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

    def set_camera_enabled(self, key: str, enabled: bool) -> None:
        for row, camera in enumerate(self.cameras.drafts):
            if camera.key == key:
                self.cameras.set_participation(row, enabled)
                return

    def sync_cameras(self) -> None:
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
            for key, name in (
                ("trial-state", "Trial state"),
                ("projector-flip", "Projector flip"),
            )
        )
        if self.projectors.timing.pulse.isChecked():
            sources.append(("photodiode", "Photodiode", True))
        self.spikeglx.set_sources(
            tuple(sources), frozenset(c.key for c in self.cameras.drafts)
        )

    def apply_view(self, view: DashboardView) -> None:
        for panel in self.panels:
            panel.apply_view(view)
