"""E06 pure incident topology and proof checks.

This module never grants authority from a failure code or GUI choice. Callers must
authenticate the wire source and supply their current registered context first.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.clock import require_int64_ns
from cephvr.shared.identity import require_uuid4

ClassificationStatus = Literal["pending", "continuable", "blocking"]
_LIFECYCLE_SOURCES = {
    "acquisition": frozenset({"behavioral", "tracking"}),
    "tracking": frozenset({"tracking"}),
    "visual_stimulus": frozenset({"renderer"}),
}


class IncidentEvidenceError(ValueError):
    """Registered identity, prepared closure or proof evidence is inconsistent."""


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
        """Validate the complete function graph and exact registered worker ancestry."""
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
                if (
                    backend == "visual_stimulus"
                    and not declaration.essential_to_stimulus_control
                ):
                    raise IncidentEvidenceError(
                        "Visual Stimulus renderer must be an essential function"
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
        if ("visual_stimulus", "renderer") not in lifecycle_claims:
            raise IncidentEvidenceError(
                "essential Visual Stimulus renderer lifecycle source is missing"
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
