"""V09/V10 timestamp selection and generation identity, independent of decoder workers."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .video_decoder import VideoPlaybackError
from .video_index import SourceFrame, VideoIndex


@dataclass(frozen=True, slots=True)
class PlaybackSelection:
    source_frame: SourceFrame
    playback_generation: int
    loop_index: int
    target: Fraction
    disposition: str


class PlaybackCursor:
    """Pure V09/V10 timestamp selection for one continuously retained instance."""

    def __init__(self, index: VideoIndex, end_behavior: str):
        if end_behavior not in ("loop", "hold_final_frame"):
            raise ValueError("unsupported video end behavior")
        if not index.frames or index.duration <= 0:
            raise ValueError("video index must have a positive timeline")
        self.index = index
        self.end_behavior = end_behavior
        self._generation = 0
        self._last_loop = 0
        self._held = False

    def reset(self) -> None:
        self._generation += 1
        self._last_loop = 0
        self._held = False

    def set_end_behavior(self, end_behavior: str) -> None:
        if end_behavior not in ("loop", "hold_final_frame"):
            raise ValueError("unsupported video end behavior")
        if end_behavior == self.end_behavior:
            return
        self.end_behavior = end_behavior
        # A setting change preserves playback time/generation. Leaving a completed
        # hold for looping makes the current authored playback clock eligible again.
        self._held = False

    def select(self, playback_seconds: float | Fraction) -> PlaybackSelection:
        requested = (
            playback_seconds
            if isinstance(playback_seconds, Fraction)
            else Fraction.from_float(playback_seconds)
        )
        target = requested
        if target < 0:
            target = Fraction(0)
        duration = self.index.duration
        disposition = "selected"
        if self.end_behavior == "loop":
            loop_index, target = divmod(target, duration)
            if loop_index < self._last_loop:
                raise VideoPlaybackError(
                    "playback clock moved behind its retained loop"
                )
            if loop_index > self._last_loop:
                self._generation += loop_index - self._last_loop
                self._last_loop = loop_index
        elif target >= duration or self._held:
            target = duration
            self._held = True
            disposition = "end_hold"
        frame = self.index.frames[-1]
        for candidate in self.index.frames:
            if candidate.start <= target < candidate.end:
                frame = candidate
                break
        return PlaybackSelection(
            source_frame=frame,
            playback_generation=self._generation,
            loop_index=self._last_loop,
            target=target,
            disposition=disposition,
        )


@dataclass(frozen=True, slots=True)
class VideoTarget:
    prepared_generation: str
    playback_generation: int
    request_id: int
    selection: PlaybackSelection

    def matches_content(self, other: VideoTarget) -> bool:
        """Match decode content within one prepared instance, ignoring request churn."""
        return (
            self.selection.source_frame.index == other.selection.source_frame.index
            and self.playback_generation == other.playback_generation
            and self.selection.loop_index == other.selection.loop_index
        )
