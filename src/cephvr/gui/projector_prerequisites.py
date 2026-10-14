"""Local calibration prerequisites; output launch retains authoritative validation."""

import math
from collections.abc import Mapping

from cephvr.gui.components import label
from cephvr.gui.projector_geometry import FACES


class CalibrationPrerequisites:
    def __init__(self) -> None:
        self.reference = label("", "muted")
        self.projection = label("", "muted")
        for control in (self.reference, self.projection):
            control.setWordWrap(True)

    def refresh(
        self,
        available_faces: tuple[str, ...],
        measurements: Mapping[str, Mapping[str, str]],
        assigned_faces: tuple[str, ...] | None = None,
    ) -> None:
        assigned_faces = available_faces if assigned_faces is None else assigned_faces
        missing = [face for face in FACES if face not in assigned_faces]
        if missing:
            text = "Assign a display to: " + ", ".join(missing) + "."
            self.reference.setText(text)
            self.projection.setText(text)
            return
        if not available_faces:
            text = "Tick Use for at least one display."
            self.reference.setText(text)
            self.projection.setText(text)
            return
        self.reference.setText(
            "Tick Use for the projector(s) to position; the others stay dark. "
            "Align the cyan outline with the screen edges, then measure the bars."
        )
        missing = [
            face
            for face in FACES
            if not all(
                _positive(measurements.get(face, {}).get(f"reference_{axis}_mm", ""))
                for axis in ("x", "y")
            )
        ]
        self.projection.setText(
            "Without a measurement each edge starts at the projector border: "
            + ", ".join(missing)
            + "."
            if missing
            else "Edges start centered from the measurement; edit any edge to override."
        )


def _positive(value: str) -> bool:
    try:
        number = float(value)
        return math.isfinite(number) and number > 0
    except ValueError:
        return False
