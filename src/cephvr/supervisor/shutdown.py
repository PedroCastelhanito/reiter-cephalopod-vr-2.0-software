"""Independent interruption and retained shutdown deadlines (E06/E08)."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.clock import host_time_ns
from cephvr.shared.emergency import write_emergency_report
from cephvr.shared.identity import require_uuid4
from cephvr.supervisor.acquisition_worker import AcquisitionWorkerControl
from cephvr.supervisor.ports import SupervisorOutbound
from cephvr.supervisor.process_exit import (
    ProcessExitEvidence,
    stop_owned_processes,
    wait_while,
)
from cephvr.supervisor.receipts import accepted, rejected
from cephvr.supervisor.recovery import RecoveryCoordinator
from cephvr.supervisor.registration import RegistrationCoordinator
from cephvr.supervisor.registry import LaunchRegistry, NativeLaunches
from cephvr.supervisor.state import HealthState, ShutdownState, SupervisorTasks
from cephvr.supervisor.visual_stimulus_worker import VisualStimulusWorkerControl
from cephvr.supervisor.worker_context import WorkerControl


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
        helper_warning: Callable[[str, str | None], None] | None = None,
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
        self.acquisition_worker_control = AcquisitionWorkerControl(
            registration=registration,
            registry=registry,
            outbound=outbound,
            issuer=identity,
            interrupt_commands=state.worker_interrupt_commands,
            cleanup_commands=state.worker_cleanup_commands,
            helper_warning=helper_warning,
        )
        self.visual_stimulus_worker_control = VisualStimulusWorkerControl(
            registration=registration,
            registry=registry,
            outbound=outbound,
            issuer=identity,
            interrupt_commands=state.worker_interrupt_commands,
            cleanup_commands=state.worker_cleanup_commands,
        )
        # Acquisition first: its helper reconcile and request order are fixed.
        self.worker_controls: tuple[WorkerControl, ...] = (
            self.acquisition_worker_control,
            self.visual_stimulus_worker_control,
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
                # A replay must not reset progress or a recorded outcome.
                self.recovery.state.operations.setdefault(
                    request.command_id,
                    types.OperationState(
                        context=types.OperationContext(command_id=request.command_id),
                        command="ShutdownApplication",
                        work=request.work,
                        progress="intent retained",
                    ),
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
        sys.stderr.write(
            f"CephVR supervisor shutdown: {reason.code}: {reason.message}\n"
        )
        self.retain_shutdown_deadlines(now)
        self.state.safety_task = asyncio.create_task(self.deliver_safety(report))
        self.changed()

    async def deliver_safety(self, report: wire.InterruptionReport) -> None:
        # Independent tasks: controller delivery cannot gate direct participant safety.
        tasks: dict[asyncio.Task[Any], str] = {
            asyncio.create_task(
                self.outbound.report_interruption(report)
            ): "interruption report",
            asyncio.create_task(
                self.outbound.notify_launcher_shutdown(
                    self.state.shutdown_deadline_ns or 0, report.reason.code
                )
            ): "launcher notification",
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
            ): "emergency report",
        }
        tasks.update(
            (task, "participant interruption")
            for task in self.interrupt_participants(report)
        )
        await self._wait_for_deliveries(tasks)
        if self.state.shutdown_task is None:
            self.state.shutdown_task = asyncio.create_task(self.shutdown_owned())
        await self.state.shutdown_task

    async def _wait_for_deliveries(self, tasks: dict[asyncio.Task[Any], str]) -> None:
        """Bound independent deliveries without letting one failure cancel peers."""
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
            self.tasks.report_failure(tasks[task], TimeoutError())
        for task in done:
            try:
                task.result()
            except Exception as exc:
                # Retained safety/launcher state stays authoritative; a failed
                # delivery is surfaced, never silent.
                self.tasks.report_failure(tasks[task], exc)

    def interrupt_participants(
        self, report: wire.InterruptionReport
    ) -> list[asyncio.Task[Any]]:
        """Start InterruptSession for registered coordinators and workers."""
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
        for control in self.worker_controls:
            for launch, worker in control.registered_workers(registered.work):
                tasks.append(
                    asyncio.create_task(
                        control.interrupt_worker(
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
        await self._wait_for_deliveries(
            {
                task: "participant interruption"
                for task in self.interrupt_participants(report)
            }
        )

    def _outer_deadline(self, cleanup_deadline: int) -> int:
        return min(
            cleanup_deadline, self.state.shutdown_deadline_ns or cleanup_deadline
        )

    async def _wait_for_cleanup_blockers(self, until_ns: int) -> None:
        await wait_while(self.recovery.cleanup_blockers, until_ns)

    async def _watch_controller_loss(self, until_ns: int) -> None:
        """Observe authority loss while bounded worker cleanup is in flight."""
        await wait_while(
            lambda: not self.state.shutdown_interrupted and not self._controller_gone(),
            until_ns,
        )
        if host_time_ns() < until_ns:
            await self.interrupt_if_controller_lost()

    def _registered_context(self) -> wire.RegisteredContext:
        # Re-read at each step: a re-registration may replace the context.
        context = self.registration.state.context
        assert context is not None
        return context

    async def _cleanup_workers(
        self, control: WorkerControl, cleanup_deadline: int
    ) -> bool:
        """Clean up one backend's registered workers; True when cleanup ran."""
        targets = control.registered_workers(self._registered_context().work)
        if not targets or host_time_ns() >= cleanup_deadline:
            return False
        results = await asyncio.gather(
            *(
                control.cleanup_worker(launch, worker, cleanup_deadline)
                for launch, worker in targets
            ),
            return_exceptions=True,
        )
        # Shutdown stays bounded; an unconfirmed worker cleanup is reported.
        for (_, worker), result in zip(targets, results, strict=True):
            if isinstance(result, Exception):
                self.tasks.report_failure(f"{worker.worker.role} cleanup", result)
        return True

    async def _cleanup_acquisition_workers(self, cleanup_deadline: int) -> None:
        if await self._cleanup_workers(
            self.acquisition_worker_control, cleanup_deadline
        ):
            # Only acquisition workers own EOF-stopped native helpers, so the
            # helper reconcile follows their cleanup and only when it ran.
            await self.acquisition_worker_control.reconcile_native_helper_exits(
                cleanup_deadline
            )

    async def _request_participant_shutdown(self, cleanup_deadline: int) -> None:
        context = self._registered_context()
        deadline = self._outer_deadline(cleanup_deadline)
        requests: dict[asyncio.Task[Any], str] = {}
        for target in context.required_participants:
            command = wire.BackendCommand(
                command_id=str(uuid4()),
                issuer=self.identity,
                target=target,
                work=context.work,
            )
            task = asyncio.create_task(
                self.outbound.shutdown_backend(target, command, deadline_ns=deadline)
            )
            requests[task] = f"{target.backend_name} shutdown request"
        for control in self.worker_controls:
            for launch, worker in control.registered_workers(context.work):
                task = asyncio.create_task(
                    control.shutdown_worker(launch, worker, deadline)
                )
                requests[task] = f"{worker.worker.role} shutdown request"
        # Rejected or timed-out requests surface as warnings; exit evidence, not
        # the reply, still decides the shutdown outcome.
        await self._wait_for_deliveries(requests)

    def _record_shutdown_outcome(self, exits: ProcessExitEvidence) -> None:
        if not self.state.shutdown_request:
            return
        request = wire.ApplicationShutdownRequest.FromString(
            self.state.shutdown_request
        )
        operation = self.recovery.state.operations.get(request.command_id)
        if operation is None:
            return
        blockers = self.recovery.cleanup_blockers()
        operation.complete = True
        operation.succeeded = (
            not exits.remaining and not blockers and not exits.unconfirmed_jobs
        )
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

    async def shutdown_owned(self) -> None:
        """Preserve the original outer deadline; exit groups have fixed inner bounds."""
        if self.registration.state.context:
            await self.interrupt_if_controller_lost()
            cleanup_deadline = min(
                self.state.cleanup_deadline_ns or host_time_ns(),
                self.state.shutdown_deadline_ns or host_time_ns(),
            )
            recovery_ns = max(0, self._registered_context().policies.recovery_ns)
            initial_deadline = max(host_time_ns(), cleanup_deadline - recovery_ns)
            observer = asyncio.create_task(
                self._watch_controller_loss(cleanup_deadline)
            )
            try:
                await self._wait_for_cleanup_blockers(initial_deadline)
                # Concurrent: one backend running to the deadline must not leave the
                # other's outputs unattempted.
                branches = await asyncio.gather(
                    self._cleanup_acquisition_workers(cleanup_deadline),
                    self._cleanup_workers(
                        self.visual_stimulus_worker_control, cleanup_deadline
                    ),
                    return_exceptions=True,
                )
                for name, branch in zip(
                    ("acquisition", "visual stimulus"), branches, strict=True
                ):
                    if isinstance(branch, Exception):
                        self.tasks.report_failure(f"{name} worker cleanup", branch)
                await self._wait_for_cleanup_blockers(cleanup_deadline)
                await self.interrupt_if_controller_lost()
                await self._request_participant_shutdown(cleanup_deadline)
            finally:
                observer.cancel()
                try:
                    await observer
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    self.tasks.report_failure("controller loss observer", exc)
        exits = await stop_owned_processes(
            registry=self.registry,
            native=self.native,
            shutdown=self.state,
            graceful_exit_ns=self.graceful_exit_ns,
            terminate_exit_ns=self.terminate_exit_ns,
        )
        self._record_shutdown_outcome(exits)
        if not exits.remaining and not exits.unconfirmed_jobs:
            self.state.shutdown_complete.set()
