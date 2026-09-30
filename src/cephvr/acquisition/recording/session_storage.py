"""Exact output observation and periodic sync decisions for RecordingSession."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cephvr.acquisition.recording.frame_log import FrameLogWriter
from cephvr.acquisition.recording.progress_watchdog import EncoderProgressWatchdog
from cephvr.acquisition.recording.session_contracts import (
    EncoderProcess,
    RecordingFailure,
    VideoSync,
    VideoSyncFactory,
)


@dataclass(frozen=True)
class VideoObservation:
    identity: object | None
    sync: VideoSync | None
    last_sync_ns: int


def observe_video_identity(
    encoder: EncoderProcess | None,
    path: Path | None,
    current_identity: object | None,
    current_sync: VideoSync | None,
    last_sync_ns: int,
    *,
    factory: VideoSyncFactory,
    clock_ns: Callable[[], int],
) -> VideoObservation:
    """Adopt video sync only after independent identity matches encoder proof."""
    if encoder is None or path is None:
        return VideoObservation(current_identity, current_sync, last_sync_ns)
    # Retain positive creation evidence only while this exact supervised child is
    # live, after launch established the reserved path absent and FFmpeg uses -n.
    _ = encoder.output_creation_identity
    identity = encoder.output_identity()
    if identity is None:
        return VideoObservation(current_identity, current_sync, last_sync_ns)
    path_identity = stat_identity(path, factory)
    if path_identity is None:
        raise RecordingFailure("encoder claims output creation but path is absent")
    if path_identity != identity:
        raise RecordingFailure("encoder output path identity differs from owned file")
    if current_identity is not None and identity != current_identity:
        raise RecordingFailure("encoder output file identity changed during recording")
    if current_sync is None:
        current_sync = factory.open(path, identity)
        last_sync_ns = clock_ns()
    elif current_sync.file_identity != identity:
        raise RecordingFailure("video sync handle refers to another file identity")
    return VideoObservation(identity, current_sync, last_sync_ns)


def sync_due(
    frame_log: FrameLogWriter | None,
    video_sync: VideoSync | None,
    last_video_sync_ns: int,
    video_sync_interval_ns: int,
    now_ns: int,
) -> int:
    """Append/sync ready frame rows and sync video on its own cadence."""
    if frame_log is not None:
        frame_log.sync_if_due(now_ns)
    if video_sync is not None and now_ns - last_video_sync_ns >= video_sync_interval_ns:
        video_sync.sync()
        return now_ns
    return last_video_sync_ns


def stat_identity(path: Path, factory: VideoSyncFactory) -> object | None:
    if path.is_symlink():
        raise RecordingFailure("recording output unexpectedly became a symlink")
    return factory.identity(path)


def write_deadline(
    watchdog: EncoderProgressWatchdog | None,
    active_deadline_ns: int | None,
    scheduled_end_ns: int,
) -> int:
    if watchdog is None:
        raise RecordingFailure("recording encoder progress watchdog is unavailable")
    finalization_deadline = active_deadline_ns or scheduled_end_ns
    return watchdog.write_deadline(finalization_deadline)
