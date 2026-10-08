"""T19 scientific movement record formatting from completed result values."""

from cephvr.tracking.config.models.record_json import feedback_json
from cephvr.tracking.config.models.records import (
    FlowProxyEvidence,
    GeometryEvidence,
    MovementResult,
    PoseUse,
    RegionCoverage,
    StageEvidence,
    TrackingRecord,
)
from cephvr.visual_stimulus.v1.data_pb2 import FeedbackResult


def movement_record(
    result: FeedbackResult,
    *,
    produced_host_ns: int,
    pose: PoseUse,
    evidence: FlowProxyEvidence | None,
) -> TrackingRecord:
    stages = (
        ()
        if evidence is None
        else (
            StageEvidence(
                stage_id="estimator",
                schema_id="tracking.flow-proxy-evidence.v1",
                payload=evidence.model_dump_json(),
            ),
        )
    )
    if evidence is not None and evidence.sections:
        coverage = GeometryEvidence(
            schema_version=1,
            regions=tuple(
                RegionCoverage(
                    region_id=f"section_{section.section_index}",
                    requested_pixels=int(section.intended_area_px2),
                    visible_pixels=int(section.visible_area_px2),
                    clipped_fraction=(
                        section.intended_area_px2 - section.visible_area_px2
                    )
                    / section.intended_area_px2,
                )
                for section in evidence.sections
                if section.intended_area_px2 > 0
            ),
        )
        stages = (
            StageEvidence(
                stage_id="geometry",
                schema_id="tracking.geometry-evidence.v1",
                payload=coverage.model_dump_json(),
            ),
            *stages,
        )
    return TrackingRecord(
        record=MovementResult(
            kind="result",
            feedback_result=feedback_json(result),
            produced_host_ns=produced_host_ns,
            pose=pose,
            stage_evidence=stages,
        )
    )
