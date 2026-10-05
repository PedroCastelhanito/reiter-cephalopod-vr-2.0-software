"""Fade authoring as ordinary V05 opacity keyframes, without a second runtime state."""

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QWidget

from cephvr.gui.components import equal_row_height, field
from cephvr.visual_stimulus.config.models.program_model import Fixed, Time


def seconds(ns: int) -> str:
    return format(Decimal(ns) / 1_000_000_000, "f")


def fade_values(
    function: dict[str, Any], duration_ns: int
) -> tuple[int, int, float] | None:
    if function["kind"] == "constant" and isinstance(function["value"], (float, int)):
        return 0, 0, float(function["value"])
    if function["kind"] != "keyframes" or function["interpolation"] != "linear":
        return None
    knots = function["knots"]
    try:
        points = [
            (Time.model_validate(k["time"]).ns(), float(k["value"])) for k in knots
        ]
    except (ValueError, TypeError):
        return None
    if not 2 <= len(points) <= 4 or points[0][0] != 0:
        return None
    peak = max(v for _, v in points)
    if not 0 < peak <= 1 or any(v not in (0, peak) for _, v in points):
        return None
    plateau = [t for t, v in points if v == peak]
    fade_in = plateau[0] if points[0][1] == 0 else 0
    fade_out = duration_ns - plateau[-1] if points[-1] == (duration_ns, 0) else 0
    if fade_out < 0:
        return None
    return (
        (fade_in, fade_out, peak)
        if envelope(fade_in, fade_out, peak, duration_ns) == function
        else None
    )


def envelope(
    fade_in: int, fade_out: int, base: float, duration_ns: int
) -> dict[str, Any]:
    if fade_in < 0 or fade_out < 0 or fade_in + fade_out > duration_ns:
        raise ValueError("Fade durations must be nonnegative and fit within the epoch")
    if not fade_in and not fade_out:
        return {"kind": "constant", "value": base}
    points = {0: 0.0 if fade_in else base}
    if fade_in:
        points[fade_in] = base
    if fade_out:
        points[duration_ns - fade_out] = base
        points[duration_ns] = 0.0
    return {
        "kind": "keyframes",
        "interpolation": "linear",
        "knots": [
            {"time": {"seconds": seconds(t)}, "value": v}
            for t, v in sorted(points.items())
        ],
    }


def retime_fades(settings: list[dict[str, Any]], old_ns: int, new_ns: int) -> None:
    for setting in settings:
        if "opacity" not in setting:
            continue
        values = fade_values(setting["opacity"], old_ns)
        if values is not None and any(values[:2]):
            setting["opacity"] = envelope(*values, new_ns)


class StimulusFades(QWidget):
    changed = pyqtSignal()

    def __init__(self, function: dict[str, Any], duration: Any) -> None:
        super().__init__()
        self.original = deepcopy(function)
        self.duration_ns = duration.duration.ns() if isinstance(duration, Fixed) else 0
        self.values = (
            fade_values(function, self.duration_ns) if self.duration_ns else None
        )
        self.edited = False
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)
        self.fade_in, self.fade_out = QLineEdit(), QLineEdit()
        for index, (title, edit) in enumerate(
            (("Fade in (s)", self.fade_in), ("Fade out (s)", self.fade_out))
        ):
            edit.setMinimumWidth(0)
            edit.setText(
                seconds(int(self.values[index])) if self.values is not None else "—"
            )
            edit.setEnabled(self.values is not None)
            edit.setToolTip(
                "0 disables the fade"
                if self.values is not None
                else "Saved custom opacity is preserved; fades require a fixed epoch duration and a constant base or standard fade envelope"
            )
            edit.textEdited.connect(self.mark_changed)
            row.addWidget(field(title, edit), 1)
        equal_row_height(self.fade_in, self.fade_out)

    def mark_changed(self) -> None:
        self.edited = True
        self.changed.emit()

    def read(self) -> dict[str, Any]:
        if not self.edited or self.values is None:
            return deepcopy(self.original)
        try:
            times = [
                Time(seconds=format(Decimal(e.text().strip()), "f")).ns()
                for e in (self.fade_in, self.fade_out)
            ]
        except (ValueError, InvalidOperation) as error:
            raise ValueError("Enter nonnegative fade durations in seconds") from error
        return envelope(times[0], times[1], self.values[2], self.duration_ns)
