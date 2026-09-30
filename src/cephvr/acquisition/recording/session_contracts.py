"""Focused contracts and immutable records for acquisition recording."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from cephvr.acquisition.buffers.end_marker import CaptureEndMarker
from cephvr.acquisition.buffers.records import FrameRecord
from cephvr.acquisition.recording.negotiation import VideoNegotiationExpectation
from cephvr.acquisition.v1 import messages_pb2 as acq


class RecordingFailure(RuntimeError):
    """Required recording evidence or storage work failed."""


class QueueEntry(Protocol):
    @property
    def record(self) -> FrameRecord: ...

    @property
    def pixels(self) -> memoryview | None: ...

    @property
    def dropped(self) -> bool: ...


class RecordingQueue(Protocol):
    @property
    def pending_records(self) -> int: ...

    @property
    def waiting_pixels(self) -> int: ...

    @property
    def pending_records_capacity(self) -> int: ...

    @property
    def capacity_frames(self) -> int: ...

    def dequeue(self, timeout: float | None = None) -> QueueEntry | None: ...
    def complete(self, record: FrameRecord) -> memoryview | None: ...
    def close(self) -> None: ...


class PixelBufferPool(Protocol):
    def release(self, pixels: memoryview) -> None: ...


class EncoderProcess(Protocol):
    @property
    def cleanup_complete(self) -> bool: ...

    @property
    def created_output(self) -> bool: ...

    @property
    def output_creation_identity(self) -> object | None: ...

    @property
    def progress_frame(self) -> int | None: ...

    @property
    def diagnostic_tail(self) -> tuple[str, ...]: ...

    @property
    def stdout_text(self) -> str: ...

    @property
    def exit_code(self) -> int | None: ...

    @property
    def reader_error(self) -> BaseException | None: ...

    @property
    def negotiated(self) -> bool: ...

    def write(self, frame: memoryview | bytes, *, deadline_ns: int) -> None: ...
    def check_negotiation(self) -> None: ...
    def close_stdin(self, *, deadline_ns: int) -> None: ...
    def wait(self, *, deadline_ns: int) -> int: ...
    def terminate(self, *, deadline_ns: int) -> None: ...
    def output_identity(self) -> object | None: ...


class EncoderLauncher(Protocol):
    def bind_schedule(self, schedule: acq.WorkerSchedule) -> None: ...

    def launch(
        self,
        argv: Sequence[str],
        *,
        deadline_ns: int,
        negotiation: VideoNegotiationExpectation | None = None,
    ) -> EncoderProcess: ...

    def terminate_unconfirmed(self, *, deadline_ns: int) -> None: ...


class VideoSync(Protocol):
    @property
    def file_identity(self) -> object: ...

    def sync(self) -> None: ...
    def close(self) -> None: ...


class VideoSyncFactory(Protocol):
    def identity(self, path: Path) -> object | None: ...

    def open(self, path: Path, expected_identity: object) -> VideoSync: ...

    def delete_exact(
        self, path: Path, expected_identity: object, *, deadline_ns: int
    ) -> bool: ...


class EndMarkerSource(Protocol):
    def poll(self) -> CaptureEndMarker | None: ...

    @property
    def completion_deadline_ns(self) -> int | None: ...

    def abort_request(self) -> tuple[str, int] | None: ...


WarningOccurrence = Callable[[str, str | None, str | None, int, int | None], None]


@dataclass(frozen=True)
class RecordingCompletionContext:
    outcome: str
    stopped_recording_end_monotonic_ns: int | None
    stopped_actual_stop_monotonic_ns: int | None
    transport_summary: dict[str, int | None] | None


@dataclass(frozen=True)
class PulseEvidence:
    on_outcome: str | None = None
    on_dispatched_monotonic_ns: int | None = None
    on_acknowledged_monotonic_ns: int | None = None
    off_outcome: str | None = None
    off_dispatched_monotonic_ns: int | None = None
    off_acknowledged_monotonic_ns: int | None = None
    required: bool = False

    def complete(self) -> bool:
        if not self.required:
            return True
        return (
            self.on_outcome == "PULSE_COMMAND_OUTCOME_APPLIED"
            and self.off_outcome == "PULSE_COMMAND_OUTCOME_APPLIED"
            and self.on_dispatched_monotonic_ns is not None
            and self.on_acknowledged_monotonic_ns is not None
            and self.off_dispatched_monotonic_ns is not None
            and self.off_acknowledged_monotonic_ns is not None
        )
