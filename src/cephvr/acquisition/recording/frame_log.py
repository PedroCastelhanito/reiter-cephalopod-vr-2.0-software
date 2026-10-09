"""Append-only A07 JSONL writer with explicit Windows storage synchronization."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import BinaryIO, Protocol, cast

from cephvr.acquisition.buffers.records import FrameRecord
from cephvr.acquisition.recording.identity import (
    RecordingIdentity,
    header_clocks,
)
from cephvr.shared.ffmpeg_encoding_rules import _format_rate
from cephvr.shared.nominal_video_grid import NominalVideoGrid

FRAME_LOG_SCHEMA_VERSION = 3

FRAME_LOG_FIELDS = {
    "header": ("type", "schema_version", "identity", "clocks", "video"),
    "header.identity": (
        "session_id",
        "trial_id",
        "trial_number",
        "camera_role",
        "device_id",
        "session_config_reference",
        "recording_identity_version",
    ),
    "header.clocks": (
        "host_clock",
        "timestamp_unit",
        "trial_start_monotonic_ns",
        "camera_clock",
        "camera_clock_source",
        "camera_clock_conversion_available",
        "camera_clock_tick_ns_numerator",
        "camera_clock_tick_ns_denominator",
        "camera_clock_timestamp_semantics",
        "camera_clock_reset_semantics",
        "camera_clock_wrap_semantics",
        "camera_clock_unavailable_reason",
        "camera_counter_source",
        "camera_counter_semantics",
        "camera_counter_width_bits",
        "camera_counter_wrap_semantics",
        "camera_counter_unavailable_reason",
    ),
    "header.video": ("nominal_frame_rate_hz", "nominal_rate_source"),
    "frame": (
        "type",
        "frame_id",
        "host_receipt_ns",
        "dropped",
        "video_frame",
        "video_disposition",
        "camera_frame_counter",
        "camera_timestamp_ns",
        "invalid_code",
    ),
    "video_frame": (
        "type",
        "encoded_frame_index",
        "nominal_slot",
        "source_frame_id",
        "source_host_receipt_ns",
        "disposition",
    ),
    "completion": (
        "type",
        "outcome",
        "timing",
        "video",
        "pulses",
        "post_cutoff",
        "transport_summary",
        "diagnostics",
    ),
    "completion.timing": (
        "recording_end_monotonic_ns",
        "first_recorded_frame_id",
        "final_received_frame_count",
        "accounting_complete",
    ),
    "completion.video": (
        "recorded_frame_count",
        "selected_source_frame_count",
        "duplicate_frame_count",
    ),
    "completion.pulses": (
        "on_outcome",
        "on_dispatched_monotonic_ns",
        "on_acknowledged_monotonic_ns",
        "off_outcome",
        "off_dispatched_monotonic_ns",
        "off_acknowledged_monotonic_ns",
    ),
    "completion.post_cutoff": (
        "accounting_complete",
        "excluded_frame_count",
        "last_native_counter",
    ),
    "completion.transport_summary": (
        "buffer_underruns",
        "failed_buffers",
        "missed_frames",
        "resend_requests",
        "resend_packets",
        "resynchronizations",
    ),
    "completion.diagnostics": (
        "code",
        "count",
        "first_observed_monotonic_ns",
        "last_observed_monotonic_ns",
        "first_frame_id",
        "details",
    ),
}


class FileSync(Protocol):
    def sync(self, file_object: object) -> None: ...


@dataclass(frozen=True)
class FrameLogCompletion:
    outcome: str
    recording_end_monotonic_ns: int | None
    final_received_frame_count: int | None
    accounting_complete: bool
    recorded_frame_count: int
    selected_source_frame_count: int
    duplicate_frame_count: int
    on_outcome: str | None
    on_dispatched_monotonic_ns: int | None
    on_acknowledged_monotonic_ns: int | None
    off_outcome: str | None
    off_dispatched_monotonic_ns: int | None
    off_acknowledged_monotonic_ns: int | None
    post_cutoff_accounting_complete: bool
    excluded_frame_count: int | None
    last_native_counter: int | None
    transport_summary: dict[str, int | None] | None
    diagnostics: tuple[dict[str, object], ...] = ()


class FrameLogWriter:
    """Own one JSONL file and advance its line/frame counters only after writes."""

    def __init__(
        self,
        path: Path,
        identity: RecordingIdentity,
        *,
        start_ns: int,
        nominal_frame_rate_hz: float,
        nominal_rate_source: str,
        sync_interval_ns: int,
        syncer: FileSync,
    ) -> None:
        if start_ns < 0 or sync_interval_ns <= 0:
            raise ValueError("invalid recording start or frame-log sync interval")
        if nominal_frame_rate_hz <= 0:
            raise ValueError("nominal video rate must be positive")
        if nominal_rate_source not in {"applied_mcu_rate", "free_running_frame_rate"}:
            raise ValueError("unsupported nominal frame-rate source")
        identity.validate()
        self.path = Path(path)
        self.identity = identity
        self.start_ns = start_ns
        self.sync_interval_ns = sync_interval_ns
        self.syncer = syncer
        self.file: BinaryIO | None = None
        self.last_sync_ns = start_ns
        self.line_count = 0
        self.frame_count = 0
        self.first_recorded_frame_id: int | None = None
        self._last_frame_id = -1
        self._closed = False
        self._completion_appended = False
        self._completion_attempted = False
        self._nominal_rate_source = nominal_rate_source
        self.video_grid = NominalVideoGrid(
            start_ns, Fraction(_format_rate(nominal_frame_rate_hz))
        )
        self._nominal_rate = float(self.video_grid.rate)
        self.next_video_slot = 0
        self.last_video_source: tuple[int, int] | None = None
        self.selected_source_count = 0
        self.duplicate_count = 0

    def create(self) -> None:
        if self.file is not None or self._closed:
            raise RuntimeError("frame log has already been created or closed")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("xb", buffering=64 * 1024)
        self._append(
            {
                "type": "header",
                "schema_version": FRAME_LOG_SCHEMA_VERSION,
                "identity": self.identity.header_identity(),
                "clocks": header_clocks(self.identity, self.start_ns),
                "video": {
                    "nominal_frame_rate_hz": self._nominal_rate,
                    "nominal_rate_source": self._nominal_rate_source,
                },
            }
        )

    def append_frame(
        self,
        record: FrameRecord,
        *,
        dropped: bool,
        video_frame: int | None = None,
        video_disposition: str | None = None,
    ) -> int | None:
        if self.file is None or self._closed:
            raise RuntimeError("frame log is not open")
        if self._completion_attempted:
            raise RuntimeError("frame line cannot follow the terminal completion line")
        frame_id = record.frame_id
        if frame_id != self._last_frame_id + 1:
            raise ValueError("frame IDs are not contiguous and ordered")
        invalid = not record.valid_image
        final_dropped = bool(dropped or invalid)
        if final_dropped and video_frame is not None:
            raise ValueError("dropped source frames cannot map to encoded slots")
        if not final_dropped and video_frame is None:
            raise ValueError("selected source frame requires a nominal video slot")
        values: dict[str, object] = {
            "type": "frame",
            "frame_id": frame_id,
            "host_receipt_ns": record.acquisition_time_ns,
            "dropped": final_dropped,
            "video_frame": video_frame,
            "video_disposition": video_disposition,
            "camera_frame_counter": record.camera_frame_counter,
            "camera_timestamp_ns": record.camera_timestamp_ns,
            "invalid_code": record.invalid_code if invalid else None,
        }
        self._append(values)
        self._last_frame_id = frame_id
        if not final_dropped:
            if self.first_recorded_frame_id is None:
                self.first_recorded_frame_id = frame_id
            self.selected_source_count += 1
        return video_frame

    def append_video_frame(
        self,
        *,
        slot: int,
        source_frame_id: int,
        source_host_receipt_ns: int,
        disposition: str,
    ) -> None:
        if slot != self.frame_count or slot != self.next_video_slot:
            raise ValueError("encoded video slots must be contiguous and ordered")
        if disposition not in {
            "real",
            "leading_duplicate",
            "interior_duplicate",
            "trailing_duplicate",
        }:
            raise ValueError("unsupported encoded-frame disposition")
        self._append(
            {
                "type": "video_frame",
                "encoded_frame_index": slot,
                "nominal_slot": slot,
                "source_frame_id": source_frame_id,
                "source_host_receipt_ns": source_host_receipt_ns,
                "disposition": disposition,
            }
        )
        self.frame_count += 1
        if disposition != "real":
            self.duplicate_count += 1
        self.next_video_slot += 1
        self.last_video_source = (source_frame_id, source_host_receipt_ns)

    def append_completion(self, completion: FrameLogCompletion) -> None:
        if self.file is None or self._closed:
            raise RuntimeError("frame log is not open")
        if self._completion_attempted:
            raise RuntimeError("frame-log completion line may be appended exactly once")
        if completion.outcome not in {"completed", "interrupted"}:
            raise ValueError("invalid recording outcome")
        if (
            completion.recorded_frame_count != self.frame_count
            or completion.selected_source_frame_count != self.selected_source_count
            or completion.duplicate_frame_count != self.duplicate_count
        ):
            raise ValueError(
                "completion video count differs from online frame-log accounting"
            )
        if completion.final_received_frame_count is not None and (
            completion.final_received_frame_count != self._last_frame_id + 1
            or not completion.accounting_complete
        ):
            raise ValueError(
                "complete frame accounting differs from contiguous logged IDs"
            )
        if (
            completion.accounting_complete
            and completion.final_received_frame_count is None
        ):
            raise ValueError("complete frame accounting requires a known final count")
        diagnostics = [
            self._bounded_diagnostic(item) for item in completion.diagnostics
        ]
        self._completion_attempted = True
        self._append(
            {
                "type": "completion",
                "outcome": completion.outcome,
                "timing": {
                    "recording_end_monotonic_ns": completion.recording_end_monotonic_ns,
                    "first_recorded_frame_id": self.first_recorded_frame_id,
                    "final_received_frame_count": completion.final_received_frame_count,
                    "accounting_complete": completion.accounting_complete,
                },
                "video": {
                    "recorded_frame_count": completion.recorded_frame_count,
                    "selected_source_frame_count": completion.selected_source_frame_count,
                    "duplicate_frame_count": completion.duplicate_frame_count,
                },
                "pulses": {
                    "on_outcome": completion.on_outcome,
                    "on_dispatched_monotonic_ns": completion.on_dispatched_monotonic_ns,
                    "on_acknowledged_monotonic_ns": completion.on_acknowledged_monotonic_ns,
                    "off_outcome": completion.off_outcome,
                    "off_dispatched_monotonic_ns": completion.off_dispatched_monotonic_ns,
                    "off_acknowledged_monotonic_ns": completion.off_acknowledged_monotonic_ns,
                },
                "post_cutoff": {
                    "accounting_complete": completion.post_cutoff_accounting_complete,
                    "excluded_frame_count": completion.excluded_frame_count,
                    "last_native_counter": completion.last_native_counter,
                },
                "transport_summary": completion.transport_summary,
                "diagnostics": diagnostics,
            }
        )
        self._completion_appended = True

    def close(self) -> None:
        if self.file is None or self._closed:
            raise RuntimeError("frame log is not open")
        if not self._completion_appended:
            raise RuntimeError("frame-log close requires its single completion line")
        self._close_storage()

    def close_failed(self) -> None:
        """Release a failed output without claiming a terminal row was written."""
        if self.file is None or self._closed:
            return
        self._close_storage()

    def _close_storage(self) -> None:
        """Flush and sync before closing; leave ownership intact on failures."""
        assert self.file is not None
        self.file.flush()
        self.syncer.sync(self.file)
        self.file.close()
        self._closed = True

    def sync_if_due(self, now_ns: int) -> bool:
        if self.file is None or self._closed:
            return False
        if now_ns - self.last_sync_ns < self.sync_interval_ns:
            return False
        self._sync(now_ns=now_ns)
        return True

    def _append(self, value: dict[str, object]) -> None:
        if self.file is None:
            raise RuntimeError("frame log has not been created")
        line_type = value.get("type")
        line_fields = FRAME_LOG_FIELDS.get(str(line_type))
        if line_fields is None or set(value) != set(line_fields):
            raise ValueError("frame-log line differs from the declared writer schema")
        for prefix in (
            "header.identity",
            "header.clocks",
            "header.video",
            "completion.timing",
            "completion.video",
            "completion.pulses",
            "completion.post_cutoff",
        ):
            if prefix.startswith(f"{line_type}."):
                nested: dict[str, object] = value
                for component in prefix.split(".")[1:]:
                    nested = cast(dict[str, object], nested[component])
                if set(nested) != set(FRAME_LOG_FIELDS[prefix]):
                    raise ValueError(
                        f"frame-log {prefix} differs from the declared schema"
                    )
        if line_type == "completion":
            summary = cast(dict[str, object] | None, value["transport_summary"])
            if summary is not None and set(summary) != set(
                FRAME_LOG_FIELDS["completion.transport_summary"]
            ):
                raise ValueError(
                    "frame-log transport summary differs from the declared schema"
                )
            if any(
                set(item) != set(FRAME_LOG_FIELDS["completion.diagnostics"])
                for item in cast(list[dict[str, object]], value["diagnostics"])
            ):
                raise ValueError(
                    "frame-log diagnostic differs from the declared schema"
                )
        line = (
            json.dumps(
                value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ).encode("utf-8")
            + b"\n"
        )
        written = self.file.write(line)
        if written != len(line):
            raise OSError("frame-log append was incomplete")
        self.line_count += 1

    def _sync(self, *, now_ns: int | None = None) -> None:
        if self.file is None or self._closed:
            raise RuntimeError("frame log is not open")
        self.file.flush()
        self.syncer.sync(self.file)
        self.last_sync_ns = time.perf_counter_ns() if now_ns is None else now_ns

    @staticmethod
    def _bounded_diagnostic(item: dict[str, object]) -> dict[str, object]:
        if set(item) != set(FRAME_LOG_FIELDS["completion.diagnostics"]):
            raise ValueError("diagnostic fields differ from A07's grouped schema")
        code = str(item["code"])
        if len(code.encode("utf-8")) > 64:
            raise ValueError("diagnostic code exceeds A07's 64-byte limit")
        details = str(item.get("details", ""))
        suffix = " [truncated]"
        encoded = details.encode("utf-8")
        if len(encoded) > 1024:
            limit = 1024 - len(suffix.encode("utf-8"))
            details = encoded[:limit].decode("utf-8", "ignore") + suffix
        result = dict(item)
        result["code"] = code
        result["details"] = details
        if int(cast(int, result["count"])) <= 0:
            raise ValueError("diagnostic count must be positive")
        return result
