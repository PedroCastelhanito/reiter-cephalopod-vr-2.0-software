"""Sessionless selected-stage diagnostics using the native Tracking method owners."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from uuid import UUID, uuid4

from cephvr.control.v1 import types_pb2 as control
from cephvr.control.v1.types_pb2 import ProcessIdentity, WorkContext
from cephvr.shared.clock import host_time_ns
from cephvr.tracking.config.annotations import manual
from cephvr.tracking.config.models.methods import (
    ContourSettings,
    FileLimits,
    ModelSettings,
)
from cephvr.tracking.config.models.records import PoseUse, Triplet
from cephvr.tracking.methods.flow_buffers import host_arrays
from cephvr.tracking.methods.landmarks import select
from cephvr.tracking.methods.screening import screen
from cephvr.tracking.processing.diagnostic_output import (
    diagnostic_frame,
    stage_status,
)
from cephvr.tracking.processing.gate import TrialGate
from cephvr.tracking.processing.session import (
    NativeSession,
    SessionSpec,
    _source_candidates,
)
from cephvr.tracking.types import (
    FlowLease,
    FlowProxyInput,
    HostFlowView,
    PoseCandidate,
    PrivateFrame,
    SamplingGeometry,
)
from cephvr.tracking.v1 import services_pb2 as wire

_status = stage_status


class DiagnosticPipeline:
    """One ordered, no-trial pass through the selected Tracking method owners."""

    def __init__(
        self,
        request: wire.TrackingDiagnosticCommand,
        identity: ProcessIdentity,
        *,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.request = wire.TrackingDiagnosticCommand.FromString(
            request.SerializeToString(deterministic=True)
        )
        self.identity, self.clock = identity, clock
        self.limits = FileLimits.model_validate_json(request.file_policies.limits_json)
        self.resolved: NativeSession | None = None
        self.pose_settings: ContourSettings | ModelSettings | None = None
        self.sequence = 0
        self.baseline: PrivateFrame | None = None
        self.input_frames = self.evaluated_frames = self.lapped_frames = 0
        self.last_duration_ns = self.maximum_duration_ns = 0
        self.status = stage_status(request)
        self.stages = set(request.selected_stages)
        available = {
            stage.stage
            for stage in self.status
            if stage.state == wire.TRACKING_DIAGNOSTIC_STAGE_STATE_AVAILABLE
        }
        self.pose_enabled = wire.TRACKING_DIAGNOSTIC_STAGE_POSE in available
        self.region_enabled = (
            wire.TRACKING_DIAGNOSTIC_STAGE_SAMPLING_REGION in available
        )
        self.flow_enabled = wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW in available
        self.quality_enabled = wire.TRACKING_DIAGNOSTIC_STAGE_FLOW_QUALITY in available
        self.locomotion_enabled = wire.TRACKING_DIAGNOSTIC_STAGE_LOCOMOTION in available

    def prepare(self) -> None:
        spec = SessionSpec(
            settings=self.request.settings,
            policies=self.request.file_policies,
            identity=self.identity,
            preparation=self.request.diagnostic_id,
            revision=self.request.configuration_revision,
            asset_root=(
                self.request.asset_root if self.request.HasField("asset_root") else ""
            ),
            deadline=self.request.deadline_monotonic_ns,
            first=lambda _frame, _disposition, _now: None,
            diagnostic_stages=frozenset(self.request.selected_stages),
        )
        session = NativeSession(spec, TrialGate(lambda _item: True), None)
        self.resolved = session
        session.prepare(self.request.frames)
        if session.source is None:
            raise RuntimeError("Tracking diagnostic source did not prepare")
        resolution = session.diagnostic_resolution
        if resolution is None:
            raise RuntimeError("Tracking diagnostic settings were not resolved")
        self.status = list(resolution.status)
        self.pose_enabled = any(
            item.stage == wire.TRACKING_DIAGNOSTIC_STAGE_POSE
            and item.state == wire.TRACKING_DIAGNOSTIC_STAGE_STATE_AVAILABLE
            for item in self.status
        )
        self.region_enabled = any(
            item.stage == wire.TRACKING_DIAGNOSTIC_STAGE_SAMPLING_REGION
            and item.state == wire.TRACKING_DIAGNOSTIC_STAGE_STATE_AVAILABLE
            for item in self.status
        )
        self.flow_enabled = any(
            item.stage == wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW
            and item.state == wire.TRACKING_DIAGNOSTIC_STAGE_STATE_AVAILABLE
            for item in self.status
        )
        self.quality_enabled = any(
            item.stage == wire.TRACKING_DIAGNOSTIC_STAGE_FLOW_QUALITY
            and item.state == wire.TRACKING_DIAGNOSTIC_STAGE_STATE_AVAILABLE
            for item in self.status
        )
        self.locomotion_enabled = any(
            item.stage == wire.TRACKING_DIAGNOSTIC_STAGE_LOCOMOTION
            and item.state == wire.TRACKING_DIAGNOSTIC_STAGE_STATE_AVAILABLE
            for item in self.status
        )
        pose_settings = next(
            (
                settings
                for definition, settings in resolution.pipeline.stages
                if definition.stage_id == "pose"
            ),
            None,
        )
        if isinstance(pose_settings, (ContourSettings, ModelSettings)):
            self.pose_settings = pose_settings
        self.resolved = session
        self.sequence = 0

    def next_frame(self) -> tuple[wire.TrackingDiagnosticFrame | None, int, int, int]:
        session = self.resolved
        if session is None or session.source is None:
            raise RuntimeError("Tracking diagnostic pipeline is not prepared")
        started = self.clock()
        run_id = UUID(self.request.frames.buffer.preview.acquisition_run_id)
        frame, gap, acquired = session.source.read_run(
            run_id,
            WorkContext(),
            self.request.diagnostic_id,
            copy_acquired=True,
            maximum_acquired_bytes=self.request.maximum_frame_bytes,
        )
        if gap:
            self.lapped_frames += 1
            if self.baseline is not None:
                session.source.pool.release(self.baseline)
                self.baseline = None
            if self.flow_enabled and session.flow.native is not None:
                session.flow.reset(self.request.diagnostic_id)
        if frame is None:
            return None, self.input_frames, self.evaluated_frames, self.lapped_frames
        self.input_frames += 1
        try:
            if acquired is None:
                result = diagnostic_frame(
                    self.request,
                    frame,
                    None,
                    ([], [], [], []),
                    clock=self.clock,
                    maximum_bytes=self.request.maximum_frame_bytes,
                    unavailable_reason="acquired image exceeds the diagnostic frame byte bound",
                )
                return (
                    result,
                    self.input_frames,
                    self.evaluated_frames,
                    self.lapped_frames,
                )
            overlays = self._evaluate(session, frame, started)
            result = diagnostic_frame(
                self.request,
                frame,
                acquired,
                overlays,
                clock=self.clock,
                maximum_bytes=self.request.maximum_frame_bytes,
            )
            self.evaluated_frames += 1
            self.last_duration_ns = max(0, self.clock() - started)
            self.maximum_duration_ns = max(
                self.maximum_duration_ns, self.last_duration_ns
            )
            return result, self.input_frames, self.evaluated_frames, self.lapped_frames
        finally:
            if self.baseline is not frame:
                session.source.pool.release(frame)

    def _evaluate(
        self, session: NativeSession, frame: PrivateFrame, started: int
    ) -> tuple[
        list[tuple[int, str, float, float]],
        list[tuple[int, str, float, float, float, float]],
        list[tuple[int, str, float, float, float, float]],
        list[tuple[int, str]],
    ]:
        assert session.source is not None
        points: list[tuple[int, str, float, float]] = []
        rectangles: list[tuple[int, str, float, float, float, float]] = []
        vectors: list[tuple[int, str, float, float, float, float]] = []
        labels: list[tuple[int, str]] = []
        geometry: SamplingGeometry | None = None
        lease: FlowLease | None = None
        try:
            pose, geometry, pose_use = self._pose(session, frame, points)
            if self.region_enabled and geometry is not None:
                import numpy as np

                outline = np.frombuffer(
                    geometry.outline_xy_px, dtype=np.float64
                ).reshape(-1, 2)
                for start, end in zip(
                    outline, np.roll(outline, -1, axis=0), strict=True
                ):
                    vectors.append(
                        (
                            wire.TRACKING_DIAGNOSTIC_STAGE_SAMPLING_REGION,
                            "sampling region",
                            float(start[0]),
                            float(start[1]),
                            float(end[0]),
                            float(end[1]),
                        )
                    )
            elif self.region_enabled:
                labels.append(
                    (
                        wire.TRACKING_DIAGNOSTIC_STAGE_SAMPLING_REGION,
                        "sampling region unavailable: pose prerequisite is unavailable",
                    )
                )
            if self.flow_enabled:
                flow_data = self._flow(session, frame)
                if flow_data is not None:
                    lease, view = flow_data
                    flow_vectors, cost, validity = host_arrays(lease, view)
                    import numpy as np

                    transformed = (
                        flow_vectors.astype(np.float64) * lease.component_scale
                    )
                    if frame.transform is not None:
                        transformed[..., 0] /= frame.transform.scale_x
                        transformed[..., 1] /= frame.transform.scale_y
                    mapping = session.flow.grid_mapping()
                    samples = np.frombuffer(
                        mapping.sample_xy_px, dtype=np.float64
                    ).reshape(mapping.grid_height, mapping.grid_width, 2)
                    max_items = max(1, self.request.maximum_overlay_items)
                    for row, column in np.ndindex(transformed.shape[:2]):
                        if len(vectors) >= max_items:
                            break
                        x, y = samples[row, column]
                        dx, dy = transformed[row, column]
                        if np.isfinite((x, y, dx, dy)).all():
                            vectors.append(
                                (
                                    wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW,
                                    "displacement (px/frame)",
                                    float(x),
                                    float(y),
                                    float(x + dx),
                                    float(y + dy),
                                )
                            )
                    if self.quality_enabled and geometry is not None:
                        quality_settings = (
                            session.diagnostic_resolution.quality
                            if session.diagnostic_resolution is not None
                            else None
                        )
                        if quality_settings is None:
                            raise RuntimeError("flow quality settings are unavailable")
                        if self.locomotion_enabled:
                            session.estimator.prepare_geometry(geometry)
                            association = session.estimator.association
                        else:
                            from cephvr.tracking.methods.association import associate

                            association = associate(
                                geometry,
                                session.flow.grid_mapping(),
                                session.source.source_layout,
                                quality_settings,
                                max(1, self.limits.max_native_bytes // 2),
                            )
                        if association is None:
                            raise RuntimeError(
                                "flow quality association is unavailable"
                            )
                        selected = (
                            association.area.sum(axis=1).reshape(transformed.shape[:2])
                            > 0
                        )
                        _, counts = screen(
                            transformed,
                            selected,
                            cost,
                            validity,
                            quality_settings.quality,
                            max(1, self.limits.max_native_bytes // 8),
                        )
                        labels.append(
                            (
                                wire.TRACKING_DIAGNOSTIC_STAGE_FLOW_QUALITY,
                                f"flow quality accepted {counts.accepted}/{counts.selected}; unavailable {counts.unavailable}; nonfinite {counts.nonfinite}; cost rejected {counts.cost_rejected}; neighbor rejected {counts.neighbor_unevaluable}; median rejected {counts.median_rejected}",
                            )
                        )
                    elif self.quality_enabled:
                        labels.append(
                            (
                                wire.TRACKING_DIAGNOSTIC_STAGE_FLOW_QUALITY,
                                "flow quality unavailable: sampling region prerequisite is unavailable",
                            )
                        )
                    if (
                        self.locomotion_enabled
                        and session.estimator is not None
                        and geometry is not None
                        and pose_use is not None
                    ):
                        evidence = session.estimator.compute(
                            FlowProxyInput(
                                frame.work,
                                frame.reset_generation,
                                lease,
                                view,
                                session.flow.grid_mapping(),
                                pose_use,
                                geometry,
                                transform=frame.transform,
                            )
                        )
                        labels.append(
                            (
                                wire.TRACKING_DIAGNOSTIC_STAGE_LOCOMOTION,
                                f"locomotion {evidence.validity}: {evidence.reason or 'ready'}",
                            )
                        )
                    if self.baseline is not None:
                        session.source.pool.release(self.baseline)
                    self.baseline = frame
            return points, rectangles, vectors, labels
        finally:
            if lease is not None:
                session.flow.release(lease)
            if geometry is not None and session.pose_geometry is not None:
                session.pose_geometry.release(geometry)

    def _pose(
        self,
        session: NativeSession,
        frame: PrivateFrame,
        points: list[tuple[int, str, float, float]],
    ) -> tuple[PoseCandidate | None, SamplingGeometry | None, PoseUse | None]:
        if not self.pose_enabled:
            return None, None, None
        if self.request.settings.pose_mode == control.TRACKING_POSE_MODE_MANUAL:
            pose = manual(self.request.settings.manual_pose)
            for name in ("tip", "left_base", "right_base"):
                value = getattr(pose, name)
                points.append(
                    (wire.TRACKING_DIAGNOSTIC_STAGE_POSE, name, value.x_px, value.y_px)
                )
            use = (
                PoseUse(
                    disposition="manual",
                    observation_id=None,
                    manual_geometry_id=session.manual_geometry.binding_id,
                    check_host_ns=self.clock(),
                    pose_source_host_ns=None,
                    age_ns=None,
                    maximum_age_ns=None,
                )
                if session.manual_geometry is not None
                else None
            )
            return None, session.manual_geometry, use
        if session.pose_method is None or session.source is None:
            return None, None, None
        candidates = _source_candidates(
            session.pose_method.compute(frame),
            session.source.transform,
            session.source.source_layout,
            self._pose_settings(session),
        )
        selected, _tied = select(candidates)
        if selected is None:
            return (
                None,
                None,
                PoseUse(
                    disposition="missing",
                    observation_id=None,
                    manual_geometry_id=None,
                    check_host_ns=self.clock(),
                    pose_source_host_ns=None,
                    age_ns=None,
                    maximum_age_ns=int(
                        self.request.settings.pose_max_age_ms * 1_000_000
                    ),
                ),
            )
        for name, (x, y) in zip(
            ("tip", "left_base", "right_base"), selected.landmarks, strict=True
        ):
            points.append((wire.TRACKING_DIAGNOSTIC_STAGE_POSE, name, x, y))
        from cephvr.tracking.config.models.records import Point

        triplet = Triplet(
            **{
                name: Point(x_px=xy[0], y_px=xy[1])
                for name, xy in zip(
                    ("tip", "left_base", "right_base"), selected.landmarks, strict=True
                )
            }
        )
        geometry = (
            session.pose_geometry.compute(triplet)
            if session.pose_geometry is not None
            and (self.region_enabled or self.locomotion_enabled)
            else None
        )
        use = PoseUse(
            disposition="valid",
            observation_id=str(uuid4()),
            manual_geometry_id=None,
            check_host_ns=self.clock(),
            pose_source_host_ns=frame.source.host_receipt_ns,
            age_ns=max(0, self.clock() - frame.source.host_receipt_ns),
            maximum_age_ns=int(self.request.settings.pose_max_age_ms * 1_000_000),
        )
        return selected, geometry, use

    def _pose_settings(self, session: NativeSession) -> ContourSettings | ModelSettings:
        del session
        if self.pose_settings is None:
            raise RuntimeError("prepared automatic pose settings are unavailable")
        return self.pose_settings

    def _flow(
        self, session: NativeSession, frame: PrivateFrame
    ) -> tuple[FlowLease, HostFlowView] | None:
        if self.baseline is None:
            if not session.flow.establish_baseline(
                frame,
                self.clock()
                + int(
                    Decimal(str(self.limits.movement_progress_timeout_s))
                    * 1_000_000_000
                ),
            ):
                raise TimeoutError("diagnostic flow baseline deadline expired")
            self.baseline = frame
            return None
        if frame.source.frame_id != self.baseline.source.frame_id + 1:
            assert session.source is not None
            session.source.pool.release(self.baseline)
            self.baseline = None
            session.flow.reset(self.request.diagnostic_id)
            if not session.flow.establish_baseline(
                frame,
                self.clock()
                + int(
                    Decimal(str(self.limits.movement_progress_timeout_s))
                    * 1_000_000_000
                ),
            ):
                raise TimeoutError("diagnostic flow baseline deadline expired")
            self.baseline = frame
            return None
        lease = session.flow.compute_pair(self.baseline, frame)
        if not session.flow.wait_complete(
            lease,
            self.clock()
            + int(
                Decimal(str(self.limits.movement_progress_timeout_s)) * 1_000_000_000
            ),
        ):
            raise TimeoutError("diagnostic optical-flow completion deadline expired")
        return lease, session.flow.host_view(lease)

    def close(self, deadline_ns: int) -> bool:
        if self.resolved is None:
            return True
        if self.resolved.source is not None and self.baseline is not None:
            self.resolved.source.pool.release(self.baseline)
            self.baseline = None
        closed = self.resolved.close(deadline_ns)
        if closed:
            self.resolved = None
        return closed
