"""T27 pure, explicit method registration. No SDK loading, discovery or execution.

Runtime factories are separately registered on the worker using the same identities.
Only installed, explicitly registered concrete schemas are accepted on this boundary.
"""

from dataclasses import dataclass

from cephvr.tracking.config.models.methods import (
    ContourSettings,
    EllipseSettings,
    FinFlowSettings,
    FlowSettings,
    ModelSettings,
    StageConfiguration,
    WaterFlowSettings,
)
from cephvr.tracking.config.models.records import FlowProxyEvidence, GeometryEvidence
from cephvr.visual_stimulus.config.models.schema_common import Model, parse_json


@dataclass(frozen=True)
class StageSpec:
    stage_id: str
    implementation_id: str
    implementation_version: str
    settings_schema_id: str
    settings_type: type[Model]
    input_contracts: tuple[str, ...]
    output_contract: str
    evidence_schema_id: str | None = None
    evidence_type: type[Model] | None = None


class StageRegistry:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], StageSpec] = {}

    def register(self, spec: StageSpec) -> None:
        names = (
            spec.stage_id,
            spec.implementation_id,
            spec.implementation_version,
            spec.settings_schema_id,
            spec.output_contract,
            *spec.input_contracts,
        )
        if not all(isinstance(x, str) and 0 < len(x) <= 128 for x in names):
            raise ValueError("nonempty bounded contract identities required")
        if not spec.input_contracts or len(set(spec.input_contracts)) != len(
            spec.input_contracts
        ):
            raise ValueError("input contracts must be present and unique")
        if not isinstance(spec.settings_type, type) or not issubclass(
            spec.settings_type, Model
        ):
            raise ValueError("strict concrete settings model required")
        if (spec.evidence_schema_id is None) != (spec.evidence_type is None):
            raise ValueError("evidence schema and model must be paired")
        if spec.evidence_type is not None:
            if not isinstance(spec.evidence_type, type) or not issubclass(
                spec.evidence_type, Model
            ):
                raise ValueError("strict concrete evidence model required")
            if (
                spec.evidence_schema_id is None
                or not 0 < len(spec.evidence_schema_id) <= 128
            ):
                raise ValueError("invalid evidence schema identity")
        key = (spec.stage_id, spec.implementation_id)
        if key in self._entries:
            raise ValueError(
                "duplicate stage implementation; never replace a prepared binding"
            )
        self._entries[key] = spec

    def declaration(self, stage_id: str, implementation_id: str) -> StageSpec:
        """Return one registered declaration without parsing its full settings."""
        try:
            return self._entries[(stage_id, implementation_id)]
        except KeyError as exc:
            raise ValueError("unregistered stage implementation") from exc

    def resolve(
        self, selection: StageConfiguration, *, max_bytes: int
    ) -> tuple[StageSpec, Model]:
        try:
            spec = self._entries[(selection.stage_id, selection.implementation_id)]
        except KeyError as exc:
            raise ValueError("unregistered stage implementation") from exc
        if selection.settings_schema_id != spec.settings_schema_id:
            raise ValueError("settings schema mismatch")
        return spec, parse_json(
            spec.settings_type, selection.settings_json, max_bytes=max_bytes
        )

    def validate_evidence(
        self, spec: StageSpec, schema_id: str, source: str, *, max_bytes: int
    ) -> Model:
        if self._entries.get((spec.stage_id, spec.implementation_id)) != spec:
            raise ValueError("unregistered implementation evidence")
        if spec.evidence_type is None or spec.evidence_schema_id != schema_id:
            raise ValueError("unsupported evidence schema")
        return parse_json(spec.evidence_type, source, max_bytes=max_bytes)


def builtin_registry() -> StageRegistry:
    registry = StageRegistry()
    for spec in (
        StageSpec(
            "pose",
            "keypoint_model",
            "1",
            "tracking.model-settings.v1",
            ModelSettings,
            ("tracking.private-image.v1",),
            "tracking.pose-candidates.v1",
        ),
        StageSpec(
            "pose",
            "threshold_contour",
            "2",
            "tracking.contour-settings.v2",
            ContourSettings,
            ("tracking.private-image.v1",),
            "tracking.pose-candidates.v1",
        ),
        StageSpec(
            "image_flow",
            "nvidia_optical_flow",
            "1",
            "tracking.flow-settings.v1",
            FlowSettings,
            ("tracking.frame-pair.v1",),
            "tracking.flow-grid.v1",
        ),
        StageSpec(
            "geometry",
            "three_point_ellipse",
            "2",
            "tracking.ellipse-settings.v2",
            EllipseSettings,
            ("tracking.landmark-triplet.v1",),
            "tracking.sampling-geometry.v1",
            "tracking.geometry-evidence.v1",
            GeometryEvidence,
        ),
        StageSpec(
            "estimator",
            "water_flow_proxy",
            "1",
            "tracking.water-flow-settings.v1",
            WaterFlowSettings,
            (
                "tracking.flow-grid.v1",
                "tracking.sampling-geometry.v1",
                "tracking.pose-use.v1",
            ),
            "tracking.flow-proxy-result.v1",
            "tracking.flow-proxy-evidence.v1",
            FlowProxyEvidence,
        ),
        StageSpec(
            "estimator",
            "fin_flow_proxy",
            "1",
            "tracking.fin-flow-settings.v1",
            FinFlowSettings,
            (
                "tracking.flow-grid.v1",
                "tracking.sampling-geometry.v1",
                "tracking.pose-use.v1",
            ),
            "tracking.flow-proxy-result.v1",
            "tracking.flow-proxy-evidence.v1",
            FlowProxyEvidence,
        ),
    ):
        registry.register(spec)
    return registry


# Registration identifies declaration schemas, not an available native runtime or Ready.
# Both estimator registrations share one numerical implementation with distinct sampling settings.
