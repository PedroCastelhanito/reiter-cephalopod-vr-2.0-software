"""Per-capture native counter and timestamp transition diagnostics (A09)."""

from __future__ import annotations

from cephvr.acquisition.buffers.records import FrameDiagnostic
from cephvr.acquisition.camera.types import GrabResult
from cephvr.acquisition.v1 import camera_pb2


class FrameDiagnosticTracker:
    """Bounded baseline state; never synthesizes frames or native values."""

    def __init__(
        self,
        clock: camera_pb2.CameraClockDescriptor,
        *,
        timestamp_available: bool,
        counter_available: bool,
    ) -> None:
        self._counter_semantics = clock.counter_semantics
        self._counter_wrap = clock.counter_wrap_semantics
        self._last_valid_counter: int | None = None
        self._counter_unavailable = not counter_available
        self._timestamp_unavailable = not timestamp_available

    def initial_unavailable(self) -> tuple[FrameDiagnostic, ...]:
        diagnostics: list[FrameDiagnostic] = []
        if self._timestamp_unavailable:
            diagnostics.append(
                FrameDiagnostic(
                    "NATIVE_TIMESTAMP_UNAVAILABLE",
                    None,
                    "optional native timestamp is unavailable at preparation",
                )
            )
        if self._counter_unavailable:
            diagnostics.append(
                FrameDiagnostic(
                    "NATIVE_COUNTER_UNAVAILABLE",
                    None,
                    "optional native frame counter is unavailable at preparation",
                )
            )
        return tuple(diagnostics)

    def reset(self) -> None:
        self._last_valid_counter = None
        self._counter_unavailable = False
        self._timestamp_unavailable = False

    def observe(self, result: GrabResult) -> tuple[FrameDiagnostic, ...]:
        diagnostics: list[FrameDiagnostic] = []
        if result.camera_timestamp_ns is None:
            if not self._timestamp_unavailable:
                diagnostics.append(
                    FrameDiagnostic(
                        "NATIVE_TIMESTAMP_UNAVAILABLE",
                        None,
                        "optional native timestamp is unavailable",
                    )
                )
            self._timestamp_unavailable = True
        else:
            self._timestamp_unavailable = False

        counter = result.camera_frame_counter
        if counter is None:
            if not self._counter_unavailable:
                diagnostics.append(
                    FrameDiagnostic(
                        "NATIVE_COUNTER_UNAVAILABLE",
                        None,
                        "optional native frame counter is unavailable",
                    )
                )
            self._counter_unavailable = True
            self._last_valid_counter = None
            return tuple(diagnostics)
        self._counter_unavailable = False
        previous = self._last_valid_counter
        if not result.valid_image or previous is None:
            if result.valid_image:
                self._last_valid_counter = counter
            return tuple(diagnostics)
        if self._is_documented_wrap(previous, counter):
            self._last_valid_counter = counter
            return tuple(diagnostics)
        if counter <= previous:
            diagnostics.append(
                FrameDiagnostic(
                    "NATIVE_COUNTER_DISCONTINUITY",
                    None,
                    f"previous={previous}; current={counter}; comparison=rebaselined",
                )
            )
        elif self._counter_semantics == "frames" and counter > previous + 1:
            missing = counter - previous - 1
            diagnostics.append(
                FrameDiagnostic(
                    "NATIVE_COUNTER_GAP",
                    None,
                    f"previous={previous}; current={counter}; missing={missing}",
                )
            )
        self._last_valid_counter = counter
        return tuple(diagnostics)

    def _is_documented_wrap(self, previous: int, current: int) -> bool:
        return (
            self._counter_wrap == "wraps_at_65535"
            and previous == 65535
            and current == 1
        )
