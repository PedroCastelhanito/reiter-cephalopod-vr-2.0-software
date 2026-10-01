"""T08 focused runtime ports and immutable leased payloads. No SDK initialization.

Generated Protobuf classes are built from contracts/ into the runtime package.
Every operation is serialized by its owning thread; cancellation does not free leases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, TypeVar

from cephvr.acquisition.v1.messages_pb2 import FrameBufferAttachment
from cephvr.control.v1.types_pb2 import OutputResult, WorkContext
from cephvr.tracking.config.models.methods import ContourSettings, FileLimits
from cephvr.tracking.config.models.records import (
    FlowProxyEvidence,
    PoseObservation,
    PoseUse,
    SourceFrame,
    TrackingRecord,
    Triplet,
)
from cephvr.tracking.v1.pose_pb2 import PoseSearchRegion, SubjectReferenceSettings
from cephvr.visual_stimulus.config.models.schema_common import Model

SettingsT = TypeVar("SettingsT", bound=Model, contravariant=True)


@dataclass(frozen=True)
class ImageLayout:
    width: int
    height: int
    row_stride_bytes: int
    channels: Literal["gray", "rgb"]
    storage: Literal["uint8", "uint16", "float32"]
    effective_bits: int
    alignment: Literal["lsb", "msb", "fractional"]
    minimum_code: float
    maximum_code: float
    transform_id: str


@dataclass(frozen=True)
class PrivateFrame:
    source: SourceFrame
    work: WorkContext
    reset_generation: str  # Processing identity; unchanged by delivery-only overflow.
    layout: ImageLayout
    pixels: memoryview  # Read-only private CPU copy, not an acquisition slot.
    lease_id: str


@dataclass(frozen=True)
class PoseCandidate:
    component_id: int
    score: float
    # Native image coordinates; posterior, left anterior, right anterior mantle tips (T21).
    landmarks: tuple[tuple[float, float], tuple[float, float], tuple[float, float]]


@dataclass(frozen=True)
class ContourCandidate:
    component_id: int
    area_px2: int
    boundary_xy: tuple[tuple[float, float], ...]
    touches_crop_boundary: bool
    centroid_xy: tuple[
        float, float
    ]  # Component foreground-pixel centroid, source coordinates.
    covariance_xx_xy_yy: tuple[
        float, float, float
    ]  # Population moments / foreground count.


class ContourGeometry(Protocol):
    """T06 implementation 2: source-mask moments and observed directional extremes.

    Declaration only. Numeric axis quality is explicit; no SDK/model loading here.
    """

    def prepare(
        self,
        settings: ContourSettings,
        reference: SubjectReferenceSettings,
        layout: ImageLayout,
    ) -> None: ...
    def landmarks(self, candidate: ContourCandidate) -> PoseCandidate | None: ...


class PoseMethod(Protocol[SettingsT]):
    def prepare(
        self,
        settings: SettingsT,
        layout: ImageLayout,
        search: PoseSearchRegion,
        reference: SubjectReferenceSettings,
        asset_root: str,
        limits: FileLimits,
    ) -> None: ...
    def compute(self, frame: PrivateFrame) -> tuple[PoseCandidate, ...]: ...
    def reset(self, generation: str) -> None: ...
    def close(
        self, deadline_host_ns: int
    ) -> bool: ...  # True only after native work/releases.


@dataclass(frozen=True)
class FlowLease:
    lease_id: str
    generation: (
        str  # Processing generation, not delivery; never substitutes for trial context.
    )
    work: WorkContext  # Exact trial context adopted by both input frames.
    mapping_id: str  # Exact prepared FlowGridMapping, including source transform.
    earlier: SourceFrame
    later: SourceFrame
    grid_width: int
    grid_height: int
    grid_step_px: int
    row_pitch_bytes: int
    completion_token: str
    # T27: method-independent layout. NVIDIA uses int16x2 with component_scale=1/32.
    storage_format: Literal["int16x2", "float32x2", "float64x2"]
    byte_order: Literal[
        "little", "big"
    ]  # Native storage convention, checked at preparation.
    memory_domain: Literal["host", "cuda"]
    component_scale: float  # finite positive; raw component * scale gives input pixels.
    units: Literal["input_pixel_displacement"]
    native_buffer_id: str  # Initial adapter: host readback buffer identity.
    quality_buffer_id: str | None
    quality_row_pitch_bytes: int | None
    quality_schema_id: (
        str | None
    )  # Declared provider-specific diagnostic, not common probability.
    validity_buffer_id: (
        str | None
    )  # Optional native availability map, uint8 0/1 per cell.
    validity_row_pitch_bytes: (
        int | None
    )  # Both absent means the complete grid is available.


@dataclass(frozen=True)
class HostFlowView:
    """Borrowed read-only native bytes; layout/lineage stay in the matching FlowLease.

    Valid only after wait_complete succeeds, until release. No extra copy. A view
    cannot extend the owner's lifetime; all consumers finish before lease release.
    """

    lease_id: str
    displacement_bytes: memoryview
    quality_bytes: memoryview | None
    validity_bytes: memoryview | None  # No inferred validity from zero flow or cost.


class FlowMethod(Protocol[SettingsT]):
    def prepare(
        self, settings: SettingsT, layout: ImageLayout, limits: FileLimits
    ) -> None: ...
    def grid_mapping(
        self,
    ) -> FlowGridMapping: ...  # Prepared mapping, lifetime through close.
    def establish_baseline(
        self, frame: PrivateFrame, deadline_host_ns: int
    ) -> bool: ...
    # True only after upload completion; False does not release an in-flight frame.
    def compute_pair(self, earlier: PrivateFrame, later: PrivateFrame) -> FlowLease: ...
    def wait_complete(self, lease: FlowLease, deadline_host_ns: int) -> bool: ...
    def host_view(
        self, lease: FlowLease
    ) -> HostFlowView: ...  # Completed host lease only.
    def release(self, lease: FlowLease) -> None: ...
    def reset(self, generation: str) -> None: ...
    def close(self, deadline_host_ns: int) -> bool: ...


class TrackingInputs(Protocol):
    def attach(self, frames: FrameBufferAttachment) -> None: ...
    def next_private_copy(self, deadline_host_ns: int) -> PrivateFrame | None: ...
    def retain_private(
        self, frame: PrivateFrame
    ) -> None: ...  # Owning thread, no copy.
    def release_private(
        self, frame: PrivateFrame
    ) -> None: ...  # One holder, exactly once.
    def retire(self, deadline_host_ns: int) -> bool: ...


class TrackingRecorder(Protocol):
    def try_admit(self, record: TrackingRecord) -> bool: ...
    def seal(self, cutoff_host_ns: int) -> None: ...
    def finalize(self, deadline_host_ns: int) -> OutputResult: ...


@dataclass(frozen=True)
class FlowGridMapping:
    """Prepared, read-only C-contiguous float64 views; source-coordinate mapping."""

    mapping_id: str
    grid_width: int
    grid_height: int
    sample_xy_px: (
        memoryview  # [height,width,2], actual adapter-declared sample positions.
    )
    footprint_xyxy_px: (
        memoryview  # [height,width,4], nonoverlapping represented rectangles.
    )


@dataclass(frozen=True)
class SamplingGeometry:
    """Immutable pose-worker-owned geometry; manual geometry prepared at Setup."""

    lease_id: str  # Host tracks bounded history/consumer references; never a saved native handle.
    binding_id: str
    origin_xy_px: tuple[
        int, int
    ]  # Includes off-image intended geometry; not camera crop.
    band_mask: (
        memoryview  # C-contiguous uint8 [height,width], 0/1 pixel-center membership.
    )
    width: int
    height: int
    outline_xy_px: memoryview  # float64 [N,2], ordered by sectioning.md.
    centre_xy_px: tuple[float, float]
    anterior_unit_xy: tuple[float, float]
    left_unit_xy: tuple[float, float]  # Orthonormal to anterior; anatomical sign.


@dataclass(frozen=True)
class PoseGeometryObservation:
    work: WorkContext
    preparation_id: str
    source_attachment_generation: str
    observation: PoseObservation  # completion_host_ns includes geometry construction.
    geometry: (
        SamplingGeometry | None
    )  # Same exact observation; none if pose/shape invalid.
    # Publish the pair atomically; retain invalid observations. Geometry absence cannot
    # trigger selection of an older valid pose. No dense geometry in scientific records.


class GeometryMethod(Protocol[SettingsT]):
    def prepare(
        self, settings: SettingsT, layout: ImageLayout, limits: FileLimits
    ) -> None: ...
    def compute(
        self, pose: Triplet
    ) -> (
        SamplingGeometry | None
    ): ...  # Pose worker, or manual Setup; no movement-loop construction.
    def release(
        self, geometry: SamplingGeometry
    ) -> None: ...  # Owner thread after last history/consumer reference.
    # Pose/geometry reset only on incompatible trial/source/preparation; retain leased arrays until release.
    def reset(self, generation: str) -> None: ...
    def close(self, deadline_host_ns: int) -> bool: ...


@dataclass(frozen=True)
class FlowProxyInput:
    work: WorkContext
    reset_generation: str  # Processing generation; must equal flow.generation.
    flow: FlowLease
    host_view: HostFlowView
    mapping: FlowGridMapping
    pose: PoseUse
    geometry: SamplingGeometry | None  # None on missing/invalid/stale pose.


class FlowProxyMethod(Protocol[SettingsT]):
    def prepare(
        self,
        settings: SettingsT,
        layout: ImageLayout,
        mapping: FlowGridMapping,
        limits: FileLimits,
    ) -> None: ...
    def compute(self, sample: FlowProxyInput) -> FlowProxyEvidence: ...
    def reset(self, generation: str) -> None: ...
    def close(self, deadline_host_ns: int) -> bool: ...
