"""Thread-safe producer terminal evidence supplied to the recording owner."""

from __future__ import annotations

from threading import Condition

from cephvr.acquisition.buffers.end_marker import CaptureEndMarker
from cephvr.acquisition.recording.session_contracts import (
    EndMarkerSource,
    PulseEvidence,
    RecordingCompletionContext,
    RecordingFailure,
)


class RecordingCompletionHandoff(EndMarkerSource):
    """Publish one immutable end/pulse/completion snapshot after producer drain."""

    def __init__(self) -> None:
        self._condition = Condition()
        self._marker: CaptureEndMarker | None = None
        self._pulses: PulseEvidence | None = None
        self._completion: RecordingCompletionContext | None = None
        self._deadline_ns: int | None = None
        self._cancel_deadline_ns: int | None = None
        self._cleanup_deadline_ns: int | None = None
        self._normal_deadline_ns: int | None = None

    def set_normal_deadline(self, deadline_ns: int) -> None:
        if deadline_ns <= 0:
            raise ValueError("normal recording deadline must be positive")
        with self._condition:
            if self._normal_deadline_ns not in (None, deadline_ns):
                raise RecordingFailure("normal recording deadline changed")
            self._normal_deadline_ns = deadline_ns

    def publish(
        self,
        marker: CaptureEndMarker,
        pulses: PulseEvidence,
        completion: RecordingCompletionContext,
        *,
        deadline_ns: int,
    ) -> None:
        with self._condition:
            normal_deadline = self._normal_deadline_ns
            if normal_deadline is None:
                raise RecordingFailure("normal recording deadline was not retained")
            deadline_ns = min(deadline_ns, normal_deadline)
            snapshot = (marker, pulses, completion, deadline_ns)
            if self._marker is not None:
                if snapshot != (
                    self._marker,
                    self._pulses,
                    self._completion,
                    self._deadline_ns,
                ):
                    raise RecordingFailure("recording terminal evidence changed")
                return
            self._marker, self._pulses, self._completion, self._deadline_ns = snapshot
            self._condition.notify_all()

    def request_abort(self, kind: str, *, deadline_ns: int) -> None:
        """Wake the active writer for bounded pre-T cancel or failed cleanup."""
        if kind not in {"cancel_before_start", "failed_cleanup"} or deadline_ns <= 0:
            raise ValueError("invalid recording abort request")
        with self._condition:
            if kind == "cancel_before_start":
                self._cancel_deadline_ns = deadline_ns
            else:
                # Failed cleanup is an escalation/reconciliation request, separate
                # from the immutable cancellation outcome and deadline.
                self._cleanup_deadline_ns = deadline_ns
            self._condition.notify_all()

    def poll(self) -> CaptureEndMarker | None:
        with self._condition:
            return self._marker

    def abort_request(self) -> tuple[str, int] | None:
        with self._condition:
            if self._cleanup_deadline_ns is not None:
                return "failed_cleanup", self._cleanup_deadline_ns
            if self._cancel_deadline_ns is not None:
                return "cancel_before_start", self._cancel_deadline_ns
            return None

    @property
    def completion_deadline_ns(self) -> int | None:
        with self._condition:
            return self._deadline_ns

    def pulse_evidence(self) -> PulseEvidence:
        with self._condition:
            if self._pulses is None:
                raise RecordingFailure("pulse evidence was not published")
            return self._pulses

    def completion_context(self) -> RecordingCompletionContext:
        with self._condition:
            if self._completion is None:
                raise RecordingFailure("completion context was not published")
            return self._completion
