"""Session recording choices, independent of the protocol editor's layout."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QLabel

from cephvr.gui.cameras import CamerasPanel
from cephvr.gui.components import Card, label
from cephvr.gui.view import DashboardView


class RecordingsCard(Card):
    changed = pyqtSignal()

    def __init__(self, cameras: CamerasPanel) -> None:
        super().__init__("Recordings")
        self.cameras = cameras
        self.can_edit = False
        self.source_grid = QGridLayout()
        self.source_grid.setHorizontalSpacing(14)
        self.source_grid.setVerticalSpacing(12)
        self.body.addLayout(self.source_grid)
        self.record: dict[str, QCheckBox] = {}
        self.source_labels: dict[str, QLabel] = {}
        self.touched: set[str] = set()
        self.add_recording("stimulus", "Visual stimulus video")
        self.velocities = QCheckBox()
        self.velocities.setAccessibleName("Tracking velocities")
        self.velocity_label = label("Tracking velocities", wrap=True)
        self.velocities.setChecked(False)
        self.velocities.toggled.connect(lambda _checked: self._touch("velocities"))
        cameras.drafts_changed.connect(self.sync_cameras)
        self.sync_cameras()

    def add_recording(self, key: str, name: str) -> None:
        caption = label(name, wrap=True)
        self.source_labels[key] = caption
        record = QCheckBox()
        record.setAccessibleName(
            f"Record {name}" if name.endswith(" video") else f"Record {name} video"
        )
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
            self.source_labels[camera.key].setText(f"{camera.role} video")
            self.record[camera.key].setAccessibleName(f"Record {camera.role} video")
        while self.source_grid.count():
            item = self.source_grid.takeAt(0)
            if item is not None and (layout := item.layout()) is not None:
                while layout.count():
                    layout.takeAt(0)
                layout.deleteLater()
        items = [
            (self.source_labels[key], control) for key, control in self.record.items()
        ]
        items.append((self.velocity_label, self.velocities))
        for index, (caption, control) in enumerate(items):
            pair = QHBoxLayout()
            pair.setSpacing(8)
            pair.addWidget(control)
            pair.addWidget(caption, 1)
            self.source_grid.addLayout(pair, index // 2, index % 2)
            self.source_grid.setColumnStretch(index % 2, 1)
        self.refresh_controls()

    def recording_changed(self) -> None:
        self.refresh_controls()
        self.changed.emit()

    def refresh_controls(self) -> None:
        self.velocities.setEnabled(self.can_edit)
        active = {camera.key: camera.enabled for camera in self.cameras.drafts}
        active["stimulus"] = True
        for key, control in self.record.items():
            control.setEnabled(self.can_edit and active.get(key, False))

    def apply_view(self, view: DashboardView) -> None:
        self.can_edit = view.can_edit
        self.refresh_controls()
