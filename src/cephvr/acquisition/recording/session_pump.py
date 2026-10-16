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
    on_video_frame_submitted: Callable[[], None] | None = None,
) -> int:
    """Append one source row and submit its usable image exactly once."""
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
    if dropped:
        frame_log.append_frame(
            record,
            dropped=True,
            video_disposition="invalid_image"
            if not record.valid_image
            else "capacity_drop",
        )
        return 0

    encoded_frame_index = frame_log.frame_count
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
        video_frame=encoded_frame_index,
        video_disposition="real",
    )
    encoder.write(prepared.data, deadline_ns=write_deadline())
    # Accepted pipe input remains submitted even if its required mapping fails.
    if on_video_frame_submitted is not None:
        on_video_frame_submitted()
    try:
        frame_log.append_video_frame(
            encoded_frame_index=encoded_frame_index,
            source_frame_id=record.frame_id,
            source_host_receipt_ns=record.acquisition_time_ns,
        )
    except BaseException as exc:
        raise RecordingFailure(
            "encoder accepted a frame whose required source mapping was not logged"
        ) from exc
    encoder.check_negotiation()
    return 1
