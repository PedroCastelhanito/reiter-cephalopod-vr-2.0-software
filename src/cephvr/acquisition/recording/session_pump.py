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
) -> bool:
    """Write one payload if usable, then append its sole ordered frame row."""
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
    submitted = False
    dropped = bool(entry.dropped or not record.valid_image)
    if not dropped:
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
        frame_deadline_ns = write_deadline()
        encoder.write(prepared.data, deadline_ns=frame_deadline_ns)
        # FFmpeg may need several packets before stream analysis completes.
        # Check live diagnostics without blocking, then feed the next bounded frame.
        encoder.check_negotiation()
        submitted = True
    frame_log.append_frame(record, dropped=dropped)
    return submitted
