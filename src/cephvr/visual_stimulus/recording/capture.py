"""Bounded immutable composite-frame handoff for the V12 recording owner."""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal, cast

from cephvr.shared.nominal_video_grid import NominalVideoGrid

from .evidence import EncoderInput, EvidenceWriter


@dataclass(frozen=True)
class CompositeFrame:
    group_id: int
    video_frame_index: int
    width: int
    height: int
    pixel_format: Literal["rgba8_bottom_up", "r10g10b10a2_le_bottom_up"]
    pixels: bytes | bytearray
    source_host_ns: int = 0
    encoded_disposition: str = "real"

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
        video_rate_hz: float | Fraction,
    ) -> None:
        if min(capture_slots, max_encoder_write_chunk) <= 0:
            raise ValueError("recording capacities must be positive")
        self.capture_slots = capture_slots
        self.evidence = evidence
        self.encoder = encoder
        self.max_encoder_write_chunk = max_encoder_write_chunk
        self.on_submitted = on_submitted
        self.video_grid = NominalVideoGrid(video_start_ns, video_rate_hz)
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
        self._last_selected_slot: int | None = None
        self._next_encoded_slot = 0
        self._active_frame: CompositeFrame | None = None
        self._active_offset = 0
        self._active_normalized = False
        self._pending_real: CompositeFrame | None = None
        self._pending_real_normalized = False
        self._repeat_remaining = 0
        self._repeat_disposition: str | None = None
        self._last_usable: CompositeFrame | None = None
        self._cutoff_slots: int | None = None
        self._duplicate_count = 0
        self._encoded_count = 0
        self._same_slot_omissions = 0
        self._selected_real = 0

    def offer(self, frame: CompositeFrame) -> CaptureAdmission:
        reservation, disposition, slot = self.classify_and_reserve(
            frame.group_id, frame.source_host_ns
        )
        if reservation is None:
            return CaptureAdmission(False, slot, disposition)
        if frame.video_frame_index != reservation.video_frame_index:
            self.cancel_reservation(reservation)
            raise ValueError("video frame index must equal its nominal slot")
        self.complete_capture(
            reservation,
            width=frame.width,
            height=frame.height,
            pixel_format=frame.pixel_format,
            pixels=frame.pixels,
        )
        return CaptureAdmission(True, reservation.video_frame_index, "admitted")

    def classify_and_reserve(
        self, group_id: int, source_host_ns: int
    ) -> tuple[CaptureReservation | None, str, int | None]:
        """Apply first-per-slot selection before bounded pixel capture admission."""
        if group_id < 0 or source_host_ns < 0:
            raise ValueError("source identity and evaluation time must be nonnegative")
        slot = self.video_grid.slot_for(source_host_ns)
        with self._lock:
            self._eligible += 1
            if self._last_selected_slot is not None and slot < self._last_selected_slot:
                raise ValueError("render evaluation times must be ordered")
            if slot == self._last_selected_slot:
                self._same_slot_omissions += 1
                return None, "same_slot_omission", slot
            if self._inflight_capture_count() >= self.capture_slots:
                self._dropped += 1
                return None, "capacity_drop", None
            reservation = CaptureReservation(
                self._next_token, group_id, slot, source_host_ns
            )
            self._next_token += 1
            self._reservations[reservation.token] = reservation
            self._admitted += 1
            self._last_selected_slot = slot
            return reservation, "admitted", slot

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
            pixels=bytearray(
                pixels
            ),  # Own the readback before the GL adapter reuses a slot.
            source_host_ns=reservation.source_host_ns,
        )
        with self._lock:
            current = self._reservations.pop(reservation.token, None)
            if current != reservation:
                raise RuntimeError("capture reservation is stale or already completed")
            self._selected_real += 1
            self._frames.append((owned, 0, False))
            self._frames = deque(
                sorted(self._frames, key=lambda item: item[0].video_frame_index)
            )

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
        return self._drain_cadence_once()

    def set_cutoff(self, cutoff_ns: int) -> None:
        slots = self.video_grid.slots_before(cutoff_ns)
        with self._lock:
            if self._cutoff_slots is not None and self._cutoff_slots != slots:
                raise RuntimeError(
                    "recording cutoff cannot change after admission seal"
                )
            self._cutoff_slots = slots

    def _inflight_capture_count(self) -> int:
        buffers = {id(frame.pixels) for frame, _offset, _normalized in self._frames}
        if self._pending_real is not None:
            buffers.add(id(self._pending_real.pixels))
        if self._active_frame is not None and self._active_frame.pixels is not getattr(
            self._last_usable, "pixels", None
        ):
            buffers.add(id(self._active_frame.pixels))
        return len(self._reservations) + len(buffers)

    def _drain_cadence_once(self) -> bool:
        with self._lock:
            if self._active_frame is None:
                if self._frames:
                    frame, _offset, normalized = self._frames[0]
                    earlier_reservation = any(
                        item.video_frame_index < frame.video_frame_index
                        for item in self._reservations.values()
                    )
                    if earlier_reservation:
                        return False
                    self._frames.popleft()
                    gap = frame.video_frame_index - self._next_encoded_slot
                    if gap < 0:
                        raise RuntimeError("capture completed behind encoded order")
                    if gap:
                        if self._last_usable is None:
                            duplicate = frame
                            disposition = "leading_duplicate"
                        else:
                            duplicate = self._last_usable
                            disposition = "interior_duplicate"
                        self._active_frame = _at_slot(
                            duplicate, self._next_encoded_slot, disposition
                        )
                        self._active_normalized = normalized or (
                            disposition == "interior_duplicate"
                        )
                        self._pending_real = frame
                        self._pending_real_normalized = normalized
                        self._repeat_remaining = gap
                        self._repeat_disposition = disposition
                    else:
                        self._active_frame = frame
                        self._active_normalized = normalized
                        self._pending_real = frame
                        self._pending_real_normalized = normalized
                        self._repeat_remaining = 0
                        self._repeat_disposition = None
                elif (
                    not self._reservations
                    and self._last_usable is not None
                    and self._cutoff_slots is not None
                    and self._next_encoded_slot < self._cutoff_slots
                ):
                    self._active_frame = _at_slot(
                        self._last_usable,
                        self._next_encoded_slot,
                        "trailing_duplicate",
                    )
                    self._active_normalized = True
                    self._pending_real = None
                    self._repeat_remaining = (
                        self._cutoff_slots - self._next_encoded_slot
                    )
                    self._repeat_disposition = "trailing_duplicate"
                else:
                    return False
            frame = self._active_frame
            if frame is None:
                return False
            if not self._active_normalized:
                frame = _ffmpeg_input_order(frame)
                self._active_frame = frame
                self._active_normalized = True
                if (
                    self._pending_real is not None
                    and self._pending_real.pixels is frame.pixels
                ):
                    self._pending_real_normalized = True
            offset = self._active_offset
            end = min(len(frame.pixels), offset + self.max_encoder_write_chunk)
            chunk = memoryview(frame.pixels)[offset:end]
        consumed = self.encoder.write_chunk(chunk)
        if consumed < 0 or consumed > len(chunk):
            raise RuntimeError("encoder input returned an invalid write count")
        if consumed == 0:
            return False
        submitted_frame: CompositeFrame | None = None
        completed_frame: CompositeFrame | None = None
        with self._lock:
            if self._active_frame is not frame or self._active_offset != offset:
                raise RuntimeError("recording frame ownership changed during write")
            self._active_offset += consumed
            if self._active_offset == len(frame.pixels):
                completed_frame = frame
                self._submitted += 1
                self._encoded_count += 1
                self._last_group = frame.group_id
                self._next_encoded_slot += 1
                if self._repeat_remaining:
                    self._duplicate_count += 1
                    self._repeat_remaining -= 1
                    if self._repeat_remaining:
                        assert self._repeat_disposition is not None
                        self._active_frame = _at_slot(
                            frame,
                            self._next_encoded_slot,
                            self._repeat_disposition,
                        )
                        self._active_offset = 0
                        self._active_normalized = True
                    elif self._pending_real is not None:
                        self._active_frame = self._pending_real
                        self._active_offset = 0
                        self._active_normalized = self._pending_real_normalized
                        self._pending_real = None
                        self._pending_real_normalized = False
                    else:
                        self._active_frame = None
                        self._active_offset = 0
                        self._active_normalized = False
                else:
                    self._last_usable = frame
                    self._active_frame = None
                    self._active_offset = 0
                    self._active_normalized = False
                    self._pending_real = None
                    self._pending_real_normalized = False
                    submitted_frame = frame
            elif not self._active_normalized:
                self._active_offset += 0
        if completed_frame is not None and self.on_submitted is not None:
            self.on_submitted(
                submitted_frame if submitted_frame is not None else completed_frame
            )
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
                encoded_frame_count=self._encoded_count,
                duplicate_frame_count=self._duplicate_count,
                same_slot_omission_count=self._same_slot_omissions,
                selected_real_count=self._selected_real,
            )

    def finish_input(self) -> RecordingCounts:
        with self._lock:
            if self._frames or self._reservations or self._active_frame is not None:
                raise RuntimeError(
                    "cannot close FFmpeg input while admitted captures remain"
                )
        self.encoder.close_input()
        return self.counts()


def _ffmpeg_input_order(frame: CompositeFrame) -> CompositeFrame:
    """Flip bottom-up capture rows and normalize the packed 10-bit X bits."""
    row_bytes = frame.width * 4
    normalized = (
        frame.pixels if isinstance(frame.pixels, bytearray) else bytearray(frame.pixels)
    )
    if frame.height > 1:
        view = memoryview(normalized)
        row_buffer = bytearray(row_bytes)
        for row in range(frame.height // 2):
            top = row * row_bytes
            bottom = (frame.height - row - 1) * row_bytes
            row_buffer[:] = view[top : top + row_bytes]
            view[top : top + row_bytes] = view[bottom : bottom + row_bytes]
            view[bottom : bottom + row_bytes] = row_buffer
    if frame.pixel_format == "r10g10b10a2_le_bottom_up":
        for index in range(3, len(normalized), 4):
            normalized[index] &= 0x3F
    return CompositeFrame(
        group_id=frame.group_id,
        video_frame_index=frame.video_frame_index,
        width=frame.width,
        height=frame.height,
        pixel_format=frame.pixel_format,
        pixels=normalized,
        source_host_ns=frame.source_host_ns,
        encoded_disposition=frame.encoded_disposition,
    )


def _at_slot(frame: CompositeFrame, slot: int, disposition: str) -> CompositeFrame:
    return CompositeFrame(
        group_id=frame.group_id,
        video_frame_index=slot,
        width=frame.width,
        height=frame.height,
        pixel_format=frame.pixel_format,
        pixels=frame.pixels,
        source_host_ns=frame.source_host_ns,
        encoded_disposition=disposition,
    )
