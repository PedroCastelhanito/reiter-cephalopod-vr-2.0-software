"""Fault-injection review evidence; run from repository root with .venv/bin/python.

Uses production capture/cancellation methods with a host GL adapter and a stopped,
full recording queue. No native GL, encoder or rig result is implied.
"""

import ctypes
import importlib.util
import json
import sys
import threading
from collections import deque
from pathlib import Path
from types import SimpleNamespace as NS

from cephvr.visual_stimulus.recording.capture import RecordingWorker
from cephvr.visual_stimulus.recording.capture_runtime import RecordingCaptureRuntime
from cephvr.visual_stimulus.recording.session import RecordingSession
from cephvr.visual_stimulus.rendering import capture as current


class GL:
    GL_ALREADY_SIGNALED, GL_CONDITION_SATISFIED, GL_WAIT_FAILED = 1, 2, 3
    GL_PIXEL_PACK_BUFFER, GL_MAP_READ_BIT = 4, 5

    def __init__(self, fail_unbind=False):
        self.pixels = (ctypes.c_ubyte * 4)(1, 2, 3, 4)
        self.fail_unbind = fail_unbind
        self.deleted_buffers = []
        self.deleted_syncs = []

    def glClientWaitSync(self, *_):
        return self.GL_ALREADY_SIGNALED

    def glBindBuffer(self, _target, buffer):
        if buffer == 0 and self.fail_unbind:
            self.fail_unbind = False
            raise RuntimeError("injected one-shot unbind error")

    def glMapBufferRange(self, *_):
        return ctypes.addressof(self.pixels)

    def glUnmapBuffer(self, *_):
        return True

    def glDeleteSync(self, sync):
        self.deleted_syncs.append(sync)

    def glDeleteBuffers(self, _count, buffers):
        self.deleted_buffers.extend(buffers)


def poll_failure(module, old=False):
    gl = GL(fail_unbind=True)
    owner = module.ReviewCapture()
    pending = (
        module._Pending(gl, 7, 8, 4)
        if old
        else module._Pending(module._Buffer(gl, 7, 4), 8)
    )
    owner._pending.append(pending)
    errors = []
    try:
        owner.poll(pending)
    except RuntimeError as exc:
        errors.append(str(exc))
    retained = pending in owner._pending
    try:
        owner.cancel(pending)
    except TypeError as exc:
        errors.append(str(exc))
    result = {
        "pending_retained_after_poll_error": retained,
        "cancellation_errors": errors[1:],
        "pooled_buffers_after_error": len(getattr(owner, "_available", [])),
        "deleted_buffers_after_cancel": gl.deleted_buffers[:],
    }
    owner.release()
    return result


def cancellation_with_full_failed_queue():
    gl = GL()
    owner = current.ReviewCapture()
    pending = current._Pending(current._Buffer(gl, 7, 4), 8)
    owner._pending.append(pending)
    evidence = NS(pending_bytes=0)
    worker = RecordingWorker(
        capture_slots=1, evidence=evidence, encoder=NS(), video_start_ns=0
    )
    reservation, _, _ = worker.classify_and_reserve(0, 0)
    # Exact queue state possible when a record factory fails before _line_bytes
    # is decremented: _run records its error and exits without draining _lines.
    session = object.__new__(RecordingSession)
    session.worker = worker
    session.evidence = evidence
    session._condition = threading.Condition()
    session._closing = False
    session.max_queued_evidence_bytes = 4096
    session._line_bytes = 4096
    session._lines = deque()
    session._done = True
    session._error = BufferError("record exceeded reserved line size")
    runtime = RecordingCaptureRuntime(
        NS(cancel_review_capture=owner.cancel), session,
        NS(native_pixel_format="rgba8_top_down", encoder_pixel_format="yuv420p"),
        evidence_pending_bytes=4096, capture_slots=1,
    )
    runtime.pending[reservation.token] = (reservation, pending)
    errors = []
    for _ in range(3):
        try:
            runtime.cancel_pending("capture_cleanup")
        except BufferError as exc:
            errors.append(str(exc))
    result = {
        "attempts": len(errors), "errors": errors,
        "runtime_pending": len(runtime.pending),
        "gl_pending": len(owner._pending),
        "worker_reservations": len(worker._reservations),
        "gl_delete_calls": len(gl.deleted_buffers) + len(gl.deleted_syncs),
    }
    assert result["attempts"] == 3 and result["gl_delete_calls"] == 0
    assert result["runtime_pending"] == result["gl_pending"] == 1
    # Diagnostic teardown bypasses the failed runtime, not a proposed fix.
    owner.release()
    return result


snapshot = Path(__file__).parents[1] / "stimulus-capture-optimization/capture-before.py"
spec = importlib.util.spec_from_file_location("capture_before_review", snapshot)
before = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = before
spec.loader.exec_module(before)
old, new = poll_failure(before, old=True), poll_failure(current)
assert old["pending_retained_after_poll_error"]
assert not new["pending_retained_after_poll_error"]
assert old["cancellation_errors"] == []
assert new["cancellation_errors"] == ["invalid pending review capture"]
print(json.dumps({
    "poll_failure_before": old, "poll_failure_current": new,
    "failed_evidence_queue_cancellation": cancellation_with_full_failed_queue(),
}, indent=2))
