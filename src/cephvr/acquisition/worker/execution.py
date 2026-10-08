"""Serialized worker camera operations and bounded coordinator reporting (A01/A02)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from threading import Event, Lock

from cephvr.acquisition.camera.basler import BaslerCameraAdapter
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns

from .camera_configuration import WorkerCameraConfiguration
from .capture_runtime import WorkerCaptureResources
from .cleanup_lifecycle import WorkerCleanupLifecycle
from .health import WorkerHealthReporter
from .ports import command_from
from .preview_lifecycle import WorkerPreviewLifecycle
from .recording_runtime import WorkerRecordingRuntime
from .report_dispatch import WorkerReportDispatcher
from .reports import CoordinatorReportClient, SupervisorErrorClient
from .state import WorkerBootstrap, WorkerState
from .trial_lifecycle import WorkerTrialLifecycle


class WorkerOperationExecutor:
    """Own camera SDK actions on the camera owner thread and retain each outcome."""

    def __init__(
        self,
        bootstrap: WorkerBootstrap,
        state: WorkerState,
        adapter: BaslerCameraAdapter,
        captures: WorkerCaptureResources,
        reports: CoordinatorReportClient,
        loop: asyncio.AbstractEventLoop,
        shutdown_requested: asyncio.Event,
        shutdown_deadline: Callable[[int], None],
        recording: WorkerRecordingRuntime | None = None,
        external_wake: Callable[[], None] = lambda: None,
        supervisor_errors: SupervisorErrorClient | None = None,
    ) -> None:
        self.bootstrap = bootstrap
        self.state = state
        self.adapter = adapter
        self.captures = captures
        self.reports = reports
        self.loop = loop
        self.shutdown_requested = shutdown_requested
        self.shutdown_deadline = shutdown_deadline
        self.recording = recording
        self.external_wake = external_wake
        self.supervisor_errors = supervisor_errors
        limits = state.limits
        if limits is None:
            raise ValueError("worker state has no adopted control limits")
        self.report_dispatcher = WorkerReportDispatcher(
            loop,
            state,
            reports,
            limits.max_records,
            lambda details: self.coordinator_lost(details=details),
        )
        self.health = WorkerHealthReporter(
            bootstrap,
            state,
            reports,
            supervisor_errors,
            self.report_dispatcher.dispatch,
            external_wake,
        )
        self._session_ready = False
        self.camera_configuration = WorkerCameraConfiguration(
            adapter, state, lambda: self.preview.manual_preview
        )
        self._cleanup_resources: dict[str, bool] = {}
        self._latest_work = (
            control.WorkContext.FromString(
                bootstrap.context.work.SerializeToString(deterministic=True)
            )
            if bootstrap.context.HasField("work")
            else None
        )
        self._cancelled = Event()
        self._coordinator_loss = Event()
        self._coordinator_loss_handled = False
        self._coordinator_loss_deadline_ns: int | None = None
        self._coordinator_loss_details: str | None = None
        self._cleanup_continuation_limit = limits.safety_reserve_records
        self.cleanup = WorkerCleanupLifecycle(
            state,
            adapter,
            captures,
            recording,
            capacity=self._cleanup_continuation_limit,
            extra_resources=lambda: self._cleanup_resources,
            report_lifecycle=self._report_lifecycle,
            report_operation=self._report,
            shutdown=self._request_shutdown,
            recording_reconciled=lambda: self.trial.clear_recording_future(),
            external_wake=external_wake,
        )
        self.trial = WorkerTrialLifecycle(
            bootstrap,
            state,
            adapter,
            captures,
            recording,
            report_lifecycle=self._report_lifecycle,
            source=self._source,
            warning_occurrence=self.health.warning_occurrence,
            recording_warning_occurrence=self.health.recording_warning_occurrence,
            begin_warning_scope=self._begin_warning_scope,
            complete_warning_scope=self._complete_warning_scope,
            external_wake=external_wake,
            recording_first_frame=self.recording_first_frame,
            recording_isolated=self._recording_isolated,
            require_ready_session=self._require_ready_session,
            capability_resource_released=self._capability_resource_released,
        )
        self.preview = WorkerPreviewLifecycle(
            state,
            captures,
            adapter,
            begin_warning_scope=self._begin_warning_scope,
            complete_warning_scope=self._complete_warning_scope,
            verify_wait=self._verify_blocking_wait,
            operation_deadline=self._operation_deadline,
            report_lifecycle=self._report_lifecycle,
            owner_failure=self.owner_failed,
            recovery_ns=bootstrap.control_policies.recovery_ns,
        )

    def execute(self, name: str, raw_request: object, deadline_ns: int) -> None:
        """Complete admitted work; a failure remains queryable and is reported."""
        request = raw_request
        command = command_from(request)
        if command.target.HasField("work"):
            self._latest_work = control.WorkContext.FromString(
                command.target.work.SerializeToString(deterministic=True)
            )
        report = acq.WorkerOperationReport(source=self._source(command.target))
        success = False
        failure: control.Failure | None = None
        try:
            if self._coordinator_loss_handled and name not in {
                "InterruptSession",
                "Cleanup",
                "Shutdown",
                "StopTrial",
                "StopPreview",
                "CancelSetup",
                "RecordPulseEvidence",
            }:
                raise RuntimeError("worker operation was fenced after coordinator loss")
            if host_time_ns() >= deadline_ns:
                raise TimeoutError("original worker operation deadline expired")
            if name == "ResolveCameraConfiguration":
                if not isinstance(request, acq.WorkerResolveCamera):
                    raise TypeError("resolve request has the wrong protobuf type")
                report.resolved_camera.CopyFrom(
                    self.camera_configuration.resolve(request)
                )
                self.state.state_revision += 1
            elif name == "EditCamera":
                if not isinstance(request, acq.WorkerEditCamera):
                    raise TypeError("camera edit request has the wrong protobuf type")
                self.camera_configuration.edit(request, report)
            elif name == "PreparePreview":
                if not isinstance(
                    request, acq.WorkerPreparePreview
                ) or not request.HasField("camera"):
                    raise ValueError("preview preparation has no camera payload")
                self.camera_configuration.require_adopted_preview(request)
                self.preview.prepare(request)
            elif name == "StartPreview":
                self.preview.start(request)
            elif name == "StopPreview":
                self.preview.stop(request, deadline_ns)
            elif name == "SetupSession":
                self.camera_configuration.require_adopted_setup(request)
                if not isinstance(
                    request, acq.WorkerSetupSession
                ) or not request.HasField("camera"):
                    raise ValueError("session Setup payload is missing")
                policy = self.bootstrap.file_policy
                if (
                    not policy.HasField("post_cutoff_drain_margin_ns")
                    or policy.post_cutoff_drain_margin_ns <= 0
                ):
                    raise ValueError(
                        "camera Setup lacks a positive post-cutoff drain allowance"
                    )
                self._begin_warning_scope(
                    request.command.target.work,
                    configuration_revision=request.configuration_revision,
                )
                self.trial.pulse_required = (
                    request.camera.device.frame_timing
                    == camera.FRAME_TIMING_EXTERNAL_TRIGGER
                )
                attached = self.captures.prepare(
                    request.camera,
                    session_preview=request.camera.capture.session_preview_max_hz > 0,
                )
                self._verify_blocking_wait(deadline_ns)
                self.trial.recording_preparation.prepare_session(request)
                self._session_ready = True
                ready = acq.WorkerLifecycleEvidence()
                ready.ready.configuration_revision = request.configuration_revision
                ready.ready.required_checks_passed = True
                for resource in attached:
                    ready.ready.attached_resources.add().CopyFrom(resource)
                self._report_lifecycle(request, ready, deadline_ns)
            elif name == "PrepareTrial":
                self._require_ready_session(request)
                if not isinstance(request, acq.WorkerPrepareTrial):
                    raise TypeError("trial preparation has the wrong protobuf type")
                self._begin_warning_scope(request.command.target.work)
                self.trial.prepare_trial_state(request, deadline_ns)
                self.trial.recording_preparation.prepare_trial(request, deadline_ns)
                self.trial.trial_prepared = True
                evidence = acq.WorkerLifecycleEvidence()
                evidence.ready.configuration_revision = (
                    self.state.confirmed_configuration_revision
                )
                evidence.ready.required_checks_passed = True
                self._report_lifecycle(request, evidence, deadline_ns)
            elif name == "ScheduleTrial":
                self._schedule(request, deadline_ns)
            elif name == "ReleaseTrial":
                self._release(request, deadline_ns)
            elif name == "RecordPulseEvidence":
                self.trial.record_pulse_evidence(request)
            elif name == "StopTrial":
                self.trial.stop_request = request
                self.trial.stop_trial(deadline_ns, report_stopped=True)
                self.trial.report_camera_finished(request, deadline_ns)
            elif name == "CancelSetup":
                if self.recording is not None and self.recording.enabled:
                    self.recording.cancel_before_start(deadline_ns=deadline_ns)
                self._session_ready = False
                self.trial.trial_prepared = False
            elif name == "InterruptSession":
                self._cancelled.set()
                self.trial.stop_request = request
                self.trial.stop_trial(deadline_ns)
                self.trial.report_camera_finished(request, deadline_ns)
                self._session_ready = False
            elif name in {"Cleanup", "Shutdown"}:
                self._cancelled.set()
                self.trial.stop_request = request
                self.trial.stop_trial(deadline_ns)
                if not self.cleanup.begin_operation(name, request, deadline_ns, report):
                    return
            else:
                raise RuntimeError(f"unknown worker operation {name!r}")
            if host_time_ns() >= deadline_ns:
                raise TimeoutError(
                    "worker operation completed after its original deadline"
                )
            success = True
        except BaseException as exc:
            logging.getLogger(__name__).error(
                "%s %s %s failed: %s: %s",
                self.state.context.worker.role,
                name,
                command.command_id,
                type(exc).__name__,
                exc,
            )
            failure = control.Failure(code=_failure_code(exc), message=str(exc)[:2048])
        now_ns = host_time_ns()
        operation = self.state.complete_operation(
            command.command_id,
            succeeded=success,
            progress="complete" if success else "failed",
            now_ns=now_ns,
            failure=failure,
            retained_result=report,
        )
        _ = operation
        self._report(report, deadline_ns)
        finalize_scope = success and (
            name in {"Cleanup", "Shutdown"}
            or (
                name in {"StopTrial", "InterruptSession"}
                and (self.recording is None or not self.recording.enabled)
            )
        )
        if finalize_scope:
            self._finalize_work_scope(command.target.work)
            if name in {"Cleanup", "Shutdown"}:
                self.state.finalize_terminal_command(command.command_id, host_time_ns())

    def failed(self, name: str, exc: BaseException) -> None:
        """Retain an owner-loop failure without claiming an operation succeeded."""
        for operation in tuple(self.state.operations.values()):
            if operation.complete or operation.command != name:
                continue
            failure = control.Failure(
                code="WORKER_OWNER_FAILURE", message=str(exc)[:2048]
            )
            command_id = operation.context.command_id
            done = self.state.complete_operation(
                command_id,
                succeeded=False,
                progress="owner_failed",
                now_ns=host_time_ns(),
                failure=failure,
            )
            retained = self.state.commands.get(command_id)
            if (
                retained is not None
                and retained.result is not None
                and retained.deadline_ns is not None
            ):
                report = acq.WorkerOperationReport.FromString(retained.result)
                self._report(report, retained.deadline_ns)
            _ = done

    def owner_failed(self, exc: BaseException) -> None:
        self.health.owner_failed(exc)

    def _require_ready_session(self, request: object) -> None:
        command = command_from(request)
        if not command.target.HasField("work"):
            raise ValueError("trial operation has no exact work context")
        if not self._session_ready:
            raise RuntimeError("worker session is not prepared")
        required = getattr(request, "required_configuration_revision", None)
        if (
            required is not None
            and required != self.state.confirmed_configuration_revision
        ):
            raise RuntimeError("trial configuration revision is stale")

    def _schedule(self, request: object, deadline_ns: int) -> None:
        self.trial.schedule(request, deadline_ns)

    def _release(self, request: object, deadline_ns: int) -> None:
        self.trial.release(request, deadline_ns)

    def _stop_trial(self, deadline_ns: int) -> None:
        self.trial.stop_trial(deadline_ns)

    def _operation_deadline(self, command_id: str) -> int:
        retained = self.state.commands.get(command_id)
        if retained is None or retained.deadline_ns is None:
            raise RuntimeError("worker operation has no retained absolute deadline")
        return retained.deadline_ns

    def _finalize_work_scope(self, work: control.WorkContext) -> None:
        self.state.finalize_scope(work, host_time_ns())

    def _request_shutdown(self, deadline_ns: int) -> None:
        self.shutdown_deadline(deadline_ns)
        self.loop.call_soon_threadsafe(self.shutdown_requested.set)

    def _report(self, report: acq.WorkerOperationReport, deadline_ns: int) -> None:
        if report.operation.context.command_id in self.state.supervisor_command_ids:
            return
        self.report_dispatcher.operation(report, deadline_ns)

    def _report_lifecycle(
        self,
        request: object,
        evidence: acq.WorkerLifecycleEvidence,
        deadline_ns: int,
    ) -> None:
        command = command_from(request)
        evidence.source.CopyFrom(self._source(command.target))
        evidence.operation.command_id = command.command_id
        evidence.state_revision = self.state.state_revision + 1
        self.state.retain_lifecycle(evidence)
        if command.command_id in self.state.supervisor_command_ids:
            return
        self.report_dispatcher.lifecycle(evidence, deadline_ns)

    def advance_due_stages(self) -> None:
        if self._coordinator_loss.is_set() and not self._coordinator_loss_handled:
            self._handle_coordinator_loss()
        self.preview.advance_due_stage()
        self.trial.advance_due_stages()
        self.cleanup.advance()
        self._refresh_health_snapshot()

    def coordinator_lost(self, *, details: str | None = None) -> None:
        """Fence new work and ask the serialized owner to stop local activity."""
        with self.state.lock:
            self.state.interrupted = True
        if not self._coordinator_loss.is_set():
            self._coordinator_loss_details = details
            self._coordinator_loss_deadline_ns = (
                host_time_ns() + self.bootstrap.control_policies.recovery_ns
            )
        self._coordinator_loss.set()
        self.external_wake()

    def _handle_coordinator_loss(self) -> None:
        self._coordinator_loss_handled = True
        self._cancelled.set()
        self.preview.fence()
        deadline_ns = self._coordinator_loss_deadline_ns
        if deadline_ns is None:
            raise RuntimeError("coordinator loss has no retained detection deadline")
        self.health.coordinator_lost(details=self._coordinator_loss_details)
        self.trial.stop_trial(deadline_ns)
        self.cleanup.begin_ambient_release(deadline_ns)

    def next_deadline_ns(self) -> int | None:
        deadlines = [
            value
            for value in (
                self.trial.next_deadline_ns(),
                self.preview.next_deadline_ns,
            )
            if value is not None
        ]
        return min(deadlines) if deadlines else None

    def _refresh_health_snapshot(self) -> None:
        if self.state.health_active_error is not None:
            self.state.update_continuing_snapshot(
                self.trial.continuing_functions(host_time_ns())
            )
        schedule = self.trial.scheduled
        last_progress_ns: int | None = None
        capture = self.captures.capture
        if capture is not None and capture.last_usable_ns > 0:
            last_progress_ns = capture.last_usable_ns
        work: control.WorkContext | None
        if schedule is not None and schedule.command.target.HasField("work"):
            work = schedule.command.target.work
            trial_phase = (
                control.TRIAL_PHASE_FINALIZING
                if self.trial.terminal_pending
                else control.TRIAL_PHASE_ENDED
                if self.trial.end_marker is not None
                else control.TRIAL_PHASE_RUNNING
                if self.captures.active
                else control.TRIAL_PHASE_STARTING
            )
        else:
            work = self._latest_work
            trial_phase = None
        closed = work is not None and (
            self.state.health_work == work
            and self.state.health_session_phase == control.SESSION_PHASE_ENDED
            or any(
                evidence.source.work == work
                and evidence.WhichOneof("evidence") == "cleanup"
                and evidence.cleanup.resources
                and all(
                    item.released and not item.HasField("failure")
                    for item in evidence.cleanup.resources
                )
                for evidence in self.state.lifecycle.values()
            )
        )
        session_phase = (
            control.SESSION_PHASE_ENDED
            if closed
            else control.SESSION_PHASE_FINALIZING
            if self.state.interrupted
            else control.SESSION_PHASE_READY
            if self._session_ready
            else control.SESSION_PHASE_SETTING_UP
            if self.state.registered
            else control.SESSION_PHASE_CONFIGURATION
        )
        self.state.update_health_snapshot(
            work=work,
            session_phase=session_phase,
            trial_phase=trial_phase,
            progress_required=self.captures.active,
            last_progress_ns=last_progress_ns,
            observed_ns=host_time_ns(),
        )

    def refresh_health_snapshot(self) -> None:
        """Refresh owner-published progress after serialized work advances."""
        self._refresh_health_snapshot()

    def warning_occurrence(self, occurrence: object) -> None:
        from .warnings import WarningOccurrence

        if isinstance(occurrence, WarningOccurrence):
            self.health.warning_occurrence(occurrence)

    def recording_warning_occurrence(
        self,
        code: str,
        native_code: str | None,
        details: str | None,
        observed_ns: int,
        frame_id: int | None,
    ) -> None:
        self.health.recording_warning_occurrence(
            code, native_code, details, observed_ns, frame_id
        )

    def camera_first_frame(self, record: object) -> None:
        if self.preview.first_usable_frame(record):
            return
        self.trial.camera_first_frame(record)

    def recording_first_frame(self, observed_ns: int) -> None:
        self.trial.recording_first_frame(observed_ns)

    def _recording_isolated(
        self,
        work: control.WorkContext,
        operation_id: str,
        observed_ns: int,
        resource_ids: tuple[str, ...],
        details: str,
        cleanup_confirmed: bool,
        capture_function: control.ContinuingFunctionEvidence,
    ) -> None:
        self.health.recording_isolated(
            work=work,
            operation_id=operation_id,
            observed_ns=observed_ns,
            resource_ids=resource_ids,
            details=details,
            cleanup_confirmed=cleanup_confirmed,
            capture_function=capture_function,
        )

    def flush_warnings(self, deadline_ns: int) -> None:
        self.health.flush(deadline_ns)

    def _begin_warning_scope(
        self,
        work: control.WorkContext,
        *,
        configuration_revision: int | None = None,
        preview_run_id: str | None = None,
    ) -> None:
        if self.state.warnings is not None:
            self.state.warnings.begin_scope(
                work,
                configuration_revision=configuration_revision,
                preview_run_id=preview_run_id,
            )

    def _complete_warning_scope(self) -> None:
        if self.state.warnings is not None:
            try:
                self.state.warnings.complete_scope()
            except RuntimeError:
                pass

    def _verify_blocking_wait(self, deadline_ns: int) -> None:
        remaining = deadline_ns - host_time_ns()
        if remaining <= 0:
            raise TimeoutError("camera wait compatibility deadline expired")
        timeout_ns = min(250_000_000, remaining)
        delay_s = min(0.01, timeout_ns / 2_000_000_000)
        cancelled = Event()
        callback_lock = Lock()
        acknowledgement = Event()
        handles: list[asyncio.TimerHandle] = []

        def fire(wake_private_event: Callable[[], None]) -> None:
            with callback_lock:
                if cancelled.is_set():
                    return
                wake_private_event()
                acknowledgement.set()

        def register(wake_private_event: Callable[[], None]) -> None:
            with callback_lock:
                if cancelled.is_set():
                    return
                handles.append(self.loop.call_later(delay_s, fire, wake_private_event))

        def schedule_wake(wake_private_event: Callable[[], None]) -> Event:
            self.loop.call_soon_threadsafe(register, wake_private_event)
            return acknowledgement

        try:
            self.adapter.verify_blocking_wait_wakeup(schedule_wake, timeout_ns)
        finally:
            with callback_lock:
                cancelled.set()

            def cancel_handles() -> None:
                for handle in handles:
                    handle.cancel()

            def cancel_on_loop() -> None:
                cancel_handles()

            self.loop.call_soon_threadsafe(cancel_on_loop)

    def _capability_resource_released(self, resource: str, released: bool) -> None:
        if not resource or "\x00" in resource:
            self.state.interrupted = True
            raise ValueError("capability cleanup evidence has an invalid resource ID")
        self._cleanup_resources[resource] = released

    def _source(self, target: acq.WorkerContext) -> acq.WorkerContext:
        source = acq.WorkerContext()
        source.CopyFrom(self.bootstrap.context)
        if target.HasField("work"):
            source.work.CopyFrom(target.work)
        return source


def _failure_code(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "DEADLINE_EXCEEDED"
    if isinstance(exc, ValueError):
        return "INVALID_REQUEST"
    return "WORKER_OPERATION_FAILED"
