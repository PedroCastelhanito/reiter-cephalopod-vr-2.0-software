"""Inline feedback entries and their input declarations, patched atomically by the owner."""

from copy import deepcopy
from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from cephvr.gui.components import button, label
from cephvr.gui.feedback_entry import FeedbackEntry
from cephvr.gui.feedback_signals import SignalDefinition, targets, tracking_signals
from cephvr.gui.program_editing import unique_id
from cephvr.visual_stimulus.config.models.program_model import Settings


class FeedbackMappings(QWidget):
    changed = pyqtSignal()

    def __init__(self, setting: Settings, channels: list[dict[str, Any]]) -> None:
        super().__init__()
        self.setting = setting
        self.channels = deepcopy(channels)
        if setting.kind == "arena":
            self.channels.extend(
                c
                for c in tracking_signals()
                if c["channel_id"] not in {v["channel_id"] for v in self.channels}
            )
        self.entries: list[FeedbackEntry] = []
        self.removed: set[str] = set()
        self.new_inputs: dict[str, dict[str, Any]] = {}
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(14)
        heading = QHBoxLayout()
        heading.addWidget(label("Feedback", "label"))
        heading.addStretch()
        self.add = button("+ Feedback")
        self.add.clicked.connect(lambda: self.add_entry())
        self.define = button("+ Input signal")
        self.define.clicked.connect(
            lambda: self.definition.setVisible(not self.definition.isVisible())
        )
        heading.addWidget(self.define)
        heading.addWidget(self.add)
        body.addLayout(heading)
        self.definition = SignalDefinition()
        self.definition.created.connect(self.add_input)
        self.definition.hide()
        body.addWidget(self.definition)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(14)
        body.addLayout(self.rows)
        self.message = label("", wrap=True)
        self.message.hide()
        body.addWidget(self.message)
        for binding in setting.feedback:
            self.append(binding.model_dump(mode="json"))

    def append(self, binding: dict[str, Any]) -> FeedbackEntry:
        row = FeedbackEntry(self.setting, self.channels, binding)
        self.entries.append(row)
        self.rows.addWidget(row)
        row.changed.connect(self.changed)
        row.removed.connect(lambda: self.remove(row))
        return row

    def add_entry(self, identity: str = "") -> None:
        channel = next(
            (
                c
                for c in self.channels
                if targets(self.setting, c)
                and (not identity or c["channel_id"] == identity)
            ),
            None,
        )
        if channel is None:
            self.definition.show()
            self.message.setText(
                "Define a compatible input signal to create a mapping."
            )
            self.message.show()
            return
        bindings = [e.binding for e in self.entries] + [
            b.model_dump(mode="json") for b in self.setting.feedback
        ]
        row = self.append(
            {
                "binding_id": unique_id(bindings, "feedback"),
                "source_channel": channel["channel_id"],
                "target": next(iter(targets(self.setting, channel))),
                "operation": "direct_value"
                if channel["value_kind"] == "absolute"
                else "movement_integration",
                "gain": {"kind": "constant", "value": 1},
                "offset": {"kind": "constant", "value": 0},
            }
        )
        self.message.hide()
        row.mark_changed()

    def add_input(self, channel: dict[str, Any]) -> None:
        identity = channel["channel_id"]
        old = next((c for c in self.channels if c["channel_id"] == identity), None)
        if old is not None and old != channel:
            self.definition.message.setText(
                "That signal name already has a different definition."
            )
            return
        if not targets(self.setting, channel):
            self.definition.message.setText(
                "This signal cannot control a parameter of this stimulus."
            )
            return
        if old is None:
            self.channels.append(channel)
            self.new_inputs[identity] = channel
        self.definition.hide()
        self.add_entry(identity)

    def remove(self, row: FeedbackEntry) -> None:
        self.removed.add(row.binding["binding_id"])
        self.entries.remove(row)
        self.rows.removeWidget(row)
        row.hide()
        row.deleteLater()
        self.changed.emit()

    def patch(self, setting: dict[str, Any], candidate: dict[str, Any]) -> None:
        bindings = [
            b for b in setting["feedback"] if b["binding_id"] not in self.removed
        ]
        for row in self.entries:
            if not row.dirty:
                continue
            value = row.read()
            index = next(
                (
                    i
                    for i, b in enumerate(bindings)
                    if b["binding_id"] == value["binding_id"]
                ),
                len(bindings),
            )
            if index == len(bindings):
                bindings.append(value)
            else:
                bindings[index] = value
        setting["feedback"] = bindings
        needed = {
            b[k]
            for b in bindings
            for k in ("source_channel", "forward_channel", "sideways_channel")
            if k in b
        }
        existing = {c["channel_id"]: c for c in candidate["input_channels"]}
        for channel in self.channels:
            identity = channel["channel_id"]
            if identity not in needed:
                continue
            if identity in existing:
                if identity in self.new_inputs and existing[identity] != channel:
                    raise ValueError(
                        f"Input signal {identity} conflicts with the trial"
                    )
            else:
                candidate["input_channels"].append(deepcopy(channel))

    def accept(self, setting: Settings, channels: list[dict[str, Any]]) -> None:
        self.setting = setting
        self.removed.clear()
        self.new_inputs.clear()
        known = {c["channel_id"]: c for c in self.channels}
        known.update((c["channel_id"], c) for c in channels)
        self.channels = list(known.values())
        bindings = {b.binding_id: b.model_dump(mode="json") for b in setting.feedback}
        for row in tuple(self.entries):
            identity = row.binding["binding_id"]
            if identity not in bindings:
                self.entries.remove(row)
                self.rows.removeWidget(row)
                row.hide()
                row.deleteLater()
                continue
            row.setting, row.channels = setting, self.channels
            row.binding = bindings.pop(identity)
            row.dirty = False
            row.populate()
        for binding in bindings.values():
            self.append(binding)
