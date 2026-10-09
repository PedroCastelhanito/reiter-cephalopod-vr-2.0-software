"""E05/E06 Setup cancellation, cleanup fences and reservation release."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from copy import deepcopy
from typing import Any, Literal

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.operations import ControlOperations
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.metadata.types import StorageError
from cephvr.controller.ports import BackendPort, SupervisorPort
from cephvr.controller.projections import ProjectionStore
from cephvr.controller.state import (
    Attempt,
    ConfigurationState,
    ControlState,
    IncidentState,
    LifecycleState,
    LimitsState,
)
from cephvr.shared.deadlines import remaining_seconds
from cephvr.shared.resources import (
    ResourceCatalogueError,
    validate_cleanup_fence_update,
)

ReportReceiver = Callable[
    [pb.LifecycleReport, int], Coroutine[Any, Any, pb.ReportReceipt]
]


class CleanupWorkflow:
    """Retire an attempt while keeping the original cleanup and recovery bounds."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        control: ControlState,
        incidents: IncidentState,
        limit_state: LimitsState,
        clock: Callable[[], int],
        publisher: SnapshotPublisher,
        control_operations: ControlOperations,
        supervisor: SupervisorPort | None,
        max_incident_bytes: int,
        reservation_released: Callable[[Attempt], Awaitable[None]] | None,
        generation: str,
        spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]],
        configuration: ConfigurationState,
        projections: ProjectionStore,
    ) -> None:
        self.lifecycle = lifecycle
        self.control = control
        self.incident_state = incidents
        self.limit_state = limit_state
        self.clock = clock
        self.publisher = publisher
        self.control_operations = control_operations
        self.supervisor = supervisor
        self.max_incident_bytes = max_incident_bytes
        self.reservation_released = reservation_released
        self.generation = generation
        self.spawn = spawn
        self.configuration_state = configuration
        self.projections = projections
        self._report: ReportReceiver | None = None

    def bind_report(self, report: ReportReceiver) -> None:
        """Complete the report/cleanup cycle during runtime assembly."""
        self._report = report

    async def report(
        self, lifecycle: pb.LifecycleReport, ingress_ns: int
    ) -> pb.ReportReceipt:
        receiver = self._report
        if receiver is None:
            raise RuntimeError("cleanup report receiver is not assembled")
        return await receiver(lifecycle, ingress_ns)

    async def release_reservation_pointer(
        self, attempt: Attempt, deadline_ns: int
    ) -> bool:
        if self.lifecycle.authority_lost or attempt.reservation_unconfirmed:
            return False
        if (
            not attempt.reservation_registration_started
            or self.reservation_released is None
        ):
            return True
        try:
            await asyncio.wait_for(
                self.reservation_released(attempt),
                remaining_seconds(deadline_ns, clock=self.clock),
            )
            return True
        except Exception as exc:
            async with self.lifecycle.lock:
                self.control.add_warning(
                    "reservation", f"durable reservation release unconfirmed: {exc}"
                )
                self.publisher.publish()
            return False

    async def retire_unactivated_reservation(
        self, attempt: Attempt, deadline_ns: int
    ) -> None:
        """E06: an unactivated attempt keeps metadata already written."""
        remaining = remaining_seconds(deadline_ns, clock=self.clock)
        if not attempt.closure.metadata_written:
            await asyncio.wait_for(
                asyncio.to_thread(attempt.reservation.cancel), remaining
            )
            return
        if attempt.writer is not None and not attempt.writer_closed:
            sealed = await asyncio.wait_for(
                asyncio.to_thread(attempt.writer.seal, remaining), remaining
            )
            if not sealed:
                raise StorageError("metadata writer seal unconfirmed")
            attempt.writer_closed = True
        await asyncio.wait_for(
            asyncio.to_thread(attempt.reservation.close_unactivated),
            remaining_seconds(deadline_ns, clock=self.clock),
        )

    def clear_projection_scope(self) -> None:
        """C1: a retired attempt leaves the projections sessionless (lock held)."""
        self.projections.set_scope(pb.WorkContext(), self.configuration_state.revision)

    def settle_operations(self, attempt: Attempt) -> None:
        """Complete every recorded command once closure is known (lock held)."""
        closure = attempt.closure
        if not closure.done:
            return
        confirmed = closure.clean and not self.lifecycle.authority_lost
        progress = (
            "interruption and cleanup confirmed"
            if confirmed
            else "cleanup evidence blocked"
        )
        cleanup_error = "" if confirmed else "cleanup could not be confirmed"
        for command_id in (
            attempt.cancel_command_ids
            + attempt.abort_command_ids
            + attempt.shutdown_command_ids
        ):
            if command_id in closure.handoff_pending:
                continue
            handoff_failure = closure.handoff_failures.get(command_id, "")
            self.control_operations.complete_operation(
                command_id,
                success=confirmed and not handoff_failure,
                progress=progress,
                error=f"shutdown handoff failed: {handoff_failure}"
                if handoff_failure
                else cleanup_error,
            )
        if attempt.setup_command_id:
            # No-op when Setup already reached Ready or failed on its own.
            self.control_operations.complete_operation(
                attempt.setup_command_id,
                success=False,
                progress=progress,
                error=f"setup cancelled: {closure.reason or 'cancelled before Ready'}",
            )
        if closure.start_command_id:
            self.control_operations.complete_operation(
                closure.start_command_id,
                success=False,
                progress=progress,
                error=f"start cancelled: {closure.reason or 'session closed'}",
            )

    async def dispatch_backend_cleanup(
        self,
        attempt: Attempt,
        deadline: int,
        method: Literal["cancel_setup", "cleanup"],
    ) -> bool:
        """Fence, then dispatch one cleanup-class command to every required backend.

        Returns whether the fences registered and every backend accepted; the
        caller handles ``TimeoutError``.
        """
        requests = {
            name: self.backend_command(attempt, backend)
            for name, backend in attempt.required.items()
        }
        attempt.cleanup_commands.update(
            {name: request.command_id for name, request in requests.items()}
        )
        fenced = (
            await self.register_cleanup_fences(attempt, requests, deadline)
            if not self.lifecycle.authority_lost
            else False
        )
        if fenced or self.lifecycle.authority_lost:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        getattr(backend, method)(requests[name], deadline_ns=deadline)
                        for name, backend in attempt.required.items()
                    ),
                    return_exceptions=True,
                ),
                remaining_seconds(deadline, clock=self.clock),
            )
            return (
                all(
                    isinstance(result, pb.CommandAdmission)
                    and result.result == pb.COMMAND_RESULT_ACCEPTED
                    for result in results
                )
                and fenced
            )
        return fenced

    async def cancel_attempt(self, attempt: Attempt) -> None:
        async with self.lifecycle.lock:
            if attempt.cancelling:
                # The running cancel completes recorded IDs; a later one is settled now.
                self.settle_operations(attempt)
                self.publisher.publish()
                return
            attempt.cancelling = True
        deadline = self.clock() + self.limit_state.current.setup_cancel_ns
        if not attempt.finalization_deadline_ns:
            attempt.finalization_deadline_ns = deadline
        else:
            deadline = min(deadline, attempt.finalization_deadline_ns)
        clean = True
        try:
            clean = await self.dispatch_backend_cleanup(
                attempt, deadline, "cancel_setup"
            )
        except TimeoutError:
            clean = False
        if attempt.setup_operations:
            clean = await self.await_cleanups(attempt, deadline) and clean
        if attempt.reservation_unconfirmed:
            clean = False
        if clean and not self.lifecycle.authority_lost and attempt.reservation.held:
            try:
                await self.retire_unactivated_reservation(
                    attempt, deadline + self.limit_state.current.recovery_ns
                )
                clean = await self.release_reservation_pointer(
                    attempt, deadline + self.limit_state.current.recovery_ns
                )
            except (StorageError, OSError) as exc:
                clean = False
                self.control.add_warning("reservation", str(exc))
            except TimeoutError:
                clean = False
        async with self.lifecycle.lock:
            if self.lifecycle.attempt is attempt:
                self.lifecycle.session = pb.SessionState(
                    phase=pb.SESSION_PHASE_CONFIGURATION,
                    cleanup_confirmed=clean and not self.lifecycle.authority_lost,
                    shutdown_requested=bool(self.lifecycle.shutdown_intent_ns),
                )
                if not clean:
                    # The retained attempt stays addressable: clients derive the
                    # required expected_work of AbortNow/Shutdown from this.
                    self.lifecycle.session.context.CopyFrom(attempt.context)
                self.lifecycle.trial = pb.TrialState(phase=pb.TRIAL_PHASE_PENDING)
                self.clear_projection_scope()
                attempt.closure.done = True
                attempt.closure.clean = clean
                self.settle_operations(attempt)
                if clean:
                    self.lifecycle.attempt = None
                self.publisher.publish()

    async def await_cleanups(self, attempt: Attempt, initial_deadline_ns: int) -> bool:
        expected = set(attempt.setup_operations)
        while self.clock() < initial_deadline_ns:
            async with self.lifecycle.lock:
                if expected <= attempt.cleanup.keys():
                    return True
                attempt.changed.clear()
            try:
                await asyncio.wait_for(
                    attempt.changed.wait(),
                    remaining_seconds(initial_deadline_ns, clock=self.clock),
                )
            except TimeoutError:
                break
        missing = expected - attempt.cleanup.keys()
        recovery_deadline = initial_deadline_ns + self.limit_state.current.recovery_ns

        async def query(name: str) -> None:
            backend = attempt.required[name]
            request = svc.BackendQuery(
                target=backend.context, work=pb.WorkContext(session=attempt.context)
            )
            try:
                state = await asyncio.wait_for(
                    backend.get_state(request, deadline_ns=recovery_deadline),
                    remaining_seconds(recovery_deadline, clock=self.clock),
                )
                if state.HasField("cleanup"):
                    await self.report(
                        pb.LifecycleReport(cleanup=state.cleanup), self.clock()
                    )
            except Exception:
                return

        await asyncio.gather(*(query(name) for name in missing))
        return expected <= attempt.cleanup.keys()

    def backend_command(
        self, attempt: Attempt, backend: BackendPort
    ) -> svc.BackendCommand:
        request = svc.BackendCommand(command_id=str(uuid.uuid4()))
        request.issuer.role = "controller"
        request.issuer.generation = self.generation
        request.target.CopyFrom(backend.context)
        request.work.session.CopyFrom(attempt.context)
        return request

    async def register_cleanup_fences(
        self,
        attempt: Attempt,
        requests: Mapping[str, svc.BackendCommand],
        deadline_ns: int,
    ) -> bool:
        previous = attempt.registered_context
        if previous is None or self.supervisor is None:
            return False
        updated = deepcopy(previous)
        for name, request in requests.items():
            updated.cleanup_commands.add(
                target=pb.ProcessIdentity(
                    role=name,
                    generation=attempt.required[name].context.backend_generation,
                ),
                work=request.work,
                operation=pb.OperationContext(command_id=request.command_id),
            )
        try:
            validate_cleanup_fence_update(
                previous, updated, max_fences=256, max_bytes=self.max_incident_bytes
            )
            receipt = await asyncio.wait_for(
                self.supervisor.register_context(
                    svc.RegisterContextRequest(
                        command_id=str(uuid.uuid4()), context=updated
                    )
                ),
                remaining_seconds(deadline_ns, clock=self.clock),
            )
            if (
                receipt.admission.result != pb.COMMAND_RESULT_ACCEPTED
                or receipt.registered != updated
            ):
                return False
            attempt.registered_context = deepcopy(updated)
            return True
        except (ResourceCatalogueError, TimeoutError, Exception):
            return False

    async def cancel_setup(self, command: svc.OperatorCommand) -> pb.CommandAdmission:
        async with self.lifecycle.lock:
            error = self.control_operations.authorized(command, targets_work=True)
            attempt = self.lifecycle.attempt
            if (
                error
                or attempt is None
                or self.lifecycle.session.phase
                not in (pb.SESSION_PHASE_SETTING_UP, pb.SESSION_PHASE_READY)
            ):
                return self.control_operations.admission(
                    command.operator.command_id,
                    error=error or "Cancel Setup unavailable",
                )
            attempt.cancel_requested = True
            attempt.cancel_command_ids.append(command.operator.command_id)
            self.control_operations.operation(
                command.operator.command_id,
                "CancelSetup",
                attempt=attempt,
                progress="bounded cleanup in progress",
            )
            if attempt.handoff is not None:
                attempt.handoff.retire()
            self.cancel_attempt_prompts(attempt)
            self.spawn(self.cancel_attempt(attempt))
            return self.control_operations.admission(command.operator.command_id)

    def cancel_attempt_prompts(self, attempt: Attempt) -> None:
        """Settle outstanding Setup prompts owned by one retiring attempt."""
        for _prompt, future, owner in self.incident_state.prompts.values():
            if owner is attempt and not future.done():
                future.cancel()

    async def late_cleanup(self, attempt: Attempt) -> None:
        async with self.lifecycle.lock:
            if (
                self.lifecycle.authority_lost
                or attempt.reservation_unconfirmed
                or self.lifecycle.attempt is not attempt
                or self.lifecycle.session.cleanup_confirmed
                or len(attempt.cleanup) != len(attempt.required)
            ):
                return
            if self.lifecycle.session.phase == pb.SESSION_PHASE_ENDED:
                if (
                    not attempt.writer_closed
                    or attempt.paired
                    and not attempt.spikeglx_stopped
                ):
                    return
                complete = True
            elif (
                self.lifecycle.session.phase == pb.SESSION_PHASE_CONFIGURATION
                and attempt.cancel_requested
            ):
                complete = False
            else:
                return
        deadline_ns = self.clock() + self.limit_state.current.metadata_ns
        try:
            if complete:
                await asyncio.wait_for(
                    asyncio.to_thread(attempt.reservation.complete),
                    remaining_seconds(deadline_ns, clock=self.clock),
                )
            else:
                await self.retire_unactivated_reservation(attempt, deadline_ns)
            if not await self.release_reservation_pointer(attempt, deadline_ns):
                return
        except (StorageError, OSError, TimeoutError):
            return
        async with self.lifecycle.lock:
            if self.lifecycle.attempt is attempt:
                self.lifecycle.session.cleanup_confirmed = True
                if not complete:
                    self.lifecycle.attempt = None
                    self.clear_projection_scope()
                self.publisher.publish()
