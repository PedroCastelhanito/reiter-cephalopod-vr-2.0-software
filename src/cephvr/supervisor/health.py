"""Heartbeat evidence, fault classification and silence monitoring (E06/E08)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, Protocol

from cephvr.acquisition.identity import FFMPEG_ROLES
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.clock import host_time_ns
from cephvr.shared.identity import require_uuid4
from cephvr.shared.incidents import (
    IncidentEvidenceError,
    IncidentTopology,
    IsolationProof,
    classify_incident,
)
from cephvr.shared.resources import ResourceCatalogueError
from cephvr.supervisor.ports import SupervisorOutbound
from cephvr.supervisor.receipts import report_accepted, report_rejected
from cephvr.supervisor.registration import RegistrationCoordinator
from cephvr.supervisor.registry import LaunchError, LaunchRegistry
from cephvr.supervisor.state import HealthState, ShutdownState, SupervisorTasks

RESERVED_AUTHORITY_CODES = frozenset({"CONTROLLER_LOST", "SUPERVISOR_LOST"})
HELPER_RECONCILE_PERIOD_NS = 1_000_000_000
HELPER_RECONCILE_BUDGET_NS = 5_000_000_000


class BeginSafety(Protocol):
    def __call__(
        self, reason: types.Failure, triggering_error_id: str | None = None
    ) -> None: ...


class HealthMonitor:
    def __init__(
        self,
        *,
        state: HealthState,
        registration: RegistrationCoordinator,
        shutdown: ShutdownState,
        registry: LaunchRegistry,
        controller: types.ProcessIdentity,
        identity: types.ProcessIdentity,
        outbound: SupervisorOutbound,
        lock: asyncio.Lock,
        silence_timeout_ns: int,
        heartbeat_interval_ns: int,
        max_retained_entries: int,
        begin_safety: BeginSafety,
        shutdown_owned: Callable[[], Coroutine[Any, Any, None]],
        changed: Callable[[], None],
        resend_status: Callable[[], None],
        reconcile_helpers: Callable[[int], Awaitable[list[str]]],
        tasks: SupervisorTasks,
        warn: Callable[[str], None],
    ) -> None:
        self.state = state
        self.registration = registration
        self.shutdown = shutdown
        self.registry = registry
        self.controller = controller
        self.identity = identity
        self.outbound = outbound
        self.lock = lock
        self.silence_timeout_ns = silence_timeout_ns
        self.heartbeat_interval_ns = heartbeat_interval_ns
        self.max_retained_entries = max_retained_entries
        self.begin_safety = begin_safety
        self.shutdown_owned = shutdown_owned
        self.changed = changed
        self.resend_status = resend_status
        self.reconcile_helpers = reconcile_helpers
        self.tasks = tasks
        self.warn = warn
        self._reconcile_task: asyncio.Task[None] | None = None
        self._next_reconcile_ns = 0

    async def report_heartbeat(
        self, request: types.HeartbeatReport, ingress_ns: int
    ) -> types.ReportReceipt:
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
            return report_rejected(
                "INVALID_HEARTBEAT", "lifecycle and sender time are required"
            )
        async with self.lock:
            if not self.registration.source_registered(
                request.source
            ) or not self.registration.same_work(request.work):
                return report_rejected(
                    "WRONG_CONTEXT", "source generation or work is not registered"
                )
            source_key = (request.source.role, request.source.generation)
            catalogue = self.registration.state.catalogues.get(source_key)
            if catalogue is None and (
                request.HasField("cleanup_resources_revision")
                or request.cleanup_resources
            ):
                return report_rejected(
                    "UNKNOWN_CATALOGUE", "cleanup catalogue source is not registered"
                )
            if catalogue is not None:
                try:
                    catalogue.allowed_owners = self.registration.catalogue_owners(
                        source_key
                    )
                    catalogue.accept_heartbeat(request)
                except (ResourceCatalogueError, LaunchError) as exc:
                    return report_rejected("INVALID_CATALOGUE", str(exc))
            self.state.last_heartbeat[source_key] = ingress_ns
            self.state.heartbeat_reports[source_key] = types.HeartbeatReport.FromString(
                request.SerializeToString()
            )
            for error_id in list(self.state.pending_error_deadlines):
                if self.verified_continuation(self.state.errors[error_id]):
                    del self.state.pending_error_deadlines[error_id]
        self.changed()
        return report_accepted()

    async def report_error(self, request: types.ErrorReport) -> types.ReportReceipt:
        if not self.registration.source_registered(
            request.source, allow_worker=True
        ) or not self.registration.same_work(request.work):
            return report_rejected(
                "WRONG_CONTEXT", "source generation or work is not registered"
            )
        try:
            require_uuid4(request.error_id)
        except ValueError as exc:
            return report_rejected("INVALID_ERROR", str(exc))
        if request.failure.code in RESERVED_AUTHORITY_CODES and (
            not self.registration.source_registered(request.source)
        ):
            return report_rejected(
                "INVALID_SOURCE",
                "authority-loss codes come only from the controller or a coordinator",
            )
        if not request.failure.code or not request.occurred_monotonic_ns:
            return report_rejected(
                "INVALID_ERROR", "failure and occurrence time are required"
            )
        async with self.lock:
            prior = self.state.errors.get(request.error_id)
            if prior and prior != request:
                return report_rejected(
                    "ERROR_ID_REUSED", "error ID has changed payload"
                )
            if not prior and len(self.state.errors) >= self.max_retained_entries:
                self.begin_safety(
                    types.Failure(
                        code="ERROR_CAPACITY",
                        message="required error accounting exhausted",
                    )
                )
                return report_rejected(
                    "ERROR_CAPACITY", "required error accounting exhausted"
                )
            self.state.errors[request.error_id] = types.ErrorReport.FromString(
                request.SerializeToString()
            )
        self.changed()
        if request.failure.code in RESERVED_AUTHORITY_CODES:
            self.begin_safety(request.failure, request.error_id)
        elif self.registration.state.context is None:
            # No prepared topology can prove a pre-session failure isolated.
            self.begin_safety(request.failure, request.error_id)
        else:
            deadline = min(host_time_ns(), request.occurred_monotonic_ns) + max(
                0, self.registration.state.context.policies.recovery_ns
            )
            classification = self.classification(request, deadline)
            if classification == "blocking":
                self.begin_safety(request.failure, request.error_id)
            elif classification == "pending":
                self.state.pending_error_deadlines.setdefault(
                    request.error_id, deadline
                )
        return report_accepted()

    def verified_continuation(self, error: types.ErrorReport) -> bool:
        deadline = self.state.pending_error_deadlines.get(error.error_id)
        if deadline is None:
            return False
        return self.classification(error, deadline) == "continuable"

    def classification(self, error: types.ErrorReport, deadline_ns: int) -> str:
        now = host_time_ns()
        if self.registration.state.topology is None:
            return "pending" if now < deadline_ns else "blocking"
        try:
            topology = (
                IncidentTopology.from_registered(
                    self.registration.state.context,
                    registered_workers=frozenset(
                        self.registration.state.prepared_worker_backend
                    ),
                    worker_backend=self.registration.state.prepared_worker_backend,
                )
                if self.registration.state.context is not None
                else self.registration.state.topology
            )
        except (IncidentEvidenceError, LaunchError):
            return "blocking"
        controller_last = self.state.last_heartbeat.get(
            ("controller", self.controller.generation)
        )
        proof = IsolationProof(
            continuing_heartbeats=self.state.heartbeat_reports,
            controller_authority_valid=(
                controller_last is not None
                and now - controller_last < self.silence_timeout_ns
            ),
            supervisor_authority_valid=True,
            bounded_accounting=len(self.state.errors) <= self.max_retained_entries,
        )
        return classify_incident(
            error,
            topology,
            proof,
            now_ns=now,
            original_deadline_ns=deadline_ns,
            max_evidence_age_ns=self.silence_timeout_ns,
        ).status

    def backend_exit_isolated(self, backend: tuple[str, str], observed_ns: int) -> bool:
        if (
            self.registration.state.topology is None
            or self.registration.state.context is None
        ):
            return False
        owned = {
            item.resource_id
            for item in self.registration.state.context.prepared_functions
            if (item.owner.role, item.owner.generation) == backend
        }
        if not owned:
            return False
        for error in self.state.errors.values():
            if (
                error.occurred_monotonic_ns >= observed_ns
                and error.HasField("isolation")
                and owned <= set(error.isolation.affected_resource_ids)
            ):
                deadline = min(host_time_ns(), error.occurred_monotonic_ns) + max(
                    0, self.registration.state.context.policies.recovery_ns
                )
                if self.classification(error, deadline) == "continuable":
                    return True
        return False

    def observe_backend_exit(self, state: wire.LaunchState, now_ns: int) -> None:
        if self.shutdown.shutdown_request or self.shutdown.interruption:
            return
        backend = (state.plan.child.role, state.plan.child.generation)
        if backend in self.state.isolated_backend_exits:
            return
        if backend not in {
            (role, generation)
            for role, generation in self.registration.required_backends().items()
        }:
            self.begin_safety(
                types.Failure(code="CHILD_EXITED", message=state.failure.message)
            )
            return
        if backend not in self.state.pending_backend_exits:
            deadline = (
                now_ns + max(0, self.registration.state.context.policies.recovery_ns)
                if self.registration.state.context
                else now_ns
            )
            self.state.pending_backend_exits[backend] = (
                now_ns,
                deadline,
                types.Failure(code="BACKEND_EXITED", message=state.failure.message),
            )
            self.changed()

    async def _reconcile_helper_exits(self) -> None:
        unconfirmed = await self.reconcile_helpers(
            host_time_ns() + HELPER_RECONCILE_BUDGET_NS
        )
        for message in unconfirmed:
            self.warn(message)

    def _maybe_reconcile_helpers(
        self, states: list[wire.LaunchState], now_ns: int
    ) -> None:
        """Background, one at a time, rate limited; never awaited by the tick."""
        if (
            self.shutdown.shutdown_request
            or now_ns < self._next_reconcile_ns
            or (self._reconcile_task is not None and not self._reconcile_task.done())
            or not any(
                state.plan.stop_method == "owner_stdin_eof"
                and state.plan.child.role in FFMPEG_ROLES
                and state.phase == wire.LAUNCH_PHASE_OPERATIONAL
                for state in states
            )
        ):
            return
        self._next_reconcile_ns = now_ns + HELPER_RECONCILE_PERIOD_NS
        self._reconcile_task = self.tasks.spawn(
            "helper reconcile", self._reconcile_helper_exits()
        )

    def _expire_pending_errors(self, now: int) -> None:
        for error_id, deadline in list(self.state.pending_error_deadlines.items()):
            if now >= deadline:
                error = self.state.errors[error_id]
                if not self.verified_continuation(error):
                    self.begin_safety(error.failure, error_id)
                del self.state.pending_error_deadlines[error_id]

    def _check_authority_silence(self, now: int) -> None:
        key = self.controller.role, self.controller.generation
        last = self.state.last_heartbeat.get(key)
        # After an accepted shutdown, ShutdownCoordinator owns the controller
        # and backends; their silence/exit is no longer a safety fault.
        if (
            not self.shutdown.shutdown_request
            and last is not None
            and now >= last + self.silence_timeout_ns
        ):
            self.begin_safety(
                types.Failure(
                    code="CONTROLLER_LOST",
                    message="controller heartbeat silence",
                )
            )
        for role, generation in self.registration.required_backends().items():
            last = self.state.last_heartbeat.get((role, generation))
            if (
                not self.shutdown.shutdown_request
                and last is not None
                and now >= last + self.silence_timeout_ns
            ):
                self.begin_safety(
                    types.Failure(
                        code="BACKEND_HEARTBEAT_LOST",
                        message=f"{role} heartbeat silence",
                    )
                )

    def _check_launch_states(self, states: list[wire.LaunchState], now: int) -> None:
        for state in states:
            if (
                state.plan.child == self.controller
                and state.phase == wire.LAUNCH_PHASE_CLEANUP_REQUIRED
            ):
                if self.shutdown.shutdown_request:
                    if self.shutdown.shutdown_task is None:
                        self.shutdown.shutdown_task = asyncio.create_task(
                            self.shutdown_owned()
                        )
                else:
                    self.begin_safety(
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
                self.observe_backend_exit(state, now)
            elif state.failure.code in {"LAUNCH_TIMEOUT", "UNCONFIRMED_CHILD"}:
                self.begin_safety(
                    types.Failure(
                        code="UNSAFE_OWNERSHIP", message=state.failure.message
                    )
                )

    def _check_pending_backend_exits(self, now: int) -> None:
        for backend, (observed_ns, deadline_ns, failure) in list(
            self.state.pending_backend_exits.items()
        ):
            if self.backend_exit_isolated(backend, observed_ns):
                self.state.isolated_backend_exits.add(backend)
                del self.state.pending_backend_exits[backend]
            elif now >= deadline_ns:
                self.begin_safety(failure)

    async def monitor(self, period_s: float = 0.25) -> None:
        if self.state.monitor_task is not None:
            raise RuntimeError("supervisor monitor already active")
        self.state.monitor_task = asyncio.current_task()
        try:
            while True:
                now = host_time_ns()
                self._expire_pending_errors(now)
                self._check_authority_silence(now)
                try:
                    states = self.registry.states()
                except LaunchError as exc:
                    self.begin_safety(types.Failure(code=exc.code, message=str(exc)))
                    await asyncio.sleep(period_s)
                    continue
                self._check_launch_states(states, now)
                self._maybe_reconcile_helpers(states, now)
                self._check_pending_backend_exits(now)
                await asyncio.sleep(period_s)
        finally:
            self.state.monitor_task = None

    async def heartbeat_loop(self) -> None:
        """Supervisor → controller unary health; no status/history polling."""
        if self.state.heartbeater_task is not None:
            raise RuntimeError("supervisor heartbeat loop already active")
        self.state.heartbeater_task = asyncio.current_task()
        try:
            while True:
                report = types.HeartbeatReport(
                    source=self.identity,
                    sent_monotonic_ns=host_time_ns(),
                    session_phase=(
                        types.SESSION_PHASE_READY
                        if self.registration.state.context
                        else types.SESSION_PHASE_CONFIGURATION
                    ),
                    health_summary="supervisor control and monitor loop active",
                )
                if self.registration.state.context:
                    report.work.CopyFrom(self.registration.state.context.work)
                try:
                    # asyncio.timeout, unlike wait_for on 3.11, never swallows a cancel.
                    async with asyncio.timeout(5):
                        await self.outbound.report_heartbeat(report)
                except Exception:
                    # Controller applies its own ingress-based 15 s loss policy.
                    pass
                self.resend_status()
                await asyncio.sleep(self.heartbeat_interval_ns / 1e9)
        finally:
            self.state.heartbeater_task = None
