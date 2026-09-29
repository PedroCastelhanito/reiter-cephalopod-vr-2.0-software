"""Supervisor control service and independent safety state (E04/E06/E08)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

import grpc

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import services_pb2_grpc
from cephvr.control.v1 import types_pb2 as types
from cephvr.platform.windows.bootstrap import run_pipe_io_daemon
from cephvr.shared.auth import AuthenticationError, require_authenticated_peer
from cephvr.shared.clock import describe_host_clock, host_time_ns
from cephvr.shared.commands import CommandCapacityError, CommandConflict, CommandLedger
from cephvr.shared.credentials import default_runtime_root
from cephvr.shared.emergency import write_emergency_report
from cephvr.shared.identity import require_uuid4
from cephvr.shared.incidents import (
    IncidentEvidenceError,
    IncidentTopology,
    IsolationProof,
    classify_incident,
)
from cephvr.shared.recovery import RecoveryStore
from cephvr.shared.resources import (
    ResourceCatalogueError,
    ResourceObligationRegistry,
    cleanup_command_fenced,
    validate_cleanup_fence_update,
)
from cephvr.supervisor.registry import LaunchError, LaunchRegistry, NativeLaunches


class SupervisorOutbound(Protocol):
    async def report_interruption(self, report: wire.InterruptionReport) -> None: ...
    async def report_status(self, report: wire.SupervisorStatusReport) -> None: ...
    async def interrupt_backend(
        self, target: types.BackendContext, request: wire.InterruptSessionRequest
    ) -> None: ...
    async def shutdown_backend(
        self, target: types.BackendContext, request: wire.BackendCommand
    ) -> None: ...
    async def cleanup_backend(
        self, target: types.BackendContext, request: wire.BackendCommand
    ) -> None: ...
    async def notify_launcher_shutdown(self, deadline_ns: int, cause: str) -> None: ...
    async def report_heartbeat(self, report: types.HeartbeatReport) -> None: ...


@dataclass(frozen=True)
class TrustedPeer:
    role: str
    generation: str
    token: str


class SupervisorRuntime(services_pb2_grpc.SupervisorServiceServicer):
    def __init__(
        self,
        *,
        identity: types.ProcessIdentity,
        controller: types.ProcessIdentity,
        credentials: dict[tuple[str, str], str],
        native: NativeLaunches,
        outbound: SupervisorOutbound,
        software_root: Path,
        silence_timeout_ns: int = 15_000_000_000,
        emergency_timeout_ns: int = 5_000_000_000,
        application_backstop_ns: int = 90_000_000_000,
        max_message_bytes: int = 16 * 1024 * 1024,
        max_retained_entries: int = 256,
        command_retention_ns: int = 300_000_000_000,
        graceful_exit_ns: int = 5_000_000_000,
        terminate_exit_ns: int = 2_000_000_000,
        heartbeat_interval_ns: int = 5_000_000_000,
        gate_controller_ack: bool = False,
    ) -> None:
        if identity.role != "supervisor" or controller.role != "controller":
            raise ValueError("supervisor/controller process roles are required")
        require_uuid4(identity.generation)
        require_uuid4(controller.generation)
        if (controller.role, controller.generation) not in credentials:
            raise ValueError("controller credential is not registered")
        self.identity = identity
        self.controller = controller
        self.credentials = dict(credentials)
        self.registry = LaunchRegistry(native, silence_timeout_ns)
        self.commands = CommandLedger(
            identity.generation,
            command_retention_ns,
            max_records=1024,
            max_bytes=16 * 1024 * 1024,
            result_reservation_bytes=64 * 1024,
        )
        self.native = native
        self.outbound = outbound
        self.software_root = Path(software_root)
        self.silence_timeout_ns = silence_timeout_ns
        self.emergency_timeout_ns = emergency_timeout_ns
        self.application_backstop_ns = application_backstop_ns
        self.graceful_exit_ns = graceful_exit_ns
        self.terminate_exit_ns = terminate_exit_ns
        self.heartbeat_interval_ns = heartbeat_interval_ns
        self.max_message_bytes = max_message_bytes
        self.clock = describe_host_clock()
        self.last_heartbeat: dict[tuple[str, str], int] = {}
        self.heartbeat_reports: dict[tuple[str, str], types.HeartbeatReport] = {}
        self.topology: IncidentTopology | None = None
        self._prepared_worker_backend: dict[tuple[str, str], str] = {}
        self.catalogues: dict[tuple[str, str], ResourceObligationRegistry] = {}
        self._issued_cleanup_commands: dict[str, wire.BackendCommand] = {}
        self.registered: types.ProcessIdentity | None = None
        self.context: wire.RegisteredContext | None = None
        self.errors: dict[str, types.ErrorReport] = {}
        self.pending_error_deadlines: dict[str, int] = {}
        self.pending_backend_exits: dict[
            tuple[str, str], tuple[int, int, types.Failure]
        ] = {}
        self.isolated_backend_exits: set[tuple[str, str]] = set()
        self.warnings: dict[str, types.Warning] = {}
        self.cleanup: dict[tuple[str, str], types.CleanupReport] = {}
        self.recoveries: dict[str, types.RecoveryState] = {}
        self.operations: dict[str, types.OperationState] = {}
        self.status_revision = 0
        if max_retained_entries <= 0:
            raise ValueError("retention bound must be positive")
        self.max_retained_entries = max_retained_entries
        self._status_task: asyncio.Task[None] | None = None
        self._pending_status: wire.SupervisorStatusReport | None = None
        self._shutdown_deadline_ns: int | None = None
        self._cleanup_deadline_ns: int | None = None
        self._shutdown_request: bytes | None = None
        self._interruption: wire.InterruptionReport | None = None
        self._safety_task: asyncio.Task[None] | None = None
        self._shutdown_task: asyncio.Task[None] | None = None
        self._monitor_task: asyncio.Task[None] | None = None
        self._heartbeater_task: asyncio.Task[None] | None = None
        self._cleanup_events: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()
        self.shutdown_complete = asyncio.Event()
        self._controller_ack = asyncio.Event()
        if not gate_controller_ack:
            self._controller_ack.set()

    def acknowledge_controller_registration(self) -> None:
        """Permit controller endpoint admission after launcher retains its exact handle."""
        self._controller_ack.set()

    async def _authenticate(
        self, context: grpc.aio.ServicerContext, source: types.ProcessIdentity
    ) -> None:
        key = source.role, source.generation
        token = self.credentials.get(key)
        if token is None:
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED, "unregistered process generation"
            )
            raise AssertionError("unreachable")
        try:
            require_authenticated_peer(
                context.peer(),
                context.invocation_metadata(),
                expected_role=source.role,
                expected_generation=source.generation,
                expected_token=token,
            )
        except AuthenticationError as exc:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, str(exc))

    async def _reject(
        self, context: grpc.aio.ServicerContext, error: Exception
    ) -> None:
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))

    def _same_work(self, work: types.WorkContext) -> bool:
        if self.context is None:
            return not work.WhichOneof("work")
        expected = self.context.work
        if not expected.WhichOneof("work"):
            return not work.WhichOneof("work")
        # Session registration covers its trial reports, not just the empty trial.
        if expected.WhichOneof("work") == "session":
            actual = (
                work.session
                if work.WhichOneof("work") == "session"
                else work.trial.session
            )
            return actual == expected.session
        return work == expected

    def _required_backends(self) -> dict[str, str]:
        if self.context is None:
            return {}
        return {
            x.backend_name: x.backend_generation
            for x in self.context.required_participants
        }

    def _worker_backend_ancestry(
        self, participants: set[tuple[str, str]]
    ) -> dict[tuple[str, str], str]:
        """Resolve only exact active descendants of required backend generations."""
        top_roles = {"controller", "supervisor", "acquisition", "vr", "tracking", "gui"}
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

    def _catalogue_owners(self, backend: tuple[str, str]) -> frozenset[tuple[str, str]]:
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

    def _source_registered(
        self, source: types.ProcessIdentity, *, allow_worker: bool = False
    ) -> bool:
        if source == self.controller:
            return True
        for state in self.registry.states():
            if (
                state.plan.child == source
                and state.phase == wire.LAUNCH_PHASE_OPERATIONAL
            ):
                return True
        return False

    async def PlanLaunch(
        self, request: wire.PlanLaunchRequest, context: grpc.aio.ServicerContext
    ) -> wire.LaunchReceipt:
        await self._authenticate(context, request.owner)
        if (
            not self._source_registered(request.owner)
            and request.owner != self.identity
        ):
            await context.abort(
                grpc.StatusCode.FAILED_PRECONDITION, "owner is not registered"
            )
        if request.HasField("work") and not self._same_work(request.work):
            await context.abort(
                grpc.StatusCode.FAILED_PRECONDITION, "work context differs"
            )
        child_key = request.child.role, request.child.generation
        child_tokens = [
            value
            for key, value in context.invocation_metadata()
            if key == "x-cephvr-child-token"
        ]
        known = self.credentials.get(child_key)
        if len(child_tokens) > 1 or (
            known is None and (len(child_tokens) != 1 or not child_tokens[0])
        ):
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "one protected child token is required",
            )
        if known is not None and child_tokens and child_tokens[0] != known:
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "child token differs from registration",
            )
        try:
            async with self._lock:
                state = self.registry.plan(request)
                if known is None:
                    self.credentials[child_key] = child_tokens[0]
            self._changed()
            return wire.LaunchReceipt(
                admission=self._accepted(request.command_id), state=state
            )
        except (LaunchError, ValueError) as exc:
            return wire.LaunchReceipt(admission=self._rejected(request.command_id, exc))

    async def ConfirmLaunch(
        self, request: wire.ConfirmLaunchRequest, context: grpc.aio.ServicerContext
    ) -> wire.LaunchReceipt:
        try:
            planned = self.registry.refresh(request.launch_command_id)
            # The owner confirms the OS stage; a Python child confirms its own
            # bootstrap endpoint after resume. Both remain bound to the one plan.
            confirmer = request.child if request.HasField("endpoint") else request.owner
            await self._authenticate(context, confirmer)
            if request.child == self.controller and request.HasField("endpoint"):
                try:
                    await asyncio.wait_for(self._controller_ack.wait(), timeout=15)
                except TimeoutError as exc:
                    raise LaunchError(
                        "LAUNCHER_ACK_TIMEOUT",
                        "launcher did not retain controller handle",
                    ) from exc
            if confirmer == request.child and planned.phase not in (
                wire.LAUNCH_PHASE_OS_CONFIRMED,
                wire.LAUNCH_PHASE_OPERATIONAL,
            ):
                raise LaunchError(
                    "WRONG_STAGE",
                    "child endpoint confirmation requires OS confirmation",
                )
            async with self._lock:
                state = self.registry.confirm(request, self.clock)
                if (
                    state.phase == wire.LAUNCH_PHASE_OPERATIONAL
                    and planned.phase != wire.LAUNCH_PHASE_OPERATIONAL
                    and request.child.role
                    in {"controller", "acquisition", "vr", "tracking"}
                ):
                    self.last_heartbeat[
                        (request.child.role, request.child.generation)
                    ] = host_time_ns()
            self._changed()
            return wire.LaunchReceipt(
                admission=self._accepted(request.command_id), state=state
            )
        except (LaunchError, ValueError) as exc:
            return wire.LaunchReceipt(admission=self._rejected(request.command_id, exc))

    async def GetLaunchState(
        self, request: wire.LaunchQuery, context: grpc.aio.ServicerContext
    ) -> wire.LaunchState:
        await self._authenticate(context, request.requester)
        try:
            state = self.registry.refresh(request.launch_command_id)
            if request.requester not in (
                state.plan.owner,
                self.controller,
                self.identity,
            ):
                await context.abort(
                    grpc.StatusCode.PERMISSION_DENIED, "not launch owner"
                )
            return state
        except LaunchError as exc:
            await self._reject(context, exc)
            raise AssertionError("unreachable") from exc

    async def RegisterContext(
        self, request: wire.RegisterContextRequest, context: grpc.aio.ServicerContext
    ) -> wire.RegistrationReceipt:
        await self._authenticate(context, request.context.controller)
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
            if self.context and not self._same_work(request.context.work):
                if self._cleanup_blockers():
                    raise ValueError("previous work still has cleanup obligations")
            for participant in request.context.required_participants:
                require_uuid4(participant.backend_generation)
                if participant.backend_name not in {"acquisition", "vr", "tracking"}:
                    raise ValueError("unsupported required backend")
            if not any(
                x.backend_name == "vr" for x in request.context.required_participants
            ):
                raise ValueError("required VR coordinator is absent")
            participant_keys = {
                (x.backend_name, x.backend_generation)
                for x in request.context.required_participants
            }
            if len(participant_keys) != len(request.context.required_participants):
                raise ValueError("duplicate required participant")
            if self.context and self._same_work(request.context.work):
                prior_participants = {
                    (item.backend_name, item.backend_generation)
                    for item in self.context.required_participants
                }
                if participant_keys != prior_participants:
                    raise ValueError(
                        "registered participant set cannot change within work"
                    )
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
            validate_cleanup_fence_update(
                self.context,
                request.context,
                max_fences=self.max_retained_entries,
                max_bytes=self.max_message_bytes // 4,
            )
            async with self._lock:
                active_states = self.registry.states()
                for participant in request.context.required_participants:
                    matching = [
                        state
                        for state in active_states
                        if state.plan.child.role == participant.backend_name
                        and state.plan.child.generation
                        == participant.backend_generation
                        and state.phase == wire.LAUNCH_PHASE_OPERATIONAL
                        and state.HasField("host_clock")
                    ]
                    if len(matching) != 1:
                        raise ValueError(
                            f"backend {participant.backend_name} generation is not operational"
                        )
                if (
                    self.context
                    and not self._same_work(request.context.work)
                    and self._cleanup_blockers()
                ):
                    raise ValueError("previous work still has cleanup obligations")
                validate_cleanup_fence_update(
                    self.context,
                    request.context,
                    max_fences=self.max_retained_entries,
                    max_bytes=self.max_message_bytes // 4,
                )
                cleanup_keys: set[tuple[str, str, str]] = set()
                allowed_resource_owners = frozenset().union(
                    *(
                        self._catalogue_owners(participant)
                        for participant in participant_keys
                    )
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
                    dict(self._prepared_worker_backend)
                    if self.topology is not None
                    and self._same_work(request.context.work)
                    else self._worker_backend_ancestry(participant_keys)
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
                    raise ValueError(
                        "resource obligations require completed prepared topology"
                    )
                if (
                    self.topology is not None
                    and self._same_work(request.context.work)
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
                        catalogue = self.catalogues.get(catalogue_key)
                        if catalogue is None:
                            raise ResourceCatalogueError(
                                "preliminary cleanup catalogue is absent"
                            )
                        catalogue.allowed_owners = self._catalogue_owners(catalogue_key)
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
                admission = self.commands.admit(
                    request.command_id,
                    request.SerializeToString(deterministic=True),
                    host_time_ns(),
                    work_key=self._work_key(request.context.work),
                )
                if admission.replayed:
                    if admission.record.result is None:
                        raise ValueError("matching registration is still pending")
                    return wire.RegistrationReceipt.FromString(admission.record.result)
                if self.context and not self._same_work(request.context.work):
                    self.commands.finalize_work(
                        self._work_key(self.context.work), host_time_ns()
                    )
                    self.commands.prune(host_time_ns())
                    self.cleanup.clear()
                    self.catalogues.clear()
                    self.heartbeat_reports.clear()
                    self.pending_error_deadlines.clear()
                    self._issued_cleanup_commands.clear()
                if not self.catalogues:
                    self.catalogues = {
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
                self.context = wire.RegisteredContext.FromString(
                    request.context.SerializeToString()
                )
                self.topology = topology
                self._prepared_worker_backend = (
                    dict(worker_backend) if topology is not None else {}
                )
                for catalogue, items in final_catalogues:
                    catalogue.seal_final(items)
                for error_id in list(self.pending_error_deadlines):
                    if self._verified_continuation(self.errors[error_id]):
                        del self.pending_error_deadlines[error_id]
                receipt = wire.RegistrationReceipt(
                    admission=self._accepted(request.command_id),
                    registered=self.context,
                )
                self.commands.complete(
                    request.command_id,
                    receipt.SerializeToString(deterministic=True),
                    host_time_ns(),
                )
            self._changed()
            return receipt
        except (
            ValueError,
            IncidentEvidenceError,
            ResourceCatalogueError,
            CommandConflict,
            CommandCapacityError,
        ) as exc:
            return wire.RegistrationReceipt(
                admission=self._rejected(request.command_id, exc),
                failure=self._failure(exc),
            )

    async def ReportHeartbeat(
        self, request: types.HeartbeatReport, context: grpc.aio.ServicerContext
    ) -> types.ReportReceipt:
        ingress_ns = host_time_ns()
        await self._authenticate(context, request.source)
        lifecycle_kind = request.WhichOneof("lifecycle")
        if (
            not lifecycle_kind
            or request.sent_monotonic_ns <= 0
            or (
                lifecycle_kind == "session_phase"
                and request.session_phase == types.SESSION_PHASE_UNSPECIFIED
            )
            or (
                lifecycle_kind == "trial_phase"
                and request.trial_phase == types.TRIAL_PHASE_UNSPECIFIED
            )
        ):
            return self._report_rejected(
                "INVALID_HEARTBEAT", "lifecycle and sender time are required"
            )
        async with self._lock:
            if not self._source_registered(request.source) or not self._same_work(
                request.work
            ):
                return self._report_rejected(
                    "WRONG_CONTEXT", "source generation or work is not registered"
                )
            source_key = (request.source.role, request.source.generation)
            catalogue = self.catalogues.get(source_key)
            if catalogue is None and (
                request.HasField("cleanup_resources_revision")
                or request.cleanup_resources
            ):
                return self._report_rejected(
                    "UNKNOWN_CATALOGUE", "cleanup catalogue source is not registered"
                )
            if catalogue is not None:
                try:
                    catalogue.allowed_owners = self._catalogue_owners(source_key)
                    catalogue.accept_heartbeat(request)
                except (ResourceCatalogueError, LaunchError) as exc:
                    return self._report_rejected("INVALID_CATALOGUE", str(exc))
            self.last_heartbeat[source_key] = ingress_ns
            self.heartbeat_reports[source_key] = types.HeartbeatReport.FromString(
                request.SerializeToString()
            )
            for error_id in list(self.pending_error_deadlines):
                if self._verified_continuation(self.errors[error_id]):
                    del self.pending_error_deadlines[error_id]
        self._changed()
        return self._report_accepted()

    async def ReportError(
        self, request: types.ErrorReport, context: grpc.aio.ServicerContext
    ) -> types.ReportReceipt:
        await self._authenticate(context, request.source)
        if not self._source_registered(
            request.source, allow_worker=True
        ) or not self._same_work(request.work):
            return self._report_rejected(
                "WRONG_CONTEXT", "source generation or work is not registered"
            )
        try:
            require_uuid4(request.error_id)
        except ValueError as exc:
            return self._report_rejected("INVALID_ERROR", str(exc))
        if not request.failure.code or not request.occurred_monotonic_ns:
            return self._report_rejected(
                "INVALID_ERROR", "failure and occurrence time are required"
            )
        async with self._lock:
            prior = self.errors.get(request.error_id)
            if prior and prior != request:
                return self._report_rejected(
                    "ERROR_ID_REUSED", "error ID has changed payload"
                )
            if not prior and len(self.errors) >= self.max_retained_entries:
                self._begin_safety(
                    types.Failure(
                        code="ERROR_CAPACITY",
                        message="required error accounting exhausted",
                    )
                )
                return self._report_rejected(
                    "ERROR_CAPACITY", "required error accounting exhausted"
                )
            self.errors[request.error_id] = types.ErrorReport.FromString(
                request.SerializeToString()
            )
        self._changed()
        if request.failure.code in {"CONTROLLER_LOST", "SUPERVISOR_LOST"}:
            self._begin_safety(request.failure, request.error_id)
        elif self.context is None:
            # No prepared topology can prove a pre-session failure isolated.
            self._begin_safety(request.failure, request.error_id)
        else:
            deadline = min(host_time_ns(), request.occurred_monotonic_ns) + max(
                0, self.context.policies.recovery_ns
            )
            classification = self._classification(request, deadline)
            if classification == "blocking":
                self._begin_safety(request.failure, request.error_id)
            elif classification == "pending":
                self.pending_error_deadlines.setdefault(request.error_id, deadline)
        return self._report_accepted()

    def _verified_continuation(self, error: types.ErrorReport) -> bool:
        deadline = self.pending_error_deadlines.get(error.error_id)
        if deadline is None:
            return False
        return self._classification(error, deadline) == "continuable"

    def _classification(self, error: types.ErrorReport, deadline_ns: int) -> str:
        now = host_time_ns()
        if self.topology is None:
            return "pending" if now < deadline_ns else "blocking"
        try:
            topology = (
                IncidentTopology.from_registered(
                    self.context,
                    registered_workers=frozenset(self._prepared_worker_backend),
                    worker_backend=self._prepared_worker_backend,
                )
                if self.context is not None
                else self.topology
            )
        except (IncidentEvidenceError, LaunchError):
            return "blocking"
        controller_last = self.last_heartbeat.get(
            ("controller", self.controller.generation)
        )
        proof = IsolationProof(
            continuing_heartbeats=self.heartbeat_reports,
            controller_authority_valid=(
                controller_last is not None
                and now - controller_last < self.silence_timeout_ns
            ),
            supervisor_authority_valid=True,
            bounded_accounting=len(self.errors) <= self.max_retained_entries,
        )
        return classify_incident(
            error,
            topology,
            proof,
            now_ns=now,
            original_deadline_ns=deadline_ns,
            max_evidence_age_ns=self.silence_timeout_ns,
        ).status

    def _backend_exit_isolated(
        self, backend: tuple[str, str], observed_ns: int
    ) -> bool:
        if self.topology is None or self.context is None:
            return False
        owned = {
            item.resource_id
            for item in self.context.prepared_functions
            if (item.owner.role, item.owner.generation) == backend
        }
        if not owned:
            return False
        for error in self.errors.values():
            if (
                error.occurred_monotonic_ns >= observed_ns
                and error.HasField("isolation")
                and owned <= set(error.isolation.affected_resource_ids)
            ):
                deadline = min(host_time_ns(), error.occurred_monotonic_ns) + max(
                    0, self.context.policies.recovery_ns
                )
                if self._classification(error, deadline) == "continuable":
                    return True
        return False

    def _observe_backend_exit(self, state: wire.LaunchState, now_ns: int) -> None:
        if self._shutdown_request or self._interruption:
            return
        backend = (state.plan.child.role, state.plan.child.generation)
        if backend in self.isolated_backend_exits:
            return
        if backend not in {
            (role, generation) for role, generation in self._required_backends().items()
        }:
            self._begin_safety(
                types.Failure(code="CHILD_EXITED", message=state.failure.message)
            )
            return
        if backend not in self.pending_backend_exits:
            deadline = (
                now_ns + max(0, self.context.policies.recovery_ns)
                if self.context
                else now_ns
            )
            self.pending_backend_exits[backend] = (
                now_ns,
                deadline,
                types.Failure(code="BACKEND_EXITED", message=state.failure.message),
            )
            self._changed()

    async def ReportLifecycle(
        self, request: types.LifecycleReport, context: grpc.aio.ServicerContext
    ) -> types.ReportReceipt:
        if request.WhichOneof("report") != "cleanup":
            return self._report_rejected(
                "INVALID_LIFECYCLE", "supervisor accepts top-level Cleanup only"
            )
        report = request.cleanup
        await self._authenticate(context, report.source)
        if (
            report.source.role not in self._required_backends()
            or not self._source_registered(report.source)
            or not self._same_work(report.work)
        ):
            return self._report_rejected(
                "WRONG_CONTEXT", "cleanup source/work is not registered"
            )
        if report.verified_monotonic_ns <= 0 or not report.operation.command_id:
            return self._report_rejected(
                "INVALID_CLEANUP", "verification time and operation required"
            )
        try:
            require_uuid4(report.operation.command_id)
        except ValueError as exc:
            return self._report_rejected("INVALID_CLEANUP", str(exc))
        key = report.source.role, report.source.generation
        async with self._lock:
            if not self._same_work(report.work) or not self._cleanup_verified(report):
                return self._report_rejected(
                    "INCOMPLETE_CLEANUP",
                    "registered output/resource obligations or cleanup fence are unverified",
                )
            previous = self.cleanup.get(key)
            if (
                previous
                and previous.operation == report.operation
                and previous != report
            ):
                return self._report_rejected(
                    "CHANGED_CLEANUP", "same operation changed evidence"
                )
            self.cleanup[key] = types.CleanupReport.FromString(
                report.SerializeToString()
            )
            event = self._cleanup_events.get(report.operation.command_id)
            if event is not None:
                event.set()
        self._changed()
        return self._report_accepted()

    def _cleanup_verified(self, report: types.CleanupReport) -> bool:
        if not self.context or not report.trial_activity_stopped:
            return False
        catalogue = self.catalogues.get((report.source.role, report.source.generation))
        if catalogue is None:
            return False
        fenced = cleanup_command_fenced(
            report,
            self.context,
            supervisor_command=self._issued_cleanup_commands.get(
                report.operation.command_id
            ),
        )
        try:
            catalogue.verify_cleanup(report, cleanup_command_fenced=fenced)
        except ResourceCatalogueError:
            return False
        expected = {
            output.output_key
            for output in self.context.outputs
            if output.backend.backend_name == report.source.role
            and output.backend.backend_generation == report.source.generation
        }
        observed = {output.output_key: output for output in report.outputs}
        if expected != observed.keys() or len(observed) != len(report.outputs):
            return False
        if any(
            observed[key].closure
            not in (
                types.OUTPUT_CLOSURE_CLOSED,
                types.OUTPUT_CLOSURE_FAILED,
            )
            for key in expected
        ):
            return False
        return True

    async def ReportPreviewConsumerState(
        self, request: wire.PreviewConsumerReport, context: grpc.aio.ServicerContext
    ) -> types.ReportReceipt:
        await self._authenticate(context, request.consumer)
        if request.result == wire.PREVIEW_CONSUMER_RESULT_ATTACHED:
            return self._report_rejected(
                "INVALID_PREVIEW", "ATTACHED belongs to controller"
            )
        if (
            not self._source_registered(request.consumer, allow_worker=True)
            or request.controller_generation != self.controller.generation
        ):
            return self._report_rejected(
                "WRONG_CONTEXT", "preview consumer is not registered"
            )
        return self._report_accepted()

    async def GetRecoveryState(
        self, request: wire.RecoveryQuery, context: grpc.aio.ServicerContext
    ) -> wire.RecoverySnapshot:
        await self._authenticate(context, self.controller)
        if request.expected_supervisor != self.identity or not self._same_work(
            request.work
        ):
            await context.abort(
                grpc.StatusCode.FAILED_PRECONDITION, "recovery query context mismatch"
            )
        prior_receipt = None
        if request.HasField("prior_controller_generation"):
            try:
                prior_generation = require_uuid4(request.prior_controller_generation)
                if (
                    prior_generation == self.controller.generation
                    or self.context is not None
                    or request.work.WhichOneof("work")
                ):
                    raise ValueError("prior exit proof is available only at startup")
                prior_receipt = await run_pipe_io_daemon(
                    lambda: RecoveryStore(default_runtime_root()).read_exit_receipt(
                        prior_generation
                    ),
                    timeout_s=min(self.emergency_timeout_ns / 1e9, 5.0),
                )
            except (ValueError, TimeoutError, RuntimeError, OSError) as exc:
                await context.abort(
                    grpc.StatusCode.FAILED_PRECONDITION,
                    f"prior exit proof is unavailable or unsafe: {exc}",
                )
        response = wire.RecoverySnapshot(
            supervisor=self.identity,
            captured_monotonic_ns=host_time_ns(),
            recoveries=list(self.recoveries.values()),
            operations=list(self.operations.values()),
            errors=list(self.errors.values()),
            status_revision=self.status_revision,
            warnings=list(self.warnings.values()),
            cleanup_blockers=self._cleanup_blockers(),
        )
        if prior_receipt is not None:
            response.prior_application_exit.CopyFrom(
                wire.PriorApplicationExitReceipt(
                    controller_generation=prior_receipt.controller_generation,
                    supervisor_generation=prior_receipt.supervisor_generation,
                    observed_monotonic_ns=prior_receipt.observed_monotonic_ns,
                    all_owned_processes_absent=prior_receipt.all_owned_processes_absent,
                    format_version=prior_receipt.format_version,
                )
            )
        return response

    async def ExecuteRecoveryAction(
        self, request: wire.RecoveryActionRequest, context: grpc.aio.ServicerContext
    ) -> types.CommandAdmission:
        await self._authenticate(context, self.controller)
        if request.supervisor != self.identity or not self._same_work(request.work):
            return self._rejected(
                request.command_id,
                LaunchError("WRONG_CONTEXT", "recovery target/context differs"),
            )
        if request.action != wire.RECOVERY_ACTION_RETRY_GRACEFUL_CLEANUP:
            return self._rejected(
                request.command_id,
                LaunchError(
                    "INVALID_ACTION", "only retry graceful cleanup is available"
                ),
            )
        if self.context is None or (
            request.target.role,
            request.target.generation,
        ) not in {
            (x.backend_name, x.backend_generation)
            for x in self.context.required_participants
        }:
            return self._rejected(
                request.command_id,
                LaunchError("WRONG_TARGET", "target generation is not registered"),
            )
        try:
            require_uuid4(request.operator.client_id)
            require_uuid4(request.operator.control_generation)
            require_uuid4(request.operator.command_id)
            if request.operator.command_id != request.command_id:
                raise ValueError("controller-verified operator command ID mismatch")
            if (
                len(self.operations) >= self.max_retained_entries
                and request.command_id not in self.operations
            ):
                self._begin_safety(
                    types.Failure(
                        code="OPERATION_CAPACITY",
                        message="required operation accounting exhausted",
                    )
                )
                raise CommandCapacityError("operation accounting exhausted")
            if (
                len(self.recoveries) >= self.max_retained_entries
                and request.command_id not in self.recoveries
            ):
                self._begin_safety(
                    types.Failure(
                        code="RECOVERY_CAPACITY",
                        message="required recovery accounting exhausted",
                    )
                )
                raise CommandCapacityError("recovery accounting exhausted")
            admitted = self.commands.admit(
                request.command_id,
                request.SerializeToString(deterministic=True),
                host_time_ns(),
                work_key=self._work_key(request.work),
            )
            if admitted.replayed:
                return (
                    types.CommandAdmission.FromString(admitted.record.result)
                    if admitted.record.result
                    else self._accepted(request.command_id)
                )
            target = types.BackendContext(
                backend_name=request.target.role,
                backend_generation=request.target.generation,
            )
            command = wire.BackendCommand(
                command_id=request.command_id,
                issuer=self.identity,
                target=target,
                work=request.work,
            )
            self.operations[request.command_id] = types.OperationState(
                context=types.OperationContext(command_id=request.command_id),
                command="Retry graceful cleanup",
                work=request.work,
                progress="accepted",
            )
            start_ns = host_time_ns()
            budget_ns = max(0, self.context.policies.recovery_ns)
            recovery = types.RecoveryState(
                attempt_id=request.command_id,
                affected=request.target,
                work=request.work,
                trigger=types.Failure(
                    code="RETRY_REQUESTED", message="operator retry graceful cleanup"
                ),
                action="retry_graceful_cleanup",
                start_monotonic_ns=start_ns,
                deadline_monotonic_ns=start_ns + budget_ns,
                progress="cleanup admission pending",
            )
            self.recoveries[request.command_id] = recovery
            self._issued_cleanup_commands[request.command_id] = command
            self._cleanup_events[request.command_id] = asyncio.Event()
            asyncio.create_task(self._run_recovery(target, command))
            receipt = self._accepted(request.command_id)
            self.commands.complete(
                request.command_id,
                receipt.SerializeToString(deterministic=True),
                host_time_ns(),
            )
            self._changed()
            return receipt
        except (ValueError, CommandConflict, CommandCapacityError) as exc:
            return self._rejected(request.command_id, exc)

    async def _run_recovery(
        self, target: types.BackendContext, command: wire.BackendCommand
    ) -> None:
        operation = self.operations[command.command_id]
        recovery = self.recoveries[command.command_id]
        try:
            remaining_s = max(
                0.0, (recovery.deadline_monotonic_ns - host_time_ns()) / 1e9
            )
            await asyncio.wait_for(
                self.outbound.cleanup_backend(target, command), timeout=remaining_s
            )
            operation.progress = "cleanup admitted; awaiting verified Cleanup evidence"
            recovery.progress = operation.progress
            remaining_s = max(
                0.0, (recovery.deadline_monotonic_ns - host_time_ns()) / 1e9
            )
            await asyncio.wait_for(
                self._cleanup_events[command.command_id].wait(), timeout=remaining_s
            )
            operation.complete = True
            operation.succeeded = True
            operation.progress = "verified Cleanup evidence received"
            recovery.progress = operation.progress
            recovery.completion_monotonic_ns = host_time_ns()
            recovery.outcome = types.RECOVERY_OUTCOME_COMPLETED
            recovery.evidence = "matching top-level Cleanup report verified"
        except Exception as exc:
            operation.complete = True
            operation.succeeded = False
            operation.progress = "cleanup unconfirmed within retained deadline"
            code = (
                "CLEANUP_TIMEOUT"
                if isinstance(exc, TimeoutError)
                else "CLEANUP_ADMISSION_FAILED"
            )
            operation.failure.CopyFrom(types.Failure(code=code, message=str(exc)))
            recovery.progress = operation.progress
            recovery.completion_monotonic_ns = host_time_ns()
            recovery.outcome = types.RECOVERY_OUTCOME_FAILED
            recovery.failure.CopyFrom(operation.failure)
        finally:
            self._cleanup_events.pop(command.command_id, None)
        self._changed()

    async def RequestApplicationShutdown(
        self,
        request: wire.ApplicationShutdownRequest,
        context: grpc.aio.ServicerContext,
    ) -> types.CommandAdmission:
        await self._authenticate(context, self.controller)
        try:
            require_uuid4(request.command_id)
            if (
                request.controller != self.controller
                or request.supervisor != self.identity
            ):
                raise ValueError("authority generation mismatch")
            if request.HasField("work") and not self._same_work(request.work):
                raise ValueError("shutdown work context differs")
            if (
                not request.operator.command_id
                or request.operator.command_id
                != request.controller_operation.command_id
            ):
                raise ValueError("original operator command/operation must match")
            if request.issued_monotonic_ns <= 0:
                raise ValueError("shutdown issue time is required")
            payload = request.SerializeToString(deterministic=True)
            async with self._lock:
                if self._shutdown_request and self._shutdown_request != payload:
                    raise ValueError("a different shutdown intent is already retained")
                if (
                    len(self.operations) >= self.max_retained_entries
                    and request.command_id not in self.operations
                ):
                    self._begin_safety(
                        types.Failure(
                            code="OPERATION_CAPACITY",
                            message="required operation accounting exhausted",
                        )
                    )
                    raise ValueError("operation accounting exhausted")
                self._shutdown_request = payload
                issued = min(host_time_ns(), request.issued_monotonic_ns)
                deadline = issued + self.application_backstop_ns
                self._shutdown_deadline_ns = min(
                    deadline, self._shutdown_deadline_ns or deadline
                )
                if self.context:
                    cleanup_limit = (
                        issued
                        + max(
                            self.context.policies.setup_cancel.initial_ns,
                            self.context.policies.trial_finished.initial_ns,
                        )
                        + self.context.policies.recovery_ns
                    )
                    self._cleanup_deadline_ns = min(
                        cleanup_limit,
                        self._cleanup_deadline_ns or cleanup_limit,
                    )
                self.operations[request.command_id] = types.OperationState(
                    context=types.OperationContext(command_id=request.command_id),
                    command="ShutdownApplication",
                    work=request.work,
                    progress="intent retained",
                )
            asyncio.create_task(
                self.outbound.notify_launcher_shutdown(
                    self._shutdown_deadline_ns, "explicit_shutdown"
                )
            )
            if self._shutdown_task is None:
                self._shutdown_task = asyncio.create_task(self._shutdown_owned())
            self._changed()
            return self._accepted(request.command_id)
        except ValueError as exc:
            return self._rejected(request.command_id, exc)

    def _begin_safety(
        self, reason: types.Failure, triggering_error_id: str | None = None
    ) -> None:
        if self._interruption is not None:
            return
        now = host_time_ns()
        report = wire.InterruptionReport(
            interruption_id=str(uuid4()),
            supervisor=self.identity,
            controller_generation=self.controller.generation,
            issued_monotonic_ns=now,
            reason=reason,
        )
        if self.context:
            report.work.CopyFrom(self.context.work)
        if triggering_error_id:
            report.triggering_error_id = triggering_error_id
        self._interruption = report
        deadline = now + self.application_backstop_ns
        self._shutdown_deadline_ns = min(
            deadline, self._shutdown_deadline_ns or deadline
        )
        if self.context:
            cleanup_limit = (
                now
                + max(
                    self.context.policies.setup_cancel.initial_ns,
                    self.context.policies.trial_finished.initial_ns,
                )
                + self.context.policies.recovery_ns
            )
            self._cleanup_deadline_ns = min(
                cleanup_limit,
                self._cleanup_deadline_ns or cleanup_limit,
            )
        self._safety_task = asyncio.create_task(self._deliver_safety(report))
        self._changed()

    async def _deliver_safety(self, report: wire.InterruptionReport) -> None:
        # Independent tasks: controller delivery cannot gate direct participant safety.
        tasks: list[asyncio.Task[Any]] = [
            asyncio.create_task(self.outbound.report_interruption(report)),
            asyncio.create_task(
                self.outbound.notify_launcher_shutdown(
                    self._shutdown_deadline_ns or 0, report.reason.code
                )
            ),
            asyncio.create_task(
                write_emergency_report(
                    self.software_root,
                    cause=report.reason.code,
                    supervisor=self.identity,
                    controller=self.controller,
                    work=report.work if report.HasField("work") else None,
                    errors=list(self.errors.values()),
                    # The supervisor has no independent SpikeGLX stop channel;
                    # the frozen Setup fact distinguishes an absent run from an
                    # expected run whose stop cannot be verified here.
                    spikeglx_stop_unconfirmed=bool(
                        self.context and self.context.paired_spikeglx
                    ),
                    timeout_ns=self.emergency_timeout_ns,
                )
            ),
        ]
        registered = self.context
        if registered:
            for participant in registered.required_participants:
                command = wire.BackendCommand(
                    command_id=str(uuid4()),
                    issuer=self.identity,
                    target=participant,
                    work=registered.work,
                )
                interrupt = wire.InterruptSessionRequest(
                    command=command,
                    issued_monotonic_ns=report.issued_monotonic_ns,
                    reason=report.reason,
                )
                tasks.append(
                    asyncio.create_task(
                        self.outbound.interrupt_backend(participant, interrupt)
                    )
                )
        remaining_s = max(
            0.0,
            min(
                5_000_000_000,
                (self._shutdown_deadline_ns or host_time_ns()) - host_time_ns(),
            )
            / 1e9,
        )
        done, pending = await asyncio.wait(tasks, timeout=remaining_s)
        for task in pending:
            task.cancel()
        for task in done:
            try:
                task.result()
            except Exception:
                pass  # Retained safety/launcher state remains authoritative.
        if self._shutdown_task is None:
            self._shutdown_task = asyncio.create_task(self._shutdown_owned())
        await self._shutdown_task

    async def _shutdown_owned(self) -> None:
        """Preserve the original outer deadline; exit groups have fixed inner bounds."""
        if self.context:
            cleanup_deadline = min(
                self._cleanup_deadline_ns or host_time_ns(),
                self._shutdown_deadline_ns or host_time_ns(),
            )
            while self._cleanup_blockers() and host_time_ns() < cleanup_deadline:
                await asyncio.sleep(
                    min(0.05, (cleanup_deadline - host_time_ns()) / 1e9)
                )
            requests = []
            for target in self.context.required_participants:
                command = wire.BackendCommand(
                    command_id=str(uuid4()),
                    issuer=self.identity,
                    target=target,
                    work=self.context.work,
                )
                requests.append(self.outbound.shutdown_backend(target, command))
            if requests:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*requests, return_exceptions=True), timeout=5
                    )
                except TimeoutError:
                    pass
        for roles in ({"acquisition", "vr", "tracking"}, {"controller", "gui"}):
            candidates = [
                state
                for state in self.registry.states()
                if state.plan.child.role in roles
            ]

            def remaining_members(
                states: tuple[wire.LaunchState, ...] = tuple(candidates),
            ) -> list[tuple[int, int, str]]:
                found: dict[tuple[int, int], tuple[int, int, str]] = {}
                for state in states:
                    for member in self.native.inspect_launch_job(
                        state.containment_job_name
                    ):
                        found[member[:2]] = member
                return list(found.values())

            grace_until = min(
                host_time_ns() + self.graceful_exit_ns,
                self._shutdown_deadline_ns or (host_time_ns() + self.graceful_exit_ns),
            )
            while host_time_ns() < grace_until and remaining_members():
                await asyncio.sleep(0.05)
            for pid, created, _ in remaining_members():
                if self.native.process_running(pid, created):
                    self.native.terminate_exact(pid, created)
            terminate_until = min(
                host_time_ns() + self.terminate_exit_ns,
                self._shutdown_deadline_ns or (host_time_ns() + self.terminate_exit_ns),
            )
            while host_time_ns() < terminate_until and remaining_members():
                await asyncio.sleep(0.05)
        remaining = [
            member
            for state in self.registry.states()
            if state.plan.child.role != "supervisor"
            for member in self.native.inspect_launch_job(state.containment_job_name)
        ]
        if self._shutdown_request:
            request = wire.ApplicationShutdownRequest.FromString(self._shutdown_request)
            operation = self.operations.get(request.command_id)
            if operation is not None:
                blockers = self._cleanup_blockers()
                operation.complete = True
                operation.succeeded = not remaining and not blockers
                operation.progress = (
                    "verified process absence and cleanup"
                    if operation.succeeded
                    else "process absence or cleanup remains unverified"
                )
                if not operation.succeeded:
                    operation.failure.CopyFrom(
                        types.Failure(
                            code="SHUTDOWN_UNCONFIRMED",
                            message=operation.progress,
                        )
                    )
                self._changed()
        if not remaining:
            self.shutdown_complete.set()

    def _cleanup_blockers(self) -> list[types.CleanupBlocker]:
        if not self.context:
            return []
        blockers = []
        for participant in self.context.required_participants:
            if (
                participant.backend_name,
                participant.backend_generation,
            ) not in self.cleanup:
                blockers.append(
                    types.CleanupBlocker(
                        responsible=types.ProcessIdentity(
                            role=participant.backend_name,
                            generation=participant.backend_generation,
                        ),
                        work=self.context.work,
                        resource="backend_cleanup",
                        reason=types.Failure(
                            code="MISSING_CLEANUP",
                            message="verified Cleanup report absent",
                        ),
                        recovery_action="retry_graceful_cleanup",
                    )
                )
        return blockers

    @staticmethod
    def _work_key(work: types.WorkContext) -> str:
        kind = work.WhichOneof("work")
        if kind == "session":
            return require_uuid4(work.session.session_id)
        if kind == "trial":
            return require_uuid4(work.trial.session.session_id)
        raise ValueError("session work context is required")

    def _changed(self) -> None:
        self.status_revision += 1
        self._pending_status = None
        if self._status_task is None or self._status_task.done():
            self._status_task = asyncio.create_task(self._send_status())

    def unavailable_component(self, role: str, reason: str) -> None:
        if len(self.warnings) >= self.max_retained_entries:
            self._begin_safety(
                types.Failure(
                    code="WARNING_CAPACITY",
                    message="required warning accounting exhausted",
                )
            )
            return
        warning_id = str(uuid4())
        self.warnings[warning_id] = types.Warning(
            warning_id=warning_id,
            component=role,
            message=reason,
        )
        self._changed()

    async def _send_status(self) -> None:
        while True:
            revision = self.status_revision
            report = self._pending_status
            if report is None or report.status_revision != revision:
                report = wire.SupervisorStatusReport(
                    supervisor=self.identity,
                    controller_generation=self.controller.generation,
                    status_revision=revision,
                    observed_monotonic_ns=host_time_ns(),
                    errors=list(self.errors.values()),
                    warnings=list(self.warnings.values()),
                    recoveries=list(self.recoveries.values()),
                    operations=list(self.operations.values()),
                )
                if self.context:
                    report.work.CopyFrom(self.context.work)
                try:
                    states = self.registry.states()
                    for state in states:
                        status = report.processes.add(
                            process=state.plan.child,
                            launch_owner=state.plan.owner,
                            process_running=state.HasField("pid")
                            and self.native.process_running(
                                state.pid, state.creation_time_100ns
                            ),
                            connected=state.phase == wire.LAUNCH_PHASE_OPERATIONAL,
                            health=wire.LaunchPhase.Name(state.phase),
                        )
                        key = (state.plan.child.role, state.plan.child.generation)
                        if key in self.last_heartbeat:
                            status.last_evidence_monotonic_ns = self.last_heartbeat[key]
                        if key in self.heartbeat_reports:
                            status.last_heartbeat.CopyFrom(self.heartbeat_reports[key])
                except (LaunchError, RuntimeError) as exc:
                    self._begin_safety(
                        types.Failure(
                            code="PROCESS_INSPECTION_FAILED", message=str(exc)
                        )
                    )
                    return
                if report.ByteSize() > self.max_message_bytes - 4096:
                    self._begin_safety(
                        types.Failure(
                            code="STATUS_OVERFLOW",
                            message="supervisor status exceeds RPC limit",
                        )
                    )
                    return
                self._pending_status = report
            try:
                await self.outbound.report_status(report)
            except Exception:
                # Retain newest complete view and retry on the next change/reconnect.
                return
            if self._pending_status is report:
                self._pending_status = None
            if revision == self.status_revision:
                return

    async def monitor(self, period_s: float = 0.25) -> None:
        if self._monitor_task is not None:
            raise RuntimeError("supervisor monitor already active")
        self._monitor_task = asyncio.current_task()
        try:
            while True:
                now = host_time_ns()
                for error_id, deadline in list(self.pending_error_deadlines.items()):
                    if now >= deadline:
                        error = self.errors[error_id]
                        if not self._verified_continuation(error):
                            self._begin_safety(error.failure, error_id)
                        del self.pending_error_deadlines[error_id]
                key = self.controller.role, self.controller.generation
                last = self.last_heartbeat.get(key)
                if last is not None and now >= last + self.silence_timeout_ns:
                    self._begin_safety(
                        types.Failure(
                            code="CONTROLLER_LOST",
                            message="controller heartbeat silence",
                        )
                    )
                for role, generation in self._required_backends().items():
                    last = self.last_heartbeat.get((role, generation))
                    if last is not None and now >= last + self.silence_timeout_ns:
                        self._begin_safety(
                            types.Failure(
                                code="BACKEND_HEARTBEAT_LOST",
                                message=f"{role} heartbeat silence",
                            )
                        )
                try:
                    states = self.registry.states()
                except LaunchError as exc:
                    self._begin_safety(types.Failure(code=exc.code, message=str(exc)))
                    await asyncio.sleep(period_s)
                    continue
                for state in states:
                    if (
                        state.plan.child == self.controller
                        and state.phase == wire.LAUNCH_PHASE_CLEANUP_REQUIRED
                    ):
                        if self._shutdown_request:
                            if self._shutdown_task is None:
                                self._shutdown_task = asyncio.create_task(
                                    self._shutdown_owned()
                                )
                        else:
                            self._begin_safety(
                                types.Failure(
                                    code="CONTROLLER_LOST",
                                    message="controller process exited",
                                )
                            )
                    if state.plan.child.role in {"controller", "gui"}:
                        continue
                    if state.phase != wire.LAUNCH_PHASE_CLEANUP_REQUIRED:
                        continue
                    if state.failure.code == "CHILD_EXITED":
                        self._observe_backend_exit(state, now)
                    elif state.failure.code in {"LAUNCH_TIMEOUT", "UNCONFIRMED_CHILD"}:
                        self._begin_safety(
                            types.Failure(
                                code="UNSAFE_OWNERSHIP", message=state.failure.message
                            )
                        )
                for backend, (observed_ns, deadline_ns, failure) in list(
                    self.pending_backend_exits.items()
                ):
                    if self._backend_exit_isolated(backend, observed_ns):
                        self.isolated_backend_exits.add(backend)
                        del self.pending_backend_exits[backend]
                    elif now >= deadline_ns:
                        self._begin_safety(failure)
                await asyncio.sleep(period_s)
        finally:
            self._monitor_task = None

    async def heartbeat_loop(self) -> None:
        """Supervisor → controller unary health; no status/history polling."""
        if self._heartbeater_task is not None:
            raise RuntimeError("supervisor heartbeat loop already active")
        self._heartbeater_task = asyncio.current_task()
        try:
            while True:
                report = types.HeartbeatReport(
                    source=self.identity,
                    sent_monotonic_ns=host_time_ns(),
                    session_phase=(
                        types.SESSION_PHASE_READY
                        if self.context
                        else types.SESSION_PHASE_CONFIGURATION
                    ),
                    health_summary="supervisor control and monitor loop active",
                )
                if self.context:
                    report.work.CopyFrom(self.context.work)
                try:
                    await asyncio.wait_for(
                        self.outbound.report_heartbeat(report), timeout=5
                    )
                except Exception:
                    # Controller applies its own ingress-based 15 s loss policy.
                    pass
                await asyncio.sleep(self.heartbeat_interval_ns / 1e9)
        finally:
            self._heartbeater_task = None

    @staticmethod
    def _failure(error: Exception) -> types.Failure:
        return types.Failure(
            code=getattr(error, "code", "INVALID_REQUEST"), message=str(error)
        )

    @classmethod
    def _rejected(cls, command_id: str, error: Exception) -> types.CommandAdmission:
        return types.CommandAdmission(
            result=types.COMMAND_RESULT_REJECTED,
            command_id=command_id,
            failure=cls._failure(error),
        )

    @staticmethod
    def _accepted(command_id: str) -> types.CommandAdmission:
        return types.CommandAdmission(
            result=types.COMMAND_RESULT_ACCEPTED, command_id=command_id
        )

    @staticmethod
    def _report_rejected(code: str, message: str) -> types.ReportReceipt:
        return types.ReportReceipt(
            result=types.COMMAND_RESULT_REJECTED,
            failure=types.Failure(code=code, message=message),
        )

    @staticmethod
    def _report_accepted() -> types.ReportReceipt:
        return types.ReportReceipt(result=types.COMMAND_RESULT_ACCEPTED)


async def start_supervisor_server(
    runtime: SupervisorRuntime, port: int
) -> grpc.aio.Server:
    if not 1 <= port <= 65535:
        raise ValueError("invalid supervisor port")
    server = grpc.aio.server(
        options=[
            ("grpc.max_send_message_length", runtime.max_message_bytes),
            ("grpc.max_receive_message_length", runtime.max_message_bytes),
        ]
    )
    services_pb2_grpc.add_SupervisorServiceServicer_to_server(runtime, server)  # type: ignore[no-untyped-call]
    for host in ("127.0.0.1", "[::1]"):
        if server.add_insecure_port(f"{host}:{port}") == 0:
            raise RuntimeError(f"supervisor loopback port {port} unavailable on {host}")
    await server.start()
    return server
