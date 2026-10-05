"""One readable input → parameter mapping; wire identifiers remain internal."""

from copy import deepcopy
from math import isfinite
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QGridLayout, QLineEdit, QSizePolicy, QWidget

from cephvr.gui.components import button, combo, equal_row_height, field
from cephvr.gui.feedback_signals import NAMES, targets
from cephvr.visual_stimulus.config.models.program_model import Settings


class FeedbackEntry(QWidget):
    changed = pyqtSignal()
    removed = pyqtSignal()

    def __init__(
        self, setting: Settings, channels: list[dict[str, Any]], binding: dict[str, Any]
    ) -> None:
        super().__init__()
        self.setting, self.channels = setting, channels
        self.binding = deepcopy(binding)
        self.dirty = False
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(8)
        self.signal = combo(())
        self.target = combo(())
        self.gain = QLineEdit()
        self.offset = QLineEdit()
        self.sideways = QLineEdit()
        self.remove = button("×", "icon", hint="Remove control")
        self.remove.setAccessibleName("Remove control")
        self.remove.clicked.connect(self.removed)
        self.controls = [
            field("Input signal", self.signal),
            field("Parameter", self.target),
            field("Gain", self.gain),
            field("Offset", self.offset),
            field("Lateral gain", self.sideways),
            self.remove,
        ]
        for control in (
            self.signal,
            self.target,
            self.gain,
            self.offset,
            self.sideways,
        ):
            control.setMinimumWidth(0)
        equal_row_height(
            self.signal, self.target, self.gain, self.offset, self.sideways, self.remove
        )
        self.remove.setFixedWidth(self.remove.height())
        self.populate()
        self.signal.currentIndexChanged.connect(self.change_signal)
        self.target.currentIndexChanged.connect(self.mark_changed)
        for edit in (self.gain, self.offset, self.sideways):
            edit.textEdited.connect(self.mark_changed)

    def populate(self) -> None:
        self.signal.blockSignals(True)
        self.signal.clear()
        for channel in self.channels:
            if channel["channel_id"] in (
                "forward_drive",
                "sideways_drive",
                "turn_drive",
            ) and targets(self.setting, channel):
                self.signal.addItem(
                    NAMES.get(channel["channel_id"], channel["channel_id"])
                    + f" ({channel['unit']})",
                    channel["channel_id"],
                )
        planar = self.binding["operation"] == "heading_relative_planar_integration"
        if planar:
            self.signal.addItem(
                "Longitudinal + lateral",
                (self.binding["forward_channel"], self.binding["sideways_channel"]),
            )
        key = (
            (self.binding["forward_channel"], self.binding["sideways_channel"])
            if planar
            else self.binding["source_channel"]
        )
        index = self.signal.findData(key)
        if index < 0:
            self.signal.addItem(str(key), key)
            index = self.signal.count() - 1
        self.signal.setCurrentIndex(index)
        self.signal.blockSignals(False)
        self.refresh_targets()
        self.target.blockSignals(True)
        saved_target = self.binding.get("target", "planar")
        index = self.target.findData(saved_target)
        if index < 0:
            self.target.addItem(str(saved_target), saved_target)
            index = self.target.count() - 1
        self.target.setCurrentIndex(index)
        self.target.blockSignals(False)
        self.load_coefficient(self.gain, self.binding["gain"])
        self.load_coefficient(
            self.offset, self.binding.get("offset", {"kind": "constant", "value": 0})
        )
        self.load_coefficient(
            self.sideways, self.binding.get("sideways_gain") or self.binding["gain"]
        )
        self.arrange()

    @staticmethod
    def load_coefficient(editor: QLineEdit, function: dict[str, Any]) -> None:
        simple = function["kind"] == "constant" and isinstance(
            function["value"], (int, float)
        )
        editor.setText(f"{function['value']:.17g}" if simple else "Custom curve")
        editor.setReadOnly(not simple)
        editor.setToolTip(
            "Saved function is preserved"
            if not simple
            else "Signed scaling; negative gain reverses the response"
        )

    def refresh_targets(self) -> None:
        self.target.blockSignals(True)
        self.target.clear()
        key = self.signal.currentData()
        if isinstance(key, (tuple, list)):
            self.target.addItem("Arena movement", "planar")
        else:
            signal = next((c for c in self.channels if c["channel_id"] == key), None)
            if signal:
                for name, title in targets(self.setting, signal).items():
                    self.target.addItem(title, name)
                hint = (
                    "Follows the signal value"
                    if signal["value_kind"] == "absolute"
                    else "Adds movement using the signal's sample interval"
                )
                self.target.setToolTip(hint)
        self.target.blockSignals(False)

    def change_signal(self) -> None:
        previous = self.target.currentData()
        self.refresh_targets()
        index = self.target.findData(previous)
        if index >= 0:
            self.target.setCurrentIndex(index)
        self.arrange()
        self.mark_changed()

    def mark_changed(self) -> None:
        self.dirty = True
        self.changed.emit()

    def arrange(self) -> None:
        planar = isinstance(self.signal.currentData(), (tuple, list))
        self.controls[3].setVisible(not planar)
        self.controls[4].setVisible(planar)
        while self.grid.count():
            self.grid.takeAt(0)
        for col in range(5):
            self.grid.setColumnStretch(col, 0)
        visible = self.controls[:3] + [self.controls[4 if planar else 3], self.remove]
        narrow = self.width() < 660
        for i, widget in enumerate(visible):
            row, col = (
                (i // 2, i % 2) if narrow and i < 4 else (0, 2) if narrow else (0, i)
            )
            self.grid.addWidget(
                widget,
                row,
                col,
                alignment=Qt.AlignmentFlag.AlignBottom
                if widget is self.remove
                else Qt.AlignmentFlag(0),
            )
            if widget is not self.remove:
                self.grid.setColumnStretch(col, 2 if i < 2 and not narrow else 1)

    def resizeEvent(self, event: QResizeEvent | None) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.arrange()

    def read(self) -> dict[str, Any]:
        if not self.dirty:
            return deepcopy(self.binding)

        def coefficient(editor: QLineEdit, original: dict[str, Any]) -> dict[str, Any]:
            if editor.isReadOnly():
                return deepcopy(original)
            value = float(editor.text())
            if not isfinite(value):
                raise ValueError("Feedback coefficients must be finite")
            return {"kind": "constant", "value": value}

        key = self.signal.currentData()
        gain = coefficient(self.gain, self.binding["gain"])
        if isinstance(key, (tuple, list)):
            return {
                "binding_id": self.binding["binding_id"],
                "operation": "heading_relative_planar_integration",
                "forward_channel": key[0],
                "sideways_channel": key[1],
                "gain": gain,
                "sideways_gain": coefficient(
                    self.sideways,
                    self.binding.get("sideways_gain") or self.binding["gain"],
                ),
            }
        signal = next((c for c in self.channels if c["channel_id"] == key), None)
        if signal is None or self.target.currentData() not in targets(
            self.setting, signal
        ):
            raise ValueError("Choose a compatible input signal and parameter")
        return {
            "binding_id": self.binding["binding_id"],
            "source_channel": key,
            "target": self.target.currentData(),
            "operation": "direct_value"
            if signal["value_kind"] == "absolute"
            else "movement_integration",
            "gain": gain,
            "offset": coefficient(
                self.offset,
                self.binding.get("offset", {"kind": "constant", "value": 0}),
            ),
        }
