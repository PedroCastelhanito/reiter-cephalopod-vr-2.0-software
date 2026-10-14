"""Temporary occupancy/timing probe for managed rig workers; never load normally."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
from weakref import WeakKeyDictionary

_ARGS = " ".join(sys.argv[1:])
_IS_ACQ = "cephvr.acquisition.worker.main" in _ARGS
_IS_VIS = "cephvr.visual_stimulus.worker.main" in _ARGS

if _IS_ACQ or _IS_VIS:
    _scope = "visual_stimulus" if _IS_VIS else "acquisition"
    _output_value = os.environ.get("CEPHVR_OCCUPANCY_OUTPUT")
    _out_dir = Path(_output_value) if _output_value else None
    _pid = os.getpid()
    _summary_path = _out_dir / f"occupancy-{_pid}.jsonl" if _out_dir else None

    def _emit(kind: str, **fields: object) -> None:
        """Write only aggregate/lifecycle records; failures never affect worker behavior."""
        if _summary_path is None:
            return
        try:
            row = {"kind": kind, "pid": _pid, "host_ns": time.perf_counter_ns(), **fields}
            with _summary_path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(row, separators=(",", ":")) + "\n")
        except Exception:
            pass

    _dll_handles = []
    if _summary_path is None:
        _IS_ACQ = _IS_VIS = False
    else:
        try:
            _manifest_path = Path(sys.executable).parent / "cephvr-python.runtime.json"
            _manifest = json.loads(_manifest_path.read_text(encoding="utf-8"))
            if hasattr(os, "add_dll_directory"):
                _dll_handles = [
                    os.add_dll_directory(path)
                    for path in _manifest["dll_directories"]
                ]
        except Exception as exc:
            _emit("instrumentation_load_error", scope=_scope, stage="dll_manifest", error_type=type(exc).__name__)
            _IS_ACQ = _IS_VIS = False
        else:
            _emit("instrumentation_loaded", scope=_scope)

    if _IS_ACQ:
        from cephvr.acquisition.buffers.queue import RecordingQueue
        from cephvr.acquisition.camera.basler import BaslerCameraAdapter

        _queues: WeakKeyDictionary[RecordingQueue, dict[str, object]] = WeakKeyDictionary()
        _camera_states: WeakKeyDictionary[BaslerCameraAdapter, dict[str, object]] = WeakKeyDictionary()

        def _camera_state(adapter: BaslerCameraAdapter) -> dict[str, object]:
            state = _camera_states.get(adapter)
            if state is None:
                state = {
                    "serial": getattr(adapter, "_device_id", None),
                    "retrieve_calls": 0, "retrieve_empty_count": 0,
                    "retrieve_result_count": 0, "retrieve_valid_count": 0,
                    "retrieve_invalid_count": 0, "retrieve_error_count": 0,
                    "first_retrieve_return_ns": None, "last_retrieve_return_ns": None,
                    "last_retrieve_valid": None, "last_retrieve_counter": None,
                    "last_retrieve_device_timestamp_ns": None,
                    "last_after_terminal_callback_ns": None,
                    "last_after_terminal_result_ns": None,
                    "last_valid_after_terminal_ns": None,
                    "last_valid_after_terminal_counter": None,
                    "last_valid_after_terminal_device_timestamp_ns": None,
                    "terminal_start_ns": None,
                    "exposure_us": None, "frame_rate_hz": None,
                }
                _camera_states[adapter] = state
            return state

        def _queue_state(queue: RecordingQueue) -> dict[str, object]:
            state = _queues.get(queue)
            if state is None:
                state = {
                    "queue_id": id(queue), "capacity_frames": queue.capacity_frames,
                    "pending_records_capacity": queue.pending_records_capacity,
                    "created_ns": time.perf_counter_ns(), "enqueue_calls": 0,
                    "dequeue_calls": 0, "complete_calls": 0, "drop_count": 0,
                    "max_waiting_pixels": 0, "max_pending_records": 0,
                    "max_enqueue_call_ns": 0, "max_dequeue_call_ns": 0,
                    "max_complete_call_ns": 0, "max_queue_wait_ns": 0,
                    "max_host_receipt_to_enqueue_ns": 0,
                    "max_consumer_service_ns": 0, "enqueued_ns": {},
                    "dequeued_ns": {}, "closed_ns": None, "reported": False,
                }
                _queues[queue] = state
            return state

        def _sample_queue(queue: RecordingQueue, state: dict[str, object]) -> None:
            # Condition uses its existing default RLock; snapshots follow that same lock.
            with queue._condition:
                waiting = queue._waiting_pixels
                pending = len(queue._entries) + (queue._inflight is not None)
            state["max_waiting_pixels"] = max(int(state["max_waiting_pixels"]), waiting)
            state["max_pending_records"] = max(int(state["max_pending_records"]), pending)

        def _maybe_report_queue(queue: RecordingQueue, state: dict[str, object]) -> None:
            if state["closed_ns"] is None:
                return
            _sample_queue(queue, state)
            with queue._condition:
                drained = not queue._entries and queue._inflight is None
            if drained and not state["reported"]:
                state["drained_ns"] = time.perf_counter_ns()
                state["closure_to_drain_ns"] = int(state["drained_ns"]) - int(state["closed_ns"])
                state["reported"] = True
                state.pop("enqueued_ns", None)
                state.pop("dequeued_ns", None)
                _emit("recording_queue_drain", **state)

        _enqueue = RecordingQueue.enqueue
        def _observed_enqueue(self, record, pixels):
            started = time.perf_counter_ns()
            state = _queue_state(self)
            try:
                with self._condition:
                    result = _enqueue(self, record, pixels)
                    ended = time.perf_counter_ns()
                    state["enqueue_calls"] = int(state["enqueue_calls"]) + 1
                    state["max_enqueue_call_ns"] = max(int(state["max_enqueue_call_ns"]), ended - started)
                    state["enqueued_ns"][id(record)] = ended
                    state["max_host_receipt_to_enqueue_ns"] = max(
                        int(state["max_host_receipt_to_enqueue_ns"]),
                        ended - record.acquisition_time_ns,
                    )
                    if result.dropped_record is not None:
                        state["drop_count"] = int(state["drop_count"]) + 1
                    _sample_queue(self, state)
            except BaseException:
                state["max_enqueue_call_ns"] = max(int(state["max_enqueue_call_ns"]), time.perf_counter_ns() - started)
                raise
            return result
        RecordingQueue.enqueue = _observed_enqueue

        _dequeue = RecordingQueue.dequeue
        def _observed_dequeue(self, timeout=None):
            started = time.perf_counter_ns()
            with self._condition:
                result = _dequeue(self, timeout)
                ended = time.perf_counter_ns()
                state = _queue_state(self)
                state["dequeue_calls"] = int(state["dequeue_calls"]) + 1
                state["max_dequeue_call_ns"] = max(int(state["max_dequeue_call_ns"]), ended - started)
                if result is not None:
                    record_id = id(result.record)
                    enqueued = state["enqueued_ns"].pop(record_id, None)
                    if enqueued is not None:
                        state["max_queue_wait_ns"] = max(int(state["max_queue_wait_ns"]), ended - int(enqueued))
                    state["dequeued_ns"][record_id] = ended
                _sample_queue(self, state)
            return result
        RecordingQueue.dequeue = _observed_dequeue

        _complete = RecordingQueue.complete
        def _observed_complete(self, record):
            started = time.perf_counter_ns()
            with self._condition:
                result = _complete(self, record)
                ended = time.perf_counter_ns()
                state = _queue_state(self)
                state["complete_calls"] = int(state["complete_calls"]) + 1
                state["max_complete_call_ns"] = max(int(state["max_complete_call_ns"]), ended - started)
                dequeued = state["dequeued_ns"].pop(id(record), None)
                if dequeued is not None:
                    state["max_consumer_service_ns"] = max(int(state["max_consumer_service_ns"]), ended - int(dequeued))
                _sample_queue(self, state)
                _maybe_report_queue(self, state)
            return result
        RecordingQueue.complete = _observed_complete

        _close = RecordingQueue.close
        def _observed_close(self):
            with self._condition:
                result = _close(self)
                waiting_pixels = self._waiting_pixels
                pending_records = len(self._entries) + (self._inflight is not None)
            state = _queue_state(self)
            state["closed_ns"] = time.perf_counter_ns()
            _sample_queue(self, state)
            _emit("recording_queue_closed", queue_id=state["queue_id"], closed_ns=state["closed_ns"], waiting_pixels=waiting_pixels, pending_records=pending_records, max_waiting_pixels=state["max_waiting_pixels"], max_pending_records=state["max_pending_records"], drop_count=state["drop_count"])
            _maybe_report_queue(self, state)
            return result
        RecordingQueue.close = _observed_close

        _retrieve = BaslerCameraAdapter.retrieve
        def _observed_retrieve(self, timeout_ns):
            state = _camera_state(self)
            try:
                result = _retrieve(self, timeout_ns)
            except BaseException:
                state["retrieve_error_count"] = int(state["retrieve_error_count"]) + 1
                raise
            returned_ns = time.perf_counter_ns()
            state["retrieve_calls"] = int(state["retrieve_calls"]) + 1
            if state["first_retrieve_return_ns"] is None:
                state["first_retrieve_return_ns"] = returned_ns
            state["last_retrieve_return_ns"] = returned_ns
            valid = None if result is None else bool(result.valid_image)
            counter = None if result is None else result.camera_frame_counter
            device_timestamp = None if result is None else result.camera_timestamp_ns
            state["last_retrieve_valid"] = valid
            state["last_retrieve_counter"] = counter
            state["last_retrieve_device_timestamp_ns"] = device_timestamp
            terminal_ns = state["terminal_start_ns"]
            if terminal_ns is not None and returned_ns >= int(terminal_ns):
                state["last_after_terminal_callback_ns"] = returned_ns
                if result is not None:
                    state["retrieve_result_count"] = int(state["retrieve_result_count"]) + 1
                    state["last_after_terminal_result_ns"] = returned_ns
                    if valid:
                        state["last_valid_after_terminal_ns"] = returned_ns
                        state["last_valid_after_terminal_counter"] = counter
                        state["last_valid_after_terminal_device_timestamp_ns"] = device_timestamp
            if result is None:
                state["retrieve_empty_count"] = int(state["retrieve_empty_count"]) + 1
            else:
                if terminal_ns is None or returned_ns < int(terminal_ns):
                    state["retrieve_result_count"] = int(state["retrieve_result_count"]) + 1
                if valid:
                    state["retrieve_valid_count"] = int(state["retrieve_valid_count"]) + 1
                else:
                    state["retrieve_invalid_count"] = int(state["retrieve_invalid_count"]) + 1
            return result
        BaslerCameraAdapter.retrieve = _observed_retrieve

        _read_settings = BaslerCameraAdapter.read_settings
        def _observed_read_settings(self):
            settings = _read_settings(self)
            state = _camera_state(self)
            state["exposure_us"] = settings.exposure_us
            state["frame_rate_hz"] = settings.frame_rate_hz
            return settings
        BaslerCameraAdapter.read_settings = _observed_read_settings

        _begin_terminal_drain = BaslerCameraAdapter.begin_terminal_drain
        def _observed_begin_terminal_drain(self):
            started = time.perf_counter_ns()
            state = _camera_state(self)
            state["terminal_start_ns"] = started
            result = _begin_terminal_drain(self)
            ended = time.perf_counter_ns()
            _emit("camera_terminal_begin", **dict(state), terminal_begin_end_ns=ended, terminal_begin_elapsed_ns=ended - started, generation_stopped=result)
            return result
        BaslerCameraAdapter.begin_terminal_drain = _observed_begin_terminal_drain

        _stop_capture = BaslerCameraAdapter.stop_capture
        def _observed_stop_capture(self, *args, **kwargs):
            started = time.perf_counter_ns()
            state = _camera_state(self)
            try:
                result = _stop_capture(self, *args, **kwargs)
            except BaseException as exc:
                ended = time.perf_counter_ns()
                terminal_ns = state["terminal_start_ns"]
                last_valid_ns = state["last_valid_after_terminal_ns"]
                _emit("camera_stop_capture", **dict(state), stop_capture_start_ns=started, stop_capture_end_ns=ended, stop_capture_elapsed_ns=ended - started, last_valid_after_terminal_elapsed_ns=(int(last_valid_ns) - int(terminal_ns) if last_valid_ns is not None and terminal_ns is not None else None), outcome="raised", error_type=type(exc).__name__)
                raise
            ended = time.perf_counter_ns()
            terminal_ns = state["terminal_start_ns"]
            last_valid_ns = state["last_valid_after_terminal_ns"]
            _emit("camera_stop_capture", **dict(state), stop_capture_start_ns=started, stop_capture_end_ns=ended, stop_capture_elapsed_ns=ended - started, last_valid_after_terminal_elapsed_ns=(int(last_valid_ns) - int(terminal_ns) if last_valid_ns is not None and terminal_ns is not None else None), outcome="returned")
            return result
        BaslerCameraAdapter.stop_capture = _observed_stop_capture

    if _IS_VIS:
        from dataclasses import asdict, is_dataclass
        import threading
        from cephvr.visual_stimulus.recording.capture import RecordingWorker

        _worker_state: WeakKeyDictionary[RecordingWorker, dict[str, object]] = WeakKeyDictionary()
        _capture_check = threading.local()

        def _state(worker: RecordingWorker) -> dict[str, object]:
            state = _worker_state.get(worker)
            if state is None:
                state = {
                    "worker_id": id(worker), "capture_slots": worker.capture_slots,
                    "created_ns": time.perf_counter_ns(), "max_inflight_captures": 0,
                    "classify_calls": 0, "classify_elapsed_max_ns": 0,
                    "first_classify_ns": None, "input_close_started_ns": None,
                }
                _worker_state[worker] = state
            return state

        _inflight_count = RecordingWorker._inflight_capture_count
        def _observed_inflight_count(self):
            count = _inflight_count(self)
            # Called inside classify_and_reserve while its non-reentrant lock is held.
            state = _state(self)
            state["max_inflight_captures"] = max(int(state["max_inflight_captures"]), count)
            _capture_check.worker_id = id(self)
            _capture_check.count = count
            return count
        RecordingWorker._inflight_capture_count = _observed_inflight_count

        _classify = RecordingWorker.classify_and_reserve
        def _observed_classify(self, group_id, source_host_ns):
            started = time.perf_counter_ns()
            state = _state(self)
            if state["first_classify_ns"] is None:
                state["first_classify_ns"] = started
            try:
                result = _classify(self, group_id, source_host_ns)
                checked = getattr(_capture_check, "count", None)
                if (
                    result[0] is not None
                    and getattr(_capture_check, "worker_id", None) == id(self)
                    and checked is not None
                ):
                    state["max_inflight_captures"] = max(
                        int(state["max_inflight_captures"]), int(checked) + 1
                    )
            finally:
                elapsed = time.perf_counter_ns() - started
                state["classify_calls"] = int(state["classify_calls"]) + 1
                state["classify_elapsed_max_ns"] = max(int(state["classify_elapsed_max_ns"]), elapsed)
            return result
        RecordingWorker.classify_and_reserve = _observed_classify

        _finish_input = RecordingWorker.finish_input
        def _observed_finish_input(self):
            started = time.perf_counter_ns()
            state = _state(self)
            try:
                counts = _finish_input(self)
            except BaseException as exc:
                state["input_close_finished_ns"] = time.perf_counter_ns()
                _emit("visual_recording_summary", **state, input_close_outcome="raised", error_type=type(exc).__name__)
                raise
            ended = time.perf_counter_ns()
            state["input_close_started_ns"] = started
            state["input_close_finished_ns"] = ended
            state["finish_input_elapsed_ns"] = ended - started
            first = state["first_classify_ns"]
            state["capture_admission_to_input_close_ns"] = ended - int(first) if first is not None else None
            state["counts"] = asdict(counts) if is_dataclass(counts) else repr(counts)
            _emit("visual_recording_summary", **state, input_close_outcome="returned")
            return counts
        RecordingWorker.finish_input = _observed_finish_input

    try:
        from file_timing_probe import install as _install_file_timing_probe

        _install_file_timing_probe(_emit, acquisition=_IS_ACQ, visual=_IS_VIS)
    except Exception as exc:
        _emit("instrumentation_load_error", scope=_scope, stage="file_timing_probe", error_type=type(exc).__name__)




