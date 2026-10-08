"""V11 local declarations only; no service or executable decoder implementation.

See decoder-ownership.md. Byte/frame/thread limits and complete media preparation
schemas are declared in artifact_models.py and runtime-bindings.md. Color transforms follow color-pipeline.md.
"""
from dataclasses import dataclass
from typing import Literal, Protocol

@dataclass(frozen=True)
class Rational:
    numerator: int
    denominator: int  # Positive; timestamps use the prepared source time base.

@dataclass(frozen=True)
class DecodeTarget:
    prepared_generation: str
    instance_id: str
    playback_generation: int
    request_id: int
    media_position: Rational  # Seconds; no rounded nominal-FPS frame index.

@dataclass(frozen=True)
class PixelPlane:
    data: memoryview  # Read-only leased storage; retain its native allocation owner.
    row_stride_bytes: int
    rows: int
    valid_row_bytes: int

@dataclass(frozen=True)
class DecodedImage:
    prepared_generation: str
    instance_id: str
    playback_generation: int
    request_id: int
    asset_id: str
    stream_index: int
    source_pts: int
    source_time_base: Rational
    interval_start: Rational  # Source-relative seconds, inclusive.
    interval_end: Rational  # Source-relative seconds, exclusive; > start.
    width: int
    height: int
    pixel_format: str  # Registry mapping with channel/depth/byte-order semantics.
    component_depth_bits: tuple[int, ...]
    color_interpretation_id: str  # Prepared, explicit interpretation; not a guess.
    planes: tuple[PixelPlane, ...]

class FrameLease(Protocol):
    @property
    def image(self) -> DecodedImage: ...
    def release(self) -> None:
        """Release once finished using pixels; repeated release is harmless."""
        ...

@dataclass(frozen=True)
class DecoderFailure:
    prepared_generation: str
    instance_id: str
    code: str
    detail: str

@dataclass(frozen=True)
class DecoderStatus:
    state: Literal['no_demand', 'capacity_wait', 'decoding', 'data_ready', 'endpoint', 'cancelled', 'failed']
    latest_request_id: int | None
    failure: DecoderFailure | None  # Retained on failure; empty queue is not EOF.

class DecoderSession(Protocol):
    def publish_target(self, target: DecodeTarget) -> None:
        """Nonblocking bounded mailbox; stale target raises, never replaces newer work."""
        ...
    def poll_frame(self) -> FrameLease | None:
        """Nonblocking next prepared frame in source order for current generation."""
        ...
    def status(self) -> DecoderStatus: ...
    def request_cancel(self) -> None:
        """Idempotently fence new work and wake owner; not proof of closure."""
        ...
