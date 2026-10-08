"""Validate and retain exact worker lifecycle evidence (E05/E06/E08)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from copy import deepcopy

from cephvr.acquisition.coordinator.evidence_cleanup import WorkerCleanupEvidence
from cephvr.acquisition.coordinator.evidence_helpers import (
    _report_rejected,
    matching_session,
    record_for_source,
)
from cephvr.acquisition.coordinator.evidence_ready import WorkerReadyReports
from cephvr.acquisition.coordinator.manual_preview_evidence import ManualPreviewEvidence
from cephvr.acquisition.coordinator.trial_lifecycle import TrialLifecycleReports
from cephvr.acquisition.ports import ControllerPort
from cephvr.acquisition.state import (
    ChildOperation,
    ResourceRecord,
    SessionRecord,
    TrialRecord,
    WorkerRecord,
)
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.resource_ledger import NativeResourceLedger
from cephvr.shared.commands import CommandLedger


class WorkerLifecycleReports:
    def __init__(
        self,
        *,
        backend: control.BackendContext,
        owner: control.ProcessIdentity,
        workers: dict[int, WorkerRecord],
        resources: dict[str, ResourceRecord],
        resource_ledger: NativeResourceLedger,
        commands: CommandLedger,
        current_session: Callable[[], SessionRecord | None],
        controller: ControllerPort,
        lock: asyncio.Lock,
        control_policies: control.ControlPolicies | None,
        trial_lifecycle: TrialLifecycleReports | None,
        ready_reports: WorkerReadyReports,
        cleanup_reports: WorkerCleanupEvidence,
    ) -> None:
        self.backend = backend
        self.owner = owner
        self.workers = workers
        self.resources = resources
        self.resource_ledger = resource_ledger
        self.commands = commands
        self.current_session = current_session
        self.controller = controller
        self.lock = lock
        self.control_policies = control_policies
        self.trial_lifecycle = trial_lifecycle
        self.ready_reports = ready_reports
        self.cleanup_reports = cleanup_reports
        self.manual_preview = ManualPreviewEvidence(resources, resource_ledger)

    def _record(self, source: acq.WorkerContext) -> WorkerRecord:
        return record_for_source(source, self.workers)

    def _matching_session(self, work: control.WorkContext) -> SessionRecord | None:
        return matching_session(work, self.current_session)

    def _admit_evidence_kind(
        self,
        record: WorkerRecord,
        child: ChildOperation,
        evidence: acq.WorkerLifecycleEvidence,
        kind: str,
        ingress_ns: int,
        child_deadline_ns: int,
        session_for_deadline: SessionRecord | None,
        trial_for_deadline: TrialRecord | None,
    ) -> tuple[SessionRecord | None, bool, bool, bool]:
        """Validate evidence against retained work before mutating lifecycle state."""
        trial_ready_session: SessionRecord | None = None
        manual_preview_event = False
        manual_preview_started = False
        manual_preview_stopped = False
        if kind == "started":
            if session_for_deadline is None:
                preview = record.preview
                if (
                    child.kind != "start_preview"
                    or preview is None
                    or preview.start_operation != evidence.operation
                    or ingress_ns > child_deadline_ns
                    or not evidence.started.HasField("actual_start_monotonic_ns")
                    or evidence.started.actual_start_monotonic_ns <= 0
                    or evidence.started.actual_start_monotonic_ns > child_deadline_ns
                    or ingress_ns < evidence.started.actual_start_monotonic_ns
                    or not self._manual_camera_started_matches(record, evidence.started)
                ):
                    raise ValueError(
                        "manual preview Started lacks its exact first usable frame"
                    )
                manual_preview_started = True
                manual_preview_event = True
            else:
                allowance = (
                    self.control_policies.start_evidence_allowance_ns
                    if self.control_policies is not None
                    else 0
                )
                cutoff = (
                    trial_for_deadline.start_monotonic_ns + allowance
                    if trial_for_deadline is not None
                    and trial_for_deadline.start_monotonic_ns is not None
                    and allowance > 0
                    else 0
                )
                if cutoff <= 0 or ingress_ns > cutoff:
                    raise ValueError("Started evidence missed its retained E05 cutoff")
                if self.trial_lifecycle is None:
                    raise RuntimeError("trial lifecycle validator is not assembled")
                self.trial_lifecycle.validate_started(
                    record, evidence, ingress_ns=ingress_ns
                )
        elif kind == "stopped":
            if session_for_deadline is None:
                preview = record.preview
                if (
                    child.kind != "stop_preview"
                    or preview is None
                    or preview.stop_operation != evidence.operation
                    or not evidence.stopped.HasField("activity_stopped")
                    or not evidence.stopped.activity_stopped
                ):
                    raise ValueError(
                        "manual preview Stopped differs from its exact stop"
                    )
                manual_preview_stopped = True
                manual_preview_event = True
            else:
                stop_cutoff = (
                    trial_for_deadline.stop_deadline_ns
                    if trial_for_deadline is not None
                    else None
                )
                if stop_cutoff is None or ingress_ns > stop_cutoff:
                    raise ValueError("Stopped evidence missed its retained E05 cutoff")
                if self.trial_lifecycle is None:
                    raise RuntimeError("trial lifecycle validator is not assembled")
                self.trial_lifecycle.validate_stopped(
                    record, evidence, ingress_ns=ingress_ns
                )
        elif kind == "finished" and session_for_deadline is not None:
            if self.trial_lifecycle is None:
                raise RuntimeError("trial lifecycle validator is not assembled")
            self.trial_lifecycle.validate_finished(record, evidence)
        elif kind == "cleanup" and session_for_deadline is None:
            preview = record.preview
            if child.kind == "stop_preview":
                if preview is None or preview.stop_operation != evidence.operation:
                    raise ValueError(
                        "manual preview cleanup does not prove its exact ring release"
                    )
                self.manual_preview.confirm_cleanup(
                    record, evidence.cleanup, exact=True
                )
                preview.cleanup_event.set()
                manual_preview_event = True
            elif child.kind == "cleanup":
                releases = {item.resource: item for item in evidence.cleanup.resources}
                if (
                    len(releases) != len(evidence.cleanup.resources)
                    or not all(
                        item.released
                        and not item.failure.code
                        and not item.failure.message
                        and not item.HasField("path")
                        for item in releases.values()
                    )
                    or f"camera-device:{record.launch.worker.generation}"
                    not in releases
                ):
                    raise ValueError(
                        "sessionless Cleanup lacks exact camera/resource release evidence"
                    )
                if preview is not None and preview.allocation_id is not None:
                    self.manual_preview.confirm_cleanup(
                        record, evidence.cleanup, exact=False
                    )
                    preview.cleanup_event.set()
            else:
                raise ValueError(
                    "sessionless cleanup evidence belongs to another child command"
                )
        elif kind == "cleanup" and session_for_deadline is not None:
            self.cleanup_reports.retain(session_for_deadline, record, evidence.cleanup)
        if kind == "ready":
            session = session_for_deadline
            if (
                not evidence.ready.HasField("configuration_revision")
                or not evidence.ready.HasField("required_checks_passed")
                or not evidence.ready.required_checks_passed
            ):
                raise ValueError("Ready evidence lacks exact revision/checks")
            if session is None:
                preview = record.preview
                child_expected = (
                    preview is not None
                    and child.kind == "prepare_preview"
                    and preview.preparation == evidence.operation
                    and preview.configuration_revision
                    == evidence.ready.configuration_revision
                    and self.manual_preview.attachments_match(record, evidence.ready)
                )
                if not child_expected:
                    raise ValueError(
                        "manual preview Ready differs from its exact preparation"
                    )
                self.ready_reports.confirm_attachments(record, evidence.ready)
                manual_preview_event = True
            elif session.setup_cancelled or session.interrupted:
                raise ValueError("Ready evidence has no live acquisition work")
            elif evidence.ready.configuration_revision != session.confirmed_revision:
                raise ValueError("Ready evidence differs from confirmed settings")
            elif child.kind == "setup_session":
                if (
                    record.setup_operation is None
                    or evidence.operation != record.setup_operation
                    or ingress_ns > (session.setup_deadline_ns or 0)
                    or not self.ready_reports.attachments_match(
                        record, evidence.ready, require_attached=False
                    )
                ):
                    raise ValueError(
                        "Ready evidence differs from the live confirmed Setup"
                    )
                self.ready_reports.confirm_attachments(record, evidence.ready)
            elif child.kind == "prepare_trial":
                trial = session.trial
                if (
                    trial is None
                    or evidence.source.work != trial.work
                    or ingress_ns > (trial.ready_deadline_ns or 0)
                    or record.trial is None
                    or record.trial.preparation != evidence.operation
                    or evidence.ready.attached_resources
                ):
                    raise ValueError(
                        "trial Ready differs from the retained exact preparation"
                    )
                trial_ready_session = session
            else:
                raise ValueError(
                    "Ready evidence is not for Setup, preview, or trial preparation"
                )
        return (
            trial_ready_session,
            manual_preview_event,
            manual_preview_started,
            manual_preview_stopped,
        )

    async def report_lifecycle(
        self,
        evidence: acq.WorkerLifecycleEvidence,
        *,
        deadline_ns: int,
        ingress_ns: int,
    ) -> control.ReportReceipt:
        kind = evidence.WhichOneof("evidence")
        if kind is None:
            return _report_rejected(
                "INVALID_EVIDENCE", "worker evidence kind is absent"
            )
        try:
            record = self._record(evidence.source)
            trial_ready_session: SessionRecord | None = None
            async with self.lock:
                child = record.child_operations.get(evidence.operation.command_id)
                if (
                    child is None
                    or child.camera != record.context.camera
                    or child.work != evidence.source.work
                ):
                    raise ValueError(
                        "worker lifecycle does not match a retained child command"
                    )
                child_deadline_ns = child.deadline_ns
                if child_deadline_ns is None:
                    raise ValueError(
                        "worker lifecycle has no retained command deadline"
                    )
                record.preflight_lifecycle(evidence, commands=self.commands)
                if kind == "ready" and ingress_ns > child_deadline_ns:
                    raise ValueError(
                        "worker lifecycle evidence missed its original command deadline"
                    )
                session_for_deadline = self._matching_session(evidence.source.work)
                trial_for_deadline = (
                    session_for_deadline.trial
                    if session_for_deadline is not None
                    else None
                )
                (
                    trial_ready_session,
                    manual_preview_event,
                    manual_preview_started,
                    manual_preview_stopped,
                ) = self._admit_evidence_kind(
                    record,
                    child,
                    evidence,
                    kind,
                    ingress_ns,
                    child_deadline_ns,
                    session_for_deadline,
                    trial_for_deadline,
                )
                retained = record.retain_lifecycle(evidence, commands=self.commands)
                if retained and manual_preview_started and record.preview is not None:
                    record.preview.started = True
                    record.preview.started_event.set()
                if retained and manual_preview_stopped and record.preview is not None:
                    record.preview.started = False
                    record.preview.stopped_event.set()
                child.updated.set()
                if kind == "ready" and child.kind == "setup_session":
                    ready_copy = acq.WorkerReadyEvidence()
                    ready_copy.CopyFrom(evidence.ready)
                    record.setup_ready = ready_copy
                session = session_for_deadline
                aggregate = (
                    self.ready_reports.build_setup_report(
                        session, session.setup_deadline_ns or 0, ingress_ns
                    )
                    if kind == "ready"
                    and child.kind == "setup_session"
                    and session is not None
                    else None
                )
                if aggregate is not None and session is not None:
                    if session.pending_ready_report is None:
                        session.pending_ready_report = deepcopy(aggregate)
                        session.pending_ready_deadline_ns = session.setup_deadline_ns
            if trial_ready_session is not None:
                return await self.ready_reports.report_trial_ready(
                    trial_ready_session, ingress_ns
                )
            if manual_preview_event:
                return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)
            if kind in {"started", "stopped", "finished"}:
                if self.trial_lifecycle is None:
                    raise RuntimeError("trial lifecycle reporter is not assembled")
                return await self.trial_lifecycle.report(
                    record, evidence, ingress_ns=ingress_ns
                )
            if aggregate is not None:
                report_deadline = deadline_ns
                pending: control.ReadyReport | None = aggregate
                if session is not None:
                    async with self.lock:
                        pending = session.pending_ready_report
                        report_deadline = (
                            session.pending_ready_deadline_ns or deadline_ns
                        )
                        if session.pending_ready_attempts >= 3:
                            return _report_rejected(
                                "READY_REPORT_UNCONFIRMED",
                                "controller did not accept the retained Ready report",
                            )
                        session.pending_ready_attempts += 1
                if pending is None:
                    return _report_rejected(
                        "READY_REPORT_MISSING", "pending Ready report was lost"
                    )
                if ingress_ns > report_deadline:
                    return _report_rejected(
                        "READY_REPORT_EXPIRED", "original Ready report deadline expired"
                    )
                receipt = await self.controller.report_lifecycle(
                    control.LifecycleReport(ready=pending), deadline_ns=report_deadline
                )
                if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                    return receipt
                if session is not None:
                    async with self.lock:
                        session.ready_report = deepcopy(pending)
                        session.pending_ready_report = None
                        session.pending_ready_deadline_ns = None
                        session.pending_ready_attempts = 0
                        session.ready_confirmed.set()
            return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)
        except (ValueError, RuntimeError) as exc:
            return _report_rejected("INVALID_EVIDENCE", str(exc))

    @staticmethod
    def _manual_camera_started_matches(
        worker: WorkerRecord, started: acq.WorkerStartedEvidence
    ) -> bool:
        if len(started.first_activity) != 1:
            return False
        activity = started.first_activity[0]
        if (
            activity.kind != "camera_callback"
            or activity.observed_monotonic_ns <= 0
            or activity.observed_monotonic_ns != started.actual_start_monotonic_ns
            or not activity.HasField("device_evidence")
            or not activity.device_evidence.HasField("camera")
            or activity.device_evidence.camera != worker.context.camera
            or not activity.device_evidence.HasField("producer")
            or activity.device_evidence.producer != worker.launch.worker
        ):
            return False
        return True
