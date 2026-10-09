"""Retain exact camera-operation reports and controller readback (E07/E08)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from copy import deepcopy

from cephvr.acquisition.coordinator.configuration_resolution import (
    ConfigurationResolution,
)
from cephvr.acquisition.coordinator.evidence_helpers import (
    _report_rejected,
    matching_session,
    record_for_source,
)
from cephvr.acquisition.ports import ControllerPort
from cephvr.acquisition.state import ChildOperation, SessionRecord, WorkerRecord
from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.commands import CommandLedger


class WorkerOperationReports:
    def __init__(
        self,
        *,
        backend: control.BackendContext,
        workers: dict[int, WorkerRecord],
        commands: CommandLedger,
        current_session: Callable[[], SessionRecord | None],
        controller: ControllerPort,
        lifecycle_report: Callable[..., Awaitable[control.ReportReceipt]],
        lock: asyncio.Lock,
        configuration_resolution: ConfigurationResolution | None,
    ) -> None:
        self.backend = backend
        self.workers = workers
        self.commands = commands
        self.current_session = current_session
        self.controller = controller
        self.lifecycle_report = lifecycle_report
        self.lock = lock
        self.configuration_resolution = configuration_resolution

    def _record(self, source: acq.WorkerContext) -> WorkerRecord:
        return record_for_source(source, self.workers)

    def _matching_session(self, work: control.WorkContext) -> SessionRecord | None:
        return matching_session(work, self.current_session)

    async def report_operation(
        self,
        report: acq.WorkerOperationReport,
        *,
        deadline_ns: int,
        ingress_ns: int,
        retained_query: bool = False,
    ) -> control.ReportReceipt:
        try:
            record = self._record(report.source)
            if (
                not report.HasField("operation")
                or not report.HasField("state_revision")
                or report.operation.context.command_id == ""
                or report.operation.work != report.source.work
                or report.operation.complete
                and not report.operation.HasField("succeeded")
            ):
                raise ValueError("worker operation report context is incomplete")
            child = self.child_operation(
                record, report.source, report.operation, report.state_revision
            )
            if child.deadline_ns is None:
                raise ValueError("worker operation has no retained deadline")
            late_terminal = retained_query or ingress_ns > child.deadline_ns
            if late_terminal and (
                not report.operation.complete
                or report.source.work.WhichOneof("work") is not None
                or child.kind
                not in {
                    "apply_camera",
                    "stop_preview",
                    "prepare_preview",
                    "start_preview",
                }
            ):
                raise ValueError(
                    "late worker evidence is not a terminal sessionless camera operation"
                )
            session = self._matching_session(report.source.work)
            pending_resolution: wire.AcquisitionResolutionReport | None = None
            if report.HasField("resolved_camera"):
                if (
                    not report.operation.complete
                    or not report.operation.succeeded
                    or child.kind
                    not in {"resolve_camera", "apply_camera", "import_pfs"}
                    or report.resolved_camera.device.configured_id == ""
                    or child.requested_device_id is None
                    or report.resolved_camera.device.configured_id
                    != child.requested_device_id
                    or report.resolved_camera.applied.device_id
                    != child.requested_device_id
                    or (
                        report.resolved_camera.HasField("configuration_revision")
                        and report.resolved_camera.configuration_revision
                        != child.configuration_revision
                    )
                ):
                    raise ValueError(
                        "camera resolution is not successful evidence for the retained request"
                    )
                if session is not None and report.source.work == session.work:
                    async with self.lock:
                        resolved = camera_pb2.CameraResolvedState()
                        resolved.CopyFrom(report.resolved_camera)
                        record_camera = report.source.camera
                        if (
                            child.parent_operation != session.operation
                            or child.configuration_revision
                            != session.requested_configuration_revision
                            or session.interrupted
                            or session.setup_cancelled
                        ):
                            raise ValueError(
                                "camera resolution belongs to a stale or cancelled configuration"
                            )
                        prior = session.camera_resolutions.get(record_camera)
                        if prior is not None and prior != resolved:
                            raise ValueError(
                                "camera resolution changed after acceptance"
                            )
                        session.camera_resolutions[record_camera] = resolved
                        resolution = self.resolution_report(session)
                        if (
                            resolution is not None
                            and session.pending_resolution_report is None
                        ):
                            session.pending_resolution_report = deepcopy(resolution)
                            session.pending_resolution_deadline_ns = child.deadline_ns
                        if not session.resolution_reported:
                            pending_resolution = session.pending_resolution_report
                elif self.configuration_resolution is not None and not late_terminal:
                    receipt = await self.configuration_resolution.accept_camera(
                        record,
                        child,
                        report.resolved_camera,
                        ingress_ns=ingress_ns,
                    )
                    if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                        return receipt
                elif self.configuration_resolution is None and not late_terminal:
                    raise ValueError(
                        "sessionless camera readback has no resolution owner"
                    )
            saved_operation = control.OperationState()
            saved_operation.CopyFrom(report.operation)
            async with self.lock:
                if child.report_revision > report.state_revision:
                    raise ValueError("stale worker operation revision")
                if (
                    child.report_revision == report.state_revision
                    and child.report is not None
                    and child.report != saved_operation
                ):
                    raise ValueError(
                        "same worker operation revision changed its report"
                    )
                if (
                    child.report_revision < report.state_revision
                    or child.report is None
                ):
                    child.report = saved_operation
                    child.report_ingress_ns = ingress_ns
                    child.report_revision = report.state_revision
                    if report.HasField("resolved_camera"):
                        resolved_copy = camera_pb2.CameraResolvedState()
                        resolved_copy.CopyFrom(report.resolved_camera)
                        child.resolved_camera = resolved_copy
                    if report.HasField("exported_pfs_path"):
                        child.exported_pfs_path = report.exported_pfs_path
                    child.updated.set()
            if pending_resolution is not None and session is not None:
                async with self.lock:
                    report_deadline = (
                        session.pending_resolution_deadline_ns or deadline_ns
                    )
                    if session.pending_resolution_attempts >= 3:
                        return _report_rejected(
                            "RESOLUTION_UNCONFIRMED",
                            "controller did not accept the retained resolution report",
                        )
                    session.pending_resolution_attempts += 1
                if ingress_ns > report_deadline:
                    return _report_rejected(
                        "RESOLUTION_REPORT_EXPIRED",
                        "original acquisition resolution deadline expired",
                    )
                receipt = await self.controller.report_acquisition_resolution(
                    pending_resolution, deadline_ns=report_deadline
                )
                if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                    return receipt
                async with self.lock:
                    session.resolution_reported = True
                    session.pending_resolution_report = None
                    session.pending_resolution_deadline_ns = None
                    session.pending_resolution_attempts = 0
            if late_terminal and self.configuration_resolution is not None:
                await self.configuration_resolution.retire_failed_if_quiescent(
                    child.parent_operation
                )
            # A worker command is one owned stage, not the parent backend command.
            # Relay only in-progress detail; the coordinator reports terminal parent
            # success/failure after every required stage and cleanup obligation ends.
            if not report.operation.complete:
                operation_report = control.LifecycleReport(
                    operation=control.BackendOperationReport(
                        source=self.backend,
                        operation=control.OperationState(
                            context=child.parent_operation,
                            command=child.kind,
                            work=child.work,
                            progress=report.operation.progress
                            or f"{child.kind} in progress",
                        ),
                    )
                )
                receipt = await self.controller.report_lifecycle(
                    operation_report, deadline_ns=deadline_ns
                )
                if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                    return receipt
            return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)
        except (ValueError, OverflowError) as exc:
            return _report_rejected("INVALID_OPERATION", str(exc))

    async def reconcile_retained_operation(
        self,
        record: WorkerRecord,
        child: ChildOperation,
        retained: acq.WorkerRetainedResult,
        *,
        deadline_ns: int,
        ingress_ns: int,
    ) -> bool:
        """Retain exact worker evidence from a read-only query without adoption."""
        expected_command = {
            "apply_camera": "ApplyCameraSettings",
            "stop_preview": "StopPreview",
            "prepare_preview": "PreparePreview",
            "start_preview": "StartPreview",
        }.get(child.kind)
        if (
            expected_command is None
            or not retained.found
            or not retained.HasField("source")
            or retained.source != record.context
            or not retained.HasField("admission")
            or retained.admission.result != control.COMMAND_RESULT_ACCEPTED
            or retained.admission.command_id != child.command_id
            or not retained.HasField("operation")
            or not retained.operation.HasField("source")
            or retained.operation.source != record.context
            or not retained.operation.HasField("operation")
            or not retained.operation.operation.HasField("context")
            or retained.operation.operation.context.command_id != child.command_id
            or retained.operation.operation.command != expected_command
            or retained.operation.operation.work != child.work
            or not retained.operation.operation.complete
            or not retained.operation.operation.HasField("succeeded")
            or retained.operation.operation.work != record.context.work
            or not retained.operation.HasField("state_revision")
            or retained.operation.state_revision <= 0
        ):
            return False

        for evidence in retained.lifecycle:
            if (
                not evidence.HasField("source")
                or evidence.source != record.context
                or not evidence.HasField("operation")
                or evidence.operation.command_id != child.command_id
                or not evidence.HasField("state_revision")
                or evidence.state_revision <= 0
                or evidence.WhichOneof("evidence") is None
            ):
                return False

        for evidence in retained.lifecycle:
            if (
                evidence.WhichOneof("evidence") in {"ready", "started"}
                and child.deadline_ns is not None
                and ingress_ns > child.deadline_ns
            ):
                # A fresh read-only query cannot make late readiness/start timely
                # or release resources through readiness processing.
                continue
            receipt = await self.lifecycle_report(
                evidence, deadline_ns=deadline_ns, ingress_ns=ingress_ns
            )
            if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                return False
        receipt = await self.report_operation(
            retained.operation,
            deadline_ns=deadline_ns,
            ingress_ns=ingress_ns,
            retained_query=True,
        )
        return receipt.result == control.COMMAND_RESULT_ACCEPTED

    def resolution_report(
        self, session: SessionRecord
    ) -> wire.AcquisitionResolutionReport | None:
        if session.resolution_reported:
            return None
        if set(session.camera_resolutions) != session.required_cameras:
            return None
        report = wire.AcquisitionResolutionReport(
            source=self.backend,
            work=session.work,
            operation=session.operation,
            requested_configuration_revision=(
                session.requested_configuration_revision
                if session.requested_configuration_revision is not None
                else session.configuration_revision
            ),
        )
        for camera in sorted(session.required_cameras):
            report.cameras.add(camera=camera, result=session.camera_resolutions[camera])
        if session.pulse_resolution is not None:
            report.pulses.CopyFrom(session.pulse_resolution)
        session.resolved_report = deepcopy(report)
        return report

    def child_operation(
        self,
        record: WorkerRecord,
        source: acq.WorkerContext,
        state: control.OperationState,
        revision: int,
    ) -> ChildOperation:
        child = record.child_operations.get(state.context.command_id)
        if child is None:
            raise ValueError(
                f"worker operation {state.command} has no retained child {state.context.command_id}"
            )
        if child.camera != record.context.camera or revision <= 0:
            raise ValueError(
                "worker operation camera/revision differs from its retained child"
            )
        if child.work != state.work or child.work != source.work:
            raise ValueError("worker operation work differs from its retained child")
        if child.report_revision > revision:
            raise ValueError("stale worker operation revision")
        if child.report_revision == revision and child.report is not None:
            if child.report != state:
                raise ValueError("same worker operation revision changed its report")
        if child.report is not None and child.report.complete:
            if not state.complete or child.report.succeeded != state.succeeded:
                raise ValueError("worker operation terminal result changed")
        return child
