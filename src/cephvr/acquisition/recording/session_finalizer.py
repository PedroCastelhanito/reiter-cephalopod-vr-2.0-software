"""Retryable exact-child and durable-output closure stages (A07/E11)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from cephvr.acquisition.recording.frame_log import FrameLogCompletion, FrameLogWriter
from cephvr.acquisition.recording.session_contracts import EncoderProcess, VideoSync


@dataclass
class FinalizationProgress:
    stdin_closed: bool = False
    exit_code: int | None = None
    video_synced: bool = False
    completion_appended: bool = False
    completion_failed: bool = False
    frame_log_closed: bool = False
    video_closed: bool = False
    late: bool = False


def close_encoder_and_sync_video(
    progress: FinalizationProgress,
    encoder: EncoderProcess,
    video_sync: VideoSync | None,
    *,
    deadline_ns: int,
    clock_ns: Callable[[], int],
    observe_video: Callable[[], VideoSync | None],
) -> tuple[int, VideoSync | None]:
    """Close exact child stdin, observe exit and sync its exact video identity."""
    if not progress.stdin_closed:
        encoder.close_stdin(deadline_ns=deadline_ns)
        progress.stdin_closed = True
        progress.late |= clock_ns() > deadline_ns
    if progress.exit_code is None:
        try:
            progress.exit_code = encoder.wait(deadline_ns=deadline_ns)
        except BaseException:
            # Reader failure is still a recording failure, but after exact child
            # and pipe cleanup it must not block independent output closure.
            if not encoder.cleanup_complete or encoder.exit_code is None:
                raise
            progress.exit_code = encoder.exit_code
        progress.late |= clock_ns() > deadline_ns
    # Observation may open the exact file handle after FFmpeg creates its
    # output.  Always sync that returned handle, not a stale pre-observation
    # argument captured by the caller.
    video_sync = observe_video()
    if video_sync is not None and not progress.video_synced:
        video_sync.sync()
        progress.video_synced = True
        progress.late |= clock_ns() > deadline_ns
    return progress.exit_code, video_sync


def append_terminal_and_close(
    progress: FinalizationProgress,
    frame_log: FrameLogWriter,
    video_sync: VideoSync | None,
    completion: FrameLogCompletion,
    *,
    deadline_ns: int,
    clock_ns: Callable[[], int],
) -> None:
    """Append one terminal row and retain all durable close stages for retries."""
    if not progress.completion_appended and not progress.completion_failed:
        try:
            frame_log.append_completion(completion)
        except BaseException:
            # append_completion is deliberately fenced after its first attempt.
            # A partial terminal write can never be retried as a second row;
            # still release/synchronize the owned file on the failure path.
            progress.completion_failed = True
    if progress.completion_failed and not progress.frame_log_closed:
        frame_log.close_failed()
        progress.frame_log_closed = True
        progress.late |= clock_ns() > deadline_ns
    if not progress.completion_failed:
        progress.completion_appended = True
    if not progress.frame_log_closed:
        frame_log.close()
        progress.frame_log_closed = True
        progress.late |= clock_ns() > deadline_ns
    if video_sync is not None and not progress.video_closed:
        video_sync.close()
        progress.video_closed = True
        progress.late |= clock_ns() > deadline_ns
