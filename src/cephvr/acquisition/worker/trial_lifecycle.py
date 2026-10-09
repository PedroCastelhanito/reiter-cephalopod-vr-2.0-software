"""Serialized trial, recording and capture lifecycle operations (A08/A09)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from cephvr.acquisition.buffers.end_marker import CaptureEndMarker
from cephvr.acquisition.buffers.records import FrameRecord
from cephvr.acquisition.camera.basler import BaslerCameraAdapter
from cephvr.acquisition.identity import camera_role_name
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control

from .capture_runtime import WorkerCaptureResources
from .recording_fault import RecordingFaultLifecycle
from .recording_preparation import TrialRecordingPreparation
from .recording_runtime import WorkerRecordingRuntime
from .state import WorkerBootstrap, WorkerState
from .transport_summary import TRANSPORT_COUNTER_FIELDS
from .trial_activity import TrialActivityEvidence
from .trial_state import WorkerTrialState
from .trial_stop import TrialStopFinalizer
from .warnings import WarningOccurrence

_TRANSPORT_COUNTER_FIELDS = TRANSPORT_COUNTER_FIELDS


class WorkerTrialLifecycle:
    """Own exact trial schedule, pulse evidence, cutoff and recording handoff."""

    def __init__(
        self,
        bootstrap: WorkerBootstrap,
        state: WorkerState,
        adapter: BaslerCameraAdapter,
        captures: WorkerCaptureResources,
        recording: WorkerRecordingRuntime | None,
        *,
        report_lifecycle: Callable[[object, acq.WorkerLifecycleEvidence, int], None],
        source: Callable[[acq.WorkerContext], acq.WorkerContext],
        warning_occurrence: Callable[[WarningOccurrence], None],
        recording_warning_occurrence: Callable[
            [str, str | None, str | None, int, int | None], None
        ],
        begin_warning_scope: Callable[..., None],
        complete_warning_scope: Callable[[], None],
        external_wake: Callable[[], None],
        recording_first_frame: Callable[[int], None],
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
        require_ready_session: Callable[[object], None],
        capability_resource_released: Callable[[str, bool], None],
    ) -> None:
        self.bootstrap = bootstrap
        self.state = state
        self.adapter = adapter
        self.captures = captures
        self.recording = recording
        self._report_lifecycle_callback = report_lifecycle
        self._source_callback = source
        self.warning_occurrence = warning_occurrence
        self.recording_warning_occurrence = recording_warning_occurrence
        self._begin_warning_scope = begin_warning_scope
        self._complete_warning_scope = complete_warning_scope
        self.external_wake = external_wake
        self.recording_first_frame_callback = recording_first_frame
        self._recording_isolated_callback = recording_isolated
        self._require_ready_session_callback = require_ready_session
        self._capability_resource_released_callback = capability_resource_released
        self.activity = TrialActivityEvidence(
            bootstrap, state, source, report_lifecycle
        )
        self.trial_state = WorkerTrialState()
        self._recording_fault = RecordingFaultLifecycle(
            recording_warning_occurrence, recording_isolated, external_wake
        )
        self.recording_preparation = TrialRecordingPreparation(
            bootstrap,
            adapter,
            captures,
            recording,
            operation_deadline=self._operation_deadline,
            first_frame_observed=recording_first_frame,
            warning_occurrence=recording_warning_occurrence,
            capability_resource_released=capability_resource_released,
        )
        self.stop_finalizer = TrialStopFinalizer(
            bootstrap,
            state,
            adapter,
            captures,
            recording,
            self.trial_state,
            self._recording_fault,
            report_lifecycle=report_lifecycle,
            source=source,
            operation_deadline=self._operation_deadline,
            complete_warning_scope=complete_warning_scope,
            external_wake=external_wake,
            recording_isolated=recording_isolated,
            warning_occurrence=warning_occurrence,
            recording_fault_observed=self._maybe_report_started,
        )

    @property
    def trial_prepared(self) -> bool:
        return self.trial_state.prepared

    @trial_prepared.setter
    def trial_prepared(self, value: bool) -> None:
        self.trial_state.prepared = value

    @property
    def pulse_required(self) -> bool:
        return self.trial_state.pulses.required

    @pulse_required.setter
    def pulse_required(self, value: bool) -> None:
        self.trial_state.pulses.reset(value)

    @property
    def scheduled(self) -> acq.WorkerSchedule | None:
        return self.trial_state.schedule

    @property
    def end_marker(self) -> CaptureEndMarker | None:
        return self.trial_state.end_marker

    @property
    def terminal_pending(self) -> bool:
        return self.trial_state.finished_future is not None

    @property
    def stop_request(self) -> object | None:
        return self.trial_state.stop_request

    @stop_request.setter
    def stop_request(self, request: object | None) -> None:
        if request is None or isinstance(
            request, (acq.WorkerStop, acq.WorkerInterrupt, acq.WorkerCommand)
        ):
            self.trial_state.stop_request = request
            return
        raise TypeError("stop request has the wrong protobuf type")

    def _report_lifecycle(
        self, request: object, evidence: acq.WorkerLifecycleEvidence, deadline_ns: int
    ) -> None:
        self._report_lifecycle_callback(request, evidence, deadline_ns)

    def report_camera_finished(self, request: object, deadline_ns: int) -> None:
        """Report capture completion for a non-saving camera after physical stop."""
        if self.recording is not None and self.recording.enabled:
            return
        marker = self.trial_state.end_marker
        if marker is None or marker.actual_stop_monotonic_ns is None:
            return
        evidence = acq.WorkerLifecycleEvidence()
        evidence.finished.activity_stopped = True
        if self.trial_state.transport_observed_ns is not None:
            summary = evidence.finished.transport_summary
            summary.camera = self.bootstrap.context.camera
            summary.observed_monotonic_ns = self.trial_state.transport_observed_ns
            if self.trial_state.transport_summary is not None:
                for field in _TRANSPORT_COUNTER_FIELDS:
                    value = self.trial_state.transport_summary[field]
                    if value is not None:
                        setattr(summary, field, value)
        self._report_lifecycle(request, evidence, deadline_ns)

    def _source(self, target: acq.WorkerContext) -> acq.WorkerContext:
        return self._source_callback(target)

    def _operation_deadline(self, command_id: str) -> int:
        retained = self.state.commands.get(command_id)
        if retained is None or retained.deadline_ns is None:
            raise RuntimeError("worker operation has no retained absolute deadline")
        return retained.deadline_ns

    def _schedule(self, request: object, deadline_ns: int) -> None:
        if not isinstance(request, acq.WorkerSchedule):
            raise TypeError("schedule request has the wrong type")
        if not self.trial_state.prepared:
            raise RuntimeError("trial was not prepared")
        if not request.HasField("start_monotonic_ns") or not request.HasField(
            "end_monotonic_ns"
        ):
            raise ValueError("schedule requires exact start and end boundaries")
        self.trial_state.schedule = acq.WorkerSchedule.FromString(
            request.SerializeToString(deterministic=True)
        )
        self.trial_state.stopped_schedule = None
        self.activity.reset()
        work = request.command.target.work
        if work.WhichOneof("work") != "trial" or not work.trial.trial_id:
            raise ValueError("trial schedule has no exact UUID trial identity")
        try:
            run_id = UUID(work.trial.trial_id)
        except ValueError as exc:
            raise ValueError("trial schedule identity is not a UUID") from exc
        self.captures.schedule(
            request.start_monotonic_ns, request.end_monotonic_ns, run_id
        )
        if (
            self.recording is not None
            and self.recording.enabled
            and not self._recording_fault.faulted_session
        ):
            self.recording.schedule(request, deadline_ns=deadline_ns)

    def _release(self, request: object, deadline_ns: int) -> None:
        if not isinstance(request, acq.WorkerRelease):
            raise TypeError("release request has the wrong type")
        scheduled = self.trial_state.schedule
        if scheduled is None or not request.HasField("schedule_operation"):
            raise RuntimeError("release has no retained schedule")
        if (
            request.schedule_operation.command_id != scheduled.command.command_id
            or request.start_monotonic_ns != scheduled.start_monotonic_ns
            or request.end_monotonic_ns != scheduled.end_monotonic_ns
        ):
            raise ValueError("release does not match the exact retained schedule")
        self.trial_state.released = True
        self.captures.release_schedule()
        if (
            self.recording is not None
            and self.recording.enabled
            and not self._recording_fault.faulted_session
        ):
            self.recording.release(request, deadline_ns=deadline_ns)

    def schedule(self, request: object, deadline_ns: int) -> None:
        self._schedule(request, deadline_ns)

    def release(self, request: object, deadline_ns: int) -> None:
        self._release(request, deadline_ns)

    def stop_trial(self, deadline_ns: int, *, report_stopped: bool = False) -> None:
        self.stop_finalizer.stop_trial(deadline_ns, report_stopped=report_stopped)

    def advance_due_stages(self) -> None:
        self.stop_finalizer.advance_due_stages()

    def next_deadline_ns(self) -> int | None:
        return self.captures.next_deadline_ns()

    def clear_recording_future(self) -> None:
        self.trial_state.finished_future = None

    def recording_trial_installed(self) -> bool:
        return self.recording is not None and self.recording.recording_queue is not None

    def continuing_functions(
        self, observed_ns: int
    ) -> tuple[control.ContinuingFunctionEvidence, ...]:
        if not self._recording_fault.faulted_session:
            return ()
        role = camera_role_name(self.bootstrap.context.camera)
        recorder = control.ContinuingFunctionEvidence(
            resource_id=f"{role}.recording",
            functioning=False,
            control_path_valid=True,
            observed_monotonic_ns=observed_ns,
        )
        return (
            self.stop_finalizer.capture_continuing_snapshot(observed_ns),
            recorder,
        )

    def prepare_trial_state(self, request: object, deadline_ns: int) -> None:
        """Reset capture-owned trial state before optional recording preparation."""
        if not isinstance(request, acq.WorkerPrepareTrial):
            raise TypeError("trial preparation has the wrong protobuf type")
        command = request.command
        if (
            not command.HasField("target")
            or not command.target.HasField("work")
            or command.target.work.WhichOneof("work") != "trial"
            or not command.target.work.trial.trial_id
        ):
            raise ValueError("trial preparation lacks exact trial identity")
        if self.trial_state.schedule is not None or self.captures.active:
            raise RuntimeError("prior trial capture has not closed")
        if self.trial_state.finished_future is not None:
            if not self.trial_state.finished_future.done():
                raise RuntimeError("prior recording closure is still pending")
            raise RuntimeError("prior recording closure was not reconciled")

        try:
            run_id = UUID(command.target.work.trial.trial_id)
        except ValueError as exc:
            raise ValueError("trial preparation identity is not a UUID") from exc
        if run_id.int == 0 or run_id.version != 4:
            raise ValueError("trial preparation identity must be UUIDv4")

        self.trial_state.end_marker = None
        self.trial_state.purge_evidence = None
        self.trial_state.stop_request = None
        self.trial_state.finish_deadline_ns = None
        self.trial_state.transport_start = None
        self.trial_state.transport_summary = None
        self.trial_state.transport_observed_ns = None
        self.trial_state.finished_future = None
        self._recording_fault.outputs = None
        self.activity.reset()
        self.trial_state.pulses.reset(self.trial_state.pulses.required)
        self.captures.prepare_trial(
            run_id,
            deadline_ns,
            should_continue_drain=self.captures.should_continue_drain,
        )
        try:
            self.trial_state.transport_start = self.adapter.read_transport_counters()
        except BaseException:
            self.trial_state.transport_start = None

    def record_pulse_evidence(self, request: object) -> None:
        self._require_ready_session_callback(request)
        self.trial_state.pulses.record(
            request,
            self.trial_state.schedule or self.trial_state.stopped_schedule,
            self.bootstrap.context.camera,
        )
        if (
            self.trial_state.end_marker is not None
            and self.trial_state.finish_deadline_ns is not None
            and self.trial_state.pulses.on is not None
            and self.trial_state.pulses.off is not None
        ):
            self.stop_finalizer.publish_if_ready(self.trial_state.finish_deadline_ns)

    def camera_first_frame(self, record: object) -> None:
        if not isinstance(record, FrameRecord):
            raise TypeError("first camera activity lacks an exact frame record")
        self.activity.camera_frame(record)
        self._maybe_report_started()

    def recording_first_frame(self, observed_ns: int) -> None:
        self.activity.recording_frame(observed_ns)
        self._maybe_report_started()

    def _maybe_report_started(self) -> None:
        saving = (
            self.recording is not None
            and self.recording.enabled
            and not self._recording_fault.faulted_session
        )
        self.activity.publish_if_ready(
            self.trial_state.schedule, recording_required=saving
        )
