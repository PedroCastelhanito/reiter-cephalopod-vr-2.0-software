"""Detailed Cleanup proof and late Finished reconciliation (E04/E06)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from copy import deepcopy
from functools import partial
from typing import Any, Protocol
from uuid import uuid4

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.evidence import outputs_satisfied
from cephvr.controller.state import (
    Attempt,
    LifecycleState,
    LimitsState,
    SupervisorState,
)
from cephvr.shared.cleanup_outputs import cleanup_output_discharged
from cephvr.shared.resources import cleanup_command_fenced


class CompletionHooks(Protocol):
    @property
    def publish(self) -> Callable[[], None]: ...

    @property
    def spawn(self) -> Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]]: ...

    @property
    def late_cleanup(self) -> Callable[[Attempt], Coroutine[Any, Any, None]]: ...

    @property
    def log_event(self) -> Callable[..., Coroutine[Any, Any, None]]: ...

    @property
    def recovery_log_done(self) -> Callable[[Attempt, asyncio.Task[object]], None]: ...


class DetailedCompletion:
    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        supervisor: SupervisorState,
        limits: LimitsState,
        hooks: CompletionHooks,
    ) -> None:
        self.lifecycle = lifecycle
        self.supervisor = supervisor
        self.limits = limits
        self.hooks = hooks

    def cleanup(self, attempt: Attempt, payload: pb.CleanupReport) -> pb.ReportReceipt:
        name = payload.source.role
        backend = attempt.required.get(name)
        registered = attempt.registered_context
        health = self.supervisor.processes.get(name)
        heartbeat = (
            health.last_heartbeat
            if health is not None and health.HasField("last_heartbeat")
            else None
        )
        catalogued = (
            heartbeat is not None
            and heartbeat.source == payload.source
            and heartbeat.work.WhichOneof("work") == "session"
            and heartbeat.work.session == attempt.context
            and heartbeat.HasField("cleanup_resources_revision")
        )
        obligations = {
            resource.resource: resource
            for resource in (
                attempt.ready[name].cleanup_resources
                if attempt.incident_topology is not None and name in attempt.ready
                else heartbeat.cleanup_resources
                if catalogued and heartbeat is not None
                else ()
            )
        }
        source_obligations = (
            attempt.ready[name].cleanup_resources
            if attempt.incident_topology is not None and name in attempt.ready
            else heartbeat.cleanup_resources
            if catalogued and heartbeat is not None
            else ()
        )
        revision = (
            attempt.cleanup_catalogue_revisions.get(name)
            if attempt.incident_topology is not None
            else heartbeat.cleanup_resources_revision
            if catalogued and heartbeat is not None
            else None
        )
        releases = {resource.resource: resource for resource in payload.resources}
        expected_outputs = (
            {
                output.output_key
                for output in registered.outputs
                if output.backend.backend_name == name
            }
            if attempt.incident_topology is not None and registered is not None
            else set()
        )
        actual_outputs = {output.output_key: output for output in payload.outputs}
        if (
            backend is None
            or payload.source.generation != backend.context.backend_generation
            or payload.work.WhichOneof("work") != "session"
            or payload.work.session != attempt.context
            or not payload.trial_activity_stopped
            or registered is None
            or not cleanup_command_fenced(payload, registered)
            or revision is None
            or not payload.HasField("cleanup_resources_revision")
            or payload.cleanup_resources_revision != revision
            or payload.verified_monotonic_ns <= 0
            or set(releases) != set(obligations)
            or len(obligations) != len(source_obligations)
            or len(releases) != len(payload.resources)
            or any(
                not release.released
                or release.failure.code
                or release.failure.message
                or release.HasField("path") != obligations[key].HasField("path")
                or release.HasField("path")
                and release.path != obligations[key].path
                for key, release in releases.items()
            )
            or set(actual_outputs) != expected_outputs
            or len(actual_outputs) != len(payload.outputs)
            or any(
                not cleanup_output_discharged(output)
                for output in actual_outputs.values()
            )
        ):
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="EVIDENCE",
                    message="cleanup identity or release proof missing",
                ),
            )
        previous_cleanup = attempt.cleanup.get(name)
        if previous_cleanup is not None and previous_cleanup.SerializeToString(
            deterministic=True
        ) != payload.SerializeToString(deterministic=True):
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="CONFLICT", message="changed duplicate Cleanup"
                ),
            )
        attempt.cleanup[name] = deepcopy(payload)
        attempt.changed.set()
        self.hooks.publish()
        if (
            self.lifecycle.session.phase
            in (pb.SESSION_PHASE_CONFIGURATION, pb.SESSION_PHASE_ENDED)
            and not self.lifecycle.session.cleanup_confirmed
        ):
            self.hooks.spawn(self.hooks.late_cleanup(attempt))
        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    def finished(
        self, attempt: Attempt, payload: pb.FinishedReport, name: str, ingress_ns: int
    ) -> pb.ReportReceipt | None:
        backend = attempt.required[name]
        trial_expected_outputs = [
            output
            for output in attempt.prepared.outputs
            if output.trial == attempt.prepared.trials[attempt.trial_index].context
            and output.backend.backend_name == name
        ]
        unavailable = {
            key
            for incident in attempt.confirmed_incidents.values()
            for key in incident.affected_resources
        }
        interrupted_recovery_deadline = (
            min(
                attempt.finished_deadline_ns + self.limits.current.recovery_ns,
                attempt.finalization_deadline_ns,
            )
            if attempt.finalization_deadline_ns
            else 0
        )
        within_finished_gate = (
            ingress_ns <= attempt.finished_deadline_ns
            or attempt.recovering_evidence == "finished"
            and ingress_ns <= attempt.recovery_deadline_ns
            or attempt.interrupted
            and ingress_ns <= interrupted_recovery_deadline
            and not attempt.recovery_log_closed
        )
        earliest_finished_ns = (
            attempt.target_ns if attempt.interruption_issued_ns else attempt.end_ns
        )
        if (
            self.lifecycle.trial.phase
            not in (pb.TRIAL_PHASE_RUNNING, pb.TRIAL_PHASE_FINALIZING)
            or ingress_ns < earliest_finished_ns
            or not within_finished_gate
            or not payload.trial_activity_stopped
            or not outputs_satisfied(
                trial_expected_outputs,
                payload.outputs,
                unavailable=unavailable,
            )
        ):
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="EVIDENCE", message="Finished closure incomplete"
                ),
            )
        old_finished = attempt.finished.get(name)
        if old_finished is not None and old_finished.SerializeToString(
            deterministic=True
        ) != payload.SerializeToString(deterministic=True):
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="CONFLICT", message="changed duplicate Finished"
                ),
            )
        if old_finished is None and ingress_ns > attempt.finished_deadline_ns:
            trial_id = payload.context.work.trial.trial_id
            recovered_key = (trial_id, name)
            if (
                len(attempt.recovered_finished)
                >= len(attempt.prepared.trials) * len(attempt.required)
                and recovered_key not in attempt.recovered_finished
            ):
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(
                        code="CAPACITY",
                        message="late Finished retention exhausted",
                    ),
                )
            attempt.recovered_finished[recovered_key] = deepcopy(payload)
            closure = [
                {
                    "output_key": item.output_key,
                    "closure": pb.OutputClosure.Name(item.closure),
                }
                for item in payload.outputs
            ]
            recovered = pb.RecoveryState(
                attempt_id=str(uuid4()),
                affected=pb.ProcessIdentity(
                    role=name, generation=backend.context.backend_generation
                ),
                work=pb.WorkContext(trial=payload.context.work.trial),
                trigger=pb.Failure(
                    code="FINISHED_TIMEOUT",
                    message="initial Finished evidence deadline expired",
                ),
                action="reconcile exact Finished output closure",
                start_monotonic_ns=attempt.finished_deadline_ns,
                deadline_monotonic_ns=attempt.finished_deadline_ns
                + self.limits.current.recovery_ns,
                completion_monotonic_ns=ingress_ns,
                progress="exact late Finished accepted; original trial outcome unchanged",
                outcome=pb.RECOVERY_OUTCOME_COMPLETED,
                evidence=f"{len(payload.outputs)} exact output closure result(s) retained",
            )
            self.supervisor.controller_recoveries.append(recovered)
            self.supervisor.controller_recoveries = (
                self.supervisor.controller_recoveries[-256:]
            )
            if (
                attempt.writer is not None
                and not attempt.writer_closed
                and not attempt.recovery_log_closed
            ):
                recovery_task = self.hooks.spawn(
                    self.hooks.log_event(
                        attempt,
                        "recovery",
                        details={
                            "component": "Finished",
                            "action": "reconcile exact output closure",
                            "trial_id": trial_id,
                            "backend": name,
                            "outputs": closure,
                            "initial_deadline_ns": attempt.finished_deadline_ns,
                        },
                        at_ns=ingress_ns,
                        trial_number=payload.context.work.trial.trial_number,
                        outcome="completed",
                    )
                )
                attempt.recovery_log_tasks.add(recovery_task)
                recovery_task.add_done_callback(
                    partial(self.hooks.recovery_log_done, attempt)
                )
        attempt.finished[name] = deepcopy(payload)
        return None
