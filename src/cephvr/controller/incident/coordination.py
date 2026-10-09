"""Controller incident admission, exact scope confirmation, and deadlines (E06)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from copy import deepcopy
from typing import Any

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.incident.registry import IncidentCapacityError
from cephvr.controller.incident.scope import Interrupt, ScopeConfirmation
from cephvr.controller.lifecycle.evidence_wait import EvidenceWaiter
from cephvr.controller.lifecycle.preparation_context import PreparationContext
from cephvr.controller.lifecycle_reports import LifecycleReports
from cephvr.controller.metadata.coordination import MetadataCoordinator
from cephvr.controller.metadata.types import StorageError
from cephvr.controller.ports import SupervisorPort
from cephvr.controller.state import (
    Attempt,
    IncidentState,
    LifecycleState,
    LimitsState,
    SupervisorState,
)
from cephvr.shared.deadlines import remaining_seconds
from cephvr.shared.incidents import (
    IncidentEvidenceError,
    IsolationProof,
    classify_incident,
)


class IncidentCoordinator:
    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        incidents: IncidentState,
        supervisor_state: SupervisorState,
        limits: LimitsState,
        health_silence_ns: int,
        clock: Callable[[], int],
        publisher: SnapshotPublisher,
        metadata: MetadataCoordinator,
        evidence_waiter: EvidenceWaiter,
        preparation_context: PreparationContext,
        lifecycle_reports: LifecycleReports,
        supervisor: SupervisorPort | None,
        interrupt: Interrupt,
        spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]],
    ) -> None:
        self.lifecycle = lifecycle
        self.incident_state = incidents
        self.supervisor_state = supervisor_state
        self.limits = limits
        self.health_silence_ns = health_silence_ns
        self.clock = clock
        self.publisher = publisher
        self.metadata = metadata
        self.interrupt = interrupt
        self.spawn = spawn
        self.scope = ScopeConfirmation(
            lifecycle=lifecycle,
            incidents=incidents,
            limits=limits,
            clock=clock,
            publisher=publisher,
            evidence_waiter=evidence_waiter,
            preparation_context=preparation_context,
            lifecycle_reports=lifecycle_reports,
            supervisor=supervisor,
            interrupt=interrupt,
            spawn=spawn,
            log_incident=self.log_incident,
        )

    async def log_incident(
        self,
        attempt: Attempt,
        event_type: str,
        details: dict[str, object],
        *,
        at_ns: int | None = None,
        trial_number: int | None = None,
        outcome: str | None = None,
    ) -> None:
        try:
            await self.metadata.log_event(
                attempt,
                event_type,
                at_ns=at_ns,
                trial_number=trial_number,
                outcome=outcome,
                details=details,
            )
        except StorageError as exc:
            await self.interrupt(
                attempt, f"incident bookkeeping persistence failed: {exc}"
            )

    async def observe_runtime_error(self, error: pb.ErrorReport) -> str | None:
        async with self.lifecycle.lock:
            attempt = self.lifecycle.attempt
            if (
                attempt is None
                or attempt.incidents is None
                or attempt.incident_topology is None
                or self.lifecycle.session.phase
                not in (pb.SESSION_PHASE_STARTING, pb.SESSION_PHASE_RUNNING)
            ):
                return None
            now = self.clock()
            episode_id = (
                error.incident_episode_id
                if error.HasField("incident_episode_id")
                else error.error_id
            )
            episode_key = (error.source.role, error.source.generation, episode_id)
            deadline = attempt.episode_deadlines.get(
                episode_key,
                error.occurred_monotonic_ns + self.limits.current.recovery_ns,
            )
            heartbeats = {
                (
                    status.last_heartbeat.source.role,
                    status.last_heartbeat.source.generation,
                ): deepcopy(status.last_heartbeat)
                for status in self.supervisor_state.all_processes
                if status.HasField("last_heartbeat")
            }
            proof = IsolationProof(
                continuing_heartbeats=heartbeats,
                controller_authority_valid=True,
                supervisor_authority_valid=now - self.supervisor_state.last_seen_ns
                <= self.health_silence_ns,
                bounded_accounting=True,
            )
            try:
                classification = classify_incident(
                    error,
                    attempt.incident_topology,
                    proof,
                    now_ns=now,
                    original_deadline_ns=deadline,
                    max_evidence_age_ns=self.health_silence_ns,
                )
                verified_scope = (
                    classification if classification.status == "continuable" else None
                )
                if classification.status == "continuable":
                    classification = type(classification)(
                        "pending",
                        "isolation proven; incident scope acknowledgements pending",
                        classification.affected_resources,
                        deadline,
                    )
                incident = attempt.incidents.observe(
                    error, classification, consequence=classification.reason
                )
            except (IncidentEvidenceError, IncidentCapacityError, ValueError) as exc:
                self.spawn(
                    self.interrupt(attempt, f"incident accounting invalid: {exc}")
                )
                return None
            attempt.incident_errors[error.error_id] = deepcopy(error)
            attempt.episode_deadlines[episode_key] = deadline
            attempt.incident_deadlines[error.error_id] = deadline
            attempt.incident_id_by_error[error.error_id] = incident.incident_id
            existing_prompt_id = next(
                (
                    key
                    for key, (
                        prompt,
                        owner,
                    ) in self.incident_state.incident_prompts.items()
                    if owner is attempt
                    and prompt.runtime_incident.incident_id == incident.incident_id
                ),
                None,
            )
            prompt_id = existing_prompt_id or str(uuid.uuid4())
            blocking = classification.status == "blocking"
            prompt = pb.Prompt(
                prompt_id=prompt_id,
                setup=attempt.context,
                operation=error.operation,
                explanation=classification.reason,
                permitted_choices=["acknowledge"] if blocking else ["abort_session"],
                runtime_incident=incident,
            )
            self.incident_state.incident_prompts[prompt.prompt_id] = (prompt, attempt)
            if blocking:
                self.spawn(
                    self.interrupt(
                        attempt,
                        f"blocking incident: {classification.reason}",
                        issued_ns=error.occurred_monotonic_ns,
                    )
                )
            else:
                self.spawn(self.incident_deadline(attempt, error.error_id, deadline))
                if (
                    verified_scope is not None
                    and incident.incident_id not in attempt.confirmed_incidents
                ):
                    affected = frozenset(verified_scope.affected_resources)
                    in_flight = attempt.scope_inflight.get(incident.incident_id)
                    if in_flight is None:
                        attempt.scope_inflight[incident.incident_id] = affected
                        self.spawn(
                            self.scope.confirm_incident_scope(
                                attempt, error, incident, verified_scope, deadline
                            )
                        )
                    elif in_flight != affected:
                        self.spawn(
                            self.interrupt(
                                attempt,
                                "incident scope changed while confirmation was in flight",
                            )
                        )
            self.publisher.publish()
            if attempt.writer is not None:
                self.spawn(
                    self.log_incident(
                        attempt,
                        "error",
                        {
                            "error_id": error.error_id,
                            "incident_id": incident.incident_id,
                            "source_role": error.source.role,
                            "failure_code": error.failure.code,
                            "affected_resources": list(incident.affected_resources),
                            "classification": classification.status,
                        },
                    )
                )
            return incident.incident_id

    async def resolve_recovered_incident(
        self,
        attempt: Attempt,
        incident_id: str,
        recovered_monotonic_ns: int,
    ) -> bool:
        """Resolve one exact confirmed incident when its source function recovers."""
        if not incident_id:
            return False
        async with self.lifecycle.lock:
            if (
                self.lifecycle.attempt is not attempt
                or attempt.interrupted
                or attempt.incidents is None
                or incident_id not in attempt.confirmed_incidents
                or self.lifecycle.session.phase
                not in (pb.SESSION_PHASE_STARTING, pb.SESSION_PHASE_RUNNING)
            ):
                return False
            current = next(
                (
                    item
                    for item in attempt.incidents.snapshot()
                    if item.incident_id == incident_id
                ),
                None,
            )
            if current is None:
                return False
            try:
                resolved = attempt.incidents.resolve_after_recovery(
                    incident_id,
                    current.revision,
                    session_active=True,
                    recovered_monotonic_ns=recovered_monotonic_ns,
                )
            except ValueError:
                return False
            attempt.confirmed_incidents[incident_id] = deepcopy(resolved)
            for plan in attempt.prepared.trials:
                retained = [
                    item
                    for item in plan.continuation_incidents
                    if item.incident_id != incident_id
                ]
                plan.ClearField("continuation_incidents")
                plan.continuation_incidents.extend(retained)
            for prompt_id, (prompt, owner) in list(
                self.incident_state.incident_prompts.items()
            ):
                if (
                    owner is attempt
                    and prompt.runtime_incident.incident_id == incident_id
                ):
                    del self.incident_state.incident_prompts[prompt_id]
            self.publisher.publish()
        if attempt.writer is not None:
            self.spawn(
                self.log_incident(
                    attempt,
                    "recovery",
                    {
                        "incident_id": incident_id,
                        "resolved_by": "spikeglx_progress",
                        "recovered_monotonic_ns": recovered_monotonic_ns,
                    },
                    at_ns=recovered_monotonic_ns,
                )
            )
        return True

    async def incident_deadline(
        self, attempt: Attempt, error_id: str, deadline_ns: int
    ) -> None:
        await asyncio.sleep(remaining_seconds(deadline_ns, clock=self.clock))
        async with self.lifecycle.lock:
            if (
                self.lifecycle.attempt is not attempt
                or attempt.interrupted
                or self.lifecycle.session.phase
                not in (pb.SESSION_PHASE_STARTING, pb.SESSION_PHASE_RUNNING)
                or error_id not in attempt.incident_errors
                or attempt.incident_id_by_error.get(error_id)
                in attempt.confirmed_incidents
            ):
                return
        await self.interrupt(
            attempt,
            f"incident {error_id} unresolved at original recovery deadline",
            issued_ns=deadline_ns,
        )
