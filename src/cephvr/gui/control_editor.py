"""One local draft for choosing/defining an input and its parameter response."""

from math import isfinite
from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from cephvr.gui.components import button, combo, field, label
from cephvr.gui.feedback_signals import NAMES, targets, tracking_signals
from cephvr.gui.notices import FormNotice
from cephvr.visual_stimulus.config.models.program_model import Settings


class ControlEditor(QWidget):
    submitted = pyqtSignal(object, object)

    def __init__(self, setting: Settings) -> None:
        super().__init__()
        self.setting = setting
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)
        self.input = combo(())
        body.addWidget(field("Input", self.input))
        self.parameter = combo(())
        self.gain, self.offset = QLineEdit("1"), QLineEdit("0")
        self.response = label("", wrap=True)
        row = QHBoxLayout()
        for title, control in (
            ("Parameter", self.parameter),
            ("Gain", self.gain),
            ("Offset", self.offset),
        ):
            control.setMinimumWidth(0)
            row.addWidget(field(title, control), 1)
        body.addLayout(row)
        body.addWidget(self.response)
        actions = QHBoxLayout()
        self.save = button("Add control", "primary")
        self.cancel = button("Cancel")
        self.save.clicked.connect(self.submit)
        self.cancel.clicked.connect(self.hide)
        actions.addWidget(self.save)
        actions.addWidget(self.cancel)
        actions.addStretch()
        body.addLayout(actions)
        self.message = FormNotice()
        body.addWidget(self.message)
        self.input.currentIndexChanged.connect(self.refresh_targets)
        self.reset(setting)

    def reset(self, setting: Settings) -> None:
        self.setting = setting
        self.input.blockSignals(True)
        self.input.clear()
        for channel in tracking_signals():
            self.input.addItem(NAMES[channel["channel_id"]], channel["channel_id"])
        self.input.setCurrentIndex(0)
        self.input.blockSignals(False)
        self.gain.setText("1")
        self.offset.setText("0")
        self.message.clear()
        self.refresh_targets()

    def channel(self) -> dict[str, Any]:
        key = self.input.currentData()
        return next(c for c in tracking_signals() if c["channel_id"] == key)

    def compatible_targets(self, channel: dict[str, Any]) -> dict[str, str]:
        if self.setting.kind == "arena" and channel["channel_id"] in (
            "forward_drive",
            "sideways_drive",
        ):
            return {"planar": "Arena movement"}
        return targets(self.setting, channel)

    def refresh_targets(self) -> None:
        old = self.parameter.currentData()
        self.parameter.blockSignals(True)
        self.parameter.clear()
        channel = self.channel()
        for key, title in self.compatible_targets(channel).items():
            self.parameter.addItem(title, key)
        selected = self.parameter.findData(old)
        if selected >= 0:
            self.parameter.setCurrentIndex(selected)
        self.parameter.blockSignals(False)
        self.save.setEnabled(self.parameter.count() > 0)
        self.offset.setEnabled(channel["channel_id"] == "turn_drive")
        self.response.setText(
            "Tracking → 2D screen conversion is not defined yet."
            if not self.parameter.count()
            else "Adds body-relative arena movement using the Tracking sample interval. Signed gain reverses movement."
        )

    def submit(self) -> None:
        try:
            channel = self.channel()
            target = self.parameter.currentData()
            if target not in self.compatible_targets(channel):
                raise ValueError("Choose a compatible input and parameter")
            gain, offset = float(self.gain.text()), float(self.offset.text())
            if not all(isfinite(v) for v in (gain, offset)):
                raise ValueError("Control coefficients must be finite")
        except (ValueError, StopIteration) as error:
            self.message.warn(f"Cannot add control · {error}")
            return
        if target == "planar":
            previous = next(
                (
                    b
                    for b in self.setting.feedback
                    if b.operation == "heading_relative_planar_integration"
                ),
                None,
            )
            response = (
                previous.model_dump(mode="json")
                if previous is not None
                else {
                    "operation": "heading_relative_planar_integration",
                    "forward_channel": "forward_drive",
                    "sideways_channel": "sideways_drive",
                    "gain": {"kind": "constant", "value": 0},
                    "sideways_gain": {"kind": "constant", "value": 0},
                }
            )
            key = (
                "gain" if channel["channel_id"] == "forward_drive" else "sideways_gain"
            )
            response[key] = {"kind": "constant", "value": gain}
        else:
            response = {
                "source_channel": channel["channel_id"],
                "target": target,
                "operation": "movement_integration",
                "gain": {"kind": "constant", "value": gain},
                "offset": {"kind": "constant", "value": offset},
            }
        self.submitted.emit(channel, response)
