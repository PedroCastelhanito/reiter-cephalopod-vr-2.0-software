"""Bounded per-recording warning groups shared by lifecycle and frame log."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from cephvr.acquisition.buffers.records import FrameDiagnostic, FrameRecord
from cephvr.acquisition.recording.session_contracts import (
    RecordingFailure,
    WarningOccurrence,
)


@dataclass
class _Group:
    count: int
    first_ns: int
    last_ns: int
    first_frame_id: int | None
    first_details: str


class RecordingDiagnostics:
    """Aggregate no more than eight stable codes, preserving first detail."""

    _CODES = frozenset(
        {
            "INVALID_IMAGE",
            "NATIVE_COUNTER_GAP",
            "NATIVE_COUNTER_DISCONTINUITY",
            "NATIVE_TIMESTAMP_UNAVAILABLE",
            "NATIVE_COUNTER_UNAVAILABLE",
            "TRANSPORT_COUNTERS_UNAVAILABLE",
            "NO_VIDEO_FRAMES",
        }
    )

    def __init__(self, warning_occurrence: WarningOccurrence) -> None:
        self.warning_occurrence = warning_occurrence
        self._groups: OrderedDict[str, _Group] = OrderedDict()

    def record_frame(self, record: FrameRecord, diagnostic: FrameDiagnostic) -> None:
        details = diagnostic.details
        if diagnostic.code == "INVALID_IMAGE":
            details = details or "invalid SDK image"
        self.record(
            diagnostic.code,
            native_code=diagnostic.native_code,
            details=details,
            observed_ns=record.acquisition_time_ns,
            frame_id=record.frame_id,
        )

    def record(
        self,
        code: str,
        *,
        native_code: str | None,
        details: str | None,
        observed_ns: int,
        frame_id: int | None,
    ) -> None:
        if code not in self._CODES or len(code.encode("utf-8")) > 64:
            raise RecordingFailure(
                "recording received an unknown stable diagnostic code"
            )
        detail = (f"sdk_code={native_code}; " if native_code is not None else "") + (
            details or ""
        )
        group = self._groups.get(code)
        if group is None:
            if len(self._groups) >= 8:
                raise RecordingFailure(
                    "recording diagnostic catalogue capacity exceeded"
                )
            group = _Group(1, observed_ns, observed_ns, frame_id, detail)
            self._groups[code] = group
        else:
            if group.count >= 2**63 - 1:
                raise RecordingFailure("recording diagnostic count overflowed int64")
            group.count += 1
            group.last_ns = observed_ns
        self.warning_occurrence(code, native_code, details, observed_ns, frame_id)

    def frame_log_groups(self) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "code": code,
                "count": item.count,
                "first_observed_monotonic_ns": item.first_ns,
                "last_observed_monotonic_ns": item.last_ns,
                "first_frame_id": item.first_frame_id,
                "details": item.first_details,
            }
            for code, item in self._groups.items()
        )

    def contains(self, code: str) -> bool:
        return code in self._groups
