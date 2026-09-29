"""E06 pure incident proof checks and controller-local bounded retention.

This module never grants authority from a failure code or GUI choice. Callers must
authenticate the wire source and supply their current registered context first.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.clock import require_int64_ns
from cephvr.shared.identity import require_uuid4

ClassificationStatus = Literal["pending", "continuable", "blocking"]
_LIFECYCLE_SOURCES = {
    "acquisition": frozenset({"behavioral", "tracking"}),
    "tracking": frozenset({"tracking"}),
    "vr": frozenset({"renderer"}),
}
_TERMINAL = {
    pb.RUNTIME_INCIDENT_DISPOSITION_RESOLVED,
    pb.RUNTIME_INCIDENT_DISPOSITION_SESSION_ENDED_UNANSWERED,
}


class IncidentEvidenceError(ValueError):
    """Registered identity, prepared closure or proof evidence is inconsistent."""


class IncidentCapacityError(RuntimeError):
    """A required incident/error cannot be retained without evicting active work."""


class StaleIncidentChoice(ValueError):
    """A prompt choice no longer matches its session, revision or allowed action."""


def validate_cleanup_catalogue(
    context: svc.RegisteredContext,
    *,
    registered_workers: frozenset[tuple[str, str]] = frozenset(),
) -> dict[tuple[str, str, str], pb.ResourceObligation]:
    """Validate exact registered native obligations, separate from output plans.

    The owning backend contract must establish any truly zero-resource backend;
    an empty catalogue alone never proves that no native release is required.
    """
    allowed = {
        (context.controller.role, context.controller.generation),
        (context.supervisor.role, context.supervisor.generation),
        *(
            (item.backend_name, item.backend_generation)
            for item in context.required_participants
        ),
    } | set(registered_workers)
    result: dict[tuple[str, str, str], pb.ResourceObligation] = {}
    for item in context.cleanup_resources:
        owner = (item.owner.role, item.owner.generation)
        key = (*owner, item.resource)
        if owner not in allowed or not item.resource or key in result:
            raise IncidentEvidenceError("cleanup obligation owner/key mismatch")
        if item.HasField("path") and not item.path:
            raise IncidentEvidenceError("cleanup obligation path is empty")
        result[key] = pb.ResourceObligation.FromString(item.SerializeToString())
    return result


def validate_registered_cleanup(
    context: svc.RegisteredContext,
    ready_by_backend: Mapping[str, pb.ReadyReport],
    *,
    registered_workers: frozenset[tuple[str, str]] = frozenset(),
    zero_resource_backends: frozenset[str] = frozenset(),
) -> None:
    """Controller checks the registration's complete catalogue against exact Ready."""
    expected = {
        item.backend_name: item.backend_generation
        for item in context.required_participants
    }
    if set(ready_by_backend) != set(expected):
        raise IncidentEvidenceError(
            "cleanup Ready backend set differs from registration"
        )
    aggregate: dict[tuple[str, str, str], pb.ResourceObligation] = {}
    for name, report in ready_by_backend.items():
        if (
            report.context.backend.backend_name != name
            or report.context.backend.backend_generation != expected[name]
            or report.context.work != context.work
            or not report.required_checks_passed
        ):
            raise IncidentEvidenceError("cleanup Ready identity/check mismatch")
        if not report.cleanup_resources and name not in zero_resource_backends:
            raise IncidentEvidenceError(
                "empty cleanup declaration has no zero-resource contract"
            )
        partial = svc.RegisteredContext(
            controller=context.controller,
            supervisor=context.supervisor,
            required_participants=context.required_participants,
            cleanup_resources=report.cleanup_resources,
        )
        for key, obligation in validate_cleanup_catalogue(
            partial, registered_workers=registered_workers
        ).items():
            if key in aggregate:
                raise IncidentEvidenceError("duplicate cleanup obligation across Ready")
            aggregate[key] = obligation
    registered = validate_cleanup_catalogue(
        context, registered_workers=registered_workers
    )
    if set(aggregate) != set(registered) or any(
        aggregate[key] != registered[key] for key in aggregate
    ):
        raise IncidentEvidenceError("registered cleanup obligations differ from Ready")


@dataclass(frozen=True)
class IncidentTopology:
    """Validated exact session closure from controller-registered Ready declarations."""

    context: svc.RegisteredContext
    functions: Mapping[str, pb.PreparedFunctionScope]
    registered_sources: frozenset[tuple[str, str]]
    trials: Mapping[str, pb.TrialContext]

    @classmethod
    def from_registered(
        cls,
        context: svc.RegisteredContext,
        *,
        registered_workers: frozenset[tuple[str, str]] = frozenset(),
        worker_backend: Mapping[tuple[str, str], str] | None = None,
    ) -> IncidentTopology:
        if context.work.WhichOneof("work") != "session":
            raise IncidentEvidenceError("incident closure requires session work")
        session = context.work.session
        require_uuid4(session.controller_generation)
        require_uuid4(session.session_id)
        sources: set[tuple[str, str]] = set()
        for source in (
            context.controller,
            context.supervisor,
            *(
                pb.ProcessIdentity(
                    role=backend.backend_name,
                    generation=backend.backend_generation,
                )
                for backend in context.required_participants
            ),
        ):
            require_uuid4(source.generation)
            if not source.role or (source.role, source.generation) in sources:
                raise IncidentEvidenceError("duplicate or empty registered source")
            sources.add((source.role, source.generation))
        if context.controller.generation != session.controller_generation:
            raise IncidentEvidenceError("controller/session generation mismatch")
        for worker in registered_workers:
            require_uuid4(worker[1])
            if not worker[0] or worker in sources:
                raise IncidentEvidenceError("invalid registered worker")
            sources.add(worker)
        backend_generations = {
            item.backend_name: item.backend_generation
            for item in context.required_participants
        }
        worker_backend = worker_backend or {}
        if set(worker_backend) != set(registered_workers) or any(
            backend not in backend_generations for backend in worker_backend.values()
        ):
            raise IncidentEvidenceError("worker/backend ancestry is incomplete")

        def owning_backend(owner: tuple[str, str]) -> str | None:
            if backend_generations.get(owner[0]) == owner[1]:
                return owner[0]
            return worker_backend.get(owner)

        functions: dict[str, pb.PreparedFunctionScope] = {}
        lifecycle_claims: set[tuple[str, str]] = set()
        for declaration in context.prepared_functions:
            key = declaration.resource_id
            owner = (declaration.owner.role, declaration.owner.generation)
            if not key or key in functions or owner not in sources:
                raise IncidentEvidenceError("prepared function identity/owner mismatch")
            backend = owning_backend(owner)
            if backend is None:
                raise IncidentEvidenceError(
                    "prepared function owner has no backend ancestry"
                )
            if not (
                declaration.HasField("essential_to_stimulus_control")
                and declaration.HasField("feedback_hold_required_on_loss")
                and declaration.HasField("bounded_uncertainty_supported")
            ):
                raise IncidentEvidenceError(
                    "prepared function classification is missing"
                )
            reporters = [
                (p.role, p.generation) for p in declaration.authorized_reporters
            ]
            if len(reporters) != len(set(reporters)) or any(
                reporter not in sources for reporter in reporters
            ):
                raise IncidentEvidenceError("prepared reporter is not registered")
            lifecycle = tuple(declaration.lifecycle_sources)
            if len(lifecycle) != len(set(lifecycle)):
                raise IncidentEvidenceError("prepared lifecycle source is repeated")
            if lifecycle:
                allowed_sources = _LIFECYCLE_SOURCES.get(backend)
                if allowed_sources is None or not set(lifecycle) <= allowed_sources:
                    raise IncidentEvidenceError(
                        "prepared lifecycle source/backend ownership is invalid"
                    )
                if any(
                    (backend, source_id) in lifecycle_claims for source_id in lifecycle
                ):
                    raise IncidentEvidenceError(
                        "lifecycle source has multiple functions"
                    )
                lifecycle_claims.update((backend, source_id) for source_id in lifecycle)
                if backend == "vr" and not declaration.essential_to_stimulus_control:
                    raise IncidentEvidenceError(
                        "VR renderer must be an essential function"
                    )
                if backend == "acquisition":
                    if (
                        len(lifecycle) != 1
                        or len(reporters) != 1
                        or reporters[0] not in registered_workers
                        or worker_backend[reporters[0]] != "acquisition"
                        or (owner in registered_workers and reporters[0] != owner)
                    ):
                        raise IncidentEvidenceError(
                            "camera lifecycle source requires one exact worker reporter"
                        )
                if any(reporter != owner for reporter in reporters):
                    if any(
                        owning_backend(reporter) != backend
                        for reporter in reporters
                        if reporter != owner
                    ):
                        raise IncidentEvidenceError(
                            "lifecycle reporter lacks exact backend ancestry"
                        )
            functions[key] = pb.PreparedFunctionScope.FromString(
                declaration.SerializeToString(deterministic=True)
            )
        if not functions or not any(
            item.essential_to_stimulus_control for item in functions.values()
        ):
            raise IncidentEvidenceError(
                "essential prepared function closure is missing"
            )
        if ("vr", "renderer") not in lifecycle_claims:
            raise IncidentEvidenceError(
                "essential VR renderer lifecycle source is missing"
            )
        for key, declaration in functions.items():
            closure = tuple(declaration.affected_closure_resource_ids)
            if (
                key not in closure
                or len(closure) != len(set(closure))
                or any(item not in functions for item in closure)
            ):
                raise IncidentEvidenceError(
                    "prepared function loss closure is incomplete"
                )
            if any(
                not set(functions[item].affected_closure_resource_ids) <= set(closure)
                for item in closure
            ):
                raise IncidentEvidenceError(
                    "prepared function closure is not transitive"
                )
        trials: dict[str, pb.TrialContext] = {}
        for output in context.outputs:
            output_function = functions.get(output.output_key)
            if (
                output_function is None
                or owning_backend(
                    (output_function.owner.role, output_function.owner.generation)
                )
                != output.backend.backend_name
            ):
                raise IncidentEvidenceError(
                    "reserved output lacks exact owning function"
                )
            trial = output.trial
            try:
                require_uuid4(trial.trial_id)
            except ValueError as exc:
                raise IncidentEvidenceError(
                    "reserved output trial ID is invalid"
                ) from exc
            if trial.session != session or trial.trial_number <= 0:
                raise IncidentEvidenceError("reserved output trial context differs")
            previous_trial = trials.get(trial.trial_id)
            if previous_trial is not None and previous_trial != trial:
                raise IncidentEvidenceError("trial ID identifies changed context")
            trials[trial.trial_id] = pb.TrialContext.FromString(
                trial.SerializeToString()
            )
        return cls(
            svc.RegisteredContext.FromString(
                context.SerializeToString(deterministic=True)
            ),
            functions,
            frozenset(sources),
            trials,
        )


@dataclass(frozen=True)
class IsolationProof:
    """Corroborated wire facts; local authority/accounting checks stay separate."""

    continuing_heartbeats: Mapping[tuple[str, str], pb.HeartbeatReport]
    controller_authority_valid: bool
    supervisor_authority_valid: bool
    bounded_accounting: bool


@dataclass(frozen=True)
class Classification:
    status: ClassificationStatus
    reason: str
    affected_resources: tuple[str, ...]
    original_deadline_ns: int

    @property
    def continuation_available(self) -> bool:
        return self.status == "continuable"


def _same_session(work: pb.WorkContext, session: pb.SessionContext) -> bool:
    kind = work.WhichOneof("work")
    return (kind == "session" and work.session == session) or (
        kind == "trial"
        and work.trial.session == session
        and work.trial.trial_number > 0
    )


def classify_incident(
    error: pb.ErrorReport,
    topology: IncidentTopology,
    proof: IsolationProof | None,
    *,
    now_ns: int,
    original_deadline_ns: int,
    max_evidence_age_ns: int,
) -> Classification:
    """Continue only when every affected and healthy-path obligation is proven."""
    require_int64_ns(now_ns)
    require_int64_ns(original_deadline_ns)
    require_int64_ns(max_evidence_age_ns)
    if max_evidence_age_ns <= 0:
        raise ValueError("evidence age bound must be positive")
    require_uuid4(error.error_id)
    source = (error.source.role, error.source.generation)
    session = topology.context.work.session
    if source not in topology.registered_sources or not _same_session(
        error.work, session
    ):
        return Classification(
            "blocking", "unregistered source or work", (), original_deadline_ns
        )
    if error.work.WhichOneof("work") == "trial" and (
        topology.trials.get(error.work.trial.trial_id) != error.work.trial
    ):
        return Classification(
            "blocking", "unprepared trial work", (), original_deadline_ns
        )
    if error.occurred_monotonic_ns <= 0 or error.occurred_monotonic_ns > now_ns:
        return Classification(
            "blocking", "invalid fault observation time", (), original_deadline_ns
        )

    def unknown(reason: str) -> Classification:
        return Classification(
            "pending" if now_ns <= original_deadline_ns else "blocking",
            reason
            if now_ns <= original_deadline_ns
            else f"{reason}; original recovery deadline expired",
            (),
            original_deadline_ns,
        )

    if proof is not None and not (
        proof.controller_authority_valid
        and proof.supervisor_authority_valid
        and proof.bounded_accounting
    ):
        return Classification(
            "blocking", "control authority or accounting lost", (), original_deadline_ns
        )
    fault = error.isolation
    affected = tuple(fault.affected_resource_ids)
    if not affected or len(set(affected)) != len(affected):
        return unknown("affected prepared resource set is unknown")
    if (
        fault.verified_monotonic_ns < error.occurred_monotonic_ns
        or fault.verified_monotonic_ns > now_ns
    ):
        return unknown("fault isolation observation is not current")
    for key in affected:
        declaration = topology.functions.get(key)
        if declaration is None:
            return Classification(
                "blocking",
                "fault names an unprepared resource",
                affected,
                original_deadline_ns,
            )
        reporters = {(declaration.owner.role, declaration.owner.generation)} | {
            (item.role, item.generation) for item in declaration.authorized_reporters
        }
        if source not in reporters:
            return Classification(
                "blocking",
                "source cannot attest affected resource",
                affected,
                original_deadline_ns,
            )
    closure = set().union(
        *(
            set(topology.functions[key].affected_closure_resource_ids)
            for key in affected
        )
    )
    if any(topology.functions[key].essential_to_stimulus_control for key in closure):
        return Classification(
            "blocking",
            "loss closure reaches required stimulus/control",
            affected,
            original_deadline_ns,
        )
    if proof is None or not error.HasField("isolation"):
        return unknown("isolation evidence unavailable")
    if not fault.HasField("leases_released_or_quarantined"):
        return unknown("safe lease disposition unconfirmed")
    if not fault.leases_released_or_quarantined:
        return Classification(
            "blocking",
            "unsafe resource lease confirmed",
            affected,
            original_deadline_ns,
        )
    fenced = set(fault.fenced_resource_ids)
    if (
        len(fenced) != len(fault.fenced_resource_ids)
        or not fenced <= topology.functions.keys()
    ):
        return Classification(
            "blocking",
            "fence names an unknown or repeated resource",
            affected,
            original_deadline_ns,
        )
    held = set(fault.feedback_hold_resource_ids)
    if (
        len(held) != len(fault.feedback_hold_resource_ids)
        or not held <= closure
        or any(
            not topology.functions[key].feedback_hold_required_on_loss for key in held
        )
    ):
        return Classification(
            "blocking",
            "feedback hold scope is not prepared",
            affected,
            original_deadline_ns,
        )
    required_holds = {
        key for key in closure if topology.functions[key].feedback_hold_required_on_loss
    }
    if not required_holds <= held:
        return unknown("declared feedback hold scope is incomplete")
    if held and not fault.HasField("feedback_hold_active"):
        return unknown("declared feedback hold is unconfirmed")
    if held and not fault.feedback_hold_active:
        return Classification(
            "blocking", "required feedback hold failed", affected, original_deadline_ns
        )
    undischarged = closure - fenced - held
    if any(
        not topology.functions[key].bounded_uncertainty_supported
        for key in undischarged
    ):
        return Classification(
            "blocking",
            "prepared loss closure is not isolated",
            affected,
            original_deadline_ns,
        )
    if undischarged and not (
        fault.HasField("bounded_uncertainty")
        and fault.bounded_uncertainty
        and now_ns <= original_deadline_ns
    ):
        return unknown("loss closure is not fenced or safely held")
    for key, declaration in topology.functions.items():
        if not declaration.essential_to_stimulus_control:
            continue
        owner = (declaration.owner.role, declaration.owner.generation)
        heartbeat = proof.continuing_heartbeats.get(owner)
        if (
            heartbeat is None
            or (
                heartbeat.source.role,
                heartbeat.source.generation,
            )
            != owner
            or not _same_session(heartbeat.work, session)
        ):
            return unknown("essential function heartbeat identity unavailable")
        observations = [
            item for item in heartbeat.continuing_functions if item.resource_id == key
        ]
        if len(observations) != 1:
            return unknown("essential function observation missing or duplicated")
        observation = observations[0]
        if (
            observation.observed_monotonic_ns < error.occurred_monotonic_ns
            or observation.observed_monotonic_ns > now_ns
            or now_ns - observation.observed_monotonic_ns > max_evidence_age_ns
        ):
            return unknown("essential function observation is stale")
        if not all(
            observation.HasField(field)
            for field in (
                "functioning",
                "schedule_valid",
                "host_clock_valid",
                "control_path_valid",
            )
        ):
            return unknown("essential function status is incomplete")
        if not (
            observation.functioning
            and observation.schedule_valid
            and observation.host_clock_valid
            and observation.control_path_valid
        ):
            return Classification(
                "blocking",
                "required continuing function failed",
                affected,
                original_deadline_ns,
            )
    return Classification(
        "continuable",
        "isolated prepared loss with continuing stimulus/control",
        affected,
        original_deadline_ns,
    )


class IncidentRegistry:
    """Bounded controller-local current incidents; active scopes are never evicted."""

    def __init__(
        self,
        session: pb.SessionContext,
        *,
        max_incidents: int,
        max_error_ids: int,
        max_bytes: int,
    ) -> None:
        require_uuid4(session.controller_generation)
        require_uuid4(session.session_id)
        if max_incidents <= 0 or max_error_ids <= 0 or max_bytes <= 0:
            raise ValueError("incident bounds must be positive")
        self.session = pb.SessionContext.FromString(session.SerializeToString())
        self.max_incidents = max_incidents
        self.max_error_ids = max_error_ids
        self.max_bytes = max_bytes
        self._records: dict[str, pb.RuntimeIncident] = {}
        self._episodes: dict[tuple[str, str, str], str] = {}
        self._errors: dict[str, bytes] = {}
        self._deadlines: dict[tuple[str, str, str], int] = {}
        self._finalized = False
        self.retained_truncated = False

    def observe(
        self,
        error: pb.ErrorReport,
        classification: Classification,
        *,
        episode_id: str | None = None,
        consequence: str,
    ) -> pb.RuntimeIncident:
        if self._finalized:
            raise IncidentEvidenceError(
                "finalized session cannot gain incident evidence"
            )
        episode_id = (
            episode_id
            if episode_id is not None
            else (
                error.incident_episode_id
                if error.HasField("incident_episode_id")
                else error.error_id
            )
        )
        require_uuid4(episode_id)
        require_uuid4(error.error_id)
        require_int64_ns(classification.original_deadline_ns)
        if not _same_session(error.work, self.session) or not consequence:
            raise IncidentEvidenceError("incident work or consequence is missing")
        encoded = error.SerializeToString(deterministic=True)
        previous = self._errors.get(error.error_id)
        if previous is not None and previous != encoded:
            raise IncidentEvidenceError("error ID was reused with changed evidence")
        episode = (error.source.role, error.source.generation, episode_id)
        old_deadline = self._deadlines.get(episode)
        if (
            old_deadline is not None
            and old_deadline != classification.original_deadline_ns
        ):
            raise IncidentEvidenceError("incident recovery deadline changed")
        records = dict(self._records)
        episodes = dict(self._episodes)
        errors = dict(self._errors)
        deadlines = dict(self._deadlines)
        truncated = self.retained_truncated
        incident_id = episodes.get(episode)
        if incident_id is None:
            if previous is not None:
                raise IncidentEvidenceError("error ID was moved to a new episode")
            if len(records) >= self.max_incidents:
                evict = next(
                    (
                        key
                        for key, value in records.items()
                        if value.disposition in _TERMINAL
                    ),
                    None,
                )
                if evict is None:
                    raise IncidentCapacityError("active incident capacity exhausted")
                removed = records.pop(evict)
                for old_error in removed.error_ids:
                    errors.pop(old_error, None)
                episodes = {
                    key: value for key, value in episodes.items() if value != evict
                }
                deadlines = {
                    key: value for key, value in deadlines.items() if key in episodes
                }
                truncated = True
            incident_id = str(uuid4())
            episodes[episode] = incident_id
            deadlines[episode] = classification.original_deadline_ns
            record = pb.RuntimeIncident(
                incident_id=incident_id,
                revision=1,
                work=error.work,
                error_ids=[error.error_id],
                affected_resources=classification.affected_resources,
                consequence=consequence,
                disposition=(
                    pb.RUNTIME_INCIDENT_DISPOSITION_AUTOMATIC_STOP
                    if classification.status == "blocking"
                    else pb.RUNTIME_INCIDENT_DISPOSITION_AWAITING_OPERATOR
                ),
                first_observed_monotonic_ns=error.occurred_monotonic_ns,
                last_observed_monotonic_ns=error.occurred_monotonic_ns,
                occurrence_count=1,
                continuation_available=classification.continuation_available,
            )
            records[incident_id] = record
        else:
            record = pb.RuntimeIncident.FromString(
                records[incident_id].SerializeToString()
            )
            cumulative_scope = tuple(
                dict.fromkeys(
                    (*record.affected_resources, *classification.affected_resources)
                )
            )
            material = (
                tuple(record.affected_resources) != cumulative_scope
                or record.consequence != consequence
                or record.continuation_available
                != classification.continuation_available
                or classification.status == "blocking"
                and record.disposition != pb.RUNTIME_INCIDENT_DISPOSITION_AUTOMATIC_STOP
            )
            if previous is None:
                if len(record.error_ids) >= self.max_error_ids:
                    raise IncidentCapacityError("incident error ID capacity exhausted")
                record.error_ids.append(error.error_id)
                record.occurrence_count += 1
                record.last_observed_monotonic_ns = max(
                    record.last_observed_monotonic_ns, error.occurred_monotonic_ns
                )
                record.revision += 1
            if material:
                record.affected_resources[:] = cumulative_scope
                record.consequence = consequence
                # Acknowledgement only covers the previous informational view.
                # Material new blocking evidence must be shown again.
                if classification.status == "blocking":
                    record.acknowledged = False
                if record.disposition in (
                    pb.RUNTIME_INCIDENT_DISPOSITION_AUTOMATIC_STOP,
                    pb.RUNTIME_INCIDENT_DISPOSITION_ABORT_SELECTED,
                ):
                    # New facts cannot undo a committed stop or Abort decision.
                    record.continuation_available = False
                else:
                    record.continuation_available = (
                        classification.continuation_available
                    )
                    record.disposition = (
                        pb.RUNTIME_INCIDENT_DISPOSITION_AUTOMATIC_STOP
                        if classification.status == "blocking"
                        else pb.RUNTIME_INCIDENT_DISPOSITION_AWAITING_OPERATOR
                    )
                if previous is not None:
                    record.revision += 1
            records[incident_id] = record
        errors[error.error_id] = encoded
        used_bytes = sum(len(item) for item in errors.values()) + sum(
            len(item.SerializeToString(deterministic=True)) for item in records.values()
        )
        if used_bytes > self.max_bytes:
            raise IncidentCapacityError("incident serialized byte capacity exhausted")
        self._records = records
        self._episodes = episodes
        self._errors = errors
        self._deadlines = deadlines
        self.retained_truncated = truncated
        return pb.RuntimeIncident.FromString(record.SerializeToString())

    def choose(
        self,
        incident_id: str,
        expected_revision: int,
        choice: Literal["continue_session", "abort_session", "acknowledge"],
        *,
        session_active: bool,
    ) -> pb.RuntimeIncident:
        require_uuid4(incident_id)
        existing = self._records.get(incident_id)
        if (
            existing is None
            or not session_active
            and choice != "acknowledge"
            or existing.revision != expected_revision
            or choice not in ("continue_session", "abort_session", "acknowledge")
            or choice == "acknowledge"
            and existing.disposition != pb.RUNTIME_INCIDENT_DISPOSITION_AUTOMATIC_STOP
            or choice == "acknowledge"
            and existing.acknowledged
            or choice != "acknowledge"
            and existing.disposition
            != pb.RUNTIME_INCIDENT_DISPOSITION_AWAITING_OPERATOR
            or choice == "continue_session"
            and not existing.continuation_available
        ):
            raise StaleIncidentChoice("incident choice is stale or unavailable")
        record = pb.RuntimeIncident.FromString(existing.SerializeToString())
        if choice == "acknowledge":
            record.acknowledged = True
        else:
            record.disposition = (
                pb.RUNTIME_INCIDENT_DISPOSITION_CONTINUE_SELECTED
                if choice == "continue_session"
                else pb.RUNTIME_INCIDENT_DISPOSITION_ABORT_SELECTED
            )
        record.revision += 1
        current_bytes = sum(len(item) for item in self._errors.values()) + sum(
            len(item.SerializeToString(deterministic=True))
            for key, item in self._records.items()
            if key != incident_id
        )
        if (
            current_bytes + len(record.SerializeToString(deterministic=True))
            > self.max_bytes
        ):
            raise IncidentCapacityError(
                "incident choice exceeds serialized byte capacity"
            )
        self._records[incident_id] = record
        return pb.RuntimeIncident.FromString(record.SerializeToString())

    def end_session(self) -> None:
        records = {
            key: pb.RuntimeIncident.FromString(value.SerializeToString())
            for key, value in self._records.items()
        }
        for record in records.values():
            if record.disposition == pb.RUNTIME_INCIDENT_DISPOSITION_AWAITING_OPERATOR:
                record.disposition = (
                    pb.RUNTIME_INCIDENT_DISPOSITION_SESSION_ENDED_UNANSWERED
                )
                record.continuation_available = False
                record.revision += 1
        used_bytes = sum(len(item) for item in self._errors.values()) + sum(
            len(item.SerializeToString(deterministic=True)) for item in records.values()
        )
        if used_bytes > self.max_bytes:
            raise IncidentCapacityError(
                "terminal incident view exceeds serialized byte capacity"
            )
        self._records = records
        self._finalized = True

    def snapshot(self) -> tuple[pb.RuntimeIncident, ...]:
        return tuple(
            pb.RuntimeIncident.FromString(record.SerializeToString())
            for record in self._records.values()
        )
