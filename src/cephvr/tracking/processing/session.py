"""Setup-time concrete method assembly on the single movement owner."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import uuid4

from cephvr.acquisition.v1.messages_pb2 import FrameBufferAttachment
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.clock import host_time_ns
from cephvr.shared.deadlines import remaining_seconds
from cephvr.tracking.config.annotations import manual
from cephvr.tracking.config.annotations import reference as validate_reference
from cephvr.tracking.config.diagnostics import DiagnosticResolution, resolve_diagnostic
from cephvr.tracking.config.models.methods import (
    ContourSettings,
    EllipseSettings,
    FileLimits,
    FlowSettings,
    ModelSettings,
    PreparedMethods,
    WaterFlowSettings,
)
from cephvr.tracking.config.validation import validate_settings
from cephvr.tracking.feedback.delivery import FeedbackDelivery
from cephvr.tracking.methods.association import Association
from cephvr.tracking.methods.contour import ContourPose
from cephvr.tracking.methods.geometry import EllipseGeometry
from cephvr.tracking.methods.landmarks import qualified
from cephvr.tracking.methods.model import ModelPose
from cephvr.tracking.methods.nvidia import NvidiaFlow
from cephvr.tracking.methods.proxy import FlowProxy
from cephvr.tracking.processing.gate import TrialGate
from cephvr.tracking.processing.history import PoseHistory
from cephvr.tracking.processing.movement import Movement, MovementPorts
from cephvr.tracking.processing.pose import PoseOperations, PoseWorker
from cephvr.tracking.processing.preprocessing import ImageTransform
from cephvr.tracking.processing.source import RingSource
from cephvr.tracking.types import (
    ImageLayout,
    PoseCandidate,
    PrivateFrame,
    SamplingGeometry,
)
from cephvr.tracking.v1 import pose_pb2
from cephvr.tracking.v1.methods_pb2 import TrackingFilePolicies
from cephvr.visual_stimulus.config.models.schema_common import Model


@dataclass(frozen=True)
class SessionSpec:
    settings: pb.TrackingSettings
    policies: TrackingFilePolicies
    identity: pb.ProcessIdentity
    preparation: str
    revision: int
    asset_root: str
    deadline: int
    first: Callable[[PrivateFrame, str, int], None]
    diagnostic_stages: frozenset[int] | None = None


class NativeSession:
    def __init__(
        self, spec: SessionSpec, gate: TrialGate, delivery: FeedbackDelivery | None
    ) -> None:
        self.spec, self.gate, self.delivery = spec, gate, delivery
        self.source: RingSource | None = None
        self.flow = NvidiaFlow()
        self.geometry = EllipseGeometry()
        self.manual_geometry: SamplingGeometry | None = None
        self.estimator = FlowProxy()
        self.pose: PoseWorker | None = None
        self.movement: Movement | None = None
        self.history = PoseHistory(max(1, spec.settings.pose_history_capacity))
        self.methods: PreparedMethods | None = None
        self.diagnostic_resolution: DiagnosticResolution | None = None
        self.diagnostic_association: Association | None = None
        self.pose_method: ContourPose | ModelPose | None = None
        self.pose_geometry: EllipseGeometry | None = None
        self.closed = False
        self.limits = FileLimits.model_validate_json(spec.policies.limits_json)

    @property
    def image_layout(self) -> ImageLayout:
        if self.source is None:
            raise RuntimeError("source layout is not prepared")
        return self.source.layout

    def prepare(self, frames: FrameBufferAttachment) -> PreparedMethods:
        spec = self.spec
        if spec.diagnostic_stages is not None:
            return self._prepare_diagnostic(frames)
        limits = FileLimits.model_validate_json(spec.policies.limits_json)
        resolved = validate_settings(spec.settings, max_bytes=limits.max_document_bytes)
        selected = {
            definition.stage_id: settings for definition, settings in resolved.stages
        }
        # Disjoint partitions include source copies, simultaneous geometry/history,
        # provider workspaces and estimator scratch; no independent full-budget pools.
        source_limit = limits.max_native_bytes // 8
        flow_limits = limits.model_copy(
            update={"max_native_bytes": limits.max_native_bytes // 4}
        )
        geometry_limits = limits.model_copy(
            update={"max_native_bytes": limits.max_native_bytes // 4}
        )
        estimate_limits = limits.model_copy(
            update={"max_native_bytes": limits.max_native_bytes // 4}
        )
        pose_limits = limits.model_copy(
            update={"max_native_bytes": limits.max_native_bytes // 8}
        )
        self.source = RingSource(
            frames, spec.identity, source_limit, spec.settings.preprocessing
        )
        self.source.open(spec.identity)
        layout = self.source.layout
        source_layout = self.source.source_layout
        transform = self.source.transform
        if spec.settings.HasField("image_scale") and (
            spec.settings.image_scale.image_width_px,
            spec.settings.image_scale.image_height_px,
        ) != (source_layout.width, source_layout.height):
            raise ValueError("image scale dimensions differ from the acquired source")
        flow, shape, estimator = (
            selected["image_flow"],
            selected["geometry"],
            selected["estimator"],
        )
        assert (
            isinstance(flow, FlowSettings)
            and isinstance(shape, EllipseSettings)
            and isinstance(estimator, WaterFlowSettings)
        )
        _validate_flow_grid(layout, flow, estimator)
        self.flow.prepare(flow, layout, flow_limits, transform)
        self.estimator.prepare(
            estimator, source_layout, self.flow.grid_mapping(), estimate_limits
        )
        if spec.settings.pose_mode == pb.TRACKING_POSE_MODE_MANUAL:
            if (
                spec.settings.manual_pose.image_width_px,
                spec.settings.manual_pose.image_height_px,
            ) != (source_layout.width, source_layout.height):
                raise ValueError("manual geometry dimensions differ from bound source")
            self.geometry.prepare(shape, source_layout, geometry_limits)
            self.manual_geometry = self.geometry.compute(
                manual(spec.settings.manual_pose)
            )
            if self.manual_geometry is None:
                raise ValueError("manual geometry has no valid raster support")
            self.estimator.prepare_geometry(self.manual_geometry)
            geometry_binding = self.manual_geometry.binding_id
        else:
            pose_settings = selected["pose"]
            assert isinstance(pose_settings, (ContourSettings, ModelSettings))
            _validate_source_reference(spec.settings.subject_reference, source_layout)
            work_search = _search_for_transform(
                spec.settings.pose_search_region, transform
            )
            work_reference = _reference_for_transform(
                spec.settings.subject_reference, transform
            )
            pose_work_settings = _pose_settings_for_transform(pose_settings, transform)
            self.pose_method = (
                ContourPose()
                if isinstance(pose_settings, ContourSettings)
                else ModelPose()
            )
            self.pose_geometry = EllipseGeometry(
                spec.settings.pose_history_capacity + 2
            )

            def factory() -> PoseOperations:
                assert self.pose_method is not None and self.pose_geometry is not None
                if isinstance(self.pose_method, ContourPose) and isinstance(
                    pose_work_settings, ContourSettings
                ):
                    self.pose_method.prepare(
                        pose_work_settings,
                        layout,
                        work_search,
                        work_reference,
                        spec.asset_root,
                        pose_limits,
                        reference_is_transformed=True,
                    )
                elif isinstance(self.pose_method, ModelPose) and isinstance(
                    pose_work_settings, ModelSettings
                ):
                    if pose_work_settings.device_ordinal != flow.device_ordinal:
                        raise ValueError(
                            "pose and flow must adopt the same physical GPU"
                        )
                    self.pose_method.prepare(
                        pose_work_settings,
                        layout,
                        work_search,
                        work_reference,
                        spec.asset_root,
                        pose_limits,
                    )
                self.pose_geometry.prepare(shape, source_layout, geometry_limits)

                def compute_pose(frame: PrivateFrame) -> tuple[PoseCandidate, ...]:
                    assert self.pose_method is not None
                    return _source_candidates(
                        self.pose_method.compute(frame),
                        transform,
                        source_layout,
                        pose_settings,
                    )

                return PoseOperations(
                    compute_pose,
                    self.pose_geometry.compute,
                    self.pose_geometry.release,
                    self._close_pose,
                    "threshold_contour"
                    if isinstance(pose_settings, ContourSettings)
                    else "keypoint_model",
                )

            self.pose = PoseWorker(
                factory,
                self.source.pool,
                self.history,
                self.gate,
                failure_close=self._close_pose,
            )
            self.pose.ready.result(
                timeout=remaining_seconds(spec.deadline, clock=host_time_ns)
            )
            assert self.pose_geometry is not None
            geometry_binding = self.pose_geometry.binding
        self.methods = PreparedMethods(
            schema_version=1,
            prepared_generation=spec.preparation,
            configuration_revision=spec.revision,
            pipeline_id=resolved.definition.pipeline_id,
            implementation_version=resolved.definition.implementation_version,
            stages=resolved.bindings(),
            source_allocation_id=frames.buffer.allocation_id,
            source_layout_digest=hashlib.sha256(
                frames.buffer.image.SerializeToString(deterministic=True)
            ).hexdigest(),
            method_assets=tuple(self.pose_method.assets.evidence)
            if isinstance(self.pose_method, ModelPose)
            else (),
            onnxruntime_version=self.pose_method.version
            if isinstance(self.pose_method, ModelPose)
            else None,
            cuda_device_identity=self.flow.device.uuid,
            nvof_api_version="2.0",
            driver_version=None,
            cpu_graph_node_names=self.pose_method.cpu_nodes
            if isinstance(self.pose_method, ModelPose)
            else (),
            channels=resolved.channels,
            geometry_binding_id=geometry_binding,
            estimator_binding_id=str(uuid4()),
        )
        self.movement = Movement(
            MovementPorts(
                self.source,
                self.flow,
                self.estimator,
                self.gate,
                self.history,
                self.pose,
                self.manual_geometry,
                self.delivery,
                spec.identity,
                spec.settings.pipeline_id,
                spec.policies.maximum_input_frame_age_ns,
                int(Decimal(str(spec.settings.pose_max_age_ms)) * 1_000_000),
                int(Decimal(str(limits.movement_progress_timeout_s)) * 1_000_000_000),
                spec.first,
                spec.settings.image_scale.pixels_per_mm,
            )
        )
        return self.methods

    def _prepare_diagnostic(
        self,
        frames: FrameBufferAttachment,
    ) -> PreparedMethods:
        """Prepare only the explicitly enabled diagnostic method owners."""
        from cephvr.tracking.v1 import services_pb2 as diagnostic_wire

        spec = self.spec
        stages = spec.diagnostic_stages or frozenset()
        limits = self.limits
        source_limit = limits.max_native_bytes // 8
        flow_limits = limits.model_copy(
            update={"max_native_bytes": limits.max_native_bytes // 4}
        )
        geometry_limits = limits.model_copy(
            update={"max_native_bytes": limits.max_native_bytes // 4}
        )
        estimate_limits = limits.model_copy(
            update={"max_native_bytes": limits.max_native_bytes // 4}
        )
        pose_limits = limits.model_copy(
            update={"max_native_bytes": limits.max_native_bytes // 8}
        )
        self.source = RingSource(
            frames, spec.identity, source_limit, spec.settings.preprocessing
        )
        self.source.open(spec.identity)
        layout, source_layout, transform = (
            self.source.layout,
            self.source.source_layout,
            self.source.transform,
        )
        if spec.settings.HasField("image_scale") and (
            spec.settings.image_scale.image_width_px,
            spec.settings.image_scale.image_height_px,
        ) != (source_layout.width, source_layout.height):
            raise ValueError("image scale dimensions differ from the acquired source")
        self.diagnostic_resolution = resolve_diagnostic(
            spec.settings,
            tuple(stages),
            source_layout,
            max_bytes=limits.max_document_bytes,
        )
        resolved = self.diagnostic_resolution.pipeline
        selected: Mapping[str, Model] = {
            stage.stage_id: model for stage, model in resolved.stages
        }
        active = {
            item.stage
            for item in self.diagnostic_resolution.status
            if item.state == diagnostic_wire.TRACKING_DIAGNOSTIC_STAGE_STATE_AVAILABLE
        }
        pose_enabled = diagnostic_wire.TRACKING_DIAGNOSTIC_STAGE_POSE in active
        flow_enabled = diagnostic_wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW in active
        geometry_enabled = (
            diagnostic_wire.TRACKING_DIAGNOSTIC_STAGE_SAMPLING_REGION in active
        )
        quality_enabled = (
            diagnostic_wire.TRACKING_DIAGNOSTIC_STAGE_FLOW_QUALITY in active
        )
        locomotion_enabled = (
            diagnostic_wire.TRACKING_DIAGNOSTIC_STAGE_LOCOMOTION in active
        )
        flow_settings = selected.get("image_flow")
        shape = selected.get("geometry")
        estimator_settings = selected.get("estimator")
        if flow_enabled and not isinstance(flow_settings, FlowSettings):
            raise ValueError("selected runnable optical flow settings are unavailable")
        if geometry_enabled and not isinstance(shape, EllipseSettings):
            raise ValueError(
                "selected runnable sampling-region settings are unavailable"
            )
        if locomotion_enabled and not isinstance(estimator_settings, WaterFlowSettings):
            raise ValueError("selected runnable locomotion settings are unavailable")
        quality_settings = self.diagnostic_resolution.quality
        if quality_settings is None and isinstance(
            estimator_settings, WaterFlowSettings
        ):
            from cephvr.tracking.config.diagnostics import DiagnosticEstimatorInputs

            quality_settings = DiagnosticEstimatorInputs.model_validate(
                estimator_settings.model_dump()
            )
        if quality_enabled and quality_settings is None and not locomotion_enabled:
            raise ValueError("selected runnable flow-quality settings are unavailable")
        if flow_enabled:
            assert isinstance(flow_settings, FlowSettings)
            _validate_flow_grid(
                layout,
                flow_settings,
                estimator_settings
                if isinstance(estimator_settings, WaterFlowSettings)
                else None,
                minimum_neighbors=(
                    quality_settings.quality.minimum_neighbors
                    if quality_settings is not None
                    else 0
                ),
            )
            self.flow.prepare(flow_settings, layout, flow_limits, transform)
        if locomotion_enabled:
            assert isinstance(estimator_settings, WaterFlowSettings)
            if not flow_enabled:
                raise ValueError("selected diagnostic quality requires optical flow")
            self.estimator.prepare(
                estimator_settings,
                source_layout,
                self.flow.grid_mapping(),
                estimate_limits,
            )
        geometry_binding: str | None = None
        if pose_enabled and spec.settings.pose_mode == pb.TRACKING_POSE_MODE_MANUAL:
            if geometry_enabled and isinstance(shape, EllipseSettings):
                self.geometry.prepare(shape, source_layout, geometry_limits)
                self.manual_geometry = self.geometry.compute(
                    manual(spec.settings.manual_pose)
                )
                if self.manual_geometry is None:
                    raise ValueError("manual geometry has no valid raster support")
                geometry_binding = self.manual_geometry.binding_id
                if locomotion_enabled:
                    self.estimator.prepare_geometry(self.manual_geometry)
        elif pose_enabled:
            pose_settings = selected["pose"]
            assert isinstance(pose_settings, (ContourSettings, ModelSettings))
            _validate_source_reference(spec.settings.subject_reference, source_layout)
            work_search = _search_for_transform(
                spec.settings.pose_search_region, transform
            )
            work_reference = _reference_for_transform(
                spec.settings.subject_reference, transform
            )
            pose_work_settings = _pose_settings_for_transform(pose_settings, transform)
            self.pose_method = (
                ContourPose()
                if isinstance(pose_settings, ContourSettings)
                else ModelPose()
            )
            if geometry_enabled and isinstance(shape, EllipseSettings):
                self.pose_geometry = EllipseGeometry(
                    spec.settings.pose_history_capacity + 2
                )
                self.pose_geometry.prepare(shape, source_layout, geometry_limits)
                geometry_binding = self.pose_geometry.binding
            if isinstance(self.pose_method, ContourPose) and isinstance(
                pose_work_settings, ContourSettings
            ):
                self.pose_method.prepare(
                    pose_work_settings,
                    layout,
                    work_search,
                    work_reference,
                    spec.asset_root,
                    pose_limits,
                    reference_is_transformed=True,
                )
            elif isinstance(self.pose_method, ModelPose) and isinstance(
                pose_work_settings, ModelSettings
            ):
                if (
                    flow_enabled
                    and isinstance(flow_settings, FlowSettings)
                    and pose_work_settings.device_ordinal
                    != flow_settings.device_ordinal
                ):
                    raise ValueError("pose and flow must adopt the same physical GPU")
                self.pose_method.prepare(
                    pose_work_settings,
                    layout,
                    work_search,
                    work_reference,
                    spec.asset_root,
                    pose_limits,
                )
        self.methods = PreparedMethods(
            schema_version=1,
            prepared_generation=spec.preparation,
            configuration_revision=spec.revision,
            pipeline_id=resolved.definition.pipeline_id,
            implementation_version=resolved.definition.implementation_version,
            stages=resolved.bindings(),
            source_allocation_id=frames.buffer.allocation_id,
            source_layout_digest=hashlib.sha256(
                frames.buffer.image.SerializeToString(deterministic=True)
            ).hexdigest(),
            method_assets=tuple(self.pose_method.assets.evidence)
            if isinstance(self.pose_method, ModelPose)
            else (),
            onnxruntime_version=self.pose_method.version
            if isinstance(self.pose_method, ModelPose)
            else None,
            cuda_device_identity=self.flow.device.uuid if self.flow.prepared else None,
            nvof_api_version="2.0" if self.flow.prepared else None,
            driver_version=None,
            cpu_graph_node_names=self.pose_method.cpu_nodes
            if isinstance(self.pose_method, ModelPose)
            else (),
            channels=resolved.channels,
            geometry_binding_id=geometry_binding,
            estimator_binding_id=str(uuid4()) if locomotion_enabled else None,
        )
        return self.methods

    def _close_pose(self, deadline: int) -> bool:
        result = True
        if self.pose_method is not None:
            result = self.pose_method.close(deadline)
        if self.pose_geometry is not None and hasattr(self.pose_geometry, "live"):
            result = self.pose_geometry.close(deadline) and result
        return result

    def begin(self) -> None:
        self.history.clear()
        self.flow.reset(self.gate.processing_generation)
        self.estimator.reset(self.gate.processing_generation)
        if self.delivery is not None:
            self.delivery.begin()

    def run(self) -> None:
        if self.movement is None:
            raise RuntimeError("movement methods are not prepared")
        self.movement.run()

    def reconcile(self, deadline: int) -> bool:
        return self.movement is None or self.movement.reconcile(deadline)

    def progress_failure(self, now: int) -> str | None:
        for name, owner, seconds in (
            ("movement", self.movement, self.limits.movement_progress_timeout_s),
            ("pose", self.pose, self.limits.pose_progress_timeout_s),
        ):
            if owner is None:
                continue
            pending = owner.pending_since_ns
            if pending is not None and now - pending >= int(
                Decimal(str(seconds)) * 1_000_000_000
            ):
                return f"{name} native completion deadline expired; ownership retained"
        if self.pose is not None and self.pose.failure is not None:
            return str(self.pose.failure)
        return None

    def close(self, deadline: int) -> bool:
        if not self.reconcile(deadline):
            return False
        if self.pose is not None and not self.pose.close(deadline):
            return False
        elif self.pose is None and self.pose_method is not None:
            if not self._close_pose(deadline):
                return False
        if self.manual_geometry is not None:
            self.geometry.release(self.manual_geometry)
            self.manual_geometry = None
        if hasattr(self.geometry, "live") and not self.geometry.close(deadline):
            return False
        if not self.flow.close(deadline):
            return False
        self.estimator.close(deadline)
        if self.source is not None and not self.source.close():
            return False
        self.closed = True
        return True


def _search_for_transform(
    source: pose_pb2.PoseSearchRegion, transform: ImageTransform
) -> pose_pb2.PoseSearchRegion:
    x, y, width, height = transform.source_region_to_output(
        source.x_px, source.y_px, source.width_px, source.height_px
    )
    return pose_pb2.PoseSearchRegion(x_px=x, y_px=y, width_px=width, height_px=height)


def _reference_for_transform(
    source: pose_pb2.SubjectReferenceSettings, transform: ImageTransform
) -> pose_pb2.SubjectReferenceSettings:
    result = pose_pb2.SubjectReferenceSettings()
    result.CopyFrom(source)
    result.image_width_px = transform.output_width
    result.image_height_px = transform.output_height
    for name in ("anterior", "posterior", "medial_left", "medial_right"):
        point = getattr(result, name)
        if point.HasField("x_px") and point.HasField("y_px"):
            point.x_px, point.y_px = transform.source_to_output(
                (point.x_px, point.y_px)
            )
    return result


def _validate_source_reference(
    reference: pose_pb2.SubjectReferenceSettings, source_layout: ImageLayout
) -> None:
    dimensions = validate_reference(reference)
    if dimensions != (source_layout.width, source_layout.height):
        raise ValueError("subject reference dimensions differ from the acquired source")


def _validate_flow_grid(
    layout: ImageLayout,
    flow: FlowSettings,
    estimator: WaterFlowSettings | None,
    *,
    minimum_neighbors: int = 0,
) -> None:
    columns = (layout.width + flow.output_grid_px - 1) // flow.output_grid_px
    rows = (layout.height + flow.output_grid_px - 1) // flow.output_grid_px
    if estimator is not None:
        minimum_neighbors = max(minimum_neighbors, estimator.quality.minimum_neighbors)
    if min(columns, rows) < 2 or columns * rows <= minimum_neighbors:
        raise ValueError(
            "preprocessed image is too small for the selected flow grid and neighbour minimum"
        )


def _pose_settings_for_transform(
    settings: ContourSettings | ModelSettings, transform: ImageTransform
) -> ContourSettings | ModelSettings:
    quality = settings.geometry_quality.model_copy(
        update={
            "minimum_axis_px": settings.geometry_quality.minimum_axis_px
            * min(transform.scale_x, transform.scale_y),
            "minimum_base_width_px": settings.geometry_quality.minimum_base_width_px
            * min(transform.scale_x, transform.scale_y),
            "minimum_triangle_area_px2": settings.geometry_quality.minimum_triangle_area_px2
            * transform.scale_x
            * transform.scale_y,
        }
    )
    updates: dict[str, Any] = {"geometry_quality": quality}
    if isinstance(settings, ContourSettings):
        updates.update(
            minimum_area_px2=max(
                1,
                math.ceil(
                    settings.minimum_area_px2 * transform.scale_x * transform.scale_y
                ),
            ),
            maximum_area_px2=max(
                1,
                math.floor(
                    settings.maximum_area_px2 * transform.scale_x * transform.scale_y
                ),
            ),
        )
        if updates["minimum_area_px2"] > updates["maximum_area_px2"]:
            raise ValueError("contour area range is empty after preprocessing")
    return settings.model_copy(update=updates)


def _source_candidates(
    candidates: tuple[PoseCandidate, ...],
    transform: ImageTransform,
    layout: ImageLayout,
    settings: ContourSettings | ModelSettings,
) -> tuple[PoseCandidate, ...]:
    normalized = tuple(
        PoseCandidate(
            candidate.component_id,
            candidate.score,
            (
                transform.output_to_source(candidate.landmarks[0]),
                transform.output_to_source(candidate.landmarks[1]),
                transform.output_to_source(candidate.landmarks[2]),
            ),
        )
        for candidate in candidates
    )
    return tuple(
        candidate
        for candidate in normalized
        if qualified(candidate, layout.width, layout.height, settings.geometry_quality)
    )
