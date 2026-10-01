"""T08/A06 single atomic publication/reset/cutoff owner."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Literal

from cephvr.control.v1.types_pb2 import WorkContext
from cephvr.tracking.config.models.records import (
    Discard,
    Reset,
    ResetCause,
    TrackingRecord,
)


class TrialGate:
    def __init__(self, admit: Callable[[TrackingRecord], bool]) -> None:
        self.lock = threading.RLock()
        self.admit = admit
        self.work = WorkContext()
        self.preparation = ""
        self.attachment = ""
        self.delivery_generation = 0
        self.processing_generation = ""
        self.start = 0
        self.end = 0
        self.cutoff: int | None = 0

    def begin(
        self,
        work: WorkContext,
        preparation: str,
        attachment: str,
        start: int,
        end: int,
        now: int,
    ) -> None:
        with self.lock:
            if self.cutoff is None or end <= start:
                raise ValueError("previous trial must be sealed and interval valid")
            self.work.CopyFrom(work)
            self.preparation, self.attachment = preparation, attachment
            self.start, self.end, self.cutoff = start, end, None
            self.reset(("trial_start",), now)

    def reset(self, causes: tuple[ResetCause, ...], now: int) -> str:
        with self.lock:
            generation = self.delivery_generation + 1
            if generation > 2**64 - 1:
                raise OverflowError("feedback generation exhausted")
            self.record(
                TrackingRecord(
                    record=Reset(
                        kind="reset",
                        reset_generation=str(generation),
                        causes=causes,
                        observed_host_ns=now,
                    )
                )
            )
            self.delivery_generation = generation
            if causes != ("result_overflow",):
                self.processing_generation = str(generation)
            return str(generation)

    def seal(self, now: int) -> int:
        with self.lock:
            if self.cutoff is None:
                self.cutoff = min(now, self.end)
            return self.cutoff

    def accepts(self, work: WorkContext, source_ns: int, now: int) -> bool:
        return (
            self.work == work
            and self.cutoff is None
            and self.start <= source_ns < self.end
            and now < self.end
        )

    def record(self, record: TrackingRecord) -> None:
        if not self.admit(record):
            raise RuntimeError("required tracking evidence admission failed")

    def discard(
        self,
        ids: tuple[str, ...],
        reason: Literal[
            "camera_gap",
            "input_age",
            "input_overflow",
            "result_overflow",
            "retired_generation",
            "trial_cutoff",
        ],
        now: int,
        *,
        result: bool = False,
    ) -> None:
        if ids:
            self.record(
                TrackingRecord(
                    record=Discard(
                        kind="discard",
                        reset_generation=str(self.delivery_generation),
                        observed_host_ns=now,
                        target="result" if result else "source_frame",
                        ids=ids,
                        reason=reason,
                    )
                )
            )
