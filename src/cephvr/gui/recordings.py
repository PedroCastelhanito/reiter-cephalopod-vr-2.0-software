"""Session recording choices, independent of the protocol editor's layout."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QGridLayout, QLabel, QSizePolicy

from cephvr.gui.cameras import CamerasPanel
from cephvr.gui.components import Card, label
from cephvr.gui.editing_card import EditingCard
from cephvr.gui.theme import SIZES
from cephvr.gui.view import DashboardView


class RecordingsCard(Card):
    changed = pyqtSignal()

    def __init__(self, cameras: CamerasPanel, spikeglx: QCheckBox) -> None:
        super().__init__("Saving options")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.cameras = cameras
        self.can_edit = False
        self.body.setSpacing(SIZES.group_gap)
        self.data_group, self.video_group = EditingCard("Data"), EditingCard("Videos")
        self.data_grid, self.video_grid = QGridLayout(), QGridLayout()
        for group, grid in (
            (self.data_group, self.data_grid),
            (self.video_group, self.video_grid),
        ):
            group.body.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(10)
            grid.setColumnMinimumWidth(2, 24)
            group.body.addLayout(grid)
            self.body.addWidget(group)
        self.video_heading = self.video_group.caption
        self.data_heading = self.data_group.caption
        self.record: dict[str, QCheckBox] = {}
        self.source_labels: dict[str, QLabel] = {}
        self.touched: set[str] = set()
        self.add_recording("stimulus", "Visual stimulus video")
        self.velocities = QCheckBox()
        self.velocities.setAccessibleName("Save tracking velocities")
        self.velocity_label = label("Save tracking velocities", wrap=True)
        self.spikeglx = spikeglx
        self.spikeglx.setText("")
        self.spikeglx.setAccessibleName("Save spikeglx")
        self.spikeglx_label = label("Save spikeglx", wrap=True)
        self.velocities.setChecked(False)
        self.velocities.toggled.connect(lambda _checked: self._touch("velocities"))
        cameras.drafts_changed.connect(self.sync_cameras)
        self.sync_cameras()

    def add_recording(self, key: str, name: str) -> None:
        name = f"Save {name}" if name.endswith(" video") else f"Save {name} video"
        caption = label(name, wrap=True)
        self.source_labels[key] = caption
        record = QCheckBox()
        record.setAccessibleName(name)
        record.setChecked(True)
        record.toggled.connect(lambda _checked, field=key: self._touch(field))
        self.record[key] = record

    def _touch(self, key: str) -> None:
        self.touched.add(key)
        self.recording_changed()

    def install_values(self, values: dict[str, bool | None]) -> None:
        """Install saved choices while keeping absence distinct from false."""
        self.touched.clear()
        for key, control in self.record.items():
            control.blockSignals(True)
            control.setChecked(
                bool(values.get(key)) if values.get(key) is not None else False
            )
            control.blockSignals(False)
        self.velocities.blockSignals(True)
        self.velocities.setChecked(
            bool(values.get("velocities"))
            if values.get("velocities") is not None
            else False
        )
        self.velocities.blockSignals(False)

    def sync_cameras(self) -> None:
        for camera in self.cameras.drafts:
            if camera.key not in self.record:
                self.add_recording(camera.key, camera.role)
        for grid in (self.data_grid, self.video_grid):
            while grid.count():
                grid.takeAt(0)
        video_items = [
            (self.source_labels[key], control)
            for key, control in self.record.items()
            if key != "stimulus"
        ]
        video_items.append((self.source_labels["stimulus"], self.record["stimulus"]))
        data_items = [
            (self.velocity_label, self.velocities),
            (self.spikeglx_label, self.spikeglx),
        ]
        for grid, items in (
            (self.data_grid, data_items),
            (self.video_grid, video_items),
        ):
            for index, (caption, control) in enumerate(items):
                column = (index % 2) * 3
                grid.addWidget(control, index // 2, column)
                grid.addWidget(caption, index // 2, column + 1)
                grid.setColumnStretch(column + 1, 1)
        self.refresh_controls()

    def recording_changed(self) -> None:
        self.refresh_controls()
        self.changed.emit()

    def refresh_controls(self) -> None:
        self.velocities.setEnabled(self.can_edit)
        active = {}
        for camera in self.cameras.drafts:
            active[camera.key] = camera.enabled
            if camera.key in self.record:
                self.source_labels[camera.key].setText(f"Save {camera.role} video")
                self.record[camera.key].setAccessibleName(f"Save {camera.role} video")
        active["stimulus"] = True
        for key, control in self.record.items():
            control.setEnabled(self.can_edit and active.get(key, False))

    def apply_view(self, view: DashboardView) -> None:
        self.can_edit = view.can_edit
        self.refresh_controls()
