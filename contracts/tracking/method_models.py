"""Pure tracking method/asset declarations; no SDK, file or inference calls.

Load with contracts/vr on the contract module path to reuse schema_common.
These models bind geometry and complete initial estimator settings. Every field is
required in resolved settings: E07 fills tracking_config defaults; saved values win.
Runtime methods remain separate work; declaration validation cannot establish Ready.
"""
from __future__ import annotations
from typing import Annotated, Literal, Self
from pydantic import Field, BeforeValidator, model_validator
from schema_common import Model, Name, Digest, Version1, Version2, U32, U64, portable_path, parse_json, exact_integer

Positive = Annotated[float, Field(gt=0)]
PosInt = Annotated[int, Field(gt=0, le=4294967295)]
Probability = Annotated[float, Field(ge=0, le=1)]

class Asset(Model):
    relative_path: str
    @model_validator(mode='after')
    def path(self) -> Self:
        portable_path(self.relative_path)
        return self

class LandmarkQuality(Model):
    minimum_axis_px: Positive
    minimum_base_width_px: Positive
    minimum_triangle_area_px2: Positive

class ModelManifest(Model):
    schema_version: Version1
    adapter: Literal['onnx_triplet_v1']
    model: Asset
    external_weights: tuple[Asset, ...]
    input_name: Name
    output_name: Name
    input_width_px: PosInt
    input_height_px: PosInt
    channels: Literal['gray', 'rgb']
    # Fixed batch=1, NCHW float32; aspect-preserving letterbox.
    mean: tuple[float, ...]
    std: tuple[Positive, ...]
    padding_source_fraction: tuple[Probability, ...]
    maximum_candidates: PosInt
    # T21 order: posterior tip, left anterior tip, right anterior tip (pose.md).
    # Fixed output [1,K,10]: score, tip(x,y,p), left_base(x,y,p), right_base(x,y,p).
    # Exported model performs any required native decode and duplicate suppression.
    @model_validator(mode='after')
    def layout(self) -> Self:
        count=1 if self.channels=='gray' else 3
        if any(len(x)!=count for x in (self.mean,self.std,self.padding_source_fraction)):
            raise ValueError('preprocessing arrays must match channel count')
        paths=[self.model.relative_path,*[x.relative_path for x in self.external_weights]]
        if len(paths)!=len(set(paths)): raise ValueError('duplicate asset path')
        return self

class ModelSettings(Model):
    schema_version: Version1
    manifest: Asset
    device_ordinal: U32
    minimum_candidate_score: Probability
    minimum_landmark_score: Probability
    geometry_quality: LandmarkQuality

class ContourSettings(Model):
    schema_version: Version2
    minimum_axis_anisotropy: Annotated[float, Field(gt=0, le=1)]
    threshold_level: float
    foreground_polarity: Literal["dark", "bright"]
    minimum_area_px2: PosInt
    maximum_area_px2: PosInt
    geometry_quality: LandmarkQuality
    @model_validator(mode='after')
    def area(self) -> Self:
        if self.minimum_area_px2>self.maximum_area_px2:raise ValueError('inverted area bounds')
        return self
    # Threshold/polarity belong to this implementation, not the shared control envelope.
    # T06: mask-moment axis and directional boundary extremes (contour-landmarks.md).

class FlowSettings(Model):
    schema_version: Version1
    adapter: Literal['nvof_cuda_v1']
    device_ordinal: U32 # Config default 0; Setup verifies the physical GPU.
    output_grid_px: Annotated[Literal[1,2,4], BeforeValidator(exact_integer)] # Default 4.
    preset: Literal['slow','medium','fast'] # Default slow.
    temporal_hints: bool # Default false.
    output_cost: bool # Default false.
    # Explicit preprocessing identity, never an implicit preview conversion.
    input_mapping: Literal['declared_full_range_gray8_v1']

class EllipseSettings(Model):
    """T25–T31 reference ellipse, body-following tapered outline and full distance band."""
    schema_version: Version2
    front_fraction: Annotated[float, Field(gt=0, le=1)] # E07 resolves default 0.60.
    taper: Annotated[float, Field(gt=-1, lt=1)] # Default 0.4.
    squareness: Positive # Default 3.5.
    inner_clearance_fraction: Annotated[float, Field(ge=0)] # Default 0.1.
    outer_extent_fraction: Positive # Default 0.75.
    # T26 clipping is logged per section; T44 support is the only coverage gate.
    @model_validator(mode='after')
    def band(self) -> Self:
        if self.outer_extent_fraction<=self.inner_clearance_fraction:
            raise ValueError('outer extent must exceed inner clearance')
        return self

class ArcSectionSettings(Model):
    """T32 subset embedded in each selected estimator's concrete settings."""
    schema_version: Version1
    count: Annotated[int, BeforeValidator(exact_integer), Field(gt=0, le=4294967295)]
    # Config default 12; origin/metric/assignment are fixed method policy.

class FinRegionSettings(Model):
    """T04 angular crop of the full band; section boundaries are unchanged."""
    schema_version: Version1
    offset_degrees: Annotated[float, Field(ge=-180, lt=180)]
    span_degrees: Annotated[float, Field(gt=0, le=360)]

class SectionFlowSupportSettings(Model):
    """T44: accepted/intended (pre-clip) area in every section; default 0.25."""
    schema_version: Version1
    minimum_accepted_area_fraction: Annotated[float, Field(gt=0, le=1)]

class ExponentialSmoothingSettings(Model):
    """T45: one source-time constant for all three drive channels; default 0.08 s."""
    schema_version: Version1
    time_constant_s: Positive

class LocalMedianSettings(Model):
    """T41/W1A/W2A; image pixels. Defaults 1, 4, 0.1 px, 2.0; no cost limit."""
    schema_version: Version1
    radius_cells: PosInt
    minimum_neighbors: PosInt
    noise_floor_px: Positive
    maximum_normalized_residual: Positive
    maximum_native_cost: Annotated[int, Field(ge=0, le=255)] | None
    @model_validator(mode='after')
    def support(self) -> Self:
        if self.minimum_neighbors > (2*self.radius_cells+1)**2-1:
            raise ValueError('neighbor requirement exceeds square excluding center')
        return self

class WaterFlowSettings(Model):
    schema_version: Version1
    sections: ArcSectionSettings
    quality: LocalMedianSettings
    support: SectionFlowSupportSettings
    smoothing: ExponentialSmoothingSettings

class FinFlowSettings(WaterFlowSettings):
    fin_region: FinRegionSettings

class StageConfiguration(Model):
    stage_id: Name
    implementation_id: Name
    settings_schema_id: Name
    settings_json: str # Bounded and validated by the registered pure concrete model.

class StageBinding(Model):
    stage_id: Name
    implementation_id: Name
    implementation_version: Name
    settings_schema_id: Name
    resolved_settings_json: str
    input_contracts: tuple[Name, ...]
    output_contract: Name
    evidence_schema_id: Name | None

class FileLimits(Model):
    schema_version: Version1
    max_document_bytes: PosInt
    max_asset_bytes: Annotated[int, Field(gt=0, le=(1<<63)-1)]
    max_native_bytes: Annotated[int, Field(gt=0, le=(1<<63)-1)]
    maximum_message_bytes: PosInt
    pose_progress_timeout_s: Positive
    movement_progress_timeout_s: Positive
    @model_validator(mode='after')
    def time(self) -> Self:
        from decimal import Decimal
        for value in (self.pose_progress_timeout_s,self.movement_progress_timeout_s):
            ns=Decimal(str(value))*1_000_000_000
            if ns!=ns.to_integral_value() or not 0<ns<=2**63-1:
                raise ValueError('timeout must resolve to exact positive int64 nanoseconds')
        return self

class ResolvedAsset(Model):
    relative_path: str
    byte_length: U64
    sha256: Digest
    @model_validator(mode='after')
    def path(self) -> Self:
        portable_path(self.relative_path)
        return self

class ChannelDeclaration(Model):
    channel_id: Name
    quantity: Literal['absolute','displacement','interval_average_rate']
    unit: Name
    coordinate_frame: Name
    # Values supplied by the accepted pipeline catalogue, not arbitrary GUI fields.

class PreparedMethods(Model):
    schema_version: Version1
    prepared_generation: Name
    configuration_revision: U64
    pipeline_id: Literal['water_flow','fin_flow']
    implementation_version: Name
    stages: tuple[StageBinding, ...]
    source_allocation_id: Name
    source_layout_digest: Digest
    method_assets: tuple[ResolvedAsset, ...]
    onnxruntime_version: Name | None
    cuda_device_identity: Name | None
    nvof_api_version: Name | None
    driver_version: Name | None
    cpu_graph_node_names: tuple[Name, ...]
    channels: tuple[ChannelDeclaration, ...]
    geometry_binding_id: Name | None
    estimator_binding_id: Name | None
    @model_validator(mode='after')
    def unique(self) -> Self:
        stages=[x.stage_id for x in self.stages]
        if len(stages)!=len(set(stages)):raise ValueError("duplicate prepared stage")
        ids=[x.channel_id for x in self.channels]
        if len(ids)!=len(set(ids)):raise ValueError('duplicate channel')
        paths=[x.relative_path for x in self.method_assets]
        if len(paths)!=len(set(paths)):raise ValueError('duplicate prepared asset')
        return self
    # No Ready from this declaration alone: geometry/estimator IDs and catalogue match required.

SCHEMAS={'model-manifest':ModelManifest,'model-settings':ModelSettings,
         'contour-settings':ContourSettings,'flow-settings':FlowSettings,
         'file-limits':FileLimits,'prepared-methods':PreparedMethods,
         'ellipse-settings':EllipseSettings,'arc-section-settings':ArcSectionSettings,
         'fin-region-settings':FinRegionSettings,
         'section-flow-support-settings':SectionFlowSupportSettings,
         'exponential-smoothing-settings':ExponentialSmoothingSettings,
         'local-median-settings':LocalMedianSettings,
         'water-flow-settings':WaterFlowSettings,'fin-flow-settings':FinFlowSettings,
         'stage-configuration':StageConfiguration,
         'stage-binding':StageBinding}

def parse_method(kind: str, source: str, *, max_bytes: int) -> Model:
    return parse_json(SCHEMAS[kind],source,max_bytes=max_bytes)
