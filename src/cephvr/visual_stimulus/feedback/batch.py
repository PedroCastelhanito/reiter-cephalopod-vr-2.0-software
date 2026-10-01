"""Application-time coordinator for finite, decoded feedback batches."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from cephvr.visual_stimulus.config.models.program_model import Program
from cephvr.visual_stimulus.feedback.consumer import (
    FeedbackConsumer,
    FeedbackDisposition,
    FeedbackResult,
)
from cephvr.visual_stimulus.feedback.mapping import FeedbackMappingApplier
from cephvr.visual_stimulus.rendering.types import FeedbackEvidenceSnapshot

_EvidenceDisposition = Literal[
    "applied",
    "invalid",
    "stale",
    "old_generation",
    "absent",
    "wrong_trial",
    "baseline_only",
]


class _CurrentRenderTarget:
    def __init__(self, applier: FeedbackMappingApplier) -> None:
        self.applier = applier
        self.context: tuple[Any, Any, int, int] | None = None
        self.applications: list[tuple[FeedbackResult, tuple[Any, ...]]] = []

    def binding_ids(self, epoch: Any, stream_id: str) -> tuple[str, ...]:
        return self.applier.binding_ids(epoch, stream_id)

    def apply(
        self, result: FeedbackResult, values: dict[str, float], now_ns: int
    ) -> None:
        if self.context is None:
            raise RuntimeError("feedback batch has no current render update")
        state, epoch, current_ns, epoch_start_ns = self.context
        _ = values, now_ns
        reports = self.applier((result,), state, epoch, current_ns, epoch_start_ns)
        self.applications.append((result, reports))


class FeedbackBatchConsumer:
    """Freshness-check and map entries against the one current epoch snapshot."""

    def __init__(
        self,
        program: Program,
        *,
        arena_boundaries: Any,
        max_result_age_ns: int,
        clock_ns: Callable[[], int],
        attachment_generation: str,
        stream_ids: frozenset[str],
        source_generation: str,
    ) -> None:
        self._target = _CurrentRenderTarget(
            FeedbackMappingApplier(program, arena_boundaries=arena_boundaries)
        )
        self._consumer = FeedbackConsumer(
            max_result_age_ns=max_result_age_ns,
            clock_ns=clock_ns,
            target=self._target,
            attachment_generation=attachment_generation,
            stream_ids=stream_ids,
            source_generation=source_generation,
        )

    def begin_trial(self, trial_id: str) -> None:
        self._consumer.begin_trial(trial_id)

    def consume(
        self,
        batch: tuple[FeedbackResult, ...],
        trial_state: Any,
        epoch: Any,
        now_ns: int,
        epoch_start_ns: int,
        group_id: int,
    ) -> tuple[FeedbackEvidenceSnapshot, ...]:
        self._target.applications.clear()
        self._target.context = (trial_state, epoch, now_ns, epoch_start_ns)
        try:
            dispositions = self._consumer.consume(batch)
        finally:
            self._target.context = None
        mapped: dict[tuple[int, int], tuple[Any, ...]] = {}
        for result, contributions in self._target.applications:
            mapped[
                (_generation_number(result.reset_generation), result.result_sequence)
            ] = contributions
        snapshots: list[FeedbackEvidenceSnapshot] = []
        for result, disposition in zip(batch, dispositions, strict=True):
            identity = (
                _generation_number(result.reset_generation),
                result.result_sequence,
            )
            disposition_names: dict[str, _EvidenceDisposition] = {
                "applied": "applied",
                "baseline": "baseline_only",
                "invalid": "invalid",
                "stale": "stale",
                "wrong_trial": "wrong_trial",
                "old_generation": "old_generation",
            }
            mapped_disposition = disposition_names[disposition.disposition]
            contributions = mapped.get(identity, ())
            if disposition.disposition == "applied" and not contributions:
                mapped_disposition = "absent"
            if mapped_disposition == "applied":
                for contribution in contributions:
                    snapshots.append(
                        _evidence_snapshot(
                            result,
                            disposition,
                            now_ns=now_ns,
                            age_limit_ns=self._consumer.max_result_age_ns,
                            status="applied",
                            binding_id=contribution.binding_id,
                            group_id=group_id,
                            requested_increment=contribution.requested_increment,
                            applied_increment=contribution.applied_increment,
                            target_units=contribution.target_units,
                            target_frame_id=contribution.target_frame_id,
                            constraint_occurred=contribution.constraint_occurred,
                        )
                    )
            else:
                binding_ids = self._target.binding_ids(epoch, result.stream_id)
                for binding_id in binding_ids or (None,):
                    snapshots.append(
                        _evidence_snapshot(
                            result,
                            disposition,
                            now_ns=now_ns,
                            age_limit_ns=(
                                self._consumer.max_result_age_ns
                                if disposition.disposition in ("applied", "stale")
                                else None
                            ),
                            status=mapped_disposition,
                            binding_id=binding_id,
                            group_id=(
                                group_id if mapped_disposition == "absent" else None
                            ),
                        )
                    )
        return tuple(snapshots)


def _generation_number(value: int | str) -> int:
    return int(value)


def _evidence_snapshot(
    result: FeedbackResult,
    disposition: FeedbackDisposition,
    *,
    now_ns: int,
    age_limit_ns: int | None,
    status: _EvidenceDisposition,
    binding_id: str | None = None,
    group_id: int | None = None,
    requested_increment: tuple[float, ...] = (),
    applied_increment: tuple[float, ...] = (),
    target_units: tuple[str, ...] = (),
    target_frame_id: str | None = None,
    constraint_occurred: bool = False,
) -> FeedbackEvidenceSnapshot:
    application_check_ns = (
        result.source_host_receipt_ns + disposition.age_ns
        if disposition.age_ns is not None
        else now_ns
    )
    return FeedbackEvidenceSnapshot(
        stream_id=result.stream_id,
        result_id=result.result_id,
        reset_generation=str(result.reset_generation),
        binding_id=binding_id,
        group_id=group_id,
        source_frame_ids=result.source_frame_ids,
        source_receipt_ns=result.source_host_receipt_ns,
        application_check_ns=application_check_ns,
        age_limit_ns=age_limit_ns,
        disposition=status,
        requested_increment=requested_increment,
        applied_increment=applied_increment,
        target_units=target_units,
        target_frame_id=target_frame_id,
        constraint_occurred=constraint_occurred,
    )
