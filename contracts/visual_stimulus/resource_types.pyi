"""Local resource/encoding adapter boundaries; implementations remain runtime work."""
from dataclasses import dataclass
from typing import BinaryIO, Protocol
from artifact_models import Interpretation, ResourceManifest, ReviewTiming
from decoder_types import Rational, DecoderSession
@dataclass(frozen=True)
class SourceFrame:
    index: int
    pts: int
    time_base: Rational
    start: Rational
    end: Rational
    seek_anchor: int
@dataclass(frozen=True)
class PreparedMedia:
    resource_id: str
    interpretation: Interpretation
    frames: tuple[SourceFrame, ...]
    duration: Rational | None # None for static images.
class ProtectedSource(Protocol):
    def independent_reader(self) -> BinaryIO: ...
    def close_after_consumers(self) -> None: ...
class MediaProvider(Protocol):
    def prepare(self, source: ProtectedSource, profile_id: str) -> PreparedMedia: ...
    def open_decoder(self, source: ProtectedSource, media: PreparedMedia,
                     instance_id: str, generation: str) -> DecoderSession: ...
class ReviewEncoderInput(Protocol):  # V12 recording thread -> FFmpeg stdin, raw frames.
    def prepare(self, *, native_pixel_format: str,  # One E13 tiled composite.
                width: int, height: int, timing: ReviewTiming) -> None: ...
    def submit(self, *, group_id: int, video_frame_index: int,
               pixels: memoryview) -> None: ...  # Frame n = n-th admitted group.
    def finish(self) -> None: ...
