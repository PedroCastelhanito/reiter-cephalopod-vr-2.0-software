"""Producer completion marker kept separate from frame records and ring sealing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CaptureEndMarker:
    received_frame_count: int
    recording_end_monotonic_ns: int
    actual_stop_monotonic_ns: int | None
    excluded_frame_count: int | None
    last_excluded_camera_counter: int | None
    excluded_accounting_complete: bool

    def __post_init__(self) -> None:
        if self.received_frame_count < 0:
            raise ValueError("received frame count must be nonnegative")
        if self.recording_end_monotonic_ns <= 0:
            raise ValueError("recording cutoff must be positive host monotonic time")
        if (
            self.actual_stop_monotonic_ns is not None
            and self.actual_stop_monotonic_ns <= 0
        ):
            raise ValueError(
                "confirmed stop time must be a positive host monotonic value"
            )
        if self.excluded_frame_count is not None and self.excluded_frame_count < 0:
            raise ValueError("excluded frame count must be nonnegative when known")
        if (
            self.last_excluded_camera_counter is not None
            and self.last_excluded_camera_counter < 0
        ):
            raise ValueError("excluded camera counter must be nonnegative")
