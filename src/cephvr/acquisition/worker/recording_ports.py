"""Narrow recording operations consumed by serialized camera lifecycle code."""

from __future__ import annotations

from concurrent.futures import Future
from typing import Protocol

from cephvr.acquisition.buffers.end_marker import CaptureEndMarker
from cephvr.acquisition.recording.session_contracts import (
    PulseEvidence,
    RecordingCompletionContext,
)
from cephvr.control.v1 import types_pb2 as control

from .recording_fault import RecordingFaultPort


class TrialRecordingPort(RecordingFaultPort, Protocol):
    """Recording operations the camera trial lifecycle is allowed to call."""

    @property
    def enabled(self) -> bool: ...

    @property
    def completion_deadline_ns(self) -> int | None: ...

    @property
    def recording_queue(self) -> object | None: ...

    def cancel_before_start(
        self, *, deadline_ns: int
    ) -> Future[list[control.OutputResult]]: ...

    def completed_results(self) -> list[control.OutputResult]: ...

    def finish(
        self,
        marker: CaptureEndMarker,
        pulses: PulseEvidence,
        completion: RecordingCompletionContext,
        *,
        deadline_ns: int,
    ) -> Future[list[control.OutputResult]]: ...

    def recycle_finished(self, deadline_ns: int) -> None: ...
