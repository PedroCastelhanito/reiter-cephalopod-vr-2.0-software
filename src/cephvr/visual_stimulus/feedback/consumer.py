"""Ordered A06/V24–V27 feedback admission, freshness and local hold semantics."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class FeedbackResult:
    trial_id: str
    stream_id: str
    reset_generation: int | str
    result_sequence: int
    source_host_receipt_ns: int
    source_interval_start_ns: int | None
    source_interval_end_ns: int | None
    validity: Literal["valid", "baseline_only", "invalid"]
    values: tuple[tuple[str, float], ...]
    result_id: str = ""
    attachment_generation: str = ""
    entry_sequence: int = 0
    source_role: str = ""
    source_generation: str = ""
    source_frame_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FeedbackDisposition:
    result_id: str
    result_sequence: int
    disposition: Literal[
        "applied", "baseline", "invalid", "stale", "wrong_trial", "old_generation"
    ]
    age_ns: int | None
    reason: str | None = None


class FeedbackTarget(Protocol):
    def apply(
        self, result: FeedbackResult, values: dict[str, float], now_ns: int
    ) -> None: ...


class FeedbackConsumer:
    """Consumes a finite ordered batch; it never retains rejected movement."""

    def __init__(
        self,
        *,
        max_result_age_ns: int,
        clock_ns: Callable[[], int],
        target: FeedbackTarget,
        attachment_generation: str | None = None,
        stream_id: str | None = None,
        stream_ids: frozenset[str] | None = None,
        source_generation: str | None = None,
    ) -> None:
        if max_result_age_ns <= 0:
            raise ValueError("max_result_age_ns must be positive")
        self.max_result_age_ns = max_result_age_ns
        self._clock_ns = clock_ns
        self._target = target
        self._attachment_generation = attachment_generation
        self._stream_id = stream_id
        self._stream_ids = stream_ids
        self._source_generation = source_generation
        self._trial_id: str | None = None
        self._generation = 0
        self._last_sequence = 0

    def begin_trial(self, trial_id: str) -> None:
        if not trial_id:
            raise ValueError("trial identity is required")
        self._trial_id = trial_id
        self._generation = 0
        self._last_sequence = 0

    def consume(
        self, batch: tuple[FeedbackResult, ...]
    ) -> tuple[FeedbackDisposition, ...]:
        dispositions: list[FeedbackDisposition] = []
        last = (0, 0)
        for result in batch:
            generation = _generation_number(result.reset_generation)
            identity = (generation, result.result_sequence)
            if identity <= last:
                raise ValueError(
                    "feedback batch must be strictly ordered by generation and sequence"
                )
            last = identity
            if result.trial_id != self._trial_id:
                dispositions.append(
                    FeedbackDisposition(
                        result.result_id,
                        result.result_sequence,
                        "wrong_trial",
                        None,
                        "trial mismatch",
                    )
                )
                continue
            if (
                self._attachment_generation is not None
                and result.attachment_generation != self._attachment_generation
            ):
                dispositions.append(
                    FeedbackDisposition(
                        result.result_id,
                        result.result_sequence,
                        "old_generation",
                        None,
                        "attachment generation mismatch",
                    )
                )
                continue
            if (
                self._stream_id is not None and result.stream_id != self._stream_id
            ) or (
                self._stream_ids is not None
                and result.stream_id not in self._stream_ids
            ):
                dispositions.append(
                    FeedbackDisposition(
                        result.result_id,
                        result.result_sequence,
                        "invalid",
                        None,
                        "feedback stream mismatch",
                    )
                )
                continue
            if (
                self._source_generation is not None
                and result.source_generation != self._source_generation
            ):
                dispositions.append(
                    FeedbackDisposition(
                        result.result_id,
                        result.result_sequence,
                        "invalid",
                        None,
                        "feedback source generation mismatch",
                    )
                )
                continue
            if generation < self._generation:
                dispositions.append(
                    FeedbackDisposition(
                        result.result_id,
                        result.result_sequence,
                        "old_generation",
                        None,
                        "retired reset generation",
                    )
                )
                continue
            if generation > self._generation:
                self._generation = generation
                self._last_sequence = 0
            if result.result_sequence <= self._last_sequence:
                raise ValueError("feedback result sequence did not increase")
            self._last_sequence = result.result_sequence
            if result.validity == "baseline_only":
                dispositions.append(
                    FeedbackDisposition(
                        result.result_id, result.result_sequence, "baseline", None
                    )
                )
                continue
            if result.validity != "valid":
                dispositions.append(
                    FeedbackDisposition(
                        result.result_id,
                        result.result_sequence,
                        "invalid",
                        None,
                        "producer marked input invalid",
                    )
                )
                continue
            if result.source_host_receipt_ns <= 0:
                raise ValueError("valid feedback requires source host receipt time")
            check_ns = self._clock_ns()
            age = check_ns - result.source_host_receipt_ns
            if age < 0:
                raise ValueError(
                    "feedback source receipt is later than application check"
                )
            if age > self.max_result_age_ns:
                dispositions.append(
                    FeedbackDisposition(
                        result.result_id,
                        result.result_sequence,
                        "stale",
                        age,
                        "age limit exceeded",
                    )
                )
                continue
            start, end = result.source_interval_start_ns, result.source_interval_end_ns
            if start is not None or end is not None:
                if start is None or end is None or start < 0 or end <= start:
                    raise ValueError(
                        "feedback interval must be a positive half-open source interval"
                    )
            values = dict(result.values)
            if len(values) != len(result.values) or any(
                not math.isfinite(v) for v in values.values()
            ):
                raise ValueError("feedback channels must be unique and finite")
            self._target.apply(result, values, check_ns)
            dispositions.append(
                FeedbackDisposition(
                    result.result_id, result.result_sequence, "applied", age
                )
            )
        return tuple(dispositions)


def _generation_number(value: int | str) -> int:
    if type(value) is int:
        if value <= 0:
            raise ValueError("feedback reset generation must be positive")
        return value
    if not isinstance(value, str):
        raise ValueError("feedback reset generation must be decimal")
    if (
        not value
        or not value.isascii()
        or not value.isdecimal()
        or value.startswith("0")
    ):
        raise ValueError("feedback reset generation must be canonical positive decimal")
    parsed = int(value)
    if parsed > (1 << 64) - 1:
        raise ValueError("feedback reset generation exceeds uint64")
    return parsed
