"""Independent interruption and retained shutdown deadlines (E06/E08)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.clock import host_time_ns
from cephvr.shared.emergency import write_emergency_report
from cephvr.shared.identity import require_uuid4
from cephvr.supervisor.acquisition_cleanup import AcquisitionWorkerCleanup
from cephvr.supervisor.acquisition_shutdown import AcquisitionWorkerShutdown
from cephvr.supervisor.ports import SupervisorOutbound
from cephvr.supervisor.receipts import accepted, rejected
from cephvr.supervisor.recovery import RecoveryCoordinator
from cephvr.supervisor.registration import RegistrationCoordinator
from cephvr.supervisor.registry import LaunchRegistry, NativeLaunches
from cephvr.supervisor.state import HealthState, ShutdownState, SupervisorTasks


class ShutdownCoordinator:
    def __init__(
        self,
        *,
        state: ShutdownState,
        registration: RegistrationCoordinator,
        recovery: RecoveryCoordinator,
        health: HealthState,
        identity: types.ProcessIdentity,
        controller: types.ProcessIdentity,
        registry: LaunchRegistry,
        native: NativeLaunches,
        outbound: SupervisorOutbound,
        software_root: Path,
        lock: asyncio.Lock,
        max_retained_entries: int,
        emergency_timeout_ns: int,
        application_backstop_ns: int,
        graceful_exit_ns: int,
        terminate_exit_ns: int,
        silence_timeout_ns: int,
        tasks: SupervisorTasks,
        changed: Callable[[], None],
    ) -> None:
        self.state = state
        self.registration = registration
        self.recovery = recovery
        self.health = health
        self.identity = identity
        self.controller = controller
        self.registry = registry
        self.native = native
        self.outbound = outbound
        self.acquisition_cleanup = AcquisitionWorkerCleanup(
            outbound=outbound,
            issuer=identity,
            command_ids=state.worker_cleanup_commands,
        )
        self.worker_shutdown = AcquisitionWorkerShutdown(
            registration=registration,
            registry=registry,
            outbound=outbound,
            issuer=identity,
            interrupt_commands=state.worker_interrupt_commands,
        )
        self.software_root = software_root
        self.lock = lock
        self.max_retained_entries = max_retained_entries
        self.emergency_timeout_ns = emergency_timeout_ns
        self.application_backstop_ns = application_backstop_ns
        self.graceful_exit_ns = graceful_exit_ns
        self.terminate_exit_ns = terminate_exit_ns
        self.silence_timeout_ns = silence_timeout_ns
        self.tasks = tasks
        self.changed = changed

    async def request_application_shutdown(
        self,
        request: wire.ApplicationShutdownRequest,
    ) -> types.CommandAdmission:
        try:
            require_uuid4(request.command_id)
            if (
                request.controller != self.controller
                or request.supervisor != self.identity
            ):
                raise ValueError("authority generation mismatch")
            if request.HasField("work") and not self.registration.same_work(
                request.work
            ):
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
            async with self.lock:
                if (
                    self.state.shutdown_request
                    and self.state.shutdown_request != payload
                ):
                    raise ValueError("a different shutdown intent is already retained")
                if (
                    len(self.recovery.state.operations) >= self.max_retained_entries
                    and request.command_id not in self.recovery.state.operations
                ):
                    self.begin_safety(
                        types.Failure(
                            code="OPERATION_CAPACITY",
                            message="required operation accounting exhausted",
                        )
                    )
                    raise ValueError("operation accounting exhausted")
                self.state.shutdown_request = payload
                issued = min(host_time_ns(), request.issued_monotonic_ns)
                shutdown_deadline = self.retain_shutdown_deadlines(issued)
                self.recovery.state.operations[request.command_id] = (
                    types.OperationState(
                        context=types.OperationContext(command_id=request.command_id),
                        command="ShutdownApplication",
                        work=request.work,
                        progress="intent retained",
                    )
                )
            self.tasks.spawn(
                "launcher shutdown notification",
                self.outbound.notify_launcher_shutdown(
                    shutdown_deadline, "explicit_shutdown"
                ),
            )
            if self.state.shutdown_task is None:
                self.state.shutdown_task = asyncio.create_task(self.shutdown_owned())
            self.changed()
            return accepted(request.command_id)
        except ValueError as exc:
            return rejected(request.command_id, exc)

    def retain_shutdown_deadlines(self, issued_ns: int) -> int:
        deadline = issued_ns + self.application_backstop_ns
        self.state.shutdown_deadline_ns = min(
            deadline, self.state.shutdown_deadline_ns or deadline
        )
        if self.registration.state.context:
            cleanup_limit = (
                issued_ns
                + max(
                    self.registration.state.context.policies.setup_cancel.initial_ns,
                    self.registration.state.context.policies.trial_finished.initial_ns,
                )
                + self.registration.state.context.policies.recovery_ns
            )
            self.state.cleanup_deadline_ns = min(
                cleanup_limit, self.state.cleanup_deadline_ns or cleanup_limit
            )
        return self.state.shutdown_deadline_ns

    def begin_safety(
        self, reason: types.Failure, triggering_error_id: str | None = None
    ) -> None:
        if self.state.interruption is not None:
            return
        now = host_time_ns()
        report = wire.InterruptionReport(
            interruption_id=str(uuid4()),
            supervisor=self.identity,
            controller_generation=self.controller.generation,
            issued_monotonic_ns=now,
            reason=reason,
        )
        if self.registration.state.context:
            report.work.CopyFrom(self.registration.state.context.work)
        if triggering_error_id:
            report.triggering_error_id = triggering_error_id
        self.state.interruption = report
        self.retain_shutdown_deadlines(now)
        self.state.safety_task = asyncio.create_task(self.deliver_safety(report))
        self.changed()

    async def deliver_safety(self, report: wire.InterruptionReport) -> None:
        # Independent tasks: controller delivery cannot gate direct participant safety.
        names = ["interruption report", "launcher notification", "emergency report"]
        tasks: list[asyncio.Task[Any]] = [
            asyncio.create_task(self.outbound.report_interruption(report)),
            asyncio.create_task(
                self.outbound.notify_launcher_shutdown(
                    self.state.shutdown_deadline_ns or 0, report.reason.code
                )
            ),
            asyncio.create_task(
                write_emergency_report(
                    self.software_root,
                    cause=report.reason.code,
                    supervisor=self.identity,
                    controller=self.controller,
                    work=report.work if report.HasField("work") else None,
                    errors=list(self.health.errors.values()),
                    # The supervisor has no independent SpikeGLX stop channel;
                    # the frozen Setup fact distinguishes an absent run from an
                    # expected run whose stop cannot be verified here.
                    spikeglx_stop_unconfirmed=bool(
                        self.registration.state.context
                        and self.registration.state.context.paired_spikeglx
                    ),
                    timeout_ns=self.emergency_timeout_ns,
                )
            ),
        ]
        interrupts = self.interrupt_participants(report)
        tasks.extend(interrupts)
        names.extend("participant interruption" for _ in interrupts)
        remaining_s = max(
            0.0,
            min(
                5_000_000_000,
                (self.state.shutdown_deadline_ns or host_time_ns()) - host_time_ns(),
            )
            / 1e9,
        )
        done, pending = await asyncio.wait(tasks, timeout=remaining_s)
        for task in pending:
            task.cancel()
            self.tasks.report_failure(names[tasks.index(task)], TimeoutError())
        for task in done:
            try:
                task.result()
            except Exception as exc:
                # Retained safety/launcher state stays authoritative; a failed
                # delivery is surfaced, never silent.
                self.tasks.report_failure(names[tasks.index(task)], exc)
        if self.state.shutdown_task is None:
            self.state.shutdown_task = asyncio.create_task(self.shutdown_owned())
        await self.state.shutdown_task

    def interrupt_participants(
        self, report: wire.InterruptionReport
    ) -> list[asyncio.Task[Any]]:
        """Start InterruptSession for registered coordinators and acquisition workers."""
        registered = self.registration.state.context
        tasks: list[asyncio.Task[Any]] = []
        if not registered:
            return tasks
        worker_deadline = min(
            self.state.cleanup_deadline_ns
            or self.state.shutdown_deadline_ns
            or host_time_ns(),
            self.state.shutdown_deadline_ns or host_time_ns(),
        )
        for launch, worker in self.worker_shutdown.registered_acquisition_workers(
            registered.work
        ):
            tasks.append(
                asyncio.create_task(
                    self.worker_shutdown.interrupt_worker(
                        launch, worker, report, worker_deadline
                    )
                )
            )
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
                    self.outbound.interrupt_backend(
                        participant,
                        interrupt,
                        deadline_ns=worker_deadline,
                    )
                )
            )
        return tasks

    def _controller_gone(self) -> bool:
        key = self.controller.role, self.controller.generation
        last = self.health.last_heartbeat.get(key)
        if last is not None and host_time_ns() >= last + self.silence_timeout_ns:
            return True
        return any(
            state.plan.child == self.controller
            and state.phase == wire.LAUNCH_PHASE_CLEANUP_REQUIRED
            for state in self.registry.states(tolerant=True)
        )

    def _controller_reported_active_session(self) -> bool:
        heartbeat = self.health.heartbeat_reports.get(
            (self.controller.role, self.controller.generation)
        )
        if heartbeat is None:
            return False
        if heartbeat.WhichOneof("lifecycle") == "session_phase":
            return heartbeat.session_phase in {
                types.SESSION_PHASE_SETTING_UP,
                types.SESSION_PHASE_STARTING,
                types.SESSION_PHASE_RUNNING,
                types.SESSION_PHASE_FINALIZING,
            }
        return heartbeat.trial_phase in {
            types.TRIAL_PHASE_PREPARING,
            types.TRIAL_PHASE_STARTING,
            types.TRIAL_PHASE_RUNNING,
            types.TRIAL_PHASE_FINALIZING,
        }

    async def interrupt_if_controller_lost(self) -> None:
        """Controller gone during orderly shutdown: interrupt an active session once.

        No safety fence or emergency report (the shutdown is intended); this only
        stops session activity before Shutdown reaches the participants.
        """
        if (
            self.state.shutdown_interrupted
            or self.state.interruption is not None  # safety already interrupted
            or not self.state.shutdown_request
            or not self.registration.state.context
            or not self._controller_gone()
            or not self._controller_reported_active_session()
        ):
            return
        self.state.shutdown_interrupted = True
        report = wire.InterruptionReport(
            interruption_id=str(uuid4()),
            supervisor=self.identity,
            controller_generation=self.controller.generation,
            issued_monotonic_ns=host_time_ns(),
            reason=types.Failure(
                code="CONTROLLER_LOST_DURING_SHUTDOWN",
                message="controller lost during shutdown",
            ),
            work=self.registration.state.context.work,
        )
        tasks = self.interrupt_participants(report)
        if not tasks:
            return
        remaining_s = max(
            0.0,
            min(
                5_000_000_000,
                (self.state.shutdown_deadline_ns or host_time_ns()) - host_time_ns(),
            )
            / 1e9,
        )
        done, pending = await asyncio.wait(tasks, timeout=remaining_s)
        for task in pending:
            task.cancel()
            self.tasks.report_failure("participant interruption", TimeoutError())
        for task in done:
            if task.exception() is not None:
                self.tasks.report_failure(
                    "participant interruption", task.exception() or RuntimeError()
                )

    async def shutdown_owned(self) -> None:
        """Preserve the original outer deadline; exit groups have fixed inner bounds."""
        if self.registration.state.context:
            await self.interrupt_if_controller_lost()
            cleanup_deadline = min(
                self.state.cleanup_deadline_ns or host_time_ns(),
                self.state.shutdown_deadline_ns or host_time_ns(),
            )
            recovery_ns = max(0, self.registration.state.context.policies.recovery_ns)
            initial_deadline = max(host_time_ns(), cleanup_deadline - recovery_ns)
            while (
                self.recovery.cleanup_blockers() and host_time_ns() < initial_deadline
            ):
                await asyncio.sleep(
                    min(0.05, (initial_deadline - host_time_ns()) / 1e9)
                )
            worker_targets = self.worker_shutdown.registered_acquisition_workers(
                self.registration.state.context.work
            )
            if worker_targets and host_time_ns() < cleanup_deadline:
                results = await asyncio.gather(
                    *(
                        self.acquisition_cleanup.reconcile(
                            launch, worker, deadline_ns=cleanup_deadline
                        )
                        for launch, worker in worker_targets
                    ),
                    return_exceptions=True,
                )
                # Shutdown stays bounded; an unconfirmed worker cleanup is reported.
                for (_, worker), result in zip(worker_targets, results, strict=True):
                    if isinstance(result, Exception):
                        self.tasks.report_failure(
                            f"{worker.worker.role} cleanup", result
                        )
                await self.worker_shutdown.reconcile_native_helper_exits(
                    cleanup_deadline
                )
            while (
                self.recovery.cleanup_blockers() and host_time_ns() < cleanup_deadline
            ):
                await asyncio.sleep(
                    min(0.05, (cleanup_deadline - host_time_ns()) / 1e9)
                )
            await self.interrupt_if_controller_lost()
            requests = []
            for target in self.registration.state.context.required_participants:
                command = wire.BackendCommand(
                    command_id=str(uuid4()),
                    issuer=self.identity,
                    target=target,
                    work=self.registration.state.context.work,
                )
                requests.append(
                    self.outbound.shutdown_backend(
                        target,
                        command,
                        deadline_ns=min(
                            cleanup_deadline,
                            self.state.shutdown_deadline_ns or cleanup_deadline,
                        ),
                    )
                )
            for launch, worker in self.worker_shutdown.registered_acquisition_workers(
                self.registration.state.context.work
            ):
                requests.append(
                    self.worker_shutdown.shutdown_worker(
                        launch,
                        worker,
                        min(
                            cleanup_deadline,
                            self.state.shutdown_deadline_ns or cleanup_deadline,
                        ),
                    )
                )
            if requests:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*requests, return_exceptions=True), timeout=5
                    )
                except TimeoutError:
                    pass
        unconfirmed: set[str] = set()

        def inspect(state: wire.LaunchState) -> list[tuple[int, int, str]]:
            # A released launch proved absence and closed its job handle.
            if state.phase == wire.LAUNCH_PHASE_RELEASED:
                return []
            # One unreadable job must not stop shutdown of the other children.
            try:
                return self.native.inspect_launch_job(state.containment_job_name)
            except Exception:
                unconfirmed.add(state.containment_job_name)
                return []

        for roles in ({"acquisition", "vr", "tracking"}, {"controller", "gui"}):
            candidates = [
                state
                for state in self.registry.states(tolerant=True)
                if state.plan.child.role in roles
            ]

            def remaining_members(
                states: tuple[wire.LaunchState, ...] = tuple(candidates),
            ) -> list[tuple[int, int, str]]:
                found: dict[tuple[int, int], tuple[int, int, str]] = {}
                for state in states:
                    for member in inspect(state):
                        found[member[:2]] = member
                return list(found.values())

            grace_until = min(
                host_time_ns() + self.graceful_exit_ns,
                self.state.shutdown_deadline_ns
                or (host_time_ns() + self.graceful_exit_ns),
            )
            while host_time_ns() < grace_until and remaining_members():
                await asyncio.sleep(0.05)
            for pid, created, _ in remaining_members():
                try:
                    if self.native.process_running(pid, created):
                        self.native.terminate_exact(pid, created)
                except Exception:
                    # Continue with the other members; the final job inspection
                    # decides whether this one is still present.
                    continue
            terminate_until = min(
                host_time_ns() + self.terminate_exit_ns,
                self.state.shutdown_deadline_ns
                or (host_time_ns() + self.terminate_exit_ns),
            )
            while host_time_ns() < terminate_until and remaining_members():
                await asyncio.sleep(0.05)
        unconfirmed.clear()  # only the final inspection can leave absence unconfirmed
        remaining = [
            member
            for state in self.registry.states(tolerant=True)
            if state.plan.child.role != "supervisor"
            for member in inspect(state)
        ]
        if self.state.shutdown_request:
            request = wire.ApplicationShutdownRequest.FromString(
                self.state.shutdown_request
            )
            operation = self.recovery.state.operations.get(request.command_id)
            if operation is not None:
                blockers = self.recovery.cleanup_blockers()
                operation.complete = True
                operation.succeeded = not remaining and not blockers and not unconfirmed
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
                self.changed()
        if not remaining and not unconfirmed:
            self.state.shutdown_complete.set()
