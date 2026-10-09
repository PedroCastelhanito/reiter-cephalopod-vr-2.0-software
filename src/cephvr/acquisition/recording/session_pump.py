"""Prepare and append one ordered camera frame on the recording owner thread."""

from __future__ import annotations

from collections.abc import Callable

from cephvr.acquisition.buffers.records import FrameRecord
from cephvr.acquisition.recording.frame_log import FrameLogWriter
from cephvr.acquisition.recording.session_contracts import (
    EncoderProcess,
    QueueEntry,
    RecordingFailure,
)
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.shared.pixels.preparer import PixelPreparer


class SubmittedFrameLogFailure(RecordingFailure):
    """Encoder input was accepted but its required slot mapping was not logged."""


def write_ordered_entry(
    entry: QueueEntry,
    *,
    expected_frame_id: int,
    schedule: acq.WorkerSchedule,
    frame_log: FrameLogWriter,
    encoder: EncoderProcess,
    pixel_preparer: PixelPreparer,
    prepared_buffer: bytearray,
    target_bits: int,
    on_started: Callable[[], None],
    write_deadline: Callable[[], int],
    record_diagnostic: Callable[[FrameRecord], None],
    on_video_slot_submitted: Callable[[], None] | None = None,
) -> int:
    """Append one source row and stream its real/duplicate nominal video slots."""
    record = entry.record
    if record.frame_id != expected_frame_id:
        raise RecordingFailure("recording queue delivered duplicate or unordered ID")
    if (
        not schedule.start_monotonic_ns
        <= record.acquisition_time_ns
        < schedule.end_monotonic_ns
    ):
        raise RecordingFailure("record receipt is outside scheduled half-open interval")
    on_started()
    record_diagnostic(record)
    dropped = bool(entry.dropped or not record.valid_image)
    slot: int | None = None
    disposition: str | None = None
    if not dropped:
        slot = frame_log.video_grid.slot_for(record.acquisition_time_ns)
        if slot < frame_log.next_video_slot:
            dropped = True
            disposition = "same_slot_omission"
    if dropped:
        source_disposition = disposition or (
            "invalid_image" if not record.valid_image else "capacity_drop"
        )
        frame_log.append_frame(
            record,
            dropped=True,
            video_disposition=source_disposition,
        )
        return 0

    assert slot is not None
    submitted = 0
    if slot > frame_log.next_video_slot and frame_log.last_video_source is not None:
        source_id, source_ns = frame_log.last_video_source
        for missing_slot in range(frame_log.next_video_slot, slot):
            submitted += _write_slot(
                prepared_buffer,
                missing_slot,
                source_id,
                source_ns,
                "interior_duplicate",
                frame_log=frame_log,
                encoder=encoder,
                write_deadline=write_deadline,
                on_submitted=on_video_slot_submitted,
            )
    if entry.pixels is None:
        raise RecordingFailure("valid retained frame has no private pixels")
    prepared = pixel_preparer.prepare_recording_into(
        entry.pixels, prepared_buffer, target_bits=target_bits
    )
    if (
        len(prepared.data) != len(prepared_buffer)
        or prepared.effective_bits != target_bits
        or prepared.source_effective_bits
        != pixel_preparer.layout.pixel_format.effective_bits
    ):
        raise RecordingFailure("prepared raw frame has unexpected byte layout")
    frame_log.append_frame(
        record,
        dropped=False,
        video_frame=slot,
        video_disposition="real",
    )
    if frame_log.last_video_source is None:
        for leading_slot in range(frame_log.next_video_slot, slot):
            submitted += _write_slot(
                prepared_buffer,
                leading_slot,
                record.frame_id,
                record.acquisition_time_ns,
                "leading_duplicate",
                frame_log=frame_log,
                encoder=encoder,
                write_deadline=write_deadline,
                on_submitted=on_video_slot_submitted,
            )
    submitted += _write_slot(
        prepared.data,
        slot,
        record.frame_id,
        record.acquisition_time_ns,
        "real",
        frame_log=frame_log,
        encoder=encoder,
        write_deadline=write_deadline,
        on_submitted=on_video_slot_submitted,
    )
    return submitted


def write_trailing_slots(
    final_slots: int,
    *,
    frame_log: FrameLogWriter,
    encoder: EncoderProcess,
    prepared_buffer: bytearray,
    write_deadline: Callable[[], int],
    on_slot_submitted: Callable[[], None],
) -> None:
    """Fill only the proven remainder of an admitted recording cadence."""
    source = frame_log.last_video_source
    if source is None:
        return
    source_id, source_ns = source
    while frame_log.next_video_slot < final_slots:
        slot = frame_log.next_video_slot
        _write_slot(
            prepared_buffer,
            slot,
            source_id,
            source_ns,
            "trailing_duplicate",
            frame_log=frame_log,
            encoder=encoder,
            write_deadline=write_deadline,
            on_submitted=on_slot_submitted,
        )


def _write_slot(
    data: bytes | bytearray | memoryview,
    slot: int,
    source_frame_id: int,
    source_ns: int,
    disposition: str,
    *,
    frame_log: FrameLogWriter,
    encoder: EncoderProcess,
    write_deadline: Callable[[], int],
    on_submitted: Callable[[], None] | None = None,
) -> int:
    """Submit one bounded frame, then record the input mapping it represents."""
    encoder_data = data if isinstance(data, (bytes, memoryview)) else memoryview(data)
    encoder.write(encoder_data, deadline_ns=write_deadline())
    try:
        frame_log.append_video_frame(
            slot=slot,
            source_frame_id=source_frame_id,
            source_host_receipt_ns=source_ns,
            disposition=disposition,
        )
    except BaseException as exc:
        raise SubmittedFrameLogFailure(
            "encoder accepted a frame whose required slot mapping was not logged"
        ) from exc
    if on_submitted is not None:
        on_submitted()
    encoder.check_negotiation()
    return 1
