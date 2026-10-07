"""Compact body-axis gains over V24 feedback; preserve custom imported mappings."""

from copy import deepcopy
from math import isfinite
from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from cephvr.gui.components import equal_row_height, field
from cephvr.gui.feedback_signals import tracking_signals
from cephvr.gui.program_editing import unique_id
from cephvr.tracking.config.pipeline import CHANNELS


class ArenaMovement(QWidget):
    changed = pyqtSignal()

    def __init__(
        self,
        values: dict[str, Any],
    ) -> None:
        super().__init__()
        self.edited = False
        functions = self.load_values(values)
        supported = self.supported
        self.cells: list[tuple[str, QWidget]] = []
        self.axes: list[QCheckBox] = []
        self.gains: list[QLineEdit] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for index, name in enumerate(("Longitudinal", "Lateral", "Angular")):
            function = functions[index]
            value = function["value"] if function is not None and supported else 0
            cell = QWidget()
            row = QHBoxLayout(cell)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            axis = QCheckBox()
            axis.setAccessibleName(f"Enable {name.lower()} movement")
            axis.setToolTip(
                f"Enable {name.lower()} movement; disabled axes use zero gain"
            )
            axis.setChecked(value != 0)
            gain = QLineEdit(f"{value if value else 1:.17g}")
            gain.setMinimumWidth(0)
            gain.setAccessibleName(f"{name} gain")
            gain.setToolTip(
                f"{name} gain ({'°/rad' if index == 2 else 'mm/px'}); signed values reverse movement"
            )
            gain.setEnabled(value != 0)
            axis.toggled.connect(gain.setEnabled)
            axis.toggled.connect(self.mark_edited)
            gain.textEdited.connect(self.mark_edited)
            row.addWidget(axis)
            row.addWidget(gain, 1)
            equal_row_height(axis, gain)
            cell.setEnabled(supported)
            self.cells.append((name, cell))
            self.axes.append(axis)
            self.gains.append(gain)
            layout.addWidget(field(name, cell))

    def load_values(self, values: dict[str, Any]) -> list[Any]:
        self.values = deepcopy(values["feedback"])
        self.planar = next(
            (
                b
                for b in self.values
                if b["operation"] == "heading_relative_planar_integration"
            ),
            None,
        )
        self.turn = next((b for b in self.values if b.get("target") == "yaw"), None)
        supported = len(self.values) == int(self.planar is not None) + int(
            self.turn is not None
        )
        if self.planar:
            supported &= (
                self.planar["forward_channel"],
                self.planar["sideways_channel"],
            ) == ("forward_drive", "sideways_drive")
        if self.turn:
            supported &= (
                self.turn["source_channel"] == "turn_drive"
                and self.turn["operation"] == "movement_integration"
                and self.turn["offset"] == {"kind": "constant", "value": 0}
            )
        functions = [
            self.planar["gain"] if self.planar else None,
            (self.planar.get("sideways_gain") or self.planar["gain"])
            if self.planar
            else None,
            self.turn["gain"] if self.turn else None,
        ]
        supported &= all(
            f is None
            or (f["kind"] == "constant" and isinstance(f["value"], (int, float)))
            for f in functions
        )
        self.supported = supported
        return functions

    def accept(self, values: dict[str, Any]) -> None:
        functions = self.load_values(values)
        for index, (axis, gain) in enumerate(zip(self.axes, self.gains, strict=True)):
            function = functions[index]
            value = function["value"] if function is not None and self.supported else 0
            axis.blockSignals(True)
            axis.setChecked(value != 0)
            axis.blockSignals(False)
            if value:
                gain.setText(f"{value:.17g}")
            gain.setEnabled(value != 0)
            self.cells[index][1].setEnabled(self.supported)
        self.edited = False

    def mark_edited(self) -> None:
        self.edited = True
        self.changed.emit()

    def read(self) -> dict[str, Any]:
        if not self.supported or not self.edited:
            return {"feedback": deepcopy(self.values)}
        gains = [
            float(g.text()) if a.isChecked() else 0.0
            for a, g in zip(self.axes, self.gains, strict=True)
        ]
        if not all(isfinite(g) for g in gains):
            raise ValueError("Movement gains must be finite")

        def constant(value: float) -> dict[str, Any]:
            return {"kind": "constant", "value": value}

        bindings = []
        if self.planar or any(gains[:2]):
            bindings.append(
                {
                    "binding_id": self.planar["binding_id"]
                    if self.planar
                    else unique_id(self.values, "arena_planar"),
                    "operation": "heading_relative_planar_integration",
                    "forward_channel": "forward_drive",
                    "sideways_channel": "sideways_drive",
                    "gain": constant(gains[0]),
                    "sideways_gain": constant(gains[1]),
                }
            )
        if self.turn or gains[2]:
            bindings.append(
                {
                    "binding_id": self.turn["binding_id"]
                    if self.turn
                    else unique_id(self.values, "arena_turn"),
                    "operation": "movement_integration",
                    "source_channel": "turn_drive",
                    "target": "yaw",
                    "gain": constant(gains[2]),
                    "offset": constant(0),
                }
            )
        return {"feedback": bindings}

    def add_inputs(self, candidate: dict[str, Any]) -> None:
        if not self.edited or not self.supported:
            return
        bindings = self.read()["feedback"]
        needed = {
            name
            for b in bindings
            for name in (
                b.get("source_channel"),
                b.get("forward_channel"),
                b.get("sideways_channel"),
            )
            if name
        }
        existing = {c["channel_id"]: c for c in candidate["input_channels"]}
        streams = {existing[name]["stream_id"] for name in needed if name in existing}
        if len(streams) > 1:
            raise ValueError("Arena movement axes must use the same Tracking stream")
        stream = next(iter(streams), "tracking")
        for channel in CHANNELS:
            if channel.channel_id not in needed:
                continue
            declaration = {
                "channel_id": channel.channel_id,
                "stream_id": stream,
                "value_kind": channel.quantity,
                "unit": channel.unit,
                "frame_id": channel.coordinate_frame,
            }
            if channel.channel_id in existing:
                if existing[channel.channel_id] != declaration:
                    raise ValueError(
                        f"{channel.channel_id} conflicts with the Tracking movement channel"
                    )
            else:
                candidate["input_channels"].append(declaration)


def patch_arena(
    setting: dict[str, Any], changes: dict[str, str], document: dict[str, Any]
) -> None:
    for name, value in changes.items():
        if name not in ("Longitudinal", "Lateral", "Angular"):
            continue
        gain = float(value)
        if not isfinite(gain):
            raise ValueError("Movement gains must be finite")
        operation = (
            "movement_integration"
            if name == "Angular"
            else "heading_relative_planar_integration"
        )
        binding = next(
            (
                b
                for b in setting["feedback"]
                if b["operation"] == operation
                and (name != "Angular" or b.get("target") == "yaw")
            ),
            None,
        )
        if binding is None:
            binding = dict(
                binding_id=unique_id(setting["feedback"], "arena_variation"),
                operation=operation,
                gain=dict(kind="constant", value=0),
            )
            if name == "Angular":
                binding.update(
                    source_channel="turn_drive",
                    target="yaw",
                    offset=dict(kind="constant", value=0),
                )
            else:
                binding.update(
                    forward_channel="forward_drive",
                    sideways_channel="sideways_drive",
                    sideways_gain=dict(kind="constant", value=0),
                )
            setting["feedback"].append(binding)
        key = "sideways_gain" if name == "Lateral" else "gain"
        if binding[key]["kind"] != "constant":
            raise ValueError("Custom movement gains cannot be replaced by a variation")
        binding[key] = dict(kind="constant", value=gain)
        needed = {
            binding.get(k)
            for k in ("source_channel", "forward_channel", "sideways_channel")
        }
        existing = {c["channel_id"]: c for c in document["input_channels"]}
        streams = {existing[key]["stream_id"] for key in needed if key in existing}
        if len(streams) > 1:
            raise ValueError("Arena movement axes must use the same Tracking stream")
        stream = next(iter(streams), "tracking")
        for channel in tracking_signals():
            channel = {**channel, "stream_id": stream}
            identity = channel["channel_id"]
            if identity not in needed:
                continue
            if identity in existing and existing[identity] != channel:
                raise ValueError(
                    f"{identity} conflicts with the Tracking movement channel"
                )
            if identity not in existing:
                document["input_channels"].append(deepcopy(channel))
