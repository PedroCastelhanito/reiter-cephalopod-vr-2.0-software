"""Bounded independent preview-consumer evidence, without start/closure authority."""

from __future__ import annotations

from cephvr.control.v1 import services_pb2 as wire
from cephvr.shared.commands import CommandCapacityError
from cephvr.shared.identity import require_uuid4

PreviewKey = tuple[str, str, str, str, str]


def retain_preview_result(
    records: dict[PreviewKey, tuple[wire.PreviewConsumerReport, ...]],
    report: wire.PreviewConsumerReport,
    *,
    max_entries: int,
    max_bytes: int,
) -> bool:
    """Retain exact failed/released evidence; evict only already released entries."""
    for identity in (
        report.client_id,
        report.controller_generation,
        report.preview_run_id,
        report.allocation_id,
        report.transfer_id,
    ):
        require_uuid4(identity)
    if report.client_id != report.consumer.generation or not report.consumer.role:
        raise ValueError("preview consumer identity differs")
    if report.result not in (
        wire.PREVIEW_CONSUMER_RESULT_FAILED,
        wire.PREVIEW_CONSUMER_RESULT_RELEASED,
    ):
        raise ValueError("only preview failure/release evidence belongs to supervisor")
    key = (
        report.consumer.role,
        report.consumer.generation,
        report.preview_run_id,
        report.allocation_id,
        report.transfer_id,
    )
    old = records.get(key, ())
    prior = next((item for item in old if item.result == report.result), None)
    if prior is not None:
        if prior != report:
            raise ValueError("preview terminal evidence changed payload")
        return False
    candidate = dict(records)
    candidate[key] = (
        *old,
        wire.PreviewConsumerReport.FromString(report.SerializeToString()),
    )
    used_bytes = sum(item.ByteSize() for group in candidate.values() for item in group)
    for retained_key, value in tuple(candidate.items()):
        if len(candidate) <= max_entries and used_bytes <= max_bytes:
            break
        if retained_key != key and any(
            item.result == wire.PREVIEW_CONSUMER_RESULT_RELEASED for item in value
        ):
            used_bytes -= sum(item.ByteSize() for item in value)
            del candidate[retained_key]
    if len(candidate) > max_entries or used_bytes > max_bytes:
        raise CommandCapacityError(
            "required preview-consumer evidence capacity exhausted"
        )
    records.clear()
    records.update(candidate)
    return True
