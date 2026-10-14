"""Aggregate-only recording file and encoder timing probe for one managed process."""
from __future__ import annotations

import threading
import time
from typing import Any, Callable
from weakref import WeakKeyDictionary


def _metric() -> dict[str, Any]:
    return {
        "count": 0, "errors": 0, "sum_ns": 0, "min_ns": None,
        "max_ns": 0, "success_interval_count": 0,
        "success_interval_sum_ns": 0, "success_interval_min_ns": None,
        "success_interval_max_ns": 0, "last_success_ns": None,
    }


def _record(metric: dict[str, Any], started_ns: int, ended_ns: int, success: bool) -> None:
    duration = max(0, ended_ns - started_ns)
    metric["count"] += 1
    metric["sum_ns"] += duration
    metric["min_ns"] = duration if metric["min_ns"] is None else min(metric["min_ns"], duration)
    metric["max_ns"] = max(metric["max_ns"], duration)
    if not success:
        metric["errors"] += 1
    else:
        previous = metric["last_success_ns"]
        if previous is not None:
            interval = ended_ns - previous
            metric["success_interval_count"] += 1
            metric["success_interval_sum_ns"] += interval
            low = metric["success_interval_min_ns"]
            metric["success_interval_min_ns"] = interval if low is None else min(low, interval)
            metric["success_interval_max_ns"] = max(metric["success_interval_max_ns"], interval)
        metric["last_success_ns"] = ended_ns


def _record_interval(metric: dict[str, Any], interval_ns: int) -> None:
    metric["count"] += 1
    metric["sum_ns"] += interval_ns
    low = metric["min_ns"]
    metric["min_ns"] = interval_ns if low is None else min(low, interval_ns)
    metric["max_ns"] = max(metric["max_ns"], interval_ns)


def install(emit: Callable[..., None], *, acquisition: bool, visual: bool) -> None:
    """Install passive wrappers; all output occurs at sync/close/wait boundaries."""
    tls = threading.local()
    video_states: WeakKeyDictionary[object, dict[str, Any]] = WeakKeyDictionary()

    if acquisition or visual:
        from cephvr.platform.windows.file_sync import WindowsVideoSync

        def video_state(sync: object) -> dict[str, Any]:
            state = video_states.get(sync)
            if state is None:
                state = {
                    "owner_id": id(sync), "configured_sync_interval_ns": None,
                    "actual_video_file_sync": _metric(),
                    "close_operation": _metric(),
                }
                video_states[sync] = state
            return state

        raw_video_sync = WindowsVideoSync.sync
        def observed_video_sync(self):
            state = video_state(self)
            started = time.perf_counter_ns()
            success = False
            try:
                result = raw_video_sync(self)
                success = True
                return result
            finally:
                _record(state["actual_video_file_sync"], started, time.perf_counter_ns(), success)
        WindowsVideoSync.sync = observed_video_sync

        raw_video_close = WindowsVideoSync.close
        def observed_video_close(self):
            state = video_state(self)
            started = time.perf_counter_ns()
            success = False
            try:
                result = raw_video_close(self)
                success = True
                return result
            finally:
                ended = time.perf_counter_ns()
                _record(state["close_operation"], started, ended, success)
                emit("video_file_sync_timing", **dict(state), close_end_ns=ended,
                     close_outcome="returned" if success else "raised")
        WindowsVideoSync.close = observed_video_close

    if acquisition:
        from cephvr.acquisition.recording.frame_log import FrameLogWriter
        from cephvr.acquisition.recording import session_storage
        from cephvr.platform.windows.file_sync import WindowsFrameLogSync, WindowsVideoSync

        frame_states: WeakKeyDictionary[object, dict[str, Any]] = WeakKeyDictionary()
        def frame_state(writer: FrameLogWriter) -> dict[str, Any]:
            state = frame_states.get(writer)
            if state is None:
                state = {
                    "owner_id": id(writer), "sync_interval_ns": writer.sync_interval_ns,
                    "actual_file_sync": _metric(),
                    "writer_sync_operation": _metric(), "close_operation": _metric(),
                    "final_sync_calls": 0, "close_outcome": None,
                }
                frame_states[writer] = state
            return state

        raw_file_sync = WindowsFrameLogSync.sync
        def observed_file_sync(self, file_object):
            started = time.perf_counter_ns()
            success = False
            try:
                result = raw_file_sync(self, file_object)
                success = True
                return result
            finally:
                ended = time.perf_counter_ns()
                state = getattr(tls, "frame_state", None)
                if state is not None:
                    _record(state["actual_file_sync"], started, ended, success)
                    if getattr(tls, "final_frame_sync", False) and success:
                        state["final_sync_calls"] += 1
        WindowsFrameLogSync.sync = observed_file_sync

        raw_writer_sync = FrameLogWriter._sync
        def observed_writer_sync(self, *, now_ns=None):
            state = frame_state(self)
            old_state = getattr(tls, "frame_state", None)
            old_final = getattr(tls, "final_frame_sync", False)
            tls.frame_state = state
            tls.final_frame_sync = False
            started = time.perf_counter_ns()
            success = False
            try:
                result = raw_writer_sync(self, now_ns=now_ns)
                success = True
                return result
            finally:
                _record(state["writer_sync_operation"], started, time.perf_counter_ns(), success)
                tls.frame_state, tls.final_frame_sync = old_state, old_final
        FrameLogWriter._sync = observed_writer_sync

        raw_storage_close = FrameLogWriter._close_storage
        def observed_storage_close(self):
            state = frame_state(self)
            old_state = getattr(tls, "frame_state", None)
            old_final = getattr(tls, "final_frame_sync", False)
            tls.frame_state = state
            tls.final_frame_sync = True
            started = time.perf_counter_ns()
            success = False
            try:
                result = raw_storage_close(self)
                success = True
                return result
            finally:
                ended = time.perf_counter_ns()
                _record(state["close_operation"], started, ended, success)
                state["close_outcome"] = "returned" if success else "raised"
                emit("frame_log_timing", **dict(state), close_end_ns=ended)
                tls.frame_state, tls.final_frame_sync = old_state, old_final
        FrameLogWriter._close_storage = observed_storage_close

        raw_sync_due = session_storage.sync_due
        def observed_sync_due(frame_log, video_sync, last_video_sync_ns,
                              video_sync_interval_ns, now_ns):
            if video_sync is not None:
                state = video_state(video_sync)
                if state["configured_sync_interval_ns"] is None:
                    state["configured_sync_interval_ns"] = video_sync_interval_ns
            return raw_sync_due(frame_log, video_sync, last_video_sync_ns,
                                video_sync_interval_ns, now_ns)
        session_storage.sync_due = observed_sync_due

    if visual:
        from cephvr.visual_stimulus.recording.evidence import EvidenceWriter
        from cephvr.visual_stimulus.recording.encoder_owner import EncoderTrialOwner
        from cephvr.visual_stimulus.recording.session import RecordingSession as VisualRecordingSession

        evidence_states: WeakKeyDictionary[object, dict[str, Any]] = WeakKeyDictionary()

        def evidence_state(writer: EvidenceWriter) -> dict[str, Any]:
            state = evidence_states.get(writer)
            if state is None:
                state = {
                    "owner_id": id(writer), "configured_sync_interval_ns": None,
                    "max_pending_byte_limit": writer.max_pending_bytes,
                    "pending_peak_bytes_observed": 0, "sync_file_call": _metric(),
                    "close_operation": _metric(), "sync_calls": 0,
                    "close_outcome": None,
                }
                evidence_states[writer] = state
            return state

        raw_evidence_init = EvidenceWriter.__init__
        def observed_evidence_init(self, *args, **kwargs):
            raw_evidence_init(self, *args, **kwargs)
            state = evidence_state(self)
            sync_file = self.sync_file
            def timed_sync_file(stream):
                started = time.perf_counter_ns()
                success = False
                try:
                    result = sync_file(stream)
                    success = True
                    return result
                finally:
                    ended = time.perf_counter_ns()
                    _record(state["sync_file_call"], started, ended, success)
                    if success:
                        state["sync_calls"] += 1
            self.sync_file = timed_sync_file
        EvidenceWriter.__init__ = observed_evidence_init

        raw_enqueue = EvidenceWriter.enqueue_json
        def observed_enqueue(self, line):
            state = evidence_state(self)
            # Candidate uses exact accepted line size; concurrent drains may lower the
            # subsequently observed value, so the field is explicitly labeled observed.
            candidate = self._pending_bytes + len(line)
            result = raw_enqueue(self, line)
            state["pending_peak_bytes_observed"] = max(
                int(state["pending_peak_bytes_observed"]), candidate,
                int(self._pending_bytes),
            )
            return result
        EvidenceWriter.enqueue_json = observed_enqueue

        raw_write_pending = EvidenceWriter.write_pending
        def observed_write_pending(self, *, sync=False):
            state = evidence_state(self)
            state["pending_peak_bytes_observed"] = max(
                int(state["pending_peak_bytes_observed"]), int(self._pending_bytes)
            )
            result = raw_write_pending(self, sync=sync)
            state["pending_peak_bytes_observed"] = max(
                int(state["pending_peak_bytes_observed"]), int(self._pending_bytes)
            )
            return result
        EvidenceWriter.write_pending = observed_write_pending

        raw_evidence_close = EvidenceWriter.close
        def observed_evidence_close(self, *, sync=True):
            state = evidence_state(self)
            started = time.perf_counter_ns()
            success = False
            try:
                result = raw_evidence_close(self, sync=sync)
                success = True
                return result
            finally:
                ended = time.perf_counter_ns()
                _record(state["close_operation"], started, ended, success)
                state["close_outcome"] = "returned" if success else "raised"
                emit("visual_evidence_timing", **dict(state), close_end_ns=ended)
        EvidenceWriter.close = observed_evidence_close

        raw_visual_session_init = VisualRecordingSession.__init__
        def observed_visual_session_init(self, *args, **kwargs):
            raw_visual_session_init(self, *args, **kwargs)
            state = evidence_state(self.evidence)
            state["configured_sync_interval_ns"] = self.sync_interval_ns
            state["max_queued_evidence_bytes"] = self.max_queued_evidence_bytes
        VisualRecordingSession.__init__ = observed_visual_session_init

        raw_periodic_sync = EncoderTrialOwner.periodic_sync
        def observed_periodic_sync(self, output_path, *, interval_ns):
            if self.video_sync is not None:
                video_state(self.video_sync)["configured_sync_interval_ns"] = interval_ns
            result = raw_periodic_sync(self, output_path, interval_ns=interval_ns)
            if self.video_sync is not None:
                video_state(self.video_sync)["configured_sync_interval_ns"] = interval_ns
            return result
        EncoderTrialOwner.periodic_sync = observed_periodic_sync

    from cephvr.platform.windows.encoder_process import WindowsEncoderProcess

    encoder_states: WeakKeyDictionary[object, dict[str, Any]] = WeakKeyDictionary()

    def encoder_state(process: WindowsEncoderProcess) -> dict[str, Any]:
        state = encoder_states.get(process)
        if state is None:
            state = {
                "owner_id": id(process), "progress_observation_interval": _metric(),
                "progress_change_interval": _metric(), "progress_observations": 0,
                "progress_change_count": 0, "last_progress_change_ns": None,
                "blocking_write": _metric(),
                "overlapped_begin_write": _metric(), "overlapped_write_wait": _metric(),
                "close_stdin": _metric(), "process_and_reader_drain": _metric(),
                "terminate": _metric(), "last_progress_frame": None,
                "last_progress_observation_ns": None, "pending_write_start_ns": None,
                "pending_write_bytes": 0, "bytes_written": 0,
            }
            encoder_states[process] = state
        return state

    progress_property = WindowsEncoderProcess.progress_frame
    raw_progress_getter = progress_property.fget
    def observed_progress_frame(self):
        value = raw_progress_getter(self)
        now = time.perf_counter_ns()
        state = encoder_state(self)
        previous = state["last_progress_frame"]
        state["progress_observations"] += 1
        prior_time = state["last_progress_observation_ns"]
        if prior_time is not None:
            _record_interval(state["progress_observation_interval"], now - prior_time)
        state["last_progress_observation_ns"] = now
        if value is not None and value != previous:
            if previous is not None:
                prior_change = state["last_progress_change_ns"]
                if prior_change is not None:
                    _record_interval(state["progress_change_interval"], now - prior_change)
                state["last_progress_change_ns"] = now
                state["progress_change_count"] += 1
            state["last_progress_frame"] = value
        return value
    WindowsEncoderProcess.progress_frame = property(
        observed_progress_frame, doc=progress_property.__doc__
    )

    raw_write = WindowsEncoderProcess.write
    def observed_write(self, frame, *, deadline_ns):
        state = encoder_state(self)
        started = time.perf_counter_ns()
        success = False
        try:
            result = raw_write(self, frame, deadline_ns=deadline_ns)
            success = True
            return result
        finally:
            ended = time.perf_counter_ns()
            _record(state["blocking_write"], started, ended, success)
            if success:
                state["bytes_written"] += len(frame)
    WindowsEncoderProcess.write = observed_write

    raw_begin_write = WindowsEncoderProcess.begin_write
    def observed_begin_write(self, frame, *, deadline_ns):
        state = encoder_state(self)
        started = time.perf_counter_ns()
        success = False
        try:
            result = raw_begin_write(self, frame, deadline_ns=deadline_ns)
            success = True
            state["pending_write_start_ns"] = time.perf_counter_ns()
            state["pending_write_bytes"] = len(frame)
            return result
        finally:
            _record(state["overlapped_begin_write"], started, time.perf_counter_ns(), success)
    WindowsEncoderProcess.begin_write = observed_begin_write

    raw_poll_write = WindowsEncoderProcess.poll_write
    def observed_poll_write(self):
        state = encoder_state(self)
        result = raw_poll_write(self)
        if result is not None and state["pending_write_start_ns"] is not None:
            now = time.perf_counter_ns()
            _record(state["overlapped_write_wait"], int(state["pending_write_start_ns"]), now, True)
            state["bytes_written"] += int(result)
            state["pending_write_start_ns"] = None
            state["pending_write_bytes"] = 0
        return result
    WindowsEncoderProcess.poll_write = observed_poll_write

    def wrap_process_call(name: str, metric_name: str, *, report: bool = False):
        original = getattr(WindowsEncoderProcess, name)
        def observed(self, *args, **kwargs):
            state = encoder_state(self)
            started = time.perf_counter_ns()
            success = False
            try:
                result = original(self, *args, **kwargs)
                success = True
                return result
            finally:
                ended = time.perf_counter_ns()
                _record(state[metric_name], started, ended, success)
                if report:
                    emit("encoder_io_timing", **dict(state), terminal_method=name,
                         terminal_end_ns=ended, terminal_outcome="returned" if success else "raised")
        setattr(WindowsEncoderProcess, name, observed)

    wrap_process_call("close_stdin", "close_stdin")
    wrap_process_call("wait", "process_and_reader_drain", report=True)
    wrap_process_call("terminate", "terminate", report=True)
