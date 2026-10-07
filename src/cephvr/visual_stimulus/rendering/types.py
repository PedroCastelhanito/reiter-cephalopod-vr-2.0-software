"""Small immutable boundary records shared by renderer, worker and recorder."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from cephvr.visual_stimulus.config.models.program_model import Settings
from cephvr.visual_stimulus.resources.media import ImagePixels

if TYPE_CHECKING:
    from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
    from cephvr.visual_stimulus.resources.display_calibration import (
        PreparedDisplayCalibration,
    )


@dataclass(frozen=True, slots=True)
class RenderedOutput:
    """Opaque final GPU output image; it is not read back during normal rendering."""

    output_id: str
    width: int
    height: int
    bits_per_channel: int
    texture_handle: object

    def __post_init__(self) -> None:
        if not self.output_id or min(self.width, self.height) <= 0:
            raise ValueError("output identity and positive dimensions are required")
        if self.bits_per_channel not in (8, 10):
            raise ValueError("physical output precision must be RGB8 or RGB10")


@dataclass(frozen=True, slots=True)
class OutputActivity:
    output_id: str
    swap_entry_ns: int
    swap_return_ns: int
    requested_swap_interval: int
    error: str | None = None


@dataclass(frozen=True, slots=True)
class InstanceSnapshot:
    instance_id: str
    family: str
    active: bool
    state: tuple[tuple[str, float | int | str | bool], ...]
    settings: Settings | None = None
    source_frame_index: int | None = None
    source_pts: int | None = None
    # CPU decode result handed to the GL owner for synchronous upload. It is
    # excluded from evidence and released immediately after the render call.
    decoded_frame: ImagePixels | None = None
    media_selection: MediaSnapshot | None = None


@dataclass(frozen=True, slots=True)
class RenderGroup:
    group_id: int
    trial_id: str
    logical_time_ns: int
    epoch_index: int
    scene_id: str
    instances: tuple[InstanceSnapshot, ...]
    outputs: tuple[OutputActivity, ...]
    clipping_stages: tuple[tuple[str, tuple[str, ...]], ...] = ()
    photodiode_high: bool | None = None


@dataclass(frozen=True, slots=True)
class UniformSnapshot:
    binding_id: str
    words: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class MediaSnapshot:
    instance_id: str
    asset_id: str
    stream_index: int
    source_frame_index: int
    source_pts: int
    time_base_numerator: int
    time_base_denominator: int
    playback_generation: int
    loop_index: int
    target_media_numerator: int
    target_media_denominator: int
    disposition: str


@dataclass(frozen=True, slots=True)
class FeedbackEvidenceSnapshot:
    """Immutable applied/rejected feedback facts for recording after its group."""

    stream_id: str
    result_id: str
    reset_generation: str
    binding_id: str | None
    group_id: int | None
    source_frame_ids: tuple[str, ...]
    source_receipt_ns: int
    application_check_ns: int
    age_limit_ns: int | None
    disposition: Literal[
        "applied",
        "invalid",
        "stale",
        "old_generation",
        "absent",
        "wrong_trial",
        "baseline_only",
    ]
    requested_increment: tuple[float, ...]
    applied_increment: tuple[float, ...]
    target_units: tuple[str, ...]
    target_frame_id: str | None
    constraint_occurred: bool = False


@dataclass(frozen=True, slots=True)
class PoseSnapshot:
    instance_id: str
    frame_id: str
    position_mm: tuple[float, float, float]
    orientation_xyzw: tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class EvidenceStateSnapshot:
    epoch_occurrence: int
    scene_id: str
    evaluation_host_ns: int
    active_instance_ids: tuple[str, ...]
    uniforms: tuple[UniformSnapshot, ...]
    media: tuple[MediaSnapshot, ...]
    effective_poses: tuple[PoseSnapshot, ...]


@dataclass(frozen=True, slots=True)
class SubmissionSnapshot:
    output_id: str
    attempt_index: int | None
    phase: str
    entry_host_ns: int | None
    return_host_ns: int | None
    swap_interval: int
    marker_index: int | None
    marker_high: bool | None
    failure_code: str | None


@dataclass(frozen=True, slots=True)
class RenderPassResult:
    """Exact values consumed by GPU/media providers for one frozen render state."""

    outputs: tuple[RenderedOutput, ...]
    uniforms: tuple[UniformSnapshot, ...]
    media: tuple[MediaSnapshot, ...]
    effective_poses: tuple[PoseSnapshot, ...]
    clipping_stages: tuple[tuple[str, tuple[str, ...]], ...] = ()


@dataclass(frozen=True, slots=True)
class DisplayInitialization:
    output_ids: tuple[str, ...]
    observed_rgb_bits: tuple[tuple[str, int, int, int], ...]
    framebuffer_sizes: tuple[tuple[str, int, int], ...]
    requested_swap_intervals: tuple[tuple[str, int], ...]
    idle_activity: tuple[OutputActivity, ...]


@dataclass(frozen=True, slots=True)
class RenderUpdate:
    group: RenderGroup
    outputs: tuple[RenderedOutput, ...]
    evidence_state: EvidenceStateSnapshot
    evidence_submissions: tuple[SubmissionSnapshot, ...]
    feedback_evidence: tuple[FeedbackEvidenceSnapshot, ...] = ()


@dataclass(frozen=True, slots=True)
class ResourceReleaseReport:
    released: tuple[str, ...]
    outstanding: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DiagnosticSnapshot:
    group_id: int
    output_id: str
    epoch_index: int
    evaluation_host_ns: int
    stages: tuple[str, ...]


class RenderPort(Protocol):
    """Implementation adapter; every method is invoked on its GL-owner thread."""

    def service_display(self) -> bool: ...

    def poll_diagnostics(self) -> tuple[DiagnosticSnapshot, ...]: ...

    @property
    def diagnostics_pending(self) -> bool: ...

    def initialize_display(self, display: object) -> DisplayInitialization: ...

    def show_idle(self, display: object) -> tuple[OutputActivity, ...]: ...

    def present_display_calibration(
        self, display: DisplayProfile, prepared: PreparedDisplayCalibration
    ) -> tuple[OutputActivity, ...]: ...

    def close_display_calibration(
        self, display: DisplayProfile, prepared: PreparedDisplayCalibration
    ) -> tuple[tuple[OutputActivity, ...], bool]: ...

    def prepare_trial(self, artifact: object, resources: object) -> None: ...

    def render(
        self, scene: object, state: Sequence[InstanceSnapshot]
    ) -> RenderPassResult: ...

    def present(
        self, frames: Sequence[RenderedOutput]
    ) -> tuple[OutputActivity, ...]: ...

    def capture_review_composite(
        self, slot: object, outputs: tuple[RenderedOutput, ...], encoding: object
    ) -> object: ...

    def poll_review_capture(self, pending: object) -> bytes | None: ...

    def cancel_review_capture(self, pending: object) -> bool: ...

    def release(self) -> ResourceReleaseReport: ...
