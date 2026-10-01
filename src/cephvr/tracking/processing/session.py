"""Setup-time concrete method assembly on the single movement owner."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from cephvr.acquisition.v1.messages_pb2 import FrameBufferAttachment
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.clock import host_time_ns
from cephvr.tracking.config.annotations import manual
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
from cephvr.tracking.methods.contour import ContourPose
from cephvr.tracking.methods.geometry import EllipseGeometry
from cephvr.tracking.methods.model import ModelPose
from cephvr.tracking.methods.nvidia import NvidiaFlow
from cephvr.tracking.methods.proxy import FlowProxy
from cephvr.tracking.processing.gate import TrialGate
from cephvr.tracking.processing.history import PoseHistory
from cephvr.tracking.processing.movement import Movement, MovementPorts
from cephvr.tracking.processing.pose import PoseOperations, PoseWorker
from cephvr.tracking.processing.source import RingSource
from cephvr.tracking.types import ImageLayout, PrivateFrame, SamplingGeometry
from cephvr.tracking.v1.methods_pb2 import TrackingFilePolicies


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
        self.source = RingSource(frames, spec.identity, source_limit)
        self.source.open(spec.identity)
        layout = self.source.layout
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
        self.flow.prepare(flow, layout, flow_limits)
        self.estimator.prepare(
            estimator, layout, self.flow.grid_mapping(), estimate_limits
        )
        if spec.settings.pose_mode == pb.TRACKING_POSE_MODE_MANUAL:
            if (
                spec.settings.manual_pose.image_width_px,
                spec.settings.manual_pose.image_height_px,
            ) != (layout.width, layout.height):
                raise ValueError("manual geometry dimensions differ from bound source")
            self.geometry.prepare(shape, layout, geometry_limits)
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
                    pose_settings, ContourSettings
                ):
                    self.pose_method.prepare(
                        pose_settings,
                        layout,
                        spec.settings.pose_search_region,
                        spec.settings.subject_reference,
                        spec.asset_root,
                        pose_limits,
                    )
                elif isinstance(self.pose_method, ModelPose) and isinstance(
                    pose_settings, ModelSettings
                ):
                    if pose_settings.device_ordinal != flow.device_ordinal:
                        raise ValueError(
                            "pose and flow must adopt the same physical GPU"
                        )
                    self.pose_method.prepare(
                        pose_settings,
                        layout,
                        spec.settings.pose_search_region,
                        spec.settings.subject_reference,
                        spec.asset_root,
                        pose_limits,
                    )
                self.pose_geometry.prepare(shape, layout, geometry_limits)
                return PoseOperations(
                    self.pose_method.compute,
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
                timeout=max(0, (spec.deadline - host_time_ns()) / 1e9)
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
            )
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
