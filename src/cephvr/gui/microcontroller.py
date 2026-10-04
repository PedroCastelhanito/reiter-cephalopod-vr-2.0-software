"""Serial inventory and local pin drafts; never open ports or drive outputs."""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtSerialPort import QSerialPortInfo
from PyQt6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from cephvr.gui.components import Card, button, combo, equal_row_height, label
from cephvr.gui.device_panel import DevicePanel, entry
from cephvr.gui.theme import SIZES
from cephvr.gui.view import DashboardView, Phase


@dataclass(frozen=True)
class CameraTrigger:
    key: str
    role: str
    source: str
    frequency: str
    enabled: bool = True


class MicrocontrollerPanel(DevicePanel):
    camera_enable_requested = pyqtSignal(str, bool)

    def __init__(self) -> None:
        super().__init__(
            "Microcontroller connection",
            "PORT        —\nFIRMWARE    —\nTRIGGER TEST Not tested",
            ("Scan ports", "Test connection"),
        )
        self.port = combo(())
        self.port.setPlaceholderText("Scan for ports")
        self.add("COM PORT", self.port)
        port_item = self.form.itemAtPosition(0, 0)
        assert port_item is not None
        port_field = port_item.widget()
        assert port_field is not None
        self.form.addWidget(port_field, 0, 0, 1, 2)
        self.camera_rows: tuple[CameraTrigger, ...] = ()
        self.pins: dict[str, str] = {}
        self.pin_editors: dict[str, QLineEdit] = {}
        self.can_test = False
        self.review_tests: set[str] = set()
        self.test_buttons: dict[str, QPushButton] = {}
        self.enable_controls: dict[str, QCheckBox] = {}
        self.triggers = Card("Outputs", compact=True)
        self.trigger_grid = QGridLayout()
        self.triggers.body.addLayout(self.trigger_grid)
        self.trial_pin = self.add_pin_row(
            self.trigger_grid, 0, "trial-state", "Trial state"
        )
        self.trial_pin.setToolTip("Trial state output is always active-high")
        self.io = Card("Inputs", compact=True)
        flip = QGridLayout()
        self.flip_pin = self.add_pin_row(flip, 0, "projector-flip", "Projector flip")
        self.flip_pin.setToolTip("Projector flip input always detects rising edges")
        self.io.body.addLayout(flip)
        layout = self.columns[0].layout()
        assert isinstance(layout, QVBoxLayout)
        layout.insertWidget(1, self.io)
        layout.insertWidget(2, self.triggers)
        self.port.currentIndexChanged.connect(self.port_changed)

    def add_pin_row(
        self, grid: QGridLayout, row: int, key: str, name: str
    ) -> QLineEdit:
        pin = entry("Pin")
        pin.setAccessibleName(f"{name} pin")
        pin.setMinimumWidth(70)
        test = button("Test", "compact")
        test.setAccessibleName(f"Test {name}")
        test.setProperty("signal_name", name)
        test.setMinimumWidth(70)
        test.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        test.setToolTip(
            "Listen for rising edges; never drive this input"
            if key == "projector-flip"
            else "Request an output test for observation in SpikeGLX"
        )
        test.clicked.connect(lambda: self.test_pin(key))
        pin.textChanged.connect(self.refresh_tests)
        self.test_buttons[key] = test
        enabled = QCheckBox()
        enabled.setChecked(True)
        enabled.setAccessibleName(f"Enable {name}")
        enabled.setToolTip("Include this signal in the experiment")
        self.enable_controls[key] = enabled
        enabled.toggled.connect(lambda checked: self.set_enabled(key, checked))
        grid.setHorizontalSpacing(SIZES.table_cell_padding)
        grid.setVerticalSpacing(SIZES.field_x_gap)
        grid.setColumnMinimumWidth(0, 28)
        grid.setColumnMinimumWidth(1, 120)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 2)
        grid.setColumnStretch(3, 2)
        grid.addWidget(enabled, row, 0, Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(label(name, wrap=True), row, 1)
        equal_row_height(pin, test)
        grid.addWidget(pin, row, 2)
        grid.addWidget(test, row, 3)
        return pin

    def set_enabled(self, key: str, enabled: bool) -> None:
        if not self.can_review:
            return
        if not enabled:
            self.stop_review_tests({key})
        if any(camera.key == key for camera in self.camera_rows):
            self.camera_enable_requested.emit(key, enabled)
        self.refresh_tests()

    def request(self, name: str) -> None:
        if not self.can_review:
            return
        if name == "Scan ports":
            self.stop_review_tests()
            current = self.port.currentData()
            self.port.clear()
            seen = set()
            for port in QSerialPortInfo.availablePorts():
                name = port.portName().upper()
                if not re.fullmatch(r"COM[1-9][0-9]*", name) or name in seen:
                    continue
                seen.add(name)
                self.port.addItem(
                    name,
                    port.systemLocation(),
                )
            self.port.setCurrentIndex(self.port.findData(current) if current else -1)
            self.port.setPlaceholderText(
                "Select a port" if self.port.count() else "No COM ports found"
            )
            self.console.appendPlainText(
                f"{self.port.count()} COM ports discovered; no hardware command sent."
            )
            return
        super().request(name)

    def set_cameras(self, cameras: tuple[CameraTrigger, ...]) -> None:
        if cameras == self.camera_rows:
            return
        self.stop_review_tests({c.key for c in self.camera_rows})
        for camera in self.camera_rows:
            self.test_buttons.pop(camera.key, None)
            self.enable_controls.pop(camera.key, None)
        self.camera_rows = cameras
        for index in reversed(range(self.trigger_grid.count())):
            if self.trigger_grid.getItemPosition(index)[0] > 0:
                item = self.trigger_grid.takeAt(index)
                if item and (widget := item.widget()):
                    widget.deleteLater()
        self.pin_editors = {}
        for row, camera in enumerate(cameras, 1):
            pin = self.add_pin_row(self.trigger_grid, row, camera.key, camera.role)
            self.pin_editors[camera.key] = pin
            control = self.enable_controls[camera.key]
            control.blockSignals(True)
            control.setChecked(camera.enabled)
            control.blockSignals(False)
            pin.setText(self.pins.get(camera.key, ""))
            pin.setToolTip("Set External controller in Cameras to use a trigger pin")
            pin.textChanged.connect(
                lambda value, key=camera.key: self.pins.__setitem__(key, value)
            )
        self.refresh_tests()

    def refresh_tests(self) -> None:
        if not hasattr(self, "flip_pin"):
            return
        active = bool(self.review_tests)
        self.port.setEnabled(self.can_review and not active)
        self.action_buttons[0].setEnabled(self.can_review and not active)
        for control in self.enable_controls.values():
            control.setEnabled(self.can_review)
        for key, editor in (
            ("trial-state", self.trial_pin),
            ("projector-flip", self.flip_pin),
        ):
            enabled = self.enable_controls[key].isChecked()
            editor.setEnabled(self.can_review and enabled and not active)
            self.test_buttons[key].setEnabled(
                self.can_test
                and enabled
                and bool(self.port.currentData())
                and bool(editor.text().strip())
            )
        for camera in self.camera_rows:
            if camera.key not in self.pin_editors:
                continue
            editor = self.pin_editors[camera.key]
            external = camera.enabled and camera.source == "External controller"
            editor.setEnabled(self.can_review and external and not active)
            self.test_buttons[camera.key].setEnabled(
                self.can_test
                and external
                and bool(self.port.currentData())
                and bool(editor.text().strip())
            )

    def port_changed(self) -> None:
        self.stop_review_tests()
        self.refresh_tests()

    def stop_review_tests(self, keys: set[str] | None = None) -> None:
        for key in tuple(
            self.review_tests if keys is None else self.review_tests & keys
        ):
            self.review_tests.remove(key)
            self.console.appendPlainText(
                f"Review · {key} test stopped locally; no hardware command sent."
            )
            self.update_test_button(key)

    def update_test_button(self, key: str) -> None:
        control = self.test_buttons[key]
        running = key in self.review_tests
        control.setText("Stop" if running else "Test")
        control.setAccessibleName(f"{control.text()} {control.property('signal_name')}")
        control.setProperty("role", "compact-stop" if running else "compact")
        style = control.style()
        if style is not None:
            style.unpolish(control)
            style.polish(control)
        control.update()

    def test_pin(self, key: str) -> None:
        if key in self.review_tests:
            self.stop_review_tests({key})
            self.refresh_tests()
            return
        if not self.can_test or not self.port.currentData():
            return
        cameras = {
            c.key: c
            for c in self.camera_rows
            if c.enabled and c.source == "External controller"
        }
        configured = {
            "trial-state": self.trial_pin.text().strip(),
            "projector-flip": self.flip_pin.text().strip(),
        }
        configured = {
            identity: pin
            for identity, pin in configured.items()
            if self.enable_controls[identity].isChecked()
        }
        configured.update(
            {
                identity: self.pin_editors[identity].text().strip()
                for identity in cameras
            }
        )
        pin = configured.get(key, "")
        if not pin:
            return
        if any(other != key and value == pin for other, value in configured.items()):
            self.console.appendPlainText(
                "Pin test: resolve duplicate camera / I/O pins."
            )
            return
        if key in cameras:
            camera = cameras[key]
            try:
                rate = Decimal(camera.frequency)
                valid = rate.is_finite() and rate > 0 and rate % Decimal("0.1") == 0
            except (InvalidOperation, ValueError):
                valid = False
            if not valid:
                self.console.appendPlainText(
                    f"Pin test: set a positive frequency on a 0.1 Hz grid for {camera.role} in Cameras."
                )
                return
            description = (
                f"{camera.role}: pin {pin}, requested {camera.frequency} Hz output test"
            )
        elif key == "trial-state":
            description = f"Trial state: pin {pin}, active-high output test"
        else:
            description = f"Projector flip: pin {pin}, rising-edge input observation"
        self.review_tests.add(key)
        self.update_test_button(key)
        self.refresh_tests()
        self.console.appendPlainText(
            f"Review · {description}; not tested — pin-test transport is not integrated, no command sent."
        )

    def apply_view(self, view: DashboardView) -> None:
        super().apply_view(view)
        self.can_test = self.can_review and view.phase == Phase.CONFIGURATION
        if not self.can_test:
            self.stop_review_tests()
        self.refresh_tests()
