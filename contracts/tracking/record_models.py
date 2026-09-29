"""T09/T15/T17/T19 compact record lines for `<prefix>_tracking.jsonl`.

One TrackingRecord is one UTF-8 JSON line. Cross-line/source/FeedbackResult validation
belongs to records.md. No recorder, file reader or simulated backend.
"""
from __future__ import annotations
import base64
import binascii
import hashlib
import math
import re
from typing import Annotated, Literal, Self
from pydantic import AfterValidator, Field, model_validator
from schema_common import Model, Name, U32, U64, NS, Digest, Version1, parse_json

class Point(Model):
    x_px: Annotated[float,Field(ge=0)]
    y_px: Annotated[float,Field(ge=0)]

class Triplet(Model):
    # T21 anatomical aliases are identical to PoseLandmarks; see pose.md.
    tip: Point
    left_base: Point
    right_base: Point
    @model_validator(mode='after')
    def nondegenerate(self) -> Self:
        a,b,c=self.tip,self.left_base,self.right_base
        area=(b.x_px-a.x_px)*(c.y_px-a.y_px)-(b.y_px-a.y_px)*(c.x_px-a.x_px)
        if not math.isfinite(area) or area==0:
            raise ValueError('landmarks must be distinct and noncollinear')
        return self

class SourceFrame(Model):
    frame_id: U64 # A09 per-camera/per-trial ID also supplies source ordering.
    host_receipt_ns: NS

UUID4 = Annotated[str,Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")]

def _generation(value: str) -> str:
    if not re.fullmatch(r'[1-9][0-9]*',value) or int(value)>(1<<64)-1:
        raise ValueError('reset generation must be a canonical positive uint64 decimal')
    return value
# A06 FeedbackResult.reset_generation: monotonic per attachment/stream.
Generation = Annotated[str,AfterValidator(_generation)]

class Identity(Model):
    session_id: UUID4
    trial_id: UUID4
    tracking_process_instance_id: UUID4
    writer_generation: UUID4
    configuration_revision: U64
    prepared_generation: UUID4
    source_allocation_id: UUID4

class Header(Model):
    kind: Literal['header']
    schema_version: Version1
    stream_kind: Literal['tracking']
    identity: Identity
    trial_start_host_ns: NS
    trial_normal_end_host_ns: NS
    pipeline_id: Literal['water_flow','fin_flow']
    pose_mode: Literal['manual','automatic']
    prepared_methods_sha256: Digest
    # Exact canonical PreparedMethods and resolved tracking settings retained here,
    # to avoid putting package/asset hashes in E04's restricted central metadata.
    prepared_methods_json: str
    resolved_settings_json: str
    image_width_px: Annotated[int,Field(gt=0,le=(1<<32)-1)]
    image_height_px: Annotated[int,Field(gt=0,le=(1<<32)-1)]
    @model_validator(mode='after')
    def interval(self) -> Self:
        if self.trial_normal_end_host_ns<=self.trial_start_host_ns:raise ValueError('invalid trial interval')
        if hashlib.sha256(self.prepared_methods_json.encode('utf8')).hexdigest()!=self.prepared_methods_sha256:
            raise ValueError('prepared methods digest disagrees with exact UTF-8 text')
        return self

class PoseObservation(Model):
    kind: Literal['pose']
    observation_id: Name
    reset_generation: Generation # Latest processing reset at computation; may cross later resets.
    source: SourceFrame
    completion_host_ns: NS # Immutable pose/geometry pair ready, including construction.
    method: Name # Registered prepared pose implementation, not a closed provider enum.
    validity: Literal['valid','invalid']
    reason: Name | None
    landmarks: Triplet | None
    eligible_candidate_count: U32
    selected_score: Annotated[float,Field(gt=0)] | None
    top_score_tie: bool
    disposition: Literal['published','retired_generation','cutoff_excluded']
    @model_validator(mode='after')
    def valid(self) -> Self:
        if self.completion_host_ns<self.source.host_receipt_ns:raise ValueError('completion precedes source')
        if self.validity=='valid':
            if self.landmarks is None or self.selected_score is None or self.eligible_candidate_count<1 or self.reason is not None:
                raise ValueError('valid pose requires complete selected candidate')
        elif self.landmarks is not None or self.selected_score is not None or self.eligible_candidate_count!=0 or self.top_score_tie or not self.reason:
            raise ValueError('invalid pose cannot fabricate selected candidate')
        if self.top_score_tie and self.eligible_candidate_count<2:raise ValueError('tie requires multiple candidates')
        return self

class PoseUse(Model):
    disposition: Literal['manual','valid','missing','invalid','stale']
    observation_id: Name | None
    manual_geometry_id: Name | None
    check_host_ns: NS
    pose_source_host_ns: NS | None
    age_ns: NS | None
    maximum_age_ns: Annotated[int,Field(gt=0,le=(1<<63)-1)] | None
    @model_validator(mode='after')
    def evidence(self) -> Self:
        if self.disposition=='manual':
            if not self.manual_geometry_id or any(x is not None for x in (self.observation_id,self.pose_source_host_ns,self.age_ns,self.maximum_age_ns)):
                raise ValueError('manual geometry has no observation or age')
        else:
            if self.manual_geometry_id is not None or self.maximum_age_ns is None:raise ValueError('automatic pose needs age limit')
            if self.disposition=='missing':
                if any(x is not None for x in (self.observation_id,self.pose_source_host_ns,self.age_ns)):raise ValueError('missing pose fabricates no identity/age')
            else:
                if self.observation_id is None or self.pose_source_host_ns is None or self.age_ns is None:raise ValueError('selected pose requires identity/timing')
                if self.check_host_ns-self.pose_source_host_ns!=self.age_ns:raise ValueError('incorrect pose age')
                if self.disposition=='valid' and self.age_ns>self.maximum_age_ns:raise ValueError('valid pose is stale')
                if self.disposition=='stale' and self.age_ns<=self.maximum_age_ns:raise ValueError('stale pose must exceed limit')
        return self

class WirePayload(Model):
    protobuf_base64: Annotated[str,Field(min_length=1)]
    @model_validator(mode='after')
    def canonical(self) -> Self:
        try:data=base64.b64decode(self.protobuf_base64,validate=True)
        except (ValueError,binascii.Error) as e:raise ValueError('invalid base64') from e
        if not data or base64.b64encode(data).decode()!=self.protobuf_base64:raise ValueError('noncanonical/empty protobuf bytes')
        return self

class RegionCoverage(Model):
    region_id: Name
    requested_pixels: Annotated[int,Field(gt=0,le=(1<<64)-1)]
    visible_pixels: U64
    clipped_fraction: Annotated[float,Field(ge=0,le=1)] # Logged only; T44 gates coverage.
    @model_validator(mode='after')
    def counts(self) -> Self:
        if self.visible_pixels>self.requested_pixels:raise ValueError('visible exceeds requested support')
        expected=(self.requested_pixels-self.visible_pixels)/self.requested_pixels
        if abs(self.clipped_fraction-expected)>1e-12:raise ValueError('incorrect clipped fraction')
        return self

class GeometryEvidence(Model):
    schema_version: Version1
    regions: tuple[RegionCoverage, ...]
    @model_validator(mode='after')
    def unique(self) -> Self:
        ids=[x.region_id for x in self.regions]
        if len(ids)!=len(set(ids)):raise ValueError('duplicate region coverage')
        return self

class DriveTriplet(Model):
    forward_drive: float
    sideways_drive: float
    turn_drive: float

class FlowSectionEvidence(Model):
    section_index: U32
    intended_area_px2: Annotated[float, Field(ge=0)]
    visible_area_px2: Annotated[float, Field(ge=0)]
    accepted_area_px2: Annotated[float, Field(ge=0)]
    @model_validator(mode='after')
    def areas(self) -> Self:
        if not self.accepted_area_px2 <= self.visible_area_px2 <= self.intended_area_px2:
            raise ValueError('accepted <= visible <= intended areas required')
        return self

class FlowSampleCounts(Model):
    selected: U64
    unavailable: U64
    nonfinite: U64
    cost_rejected: U64
    neighbor_unevaluable: U64
    median_rejected: U64
    accepted: U64
    @model_validator(mode='after')
    def partition(self) -> Self:
        if self.selected != sum((self.unavailable,self.nonfinite,self.cost_rejected,
                                 self.neighbor_unevaluable,self.median_rejected,self.accepted)):
            raise ValueError('sample dispositions must partition selected native cells')
        return self

class FlowProxyEvidence(Model):
    schema_version: Version1
    pipeline_id: Literal['water_flow','fin_flow']
    validity: Literal['valid','invalid']
    reason: Name | None
    sections: tuple[FlowSectionEvidence,...]
    counts: FlowSampleCounts | None # None when pose/geometry prevents selecting samples.
    # Float64 anatomical basis; no dense vectors or per-sample scores.
    centroid_body_px: tuple[float,float] | None
    mean_velocity_body_px_per_s: tuple[float,float] | None
    centred_moment_px2_per_s: float | None
    centred_second_moment_px2: Annotated[float,Field(gt=0)] | None # Area-averaged; raw turn is -moment/this in 1/s.
    raw: DriveTriplet | None
    filtered_average: DriveTriplet | None
    filter_end: DriveTriplet | None
    filter_disposition: Literal['seeded','continued','cleared']
    @model_validator(mode='after')
    def coherent(self) -> Self:
        ids=[x.section_index for x in self.sections]
        if ids != list(range(len(ids))):raise ValueError('complete ordered section indices required')
        values=(self.centroid_body_px,self.mean_velocity_body_px_per_s,
                self.centred_moment_px2_per_s,self.centred_second_moment_px2,self.raw,self.filtered_average,self.filter_end)
        if self.validity=='valid':
            if self.reason is not None or any(x is None for x in values) or self.filter_disposition=='cleared':
                raise ValueError('valid proxy requires complete controls and diagnostics')
            if not self.sections or self.counts is None or self.counts.accepted==0 or sum(x.accepted_area_px2 for x in self.sections)<=0:
                raise ValueError('valid proxy needs accepted support')
            if (self.raw.forward_drive,self.raw.sideways_drive,self.raw.turn_drive) != (
                    -self.mean_velocity_body_px_per_s[0],-self.mean_velocity_body_px_per_s[1],
                    -self.centred_moment_px2_per_s/self.centred_second_moment_px2):
                raise ValueError('raw controls must preserve proxy signs and units')
            if self.filter_disposition=='seeded' and not self.raw==self.filtered_average==self.filter_end:
                raise ValueError('seeded filter must equal raw controls')
        elif not self.reason or any(x is not None for x in values) or self.filter_disposition!='cleared':
            raise ValueError('invalid proxy clears state and carries no usable controls')
        return self

class StageEvidence(Model):
    stage_id: Name
    schema_id: Name
    payload_json: str # Exact registered compact schema, never arbitrary data.

class MovementResult(Model):
    kind: Literal['result']
    feedback_result: WirePayload # Exact cephvr.vr.v1.FeedbackResult bytes, independently typed/validated.
    produced_host_ns: NS
    pose: PoseUse
    stage_evidence: tuple[StageEvidence, ...]
    @model_validator(mode="after")
    def unique_stages(self) -> Self:
        ids=[x.stage_id for x in self.stage_evidence]
        if len(ids)!=len(set(ids)):raise ValueError("duplicate stage evidence")
        return self
    # Estimator quality uses the registered FlowProxyEvidence schema; no arbitrary dict.

ResetCause = Literal['trial_start','camera_gap','input_age','input_overflow','result_overflow']

class Reset(Model):
    """A06: one line per reset, before any result carrying its generation."""
    kind: Literal['reset']
    reset_generation: Generation
    causes: Annotated[tuple[ResetCause,...],Field(min_length=1)]
    observed_host_ns: NS
    @model_validator(mode='after')
    def unique(self) -> Self:
        if len(self.causes)!=len(set(self.causes)):raise ValueError('duplicate reset cause')
        return self
    # Only ('result_overflow',) is delivery-only; any other cause also resets processing.

class Discard(Model):
    kind: Literal['discard']
    reset_generation: Generation
    observed_host_ns: NS
    target: Literal['source_frame','result']
    ids: Annotated[tuple[Name,...],Field(min_length=1)]
    reason: Literal['camera_gap','input_age','input_overflow','result_overflow','retired_generation','trial_cutoff']
    @model_validator(mode='after')
    def unique(self) -> Self:
        if len(self.ids)!=len(set(self.ids)):raise ValueError('duplicate discard target')
        if self.target=='source_frame' and any(not re.fullmatch(r'0|[1-9][0-9]*',v) or int(v)>(1<<64)-1 for v in self.ids):
            raise ValueError('source frame IDs must be canonical unsigned uint64 decimals')
        return self

class Completion(Model):
    kind: Literal['completion']
    cutoff_host_ns: NS
    outcome: Literal['completed','interrupted']
    pose_records: U64
    result_records: U64
    reset_records: U64
    discard_records: U64
    # This counts records, not unique dropped IDs or unknown unacquired camera frames.

Record=Annotated[Header|PoseObservation|MovementResult|Reset|Discard|Completion,Field(discriminator='kind')]
class TrackingRecord(Model):
    record: Record

SCHEMAS={'tracking-record':TrackingRecord,'geometry-evidence':GeometryEvidence,
         'flow-proxy-evidence':FlowProxyEvidence}
def parse_record(source: str, *, max_bytes: int) -> TrackingRecord:
    """Parse one line's JSON text (without its LF) within recording.max_record_bytes."""
    return parse_json(TrackingRecord,source,max_bytes=max_bytes)
