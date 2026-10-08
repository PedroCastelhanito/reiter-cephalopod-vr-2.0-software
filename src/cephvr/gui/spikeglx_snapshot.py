"""Editable pulse mapping snapshots with informational startup endpoint provenance."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit

from cephvr.gui.configuration_files import (
    JSON,
    ConfigurationFiles,
    boolean,
    envelope,
    fields,
    text,
)
from cephvr.synchronization.v1 import spikeglx_pb2 as pb

if TYPE_CHECKING:
    from cephvr.gui.spikeglx import SpikeGLXPanel

ROW_KEYS = {
    "key",
    "signal",
    "stream",
    "index",
    "channel",
    "bit",
    "enabled",
    "role",
    "source_id",
    "custom",
}


class SpikeGLXSnapshot:
    def __init__(self, panel: SpikeGLXPanel) -> None:
        self.panel = panel
        self.files = ConfigurationFiles(
            panel,
            "SpikeGLX",
            "spikeglx.json",
            capture=self.capture,
            validate=self.validate,
            apply=self.restore,
            available=lambda: panel.can_review,
        )
        self.files.message.connect(panel.console.appendPlainText)
        row = QHBoxLayout()
        row.addWidget(self.files.load_button)
        row.addWidget(self.files.save_button)
        panel.configuration.body.insertLayout(1, row)

    def host(self) -> JSON:
        panel = self.panel
        return {
            "pairing": panel.pairing.isChecked(),
            "address": panel.address.text(),
            "command_port": panel.command_port.text(),
        }

    def capture(self) -> JSON:
        rows = []
        for key in self.panel.row_keys:
            signal, stream, index, channel, bit = self.panel.rows[key]
            assert isinstance(signal, (QLabel, QLineEdit))
            assert isinstance(stream, QComboBox)
            assert (
                isinstance(index, QLineEdit)
                and isinstance(channel, QLineEdit)
                and isinstance(bit, QLineEdit)
            )
            rows.append(
                {
                    "key": key,
                    "signal": signal.text(),
                    "stream": stream.currentText(),
                    "index": index.text(),
                    "channel": channel.text(),
                    "bit": bit.text(),
                    "enabled": self.panel.enable_controls[key].isChecked(),
                    "role": self.panel.row_roles.get(key),
                    "source_id": self.panel.row_source_ids.get(key, ""),
                    "custom": key in self.panel.remove_buttons,
                }
            )
        return {
            "format": "cephvr-spikeglx-config",
            "version": 1,
            "host_reference": self.host(),
            "rows": rows,
        }

    def validate(self, value: Any) -> JSON:
        data = envelope(value, "cephvr-spikeglx-config", {"host_reference", "rows"})
        host = fields(
            data["host_reference"],
            {"pairing", "address", "command_port"},
            "SpikeGLX host reference",
        )
        boolean(host["pairing"], "Pairing")
        text(host["address"], "Host")
        text(host["command_port"], "Port")
        if not isinstance(data["rows"], list):
            raise ValueError("SpikeGLX rows must be a list")
        keys: set[str] = set()
        roles: set[int] = set()
        for raw in data["rows"]:
            row = fields(raw, ROW_KEYS, "SpikeGLX input")
            for name in ROW_KEYS - {"enabled", "role", "custom"}:
                text(row[name], name)
            if (
                not row["key"]
                or row["key"] in keys
                or row["stream"] not in ("OneBox", "NI", "imec")
            ):
                raise ValueError("Invalid or duplicate SpikeGLX row identity/stream")
            keys.add(row["key"])
            boolean(row["enabled"], "Input enable")
            boolean(row["custom"], "Custom input")
            role = row["role"]
            if role is not None and (
                type(role) is not int
                or role not in pb.PulseRole.values()
                or role == pb.PULSE_ROLE_UNSPECIFIED
            ):
                raise ValueError("Unknown SpikeGLX pulse role")
            if row["custom"] != (role == pb.PULSE_ROLE_CUSTOM) or row["custom"] != row[
                "key"
            ].startswith("custom:"):
                raise ValueError("Custom SpikeGLX row identity disagrees with its role")
            if role is not None and role != pb.PULSE_ROLE_CUSTOM:
                if role in roles:
                    raise ValueError("Duplicate SpikeGLX pulse role")
                roles.add(role)
        return data

    def restore(self, data: JSON) -> None:
        panel = self.panel
        if data["host_reference"] != self.host():
            panel.console.appendPlainText(
                "Loaded pulse mapping; saved host reference differs. The current startup host/pairing settings remain authoritative."
            )
        panel.table.setRowCount(0)
        panel.rows.clear()
        panel.row_keys.clear()
        panel.enable_controls.clear()
        panel.remove_buttons.clear()
        panel.inventory_rows.clear()
        panel.row_roles.clear()
        panel.row_source_ids.clear()
        for row in data["rows"]:
            key, role = row["key"], row["role"]
            panel.add_row(key, row["signal"], custom=row["custom"])
            signal, stream, index, channel, bit = panel.rows[key]
            assert isinstance(signal, (QLabel, QLineEdit)) and isinstance(
                stream, QComboBox
            )
            assert (
                isinstance(index, QLineEdit)
                and isinstance(channel, QLineEdit)
                and isinstance(bit, QLineEdit)
            )
            signal.setText(row["signal"])
            stream.setCurrentText(row["stream"])
            for editor, name in ((index, "index"), (channel, "channel"), (bit, "bit")):
                editor.setText(row[name])
            panel.row_source_ids[key] = row["source_id"]
            if role is not None:
                panel.row_roles[key] = role
                if role in (
                    pb.PULSE_ROLE_BEHAVIORAL_CAMERA,
                    pb.PULSE_ROLE_TRACKING_CAMERA,
                    pb.PULSE_ROLE_PHOTODIODE,
                ):
                    panel.inventory_rows[role] = key
            panel.enable_controls[key].setChecked(row["enabled"])
        panel.refresh_controls()
