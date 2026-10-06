"""Bounded worker-owned acquisition warning views (A09)."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from uuid import uuid4

from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control

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
_LIMIT = 8


@dataclass(frozen=True, slots=True)
class WarningOccurrence:
    code: str
    observed_ns: int
    native_code: str | None = None
    details: str = ""


class WorkerWarningLedger:
    """Keeps only the current and most recently completed work warning views.

    Callers enqueue returned complete views onto their report executor; this class
    never performs RPC or retains per-occurrence history.
    """

    def __init__(self, source: acq.WorkerContext) -> None:
        self._source = _copy_context(source)
        self._lock = RLock()
        self._revision = 0
        self._current: control.AcquisitionWarningView | None = None
        self._latest: control.AcquisitionWarningView | None = None
        self._unavailable: set[str] = set()

    def begin_scope(
        self,
        work: control.WorkContext,
        *,
        configuration_revision: int | None = None,
        preview_run_id: str | None = None,
    ) -> control.AcquisitionWarningView:
        with self._lock:
            self._latest = None
            self._unavailable.clear()
            self._current = self._empty_view(
                work, configuration_revision, preview_run_id
            )
            self._revision += 1
            self._current.warning_revision = self._revision
            return _copy_view(self._current)

    def observe(self, occurrence: WarningOccurrence) -> control.AcquisitionWarningView:
        if occurrence.code not in _CODES:
            raise ValueError(
                f"unsupported acquisition warning code {occurrence.code!r}"
            )
        if occurrence.observed_ns <= 0:
            raise ValueError("warning observation time must be positive")
        with self._lock:
            view = self._require_current()
            warning = next(
                (
                    item
                    for item in view.warnings
                    if item.acquisition_occurrence.code == occurrence.code
                ),
                None,
            )
            if warning is None:
                if len(view.warnings) >= _LIMIT:
                    raise RuntimeError("worker warning catalogue capacity exhausted")
                warning = view.warnings.add(
                    warning_id=str(uuid4()),
                    component="acquisition_camera",
                )
                metadata = warning.acquisition_occurrence
                metadata.source.CopyFrom(self._source.worker)
                metadata.work.CopyFrom(view.work)
                metadata.camera = self._source.camera
                if view.HasField("configuration_revision"):
                    metadata.configuration_revision = view.configuration_revision
                if view.HasField("preview_run_id"):
                    metadata.preview_run_id = view.preview_run_id
                metadata.code = occurrence.code
                metadata.count = 0
                metadata.first_observed_monotonic_ns = occurrence.observed_ns
            metadata = warning.acquisition_occurrence
            if metadata.count == (1 << 64) - 1:
                raise OverflowError("worker warning count exhausted uint64")
            if occurrence.observed_ns < metadata.last_observed_monotonic_ns:
                raise ValueError("warning observation time regressed")
            metadata.count += 1
            metadata.last_observed_monotonic_ns = occurrence.observed_ns
            if occurrence.native_code is not None:
                metadata.latest_sdk_code = _truncate_utf8(occurrence.native_code, 64)
            warning.message = _truncate_utf8(occurrence.details, 1024)
            self._revision += 1
            view.warning_revision = self._revision
            return _copy_view(view)

    def observe_unavailability(
        self,
        code: str,
        unavailable: bool,
        observed_ns: int,
        *,
        native_code: str | None = None,
        details: str = "",
    ) -> control.AcquisitionWarningView | None:
        """Count only a transition into absence; a return permits another transition."""
        if code not in {"NATIVE_TIMESTAMP_UNAVAILABLE", "NATIVE_COUNTER_UNAVAILABLE"}:
            raise ValueError(
                "only optional native metadata can use transition tracking"
            )
        with self._lock:
            was_unavailable = code in self._unavailable
            if unavailable:
                self._unavailable.add(code)
            else:
                self._unavailable.discard(code)
        if unavailable and not was_unavailable:
            return self.observe(
                WarningOccurrence(code, observed_ns, native_code, details)
            )
        return None

    def complete_scope(self) -> control.AcquisitionWarningView:
        with self._lock:
            current = self._require_current()
            self._latest = _copy_view(current)
            self._current = None
            self._unavailable.clear()
            return _copy_view(self._latest)

    def views(
        self, work: control.WorkContext | None = None
    ) -> tuple[control.AcquisitionWarningView, ...]:
        with self._lock:
            values = (self._current, self._latest)
            result: list[control.AcquisitionWarningView] = []
            for item in values:
                if item is None:
                    continue
                if work is not None and item.work != work:
                    continue
                result.append(_copy_view(item))
            return tuple(result)

    def _empty_view(
        self,
        work: control.WorkContext,
        configuration_revision: int | None,
        preview_run_id: str | None,
    ) -> control.AcquisitionWarningView:
        result = control.AcquisitionWarningView(
            producer=self._source.worker,
            camera=self._source.camera,
        )
        result.work.CopyFrom(work)
        if configuration_revision is not None:
            if configuration_revision < 0:
                raise ValueError("configuration revision must be nonnegative")
            result.configuration_revision = configuration_revision
        if preview_run_id is not None:
            result.preview_run_id = preview_run_id
        return result

    def _require_current(self) -> control.AcquisitionWarningView:
        if self._current is None:
            raise RuntimeError("worker warning scope is not active")
        return self._current


def _copy_context(value: acq.WorkerContext) -> acq.WorkerContext:
    result = acq.WorkerContext()
    result.CopyFrom(value)
    return result


def _copy_view(value: control.AcquisitionWarningView) -> control.AcquisitionWarningView:
    result = control.AcquisitionWarningView()
    result.CopyFrom(value)
    return result


def _truncate_utf8(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")
    marker = " [truncated]"
    marker_bytes = marker.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    if len(marker_bytes) >= max_bytes:
        return marker[:max_bytes]
    prefix = encoded[: max_bytes - len(marker_bytes)]
    while prefix:
        try:
            return prefix.decode("utf-8") + marker
        except UnicodeDecodeError:
            prefix = prefix[:-1]
    return marker
