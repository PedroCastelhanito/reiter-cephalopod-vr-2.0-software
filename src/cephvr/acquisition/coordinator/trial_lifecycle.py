"""Aggregate exact camera trial lifecycle evidence into owner reports (E05/E08)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from copy import deepcopy

from cephvr.acquisition.coordinator.session_payloads import role_name
from cephvr.acquisition.ports import ControllerPort
from cephvr.acquisition.state import (
    CoordinatorIdentity,
    SessionSlot,
    TrialRecord,
    WorkerRecord,
)
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger

from .trial_delivery import TrialReportDelivery
from .trial_helpers import _external_roles
from .trial_validation import (
    TrialLifecycleValidation,
    empty_video_exception,
    finished_cutoff_ns,
    finished_is_timely,
    pulse_off_satisfies_trial,
    valid_pulse,
)


class TrialLifecycleReports:
    """Require all required camera workers before publishing trial lifecycle."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        session_slot: SessionSlot,
        workers: dict[int, WorkerRecord],
        controller: ControllerPort,
        policies: control.ControlPolicies,
        commands: CommandLedger,
        lock: asyncio.Lock,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.session_slot = session_slot
        self.workers = workers
        self.policies = policies
        self.lock = lock
        self.clock = clock
        self.validation = TrialLifecycleValidation()
        self.delivery = TrialReportDelivery(
            session_slot=session_slot,
            workers=workers,
            controller=controller,
            commands=commands,
            clock=clock,
        )

    async def report(
        self,
        worker: WorkerRecord,
        evidence: acq.WorkerLifecycleEvidence,
        *,
        ingress_ns: int,
    ) -> control.ReportReceipt:
        kind = evidence.WhichOneof("evidence")
        session = self.session_slot.current
        trial = session.trial if session is not None else None
        if session is None or trial is None or evidence.source.work != trial.work:
            return _rejected(
                "STALE_TRIAL", "lifecycle evidence is not current trial work"
            )
        if kind not in {"started", "stopped", "finished"}:
            return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)
        if kind == "started":
            return await self._started(worker, evidence, trial, ingress_ns)
        if kind == "stopped":
            return await self._stopped(worker, evidence, trial, ingress_ns)
        return await self._finished(worker, evidence, trial, ingress_ns)

    async def pulse_evidence_changed(self, trial: TrialRecord) -> None:
        """Retry aggregates whose final prerequisite is the retained pulse result."""
        session = self.session_slot.current
        if session is None or session.trial is not trial:
            return
        for worker in self.workers.values():
            evidence = _matching(worker, trial, "started")
            if evidence is not None:
                await self._started(worker, evidence, trial, self.clock())
            evidence = _matching(worker, trial, "stopped")
            if evidence is not None:
                await self._stopped(worker, evidence, trial, self.clock())

    def validate_started(
        self,
        worker: WorkerRecord,
        evidence: acq.WorkerLifecycleEvidence,
        *,
        ingress_ns: int,
    ) -> None:
        session = self.session_slot.current
        self.validation.validate_started(
            worker,
            evidence,
            session,
            session.trial if session is not None else None,
            ingress_ns=ingress_ns,
            allowance_ns=self.policies.start_evidence_allowance_ns,
        )

    def validate_stopped(
        self,
        worker: WorkerRecord,
        evidence: acq.WorkerLifecycleEvidence,
        *,
        ingress_ns: int,
    ) -> None:
        session = self.session_slot.current
        self.validation.validate_stopped(
            worker,
            evidence,
            session,
            session.trial if session is not None else None,
            ingress_ns=ingress_ns,
        )

    def validate_finished(
        self, worker: WorkerRecord, evidence: acq.WorkerLifecycleEvidence
    ) -> None:
        session = self.session_slot.current
        self.validation.validate_finished(
            worker, evidence, session, session.trial if session is not None else None
        )

    async def _started(
        self,
        worker: WorkerRecord,
        evidence: acq.WorkerLifecycleEvidence,
        trial: TrialRecord,
        ingress_ns: int,
    ) -> control.ReportReceipt:
        item = evidence.started
        worker_trial = worker.trial
        cutoff = (
            trial.start_monotonic_ns + self.policies.start_evidence_allowance_ns
            if trial.start_monotonic_ns is not None
            else 0
        )
        child = worker.child_operations.get(evidence.operation.command_id)
        if (
            cutoff <= 0
            or ingress_ns > cutoff
            or worker_trial is None
            or worker_trial.schedule is None
            or worker_trial.schedule.command_id != evidence.operation.command_id
            or child is None
            or child.kind != "schedule_trial"
            or not item.HasField("actual_start_monotonic_ns")
            or not item.first_activity
            or item.actual_start_monotonic_ns < (trial.start_monotonic_ns or 0)
            or item.actual_start_monotonic_ns > cutoff
        ):
            return _rejected(
                "INVALID_STARTED", "Started evidence differs from E05 schedule"
            )
        try:
            self.validate_started(worker, evidence, ingress_ns=ingress_ns)
        except ValueError as exc:
            return _rejected("INVALID_STARTED", str(exc))
        session = self.session_slot.current
        if session is None:
            return _rejected("STALE_TRIAL", "trial session ended")
        if _external_roles(session) and not valid_pulse(
            trial.pulse_on,
            command=mcu.PULSE_BOUNDARY_COMMAND_ON,
            boundary_ns=trial.start_monotonic_ns,
        ):
            return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)
        async with self.lock:
            session = self.session_slot.current
            if session is None or session.trial is not trial:
                return _rejected(
                    "STALE_TRIAL", "trial changed during Started aggregation"
                )
            if trial.started_report is not None:
                return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)
            if trial.pending_started_report is None:
                evidence_by_role: list[tuple[int, acq.WorkerStartedEvidence]] = []
                for role in sorted(session.required_cameras):
                    record = self.workers.get(role)
                    found = _matching(record, trial, "started") if record else None
                    if found is None:
                        return control.ReportReceipt(
                            result=control.COMMAND_RESULT_ACCEPTED
                        )
                    if (
                        record is None
                        or record.trial is None
                        or record.trial.schedule is None
                    ):
                        return _rejected(
                            "STARTED_MISSING", "camera schedule is not retained"
                        )
                    if found.operation.command_id != record.trial.schedule.command_id:
                        return _rejected(
                            "STARTED_STALE", "camera Started command is stale"
                        )
                    evidence_by_role.append((role, found.started))
                actual = min(
                    next(
                        activity.observed_monotonic_ns
                        for activity in item.first_activity
                        if activity.kind == "camera_callback"
                    )
                    for _, item in evidence_by_role
                )
                if actual > cutoff:
                    return _rejected(
                        "STARTED_LATE", "aggregate camera start missed E05 cutoff"
                    )
                report = control.StartedReport(
                    context=control.ReportContext(
                        backend=self.identity.backend,
                        work=trial.work,
                        operation=trial.preparation,
                    ),
                    actual_start_monotonic_ns=actual,
                )
                for _role, started in evidence_by_role:
                    report.first_required_activity.extend(
                        activity
                        for activity in started.first_activity
                        if activity.kind == "camera_callback"
                    )
                if trial.pulse_on is not None:
                    report.acquisition_pulse_on.CopyFrom(trial.pulse_on)
                trial.pending_started_report = report
            pending = deepcopy(trial.pending_started_report)
        return await self.delivery.deliver(trial, "started", pending, cutoff)

    async def _stopped(
        self,
        worker: WorkerRecord,
        evidence: acq.WorkerLifecycleEvidence,
        trial: TrialRecord,
        ingress_ns: int,
    ) -> control.ReportReceipt:
        item = evidence.stopped
        worker_trial = worker.trial
        cutoff = trial.stop_deadline_ns or 0
        child = worker.child_operations.get(evidence.operation.command_id)
        if (
            cutoff <= 0
            or ingress_ns > cutoff
            or worker_trial is None
            or worker_trial.stop is None
            or worker_trial.stop.command_id != evidence.operation.command_id
            or child is None
            or child.kind != "stop_trial"
            or not item.HasField("activity_stopped")
            or not item.activity_stopped
            or not item.HasField("actual_stop_monotonic_ns")
            or not item.HasField("recording_end_monotonic_ns")
            or item.recording_end_monotonic_ns <= 0
            or item.actual_stop_monotonic_ns > cutoff
        ):
            return _rejected(
                "INVALID_STOPPED", "Stopped evidence lacks exact E11 cutoff"
            )
        async with self.lock:
            session = self.session_slot.current
            if session is None or session.trial is not trial:
                return _rejected(
                    "STALE_TRIAL", "trial changed during Stopped aggregation"
                )
            if trial.stopped_report is not None:
                return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)
            if trial.pending_stopped_report is None:
                if _external_roles(session) and not pulse_off_satisfies_trial(trial):
                    return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)
                ended: list[tuple[WorkerRecord, acq.WorkerStoppedEvidence]] = []
                for role in sorted(session.required_cameras):
                    record = self.workers.get(role)
                    found = _matching(record, trial, "stopped") if record else None
                    if found is None:
                        return control.ReportReceipt(
                            result=control.COMMAND_RESULT_ACCEPTED
                        )
                    if (
                        record is None
                        or record.trial is None
                        or record.trial.stop is None
                    ):
                        return _rejected(
                            "STOPPED_MISSING", "camera stop is not retained"
                        )
                    if found.operation.command_id != record.trial.stop.command_id:
                        return _rejected(
                            "STOPPED_STALE", "camera Stopped command is stale"
                        )
                    ended.append((record, found.stopped))
                actual = max(item.actual_stop_monotonic_ns for _, item in ended)
                recording_required = {
                    output.output_tag.removesuffix("_cam")
                    for output in trial.outputs
                    if output.backend.backend_name == "acquisition"
                    and output.extension == "mp4"
                    and output.output_tag.endswith("_cam")
                }
                recording_sealed = all(
                    stopped.HasField("recording_interval_sealed")
                    and stopped.recording_interval_sealed
                    for record, stopped in ended
                    if role_name(record.context.camera) in recording_required
                )
                report = control.StoppedReport(
                    context=control.ReportContext(
                        backend=self.identity.backend,
                        work=trial.work,
                        operation=trial.preparation,
                    ),
                    actual_stop_monotonic_ns=actual,
                    trial_activity_stopped=True,
                )
                if recording_sealed:
                    report.recording_interval_sealed = True
                for record, stopped in ended:
                    report.producer_ends.add(
                        producer=record.launch.worker,
                        source_id=role_name(record.context.camera),
                        end_monotonic_ns=stopped.recording_end_monotonic_ns,
                    )
                if trial.pulse_off is not None:
                    report.acquisition_pulse_off.CopyFrom(trial.pulse_off)
                trial.pending_stopped_report = report
            pending = deepcopy(trial.pending_stopped_report)
        return await self.delivery.deliver(trial, "stopped", pending, cutoff)

    async def _finished(
        self,
        worker: WorkerRecord,
        evidence: acq.WorkerLifecycleEvidence,
        trial: TrialRecord,
        ingress_ns: int,
    ) -> control.ReportReceipt:
        worker_trial = worker.trial
        child = worker.child_operations.get(evidence.operation.command_id)
        if (
            worker_trial is None
            or worker_trial.stop is None
            or worker_trial.stop.command_id != evidence.operation.command_id
            or child is None
            or child.kind != "stop_trial"
            or not evidence.finished.HasField("activity_stopped")
            or not evidence.finished.activity_stopped
        ):
            return _rejected(
                "INVALID_FINISHED", "Finished evidence differs from exact stop"
            )
        finalization_cutoff = finished_cutoff_ns(
            trial, self.policies.trial_finished.initial_ns, ingress_ns
        )
        # Late closure is retained by WorkerRecord as recovery evidence, but cannot
        # be converted into a timely successful parent Finished report.
        if not finished_is_timely(
            trial, self.policies.trial_finished.initial_ns, ingress_ns
        ):
            return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)
        async with self.lock:
            session = self.session_slot.current
            if session is None or session.trial is not trial:
                return _rejected(
                    "STALE_TRIAL", "trial changed during Finished aggregation"
                )
            if trial.finished_report is not None:
                return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)
            if trial.pending_finished_report is None:
                parts: list[tuple[WorkerRecord, acq.WorkerFinishedEvidence]] = []
                for role in sorted(session.required_cameras):
                    record = self.workers.get(role)
                    found = _matching(record, trial, "finished") if record else None
                    if found is None:
                        return control.ReportReceipt(
                            result=control.COMMAND_RESULT_ACCEPTED
                        )
                    if (
                        record is None
                        or record.trial is None
                        or record.trial.stop is None
                    ):
                        return _rejected(
                            "FINISHED_MISSING", "camera stop is not retained"
                        )
                    if found.operation.command_id != record.trial.stop.command_id:
                        return _rejected(
                            "FINISHED_STALE", "camera Finished command is stale"
                        )
                    expected_role_keys = {
                        output.output_key
                        for output in trial.outputs
                        if output.backend == self.identity.backend
                        and output.output_tag.startswith(role_name(role) + "_cam")
                    }
                    reported_role_keys = [
                        output.output_key for output in found.finished.outputs
                    ]
                    if set(reported_role_keys) != expected_role_keys or len(
                        reported_role_keys
                    ) != len(set(reported_role_keys)):
                        return _rejected(
                            "FINISHED_OUTPUT_SCOPE",
                            "camera Finished outputs differ from its exact role plans",
                        )
                    parts.append((record, found.finished))
                outputs = [out for _, part in parts for out in part.outputs]
                output_keys = [out.output_key for out in outputs]
                expected = {
                    output.output_key
                    for output in trial.outputs
                    if output.backend == self.identity.backend
                }
                if (
                    set(output_keys) != expected
                    or len(output_keys) != len(set(output_keys))
                    or any(
                        out.closure
                        not in {
                            control.OUTPUT_CLOSURE_CLOSED,
                            control.OUTPUT_CLOSURE_FAILED,
                            control.OUTPUT_CLOSURE_NOT_STARTED,
                        }
                        or (
                            out.closure == control.OUTPUT_CLOSURE_NOT_STARTED
                            and not empty_video_exception(trial.outputs, outputs, out)
                        )
                        for out in outputs
                    )
                ):
                    return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)
                report = control.FinishedReport(
                    context=control.ReportContext(
                        backend=self.identity.backend,
                        work=trial.work,
                        operation=trial.preparation,
                    ),
                    trial_activity_stopped=True,
                )
                report.outputs.extend(outputs)
                summary_roles: set[int] = set()
                for record, part in parts:
                    if part.HasField("transport_summary"):
                        summary = part.transport_summary
                        if (
                            summary.camera != record.context.camera
                            or summary.camera in summary_roles
                        ):
                            return _rejected(
                                "FINISHED_SUMMARY_SCOPE",
                                "transport summary differs from exact camera role",
                            )
                        summary_roles.add(summary.camera)
                        report.acquisition_transport_summaries.add().CopyFrom(summary)
                trial.pending_finished_report = report
            pending = deepcopy(trial.pending_finished_report)
        return await self.delivery.deliver(
            trial, "finished", pending, finalization_cutoff
        )


def _matching(
    worker: WorkerRecord | None, trial: TrialRecord, kind: str
) -> acq.WorkerLifecycleEvidence | None:
    if worker is None:
        return None
    candidates = [
        item
        for item in worker.lifecycle_evidence.values()
        if item.source.work == trial.work and item.WhichOneof("evidence") == kind
    ]
    return max(candidates, key=lambda item: item.state_revision, default=None)


def _rejected(code: str, message: str) -> control.ReportReceipt:
    return control.ReportReceipt(
        result=control.COMMAND_RESULT_REJECTED,
        failure=control.Failure(code=code, message=message[:2048]),
    )
