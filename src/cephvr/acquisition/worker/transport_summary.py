"""One-shot comparable camera transport-counter summary for Finished (A07)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from cephvr.acquisition.camera.types import CameraAdapter, TransportCounters
from cephvr.acquisition.worker.warnings import WarningOccurrence
from cephvr.shared.clock import host_time_ns

TRANSPORT_COUNTER_FIELDS = (
    "buffer_underruns",
    "failed_buffers",
    "missed_frames",
    "resend_requests",
    "resend_packets",
    "resynchronizations",
)


@dataclass(frozen=True, slots=True)
class TransportSummary:
    observed_ns: int
    counters: dict[str, int | None]


def collect_transport_summary(
    adapter: CameraAdapter,
    start: TransportCounters | None,
    warning_occurrence: Callable[[WarningOccurrence], None],
    *,
    clock_ns: Callable[[], int] = host_time_ns,
) -> TransportSummary:
    try:
        current = adapter.read_transport_counters()
    except BaseException:
        current = None
    result: dict[str, int | None] = {}
    for field in TRANSPORT_COUNTER_FIELDS:
        first = getattr(start, field) if start is not None else None
        last = getattr(current, field) if current is not None else None
        result[field] = (
            last - first
            if isinstance(first, int) and isinstance(last, int) and last >= first
            else None
        )
    observed_ns = clock_ns()
    if any(value is None for value in result.values()):
        warning_occurrence(
            WarningOccurrence(
                "TRANSPORT_COUNTERS_UNAVAILABLE",
                observed_ns,
                details="one or more SDK transport counters are unavailable or noncomparable",
            )
        )
    return TransportSummary(observed_ns, result)
