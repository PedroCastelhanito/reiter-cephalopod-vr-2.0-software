"""Worker report admission composed from focused evidence owners."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from cephvr.acquisition.coordinator.configuration_resolution import (
    ConfigurationResolution,
)
from cephvr.acquisition.coordinator.evidence_cleanup import WorkerCleanupEvidence
from cephvr.acquisition.coordinator.evidence_lifecycle import WorkerLifecycleReports
from cephvr.acquisition.coordinator.evidence_operations import WorkerOperationReports
from cephvr.acquisition.coordinator.evidence_ready import WorkerReadyReports
from cephvr.acquisition.coordinator.evidence_telemetry import WorkerTelemetryReports
from cephvr.acquisition.coordinator.trial_lifecycle import TrialLifecycleReports
from cephvr.acquisition.ports import ControllerPort
from cephvr.acquisition.state import ResourceRecord, SessionRecord, WorkerRecord
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.resource_ledger import NativeResourceLedger
from cephvr.shared.commands import CommandLedger


class WorkerEvidenceCoordinator:
    """Public report surface; each evidence family owns its explicit dependencies."""

    def __init__(
        self,
        *,
        backend: control.BackendContext,
        owner: control.ProcessIdentity,
        settings: control.AcquisitionSettings,
        workers: dict[int, WorkerRecord],
        resources: dict[str, ResourceRecord],
        resource_ledger: NativeResourceLedger,
        commands: CommandLedger,
        current_session: Callable[[], SessionRecord | None],
        controller: ControllerPort,
        lock: asyncio.Lock,
        control_policies: control.ControlPolicies | None = None,
        configuration_resolution: ConfigurationResolution | None = None,
        trial_lifecycle: TrialLifecycleReports | None = None,
    ) -> None:
        ready = WorkerReadyReports(
            backend=backend,
            settings=settings,
            workers=workers,
            resources=resources,
            resource_ledger=resource_ledger,
            commands=commands,
            current_session=current_session,
            controller=controller,
            lock=lock,
        )
        cleanup = WorkerCleanupEvidence(
            resources=resources, resource_ledger=resource_ledger, commands=commands
        )
        self.lifecycle = WorkerLifecycleReports(
            backend=backend,
            owner=owner,
            workers=workers,
            resources=resources,
            resource_ledger=resource_ledger,
            commands=commands,
            current_session=current_session,
            controller=controller,
            lock=lock,
            control_policies=control_policies,
            trial_lifecycle=trial_lifecycle,
            ready_reports=ready,
            cleanup_reports=cleanup,
        )
        self.operations = WorkerOperationReports(
            backend=backend,
            workers=workers,
            commands=commands,
            current_session=current_session,
            controller=controller,
            lock=lock,
            configuration_resolution=configuration_resolution,
        )
        self.telemetry = WorkerTelemetryReports(
            backend=backend,
            workers=workers,
            commands=commands,
            current_session=current_session,
            controller=controller,
            lock=lock,
        )

    async def report_lifecycle(
        self,
        evidence: acq.WorkerLifecycleEvidence,
        *,
        deadline_ns: int,
        ingress_ns: int,
    ) -> control.ReportReceipt:
        return await self.lifecycle.report_lifecycle(
            evidence, deadline_ns=deadline_ns, ingress_ns=ingress_ns
        )

    async def report_operation(
        self, report: acq.WorkerOperationReport, *, deadline_ns: int, ingress_ns: int
    ) -> control.ReportReceipt:
        return await self.operations.report_operation(
            report, deadline_ns=deadline_ns, ingress_ns=ingress_ns
        )

    async def report_warnings(
        self, report: acq.WorkerWarningReport, *, deadline_ns: int, ingress_ns: int
    ) -> control.ReportReceipt:
        return await self.telemetry.report_warnings(
            report, deadline_ns=deadline_ns, ingress_ns=ingress_ns
        )

    async def report_heartbeat(
        self, heartbeat: control.HeartbeatReport, *, deadline_ns: int, ingress_ns: int
    ) -> control.ReportReceipt:
        return await self.telemetry.report_heartbeat(
            heartbeat, deadline_ns=deadline_ns, ingress_ns=ingress_ns
        )
