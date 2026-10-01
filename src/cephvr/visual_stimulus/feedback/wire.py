"""Strict adapter for the existing A06 FeedbackEntry protobuf contract."""

from __future__ import annotations

import math
from typing import Literal

from cephvr.visual_stimulus.feedback.consumer import FeedbackResult
from cephvr.visual_stimulus.v1 import data_pb2 as wire


def decode_entry(
    entry: wire.FeedbackEntry,
    *,
    attachment_generation: str,
) -> FeedbackResult:
    """Convert one bounded pipe message without repairing missing identities."""
    if not entry.HasField("result") or not entry.HasField("entry_sequence"):
        raise ValueError("feedback entry requires result and positive entry_sequence")
    if entry.entry_sequence == 0:
        raise ValueError("feedback entry_sequence must be positive")
    result = entry.result
    if not result.HasField("source") or not result.HasField("work"):
        raise ValueError("feedback result requires source and exact trial work")
    if result.source.role != "tracking" or not result.source.generation:
        raise ValueError("feedback source must be an exact tracking process generation")
    if result.work.WhichOneof("work") != "trial" or not result.work.trial.trial_id:
        raise ValueError("feedback result work must name the released trial")
    if not result.stream_id or not result.result_id or result.result_sequence == 0:
        raise ValueError("feedback stream/result identities and sequence are required")
    generation = _canonical_generation(result.reset_generation)
    if result.source_host_receipt_ns <= 0:
        raise ValueError("feedback source host receipt time must be positive")
    interval_start = (
        result.interval_start_ns if result.HasField("interval_start_ns") else None
    )
    interval_end = (
        result.interval_end_ns if result.HasField("interval_end_ns") else None
    )
    if result.validity == wire.FEEDBACK_VALIDITY_VALID:
        validity: Literal["valid", "baseline_only", "invalid"] = "valid"
    elif result.validity == wire.FEEDBACK_VALIDITY_BASELINE_ONLY:
        validity = "baseline_only"
    elif result.validity == wire.FEEDBACK_VALIDITY_INVALID:
        validity = "invalid"
    else:
        raise ValueError("feedback validity is unspecified or unsupported")
    values = tuple((item.channel_id, float(item.value)) for item in result.values)
    if any(not channel or not math.isfinite(value) for channel, value in values):
        raise ValueError("feedback channels must be named and finite")
    if len({channel for channel, _ in values}) != len(values):
        raise ValueError("feedback result repeats a channel")
    source_frame_ids = tuple(result.source_frame_ids)
    if any(not frame_id for frame_id in source_frame_ids) or len(
        set(source_frame_ids)
    ) != len(source_frame_ids):
        raise ValueError("feedback source frame IDs must be named and unique")
    if validity == "valid" and not source_frame_ids:
        raise ValueError("valid feedback requires its contributing source frame IDs")
    if (
        result.newest_source_frame_id
        and source_frame_ids
        and result.newest_source_frame_id not in source_frame_ids
    ):
        raise ValueError("newest feedback frame must be in its contributing frames")
    return FeedbackResult(
        trial_id=result.work.trial.trial_id,
        stream_id=result.stream_id,
        reset_generation=generation,
        result_sequence=result.result_sequence,
        source_host_receipt_ns=result.source_host_receipt_ns,
        source_interval_start_ns=interval_start,
        source_interval_end_ns=interval_end,
        validity=validity,
        values=values,
        result_id=result.result_id,
        attachment_generation=attachment_generation,
        entry_sequence=entry.entry_sequence,
        source_role=result.source.role,
        source_generation=result.source.generation,
        source_frame_ids=source_frame_ids,
    )


def _canonical_generation(value: str) -> str:
    if (
        not value
        or not value.isascii()
        or not value.isdecimal()
        or value.startswith("0")
    ):
        raise ValueError("feedback reset_generation must be canonical positive decimal")
    if int(value) > (1 << 64) - 1:
        raise ValueError("feedback reset_generation exceeds uint64")
    return value
