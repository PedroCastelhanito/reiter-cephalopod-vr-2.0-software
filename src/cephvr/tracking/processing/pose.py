"""T08/T09 one automatic pose job plus a replaceable waiting frame."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from cephvr.shared.clock import host_time_ns
from cephvr.tracking.config.models.records import (
    Point,
    PoseObservation,
    TrackingRecord,
    Triplet,
)
from cephvr.tracking.methods.landmarks import select
from cephvr.tracking.processing.frames import FramePool
from cephvr.tracking.processing.gate import TrialGate
from cephvr.tracking.processing.history import PoseHistory
from cephvr.tracking.types import (
    PoseCandidate,
    PoseGeometryObservation,
    PrivateFrame,
    SamplingGeometry,
)


@dataclass(frozen=True)
class PoseOperations:
    compute: Callable[[PrivateFrame], tuple[PoseCandidate, ...]]
    geometry: Callable[[Triplet], SamplingGeometry | None]
    release_geometry: Callable[[SamplingGeometry], None]
    close: Callable[[int], bool]
    method: str


@dataclass(frozen=True)
class _Job:
    frame: PrivateFrame
    preparation: str
    attachment: str


class PoseWorker:
    def __init__(
        self,
        factory: Callable[[], PoseOperations],
        pool: FramePool,
        history: PoseHistory,
        gate: TrialGate,
        *,
        failure_close: Callable[[int], bool],
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.factory, self.pool, self.history, self.gate, self.clock = (
            factory,
            pool,
            history,
            gate,
            clock,
        )
        self.failure_close = failure_close
        self.condition = threading.Condition()
        self.waiting: _Job | None = None
        self.running = False
        self.pending_since_ns: int | None = None
        self.last_completion_ns: int | None = None
        self.stopping = False
        self.close_deadline = 0
        self.closed = False
        self.failure: BaseException | None = None
        self.ready: Future[None] = Future()
        self.thread = threading.Thread(
            target=self._run, name="tracking-pose", daemon=False
        )
        self.thread.start()

    def offer(self, frame: PrivateFrame) -> None:
        with self.gate.lock:
            if not self.gate.accepts(
                frame.work, frame.source.host_receipt_ns, self.clock()
            ):
                return
            with self.condition:
                if self.stopping or self.failure is not None:
                    raise RuntimeError("pose worker cannot admit another frame")
                self.pool.retain(frame)
                if self.waiting is not None:
                    self.pool.release(self.waiting.frame)
                self.waiting = _Job(frame, self.gate.preparation, self.gate.attachment)
                self.condition.notify()

    def retire_waiting(self) -> None:
        with self.condition:
            if self.waiting is not None:
                self.pool.release(self.waiting.frame)
                self.waiting = None
            self.condition.notify()

    def idle(self) -> bool:
        with self.condition:
            return not self.running and self.waiting is None

    def close(self, deadline: int) -> bool:
        self.retire_waiting()
        self.history.clear()
        with self.condition:
            self.close_deadline = (
                deadline
                if not self.close_deadline
                else min(deadline, self.close_deadline)
            )
            self.stopping = True
            self.condition.notify()
        self.thread.join(max(0, (deadline - self.clock()) / 1e9))
        return self.closed and not self.thread.is_alive()

    def _run(self) -> None:
        operations: PoseOperations | None = None
        try:
            operations = self.factory()
            self.ready.set_result(None)
            while True:
                self._release_retired(operations)
                with self.condition:
                    if self.waiting is None and not self.stopping:
                        self.condition.wait(0.05)
                        continue
                    if self.stopping and self.waiting is None:
                        break
                    job, self.waiting = self.waiting, None
                    self.running = True
                    self.pending_since_ns = self.clock()
                assert job is not None
                try:
                    self._compute(operations, job)
                    self.last_completion_ns = self.clock()
                finally:
                    self.pool.release(job.frame)
                    with self.condition:
                        self.running = False
                        self.pending_since_ns = None
            self._release_retired(operations)
            self.closed = operations.close(self.close_deadline)
        except BaseException as exc:
            self.failure = exc
            if not self.ready.done():
                self.ready.set_exception(exc)
            # Native ownership stays in the failed owner until explicit close reconciliation.
            with self.condition:
                while not self.stopping:
                    self.condition.wait(0.05)
            try:
                if operations is not None:
                    self.history.clear()
                    self._release_retired(operations)
                    self.closed = operations.close(self.close_deadline)
                else:
                    self.closed = self.failure_close(self.close_deadline)
            except BaseException:
                self.closed = False

    def _release_retired(self, operations: PoseOperations) -> None:
        """Release unborrowed geometry on its owning pose thread."""
        for value in self.history.take_retired():
            if value.geometry is not None:
                operations.release_geometry(value.geometry)

    def _compute(self, operations: PoseOperations, job: _Job) -> None:
        frame = job.frame
        candidates = operations.compute(frame)
        selected, tie = select(candidates)
        landmarks = (
            None
            if selected is None
            else Triplet(
                **{
                    name: Point(x_px=xy[0], y_px=xy[1])
                    for name, xy in zip(
                        ("tip", "left_base", "right_base"),
                        selected.landmarks,
                        strict=True,
                    )
                }
            )
        )
        geometry = None if landmarks is None else operations.geometry(landmarks)
        if geometry is None:
            landmarks, selected, tie = None, None, False
        now = self.clock()
        with self.gate.lock:
            compatible = (
                frame.work == self.gate.work
                and job.preparation == self.gate.preparation
                and job.attachment == self.gate.attachment
            )
            disposition: Literal[
                "published", "cutoff_excluded", "retired_generation"
            ] = (
                "retired_generation"
                if not compatible
                else "cutoff_excluded"
                if not self.gate.accepts(frame.work, frame.source.host_receipt_ns, now)
                else "published"
            )
            observed = PoseObservation(
                kind="pose",
                observation_id=str(uuid4()),
                reset_generation=frame.reset_generation,
                source=frame.source,
                completion_host_ns=now,
                method=operations.method,
                validity="valid" if selected else "invalid",
                reason=None if selected else "no_qualified_geometry",
                landmarks=landmarks,
                eligible_candidate_count=len(candidates) if selected else 0,
                selected_score=selected.score if selected else None,
                top_score_tie=tie,
                disposition=disposition,
            )
            try:
                self.gate.record(TrackingRecord(record=observed))
                if disposition == "published":
                    self.history.publish(
                        PoseGeometryObservation(
                            frame.work,
                            job.preparation,
                            job.attachment,
                            observed,
                            geometry,
                        )
                    )
                    geometry = None
            finally:
                if geometry is not None:
                    operations.release_geometry(geometry)
