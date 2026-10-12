"""Admission checks for one exact active grid without session work."""

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.visual_stimulus.config.calibration_adjustments import validated_adjustments
from cephvr.visual_stimulus.v1 import runtime_pb2 as vp


def validate_live_update(
    request: wire.VisualStimulusDisplayCalibrationUpdateRequest,
    *,
    display: pb.VisualStimulusDisplayView | None,
    session_active: bool,
) -> None:
    evidence = (
        display.calibration
        if display is not None and display.HasField("calibration")
        else None
    )
    if (
        session_active
        or evidence is None
        or evidence.state != vp.DISPLAY_CALIBRATION_STATE_ACTIVE
        or evidence.diagnostic_id != request.diagnostic_id
        or evidence.calibration_view != "frame_grid"
        or evidence.configuration_revision != request.configuration_revision
        or request.adjustment_sequence <= evidence.adjustment_sequence
    ):
        raise ValueError(
            "Live calibration update targets a stale or inactive diagnostic"
        )
    validated_adjustments(
        (item.mapping_id, item.destination_xy) for item in request.adjustments
    )
