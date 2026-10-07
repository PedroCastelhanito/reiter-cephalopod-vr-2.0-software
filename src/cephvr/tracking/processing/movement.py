"""T08 ordered movement execution and record-before-feedback commit."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import uuid4

from cephvr.control.v1.types_pb2 import ProcessIdentity, WorkContext
from cephvr.shared.clock import host_time_ns
from cephvr.tracking.config.models.methods import FlowSettings
from cephvr.tracking.config.models.records import (
    FlowProxyEvidence,
    PoseUse,
)
from cephvr.tracking.feedback.delivery import FeedbackDelivery
from cephvr.tracking.methods.proxy import FlowProxy
from cephvr.tracking.processing.frames import FramePool
from cephvr.tracking.processing.gate import TrialGate
from cephvr.tracking.processing.history import PoseHistory
from cephvr.tracking.processing.pose import PoseWorker
from cephvr.tracking.recording.results import movement_record
from cephvr.tracking.types import (
    FlowLease,
    FlowMethod,
    FlowProxyInput,
    PoseGeometryObservation,
    PrivateFrame,
    SamplingGeometry,
)
from cephvr.visual_stimulus.v1 import data_pb2 as feedback

InputResetCause = Literal["input_overflow", "input_age", "camera_gap"]


class SourcePort(Protocol):
    pool: FramePool

    def read(
        self, work: WorkContext, generation: str
    ) -> tuple[PrivateFrame | None, bool]: ...
    def latest(self) -> None: ...
    def begin(self) -> None: ...


@dataclass(frozen=True)
class MovementPorts:
    source: SourcePort
    flow: FlowMethod[FlowSettings]
    estimator: FlowProxy
    gate: TrialGate
    history: PoseHistory
    pose: PoseWorker | None
    manual_geometry: SamplingGeometry | None
    feedback: FeedbackDelivery | None
    identity: ProcessIdentity
    stream_id: str
    maximum_frame_age_ns: int
    maximum_pose_age_ns: int
    movement_timeout_ns: int
    first_evaluation: Callable[[PrivateFrame, str, int], None]


class Movement:
    def __init__(
        self, ports: MovementPorts, *, clock: Callable[[], int] = host_time_ns
    ) -> None:
        self.ports, self.clock = ports, clock
        self.baseline: PrivateFrame | None = None
        self.inflight: FlowLease | None = None
        self.current: PrivateFrame | None = None
        self.pending_since_ns: int | None = None
        self.last_completion_ns: int | None = None
        self.result_sequence = 0
        self.first = False

    def run(self) -> None:
        p = self.ports
        p.source.begin()
        self.first = False
        while True:
            with p.gate.lock:
                now = self.clock()
                if p.gate.cutoff is not None or now >= p.gate.end:
                    p.gate.seal(now)
                    break
                generation = p.gate.processing_generation
                work = WorkContext.FromString(p.gate.work.SerializeToString())
            if p.pose is not None and p.pose.failure is not None:
                raise RuntimeError("automatic pose worker failed") from p.pose.failure
            frame, gap = p.source.read(work, generation)
            if gap:
                self._discard_input(frame, "input_overflow", now)
                continue
            if frame is None:
                time.sleep(0.001)
                continue
            now = self.clock()
            if now < frame.source.host_receipt_ns:
                p.source.pool.release(frame)
                raise ValueError("negative source frame age")
            if frame.source.host_receipt_ns < p.gate.start:
                p.source.pool.release(frame)
                continue
            if now - frame.source.host_receipt_ns > p.maximum_frame_age_ns:
                self._discard_input(frame, "input_age", now)
                continue
            if (
                self.baseline is not None
                and frame.source.frame_id != self.baseline.source.frame_id + 1
            ):
                self._discard_input(frame, "camera_gap", now)
                continue
            self.current = frame
            with p.gate.lock:
                admitted = p.gate.accepts(frame.work, frame.source.host_receipt_ns, now)
            if not admitted:
                p.gate.discard((str(frame.source.frame_id),), "trial_cutoff", now)
                p.source.pool.release(frame)
                self.current = None
                continue
            if p.pose is not None:
                p.pose.offer(frame)
            self.pending_since_ns = now
            deadline = now + p.movement_timeout_ns
            if self.baseline is None:
                if not p.flow.establish_baseline(frame, deadline):
                    raise TimeoutError("native baseline completion deadline expired")
                evidence = None
                use, observation = self._pose(frame)
                if observation is not None:
                    p.history.release(observation)
                disposition = "baseline_only"
            else:
                self.inflight = p.flow.compute_pair(self.baseline, frame)
                if not p.flow.wait_complete(self.inflight, deadline):
                    raise TimeoutError(
                        "native flow/readback completion deadline expired"
                    )
                use, observation = self._pose(frame)
                try:
                    geometry = (
                        p.manual_geometry
                        if p.manual_geometry is not None
                        else None
                        if observation is None
                        else observation.geometry
                    )
                    evidence = p.estimator.compute(
                        FlowProxyInput(
                            frame.work,
                            frame.reset_generation,
                            self.inflight,
                            p.flow.host_view(self.inflight),
                            p.flow.grid_mapping(),
                            use,
                            geometry,
                            transform=frame.transform,
                        )
                    )
                finally:
                    if observation is not None:
                        p.history.release(observation)
                disposition = evidence.validity
                p.flow.release(self.inflight)
                self.inflight = None
            self.last_completion_ns = self.clock()
            self.pending_since_ns = None
            self._commit(frame, evidence, disposition, use)
            if self.baseline is not None:
                p.source.pool.release(self.baseline)
            self.baseline, self.current = frame, None
        if p.pose is not None:
            p.pose.retire_waiting()
        if p.feedback is not None:
            p.feedback.seal(self.clock())

    def reconcile(self, deadline: int) -> bool:
        p = self.ports
        if self.inflight is not None:
            if not p.flow.wait_complete(self.inflight, deadline):
                return False
            p.flow.release(self.inflight)
            self.inflight = None
        elif self.current is not None and self.baseline is None:
            if not p.flow.establish_baseline(self.current, deadline):
                return False
        if self.current is not None:
            p.gate.discard(
                (str(self.current.source.frame_id),), "trial_cutoff", self.clock()
            )
            p.source.pool.release(self.current)
            self.current = None
        if self.baseline is not None:
            p.source.pool.release(self.baseline)
            self.baseline = None
        if p.pose is not None:
            p.pose.retire_waiting()
            while not p.pose.idle() and self.clock() < deadline:
                time.sleep(0.001)
            if not p.pose.idle():
                return False
        p.history.clear()
        return p.source.pool.idle()

    def _discard_input(
        self, frame: PrivateFrame | None, cause: InputResetCause, now: int
    ) -> None:
        p = self.ports
        if frame is not None:
            p.gate.discard((str(frame.source.frame_id),), cause, now)
            p.source.pool.release(frame)
        self._reset(cause, now)
        p.source.latest()

    def _reset(self, cause: InputResetCause, now: int) -> None:
        p = self.ports
        with p.gate.lock:
            if p.feedback is not None:
                p.feedback.retire(now, cause)
            generation = p.gate.reset((cause,), now)
        p.flow.reset(generation)
        p.estimator.reset(generation)
        if self.baseline is not None:
            p.source.pool.release(self.baseline)
            self.baseline = None

    def _pose(
        self, frame: PrivateFrame
    ) -> tuple[PoseUse, PoseGeometryObservation | None]:
        p = self.ports
        now = self.clock()
        if p.manual_geometry is not None:
            return PoseUse(
                disposition="manual",
                observation_id=None,
                manual_geometry_id=p.manual_geometry.binding_id,
                check_host_ns=now,
                pose_source_host_ns=None,
                age_ns=None,
                maximum_age_ns=None,
            ), None
        return p.history.select(
            frame.work,
            p.gate.preparation,
            p.gate.attachment,
            frame.source.frame_id,
            now,
            p.maximum_pose_age_ns,
        )

    def _commit(
        self,
        frame: PrivateFrame,
        evidence: FlowProxyEvidence | None,
        disposition: str,
        use: PoseUse,
    ) -> None:
        p = self.ports
        now = self.clock()
        with p.gate.lock:
            if (
                not p.gate.accepts(frame.work, frame.source.host_receipt_ns, now)
                or frame.reset_generation != p.gate.processing_generation
            ):
                p.gate.discard((str(frame.source.frame_id),), "trial_cutoff", now)
                return
            if p.feedback is not None:
                p.feedback.before_result(now)
            self.result_sequence += 1
            if self.result_sequence > 2**64 - 1:
                raise OverflowError("tracking result sequence exhausted")
            result = feedback.FeedbackResult(
                source=p.identity,
                work=frame.work,
                stream_id=p.stream_id,
                reset_generation=str(p.gate.delivery_generation),
                result_id=str(uuid4()),
                result_sequence=self.result_sequence,
                newest_source_frame_id=str(frame.source.frame_id),
                source_host_receipt_ns=frame.source.host_receipt_ns,
                source_frame_ids=[str(frame.source.frame_id)]
                if self.baseline is None
                else [str(self.baseline.source.frame_id), str(frame.source.frame_id)],
                validity={
                    "baseline_only": feedback.FEEDBACK_VALIDITY_BASELINE_ONLY,
                    "valid": feedback.FEEDBACK_VALIDITY_VALID,
                    "invalid": feedback.FEEDBACK_VALIDITY_INVALID,
                }[disposition],
                reason="baseline" if evidence is None else evidence.reason or "",
            )
            if self.baseline is not None:
                result.interval_start_ns = self.baseline.source.host_receipt_ns
                result.interval_end_ns = frame.source.host_receipt_ns
            if evidence is not None and evidence.filtered_average is not None:
                for name, value in evidence.filtered_average.model_dump().items():
                    result.values.add(channel_id=name, value=value)
            p.gate.record(
                movement_record(
                    result, produced_host_ns=now, pose=use, evidence=evidence
                )
            )
            if p.feedback is not None:
                p.feedback.publish(result)
            if not self.first:
                self.first = True
                p.first_evaluation(frame, disposition, now)
