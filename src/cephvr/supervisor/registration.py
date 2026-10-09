"""Launch ancestry and registered work identity checks (E08)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandCapacityError, CommandConflict, CommandLedger
from cephvr.shared.identity import require_uuid4
from cephvr.shared.incidents import IncidentEvidenceError, IncidentTopology
from cephvr.shared.resources import (
    ResourceCatalogueError,
    ResourceObligationRegistry,
    validate_cleanup_fence_update,
)
from cephvr.supervisor.receipts import accepted, failure, rejected
from cephvr.supervisor.registry import (
    BACKEND_ROLES,
    TOP_LEVEL_ROLES,
    LaunchRegistry,
)
from cephvr.supervisor.state import HealthState, RecoveryState, RegistrationState
from cephvr.supervisor.worker_context import work_covered_by


class RegistrationCoordinator:
    def __init__(
        self,
        *,
        state: RegistrationState,
        registry: LaunchRegistry,
        controller: types.ProcessIdentity,
        identity: types.ProcessIdentity,
        recovery: RecoveryState,
        health: HealthState,
        commands: CommandLedger,
        lock: asyncio.Lock,
        max_retained_entries: int,
        max_message_bytes: int,
        cleanup_blockers: Callable[[], list[types.CleanupBlocker]],
        verified_continuation: Callable[[types.ErrorReport], bool],
        changed: Callable[[], None],
    ) -> None:
        self.state = state
        self.registry = registry
        self.controller = controller
        self.identity = identity
        self.recovery = recovery
        self.health = health
        self.commands = commands
        self.lock = lock
        self.max_retained_entries = max_retained_entries
        self.max_message_bytes = max_message_bytes
        self.cleanup_blockers = cleanup_blockers
        self.verified_continuation = verified_continuation
        self.changed = changed

    def same_work(self, work: types.WorkContext) -> bool:
        return work_covered_by(
            self.state.context.work if self.state.context else None, work
        )

    def required_backends(self) -> dict[str, str]:
        if self.state.context is None:
            return {}
        return {
            x.backend_name: x.backend_generation
            for x in self.state.context.required_participants
        }

    def worker_backend_ancestry(
        self, participants: set[tuple[str, str]]
    ) -> dict[tuple[str, str], str]:
        """Resolve only exact active descendants of required backend generations."""
        top_roles = TOP_LEVEL_ROLES | {"supervisor"}
        states: dict[tuple[str, str], wire.LaunchState] = {}
        for state in self.registry.states():
            if state.HasField("pid") and state.phase == wire.LAUNCH_PHASE_OPERATIONAL:
                child = (state.plan.child.role, state.plan.child.generation)
                if child in states:
                    raise IncidentEvidenceError("duplicate active launch identity")
                states[child] = state
        ancestry: dict[tuple[str, str], str] = {}
        for child, state in states.items():
            if child[0] in top_roles:
                continue
            visited = {child}
            current = state
            while True:
                owner = (current.plan.owner.role, current.plan.owner.generation)
                if owner in visited:
                    raise IncidentEvidenceError(
                        "worker launch ancestry contains a cycle"
                    )
                if owner in participants:
                    ancestry[child] = owner[0]
                    break
                visited.add(owner)
                parent = states.get(owner)
                if parent is None:
                    break
                current = parent
        return ancestry

    def catalogue_owners(self, backend: tuple[str, str]) -> frozenset[tuple[str, str]]:
        owners = {backend}
        changed = True
        states = self.registry.states()
        while changed:
            changed = False
            for state in states:
                owner = (state.plan.owner.role, state.plan.owner.generation)
                child = (state.plan.child.role, state.plan.child.generation)
                if (
                    owner in owners
                    and state.phase == wire.LAUNCH_PHASE_OPERATIONAL
                    and child not in owners
                ):
                    owners.add(child)
                    changed = True
        return frozenset(owners)

    def source_registered(
        self, source: types.ProcessIdentity, *, allow_worker: bool = False
    ) -> bool:
        """Controller and operational coordinators; workers only when allowed (E08).

        Workers heartbeat to their coordinator, so heartbeats and cleanup evidence
        use the default. Errors and previews also admit exact operational workers.
        """
        if source == self.controller:
            return True
        if not allow_worker and source.role not in BACKEND_ROLES:
            return False
        # Tolerant: one unreadable job must not fail every other source's report.
        for state in self.registry.states(tolerant=True):
            if (
                state.plan.child == source
                and state.phase == wire.LAUNCH_PHASE_OPERATIONAL
            ):
                return True
        return False

    @staticmethod
    def work_key(work: types.WorkContext) -> str:
        kind = work.WhichOneof("work")
        if kind == "session":
            return require_uuid4(work.session.session_id)
        if kind == "trial":
            return require_uuid4(work.trial.session.session_id)
        raise ValueError("session work context is required")

    def _validate_operational_context(
        self,
        request: wire.RegisterContextRequest,
        participant_keys: set[tuple[str, str]],
    ) -> tuple[
        dict[tuple[str, str], str],
        IncidentTopology | None,
        list[tuple[ResourceObligationRegistry, list[types.ResourceObligation]]],
    ]:
        """Check live launches, resource ownership and final catalogues under lock."""
        active_states = self.registry.states()
        for participant in request.context.required_participants:
            matching = [
                state
                for state in active_states
                if state.plan.child.role == participant.backend_name
                and state.plan.child.generation == participant.backend_generation
                and state.phase == wire.LAUNCH_PHASE_OPERATIONAL
                and state.HasField("host_clock")
            ]
            if len(matching) != 1:
                raise ValueError(
                    f"backend {participant.backend_name} generation is not operational"
                )
        if (
            self.state.context
            and not self.same_work(request.context.work)
            and self.cleanup_blockers()
        ):
            raise ValueError("previous work still has cleanup obligations")
        validate_cleanup_fence_update(
            self.state.context,
            request.context,
            max_fences=self.max_retained_entries,
            max_bytes=self.max_message_bytes // 4,
        )
        cleanup_keys: set[tuple[str, str, str]] = set()
        allowed_resource_owners = frozenset().union(
            *(self.catalogue_owners(participant) for participant in participant_keys)
        )
        for obligation in request.context.cleanup_resources:
            owner = (obligation.owner.role, obligation.owner.generation)
            key = (*owner, obligation.resource)
            if (
                owner not in allowed_resource_owners
                or not obligation.resource
                or key in cleanup_keys
            ):
                raise ValueError(
                    "cleanup obligation owner/resource is invalid or duplicated"
                )
            cleanup_keys.add(key)
        worker_backend = (
            dict(self.state.prepared_worker_backend)
            if self.state.topology is not None and self.same_work(request.context.work)
            else self.worker_backend_ancestry(participant_keys)
        )
        topology = (
            IncidentTopology.from_registered(
                request.context,
                registered_workers=frozenset(worker_backend),
                worker_backend=worker_backend,
            )
            if request.context.prepared_functions
            else None
        )
        if topology is None and (
            request.context.outputs or request.context.cleanup_resources
        ):
            raise ValueError("resource obligations require completed prepared topology")
        if (
            self.state.topology is not None
            and self.same_work(request.context.work)
            and topology is None
        ):
            raise ValueError("prepared topology cannot regress within work")
        final_catalogues: list[
            tuple[ResourceObligationRegistry, list[types.ResourceObligation]]
        ] = []
        if topology is not None:
            assigned = 0
            for participant in request.context.required_participants:
                catalogue_key = (
                    participant.backend_name,
                    participant.backend_generation,
                )
                catalogue = self.state.catalogues.get(catalogue_key)
                if catalogue is None:
                    raise ResourceCatalogueError(
                        "preliminary cleanup catalogue is absent"
                    )
                catalogue.allowed_owners = self.catalogue_owners(catalogue_key)
                items = [
                    item
                    for item in request.context.cleanup_resources
                    if (item.owner.role, item.owner.generation)
                    in catalogue.allowed_owners
                ]
                catalogue.verify_final(items)
                assigned += len(items)
                final_catalogues.append((catalogue, items))
            if assigned != len(request.context.cleanup_resources):
                raise ResourceCatalogueError(
                    "final cleanup owner has no registered catalogue"
                )
        return worker_backend, topology, final_catalogues

    def _apply_registration(
        self,
        request: wire.RegisterContextRequest,
        worker_backend: dict[tuple[str, str], str],
        topology: IncidentTopology | None,
        final_catalogues: list[
            tuple[ResourceObligationRegistry, list[types.ResourceObligation]]
        ],
    ) -> tuple[wire.RegistrationReceipt, bool]:
        """Commit the accepted context and replay receipt under the same lock."""
        admission = self.commands.admit(
            request.command_id,
            request.SerializeToString(deterministic=True),
            host_time_ns(),
            work_key=self.work_key(request.context.work),
        )
        if admission.replayed:
            if admission.record.result is None:
                raise ValueError("matching registration is still pending")
            return wire.RegistrationReceipt.FromString(admission.record.result), False
        if self.state.context and not self.same_work(request.context.work):
            finalized_ns = host_time_ns()
            prior_work_key = self.work_key(self.state.context.work)
            self.commands.finalize_work(
                prior_work_key,
                finalized_ns,
            )
            self.registry.finalize_work(prior_work_key, finalized_ns)
            self.commands.prune(finalized_ns)
            self.recovery.cleanup.clear()
            self.state.catalogues.clear()
            self.health.heartbeat_reports.clear()
            self.health.pending_error_deadlines.clear()
            self.recovery.issued_cleanup_commands.clear()
        if not self.state.catalogues:
            self.state.catalogues = {
                (
                    participant.backend_name,
                    participant.backend_generation,
                ): ResourceObligationRegistry(
                    types.ProcessIdentity(
                        role=participant.backend_name,
                        generation=participant.backend_generation,
                    ),
                    request.context.work,
                    allowed_owners=frozenset(
                        {
                            (
                                participant.backend_name,
                                participant.backend_generation,
                            )
                        }
                    ),
                    max_resources=self.max_retained_entries,
                    max_bytes=self.max_message_bytes // 4,
                )
                for participant in request.context.required_participants
            }
        self.state.context = wire.RegisteredContext.FromString(
            request.context.SerializeToString()
        )
        self.state.topology = topology
        self.state.prepared_worker_backend = (
            dict(worker_backend) if topology is not None else {}
        )
        for catalogue, items in final_catalogues:
            catalogue.seal_final(items)
        for error_id in list(self.health.pending_error_deadlines):
            if self.verified_continuation(self.health.errors[error_id]):
                del self.health.pending_error_deadlines[error_id]
        receipt = wire.RegistrationReceipt(
            admission=accepted(request.command_id),
            registered=self.state.context,
        )
        self.commands.complete(
            request.command_id,
            receipt.SerializeToString(deterministic=True),
            host_time_ns(),
        )
        return receipt, True

    @staticmethod
    def _participant_keys(
        request: wire.RegisterContextRequest,
    ) -> set[tuple[str, str]]:
        """Stateless participant checks; returns the exact required participant keys."""
        for participant in request.context.required_participants:
            require_uuid4(participant.backend_generation)
            if participant.backend_name not in BACKEND_ROLES:
                raise ValueError("unsupported required backend")
        if not any(
            x.backend_name == "visual_stimulus"
            for x in request.context.required_participants
        ):
            raise ValueError("required Visual Stimulus coordinator is absent")
        participant_keys = {
            (x.backend_name, x.backend_generation)
            for x in request.context.required_participants
        }
        if len(participant_keys) != len(request.context.required_participants):
            raise ValueError("duplicate required participant")
        return participant_keys

    @staticmethod
    def _validate_outputs(
        request: wire.RegisterContextRequest,
        participant_keys: set[tuple[str, str]],
    ) -> None:
        output_keys: set[str] = set()
        for output in request.context.outputs:
            if (
                output.backend.backend_name,
                output.backend.backend_generation,
            ) not in participant_keys:
                raise ValueError("output owner is not a required participant")
            if not output.output_key or output.output_key in output_keys:
                raise ValueError("duplicate or empty output key")
            output_keys.add(output.output_key)

    async def register_context(
        self, request: wire.RegisterContextRequest
    ) -> wire.RegistrationReceipt:
        try:
            require_uuid4(request.command_id)
            if (
                request.context.controller != self.controller
                or request.context.supervisor != self.identity
            ):
                raise ValueError("authority generation mismatch")
            old = self.commands.get(request.command_id)
            if old is not None:
                if old.canonical_request != request.SerializeToString(
                    deterministic=True
                ):
                    raise CommandConflict(
                        "command ID identifies a changed registration"
                    )
                if old.result is not None:
                    return wire.RegistrationReceipt.FromString(old.result)
                raise ValueError("matching registration is still pending")
            if not request.context.HasField(
                "work"
            ) or not request.context.work.WhichOneof("work"):
                raise ValueError("registered work is required")
            participant_keys = self._participant_keys(request)
            if self.state.context and self.same_work(request.context.work):
                prior_participants = {
                    (item.backend_name, item.backend_generation)
                    for item in self.state.context.required_participants
                }
                if participant_keys != prior_participants:
                    raise ValueError(
                        "registered participant set cannot change within work"
                    )
            self._validate_outputs(request, participant_keys)
            async with self.lock:
                worker_backend, topology, final_catalogues = (
                    self._validate_operational_context(request, participant_keys)
                )
                receipt, changed = self._apply_registration(
                    request, worker_backend, topology, final_catalogues
                )
            if changed:
                self.changed()
            return receipt
        except (
            ValueError,
            IncidentEvidenceError,
            ResourceCatalogueError,
            CommandConflict,
            CommandCapacityError,
        ) as exc:
            return wire.RegistrationReceipt(
                admission=rejected(request.command_id, exc),
                failure=failure(exc),
            )
