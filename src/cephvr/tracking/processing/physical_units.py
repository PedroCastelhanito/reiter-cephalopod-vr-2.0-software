"""T20/T38 conversion of pixel-space estimator controls into calibrated outputs."""

import math

from cephvr.tracking.config.models.records import DriveTriplet


def physical_drive(drive: DriveTriplet, pixels_per_mm: float) -> DriveTriplet:
    if not math.isfinite(pixels_per_mm) or pixels_per_mm <= 0:
        raise ValueError("Tracking requires a finite positive camera pixels_per_mm")
    return DriveTriplet(
        forward_drive=drive.forward_drive / pixels_per_mm,
        sideways_drive=drive.sideways_drive / pixels_per_mm,
        turn_drive=math.degrees(drive.turn_drive),
    )
