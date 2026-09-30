"""Aggregate camera Ready facts only after exact retained ownership checks."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from copy import deepcopy

from cephvr.acquisition.coordinator.evidence_helpers import (
    _latest_evidence,
    _report_rejected,
)
from cephvr.acquisition.ports import ControllerPort
from cephvr.acquisition.state import ResourceRecord, SessionRecord, WorkerRecord
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.resource_ledger import NativeResourceLedger
from cephvr.shared.commands import CommandLedger


class WorkerReadyReports:
    def __init__(
        self,
        *,
        backend: control.BackendContext,
        settings: control.AcquisitionSettings,
        workers: dict[int, WorkerRecord],
        resources: dict[str, ResourceRecord],
        resource_ledger: NativeResourceLedger,
        commands: CommandLedger,
        current_session: Callable[[], SessionRecord | None],
        controller: ControllerPort,
        lock: asyncio.Lock,
    ) -> None:
        self.backend = backend
        self.settings = settings
        self.workers = workers
        self.resources = resources
        self.resource_ledger = resource_ledger
        self.commands = commands
        self.current_session = current_session
        self.controller = controller
        self.lock = lock

    async def report_trial_ready(
        self, session: SessionRecord, ingress_ns: int
    ) -> control.ReportReceipt:
        async with self.lock:
            trial = session.trial
            if (
                trial is None
                or trial.ready_reported
                or trial.ready_deadline_ns is None
                or ingress_ns > trial.ready_deadline_ns
                or session.confirmed_settings is None
            ):
                return _report_rejected(
                    "TRIAL_READY_EXPIRED", "trial Ready missed its original deadline"
                )
            if trial.pending_ready_report is None:
                for camera in sorted(session.required_cameras):
                    worker = self.workers.get(camera)
                    if worker is None or worker.trial is None:
                        return control.ReportReceipt(
                            result=control.COMMAND_RESULT_ACCEPTED
                        )
                    operation = worker.trial.preparation
                    if operation is None:
                        return _report_rejected(
                            "TRIAL_READY_MISSING", "worker trial preparation is absent"
                        )
                    matching = _latest_evidence(worker, trial.work, "ready")
                    if (
                        matching is None
                        or matching.operation != operation
                        or not matching.ready.required_checks_passed
                        or matching.ready.configuration_revision
                        != trial.configuration_revision
                    ):
                        return control.ReportReceipt(
                            result=control.COMMAND_RESULT_ACCEPTED
                        )
                resolved = control.BackendSettings(
                    backend_name="acquisition", enabled=True
                )
                resolved.acquisition.CopyFrom(session.confirmed_settings)
                trial.pending_ready_report = control.ReadyReport(
                    context=control.ReportContext(
                        backend=self.backend,
                        work=trial.work,
                        operation=trial.preparation,
                    ),
                    configuration_revision=trial.configuration_revision,
                    required_checks_passed=True,
                    resolved_settings=resolved,
                )
            if trial.pending_ready_attempts >= 3:
                return _report_rejected(
                    "TRIAL_READY_UNCONFIRMED",
                    "controller did not accept retained trial Ready",
                )
            trial.pending_ready_attempts += 1
            pending = deepcopy(trial.pending_ready_report)
            report_deadline = trial.ready_deadline_ns
        receipt = await self.controller.report_lifecycle(
            control.LifecycleReport(ready=pending), deadline_ns=report_deadline
        )
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            return receipt
        async with self.lock:
            if session.trial is not trial or trial.interrupted:
                return _report_rejected(
                    "TRIAL_READY_STALE", "trial changed during Ready acknowledgement"
                )
            trial.ready_report = deepcopy(pending)
            trial.pending_ready_report = None
            trial.pending_ready_attempts = 0
            trial.ready_reported = True
            trial.ready_confirmed.set()
        return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)

    def build_setup_report(
        self, session: SessionRecord, deadline_ns: int, ingress_ns: int
    ) -> control.ReadyReport | None:
        if (
            session.setup_cancelled
            or session.interrupted
            or session.ready_report is not None
            or ingress_ns > deadline_ns
        ):
            return None
        collected: list[acq.WorkerReadyEvidence] = []
        for camera in sorted(session.required_cameras):
            worker = self.workers.get(camera)
            if (
                worker is None
                or worker.setup_ready is None
                or worker.setup_operation is None
            ):
                return None
            matching = _latest_evidence(worker, session.work, "ready")
            if (
                matching is None
                or matching.operation != worker.setup_operation
                or not matching.ready.required_checks_passed
                or matching.ready.configuration_revision
                != session.configuration_revision
                or not self._setup_child_matches(
                    session, worker, worker.setup_operation
                )
                or not self.attachments_match(worker, matching.ready)
            ):
                return None
            collected.append(matching.ready)
        if session.tracking_required and session.tracking_input_confirmation is None:
            return None
        resolved = control.BackendSettings(backend_name="acquisition", enabled=True)
        resolved.acquisition.CopyFrom(self.settings)
        aggregate = control.ReadyReport(
            context=control.ReportContext(
                backend=self.backend,
                work=session.work,
                operation=session.operation,
            ),
            configuration_revision=session.configuration_revision,
            required_checks_passed=all(
                item.required_checks_passed for item in collected
            ),
            resolved_settings=resolved,
        )
        for camera_role in sorted(session.required_cameras):
            worker = self.workers.get(camera_role)
            if worker is None:
                return None
            scopes = session.prepared_functions.get(camera_role)
            if scopes is None:
                return None
            aggregate.prepared_functions.extend(scopes)
        aggregate.cleanup_resources.extend(session.cleanup_resources)
        return aggregate

    @staticmethod
    def _setup_child_matches(
        session: SessionRecord,
        worker: WorkerRecord,
        operation: control.OperationContext,
    ) -> bool:
        child = worker.child_operations.get(operation.command_id)
        return bool(
            child is not None
            and child.kind == "setup_session"
            and child.camera == worker.context.camera
            and child.work == session.work
            and child.parent_operation == session.operation
        )

    def attachments_match(
        self,
        worker: WorkerRecord,
        ready: acq.WorkerReadyEvidence,
        *,
        require_attached: bool = True,
    ) -> bool:
        """Validate the complete exact transfer set before mutating the ledger."""
        session = self.current_session()
        if session is None:
            return False
        expected_ids = session.expected_attachments.get(worker.context.camera, set())
        provided: dict[str, str] = {}
        for attachment in ready.attached_resources:
            resource_id = attachment.resource_id
            if not resource_id or not attachment.transfer_id or resource_id in provided:
                return False
            provided[resource_id] = attachment.transfer_id
        if set(provided) != expected_ids:
            return False
        for resource_id, transfer_id in provided.items():
            resource = self.resources.get(resource_id)
            if resource is None:
                return False
            expected = resource.attachment
            if (
                expected.buffer.producer != worker.launch.worker
                or expected.buffer.owner != worker.launch.owner
                or expected.sync.target != worker.launch.worker
                or expected.sync.transfer_id != transfer_id
            ):
                return False
            snapshot = self.resource_ledger.snapshot(resource.ledger_key)
            peer_id = worker.launch.worker.generation
            if not any(
                item.peer_instance_id == peer_id
                and item.transfer_id == transfer_id
                and not item.released
                and (item.attached or not require_attached)
                for item in snapshot.transfers
            ):
                return False
        return True

    def confirm_attachments(
        self, worker: WorkerRecord, ready: acq.WorkerReadyEvidence
    ) -> None:
        """Transfer only descriptors allocated for this exact producer generation."""
        for attached in ready.attached_resources:
            resource = self.resources.get(attached.resource_id)
            if resource is None:
                raise ValueError("Ready names an unregistered frame allocation")
            expected = resource.attachment
            if (
                expected.buffer.producer != worker.launch.worker
                or expected.buffer.owner != worker.launch.owner
                or expected.sync.target != worker.launch.worker
                or expected.sync.transfer_id != attached.transfer_id
            ):
                raise ValueError(
                    "Ready frame attachment differs from allocation transfer"
                )
            self.resource_ledger.confirm_attachment(
                resource.ledger_key,
                peer_instance_id=worker.launch.worker.generation,
                transfer_id=attached.transfer_id,
            )

    def _matching_session(self, work: control.WorkContext) -> SessionRecord | None:
        """Resolve only the active session/trial named by this report."""
        session = self.current_session()
        if session is None:
            return None
        selected = work.WhichOneof("work")
        if selected == "session" and work == session.work:
            return session
        if (
            selected == "trial"
            and session.trial is not None
            and work == session.trial.work
        ):
            return session
        return None
