from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from cephvr.acquisition.v1 import camera_pb2
from cephvr.gui import tracking_live
from cephvr.tracking.v1 import services_pb2 as wire


def test_tracking_diagnostic_presentation_copies_frame_and_checks_exact_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PreviewPixels:
        def __init__(self, _layout: object) -> None:
            pass

        def prepare_preview(self, pixels: bytes, _depth: int) -> object:
            return SimpleNamespace(
                data=pixels,
                width=2,
                height=1,
                row_stride_bytes=2,
                channel_order="gray",
            )

    monkeypatch.setattr(tracking_live, "PixelPreparer", PreviewPixels)
    diagnostic_id, run_id = str(uuid4()), str(uuid4())
    frame = wire.TrackingDiagnosticFrame(
        available=True,
        diagnostic_id=diagnostic_id,
        configuration_revision=8,
        preview_run_id=run_id,
        source_frame_id=11,
        source_host_receipt_ns=100,
        produced_monotonic_ns=120,
        image=camera_pb2.CameraImageLayout(
            width=2,
            height=1,
            pixel_format="Mono8",
            row_stride_bytes=2,
            image_payload_bytes=2,
        ),
        image_bytes=b"\x20\xe0",
    )
    frame.points.add(
        stage=wire.TRACKING_DIAGNOSTIC_STAGE_POSE, label="tip", x_px=1, y_px=0
    )

    shown = tracking_live.tracking_diagnostic_presentation(
        frame,
        diagnostic_id=diagnostic_id,
        configuration_revision=8,
        preview_run_id=run_id,
        maximum_image_bytes=4,
    )
    assert shown.image.width() == 2
    assert shown.image.pixelColor(1, 0).red() == 0xE0
    assert shown.source_frame_id == 11
    assert shown.points == ((wire.TRACKING_DIAGNOSTIC_STAGE_POSE, "tip", 1, 0),)

    with pytest.raises(ValueError, match="current preview scope"):
        tracking_live.tracking_diagnostic_presentation(
            frame,
            diagnostic_id=diagnostic_id,
            configuration_revision=9,
            preview_run_id=run_id,
            maximum_image_bytes=4,
        )
