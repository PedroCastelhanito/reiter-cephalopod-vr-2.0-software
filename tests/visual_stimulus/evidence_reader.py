"""Test-only reader for the V13 experiment-output contract; no rendering/export."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from cephvr.visual_stimulus.config.models.evidence_model import (
    Clipping,
    Completion,
    EvidenceRecord,
    GroupUpdate,
    Header,
    RenderGroup,
    Submission,
    parse_evidence_json,
)

Payload: TypeAlias = object


class EvidenceValidationError(ValueError):
    """The evidence file cannot support the requested reconstruction."""


@dataclass(frozen=True)
class EvidenceFile:
    header: Header
    groups: tuple[RenderGroup, ...]
    completion: Completion | None
    records: tuple[EvidenceRecord, ...]
    discarded_partial_tail: bool
    clippings: dict[tuple[int, str], Clipping]

    @property
    def last_group_id(self) -> int | None:
        return self.groups[-1].group_id if self.groups else None


def read_evidence(path: Path, *, max_line_bytes: int) -> EvidenceFile:
    if max_line_bytes <= 0:
        raise ValueError("max_line_bytes must be positive")
    records: list[EvidenceRecord] = []
    incomplete_tail = False
    try:
        stream = Path(path).open("rb")
    except OSError as exc:
        raise EvidenceValidationError(
            f"evidence file cannot be opened: {path}"
        ) from exc
    with stream:
        number = 0
        while line := stream.readline(max_line_bytes + 1):
            number += 1
            if len(line) > max_line_bytes:
                raise EvidenceValidationError(
                    f"evidence line {number} exceeds max_line_bytes"
                )
            if not line.endswith(b"\n"):
                incomplete_tail = True
                break
            try:
                records.append(
                    parse_evidence_json(
                        line[:-1].decode("utf-8"), max_bytes=max_line_bytes
                    )
                )
            except (UnicodeDecodeError, ValueError) as exc:
                raise EvidenceValidationError(
                    f"invalid evidence line {number}: {exc}"
                ) from exc
    if not records or not isinstance(records[0].payload, Header):
        raise EvidenceValidationError("evidence must begin with exactly one Header")
    header = records[0].payload
    groups: list[RenderGroup] = []
    group_map: dict[int, RenderGroup] = {}
    completion: Completion | None = None
    attempts: dict[str, int] = {}
    outcomes: dict[tuple[int, str], Submission] = {}
    pending: dict[tuple[int, str], Submission] = {}
    clippings: dict[tuple[int, str], Clipping] = {}
    required_outputs = set(header.required_output_ids)
    for index, record in enumerate(records[1:], start=2):
        payload = record.payload
        if completion is not None:
            raise EvidenceValidationError(f"line {index} follows Completion")
        if isinstance(payload, Header):
            raise EvidenceValidationError("evidence contains more than one Header")
        if isinstance(payload, RenderGroup):
            expected = len(groups)
            if payload.group_id != expected:
                raise EvidenceValidationError(
                    "render group IDs must begin at zero without gaps"
                )
            if payload.state.evaluation_host_ns < header.trial_start_host_ns:
                raise EvidenceValidationError("render state precedes trial start")
            if (
                groups
                and payload.state.evaluation_host_ns
                < groups[-1].state.evaluation_host_ns
            ):
                raise EvidenceValidationError(
                    "render state times must be nondecreasing"
                )
            group_map[payload.group_id] = payload
            groups.append(payload)
            _apply_submissions(
                payload.group_id, payload.submissions, attempts, outcomes, pending
            )
        elif isinstance(payload, GroupUpdate):
            if payload.group_id not in group_map:
                raise EvidenceValidationError(
                    "GroupUpdate refers to a group not yet written"
                )
            _apply_submissions(
                payload.group_id, payload.submissions, attempts, outcomes, pending
            )
        elif isinstance(payload, Clipping):
            group = group_map.get(payload.group_id)
            if group is None:
                raise EvidenceValidationError(
                    "Clipping refers to a render group not yet written"
                )
            if payload.output_id not in required_outputs:
                raise EvidenceValidationError(
                    "Clipping refers to an output absent from the evidence Header"
                )
            if (
                payload.occurrence_index != group.state.epoch_occurrence
                or payload.observation_host_ns != group.state.evaluation_host_ns
            ):
                raise EvidenceValidationError(
                    "Clipping epoch or timestamp differs from its render group"
                )
            key = (payload.group_id, payload.output_id)
            if key in clippings:
                raise EvidenceValidationError(
                    "render group/output has duplicate Clipping evidence"
                )
            clippings[key] = payload
        elif isinstance(payload, Completion):
            completion = payload
            if payload.last_group_id != (groups[-1].group_id if groups else None):
                raise EvidenceValidationError(
                    "Completion last_group_id does not match evidence"
                )
            if payload.state_count != len(groups):
                raise EvidenceValidationError(
                    "Completion state_count does not match evidence"
                )
            if payload.unresolved_attempt_count != len(pending):
                raise EvidenceValidationError(
                    "Completion unresolved attempt count does not reconcile"
                )
        # Feedback, intervals and encoder outcome have their own model-level checks;
        # references are verified where the corresponding immutable group is known.
    if completion is not None and completion is not records[-1].payload:
        raise EvidenceValidationError("Completion must be the final evidence record")
    return EvidenceFile(
        header, tuple(groups), completion, tuple(records), incomplete_tail, clippings
    )


def _apply_submissions(
    group_id: int,
    submissions: tuple[Submission, ...],
    attempts: dict[str, int],
    outcomes: dict[tuple[int, str], Submission],
    pending: dict[tuple[int, str], Submission],
) -> None:
    seen: set[str] = set()
    for item in submissions:
        output_id = item.output_id
        if output_id in seen:
            raise EvidenceValidationError(
                "a group has more than one submission observation per output"
            )
        seen.add(output_id)
        key = (group_id, output_id)
        if item.phase == "cutoff_excluded":
            continue
        assert item.attempt_index is not None
        if key in outcomes:
            raise EvidenceValidationError(
                "submission outcome was resolved more than once"
            )
        if item.phase == "attempt":
            if key in pending:
                raise EvidenceValidationError(
                    "submission attempt was declared more than once"
                )
            expected = attempts.get(output_id, 0)
            if item.attempt_index != expected:
                raise EvidenceValidationError(
                    "per-output attempt indices must increase from zero"
                )
            attempts[output_id] = expected + 1
            pending[key] = item
            continue
        expected = attempts.get(output_id, 0)
        prior = pending.get(key)
        if prior is not None:
            if (
                prior.attempt_index != item.attempt_index
                or prior.entry_host_ns != item.entry_host_ns
            ):
                raise EvidenceValidationError(
                    "GroupUpdate changed a pending attempt identity"
                )
            del pending[key]
        else:
            if item.attempt_index != expected:
                raise EvidenceValidationError(
                    "per-output attempt indices must increase from zero"
                )
            attempts[output_id] = expected + 1
        outcomes[key] = item
