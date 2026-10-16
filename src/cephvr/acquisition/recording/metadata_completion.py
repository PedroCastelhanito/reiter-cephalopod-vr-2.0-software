"""Close required camera evidence when no video encoder was requested."""

from collections.abc import Callable
from pathlib import Path

from cephvr.acquisition.buffers.end_marker import CaptureEndMarker
from cephvr.acquisition.recording.frame_log import FrameLogCompletion, FrameLogWriter
from cephvr.acquisition.recording.session_completion import terminal_capture_proof
from cephvr.acquisition.recording.session_contracts import (
    PulseEvidence,
    RecordingCompletionContext,
    RecordingFailure,
    RecordingQueue,
)
from cephvr.acquisition.recording.session_diagnostics import RecordingDiagnostics
from cephvr.acquisition.recording.session_finalizer import (
    FinalizationProgress,
    append_terminal_and_close,
)
from cephvr.acquisition.recording.session_outputs import output_result
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control


def finish_metadata(
    end: CaptureEndMarker,
    pulses: PulseEvidence,
    completion: RecordingCompletionContext,
    *,
    schedule: acq.WorkerSchedule,
    frame_log: FrameLogWriter,
    received: int,
    logged: int,
    last_frame_id: int,
    diagnostics: RecordingDiagnostics,
    finalization: FinalizationProgress,
    deadline_ns: int,
    clock_ns: Callable[[], int],
) -> list[control.OutputResult]:
    if completion.outcome not in {"completed", "interrupted"}:
        raise RecordingFailure("terminal recording outcome is invalid")
    stop, timing, accounting = terminal_capture_proof(
        end,
        completion,
        schedule=schedule,
        received=received,
        logged=logged,
        last_frame_id=last_frame_id,
    )
    success = (
        stop
        and timing
        and accounting
        and end.excluded_accounting_complete
        and pulses.complete()
        and received > 0
    )
    finalization.late |= clock_ns() > deadline_ns
    terminal = FrameLogCompletion(
        outcome=completion.outcome
        if success and not finalization.late
        else "interrupted",
        recording_end_monotonic_ns=end.recording_end_monotonic_ns
        if stop and timing
        else None,
        final_received_frame_count=received if accounting else None,
        accounting_complete=accounting,
        recorded_frame_count=0,
        selected_source_frame_count=0,
        duplicate_frame_count=0,
        on_outcome=pulses.on_outcome,
        on_dispatched_monotonic_ns=pulses.on_dispatched_monotonic_ns,
        on_acknowledged_monotonic_ns=pulses.on_acknowledged_monotonic_ns,
        off_outcome=pulses.off_outcome,
        off_dispatched_monotonic_ns=pulses.off_dispatched_monotonic_ns,
        off_acknowledged_monotonic_ns=pulses.off_acknowledged_monotonic_ns,
        post_cutoff_accounting_complete=end.excluded_accounting_complete,
        excluded_frame_count=end.excluded_frame_count
        if end.excluded_accounting_complete
        else None,
        last_native_counter=end.last_excluded_camera_counter if stop else None,
        transport_summary=completion.transport_summary,
        diagnostics=diagnostics.frame_log_groups(),
    )
    append_terminal_and_close(
        finalization,
        frame_log,
        None,
        terminal,
        deadline_ns=deadline_ns,
        clock_ns=clock_ns,
    )
    closed = success and not finalization.late and not finalization.completion_failed
    result = output_result(
        schedule,
        frame_log.path,
        control.OUTPUT_CLOSURE_CLOSED if closed else control.OUTPUT_CLOSURE_FAILED,
        True,
    )
    if closed:
        result.counts["source_frames"] = logged
    return [result]


def cleanup_metadata(
    schedule: acq.WorkerSchedule | None,
    frame_log: FrameLogWriter | None,
    queue: RecordingQueue,
    *,
    cancelled: bool,
) -> list[control.OutputResult]:
    queue.close()
    while (entry := queue.dequeue(0)) is not None:
        queue.complete(entry.record)
    if frame_log is not None:
        frame_log.close_failed()
    if schedule is None:
        return []
    results = []
    for plan in schedule.outputs:
        present = Path(plan.path).exists()
        owned = frame_log is not None and frame_log.file is not None
        closure = control.OUTPUT_CLOSURE_FAILED
        if present and not owned:
            closure = control.OUTPUT_CLOSURE_UNCONFIRMED
        elif cancelled and not present and not owned:
            closure = control.OUTPUT_CLOSURE_NOT_STARTED
        results.append(
            control.OutputResult(
                output_key=plan.output_key,
                path=plan.path,
                closure=closure,
                artifact_present=present,
            )
        )
    return results
