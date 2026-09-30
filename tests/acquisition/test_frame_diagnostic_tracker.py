"""Prepared native-counter transition cases for the A09 rig suite."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from cephvr.acquisition.camera.types import GrabResult
from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.worker.frame_diagnostics import FrameDiagnosticTracker


@dataclass(frozen=True)
class _Result:
    camera_frame_counter: int | None
    camera_timestamp_ns: int | None = 10
    valid_image: bool = True


def _tracker(semantics: str, wrap: str = "unknown") -> FrameDiagnosticTracker:
    return FrameDiagnosticTracker(
        camera_pb2.CameraClockDescriptor(
            counter_semantics=semantics,
            counter_wrap_semantics=wrap,
        ),
        timestamp_available=True,
        counter_available=True,
    )


def _observe(tracker: FrameDiagnosticTracker, counter: int) -> tuple[str, ...]:
    result = cast(GrabResult, _Result(counter))
    return tuple(diagnostic.code for diagnostic in tracker.observe(result))


def test_frame_counter_gap_is_only_classified_for_frame_semantics() -> None:
    frames = _tracker("frames")
    assert _observe(frames, 20) == ()
    assert _observe(frames, 23) == ("NATIVE_COUNTER_GAP",)

    triggers = _tracker("triggers")
    assert _observe(triggers, 20) == ()
    assert _observe(triggers, 23) == ()


def test_native_counter_reset_rebaselines_without_synthesizing_missing_frames() -> None:
    tracker = _tracker("frames")
    assert _observe(tracker, 40) == ()
    assert _observe(tracker, 3) == ("NATIVE_COUNTER_DISCONTINUITY",)
    assert _observe(tracker, 4) == ()


def test_only_documented_counter_wrap_is_exempt_from_discontinuity() -> None:
    documented = _tracker("frames", "wraps_at_65535")
    assert _observe(documented, 65535) == ()
    assert _observe(documented, 1) == ()

    unknown = _tracker("frames")
    assert _observe(unknown, 65535) == ()
    assert _observe(unknown, 1) == ("NATIVE_COUNTER_DISCONTINUITY",)
