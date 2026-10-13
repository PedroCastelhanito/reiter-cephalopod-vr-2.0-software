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
    ) -> None:
        missing = [face for face in FACES if face not in available_faces]
        if missing:
            text = "Assign and enable displays: " + ", ".join(missing) + "."
            self.reference.setText(text)
            self.projection.setText(text)
            return
        self.reference.setText(
            "Reference bars can be measured before screen calibration."
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
            "Measure reference bars first: " + ", ".join(missing) + "."
            if missing
            else "Display bindings, geometry and measurements are checked on launch."
        )


def _positive(value: str) -> bool:
    try:
        number = float(value)
        return math.isfinite(number) and number > 0
    except ValueError:
        return False
