"""Apply controller-selected acquisition incident scopes (E06)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from uuid import uuid4

from cephvr.acquisition.coordinator.session import SessionSetup
from cephvr.acquisition.coordinator.trials import TrialCoordinator
from cephvr.acquisition.ports import ControllerPort
from cephvr.acquisition.state import (
    CoordinatorIdentity,
    SessionRecord,
    SessionSlot,
    WorkerRecord,
)
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns


class IncidentScopeOwner:
    """Validate exact isolation evidence and apply the selected incident result."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        session_slot: SessionSlot,
        workers: dict[int, WorkerRecord],
        controller: ControllerPort,
        session_setup: SessionSetup,
        trials: TrialCoordinator,
        lock: asyncio.Lock,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.session_slot = session_slot
        self.workers = workers
        self.controller = controller
        self.session_setup = session_setup
        self.trials = trials
        self.lock = lock
        self.clock = clock

    async def apply(
        self, request: wire.IncidentScopeRequest, *, deadline_ns: int
    ) -> control.CommandAdmission:
        incident = request.incident
        session = self.session_slot.current
        declared = (
            {item.resource_id for item in session.ready_report.prepared_functions}
            if session is not None and session.ready_report is not None
            else set()
        )
        previous = (
            session.incident_revisions.get(incident.incident_id)
            if session is not None
            else None
        )
        if (
            self.clock() >= deadline_ns
            or request.command.issuer != self.identity.controller
            or request.command.target != self.identity.backend
            or session is None
            or request.command.work != session.work
            or incident.work != session.work
            or not incident.incident_id
            or incident.revision <= 0
            or incident.revision != (1 if previous is None else previous + 1)
            or not incident.affected_resources
            or not set(incident.affected_resources) <= declared
            or (len(session.incident_revisions) >= 64 and previous is None)
        ):
            return _rejected(
                request.command.command_id,
                "INCIDENT_SCOPE",
                "incident scope is stale",
            )
        if incident.disposition in {
            control.RUNTIME_INCIDENT_DISPOSITION_ABORT_SELECTED,
            control.RUNTIME_INCIDENT_DISPOSITION_AUTOMATIC_STOP,
        }:
            await self._abort(session, request, deadline_ns)
            session.incident_revisions[incident.incident_id] = incident.revision
            await self._report_operation(
                control.OperationState(
                    context=control.OperationContext(
                        command_id=request.command.command_id
                    ),
                    command="apply_incident_scope",
                    work=session.work,
                    complete=True,
                    succeeded=True,
                    progress="acquisition interruption path admitted; lifecycle closure remains retained",
                ),
                deadline_ns,
            )
            return _accepted(request.command.command_id)
        if (
            incident.disposition
            != control.RUNTIME_INCIDENT_DISPOSITION_CONTINUE_SELECTED
        ):
            return _rejected(
                request.command.command_id,
                "INCIDENT_DISPOSITION",
                "acquisition received a non-actionable incident disposition",
            )
        if not self._isolation_proven(session, incident):
            await self._abort(session, request, deadline_ns)
            session.incident_revisions[incident.incident_id] = incident.revision
            await self._report_operation(
                control.OperationState(
                    context=control.OperationContext(
                        command_id=request.command.command_id
                    ),
                    command="apply_incident_scope",
                    work=session.work,
                    complete=True,
                    succeeded=False,
                    failure=control.Failure(
                        code="INCIDENT_ISOLATION_UNAVAILABLE",
                        message="registered worker evidence does not prove exact isolation and continuing paths",
                    ),
                ),
                deadline_ns,
            )
            return _rejected(
                request.command.command_id,
                "INCIDENT_ISOLATION_UNAVAILABLE",
                "registered worker evidence does not prove exact isolation and continuing paths",
            )
        retained = control.RuntimeIncident()
        retained.CopyFrom(incident)
        session.incident_revisions[incident.incident_id] = incident.revision
        session.confirmed_incidents[incident.incident_id] = retained
        session.unavailable_resources.update(incident.affected_resources)
        await self._report_operation(
            control.OperationState(
                context=control.OperationContext(command_id=request.command.command_id),
                command="apply_incident_scope",
                work=session.work,
                complete=True,
                succeeded=True,
                progress="unavailable acquisition scope retained: "
                + ",".join(sorted(incident.affected_resources)),
            ),
            deadline_ns,
        )
        return _accepted(request.command.command_id)

    async def _abort(
        self,
        session: SessionRecord,
        request: wire.IncidentScopeRequest,
        deadline_ns: int,
    ) -> None:
        current = self.session_slot.current
        if current is None or current is not session:
            raise RuntimeError("incident session changed before its safety action")
        current.interrupted = True
        self.session_slot.interrupted = True
        trial = current.trial
        if trial is not None and trial.schedule is not None and trial.stop is None:
            stop = wire.StopTrialRequest(
                command=wire.BackendCommand(
                    command_id=str(uuid4()),
                    issuer=self.identity.process,
                    target=self.identity.backend,
                    work=trial.work,
                ),
                issued_monotonic_ns=self.clock(),
                reason=control.Failure(
                    code="RUNTIME_INCIDENT",
                    message=request.incident.consequence[:2048]
                    or "runtime incident requires acquisition interruption",
                ),
            )
            trial.interrupted = True
            receipt = await self.trials.stop(
                stop, deadline_ns=deadline_ns, aborted=True, internal=True
            )
            if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError("acquisition could not admit incident Stop")
        else:
            await self.session_setup.cancel(current, deadline_ns=deadline_ns)

    async def _report_operation(
        self, operation: control.OperationState, deadline_ns: int
    ) -> None:
        receipt = await self.controller.report_lifecycle(
            control.LifecycleReport(
                operation=control.BackendOperationReport(
                    source=self.identity.backend,
                    operation=operation,
                )
            ),
            deadline_ns=deadline_ns,
        )
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError("controller rejected retained incident operation")

    def _isolation_proven(
        self, session: SessionRecord, incident: control.RuntimeIncident
    ) -> bool:
        current = self.session_slot.current
        if current is None or current is not session:
            return False
        ready = current.ready_report
        if (
            ready is None
            or not incident.continuation_available
            or incident.work != current.work
            or incident.first_observed_monotonic_ns <= 0
            or incident.last_observed_monotonic_ns
            < incident.first_observed_monotonic_ns
            or len(set(incident.affected_resources)) != len(incident.affected_resources)
        ):
            return False
        functions = {item.resource_id: item for item in ready.prepared_functions}
        if any(item.owner != self.identity.process for item in functions.values()):
            return False
        affected = set(incident.affected_resources)
        if not affected or not affected <= set(functions):
            return False
        closure = {
            resource_id
            for resource_id in affected
            for resource_id in functions[resource_id].affected_closure_resource_ids
        }
        if not closure <= set(functions):
            return False
        faults: dict[str, control.ErrorReport] = {}
        continuing: set[str] = set()
        trial_work = current.trial.work if current.trial is not None else None
        for record in self.workers.values():
            heartbeat = record.heartbeat
            if (
                heartbeat is None
                or heartbeat.sent_monotonic_ns <= incident.first_observed_monotonic_ns
                or heartbeat.source != record.launch.worker
                or (
                    heartbeat.work != current.work
                    and (trial_work is None or heartbeat.work != trial_work)
                )
            ):
                continue
            if heartbeat.HasField("active_error"):
                error = heartbeat.active_error
                if (
                    error.source == record.launch.worker
                    and error.work == heartbeat.work
                    and error.HasField("isolation")
                    and error.isolation.verified_monotonic_ns
                    >= incident.last_observed_monotonic_ns
                    and (
                        error.error_id in incident.error_ids
                        or error.incident_episode_id == incident.incident_id
                    )
                    and error.isolation.leases_released_or_quarantined
                ):
                    for resource in error.isolation.affected_resource_ids:
                        if resource not in functions:
                            continue
                        reporters = {
                            (item.role, item.generation)
                            for item in functions[resource].authorized_reporters
                        }
                        if (
                            resource in affected
                            and (
                                record.launch.worker.role,
                                record.launch.worker.generation,
                            )
                            in reporters
                        ):
                            faults[resource] = error
            for item in heartbeat.continuing_functions:
                if item.resource_id not in functions or item.resource_id in affected:
                    continue
                reporters = {
                    (reporter.role, reporter.generation)
                    for reporter in functions[item.resource_id].authorized_reporters
                }
                if (
                    record.launch.worker.role,
                    record.launch.worker.generation,
                ) not in reporters:
                    continue
                if (
                    all(
                        item.HasField(field) and getattr(item, field)
                        for field in (
                            "functioning",
                            "schedule_valid",
                            "host_clock_valid",
                            "control_path_valid",
                        )
                    )
                    and item.observed_monotonic_ns
                    >= incident.last_observed_monotonic_ns
                ):
                    continuing.add(item.resource_id)
        for resource in affected:
            function = functions[resource]
            fault = faults.get(resource)
            if fault is None or not fault.HasField("isolation"):
                return False
            isolation = fault.isolation
            if resource not in isolation.affected_resource_ids:
                return False
            if function.feedback_hold_required_on_loss:
                if (
                    not isolation.feedback_hold_active
                    or resource not in isolation.feedback_hold_resource_ids
                ):
                    return False
            elif resource not in isolation.fenced_resource_ids:
                return False
        fenced = {
            resource
            for error in faults.values()
            for resource in error.isolation.fenced_resource_ids
        }
        held = {
            resource
            for error in faults.values()
            for resource in error.isolation.feedback_hold_resource_ids
        }
        bounded = all(
            error.isolation.HasField("bounded_uncertainty")
            and error.isolation.bounded_uncertainty
            for error in faults.values()
        )
        if any(
            functions[key].feedback_hold_required_on_loss and key not in held
            for key in closure
        ):
            return False
        if any(
            key not in fenced
            and key not in held
            and not (bounded and functions[key].bounded_uncertainty_supported)
            for key in closure
        ):
            return False
        required_continuing = {
            key
            for key, function in functions.items()
            if function.essential_to_stimulus_control and key not in closure
        }
        return required_continuing <= continuing


def _accepted(command_id: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        result=control.COMMAND_RESULT_ACCEPTED, command_id=command_id
    )


def _rejected(command_id: str, code: str, message: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        result=control.COMMAND_RESULT_REJECTED,
        command_id=command_id,
        failure=control.Failure(code=code, message=message[:2048]),
    )
