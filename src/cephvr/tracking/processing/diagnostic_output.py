"""Bounded diagnostic stage availability and exact-frame overlay encoding."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cephvr.tracking.types import PrivateFrame
from cephvr.tracking.v1 import services_pb2 as wire

DiagnosticOverlays = tuple[Any, Any, Any, Any]


def stage_status(
    request: wire.TrackingDiagnosticCommand,
) -> list[wire.TrackingDiagnosticStageStatus]:
    selected = set(request.selected_stages)
    prerequisites = {
        wire.TRACKING_DIAGNOSTIC_STAGE_POSE: set(),
        wire.TRACKING_DIAGNOSTIC_STAGE_SAMPLING_REGION: {
            wire.TRACKING_DIAGNOSTIC_STAGE_POSE
        },
        wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW: set(),
        wire.TRACKING_DIAGNOSTIC_STAGE_FLOW_QUALITY: {
            wire.TRACKING_DIAGNOSTIC_STAGE_POSE,
            wire.TRACKING_DIAGNOSTIC_STAGE_SAMPLING_REGION,
            wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW,
        },
        wire.TRACKING_DIAGNOSTIC_STAGE_LOCOMOTION: {
            wire.TRACKING_DIAGNOSTIC_STAGE_POSE,
            wire.TRACKING_DIAGNOSTIC_STAGE_SAMPLING_REGION,
            wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW,
            wire.TRACKING_DIAGNOSTIC_STAGE_FLOW_QUALITY,
        },
    }
    return [
        wire.TrackingDiagnosticStageStatus(
            stage=stage,
            state=(
                wire.TRACKING_DIAGNOSTIC_STAGE_STATE_AVAILABLE
                if prerequisites[stage] <= selected
                else wire.TRACKING_DIAGNOSTIC_STAGE_STATE_UNAVAILABLE
            ),
            reason=""
            if prerequisites[stage] <= selected
            else "required diagnostic prerequisite was disabled",
        )
        for stage in request.selected_stages
    ]


def diagnostic_frame(
    request: wire.TrackingDiagnosticCommand,
    frame: PrivateFrame,
    image_bytes: bytes | None,
    overlays: DiagnosticOverlays,
    *,
    clock: Callable[[], int],
    maximum_bytes: int,
    unavailable_reason: str = "",
) -> wire.TrackingDiagnosticFrame:
    points, rectangles, vectors, labels = overlays
    result = wire.TrackingDiagnosticFrame(
        diagnostic_id=request.diagnostic_id,
        configuration_revision=request.configuration_revision,
        preview_run_id=request.frames.buffer.preview.acquisition_run_id,
        source_frame_id=frame.source.frame_id,
        source_host_receipt_ns=frame.source.host_receipt_ns,
        produced_monotonic_ns=clock(),
        image=request.frames.buffer.image,
        image_bytes=image_bytes or b"",
        available=not unavailable_reason,
        unavailable_reason=unavailable_reason,
    )
    for stage, label, x, y in points:
        result.points.add(stage=stage, label=label, x_px=x, y_px=y)
    for stage, label, x, y, width, height in rectangles:
        result.rectangles.add(
            stage=stage,
            label=label,
            x_px=x,
            y_px=y,
            width_px=width,
            height_px=height,
        )
    for stage, label, x0, y0, x1, y1 in vectors:
        result.vectors.add(
            stage=stage,
            label=label,
            start_x_px=x0,
            start_y_px=y0,
            end_x_px=x1,
            end_y_px=y1,
        )
    for stage, text in labels:
        result.labels.add(stage=stage, text=text)

    def drop_last_overlay() -> bool:
        if result.vectors:
            del result.vectors[-1]
        elif result.rectangles:
            del result.rectangles[-1]
        elif result.points:
            del result.points[-1]
        else:
            if not result.labels:
                return False
            del result.labels[-1]
        result.overlays_truncated = True
        return True

    while (
        len(result.points)
        + len(result.rectangles)
        + len(result.vectors)
        + len(result.labels)
        > request.maximum_overlay_items
        or result.ByteSize() > maximum_bytes
    ):
        if not drop_last_overlay():
            result.image_bytes = b""
            result.available = False
            result.unavailable_reason = (
                "acquired image exceeds the diagnostic frame byte bound"
            )
            break
    return result
