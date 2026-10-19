"""Stop, drain and terminal-output finalization for one camera trial (A08/A09)."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass

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


@dataclass(slots=True)
class PendingStopOperation:
    request: object
    deadline_ns: int
    report: acq.WorkerOperationReport
    complete: Callable[[acq.WorkerOperationReport, int, BaseException | None], None]


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
        self._pending: list[PendingStopOperation] = []
        self._stop_deadline_ns: int | None = None
        self._report_stopped = False
        self._capture_finished: Callable[[object, int], None] | None = None
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

    def begin_operation(
        self,
        request: object,
        deadline_ns: int,
        report: acq.WorkerOperationReport,
        *,
        complete: Callable[
            [acq.WorkerOperationReport, int, BaseException | None], None
        ],
        capture_finished: Callable[[object, int], None],
        report_stopped: bool,
    ) -> None:
        limits = self.state.limits
        if limits is None or len(self._pending) >= limits.safety_reserve_records:
            raise RuntimeError("retained stop continuation capacity is unavailable")
        if not isinstance(request, (acq.WorkerStop, acq.WorkerInterrupt)):
            raise TypeError("stop continuation requires an exact Stop or Interrupt")
        report.operation.context.command_id = request.command.command_id
        first_stop = self.trial.stop_request is None
        if first_stop:
            self.trial.stop_request = request
        self._pending.append(
            PendingStopOperation(request, deadline_ns, report, complete)
        )
        if first_stop:
            self._capture_finished = capture_finished
            self._report_stopped = report_stopped
        self._stop_deadline_ns = (
            deadline_ns
            if self._stop_deadline_ns is None
            else min(self._stop_deadline_ns, deadline_ns)
        )
        if self.trial.actual_stop_ns is not None:
            self._complete_pending(None)
        self._advance_stop()

    def _complete_pending(self, failure: BaseException | None) -> None:
        pending, self._pending = self._pending, []
        for item in pending:
            item.complete(item.report, item.deadline_ns, failure)

    def _advance_stop(self) -> None:
        deadline = self._stop_deadline_ns
        if deadline is None:
            return
        failure: BaseException | None = None
        try:
            if not self.stop_trial(deadline, report_stopped=self._report_stopped):
                return
        except BaseException as exc:
            failure = exc
        if failure is not None and not self._pending:
            raise failure
        self._stop_deadline_ns = None
        self._capture_finished = None
        self._report_stopped = False
        self._complete_pending(failure)

    def stop_trial(self, deadline_ns: int, *, report_stopped: bool = False) -> bool:
        scheduled = self.trial.schedule or self.trial.stopped_schedule
        if not self.captures.active and self.trial.end_marker is not None:
            return True
        if self.captures.active:
            deadline_ns = self.captures.seal_admission(deadline_ns)
            if (
                self.captures.requires_external_trigger
                and self.trial.pulses.off is None
                and host_time_ns() < deadline_ns
            ):
                self.trial.stopped_schedule = scheduled
                self._stop_deadline_ns = deadline_ns
                return False
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
            return True

        scheduled_end = (
            scheduled.end_monotonic_ns
            if scheduled is not None and scheduled.HasField("end_monotonic_ns")
            else None
        )
        recording_end: int | None = None
        actual_stop = self.trial.actual_stop_ns
        stopped_reported = self.trial.stopped_reported

        def activity_stopped(observed_ns: int) -> None:
            nonlocal actual_stop, stopped_reported
            actual_stop = observed_ns
            self.trial.actual_stop_ns = observed_ns
            admission_stop = self.captures.admission_stop_ns
            if report_stopped and admission_stop is not None:
                end = (
                    min(scheduled_end, admission_stop)
                    if scheduled_end is not None
                    else admission_stop
                )
                self._publish_stopped(observed_ns, end, deadline_ns)
                stopped_reported = True
                self.trial.stopped_reported = True
            self._complete_pending(None)

        purge = self.trial.purge_evidence
        if self.captures.active:
            off_terminal = (
                not self.captures.requires_external_trigger
                or self.terminal.off_terminal_confirmed()
            )
            admission_stop = self.captures.admission_stop_ns
            if self.trial.finish_deadline_ns is None and admission_stop is not None:
                self.trial.finish_deadline_ns = self.terminal.finish_deadline(
                    deadline_ns,
                    min(scheduled_end, admission_stop)
                    if scheduled_end is not None
                    else None,
                    scheduled_end,
                )
            stopped = self.captures.stop(
                deadline_ns,
                drain_margin_ns=max(
                    0,
                    int(self.bootstrap.file_policy.post_cutoff_drain_margin_ns),
                ),
                terminal_off_confirmed=off_terminal,
                activity_stopped=activity_stopped,
                resumable=True,
                finalization_deadline_ns=self.trial.finish_deadline_ns,
            )
            if stopped is None:
                self._stop_deadline_ns = deadline_ns
                self.trial.stopped_schedule = scheduled
                return False
            if not isinstance(stopped, PurgeEvidence):
                raise TypeError("camera stop returned invalid purge evidence")
            purge = stopped
            actual_stop = actual_stop or host_time_ns()
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
        if (
            report_stopped
            and not stopped_reported
            and marker is not None
            and marker.actual_stop_monotonic_ns is not None
        ):
            self._publish_stopped(
                marker.actual_stop_monotonic_ns,
                marker.recording_end_monotonic_ns,
                deadline_ns,
            )
            self.trial.stopped_reported = True
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
        if self._capture_finished is not None and self.trial.stop_request is not None:
            callback, self._capture_finished = self._capture_finished, None
            callback(
                self.trial.stop_request,
                self.trial.finish_deadline_ns or deadline_ns,
            )
        return True

    def _publish_stopped(self, actual_ns: int, end_ns: int, deadline_ns: int) -> None:
        request = self.trial.stop_request
        if request is None:
            raise RuntimeError("camera Stopped has no exact Stop command")
        evidence = acq.WorkerLifecycleEvidence()
        evidence.stopped.actual_stop_monotonic_ns = actual_ns
        evidence.stopped.recording_end_monotonic_ns = end_ns
        evidence.stopped.recording_interval_sealed = True
        evidence.stopped.activity_stopped = True
        self._report_lifecycle(request, evidence, deadline_ns)

    def advance_due_stages(self) -> None:
        self._advance_stop()
        self.terminal.advance_due_stages()

    def publish_if_ready(self, deadline_ns: int | None) -> None:
        self.terminal.publish_if_ready(deadline_ns)

    def capture_continuing_snapshot(
        self, observed_ns: int
    ) -> control.ContinuingFunctionEvidence:
        return self.terminal.capture_continuing_snapshot(observed_ns)

    def recording_trial_installed(self) -> bool:
        return self.terminal.recording_trial_installed()
