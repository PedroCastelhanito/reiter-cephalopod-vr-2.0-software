"""Writer completion and retained terminal evidence for camera trials (A07/A08)."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future

from cephvr.acquisition.camera.basler import BaslerCameraAdapter
from cephvr.acquisition.recording.session_contracts import RecordingCompletionContext
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns

from .capture_runtime import WorkerCaptureResources
from .ports import command_from
from .recording_fault import RecordingFaultLifecycle, failed_outputs
from .recording_ports import TrialRecordingPort
from .state import WorkerBootstrap, WorkerState
from .transport_summary import TRANSPORT_COUNTER_FIELDS, collect_transport_summary
from .trial_state import WorkerTrialState


class TrialRecordingTerminal:
    """Own writer completion, fault isolation and trial terminal evidence."""

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
        self._external_wake = external_wake
        self._recording_isolated = recording_isolated
        self._warning_occurrence = warning_occurrence
        self._recording_fault_observed = recording_fault_observed

    def advance_due_stages(self) -> None:
        self._observe_recording_failure()
        self.captures.advance_due_stage()
        future = self.trial.finished_future
        runtime = self.recording
        if (
            self.recording_fault.cleanup_pending
            and future is not None
            and future.done()
            and self.trial.stop_request is None
        ):
            self._reconcile_recording_fault(future)
            return
        if future is None or not future.done() or self.trial.stop_request is None:
            return
        stop_request = self.trial.stop_request
        cleanup_recovered = False
        try:
            outputs = (
                runtime.completed_results()
                if runtime is not None
                and runtime.enabled
                and not self.recording_fault.faulted_session
                else future.result()
            )
        except BaseException:
            outputs = failed_outputs(
                self.trial.schedule or self.trial.stopped_schedule,
                control.OUTPUT_CLOSURE_UNCONFIRMED,
            )
        else:
            cleanup_recovered = self.recording_fault.cleanup_pending
        self.trial.finished_future = None
        command = command_from(stop_request)
        evidence = acq.WorkerLifecycleEvidence()
        evidence.finished.activity_stopped = True
        evidence.finished.outputs.extend(outputs)
        self._fill_transport_summary(evidence)
        evidence.source.CopyFrom(self._source(command.target))
        evidence.operation.command_id = command.command_id
        evidence.state_revision = self.state.state_revision + 1
        finish_deadline = self.trial.finish_deadline_ns or self._operation_deadline(
            command.command_id
        )
        self._report_lifecycle(stop_request, evidence, finish_deadline)
        if (
            runtime is not None
            and runtime.enabled
            and (not self.recording_fault.faulted_session or cleanup_recovered)
        ):
            try:
                runtime.recycle_finished(finish_deadline)
                if cleanup_recovered:
                    self.recording_fault.cleanup_pending = False
            except BaseException:
                self.recording_fault.faulted_session = True
                cleanup_recovered = False
                self.recording_fault.cleanup_pending = False
        if cleanup_recovered:
            schedule = self.trial.stopped_schedule or self.trial.schedule
            if schedule is not None:
                self._recording_isolated(
                    command.target.work,
                    schedule.command.command_id,
                    host_time_ns(),
                    self.state.recording_fault_resources(),
                    "recording resources were reconciled after the isolated fault",
                    True,
                    self.capture_continuing_snapshot(host_time_ns()),
                )
        can_finalize = (
            runtime is None
            or not runtime.enabled
            or not self.recording_fault.faulted_session
            or cleanup_recovered
        )
        work = command.target.work
        if can_finalize and work.WhichOneof("work") == "trial":
            self.state.finalize_scope(work, host_time_ns())

    def _observe_recording_failure(self) -> None:
        runtime, schedule = self.recording, self.trial.schedule
        if (
            runtime is None
            or not runtime.enabled
            or self.recording_fault.faulted_session
            or schedule is None
            or self.trial.end_marker is not None
            or self.trial.finished_future is not None
        ):
            return
        observed_ns = host_time_ns()
        self.trial.finished_future = self.recording_fault.observe_failure(
            schedule,
            runtime,
            observed_ns=observed_ns,
            recovery_deadline_ns=(
                observed_ns + self.bootstrap.control_policies.recovery_ns
            ),
            capture_function=self.capture_continuing_snapshot(observed_ns),
            capture_resource_id=self._camera_resource_id(),
            resource_ids=self.state.recording_fault_resources(),
            detach_recording=self.captures.remove_recording,
        )
        if self.trial.finished_future is not None:
            self._recording_fault_observed()

    def _reconcile_recording_fault(
        self, future: Future[list[control.OutputResult]]
    ) -> None:
        now = host_time_ns()
        self.recording_fault.reconcile(
            future,
            observed_ns=now,
            capture_function=self.capture_continuing_snapshot(now),
        )

    def publish_if_ready(self, deadline_ns: int | None) -> None:
        runtime, marker = self.recording, self.trial.end_marker
        if (
            runtime is None
            or marker is None
            or deadline_ns is None
            or self.trial.finished_future is not None
        ):
            return
        pulses = self.trial.pulses.combined()
        if self.trial.pulses.required and not self.pulses_received():
            return
        completion = RecordingCompletionContext(
            "completed"
            if marker.excluded_accounting_complete
            and marker.actual_stop_monotonic_ns is not None
            and pulses.complete()
            else "interrupted",
            marker.recording_end_monotonic_ns,
            marker.actual_stop_monotonic_ns,
            self.trial.transport_summary,
        )
        self.trial.finished_future = runtime.finish(
            marker, pulses, completion, deadline_ns=deadline_ns
        )
        self.trial.finished_future.add_done_callback(
            lambda _future: self._external_wake()
        )

    def finish_deadline(
        self,
        operation_deadline: int,
        recording_end: int | None,
        scheduled_end: int | None,
    ) -> int:
        normal = (
            self.recording.completion_deadline_ns
            if self.recording is not None
            and self.recording.enabled
            and not self.recording_fault.faulted_session
            else None
        )
        if normal is not None and recording_end == scheduled_end:
            return normal
        anchor = self.trial.pulses.off_boundary_ns
        stop = self.trial.stop_request
        if anchor is None and stop is not None and stop.HasField("issued_monotonic_ns"):
            anchor = stop.issued_monotonic_ns
        if anchor is None:
            return operation_deadline
        return anchor + self.bootstrap.control_policies.trial_finished.initial_ns

    def off_terminal_confirmed(self) -> bool:
        off = self.trial.pulses.off
        return (
            off is not None
            and off.off_outcome == "PULSE_COMMAND_OUTCOME_APPLIED"
            and off.off_acknowledged_monotonic_ns is not None
        )

    def pulses_received(self) -> bool:
        return self.trial.pulses.on is not None and self.trial.pulses.off is not None

    def recording_trial_installed(self) -> bool:
        return (
            self.recording is not None
            and self.recording.enabled
            and self.recording.recording_queue is not None
        )

    def _camera_resource_id(self) -> str:
        role = (
            "behavioral"
            if self.bootstrap.context.camera == camera.CAMERA_ROLE_BEHAVIORAL
            else "tracking"
        )
        return f"{role}.capture"

    def capture_continuing_snapshot(
        self, observed_ns: int
    ) -> control.ContinuingFunctionEvidence:
        schedule = self.trial.schedule or self.trial.stopped_schedule
        capture = self.captures.capture
        last_usable = capture.last_usable_ns if capture is not None else 0
        active = self.captures.active
        functioning = bool(
            (not active and self.trial.schedule is None)
            or (
                active
                and last_usable > 0
                and observed_ns >= last_usable
                and observed_ns - last_usable < self.captures.frame_silence_timeout_ns
            )
        )
        result = control.ContinuingFunctionEvidence(
            resource_id=self._camera_resource_id(),
            functioning=functioning,
            control_path_valid=True,
            observed_monotonic_ns=observed_ns,
        )
        if schedule is not None and observed_ns < schedule.end_monotonic_ns:
            result.schedule_valid = True
        if observed_ns > 0:
            result.host_clock_valid = True
        return result

    def collect_transport_summary(self) -> None:
        summary = collect_transport_summary(
            self.adapter,
            self.trial.transport_start,
            self._warning_occurrence,
        )
        self.trial.transport_summary = summary.counters
        self.trial.transport_observed_ns = summary.observed_ns

    def _fill_transport_summary(self, evidence: acq.WorkerLifecycleEvidence) -> None:
        if self.trial.transport_observed_ns is None:
            return
        summary = evidence.finished.transport_summary
        summary.camera = self.bootstrap.context.camera
        summary.observed_monotonic_ns = self.trial.transport_observed_ns
        if self.trial.transport_summary is not None:
            for field in TRANSPORT_COUNTER_FIELDS:
                value = self.trial.transport_summary[field]
                if value is not None:
                    setattr(summary, field, value)
