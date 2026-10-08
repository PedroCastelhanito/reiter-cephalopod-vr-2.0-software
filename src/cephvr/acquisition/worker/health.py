"""Independent worker health, warning coalescing and fatal error reports (A02/A09)."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from threading import Lock
from typing import Any
from uuid import uuid4

from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns

from .reports import CoordinatorReportClient, SupervisorErrorClient
from .state import WorkerBootstrap, WorkerState
from .warnings import WarningOccurrence


class WorkerHealthReporter:
    """Own bounded worker warning views and direct fatal-owner reporting."""

    def __init__(
        self,
        bootstrap: WorkerBootstrap,
        state: WorkerState,
        reports: CoordinatorReportClient,
        supervisor_errors: SupervisorErrorClient | None,
        dispatch: Callable[[Coroutine[Any, Any, control.ReportReceipt]], None],
        external_wake: Callable[[], None],
    ) -> None:
        self.bootstrap = bootstrap
        self.state = state
        self.reports = reports
        self.supervisor_errors = supervisor_errors
        self._dispatch = dispatch
        self._external_wake = external_wake
        self._warning_lock = Lock()
        self._warnings_dirty = False

    def owner_failed(self, error: BaseException) -> None:
        """Report an owner-thread failure directly to the supervisor (E08)."""
        with self.state.lock:
            self.state.interrupted = True
        reporter = self.supervisor_errors
        if reporter is None:
            return
        now_ns = host_time_ns()
        request = control.ErrorReport(
            error_id=str(uuid4()),
            source=self.bootstrap.context.worker,
            occurred_monotonic_ns=now_ns,
            failure=control.Failure(
                code="WORKER_OWNER_FAILURE", message=str(error)[:2048]
            ),
        )
        if self.state.context.HasField("work"):
            request.work.CopyFrom(self.state.context.work)
        deadline_ns = now_ns + self.bootstrap.control_policies.recovery_ns
        try:
            self._dispatch(reporter.report_error(request, deadline_ns=deadline_ns))
        except BaseException:
            # Local interruption remains retained; supervisor silence monitoring is
            # the fallback when this bounded direct report cannot be delivered.
            return

    def coordinator_lost(self, *, details: str | None = None) -> None:
        """Tell the supervisor the worker has locally fenced after owner silence."""
        reporter = self.supervisor_errors
        if reporter is None:
            return
        now_ns = host_time_ns()
        request = control.ErrorReport(
            error_id=str(uuid4()),
            source=self.bootstrap.context.worker,
            occurred_monotonic_ns=now_ns,
            failure=control.Failure(
                code="COORDINATOR_HEALTH_LOST",
                message=(
                    details
                    or "coordinator heartbeat receipt exceeded the configured silence bound"
                )[:2048],
            ),
        )
        if self.state.context.HasField("work"):
            request.work.CopyFrom(self.state.context.work)
        deadline_ns = now_ns + self.bootstrap.control_policies.recovery_ns
        try:
            self._dispatch(reporter.report_error(request, deadline_ns=deadline_ns))
        except BaseException:
            return  # The fault is already in the local snapshot; no second channel exists.

    def recording_isolated(
        self,
        *,
        work: control.WorkContext,
        operation_id: str,
        observed_ns: int,
        resource_ids: tuple[str, ...],
        details: str,
        cleanup_confirmed: bool,
        capture_function: control.ContinuingFunctionEvidence,
    ) -> None:
        """Publish source-owned recording loss and the still-running capture path."""
        if resource_ids != self.state.recording_fault_resources():
            raise ValueError(
                "recording isolation differs from the prepared fault closure"
            )
        with self.state.lock:
            prior = self.state.health_active_error
            same_episode = bool(
                prior is not None
                and prior.failure.code == "RECORDING_PIPELINE_FAILURE"
                and prior.HasField("work")
                and prior.work == work
                and resource_ids
                and resource_ids[0] in prior.isolation.affected_resource_ids
                and prior.incident_episode_id
            )
            episode_id = (
                prior.incident_episode_id
                if same_episode and prior is not None
                else str(uuid4())
            )
            occurred_ns = (
                prior.occurred_monotonic_ns
                if same_episode and prior is not None
                else observed_ns
            )
        error = control.ErrorReport(
            error_id=str(uuid4()),
            source=self.bootstrap.context.worker,
            work=work,
            occurred_monotonic_ns=occurred_ns,
            failure=control.Failure(
                code="RECORDING_PIPELINE_FAILURE", message=details[:2048]
            ),
            incident_episode_id=episode_id,
        )
        if operation_id:
            error.operation.command_id = operation_id
        error.isolation.affected_resource_ids.extend(resource_ids)
        error.isolation.fenced_resource_ids.extend(resource_ids)
        if cleanup_confirmed:
            error.isolation.leases_released_or_quarantined = True
        error.isolation.verified_monotonic_ns = observed_ns

        camera_name = (
            "behavioral"
            if self.bootstrap.context.camera == camera_pb2.CAMERA_ROLE_BEHAVIORAL
            else "tracking"
        )
        capture = control.ContinuingFunctionEvidence()
        capture.CopyFrom(capture_function)
        capture.resource_id = f"{camera_name}.capture"
        recorder = control.ContinuingFunctionEvidence(
            resource_id=resource_ids[0] if resource_ids else "recording",
            functioning=False,
            observed_monotonic_ns=observed_ns,
        )
        if capture_function.HasField("schedule_valid"):
            recorder.schedule_valid = capture_function.schedule_valid
        if capture_function.HasField("host_clock_valid"):
            recorder.host_clock_valid = capture_function.host_clock_valid
        if capture_function.HasField("control_path_valid"):
            recorder.control_path_valid = capture_function.control_path_valid
        self.state.update_fault_snapshot(error, (capture, recorder))
        reporter = self.supervisor_errors
        if reporter is not None:
            deadline_ns = occurred_ns + self.bootstrap.control_policies.recovery_ns
            try:
                self._dispatch(reporter.report_error(error, deadline_ns=deadline_ns))
            except BaseException:
                pass  # The fault is already in the local snapshot (update_fault_snapshot).

    def warning_occurrence(self, occurrence: WarningOccurrence) -> None:
        warnings = self.state.warnings
        if warnings is None:
            return
        warnings.observe(occurrence)
        with self._warning_lock:
            self._warnings_dirty = True

    def recording_warning_occurrence(
        self,
        code: str,
        native_code: str | None,
        details: str | None,
        observed_ns: int,
        frame_id: int | None,
    ) -> None:
        """Forward writer-owned terminal warnings; capture owns per-frame counts."""
        if frame_id is not None:
            return
        self.warning_occurrence(
            WarningOccurrence(code, observed_ns, native_code, details or "")
        )
        self._external_wake()

    def flush(self, deadline_ns: int) -> None:
        """Dispatch the latest immutable warning views outside the data path."""
        with self._warning_lock:
            if not self._warnings_dirty:
                return
            self._warnings_dirty = False
        warnings = self.state.warnings
        if warnings is None:
            return
        for view in warnings.views():
            report = acq.WorkerWarningReport(source=self.bootstrap.context)
            report.view.CopyFrom(view)
            report.source.work.CopyFrom(view.work)
            self._dispatch(
                self.reports.report_warnings(report, deadline_ns=deadline_ns)
            )
