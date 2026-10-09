"""Truthful online outcome for empty, all-dropped, and submitted review videos."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .capture import RecordingCounts

VideoContent = Literal["UNKNOWN", "NO_FRAMES", "FRAMES_SUBMITTED"]
OutputClosure = Literal["CLOSED", "NOT_STARTED", "UNCONFIRMED"]


@dataclass(frozen=True)
class VideoCompletion:
    content: VideoContent
    artifact_present: bool | None
    closure: OutputClosure
    warning: str | None


def resolve_video_completion(
    counts: RecordingCounts,
    *,
    final_cutoff_known: bool,
    every_eligible_group_resolved: bool,
    no_partial_input_write: bool,
    encoder_cleanup_confirmed: bool,
    encoder_finalized: bool,
    file_sync_and_close_confirmed: bool,
    artifact_present: bool | None,
    artifact_created_by_session: bool | None,
    reserved_path_absent_after_cleanup: bool,
) -> VideoCompletion:
    """Classify only from complete online evidence, never from file contents.

    An absent NOT_STARTED output requires exact ownership proof that this trial never
    created it and a post-cleanup absent-path observation. A created-then-missing file
    and an empty-input encoder error remain unconfirmed/failures.
    """
    reconciled_counts = counts.eligible_group_count == (
        counts.admitted_count
        + counts.capacity_drop_count
        + counts.same_slot_omission_count
    )
    accounting_complete = (
        final_cutoff_known
        and every_eligible_group_resolved
        and reconciled_counts
        and counts.unresolved_capture_count == 0
        and counts.failed_capture_count == 0
    )
    if not accounting_complete or not no_partial_input_write:
        return VideoCompletion("UNKNOWN", artifact_present, "UNCONFIRMED", None)
    content: VideoContent = (
        "FRAMES_SUBMITTED" if counts.input_submitted_count > 0 else "NO_FRAMES"
    )
    if content == "FRAMES_SUBMITTED":
        closed = (
            artifact_present is True
            and artifact_created_by_session is True
            and encoder_finalized
            and file_sync_and_close_confirmed
            and encoder_cleanup_confirmed
        )
        return VideoCompletion(
            content, artifact_present, "CLOSED" if closed else "UNCONFIRMED", None
        )
    if artifact_present is True:
        closed = (
            artifact_created_by_session is True
            and encoder_finalized
            and file_sync_and_close_confirmed
            and encoder_cleanup_confirmed
        )
        return VideoCompletion(
            "NO_FRAMES",
            True,
            "CLOSED" if closed else "UNCONFIRMED",
            "Visual Stimulus review video contains no submitted frames"
            if closed
            else None,
        )
    never_created_absence = (
        artifact_present is False
        and artifact_created_by_session is False
        and reserved_path_absent_after_cleanup
        and encoder_cleanup_confirmed
        and encoder_finalized
    )
    if never_created_absence:
        return VideoCompletion(
            "NO_FRAMES",
            False,
            "NOT_STARTED",
            "Visual Stimulus review video contains no submitted frames",
        )
    return VideoCompletion("NO_FRAMES", artifact_present, "UNCONFIRMED", None)
