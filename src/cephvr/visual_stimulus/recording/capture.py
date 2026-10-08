"""Bounded immutable composite-frame handoff for the V12 recording owner."""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, cast

from .evidence import EncoderInput, EvidenceWriter


@dataclass(frozen=True)
class CompositeFrame:
    group_id: int
    video_frame_index: int
    width: int
    height: int
    pixel_format: Literal["rgba8_bottom_up", "r10g10b10a2_le_bottom_up"]
    pixels: bytes

    def __post_init__(self) -> None:
        if (
            self.group_id < 0
            or self.video_frame_index < 0
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
    video_frame_index: int


@dataclass(frozen=True)
class RecordingCounts:
    eligible_group_count: int
    admitted_count: int
    input_submitted_count: int
    capacity_drop_count: int
    failed_capture_count: int
    unresolved_capture_count: int
    final_input_group_id: int | None


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
    ) -> None:
        if min(capture_slots, max_encoder_write_chunk) <= 0:
            raise ValueError("recording capacities must be positive")
        self.capture_slots = capture_slots
        self.evidence = evidence
        self.encoder = encoder
        self.max_encoder_write_chunk = max_encoder_write_chunk
        self.on_submitted = on_submitted
        self._frames: deque[tuple[CompositeFrame, int, bool]] = deque()
        self._lock = threading.Lock()
        self._reservations: dict[int, CaptureReservation] = {}
        self._next_token = 0
        self._admitted = 0
        self._eligible = 0
        self._submitted = 0
        self._dropped = 0
        self._failed_capture = 0
        self._last_group: int | None = None

    def offer(self, frame: CompositeFrame) -> CaptureAdmission:
        reservation = self.try_reserve(frame.group_id)
        if reservation is None:
            return CaptureAdmission(False, None, "capacity_drop")
        if frame.video_frame_index != reservation.video_frame_index:
            self.cancel_reservation(reservation)
            raise ValueError("video frame indices must count admitted groups only")
        self.complete_capture(
            reservation,
            width=frame.width,
            height=frame.height,
            pixel_format=frame.pixel_format,
            pixels=frame.pixels,
        )
        return CaptureAdmission(True, reservation.video_frame_index, "admitted")

    def try_reserve(self, group_id: int) -> CaptureReservation | None:
        """Reserve one bounded PBO/readback slot without waiting on the GL thread."""
        if group_id < 0:
            raise ValueError("group_id must be nonnegative")
        with self._lock:
            self._eligible += 1
            if len(self._frames) + len(self._reservations) >= self.capture_slots:
                self._dropped += 1
                return None
            reservation = CaptureReservation(self._next_token, group_id, self._admitted)
            self._next_token += 1
            self._reservations[reservation.token] = reservation
            self._admitted += 1
            return reservation

    def complete_capture(
        self,
        reservation: CaptureReservation,
        *,
        width: int,
        height: int,
        pixel_format: str,
        pixels: bytes | bytearray | memoryview,
    ) -> None:
        """Transfer a signaled PBO's bytes to the recording thread's owned slot."""
        if pixel_format not in {"rgba8_bottom_up", "r10g10b10a2_le_bottom_up"}:
            raise ValueError("unsupported review-composite pixel format")
        owned = CompositeFrame(
            group_id=reservation.group_id,
            video_frame_index=reservation.video_frame_index,
            width=width,
            height=height,
            pixel_format=cast(
                Literal["rgba8_bottom_up", "r10g10b10a2_le_bottom_up"], pixel_format
            ),
            pixels=bytes(
                pixels
            ),  # Own the readback before the GL adapter reuses a slot.
        )
        with self._lock:
            current = self._reservations.pop(reservation.token, None)
            if current != reservation:
                raise RuntimeError("capture reservation is stale or already completed")
            self._frames.append((owned, 0, False))

    def cancel_reservation(self, reservation: CaptureReservation) -> None:
        with self._lock:
            current = self._reservations.pop(reservation.token, None)
            if current != reservation:
                raise RuntimeError("capture reservation is stale or already completed")
            self._failed_capture += 1

    def drain_once(self) -> bool:
        """Service evidence first, then one bounded write chunk; return if progressed."""
        if self.evidence.pending_bytes:
            self.evidence.write_pending()
            return True
        with self._lock:
            if not self._frames:
                return False
            frame, offset, normalized = self._frames[0]
            if not normalized:
                frame = _ffmpeg_input_order(frame)
                self._frames[0] = (frame, offset, True)
            end = min(len(frame.pixels), offset + self.max_encoder_write_chunk)
            chunk = memoryview(frame.pixels)[offset:end]
        consumed = self.encoder.write_chunk(chunk)
        if consumed < 0 or consumed > len(chunk):
            raise RuntimeError("encoder input returned an invalid write count")
        if consumed == 0:
            return False
        with self._lock:
            current, current_offset, _normalized = self._frames[0]
            if current is not frame or current_offset != offset:
                raise RuntimeError("recording frame ownership changed during write")
            new_offset = offset + consumed
            if new_offset == len(frame.pixels):
                self._frames.popleft()
                self._submitted += 1
                self._last_group = frame.group_id
            else:
                self._frames[0] = (frame, new_offset, True)
        if new_offset == len(frame.pixels) and self.on_submitted is not None:
            self.on_submitted(frame)
        return True

    def counts(self) -> RecordingCounts:
        with self._lock:
            return RecordingCounts(
                eligible_group_count=self._eligible,
                admitted_count=self._admitted,
                input_submitted_count=self._submitted,
                capacity_drop_count=self._dropped,
                failed_capture_count=self._failed_capture,
                unresolved_capture_count=len(self._reservations) + len(self._frames),
                final_input_group_id=self._last_group,
            )

    def finish_input(self) -> RecordingCounts:
        with self._lock:
            if self._frames:
                raise RuntimeError(
                    "cannot close FFmpeg input while admitted captures remain"
                )
        self.encoder.close_input()
        return self.counts()


def _ffmpeg_input_order(frame: CompositeFrame) -> CompositeFrame:
    """Flip bottom-up capture rows and normalize the packed 10-bit X bits."""
    row_bytes = frame.width * 4
    source = frame.pixels
    normalized = bytearray(len(source))
    for row in range(frame.height):
        source_start = row * row_bytes
        target_start = (frame.height - row - 1) * row_bytes
        normalized[target_start : target_start + row_bytes] = source[
            source_start : source_start + row_bytes
        ]
    if frame.pixel_format == "r10g10b10a2_le_bottom_up":
        for index in range(3, len(normalized), 4):
            normalized[index] &= 0x3F
    return CompositeFrame(
        group_id=frame.group_id,
        video_frame_index=frame.video_frame_index,
        width=frame.width,
        height=frame.height,
        pixel_format=frame.pixel_format,
        pixels=bytes(normalized),
    )
