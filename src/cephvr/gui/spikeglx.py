"""Local pulse-inventory drafts; remote saved-channel validation belongs to E12."""

from typing import cast

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import Card, button, combo, label
from cephvr.gui.device_panel import DevicePanel, entry
from cephvr.gui.spikeglx_snapshot import SpikeGLXSnapshot
from cephvr.gui.tables import DataTable
from cephvr.gui.theme import SIZES
from cephvr.gui.view import DashboardView
from cephvr.synchronization.v1 import spikeglx_pb2 as sync_pb


class SpikeGLXPanel(DevicePanel):
    connection_requested = pyqtSignal()
    inventory_update_requested = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__(
            "SpikeGLX connection",
            "SERVER      —\nVERSION     —\nACQUISITION Unknown\nSTREAMS     —",
            ("Test connection",),
        )
        self.pairing = QCheckBox("SpikeGLX pairing enabled")
        self.pairing.setChecked(False)
        self.pairing.setToolTip(
            "Read-only host setting from config/backends/synchronization_config.toml"
        )
        self.pairing.setEnabled(False)
        self.configuration.body.insertWidget(1, self.pairing)
        self.host_settings_note = QLabel(
            "Pairing and endpoint are read-only here; change them in "
            "config/backends/synchronization_config.toml."
        )
        self.host_settings_note.setWordWrap(True)
        self.host_settings_note.setToolTip(self.pairing.toolTip())
        self.configuration.body.insertWidget(2, self.host_settings_note)
        self.form.setContentsMargins(0, SIZES.section_toggle_gap, 0, 0)
        self.address = entry("Not loaded")
        self.address.setReadOnly(True)
        self.address.setToolTip("Read-only synchronization_config.toml setting")
        self.command_port = entry("Not loaded")
        self.command_port.setReadOnly(True)
        self.command_port.setToolTip("Read-only synchronization_config.toml setting")
        self.add("HOST", self.address)
        self.add("COMMAND PORT", self.command_port)
        self.mapping = Card("Input channels")
        self.table = DataTable(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Use", "Signal", "Stream", "Index", "Channel", "Bit", ""]
        )
        self.table.setColumnHidden(2, True)
        header = self.table.horizontalHeader()
        assert header is not None
        for column, width in ((0, 42), (2, 102), (3, 58), (4, 82), (5, 48), (6, 40)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(column, width)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.mapping.body.addWidget(self.table)
        self.row_keys: list[str] = []
        self.rows: dict[str, tuple[QWidget, ...]] = {}
        self.inventory_rows: dict[int, str] = {}
        self.row_roles: dict[str, int] = {}
        self.row_source_ids: dict[str, str] = {}
        self.inventory_file_sha256 = ""
        self.required_inventory_roles: frozenset[int] = frozenset()
        self.active_inventory_roles: frozenset[int] = frozenset()
        self.enable_controls: dict[str, QCheckBox] = {}
        self.remove_buttons: dict[str, QPushButton] = {}
        self.custom_count = 0
        self.add_input = button("Add input", "secondary")
        self.add_input.clicked.connect(self.add_custom)
        self.mapping.body.addWidget(self.add_input)
        self.save_inventory = button("Save pulse mapping", "secondary")
        self.save_inventory.clicked.connect(self.request_inventory_update)
        self.mapping.body.addWidget(self.save_inventory)
        layout = self.columns[0].layout()
        assert isinstance(layout, QVBoxLayout)
        layout.insertWidget(1, self.mapping)
        self.snapshots = SpikeGLXSnapshot(self)
        self.config_files = self.snapshots.files

    def add_row(self, key: str, name: str, *, custom: bool = False) -> None:
        signal = entry("Input name") if custom else label(name)
        stream = combo(("OneBox", "NI", "imec"))
        stream.setMinimumWidth(82)
        index, channel = entry("0"), entry("Channel")
        for editor in (index, channel):
            editor.setMinimumWidth(0)
        index.setMaximumWidth(58)
        channel.setMaximumWidth(82)
        channel.setToolTip("Saved SpikeGLX channel index")
        bit = entry("0–15")
        bit.setMinimumWidth(0)
        bit.setMaximumWidth(48)
        bit.setToolTip("Optional bit of a source-mapped 16-bit digital word")
        stream.setStyleSheet("padding: 3px 4px; min-height: 16px;")
        for editor in (index, channel, bit):
            editor.setStyleSheet("padding: 3px 4px; min-height: 16px;")
        self.rows[key] = (signal, stream, index, channel, bit)
        enabled = QCheckBox()
        enabled.setChecked(True)
        enabled.setAccessibleName(f"Record {name} input")
        enabled.toggled.connect(self.refresh_controls)
        self.enable_controls[key] = enabled
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.row_keys.append(key)
        self.table.set_control(row, 0, enabled)
        if custom:
            remove = button("×", "compact", hint="Remove this custom input")
            remove.setAccessibleName("Remove custom input")
            remove.clicked.connect(lambda: self.remove_custom(key))
            self.remove_buttons[key] = remove
            self.table.set_control(row, 6, remove)
        for col, control in enumerate(self.rows[key]):
            control.setAccessibleName(
                f"{name} {('signal', 'stream', 'index', 'channel', 'bit')[col]}"
            )
        for col, control in enumerate(self.rows[key], 1):
            self.table.set_control(row, col, control)
        self.table.fit_rows()

    def add_custom(self) -> None:
        if not self.can_review:
            return
        self.custom_count += 1
        source_id = f"custom-{self.custom_count}"
        key = f"custom:{source_id}"
        while key in self.rows:
            self.custom_count += 1
            source_id = f"custom-{self.custom_count}"
            key = f"custom:{source_id}"
        self.add_row(key, "Other input", custom=True)
        from PyQt6.QtWidgets import QLineEdit

        signal = self.rows[key][0]
        assert isinstance(signal, QLineEdit)
        signal.setText(source_id)
        signal.setToolTip("Stable custom source identifier")
        self.row_roles[key] = sync_pb.PULSE_ROLE_CUSTOM
        self.row_source_ids[key] = source_id
        self.refresh_controls()

    def remove_custom(self, key: str) -> None:
        if not self.can_review or key not in self.remove_buttons:
            return
        controls = self.rows.pop(key)
        controls[1].deleteLater()
        self.enable_controls.pop(key)
        self.remove_buttons.pop(key)
        self.row_roles.pop(key, None)
        self.row_source_ids.pop(key, None)
        self.table.removeRow(self.row_keys.index(key))
        self.row_keys.remove(key)
        self.table.fit_rows()

    def set_sources(
        self, sources: tuple[tuple[str, str, bool], ...], camera_keys: frozenset[str]
    ) -> None:
        visible = set()
        active_roles: set[int] = set()
        for source_key, name, active in sources:
            normalized_name = name.casefold()
            role = None
            if source_key in camera_keys:
                if "behavior" in normalized_name:
                    role = sync_pb.PULSE_ROLE_BEHAVIORAL_CAMERA
                elif "tracking" in normalized_name:
                    role = sync_pb.PULSE_ROLE_TRACKING_CAMERA
            elif source_key == "photodiode":
                role = sync_pb.PULSE_ROLE_PHOTODIODE
            key = self.inventory_rows.get(role, source_key) if role else source_key
            if key not in self.rows:
                self.add_row(key, name)
            signal = self.rows[key][0]
            if isinstance(signal, QLabel):
                signal.setText(name)
            if role is not None:
                self.inventory_rows[role] = key
                self.row_roles[key] = role
                if active:
                    active_roles.add(role)
            visible.add(key)
        self.active_inventory_roles = frozenset(active_roles)
        for row, key in enumerate(self.row_keys):
            shown = (
                key in visible
                or key.startswith("custom:")
                or key.startswith("saved:")
                or key.startswith("supplemental:")
            )
            controls = self.rows[key]
            for control in (*controls, self.enable_controls[key]):
                control.setVisible(shown)
            self.table.setRowHidden(row, not shown)
        self.table.fit_rows()
        self.refresh_controls()

    def refresh_controls(self) -> None:
        self.config_files.set_enabled(self.can_review)
        self.add_input.setEnabled(self.can_review)
        self.save_inventory.setEnabled(self.can_review)
        for key, controls in self.rows.items():
            toggle = self.enable_controls[key]
            role = self.row_roles.get(key)
            required = role in self.required_inventory_roles
            source_active = (
                role
                not in {
                    sync_pb.PULSE_ROLE_BEHAVIORAL_CAMERA,
                    sync_pb.PULSE_ROLE_TRACKING_CAMERA,
                    sync_pb.PULSE_ROLE_PHOTODIODE,
                }
                or role in self.active_inventory_roles
            )
            if required:
                toggle.setChecked(True)
            toggle.setEnabled(self.can_review and source_active and not required)
            for control in controls:
                control.setEnabled(
                    self.can_review and source_active and toggle.isChecked()
                )
            if key in self.remove_buttons:
                self.remove_buttons[key].setEnabled(self.can_review)

    def install_inventory(
        self,
        pulse_channels: tuple[sync_pb.PulseChannel, ...],
        file_sha256: str,
        *,
        required_roles: frozenset[int] = frozenset(),
        backend_enabled: bool | None = None,
        address: str = "",
        command_port: int | None = None,
    ) -> None:
        """Install read-only host settings and the editable saved pulse mapping."""
        if backend_enabled is not None:
            if not address or command_port is None or not 1 <= command_port <= 65535:
                raise ValueError("saved SpikeGLX host settings are incomplete")
            self.pairing.setChecked(backend_enabled)
            self.address.setText(address)
            self.command_port.setText(str(command_port))
        self.inventory_file_sha256 = file_sha256
        self.required_inventory_roles = required_roles
        for channel in pulse_channels:
            source_id = channel.source_id if channel.HasField("source_id") else ""
            key = (
                f"custom:{source_id}"
                if channel.role == sync_pb.PULSE_ROLE_CUSTOM
                else self.inventory_rows.get(channel.role)
            )
            if key is None and channel.role in {
                sync_pb.PULSE_ROLE_BEHAVIORAL_CAMERA,
                sync_pb.PULSE_ROLE_TRACKING_CAMERA,
                sync_pb.PULSE_ROLE_PHOTODIODE,
            }:
                source_name = (
                    sync_pb.PulseRole.Name(channel.role)
                    .removeprefix("PULSE_ROLE_")
                    .replace("_", " ")
                    .title()
                )
                key = f"saved:{channel.role}"
                if key not in self.rows:
                    self.add_row(key, source_name)
                self.inventory_rows[channel.role] = key
                self.row_roles[key] = channel.role
            if key is None and channel.role in {
                sync_pb.PULSE_ROLE_TRIAL_STATE,
                sync_pb.PULSE_ROLE_PROJECTOR_FLIP,
            }:
                source_name = (
                    "trial_state"
                    if channel.role == sync_pb.PULSE_ROLE_TRIAL_STATE
                    else "projector_flip"
                )
                key = f"supplemental:{source_name}"
                if key not in self.rows:
                    self.add_row(key, source_name.replace("_", " ").title())
                self.row_roles[key] = channel.role
            if key is None:
                continue
            if key not in self.rows:
                if channel.role != sync_pb.PULSE_ROLE_CUSTOM:
                    continue
                self.add_row(key, "Other input", custom=True)
                from PyQt6.QtWidgets import QLineEdit

                signal = self.rows[key][0]
                assert isinstance(signal, QLineEdit)
                signal.setText(source_id)
                self.row_roles[key] = sync_pb.PULSE_ROLE_CUSTOM
                self.row_source_ids[key] = source_id
                self.custom_count += 1
            from PyQt6.QtWidgets import QComboBox, QLineEdit

            signal, stream, index, number, bit = self.rows[key]
            assert isinstance(stream, QComboBox)
            assert isinstance(index, QLineEdit)
            assert isinstance(number, QLineEdit)
            assert isinstance(bit, QLineEdit)
            if channel.role == sync_pb.PULSE_ROLE_CUSTOM:
                assert isinstance(signal, QLineEdit)
                signal.setText(source_id)
                self.row_source_ids[key] = source_id
                self.row_roles[key] = channel.role
            family = {
                sync_pb.STREAM_FAMILY_ONEBOX: "OneBox",
                sync_pb.STREAM_FAMILY_NI: "NI",
                sync_pb.STREAM_FAMILY_IMEC: "imec",
            }.get(channel.family)
            if family is None:
                continue
            stream.setCurrentText(family)
            index.setText(str(channel.stream_index))
            number.setText(str(channel.channel_index))
            bit.setText(str(channel.bit) if channel.HasField("bit") else "")
            if channel.role in self.required_inventory_roles:
                self.enable_controls[key].setChecked(True)
                self.enable_controls[key].setEnabled(False)
        self.refresh_controls()

    def inventory_for_submit(self) -> tuple[sync_pb.PulseChannel, ...]:
        """Collect configured source mappings and preserve absent bit presence."""
        from PyQt6.QtWidgets import QComboBox, QLineEdit

        families = {
            "OneBox": sync_pb.STREAM_FAMILY_ONEBOX,
            "NI": sync_pb.STREAM_FAMILY_NI,
            "imec": sync_pb.STREAM_FAMILY_IMEC,
        }
        result = []
        for key in self.row_keys:
            role = self.row_roles.get(key)
            if (
                role is None
                or key not in self.rows
                or (
                    role not in self.required_inventory_roles
                    and not self.enable_controls[key].isChecked()
                )
            ):
                continue
            signal, stream, index, channel, bit = self.rows[key]
            assert isinstance(stream, QComboBox)
            assert isinstance(index, QLineEdit)
            assert isinstance(channel, QLineEdit)
            assert isinstance(bit, QLineEdit)
            family = families.get(stream.currentText())
            if family is None:
                raise ValueError("select a supported SpikeGLX stream family")
            try:
                stream_index = int(index.text())
                channel_index = int(channel.text())
                bit_index = int(bit.text()) if bit.text().strip() else None
            except ValueError as exc:
                raise ValueError(
                    "stream, channel and bit indices must be integers"
                ) from exc
            if stream_index < 0 or channel_index < 0:
                raise ValueError("stream and channel indices must be nonnegative")
            if bit_index is not None and not 0 <= bit_index <= 15:
                raise ValueError("digital word bit must be in the range 0..15")
            item = sync_pb.PulseChannel(
                role=cast(sync_pb.PulseRole, role),
                family=family,
                stream_index=stream_index,
                channel_index=channel_index,
            )
            if bit_index is not None:
                item.bit = bit_index
            if role == sync_pb.PULSE_ROLE_CUSTOM:
                assert isinstance(signal, QLineEdit)
                source_id = signal.text().strip()
                if not source_id:
                    raise ValueError("custom input needs a stable source identifier")
                item.source_id = source_id
            result.append(item)
        present = {channel.role for channel in result}
        if not self.required_inventory_roles <= present:
            raise ValueError("active pulse sources cannot be disabled")
        return tuple(result)

    def request_inventory_update(self) -> None:
        if not self.can_review or not self.inventory_file_sha256:
            return
        try:
            self.inventory_update_requested.emit(self.inventory_for_submit())
        except ValueError as exc:
            self.console.appendPlainText(f"Pulse mapping is invalid: {exc}")

    def apply_view(self, view: DashboardView) -> None:
        super().apply_view(view)
        self.action_buttons[0].setEnabled(view.connected and not view.sample)
        self.pairing.setEnabled(self.can_review and view.sample)
        self.refresh_controls()

    def request(self, name: str) -> None:
        if self.can_review:
            super().request(name)
        elif name == "Test connection":
            self.connection_requested.emit()
