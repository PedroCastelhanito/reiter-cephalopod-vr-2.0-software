"""Local pulse-inventory drafts; remote saved-channel validation belongs to E12."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import Card, button, combo, label
from cephvr.gui.device_panel import DevicePanel, entry
from cephvr.gui.view import DashboardView


class SpikeGLXPanel(DevicePanel):
    connection_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(
            "SpikeGLX connection",
            "SERVER      —\nVERSION     —\nACQUISITION Unknown\nSTREAMS     —",
            ("Test connection",),
        )
        self.pairing = QCheckBox("Enable SpikeGLX control")
        self.pairing.setChecked(True)
        self.pairing.setToolTip(
            "Include SpikeGLX pairing in the experiment; local draft only"
        )
        self.configuration.body.insertWidget(1, self.pairing)
        self.add("HOST", entry("SpikeGLX computer address"))
        self.add("COMMAND PORT", entry("Command server port"))
        self.mapping = Card("Input channels")
        self.mapping_grid = QGridLayout()
        self.mapping_grid.setHorizontalSpacing(8)
        for col, text in enumerate(("USE", "SIGNAL", "INDEX", "CHANNEL", "")):
            self.mapping_grid.addWidget(label(text, "label"), 0, col)
        self.mapping_grid.setColumnStretch(1, 2)
        self.mapping_grid.setColumnStretch(2, 1)
        self.mapping.body.addLayout(self.mapping_grid)
        self.rows: dict[str, tuple[QWidget, ...]] = {}
        self.active: dict[str, bool] = {}
        self.enable_controls: dict[str, QCheckBox] = {}
        self.remove_buttons: dict[str, QPushButton] = {}
        self.custom_count = 0
        self.add_input = button("Add input", "secondary")
        self.add_input.clicked.connect(self.add_custom)
        self.mapping.body.addWidget(self.add_input)
        layout = self.columns[0].layout()
        assert isinstance(layout, QVBoxLayout)
        layout.insertWidget(1, self.mapping)

    def add_row(self, key: str, name: str, *, custom: bool = False) -> None:
        signal = entry("Input name") if custom else label(name)
        stream = combo(("OneBox", "NI", "imec"))
        # Retain saved stream identity without exposing another mapping column.
        stream.setParent(self.mapping)
        stream.hide()
        index, channel = entry("0"), entry("Channel")
        for editor in (index, channel):
            editor.setMinimumWidth(0)
            editor.setMaximumWidth(80)
        channel.setToolTip("Saved SpikeGLX channel index")
        self.rows[key] = (signal, stream, index, channel)
        enabled = QCheckBox()
        enabled.setChecked(True)
        enabled.setAccessibleName(f"Record {name} input")
        enabled.toggled.connect(self.refresh_controls)
        self.enable_controls[key] = enabled
        row = self.mapping_grid.rowCount()
        self.mapping_grid.addWidget(enabled, row, 0)
        if custom:
            remove = button("×", "compact", hint="Remove this custom input")
            remove.setAccessibleName("Remove custom input")
            remove.clicked.connect(lambda: self.remove_custom(key))
            self.remove_buttons[key] = remove
            self.mapping_grid.addWidget(remove, row, 4)
        for col, control in enumerate(self.rows[key]):
            control.setAccessibleName(
                f"{name} {('signal', 'stream', 'index', 'channel')[col]}"
            )
        for col, control in enumerate((signal, index, channel), 1):
            self.mapping_grid.addWidget(control, row, col)
        self.active[key] = True

    def add_custom(self) -> None:
        if not self.can_review:
            return
        self.custom_count += 1
        self.add_row(f"custom:{self.custom_count}", "Other input", custom=True)
        self.refresh_controls()

    def remove_custom(self, key: str) -> None:
        if not self.can_review or key not in self.remove_buttons:
            return
        for control in (
            *self.rows.pop(key),
            self.enable_controls.pop(key),
            self.remove_buttons.pop(key),
        ):
            self.mapping_grid.removeWidget(control)
            control.deleteLater()
        self.active.pop(key)

    def set_sources(
        self, sources: tuple[tuple[str, str, bool], ...], camera_keys: frozenset[str]
    ) -> None:
        visible = {key for key, _, _ in sources}
        for key, name, active in sources:
            if key not in self.rows:
                self.add_row(key, name)
            signal = self.rows[key][0]
            if isinstance(signal, QLabel):
                signal.setText(name)
            if key in camera_keys:
                stream = self.rows[key][1]
                from PyQt6.QtWidgets import QComboBox

                assert isinstance(stream, QComboBox)
                while stream.count() > 1:
                    stream.removeItem(1)
            self.active[key] = active
        for key, controls in self.rows.items():
            for control in (controls[0], *controls[2:], self.enable_controls[key]):
                control.setVisible(key in visible or key.startswith("custom:"))
        self.refresh_controls()

    def refresh_controls(self) -> None:
        self.add_input.setEnabled(self.can_review)
        for key, controls in self.rows.items():
            toggle = self.enable_controls[key]
            toggle.setEnabled(self.can_review and self.active[key])
            for control in controls:
                control.setEnabled(
                    self.can_review and self.active[key] and toggle.isChecked()
                )
            if key in self.remove_buttons:
                self.remove_buttons[key].setEnabled(self.can_review)

    def apply_view(self, view: DashboardView) -> None:
        super().apply_view(view)
        self.action_buttons[0].setEnabled(view.connected and not view.sample)
        self.pairing.setEnabled(self.can_review)
        self.refresh_controls()

    def request(self, name: str) -> None:
        if self.can_review:
            super().request(name)
        elif name == "Test connection":
            self.connection_requested.emit()
