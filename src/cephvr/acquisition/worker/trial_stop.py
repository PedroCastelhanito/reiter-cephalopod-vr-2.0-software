"""Stop, drain and terminal-output finalization for one camera trial (A08/A09)."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future

from cephvr.acquisition.camera.basler import BaslerCameraAdapter
from cephvr.acquisition.camera.types import PurgeEvidence
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns

from .capture_runtime import WorkerCaptureResources
from .recording_fault import (
    RecordingFaultLifecycle,
    not_started_outputs,
)
from .recording_ports import TrialRecordingPort
from .state import WorkerBootstrap, WorkerState
from .trial_recording_terminal import TrialRecordingTerminal
from .trial_state import WorkerTrialState


class TrialStopFinalizer:
    """Own local cutoff, drain evidence and asynchronous terminal report handoff."""

    def __init__(
        self,
        bootstrap: WorkerBootstrap,
        state: WorkerState,
        adapter: BaslerCameraAdapter,
        captures: WorkerCaptureResources,
        recording: TrialRecordingPort | None,
        trial: WorkerTrialState,
        recording_fault: RecordingFaultLifecycle,
        *,
        report_lifecycle: Callable[[object, acq.WorkerLifecycleEvidence, int], None],
        source: Callable[[acq.WorkerContext], acq.WorkerContext],
        operation_deadline: Callable[[str], int],
        complete_warning_scope: Callable[[], None],
        external_wake: Callable[[], None],
        recording_isolated: Callable[
            [
                control.WorkContext,
                str,
                int,
                tuple[str, ...],
                str,
                bool,
                control.ContinuingFunctionEvidence,
            ],
            None,
        ],
        warning_occurrence: Callable[..., None],
        recording_fault_observed: Callable[[], None],
    ) -> None:
        self.bootstrap = bootstrap
        self.state = state
        self.adapter = adapter
        self.captures = captures
        self.recording = recording
        self.trial = trial
        self.recording_fault = recording_fault
        self._report_lifecycle = report_lifecycle
        self._source = source
        self._operation_deadline = operation_deadline
        self._complete_warning_scope = complete_warning_scope
        self._external_wake = external_wake
        self._recording_isolated = recording_isolated
        self._warning_occurrence = warning_occurrence
        self._recording_fault_observed = recording_fault_observed
        self.terminal = TrialRecordingTerminal(
            bootstrap,
            state,
            adapter,
            captures,
            recording,
            trial,
            recording_fault,
            report_lifecycle=report_lifecycle,
            source=source,
            operation_deadline=operation_deadline,
            external_wake=external_wake,
            recording_isolated=recording_isolated,
            warning_occurrence=warning_occurrence,
            recording_fault_observed=recording_fault_observed,
        )

    def stop_trial(self, deadline_ns: int) -> None:
        scheduled = self.trial.schedule
        if not self.captures.active and scheduled is not None:
            self.captures.cancel_schedule()
            if self.terminal.recording_trial_installed():
                runtime = self.recording
                if runtime is None:
                    raise RuntimeError("recording trial has no writer runtime")
                self.trial.finished_future = runtime.cancel_before_start(
                    deadline_ns=deadline_ns
                )
                self.trial.finished_future.add_done_callback(
                    lambda _future: self._external_wake()
                )
            self.captures.remove_recording()
            self.trial.stopped_schedule = scheduled
            self.trial.schedule = None
            self.trial.released = False
            self.trial.prepared = False
            self._complete_warning_scope()
            return
        if not self.captures.active and self.trial.end_marker is not None:
            return

        scheduled_end = (
            scheduled.end_monotonic_ns
            if scheduled is not None and scheduled.HasField("end_monotonic_ns")
            else None
        )
        recording_end: int | None = None
        actual_stop: int | None = None
        purge = self.trial.purge_evidence
        if self.captures.active:
            off_terminal = (
                not self.captures.requires_external_trigger
                or self.terminal.off_terminal_confirmed()
            )
            stopped = self.captures.stop(
                deadline_ns,
                drain_margin_ns=max(
                    0,
                    int(self.bootstrap.file_policy.post_cutoff_drain_margin_ns),
                ),
                terminal_off_confirmed=off_terminal,
            )
            if not isinstance(stopped, PurgeEvidence):
                raise TypeError("camera stop returned invalid purge evidence")
            purge = stopped
            actual_stop = host_time_ns()
            self.trial.purge_evidence = stopped
            self.terminal.collect_transport_summary()
            admission_stop = self.captures.admission_stop_ns
            if admission_stop is None:
                raise RuntimeError("camera admission stop has no local timestamp")
            recording_end = (
                min(scheduled_end, admission_stop)
                if scheduled_end is not None
                else None
            )

        capture = self.captures.capture
        if recording_end is not None and capture is not None:
            excluded = (
                capture.excluded_frame_count + purge.discarded_frame_count
                if purge is not None
                and purge.accounting_complete
                and purge.discarded_frame_count is not None
                else None
            )
            last_excluded = None
            if excluded is not None:
                last_excluded = (
                    purge.last_native_counter
                    if purge is not None and purge.last_native_counter is not None
                    else capture.last_excluded_counter
                )
            from cephvr.acquisition.buffers.end_marker import CaptureEndMarker

            self.trial.end_marker = CaptureEndMarker(
                received_frame_count=capture.received_frame_count,
                recording_end_monotonic_ns=recording_end,
                actual_stop_monotonic_ns=actual_stop,
                excluded_frame_count=excluded,
                last_excluded_camera_counter=last_excluded,
                excluded_accounting_complete=bool(
                    purge is not None and purge.accounting_complete
                ),
            )

        marker = self.trial.end_marker
        if marker is not None and self.trial.finish_deadline_ns is None:
            self.trial.finish_deadline_ns = self.terminal.finish_deadline(
                deadline_ns, recording_end, scheduled_end
            )
        if (
            self.recording is not None
            and self.recording.enabled
            and marker is not None
            and self.trial.finished_future is None
        ):
            self.trial.finish_deadline_ns = self.terminal.finish_deadline(
                deadline_ns, recording_end, scheduled_end
            )
            if self.recording_fault.faulted_session:
                self.trial.finished_future = Future()
                self.trial.finished_future.set_result(
                    self.recording_fault.outputs
                    if self.recording_fault.outputs is not None
                    else not_started_outputs(scheduled)
                )
                self.trial.finished_future.add_done_callback(
                    lambda _future: self._external_wake()
                )
            elif self.terminal.recording_trial_installed() and (
                not self.trial.pulses.required or self.terminal.pulses_received()
            ):
                self.terminal.publish_if_ready(self.trial.finish_deadline_ns)
        self.captures.remove_recording()
        self.trial.stopped_schedule = scheduled
        self.trial.schedule = None
        self.trial.released = False
        self.trial.prepared = False
        self._complete_warning_scope()

    def advance_due_stages(self) -> None:
        self.terminal.advance_due_stages()

    def publish_if_ready(self, deadline_ns: int | None) -> None:
        self.terminal.publish_if_ready(deadline_ns)

    def capture_continuing_snapshot(
        self, observed_ns: int
    ) -> control.ContinuingFunctionEvidence:
        return self.terminal.capture_continuing_snapshot(observed_ns)

    def recording_trial_installed(self) -> bool:
        return self.terminal.recording_trial_installed()
