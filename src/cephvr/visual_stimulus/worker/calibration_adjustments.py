"""Confirm bounded live grid updates on the existing GL-owner presentation path."""

from collections.abc import Callable

from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.resources.display_calibration import (
    PreparedDisplayCalibration,
)
from cephvr.visual_stimulus.v1 import messages_pb2 as messages
from cephvr.visual_stimulus.v1 import runtime_pb2 as view
from cephvr.visual_stimulus.worker.ports import EnginePort


def update_presentation(
    request: messages.UpdateDisplayCalibrationCommand,
    deadline_ns: int,
    *,
    prepared: PreparedDisplayCalibration | None,
    display: DisplayProfile | None,
    evidence: view.DisplayCalibrationEvidence,
    engine: EnginePort,
    clock: Callable[[], int],
    report: Callable[[messages.WorkerCommand, int], None],
) -> None:
    from cephvr.visual_stimulus.config.calibration_adjustments import (
        LIVE_ADJUSTABLE_VIEWS,
        CalibrationAdjustmentRejected,
        validated_update,
    )

    if (
        prepared is None
        or display is None
        or evidence.state != view.DISPLAY_CALIBRATION_STATE_ACTIVE
        or evidence.diagnostic_id != request.diagnostic_id
        or evidence.configuration_revision
        != request.command.target.configuration_revision
        or display.calibration_view not in LIVE_ADJUSTABLE_VIEWS
        or request.adjustment_sequence <= evidence.adjustment_sequence
    ):
        raise CalibrationAdjustmentRejected(
            "Live update targets an inactive or stale calibration"
        )
    if clock() >= deadline_ns:
        raise TimeoutError("Live update missed its original deadline")
    try:
        adjustments = validated_update(
            display.calibration_view,
            ((item.mapping_id, item.destination_xy) for item in request.adjustments),
            request.placement_json,
        )
        activities = engine.update_display_calibration(display, prepared, adjustments)
        expected = {output.output_id for output in display.active_outputs}
        if (
            {item.output_id for item in activities} != expected
            or len(activities) != len(expected)
            or any(
                item.error or item.swap_return_ns < item.swap_entry_ns
                for item in activities
            )
            or clock() >= deadline_ns
        ):
            raise RuntimeError("Live grid lacks actual presentation evidence")
    except CalibrationAdjustmentRejected as exc:
        evidence.failure_code = "CALIBRATION_ADJUSTMENT_REJECTED"
        evidence.failure_message = str(exc)[:1024]
        evidence.observed_monotonic_ns = clock()
        report(request.command, deadline_ns)
        raise
    except BaseException as exc:
        evidence.state = view.DISPLAY_CALIBRATION_STATE_UNKNOWN
        evidence.presented = False
        evidence.failure_code = "CALIBRATION_UPDATE"
        evidence.failure_message = str(exc)[:1024]
        evidence.observed_monotonic_ns = clock()
        report(request.command, deadline_ns)
        raise
    evidence.ClearField("failure_code")
    evidence.ClearField("failure_message")
    evidence.adjustment_sequence = request.adjustment_sequence
    evidence.observed_monotonic_ns = clock()
    report(request.command, deadline_ns)
