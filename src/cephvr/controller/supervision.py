"""Authenticated supervisor heartbeat and bounded status projection."""

from __future__ import annotations

from copy import deepcopy

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.incident.coordination import IncidentCoordinator
from cephvr.controller.receipts import rejected_receipt
from cephvr.controller.state import RETAINED_LIMIT, LifecycleState, SupervisorState


class SupervisorObservations:
    """Admit registered status revisions and feed runtime incident classification."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        supervisor_state: SupervisorState,
        publisher: SnapshotPublisher,
        incidents: IncidentCoordinator,
        generation: str,
        supervisor_generation: str,
    ) -> None:
        self.lifecycle = lifecycle
        self.supervisor_state = supervisor_state
        self.publisher = publisher
        self.incidents = incidents
        self.generation = generation
        self.supervisor_generation = supervisor_generation

    async def supervisor_heartbeat(
        self, report: pb.HeartbeatReport, ingress_ns: int
    ) -> pb.ReportReceipt:
        if (
            report.source.role != "supervisor"
            or report.source.generation != self.supervisor_generation
        ):
            return rejected_receipt("IDENTITY", "supervisor identity mismatch")
        async with self.lifecycle.lock:
            self.supervisor_state.last_seen_ns = ingress_ns
        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    async def supervisor_status(
        self, report: svc.SupervisorStatusReport, ingress_ns: int
    ) -> pb.ReportReceipt:
        if (
            report.supervisor.role != "supervisor"
            or report.supervisor.generation != self.supervisor_generation
            or report.controller_generation != self.generation
        ):
            return rejected_receipt("IDENTITY", "status identity mismatch")
        if len(report.processes) > 256:
            return rejected_receipt(
                "CAPACITY", "supervisor process projection exceeds controller limit"
            )
        serialized = report.SerializeToString(deterministic=True)
        new_errors: list[pb.ErrorReport] = []
        async with self.lifecycle.lock:
            if report.status_revision < self.supervisor_state.status_revision:
                return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
            if report.status_revision == self.supervisor_state.status_revision:
                if serialized != self.supervisor_state.status_bytes:
                    return rejected_receipt(
                        "CONFLICT", "changed duplicate supervisor status"
                    )
                self.supervisor_state.last_seen_ns = ingress_ns
                return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
            self.supervisor_state.status_revision = report.status_revision
            self.supervisor_state.status_bytes = serialized
            self.supervisor_state.last_seen_ns = ingress_ns
            self.supervisor_state.processes = {
                item.process.role: deepcopy(item) for item in report.processes
            }
            self.supervisor_state.all_processes = [
                deepcopy(item) for item in report.processes
            ]
            self.supervisor_state.errors = [
                deepcopy(item) for item in report.errors[-RETAINED_LIMIT:]
            ]
            self.supervisor_state.warnings = [
                deepcopy(item) for item in report.warnings[-RETAINED_LIMIT:]
            ]
            self.supervisor_state.recoveries = [
                deepcopy(item) for item in report.recoveries[-RETAINED_LIMIT:]
            ]
            self.supervisor_state.operations = {
                item.context.command_id: deepcopy(item)
                for item in report.operations[-1024:]
            }
            attempt = self.lifecycle.attempt
            if attempt is not None:
                attempt.changed.set()
            if (
                attempt is not None
                and attempt.incidents is not None
                and self.lifecycle.session.phase
                in (pb.SESSION_PHASE_STARTING, pb.SESSION_PHASE_RUNNING)
            ):
                new_errors = [
                    deepcopy(item)
                    for item in report.errors
                    if item.error_id not in attempt.incident_errors
                    or item.SerializeToString(deterministic=True)
                    != attempt.incident_errors[item.error_id].SerializeToString(
                        deterministic=True
                    )
                ]
            self.publisher.publish()
        for error in new_errors:
            await self.incidents.observe_runtime_error(error)
        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
