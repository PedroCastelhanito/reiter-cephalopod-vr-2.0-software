"""GL-owner capture admission and bounded readback handoff for one trial."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from cephvr.visual_stimulus.config.models.artifact_models import ReviewEncoding
from cephvr.visual_stimulus.config.models.evidence_model import (
    Clipping,
    FeedbackEvidence,
    Interval,
    RenderGroup,
)
from cephvr.visual_stimulus.rendering.types import (
    DiagnosticSnapshot,
    EvidenceStateSnapshot,
    FeedbackEvidenceSnapshot,
    RenderPort,
    RenderUpdate,
    SubmissionSnapshot,
)

from .capture import CaptureReservation
from .evidence_records import (
    CaptureDisposition,
    build_capture_update,
    build_clipping_record,
    build_feedback_interval,
    build_render_group_record,
)
from .session import RecordingSession


class RecordingCaptureRuntime:
    """Own mutable GL/capture state while the session owns disk and encoder I/O."""

    def __init__(
        self,
        renderer: RenderPort,
        session: RecordingSession,
        encoding: ReviewEncoding,
        *,
        evidence_pending_bytes: int,
        capture_slots: int,
    ) -> None:
        self.renderer = renderer
        self.session = session
        self.encoding = encoding
        self.evidence_pending_bytes = evidence_pending_bytes
        self.capture_slots = capture_slots
        self.pending: dict[int, tuple[CaptureReservation, object]] = {}
        self.reservation: CaptureReservation | None = None
        self.next_group_id = 0
        self.last_group_id: int | None = None
        self.state_count = 0
        self.submission_count = 0
        self._cancelled_tokens: set[int] = set()
        self._feedback_intervals: dict[
            tuple[Literal["feedback_hold", "arena_constraint"], str, str],
            tuple[str, FeedbackEvidenceSnapshot, str],
        ] = {}
        self._interval_serial = 0

    def before_render(self) -> None:
        for token, (reservation, pending) in tuple(self.pending.items()):
            pixels = self.renderer.poll_review_capture(pending)
            if pixels is None:
                continue
            self.session.complete_capture(
                reservation,
                width=self.encoding.composite_width,
                height=self.encoding.composite_height,
                pixel_format=self.encoding.native_pixel_format,
                pixels=pixels,
            )
            del self.pending[token]
            self.enqueue_capture_update(
                reservation.group_id,
                "transfer_complete",
                reservation.video_frame_index,
                None,
            )
        self.reservation = self.session.try_reserve_capture(self.next_group_id)

    def rendered(self, update: RenderUpdate) -> None:
        group_id = update.group.group_id
        if group_id != self.next_group_id:
            raise ValueError("renderer and recorder group identities diverged")
        self.last_group_id = group_id
        self.state_count += 1
        self.submission_count += len(update.group.outputs)
        state = update.evidence_state
        submissions = update.evidence_submissions
        reservation, self.reservation = self.reservation, None
        captures: tuple[tuple[CaptureDisposition, int | None, str | None], ...]
        if reservation is None:
            captures = (("capacity_drop", None, None),)
        else:
            try:
                pending = self.renderer.capture_review_composite(
                    reservation, update.outputs, self.encoding
                )
            except BaseException:
                self.session.cancel_capture(reservation)
                captures = (
                    (
                        "transfer_failed",
                        reservation.video_frame_index,
                        "CAPTURE_FAILED",
                    ),
                )
                self.next_group_id += 1
                self.session.enqueue_evidence_factory(
                    _render_evidence_factory(
                        group_id, state, submissions, captures, self.encoding
                    ),
                    reserved_bytes=min(self.evidence_pending_bytes, 256 * 1024),
                )
                raise
            self.pending[reservation.token] = (reservation, pending)
            captures = (("admitted", reservation.video_frame_index, None),)
        self.next_group_id += 1
        self.session.enqueue_evidence_factory(
            _render_evidence_factory(
                group_id, state, submissions, captures, self.encoding
            ),
            reserved_bytes=min(self.evidence_pending_bytes, 256 * 1024),
        )

    def diagnostics(self, records: tuple[DiagnosticSnapshot, ...]) -> None:
        for snapshot in records:
            if self.last_group_id is None or snapshot.group_id > self.last_group_id:
                raise ValueError(
                    "clipping diagnostic references an unrecorded render group"
                )
            self.session.enqueue_evidence_factory(
                _clipping_factory(snapshot),
                reserved_bytes=min(self.evidence_pending_bytes, 256 * 1024),
            )

    def feedback(self, records: tuple[FeedbackEvidence, ...]) -> None:
        for record in records:
            if record.disposition == "applied" and (
                record.group_id is None
                or self.last_group_id is None
                or record.group_id > self.last_group_id
            ):
                raise ValueError(
                    "applied feedback references an unrecorded render group"
                )
            self.session.enqueue_evidence_factory(
                _feedback_factory(record),
                reserved_bytes=min(self.evidence_pending_bytes, 256 * 1024),
            )

    def feedback_snapshots(self, records: tuple[FeedbackEvidenceSnapshot, ...]) -> None:
        """Queue feedback lines after their render group, then update hold intervals."""
        for snapshot in records:
            if snapshot.disposition == "applied" and (
                snapshot.group_id is None
                or self.last_group_id is None
                or snapshot.group_id > self.last_group_id
            ):
                raise ValueError(
                    "applied feedback references an unrecorded render group"
                )
            self.session.enqueue_evidence_factory(
                _feedback_snapshot_factory(snapshot),
                reserved_bytes=min(self.evidence_pending_bytes, 256 * 1024),
            )
            if snapshot.binding_id is None:
                continue
            key: tuple[Literal["feedback_hold", "arena_constraint"], str, str] = (
                "feedback_hold",
                snapshot.stream_id,
                snapshot.binding_id,
            )
            hold = snapshot.disposition != "applied"
            self._transition_feedback_interval(
                key,
                hold,
                snapshot,
                f"feedback disposition {snapshot.disposition}",
            )
            if snapshot.constraint_occurred:
                interval_id = f"arena_constraint-{self._interval_serial}"
                self._interval_serial += 1
                self.session.enqueue_evidence_factory(
                    _interval_factory(
                        interval_id,
                        "begin",
                        "arena_constraint",
                        snapshot,
                        snapshot.application_check_ns,
                        "arena constraint applied",
                    ),
                    reserved_bytes=2048,
                )
                self.session.enqueue_evidence_factory(
                    _interval_factory(
                        interval_id,
                        "end",
                        "arena_constraint",
                        snapshot,
                        snapshot.application_check_ns,
                        "arena constraint applied",
                    ),
                    reserved_bytes=2048,
                )

    def close_feedback_intervals(self, cutoff_ns: int) -> None:
        """Close ongoing feedback intervals at the trial's retained cutoff."""
        for (category, _stream_id, _binding_id), (
            interval_id,
            snapshot,
            reason,
        ) in tuple(self._feedback_intervals.items()):
            observation_ns = max(cutoff_ns, snapshot.application_check_ns)
            self.session.enqueue_terminal_evidence_factory(
                _interval_factory(
                    interval_id, "end", category, snapshot, observation_ns, reason
                ),
                reserved_bytes=2048,
            )
        self._feedback_intervals.clear()

    def _transition_feedback_interval(
        self,
        key: tuple[Literal["feedback_hold", "arena_constraint"], str, str],
        active: bool,
        snapshot: FeedbackEvidenceSnapshot,
        reason: str,
    ) -> None:
        current = self._feedback_intervals.get(key)
        if active and current is None:
            interval_id = f"{key[0]}-{self._interval_serial}"
            self._interval_serial += 1
            self._feedback_intervals[key] = (interval_id, snapshot, reason)
            phase: Literal["begin", "end"] = "begin"
        elif not active and current is not None:
            interval_id, start_snapshot, start_reason = current
            self._feedback_intervals.pop(key)
            snapshot = _at_time(
                snapshot,
                max(snapshot.application_check_ns, start_snapshot.application_check_ns),
            )
            phase = "end"
            reason = start_reason
        else:
            return
        self.session.enqueue_evidence_factory(
            _interval_factory(
                interval_id,
                phase,
                key[0],
                snapshot,
                snapshot.application_check_ns,
                reason,
            ),
            reserved_bytes=2048,
        )

    def enqueue_capture_update(
        self,
        group_id: int,
        disposition: CaptureDisposition,
        frame_index: int | None,
        failure: str | None,
        *,
        terminal: bool = False,
    ) -> None:
        enqueue = (
            self.session.enqueue_terminal_evidence_factory
            if terminal
            else self.session.enqueue_evidence_factory
        )
        enqueue(
            lambda: build_capture_update(
                group_id,
                disposition,
                frame_index,
                failure,
                self.encoding.native_pixel_format,
                self.encoding.encoder_pixel_format,
            ),
            reserved_bytes=2048,
        )

    def cancel_pending(self, failure: str) -> bool:
        released = True
        for token, (reservation, pending) in tuple(self.pending.items()):
            if token not in self._cancelled_tokens:
                self.enqueue_capture_update(
                    reservation.group_id,
                    "transfer_failed",
                    reservation.video_frame_index,
                    failure,
                )
                self.session.cancel_capture(reservation)
                self._cancelled_tokens.add(token)
            if self.renderer.cancel_review_capture(pending):
                del self.pending[token]
            else:
                released = False
        if self.reservation is not None:
            self.session.cancel_capture(self.reservation)
            self.reservation = None
        return released


def _render_evidence_factory(
    group_id: int,
    state: EvidenceStateSnapshot,
    submissions: tuple[SubmissionSnapshot, ...],
    captures: tuple[tuple[CaptureDisposition, int | None, str | None], ...],
    encoding: ReviewEncoding,
) -> Callable[[], RenderGroup]:
    def build() -> RenderGroup:
        return build_render_group_record(
            group_id,
            state,
            submissions,
            captures,
            encoding.native_pixel_format,
            encoding.encoder_pixel_format,
        )

    return build


def _clipping_factory(snapshot: DiagnosticSnapshot) -> Callable[[], Clipping]:
    def build() -> Clipping:
        return build_clipping_record(snapshot)

    return build


def _feedback_factory(record: FeedbackEvidence) -> Callable[[], FeedbackEvidence]:
    def build() -> FeedbackEvidence:
        return record

    return build


def _feedback_snapshot_factory(
    snapshot: FeedbackEvidenceSnapshot,
) -> Callable[[], FeedbackEvidence]:
    def build() -> FeedbackEvidence:
        from .evidence_records import build_feedback_record

        return build_feedback_record(snapshot)

    return build


def _interval_factory(
    interval_id: str,
    phase: Literal["begin", "end"],
    category: Literal["feedback_hold", "arena_constraint"],
    snapshot: FeedbackEvidenceSnapshot,
    observation_host_ns: int,
    reason: str,
) -> Callable[[], Interval]:
    def build() -> Interval:
        return build_feedback_interval(
            interval_id, phase, category, snapshot, observation_host_ns, reason
        )

    return build


def _at_time(
    snapshot: FeedbackEvidenceSnapshot, application_check_ns: int
) -> FeedbackEvidenceSnapshot:
    """Return a minimal immutable copy whose check timestamp closes the interval."""
    from dataclasses import replace

    return replace(snapshot, application_check_ns=application_check_ns)
