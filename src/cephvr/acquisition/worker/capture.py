"""Single-owner camera wait, frame accounting, and bounded pixel handoff (A03/A07)."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from cephvr.acquisition.buffers.pixel_pool import PixelBufferPool
from cephvr.acquisition.buffers.queue import RecordingQueue
from cephvr.acquisition.buffers.records import FrameDiagnostic, FrameRecord
from cephvr.acquisition.buffers.ring import SharedRing
from cephvr.acquisition.camera.errors import CameraAdapterError
from cephvr.acquisition.camera.types import CameraAdapter, GrabResult, PixelLayout
from cephvr.acquisition.worker.warnings import WarningOccurrence
from cephvr.shared.clock import host_time_ns


@dataclass(frozen=True, slots=True)
class CaptureWindow:
    """Host receipt interval for one scheduled trial; stop is exclusive."""

    start_ns: int
    end_ns: int

    def __post_init__(self) -> None:
        if self.start_ns <= 0 or self.end_ns <= self.start_ns:
            raise ValueError("capture window requires positive ordered host times")


class CameraCaptureLoop:
    """Process camera results on the lifecycle owner thread only.

    The capture event wait is joint with the manual control event. `capture_handoff`
    is called after every wake, before RetrieveResult, to prioritize queued commands
    and clear the control event under the owner's handoff lock.
    """

    def __init__(
        self,
        *,
        adapter: CameraAdapter,
        layout: PixelLayout,
        wait_timeout_ns: Callable[[], int],
        frame_silence_timeout_ns: int,
        tracking_ring: SharedRing | None = None,
        preview_ring: SharedRing | None = None,
        recording_queue: RecordingQueue | None = None,
        pixel_pool: PixelBufferPool | None = None,
        session_preview: bool = False,
        preview_max_hz: float | None = None,
        recording_window: Callable[[], CaptureWindow | None] = lambda: None,
        warning_occurrence: Callable[[WarningOccurrence], None] = lambda _: None,
        diagnostics_for: Callable[
            [GrabResult], tuple[FrameDiagnostic, ...]
        ] = lambda _: (),
        first_trial_frame: Callable[[FrameRecord], None] = lambda _: None,
        clock_ns: Callable[[], int] = host_time_ns,
    ) -> None:
        if (recording_queue is None) != (pixel_pool is None):
            raise ValueError(
                "recording queue and pixel pool must be configured together"
            )
        if (
            recording_queue is not None
            and pixel_pool is not None
            and pixel_pool.capacity < recording_queue.capacity_frames + 2
        ):
            raise ValueError(
                "recording pool must cover waiting, in-flight and capture buffers"
            )
        if preview_max_hz is not None and (
            not math.isfinite(preview_max_hz) or preview_max_hz <= 0
        ):
            raise ValueError("preview maximum rate must be finite and positive")
        self.adapter = adapter
        self.layout = layout
        self.wait_timeout_ns = wait_timeout_ns
        if frame_silence_timeout_ns <= 0:
            raise ValueError("frame silence timeout must be positive")
        self.frame_silence_timeout_ns = frame_silence_timeout_ns
        self.tracking_ring = tracking_ring
        self.preview_ring = preview_ring
        self.recording_queue = recording_queue
        self.pixel_pool = pixel_pool
        self.session_preview = session_preview
        self.preview_period_ns = (
            None
            if preview_max_hz is None
            else math.ceil(1_000_000_000 / preview_max_hz)
        )
        self.recording_window = recording_window
        self.warning_occurrence = warning_occurrence
        self.diagnostics_for = diagnostics_for
        self.first_trial_frame = first_trial_frame
        self.clock_ns = clock_ns
        self._acquisition_frame_id = 0
        self._trial_frame_id = 0
        self._received = 0
        self._excluded = 0
        self._last_excluded_counter: int | None = None
        self._last_native_counter: int | None = None
        self._last_receipt_ns = 0
        self._last_usable_ns = 0
        self._last_preview_ns = 0
        self._trial_activity_reported = False
        self._first_usable_reported = False

    @property
    def received_frame_count(self) -> int:
        return self._received

    @property
    def last_native_counter(self) -> int | None:
        return self._last_native_counter

    @property
    def last_receipt_ns(self) -> int:
        return self._last_receipt_ns

    @property
    def last_usable_ns(self) -> int:
        return self._last_usable_ns

    @property
    def excluded_frame_count(self) -> int:
        return self._excluded

    @property
    def last_excluded_counter(self) -> int | None:
        return self._last_excluded_counter

    def reset_trial_counters(self) -> None:
        """Reset trial IDs only after prior capture and recording closure."""
        self._trial_frame_id = 0
        self._received = 0
        self._excluded = 0
        self._last_excluded_counter = None
        self._trial_activity_reported = False
        self._first_usable_reported = False
        self._last_usable_ns = 0

    def capture_once(self, capture_handoff: Callable[[], bool]) -> bool:
        """Wait once, then retrieve/copy/account one result if commands permit it."""
        timeout_ns = self.wait_timeout_ns()
        if timeout_ns < 0:
            raise ValueError("camera wait timeout must be nonnegative")
        outcome = self.adapter.wait_for_frame_or_control(timeout_ns)
        if not capture_handoff():
            return False
        if outcome != "frame":
            self._raise_if_usable_silence(self.clock_ns())
            return False
        result = self.adapter.retrieve(0)
        if result is None:
            raise CameraAdapterError(
                "SDK_STATE",
                "SDK result wait signaled without a retrievable grab result",
            )
        try:
            receipt_ns = self.clock_ns()
            if receipt_ns <= 0 or receipt_ns < self._last_receipt_ns:
                raise RuntimeError("camera host receipt clock regressed")
            self._last_receipt_ns = receipt_ns
            counter = result.camera_frame_counter
            timestamp = result.camera_timestamp_ns
            window = self.recording_window()
            in_trial = (
                window is not None and window.start_ns <= receipt_ns < window.end_ns
            )
            if in_trial:
                frame_id = self._trial_frame_id
                self._trial_frame_id += 1
                self._received += 1
            else:
                frame_id = self._acquisition_frame_id
                self._acquisition_frame_id += 1
                if window is not None and receipt_ns >= window.end_ns:
                    self._excluded += 1
                    if counter is not None:
                        self._last_excluded_counter = counter
            if counter is not None:
                self._last_native_counter = counter
            diagnostics = self.diagnostics_for(result)
            invalid_code = "INVALID_IMAGE" if not result.valid_image else None
            if invalid_code is not None:
                diagnostics = _with_diagnostic(
                    diagnostics,
                    FrameDiagnostic(
                        "INVALID_IMAGE",
                        _bounded_text(result.error_code, 64),
                        _bounded_text(result.error_message, 1024),
                    ),
                )
            record = FrameRecord(
                frame_id,
                receipt_ns,
                counter,
                timestamp,
                result.valid_image,
                invalid_code,
                diagnostics,
            )
            if in_trial or (self.preview_ring is not None and not self.session_preview):
                self._record_warnings(diagnostics, receipt_ns, frame_id)
            tracking_capture = in_trial or (
                self.preview_ring is not None and not self.session_preview
            )
            if (
                tracking_capture
                and self.tracking_ring is not None
                and (
                    not result.valid_image
                    or any(
                        item.code
                        in {"NATIVE_COUNTER_GAP", "NATIVE_COUNTER_DISCONTINUITY"}
                        for item in diagnostics
                    )
                )
            ):
                self.tracking_ring.advance_discontinuity()
            if result.valid_image:
                self._last_usable_ns = receipt_ns
                pixels = result.pixels
                if pixels is None or result.layout != self.layout:
                    raise RuntimeError(
                        "valid camera result differs from prepared layout"
                    )
                if tracking_capture:
                    self._publish_tracking(record, pixels)
                self._publish_preview(record, pixels, receipt_ns, in_trial)
                if not self._first_usable_reported:
                    self._first_usable_reported = True
                    self.first_trial_frame(record)
                if in_trial:
                    self._enqueue_recording(record, pixels, receipt_ns)
                    if not self._trial_activity_reported:
                        self._trial_activity_reported = True
                        # The general callback above provides the same first-frame
                        # evidence for trial capture and manual preview.
            else:
                if in_trial:
                    self._enqueue_invalid_record(record, receipt_ns)
            self._raise_if_usable_silence(self.clock_ns())
            return True
        finally:
            result.release()

    def _raise_if_usable_silence(self, now_ns: int) -> None:
        window = self.recording_window()
        if (
            window is not None
            and now_ns < window.end_ns
            and now_ns
            >= max(window.start_ns, self._last_usable_ns)
            + self.frame_silence_timeout_ns
        ):
            raise RuntimeError("usable camera frame silence exceeded its limit")

    def _publish_tracking(self, record: FrameRecord, pixels: memoryview) -> None:
        ring = self.tracking_ring
        if ring is not None:
            ring.publish(record, pixels)

    def _publish_preview(
        self, record: FrameRecord, pixels: memoryview, receipt_ns: int, in_trial: bool
    ) -> None:
        ring = self.preview_ring
        if ring is None:
            return
        if self.session_preview != in_trial:
            return
        if (
            self.preview_period_ns is not None
            and self._last_preview_ns > 0
            and receipt_ns - self._last_preview_ns < self.preview_period_ns
        ):
            return
        # A03 preview slots preserve native pixels; each consumer converts its copy.
        ring.publish(record, pixels)
        self._last_preview_ns = receipt_ns

    def _enqueue_recording(
        self, record: FrameRecord, pixels: memoryview, receipt_ns: int
    ) -> None:
        queue, pool = self.recording_queue, self.pixel_pool
        window = self.recording_window()
        if queue is None or pool is None or window is None:
            return
        if not window.start_ns <= receipt_ns < window.end_ns:
            return
        private_pixels = pool.acquire_nowait()
        if private_pixels.nbytes != pixels.nbytes:
            pool.release(private_pixels)
            raise RuntimeError(
                "recording pool differs from confirmed native frame size"
            )
        private_pixels[:] = pixels
        try:
            admission = queue.enqueue(record, private_pixels)
        except BaseException:
            pool.release(private_pixels)
            raise
        if admission.dropped_pixels is not None:
            pool.release(admission.dropped_pixels)

    def _enqueue_invalid_record(self, record: FrameRecord, receipt_ns: int) -> None:
        queue = self.recording_queue
        window = self.recording_window()
        if (
            queue is None
            or window is None
            or not window.start_ns <= receipt_ns < window.end_ns
        ):
            return
        admission = queue.enqueue(record, None)
        if admission.dropped_pixels is not None:
            raise RuntimeError("invalid frame unexpectedly dropped pixel payload")

    def _record_warnings(
        self,
        diagnostics: tuple[FrameDiagnostic, ...],
        observed_ns: int,
        frame_id: int,
    ) -> None:
        for diagnostic in diagnostics:
            self.warning_occurrence(
                WarningOccurrence(
                    diagnostic.code,
                    observed_ns,
                    diagnostic.native_code,
                    _bounded_text(
                        f"frame_id={frame_id}; {diagnostic.details or ''}", 1024
                    )
                    or "",
                )
            )


def _with_diagnostic(
    values: tuple[FrameDiagnostic, ...], diagnostic: FrameDiagnostic
) -> tuple[FrameDiagnostic, ...]:
    if any(item.code == diagnostic.code for item in values):
        return values
    if len(values) >= 8:
        raise RuntimeError("frame diagnostic catalogue capacity exhausted")
    return (*values, diagnostic)


def _bounded_text(value: str | None, max_bytes: int) -> str | None:
    if value is None:
        return None
    marker = " [truncated]"
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    marker_bytes = marker.encode("utf-8")
    prefix = encoded[: max(0, max_bytes - len(marker_bytes))]
    while prefix:
        try:
            return prefix.decode("utf-8") + marker
        except UnicodeDecodeError:
            prefix = prefix[:-1]
    return marker[:max_bytes]
