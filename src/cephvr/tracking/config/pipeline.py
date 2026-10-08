"""Pure supported pipeline composition, not factory loading or runtime preparation.

T02/T04/T12/T27: direct stage references, one selected pipeline; no graph interpreter.
"""

from dataclasses import dataclass
from typing import Literal

from cephvr.tracking.config.models.methods import (
    ChannelDeclaration,
    EllipseSettings,
    FlowSettings,
    PreparedMethods,
    StageBinding,
    StageConfiguration,
    WaterFlowSettings,
)
from cephvr.tracking.config.models.records import FlowProxyEvidence
from cephvr.tracking.config.stages import StageRegistry, StageSpec
from cephvr.visual_stimulus.config.models.schema_common import Model


@dataclass(frozen=True)
class PipelineSpec:
    pipeline_id: Literal["water_flow", "fin_flow"]
    implementation_version: str
    estimator_id: str


PIPELINES = {
    "water_flow": PipelineSpec("water_flow", "2", "water_flow_proxy"),
    "fin_flow": PipelineSpec("fin_flow", "2", "fin_flow_proxy"),
}
CHANNELS = tuple(
    ChannelDeclaration(
        channel_id=name,
        quantity="interval_average_rate",
        unit=unit,
        coordinate_frame="anatomical_body",
    )
    for name, unit in (
        ("forward_drive", "mm/s"),
        ("sideways_drive", "mm/s"),
        ("turn_drive", "deg/s"),
    )
)
# The host supplies these adapters; methods are connected once during Setup.
PORTS = {
    "pose": (("tracking.private-image.v1",), "tracking.pose-candidates.v1"),
    "image_flow": (("tracking.frame-pair.v1",), "tracking.flow-grid.v1"),
    "geometry": (("tracking.landmark-triplet.v1",), "tracking.sampling-geometry.v1"),
    "estimator": (
        (
            "tracking.flow-grid.v1",
            "tracking.sampling-geometry.v1",
            "tracking.pose-use.v1",
        ),
        "tracking.flow-proxy-result.v1",
    ),
}
IMPLEMENTATIONS = {
    "pose": {"keypoint_model", "threshold_contour"},
    "image_flow": {"nvidia_optical_flow"},
    "geometry": {"three_point_ellipse"},
}


@dataclass(frozen=True)
class ResolvedPipeline:
    definition: PipelineSpec
    stages: tuple[tuple[StageSpec, Model], ...]
    channels: tuple[ChannelDeclaration, ...]

    def bindings(self) -> tuple[StageBinding, ...]:
        return tuple(
            StageBinding(
                stage_id=s.stage_id,
                implementation_id=s.implementation_id,
                implementation_version=s.implementation_version,
                settings_schema_id=s.settings_schema_id,
                resolved_settings_json=m.model_dump_json(),
                input_contracts=s.input_contracts,
                output_contract=s.output_contract,
                evidence_schema_id=s.evidence_schema_id,
            )
            for s, m in self.stages
        )


def resolve_pipeline(
    pipeline_id: str,
    pose_mode: str,
    selections: tuple[StageConfiguration, ...],
    registry: StageRegistry,
    *,
    max_bytes: int,
) -> ResolvedPipeline:
    try:
        definition = PIPELINES[pipeline_id]
    except KeyError as exc:
        raise ValueError("unsupported pipeline") from exc
    if pose_mode not in ("manual", "automatic"):
        raise ValueError("explicit pose mode required")
    order = (("pose",) if pose_mode == "automatic" else ()) + (
        "image_flow",
        "geometry",
        "estimator",
    )
    selected = {x.stage_id: x for x in selections}
    if len(selected) != len(selections) or set(selected) != set(order):
        raise ValueError("missing, duplicate or inactive stage")
    resolved = []
    for role in order:
        s, m = registry.resolve(selected[role], max_bytes=max_bytes)
        supported = (
            {definition.estimator_id} if role == "estimator" else IMPLEMENTATIONS[role]
        )
        if s.implementation_id not in supported:
            raise ValueError("incompatible pipeline implementation")
        if (s.input_contracts, s.output_contract) != PORTS[role]:
            raise ValueError("incompatible stage ports")
        if role in ("geometry", "estimator") and s.evidence_type is None:
            raise ValueError("required stage evidence missing")
        resolved.append((s, m))
    settings = {s.stage_id: m for s, m in resolved}
    flow, estimator = settings["image_flow"], settings["estimator"]
    if not isinstance(flow, FlowSettings) or not isinstance(
        estimator, WaterFlowSettings
    ):
        raise ValueError("incompatible initial flow/estimator settings")
    if estimator.quality.maximum_native_cost is not None and not flow.output_cost:
        raise ValueError("cost screening requires prepared native cost output")
    return ResolvedPipeline(definition, tuple(resolved), CHANNELS)


def validate_prepared(prepared: PreparedMethods, resolved: ResolvedPipeline) -> None:
    """Checks declarations only; lifecycle still verifies source, assets and factories."""
    if (prepared.pipeline_id, prepared.implementation_version) != (
        resolved.definition.pipeline_id,
        resolved.definition.implementation_version,
    ):
        raise ValueError("prepared pipeline identity mismatch")
    if prepared.channels != resolved.channels or prepared.stages != resolved.bindings():
        raise ValueError("prepared channels or stage bindings mismatch")
    if not prepared.geometry_binding_id or not prepared.estimator_binding_id:
        raise ValueError("prepared concrete geometry and estimator identities required")


def validate_proxy_evidence(
    evidence: FlowProxyEvidence, resolved: ResolvedPipeline
) -> None:
    """Cross-settings validation shared by compact-record admission and external inspection."""
    settings = {s.stage_id: m for s, m in resolved.stages}
    estimator, geometry = settings["estimator"], settings["geometry"]
    if not isinstance(estimator, WaterFlowSettings) or not isinstance(
        geometry, EllipseSettings
    ):
        raise ValueError("unsupported evidence validator for settings")
    if evidence.pipeline_id != resolved.definition.pipeline_id:
        raise ValueError("evidence pipeline mismatch")
    if evidence.counts is None:
        if evidence.sections or evidence.validity == "valid":
            raise ValueError("unmeasured support must be absent")
        return
    if len(evidence.sections) != estimator.sections.count:
        raise ValueError("section count mismatch")
    total_area = sum(s.accepted_area_px2 for s in evidence.sections)
    if (evidence.counts.accepted == 0) != (total_area == 0):
        raise ValueError("count/area support mismatch")
    if estimator.quality.maximum_native_cost is None and evidence.counts.cost_rejected:
        raise ValueError("cost rejection without configured cost test")
    if evidence.validity == "valid":
        required = [s for s in evidence.sections if s.intended_area_px2 > 0]
        if not required:
            raise ValueError("empty required selection")
        if evidence.pipeline_id == "water_flow" and len(required) != len(
            evidence.sections
        ):
            raise ValueError("water requires every configured section")
        # T26/T44: one gate per section; clipped pixels count as missing, never renormalized.
        for s in required:
            if (
                s.accepted_area_px2 / s.intended_area_px2
                < estimator.support.minimum_accepted_area_fraction
            ):
                raise ValueError("valid estimate fails a required section gate")
