"""Declared feedback inputs and compatible targets, using the canonical unit rules."""

import json
from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QGridLayout, QLineEdit, QWidget

from cephvr.gui.components import button, combo, field, label
from cephvr.tracking.config.pipeline import CHANNELS
from cephvr.visual_stimulus.config.models.parameter_catalogue import (
    DIRECT_GAIN_UNITS,
    MOVEMENT_GAIN_UNITS,
    parameter_units,
)
from cephvr.visual_stimulus.config.models.program_model import InputChannel, Settings

NAMES = {
    "forward_drive": "Tracking · Longitudinal",
    "sideways_drive": "Tracking · Lateral",
    "turn_drive": "Tracking · Turning",
}
TARGETS = {
    "x": "Position X",
    "y": "Position Y",
    "rotation": "Rotation",
    "yaw": "Heading",
    "phase_x": "Texture phase X",
    "phase_y": "Texture phase Y",
    "opacity": "Opacity",
    "width": "Width",
    "height": "Height",
    "contrast": "Contrast",
    "frequency": "Frequency",
    "frequency_x": "Frequency X",
    "frequency_y": "Frequency Y",
    "period_x": "Tile width",
    "period_y": "Tile height",
}


def tracking_signals() -> list[dict[str, Any]]:
    return [
        {
            "channel_id": c.channel_id,
            "stream_id": "tracking",
            "value_kind": c.quantity,
            "unit": c.unit,
            "frame_id": c.coordinate_frame,
        }
        for c in CHANNELS
    ]


def targets(setting: Settings, signal: dict[str, Any]) -> dict[str, str]:
    units = parameter_units(setting)
    if signal["frame_id"] == "anatomical_body":
        return (
            {"yaw": "Heading"}
            if setting.kind == "arena"
            and signal["value_kind"] == "interval_average_rate"
            and signal["unit"] == "1/s"
            else {}
        )
    state = {"x", "y", "yaw"} if setting.kind == "arena" else {"x", "y", "rotation"}
    if setting.kind == "texture":
        state.update(("phase_x", "phase_y"))
    return {
        key: TARGETS.get(key, key)
        for key, unit in units.items()
        if (
            signal["value_kind"] == "absolute"
            and (signal["unit"], unit) in DIRECT_GAIN_UNITS
        )
        or (
            key in state
            and (signal["value_kind"], signal["unit"], unit) in MOVEMENT_GAIN_UNITS
        )
    }


class SignalDefinition(QWidget):
    """Explicit custom input declaration, only opened from the feedback section."""

    created = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        self.name = QLineEdit()
        self.source = QLineEdit()
        self.coordinates = QLineEdit()
        self.name.setPlaceholderText("e.g. forward_speed")
        self.source.setPlaceholderText("Stream name")
        self.coordinates.setPlaceholderText("e.g. world")
        self.measurement = combo(("Value / position", "Change per sample", "Velocity"))
        self.units = combo(())
        self.measurement.currentIndexChanged.connect(self.refresh_units)
        self.refresh_units()
        for i, (name, control) in enumerate(
            (
                ("Signal name", self.name),
                ("Source", self.source),
                ("Measurement", self.measurement),
                ("Units", self.units),
                ("Coordinates", self.coordinates),
            )
        ):
            control.setMinimumWidth(0)
            grid.addWidget(field(name, control), i // 3, i % 3)
        self.save = button("Add input")
        self.save.clicked.connect(self.submit)
        grid.addWidget(self.save, 1, 2)
        self.message = label("", wrap=True)
        grid.addWidget(self.message, 2, 0, 1, 3)

    def refresh_units(self) -> None:
        self.units.clear()
        self.units.addItems(
            ("1/s", "mm/s", "deg/s", "cycle/s", "px/s")
            if self.measurement.currentIndex() == 2
            else ("1", "mm", "deg", "cycle", "px")
        )

    def submit(self) -> None:
        try:
            channel = InputChannel.model_validate_json(
                json.dumps(
                    {
                        "channel_id": self.name.text().strip(),
                        "stream_id": self.source.text().strip(),
                        "frame_id": self.coordinates.text().strip(),
                        "value_kind": (
                            "absolute",
                            "displacement",
                            "interval_average_rate",
                        )[self.measurement.currentIndex()],
                        "unit": self.units.currentText(),
                    }
                )
            )
        except ValueError:
            self.message.setText("Enter a signal name, source and coordinate system.")
            return
        self.message.clear()
        self.created.emit(channel.model_dump(mode="json"))
