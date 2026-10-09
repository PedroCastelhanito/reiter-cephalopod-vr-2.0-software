"""Exact incident scope registration, backend admission, evidence, and commit."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from copy import deepcopy
from typing import Any, Protocol

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.lifecycle.evidence_wait import EvidenceWaiter
from cephvr.controller.lifecycle.preparation_context import PreparationContext
from cephvr.controller.lifecycle_reports import LifecycleReports
from cephvr.controller.ports import SupervisorPort
from cephvr.controller.state import Attempt, IncidentState, LifecycleState, LimitsState
from cephvr.shared.deadlines import remaining_seconds


class Interrupt(Protocol):
    async def __call__(
        self, attempt: Attempt, reason: str, *, issued_ns: int | None = None
    ) -> None: ...


class ScopeConfirmation:
    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        incidents: IncidentState,
        limits: LimitsState,
        clock: Callable[[], int],
        publisher: SnapshotPublisher,
        evidence_waiter: EvidenceWaiter,
        preparation_context: PreparationContext,
        lifecycle_reports: LifecycleReports,
        supervisor: SupervisorPort | None,
        interrupt: Interrupt,
        spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]],
        log_incident: Callable[
            [Attempt, str, dict[str, object]], Coroutine[Any, Any, None]
        ],
    ) -> None:
        self.lifecycle = lifecycle
        self.incident_state = incidents
        self.limits = limits
        self.clock = clock
        self.publisher = publisher
        self.evidence_waiter = evidence_waiter
        self.preparation_context = preparation_context
        self.lifecycle_reports = lifecycle_reports
        self.supervisor = supervisor
        self.interrupt = interrupt
        self.spawn = spawn
        self.log_incident = log_incident

    async def confirm_incident_scope(
        self,
        attempt: Attempt,
        error: pb.ErrorReport,
        pending: pb.RuntimeIncident,
        classification: Any,
        deadline_ns: int,
    ) -> None:
        try:
            async with attempt.scope_lock:
                await self._confirm_incident_scope_serial(
                    attempt, error, pending, classification, deadline_ns
                )
        finally:
            attempt.scope_inflight.pop(pending.incident_id, None)

    async def _dispatch_and_verify(
        self,
        attempt: Attempt,
        candidate: pb.RuntimeIncident,
        classification: Any,
        deadline_ns: int,
    ) -> dict[str, str] | None:
        """Register scope commands before dispatch and verify their exact results."""
        affected = set(classification.affected_resources)
        healthy_names = {
            name
            for name in attempt.required
            if any(
                function.resource_id not in affected
                for function in attempt.ready[name].prepared_functions
            )
        }
        commands: dict[str, str] = {}
        requests: dict[str, svc.IncidentScopeRequest] = {}
        for name in healthy_names:
            command_id = str(uuid.uuid4())
            commands[name] = command_id
            requests[name] = svc.IncidentScopeRequest(
                command=self.preparation_context.handoff_command(
                    attempt, name, command_id
                ),
                incident=candidate,
            )
        async with self.lifecycle.lock:
            if self.lifecycle.attempt is not attempt or attempt.interrupted:
                return None
            for name, command_id in commands.items():
                attempt.scope_commands[command_id] = (
                    name,
                    candidate.incident_id,
                    candidate.revision,
                )
        replies = await asyncio.wait_for(
            asyncio.gather(
                *(
                    attempt.required[name].apply_incident_scope(
                        requests[name], deadline_ns=deadline_ns
                    )
                    for name in commands
                )
            ),
            remaining_seconds(deadline_ns, clock=self.clock),
        )
        if any(reply.result != pb.COMMAND_RESULT_ACCEPTED for reply in replies):
            raise RuntimeError("healthy coordinator rejected incident scope")
        if commands:
            initial_scope_deadline = min(
                deadline_ns, self.clock() + self.limits.current.registration_ns
            )
            try:
                await self.evidence_waiter.wait_evidence(
                    lambda: all(
                        command_id in attempt.scope_results
                        for command_id in commands.values()
                    ),
                    initial_scope_deadline,
                    attempt,
                )
            except TimeoutError as exc:
                for name, command_id in commands.items():
                    state = attempt.scope_results.get(command_id)
                    if state is not None:
                        continue
                    retained = await asyncio.wait_for(
                        attempt.required[name].get_retained_result(
                            svc.RetainedResultQuery(
                                query=svc.BackendQuery(
                                    target=attempt.required[name].context,
                                    work=pb.WorkContext(session=attempt.context),
                                ),
                                command_id=command_id,
                            ),
                            deadline_ns=deadline_ns,
                        ),
                        remaining_seconds(deadline_ns, clock=self.clock),
                    )
                    if (
                        not retained.found
                        or not retained.operation.complete
                        or not retained.operation.succeeded
                        or retained.operation.context.command_id != command_id
                    ):
                        raise RuntimeError(
                            f"{name} incident scope completion unconfirmed"
                        ) from exc
                    receipt = await self.lifecycle_reports.receive(
                        pb.LifecycleReport(
                            operation=pb.BackendOperationReport(
                                source=attempt.required[name].context,
                                operation=retained.operation,
                            )
                        ),
                        self.clock(),
                    )
                    if receipt.result != pb.COMMAND_RESULT_ACCEPTED:
                        raise RuntimeError(
                            f"{name} retained scope result was rejected"
                        ) from exc
        if any(
            not attempt.scope_results[command_id].succeeded
            for command_id in commands.values()
        ):
            raise RuntimeError("backend incident scope completed unsuccessfully")
        return commands

    async def _confirm_incident_scope_serial(
        self,
        attempt: Attempt,
        error: pb.ErrorReport,
        pending: pb.RuntimeIncident,
        classification: Any,
        deadline_ns: int,
    ) -> None:
        topology = attempt.incident_topology
        registered = attempt.registered_context
        if topology is None or registered is None or self.supervisor is None:
            await self.interrupt(attempt, "incident scope authority unavailable")
            return
        candidate = deepcopy(pending)
        candidate.revision += 1
        candidate.continuation_available = True
        candidate.consequence = classification.reason
        scope = deepcopy(registered)
        scope.ClearField("continuation_incidents")
        scope.continuation_incidents.extend(
            item
            for item in attempt.confirmed_incidents.values()
            if item.incident_id != candidate.incident_id
        )
        scope.continuation_incidents.add().CopyFrom(candidate)
        registration = svc.RegisterContextRequest(
            command_id=str(uuid.uuid4()), context=scope
        )
        try:
            acknowledgement = await asyncio.wait_for(
                self.supervisor.register_context(registration),
                remaining_seconds(deadline_ns, clock=self.clock),
            )
            if (
                acknowledgement.admission.result != pb.COMMAND_RESULT_ACCEPTED
                or acknowledgement.registered != scope
            ):
                raise RuntimeError("supervisor did not retain exact incident scope")
            commands = await self._dispatch_and_verify(
                attempt, candidate, classification, deadline_ns
            )
            if commands is None:
                return
            async with self.lifecycle.lock:
                if (
                    self.lifecycle.attempt is not attempt
                    or attempt.interrupted
                    or attempt.incidents is None
                    or self.clock() > deadline_ns
                ):
                    return
                confirmed = attempt.incidents.observe(
                    error, classification, consequence=classification.reason
                )
                if (
                    confirmed.incident_id != candidate.incident_id
                    or confirmed.revision != candidate.revision
                ):
                    raise RuntimeError("incident scope changed during registration")
                attempt.confirmed_incidents[confirmed.incident_id] = deepcopy(confirmed)
                attempt.registered_context = deepcopy(scope)
                for plan in attempt.prepared.trials:
                    kept = [
                        item
                        for item in plan.continuation_incidents
                        if item.incident_id != confirmed.incident_id
                    ]
                    plan.ClearField("continuation_incidents")
                    plan.continuation_incidents.extend(kept)
                    plan.continuation_incidents.add().CopyFrom(confirmed)
                for prompt_id, (prompt, owner) in list(
                    self.incident_state.incident_prompts.items()
                ):
                    if (
                        owner is attempt
                        and prompt.runtime_incident.incident_id == confirmed.incident_id
                    ):
                        prompt.runtime_incident.CopyFrom(confirmed)
                        prompt.explanation = classification.reason
                        prompt.permitted_choices[:] = [
                            "continue_session",
                            "abort_session",
                        ]
                        self.incident_state.incident_prompts[prompt_id] = (
                            prompt,
                            owner,
                        )
                self.publisher.publish()
                if attempt.writer is not None:
                    self.spawn(
                        self.log_incident(
                            attempt,
                            "incident_scope",
                            {
                                "incident_id": confirmed.incident_id,
                                "incident_revision": confirmed.revision,
                                "affected_resources": list(
                                    confirmed.affected_resources
                                ),
                            },
                        )
                    )
        except Exception as exc:
            await self.interrupt(
                attempt, f"incident scope could not be confirmed: {exc}"
            )
