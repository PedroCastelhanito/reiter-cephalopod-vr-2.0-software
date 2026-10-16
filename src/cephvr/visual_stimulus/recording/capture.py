"""Bounded immutable composite-frame handoff for the V12 recording owner."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal, cast

from .evidence import EncoderInput, EvidenceWriter
from .metrics import RecordingMetrics


@dataclass(frozen=True)
class CompositeFrame:
    group_id: int
    video_frame_index: int | None
    width: int
    height: int
    pixel_format: Literal[
        "rgba8_top_down",
        "r10g10b10a2_le_top_down",
        "rgba8_bottom_up",
        "r10g10b10a2_le_bottom_up",
    ]
    pixels: bytes | bytearray
    source_host_ns: int = 0

    def __post_init__(self) -> None:
        if (
            self.group_id < 0
            or (self.video_frame_index is not None and self.video_frame_index < 0)
            or min(self.width, self.height) <= 0
        ):
            raise ValueError("invalid review-composite identity or dimensions")
        if len(self.pixels) != self.width * self.height * 4:
            raise ValueError(
                "review composite must contain exactly four bytes per pixel"
            )


@dataclass(frozen=True)
class CaptureAdmission:
    admitted: bool
    video_frame_index: int | None
    disposition: str


@dataclass(frozen=True)
class CaptureReservation:
    token: int
    group_id: int
    source_host_ns: int = 0


@dataclass(frozen=True)
class RecordingCounts:
    eligible_group_count: int
    admitted_count: int
    input_submitted_count: int
    capacity_drop_count: int
    failed_capture_count: int
    unresolved_capture_count: int
    final_input_group_id: int | None
    encoded_frame_count: int = 0
    duplicate_frame_count: int = 0
    same_slot_omission_count: int = 0
    selected_real_count: int = 0


class RecordingWorker:
    """One-thread evidence-first drain over bounded frame slots and encoder writes.

    The rendering owner supplies an already-tiled device-code buffer. ``offer`` copies
    it before returning, so the renderer can safely advance to the next frame.
    ``drain_once`` must run on the one recording thread and processes pending evidence
    before making progress on raw FFmpeg input.
    """

    def __init__(
        self,
        *,
        capture_slots: int,
        evidence: EvidenceWriter,
        encoder: EncoderInput,
        max_encoder_write_chunk: int = 256 * 1024,
        on_submitted: Callable[[CompositeFrame], None] | None = None,
        video_start_ns: int,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        if min(capture_slots, max_encoder_write_chunk) <= 0:
            raise ValueError("recording capacities must be positive")
        self.metrics = RecordingMetrics(clock_ns)
        self.capture_slots = capture_slots
        self.evidence = evidence
        self.encoder = encoder
        self.max_encoder_write_chunk = max_encoder_write_chunk
        self.on_submitted = on_submitted
        if video_start_ns < 0:
            raise ValueError("video start must be nonnegative")
        self.video_start_ns = video_start_ns
        self._frames: deque[CompositeFrame] = deque()
        self._lock = threading.Lock()
        self._reservations: dict[int, CaptureReservation] = {}
        self._next_token = 0
        self._admitted = 0
        self._eligible = 0
        self._submitted = 0
        self._dropped = 0
        self._failed_capture = 0
        self._last_group: int | None = None
        self._last_eligible: tuple[int, int] | None = None
        self._active_frame: CompositeFrame | None = None
        self._active_offset = 0
        self._active_normalized = False
        self._cutoff_ns: int | None = None
        self._failed = False
        self._selected_real = 0

    def offer(self, frame: CompositeFrame) -> CaptureAdmission:
        if frame.video_frame_index is not None:
            raise ValueError("video index is assigned only when writing encoder input")
        reservation, disposition, index = self.classify_and_reserve(
            frame.group_id, frame.source_host_ns
        )
        if reservation is None:
            return CaptureAdmission(False, index, disposition)
        self.complete_capture(
            reservation,
            width=frame.width,
            height=frame.height,
            pixel_format=frame.pixel_format,
            pixels=frame.pixels,
        )
        return CaptureAdmission(True, None, "admitted")

    def classify_and_reserve(
        self, group_id: int, source_host_ns: int
    ) -> tuple[CaptureReservation | None, str, int | None]:
        """Admit each ordered render group once, without rate-based resampling."""
        if group_id < 0 or source_host_ns < self.video_start_ns:
            raise ValueError("source identity or evaluation time precedes trial start")
        with self._lock:
            if self._failed or self._cutoff_ns is not None:
                raise RuntimeError("recording admission is closed")
            if self._last_eligible is not None:
                last_group, last_time = self._last_eligible
                if group_id <= last_group or source_host_ns < last_time:
                    raise ValueError(
                        "render groups and evaluation times must be ordered"
                    )
            self._last_eligible = (group_id, source_host_ns)
            self._eligible += 1
            if self._inflight_capture_count() >= self.capture_slots:
                self._dropped += 1
                return None, "capacity_drop", None
            reservation = CaptureReservation(self._next_token, group_id, source_host_ns)
            self._next_token += 1
            self._reservations[reservation.token] = reservation
            self.metrics.reserve(reservation.group_id, self._inflight_capture_count())
            self._admitted += 1
            return reservation, "admitted", None

    def complete_capture(
        self,
        reservation: CaptureReservation,
        *,
        width: int,
        height: int,
        pixel_format: str,
        pixels: bytes | bytearray | memoryview,
        take_ownership: bool = False,
    ) -> None:
        """Copy borrowed pixels, or consume an exclusively owned bytearray.

        With take_ownership, callers must never access the buffer after success.
        Validation failure leaves ownership with the caller.
        """
        if take_ownership and not isinstance(pixels, bytearray):
            raise TypeError("owned capture requires a bytearray")
        if pixel_format not in {
            "rgba8_top_down",
            "r10g10b10a2_le_top_down",
            "rgba8_bottom_up",
            "r10g10b10a2_le_bottom_up",
        }:
            raise ValueError("unsupported review-composite pixel format")
        owned = CompositeFrame(
            group_id=reservation.group_id,
            video_frame_index=None,
            width=width,
            height=height,
            pixel_format=cast(
                Literal[
                    "rgba8_top_down",
                    "r10g10b10a2_le_top_down",
                    "rgba8_bottom_up",
                    "r10g10b10a2_le_bottom_up",
                ],
                pixel_format,
            ),
            pixels=pixels
            if take_ownership and isinstance(pixels, bytearray)
            else bytearray(pixels),
            source_host_ns=reservation.source_host_ns,
        )
        with self._lock:
            current = self._reservations.get(reservation.token)
            if current != reservation:
                raise RuntimeError("capture reservation is stale or already completed")
            del self._reservations[reservation.token]
            self.metrics.ready(reservation.group_id)
            self._selected_real += 1
            self._frames.append(owned)
            self._frames = deque(sorted(self._frames, key=lambda item: item.group_id))

    def cancel_reservation(self, reservation: CaptureReservation) -> None:
        with self._lock:
            current = self._reservations.get(reservation.token)
            if current != reservation:
                raise RuntimeError("capture reservation is stale or already completed")
            del self._reservations[reservation.token]
            self.metrics.release(reservation.group_id, cancelled=True)
            self._failed_capture += 1

    def drain_once(self) -> bool:
        """Service evidence first, then one bounded write chunk; return if progressed."""
        if self._failed:
            raise RuntimeError("recording input failed; cannot retry")
        try:
            if self.evidence.pending_bytes:
                self.evidence.write_pending()
                return True
            return self._drain_frame_once()
        except Exception:
            self._failed = True
            raise

    def set_cutoff(self, cutoff_ns: int) -> None:
        if cutoff_ns < self.video_start_ns:
            raise ValueError("video cutoff precedes video start")
        with self._lock:
            if self._cutoff_ns is not None and self._cutoff_ns != cutoff_ns:
                raise RuntimeError(
                    "recording cutoff cannot change after admission seal"
                )
            self._cutoff_ns = cutoff_ns

    def _inflight_capture_count(self) -> int:
        return (
            len(self._reservations)
            + len(self._frames)
            + int(self._active_frame is not None)
        )

    def _drain_frame_once(self) -> bool:
        with self._lock:
            if self._active_frame is None:
                if not self._frames:
                    return False
                frame = self._frames[0]
                if any(
                    item.group_id < frame.group_id
                    for item in self._reservations.values()
                ):
                    return False
                self._frames.popleft()
                self.metrics.dequeue(frame.group_id)
                self._active_frame = replace(frame, video_frame_index=self._submitted)
            frame = self._active_frame
            assert frame.video_frame_index is not None
            normalize = not self._active_normalized
            offset = self._active_offset
        # Only the recording thread changes the active pixels. Admission and
        # accounting must remain available while the native row copies run.
        if normalize:
            started = self.metrics.clock_ns()
            normalized_frame = _ffmpeg_input_order(frame)
            completed = self.metrics.clock_ns()
            self.metrics.observe(
                "normalization",
                completed - started,
                sample={
                    "group_id": frame.group_id,
                    "video_frame_index": frame.video_frame_index,
                    "start_monotonic_ns": started,
                    "end_monotonic_ns": completed,
                },
            )
            with self._lock:
                if self._active_frame is not frame or self._active_offset != offset:
                    raise RuntimeError(
                        "recording frame ownership changed during normalization"
                    )
                frame = normalized_frame
                self._active_frame = frame
                self._active_normalized = True
        end = min(len(frame.pixels), offset + self.max_encoder_write_chunk)
        chunk = memoryview(frame.pixels)[offset:end]
        started = self.metrics.clock_ns()
        consumed = self.encoder.write_chunk(chunk)
        if consumed < 0 or consumed > len(chunk):
            raise RuntimeError("encoder input returned an invalid write count")
        completed = self.metrics.clock_ns()
        self.metrics.write(
            completed - started,
            consumed,
            group_id=frame.group_id,
            video_frame_index=cast(int, frame.video_frame_index),
            started_ns=started,
            completed_ns=completed,
            frame_complete=offset + consumed == len(frame.pixels),
        )
        if consumed == 0:
            return False
        completed_frame: CompositeFrame | None = None
        with self._lock:
            if self._active_frame is not frame or self._active_offset != offset:
                raise RuntimeError("recording frame ownership changed during write")
            self._active_offset += consumed
            if self._active_offset == len(frame.pixels):
                completed_frame = frame
                self._submitted += 1
                self._last_group = frame.group_id
                self.metrics.release(frame.group_id)
                self._active_frame = None
                self._active_offset = 0
                self._active_normalized = False
        # Input acceptance is irreversible even if recording its mapping fails.
        if completed_frame is not None and self.on_submitted is not None:
            self.on_submitted(completed_frame)
        return True

    def counts(self) -> RecordingCounts:
        with self._lock:
            return RecordingCounts(
                eligible_group_count=self._eligible,
                admitted_count=self._admitted,
                input_submitted_count=self._submitted,
                capacity_drop_count=self._dropped,
                failed_capture_count=self._failed_capture,
                unresolved_capture_count=(
                    len(self._reservations)
                    + len(self._frames)
                    + int(self._active_frame is not None)
                ),
                final_input_group_id=self._last_group,
                encoded_frame_count=self._submitted,
                selected_real_count=self._selected_real,
            )

    def finish_input(self) -> RecordingCounts:
        with self._lock:
            if self._frames or self._reservations or self._active_frame is not None:
                raise RuntimeError(
                    "cannot close FFmpeg input while admitted captures remain"
                )
        if self._failed:
            raise RuntimeError("cannot finalize failed recording input")
        self.encoder.close_input()
        return self.counts()


def _ffmpeg_input_order(frame: CompositeFrame) -> CompositeFrame:
    """Accept GPU-oriented rows; normalize packed X bits and legacy bottom-up input."""
    if frame.pixel_format == "rgba8_top_down":
        return frame
    import numpy as np

    normalized = (
        frame.pixels if isinstance(frame.pixels, bytearray) else bytearray(frame.pixels)
    )
    if frame.height > 1 and frame.pixel_format.endswith("bottom_up"):
        # Native copies release the GIL while the GL owner continues presenting.
        # Only half a frame is temporary; odd-height middle rows stay in place.
        rows = np.frombuffer(normalized, dtype=np.uint8).reshape(frame.height, -1)
        half = frame.height // 2
        top = rows[:half]
        bottom = rows[-half:][::-1]
        saved = top.copy()
        np.copyto(top, bottom)
        np.copyto(bottom, saved)
    if frame.pixel_format.startswith("r10g10b10a2_le_"):
        x_bytes = np.frombuffer(normalized, dtype=np.uint8)[3::4]
        np.bitwise_and(x_bytes, 0x3F, out=x_bytes)
    return CompositeFrame(
        group_id=frame.group_id,
        video_frame_index=frame.video_frame_index,
        width=frame.width,
        height=frame.height,
        pixel_format=frame.pixel_format,
        pixels=normalized,
        source_host_ns=frame.source_host_ns,
    )
