"""Publish immutable worker health from owner-owned capture and trial state (A02)."""

from __future__ import annotations

from collections.abc import Callable

from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns

from .capture_runtime import WorkerCaptureResources
from .state import WorkerState
from .trial_lifecycle import WorkerTrialLifecycle


def refresh_health_snapshot(
    state: WorkerState,
    trial: WorkerTrialLifecycle,
    captures: WorkerCaptureResources,
    latest_work: control.WorkContext | None,
    session_ready: bool,
    *,
    clock_ns: Callable[[], int] = host_time_ns,
) -> None:
    if state.health_active_error is not None:
        state.update_continuing_snapshot(trial.continuing_functions(clock_ns()))
    schedule = trial.scheduled
    last_progress_ns: int | None = None
    capture = captures.capture
    if capture is not None and capture.last_usable_ns > 0:
        last_progress_ns = capture.last_usable_ns
    work: control.WorkContext | None
    if schedule is not None and schedule.command.target.HasField("work"):
        work = schedule.command.target.work
        trial_phase = (
            control.TRIAL_PHASE_FINALIZING
            if trial.terminal_pending
            else control.TRIAL_PHASE_ENDED
            if trial.end_marker is not None
            else control.TRIAL_PHASE_RUNNING
            if captures.active
            else control.TRIAL_PHASE_STARTING
        )
    else:
        work = latest_work
        trial_phase = None
    closed = work is not None and (
        state.health_work == work
        and state.health_session_phase == control.SESSION_PHASE_ENDED
        or any(
            evidence.source.work == work
            and evidence.WhichOneof("evidence") == "cleanup"
            and evidence.cleanup.resources
            and all(
                item.released and not item.HasField("failure")
                for item in evidence.cleanup.resources
            )
            for evidence in state.lifecycle.values()
        )
    )
    session_phase = (
        control.SESSION_PHASE_ENDED
        if closed
        else control.SESSION_PHASE_FINALIZING
        if state.interrupted
        else control.SESSION_PHASE_READY
        if session_ready
        else control.SESSION_PHASE_SETTING_UP
        if state.registered
        else control.SESSION_PHASE_CONFIGURATION
    )
    state.update_health_snapshot(
        work=work,
        session_phase=session_phase,
        trial_phase=trial_phase,
        progress_required=captures.active,
        last_progress_ns=last_progress_ns,
        observed_ns=clock_ns(),
    )
