"""Serial inventory and pin intents; managed actions use the controller."""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from PyQt6.QtCore import QSettings, QSignalBlocker, pyqtSignal
from PyQt6.QtSerialPort import QSerialPortInfo
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import Card, button, combo, equal_row_height, field
from cephvr.gui.device_panel import DevicePanel
from cephvr.gui.microcontroller_signals import ROLE_OUTPUTS, MicrocontrollerSignals
from cephvr.gui.microcontroller_snapshot import MicrocontrollerSnapshot
from cephvr.gui.paths import PathField
from cephvr.gui.pin_numbers import PinNumber
from cephvr.gui.tables import DataTable, refresh_button
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
    draft_changed = pyqtSignal()
    connection_requested = pyqtSignal()
    firmware_requested = pyqtSignal(str)
    save_requested = pyqtSignal(str, str, bool, str, bool, object, object, object)
    pin_test_requested = pyqtSignal(str, bool)

    def __init__(self, *, settings: QSettings | None = None) -> None:
        super().__init__(
            "Microcontroller connection",
            "PORT        —\nFIRMWARE    —\nTRIGGER TEST Not tested",
            ("Test connection",),
        )
        self.port = combo(())
        self.port.setPlaceholderText("Scan for ports")
        self.scan_button = refresh_button("Refresh available COM ports")
        self.scan_button.clicked.connect(lambda: self.request("Scan ports"))
        self.test_connection_button = self.action_buttons[0]
        self.port_row = port_row = QWidget()
        port_layout = QHBoxLayout(port_row)
        port_layout.setContentsMargins(0, 0, 0, 0)
        port_layout.setSpacing(SIZES.field_x_gap)
        port_layout.addWidget(self.port, 1)
        port_layout.addWidget(self.scan_button)
        self.add("COM PORT", port_row)
        port_item = self.form.itemAtPosition(0, 0)
        assert port_item is not None
        port_field = port_item.widget()
        assert port_field is not None
        self.form.addWidget(port_field, 0, 0, 1, 2)
        self.firmware = PathField(
            title="Select Uno firmware sketch or image",
            placeholder="Firmware .ino or .hex file",
            file_filter="Uno firmware (*.ino *.hex)",
        )
        self.firmware.editor.filename_only = True
        self.upload = button(
            "Upload",
            hint="Compile an Arduino sketch if needed, then upload and verify Uno firmware during Configuration",
        )
        self.upload_pending = False
        self.upload_available = False
        firmware_row = QWidget()
        firmware_layout = QHBoxLayout(firmware_row)
        firmware_layout.setContentsMargins(0, 0, 0, 0)
        firmware_layout.addWidget(self.firmware, 1)
        firmware_layout.addWidget(self.upload)
        equal_row_height(self.firmware.editor, self.firmware.browse, self.upload)
        self.form.addWidget(field("FIRMWARE", firmware_row), 1, 0, 1, 2)
        self.upload.clicked.connect(self.request_upload)
        if settings is not None:
            self.firmware.editor.setText(
                str(settings.value("microcontroller/firmware_path", ""))
            )
            self.firmware.editor.textChanged.connect(
                lambda path: settings.setValue("microcontroller/firmware_path", path)
            )
        self.firmware.editor.textChanged.connect(self.refresh_tests)
        self.camera_rows: tuple[CameraTrigger, ...] = ()
        self.pins: dict[str, str] = {}
        self.pin_editors: dict[str, QLineEdit] = {}
        self.role_rows: dict[str, int] = {}
        self.output_remove: dict[str, QPushButton] = {}
        self.can_test = False
        self.managed = False
        self.simulated_inventory = False
        self.managed_test_key = ""
        self.pending_test_key = ""
        self.connection_pending = False
        self.review_tests: set[str] = set()
        self.test_buttons: dict[str, QPushButton] = {}
        self.enable_controls: dict[str, QCheckBox] = {}
        self.triggers = Card("Outputs", compact=True)
        self.output_table = self.pin_table("Output")
        self.triggers.body.addWidget(self.output_table)
        self.trial_pin = self.add_pin_row(
            self.output_table, 0, "trial-state", "Trial state"
        )
        self.trial_pin.setToolTip("Trial state output is always active-high")
        self.trial_pin.setPlaceholderText("2–13")
        for row, (key, name) in enumerate(ROLE_OUTPUTS, 1):
            editor = self.add_pin_row(
                self.output_table, row, key, name, use_control=False
            )
            self.role_rows[key] = row
            self.pin_editors[key] = editor
            self.pins[key] = ""
            editor.textChanged.connect(
                lambda value, role_key=key: self.pins.__setitem__(role_key, value)
            )
            editor.textChanged.connect(self.mark_draft_changed)
            self.output_remove[key] = button(
                "×", "compact", hint="Remove this MCU role output"
            )
            self.output_remove[key].setAccessibleName(f"Remove {name} output")
            self.output_remove[key].clicked.connect(
                lambda _checked=False, role_key=key: (
                    self.signals.remove(role_key)
                    if hasattr(self, "signals")
                    else self.set_role_pin(role_key, "")
                )
            )
            self.output_table.set_control(row, 4, self.output_remove[key])
        self.io = Card("Inputs", compact=True)
        self.input_table = self.pin_table("Input")
        self.flip_pin = self.add_pin_row(
            self.input_table, 0, "projector-flip", "Projector flip"
        )
        self.flip_pin.setToolTip("Projector flip input always detects rising edges")
        self.flip_pin.setPlaceholderText("2 or 3")
        self.io.body.addWidget(self.input_table)
        layout = self.columns[0].layout()
        assert isinstance(layout, QVBoxLayout)
        self.io.hide()
        layout.insertWidget(2, self.triggers)
        self.port.currentIndexChanged.connect(self.port_changed)
        self.snapshots = MicrocontrollerSnapshot(self)
        self.config_files = self.snapshots.files
        for editor in (self.trial_pin, self.flip_pin):
            editor.textChanged.connect(self.mark_draft_changed)
        self.signals = MicrocontrollerSignals(self)
        self.refresh_tests()

    def request_upload(self) -> None:
        if self.upload.isEnabled():
            self.firmware_requested.emit(self.firmware.editor.text().strip())

    @staticmethod
    def pin_table(direction: str) -> DataTable:
        table = DataTable(0, 5)
        table.setHorizontalHeaderLabels(["Enable", direction, "Pin", "Test", ""])
        header = table.horizontalHeader()
        assert header is not None
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 72)
        return table

    def add_pin_row(
        self,
        table: DataTable,
        row: int,
        key: str,
        name: str,
        *,
        use_control: bool = True,
    ) -> QLineEdit:
        pin = PinNumber()
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
            else "Drive an output until Stop is clicked; observe the receiving device"
        )
        test.clicked.connect(lambda: self.test_pin(key))
        pin.textChanged.connect(self.refresh_tests)
        pin.editingFinished.connect(self.save_pins)
        pin.editingFinished.connect(self.refresh_tests)
        self.test_buttons[key] = test
        enabled: QWidget
        if use_control:
            enabled = QCheckBox()
            enabled.setChecked(True)
            enabled.setAccessibleName(f"Enable {name}")
            enabled.setToolTip("Include this signal in the experiment")
            self.enable_controls[key] = enabled
            enabled.toggled.connect(lambda checked: self.set_enabled(key, checked))
        else:
            enabled = QWidget()
            enabled.setFixedWidth(52)
        table.setRowCount(max(table.rowCount(), row + 1))
        table.set_control(row, 0, enabled)
        table.setItem(row, 1, QTableWidgetItem(name))
        equal_row_height(pin, test)
        table.set_control(row, 2, pin)
        table.set_control(row, 3, test)
        table.fit_rows()
        return pin

    def set_enabled(self, key: str, enabled: bool) -> None:
        if not self.can_review:
            return
        if not enabled:
            self.stop_review_tests({key})
        self.save_pins()
        self.refresh_tests()

    def request(self, name: str) -> None:
        if not self.can_review:
            return
        if name == "Scan ports":
            self.scan_ports()
            return
        if self.managed and name == "Test connection":
            if not self.port.currentData():
                self.console.appendPlainText(
                    "Select a COM port before testing connection."
                )
                return
            self.console.appendPlainText(f"Connecting to {self.port.currentData()}…")
            self.connection_requested.emit()
            return
        super().request(name)

    def scan_ports(self) -> None:
        """List ports without opening them; managed startup may call this directly."""
        with QSignalBlocker(self.port):
            self._scan_ports()

    def _scan_ports(self) -> None:
        self.stop_review_tests()
        current = self.port.currentData()
        self.port.clear()
        if self.simulated_inventory:
            self.port.addItem("Simulated Arduino Uno", "SIM-UNO")
            self.port.setCurrentIndex(0)
            self.console.appendPlainText(
                "Simulated microcontroller available; no hardware command sent."
            )
            self.refresh_tests()
            return
        seen = set()
        for port in QSerialPortInfo.availablePorts():
            name = port.portName().upper()
            if not re.fullmatch(r"COM[1-9][0-9]*", name) or name in seen:
                continue
            seen.add(name)
            description = port.description().strip()
            label = (
                f"{name} — {description}"
                if description and description != name
                else name
            )
            self.port.addItem(label, name)
        self.port.setCurrentIndex(self.port.findData(current) if current else -1)
        self.port.setPlaceholderText(
            "Select a port" if self.port.count() else "No COM ports found"
        )
        self.console.appendPlainText(
            f"{self.port.count()} COM ports discovered; no hardware command sent."
        )
        self.refresh_tests()

    def save_pins(self) -> None:
        self.mark_draft_changed()

    def mark_draft_changed(self) -> None:
        if hasattr(self, "snapshots"):
            self.snapshots.draft_loaded = True
        self.draft_changed.emit()

    def set_role_pin(self, key: str, pin: str) -> None:
        if key not in self.pin_editors or not self.can_review:
            return
        self.pin_editors[key].setText(pin)
        self.pins[key] = pin
        self.mark_draft_changed()

    def set_saved_pins(
        self,
        port: str,
        trial_pin: str,
        trial_enabled: bool,
        flip_pin: str,
        flip_enabled: bool,
    ) -> None:
        with QSignalBlocker(self.port):
            if port and self.port.findData(port) < 0:
                self.port.addItem(port, port)
            self.port.setCurrentIndex(self.port.findData(port) if port else -1)
        for key, editor, pin, enabled in (
            ("trial-state", self.trial_pin, trial_pin, trial_enabled),
            ("projector-flip", self.flip_pin, flip_pin, False),
        ):
            editor.setText(pin)
            control = self.enable_controls[key]
            control.blockSignals(True)
            control.setChecked(enabled)
            control.blockSignals(False)
        self.refresh_tests()

    def set_diagnostic(self, key: str, active: bool, edges: int) -> None:
        previous = self.managed_test_key
        self.pending_test_key = ""
        self.managed_test_key = key if active else ""
        for changed in {previous, key}:
            if changed in self.test_buttons:
                self.update_test_button(changed)
        if key:
            state = "running" if active else "stopped"
            if key == "projector-flip":
                result = f"{state}, {edges} rising edges reported"
            elif key == "trial-state":
                result = (
                    f"output {'HIGH' if active else 'LOW'}, "
                    f"{edges} rising transitions generated by MCU"
                )
            else:
                result = (
                    f"pulse output {state}, {edges} rising transitions generated by MCU"
                )
            # Polls update live counts; only lifecycle changes belong in the console.
            if not active or previous != key:
                self.console.appendPlainText(f"{key}: {result}.")
                if active and key != "projector-flip":
                    self.console.appendPlainText(
                        "MCU counts generated transitions; use the receiving device to "
                        "verify voltage, physical pulse timing and reception."
                    )
            lines = [
                line
                for line in self.status_column.hud.toPlainText().splitlines()
                if not line.startswith("TRIGGER TEST")
            ]
            lines.append(f"TRIGGER TEST {key}: {result}")
            self.status_column.hud.setPlainText("\n".join(lines))
        self.refresh_tests()

    def set_test_failure(self, key: str, message: str) -> None:
        self.pending_test_key = ""
        self.console.appendPlainText(f"{key}: {message}")
        self.refresh_tests()

    def set_cameras(self, cameras: tuple[CameraTrigger, ...]) -> None:
        if cameras == self.camera_rows:
            return
        self.signals.invalidate()
        self.stop_review_tests()
        self.camera_rows = cameras
        self.refresh_tests()

    def refresh_tests(self) -> None:
        if not hasattr(self, "flip_pin"):
            return
        if hasattr(self, "snapshots"):
            self.snapshots.refresh()
        active = bool(
            self.review_tests
            or self.managed_test_key
            or self.pending_test_key
            or self.connection_pending
        )
        exclusive_active = bool(
            self.managed_test_key
            or self.pending_test_key
            or self.connection_pending
            or self.upload_pending
        )
        self.firmware.setEnabled(self.can_review and not active)
        self.upload.setText("Uploading…" if self.upload_pending else "Upload")
        self.upload.setEnabled(
            self.managed
            and self.can_review
            and self.upload_available
            and not active
            and bool(self.port.currentData())
            and bool(self.firmware.editor.text().strip())
        )
        self.upload.setToolTip(
            "Compile if needed, upload and verify Uno firmware"
            if self.managed
            else "Firmware upload requires the managed runtime"
        )
        self.port_row.setEnabled(self.can_review and not active)
        self.port.setEnabled(self.can_review and not active)
        self.scan_button.setEnabled(self.can_review and not active)
        self.test_connection_button.setEnabled(
            self.can_review and not active and bool(self.port.currentData())
        )
        for control in self.enable_controls.values():
            control.setEnabled(self.can_review and (not self.managed or not active))
        for key, editor in (
            ("trial-state", self.trial_pin),
            ("projector-flip", self.flip_pin),
        ):
            enabled = self.enable_controls[key].isChecked()
            editor.setEnabled(self.can_review and enabled and not active)
            self.test_buttons[key].setEnabled(
                self.can_test
                and enabled
                and not self.connection_pending
                and (not exclusive_active or key == self.managed_test_key)
                and bool(self.port.currentData())
                and bool(editor.text().strip())
            )
        for key, editor in self.pin_editors.items():
            camera = next(
                (c for c in self.camera_rows if c.role == self.role_name(key)), None
            )
            editor.setEnabled(self.can_review and not active)
            if camera is None:
                self.test_buttons[key].setEnabled(False)
                self.test_buttons[key].setToolTip(
                    f"Assign {self.role_name(key)} and set a positive trigger rate before testing."
                )
                continue
            rate_ready = self.valid_trigger_rate(camera.frequency)
            self.test_buttons[key].setEnabled(
                self.can_test
                and rate_ready
                and not self.connection_pending
                and (not exclusive_active or key == self.managed_test_key)
                and bool(self.port.currentData())
                and bool(editor.text().strip())
            )
            self.test_buttons[key].setToolTip(
                "MCU pulse test is ready"
                if rate_ready
                else f"Set a positive 0.1 Hz-grid trigger rate for {camera.role} in Cameras."
            )

        if hasattr(self, "signals"):
            self.signals.refresh(
                self.can_review and not active and not self.upload_pending
            )

    def port_changed(self) -> None:
        self.stop_review_tests()
        self.refresh_tests()
        self.mark_draft_changed()

    @staticmethod
    def role_name(key: str) -> str:
        return dict(ROLE_OUTPUTS).get(key, "")

    @staticmethod
    def role_key(role: str) -> str:
        return {name: key for key, name in ROLE_OUTPUTS}.get(role, "")

    @staticmethod
    def valid_trigger_rate(value: str) -> bool:
        try:
            rate = Decimal(value)
            return rate.is_finite() and rate > 0 and rate % Decimal("0.1") == 0
        except (InvalidOperation, ValueError):
            return False

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
        running = key in self.review_tests or key == self.managed_test_key
        control.setText("Stop" if running else "Test")
        control.setAccessibleName(f"{control.text()} {control.property('signal_name')}")
        control.setProperty("role", "compact-stop" if running else "compact")
        style = control.style()
        if style is not None:
            style.unpolish(control)
            style.polish(control)
        control.update()

    def test_pin(self, key: str) -> None:
        if key == "projector-flip":
            return
        if self.managed and key == self.managed_test_key:
            self.pin_test_requested.emit(key, False)
            return
        if key in self.review_tests:
            self.stop_review_tests({key})
            self.refresh_tests()
            return
        if not self.can_test or not self.port.currentData():
            return
        cameras = {
            self.role_key(c.role): c for c in self.camera_rows if self.role_key(c.role)
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
        for camera in self.camera_rows:
            role_key = self.role_key(camera.role)
            if role_key and (
                role_key == key
                or camera.enabled
                and camera.source == "External controller"
            ):
                configured[role_key] = self.pin_editors[role_key].text().strip()
        pin = configured.get(key, "")
        if not pin:
            return
        normalized_pin = pin.upper().removeprefix("D")
        if any(
            other != key and value.upper().removeprefix("D") == normalized_pin
            for other, value in configured.items()
        ):
            self.console.appendPlainText(
                "Pin test: resolve duplicate camera / I/O pins."
            )
            return
        if key in self.pin_editors:
            trigger = cameras.get(key)
            if trigger is None:
                self.test_buttons[key].setToolTip(
                    f"Assign {self.role_name(key)} and set a positive trigger rate before testing."
                )
                self.console.appendPlainText(
                    f"Pin test: assign {self.role_name(key)} to a camera and set its trigger frequency in Cameras first."
                )
                return
            if not self.valid_trigger_rate(trigger.frequency):
                self.console.appendPlainText(
                    f"Pin test: set a positive frequency on a 0.1 Hz grid for {trigger.role} in Cameras."
                )
                return
            description = f"{trigger.role}: pin {pin}, requested {trigger.frequency} Hz output test"
        elif key == "trial-state":
            description = f"Trial state: pin {pin}, active-high output test"
        else:
            description = f"Projector flip: pin {pin}, rising-edge input observation"
        if self.managed:
            self.pin_test_requested.emit(key, True)
            return
        self.review_tests.add(key)
        self.update_test_button(key)
        self.refresh_tests()
        self.console.appendPlainText(
            f"Review · {description}; not tested, no command sent. Use the managed runtime to test pins."
        )

    def apply_view(self, view: DashboardView) -> None:
        super().apply_view(view)
        if self.managed:
            self.can_review = (
                view.connected
                and view.has_control
                and view.phase == Phase.CONFIGURATION
            )
        self.can_test = self.can_review and view.phase == Phase.CONFIGURATION
        if not self.can_test:
            self.stop_review_tests()
        self.refresh_tests()
