"""A06 exact credits and bounded immutable transport entries."""

from __future__ import annotations

import threading
from collections import deque

from cephvr.tracking.processing.gate import TrialGate
from cephvr.visual_stimulus.feedback.credits import FeedbackCredits
from cephvr.visual_stimulus.v1 import data_pb2 as pb


class FeedbackDelivery:
    def __init__(
        self,
        attachment: str,
        stream: str,
        capacity: int,
        maximum_bytes: int,
        gate: TrialGate,
    ) -> None:
        self.gate = gate
        self.condition = threading.Condition(gate.lock)
        self.credits = FeedbackCredits(
            attachment_generation=attachment, stream_id=stream, capacity=capacity
        )
        self.maximum_bytes = maximum_bytes
        self.pending: deque[pb.FeedbackEntry] = deque()
        self.inflight: pb.FeedbackEntry | None = None
        self.sequence = 0
        self.sealed = False

    def before_result(self, now: int) -> None:
        """Before constructing evidence: reset delivery only when current budget is full."""
        with self.gate.lock:
            if self.credits.available == 0:
                self.retire(now, "result_overflow")
                self.gate.reset(("result_overflow",), now)

    def publish(self, result: pb.FeedbackResult) -> None:
        with self.condition:
            if self.sealed or result.reset_generation != str(
                self.gate.delivery_generation
            ):
                raise ValueError("publication is sealed or generation is stale")
            if self.sequence == 2**64 - 1:
                raise OverflowError("feedback entry sequence exhausted")
            self.sequence += 1
            entry = pb.FeedbackEntry(entry_sequence=self.sequence, result=result)
            if entry.ByteSize() > self.maximum_bytes:
                raise ValueError("feedback message exceeds prepared bound")
            if len(self.pending) >= self.credits.capacity:
                raise BufferError("physical feedback storage exhausted")
            self.credits.capture(
                reset_generation=result.reset_generation, entry_sequence=self.sequence
            )
            self.pending.append(entry)
            self.condition.notify()

    def take(self, timeout: float) -> pb.FeedbackEntry | None:
        with self.condition:
            if self.inflight is not None:
                raise ValueError("previous write still owns its storage")
            if not self.pending and not self.sealed:
                self.condition.wait(timeout)
            if not self.pending:
                return None
            self.inflight = self.pending.popleft()
            return self.inflight

    def written(self, entry: pb.FeedbackEntry) -> None:
        with self.condition:
            if self.inflight is not entry:
                raise ValueError("unknown native write completion")
            self.inflight = None

    def credit(self, credit: pb.FeedbackCredit) -> bool:
        with self.condition:
            return self.credits.return_credit(credit)

    def retire(self, now: int, reason: str) -> None:
        with self.condition:
            ids = tuple(entry.result.result_id for entry in self.pending)
            self.pending.clear()
            if ids:
                self.gate.discard(ids, reason, now, result=True)  # type: ignore[arg-type]
            # The in-flight immutable payload remains owned until its native write completes.

    def seal(self, now: int) -> None:
        with self.condition:
            self.sealed = True
            self.retire(now, "trial_cutoff")
            self.condition.notify_all()

    def begin(self) -> None:
        with self.condition:
            if self.pending or self.inflight is not None:
                raise ValueError("prior feedback transport remains active")
            self.sealed = False
