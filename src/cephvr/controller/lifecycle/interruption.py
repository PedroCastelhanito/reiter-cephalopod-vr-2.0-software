"""E06 interruption delivery, metadata closure and bounded finalization."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.operations import ControlOperations
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.incident.registry import IncidentCapacityError
from cephvr.controller.lifecycle.cleanup import CleanupWorkflow
from cephvr.controller.metadata.coordination import MetadataCoordinator
from cephvr.controller.metadata.trial_logs import TrialLogs
from cephvr.controller.metadata.types import StorageError
from cephvr.controller.ports import BackendPort, SpikeGLXPort
from cephvr.controller.state import (
    Attempt,
    ControlState,
    IncidentState,
    LifecycleState,
    LimitsState,
    MetadataState,
    SupervisorState,
)


class InterruptionWorkflow:
    """Interrupt once, retain the original bound, then seal and clean."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        control: ControlState,
        incidents: IncidentState,
        metadata_state: MetadataState,
        supervisor_state: SupervisorState,
        limit_state: LimitsState,
        cleanup: CleanupWorkflow,
        metadata: MetadataCoordinator,
        trial_logs: TrialLogs,
        spikeglx: SpikeGLXPort | None,
        publisher: SnapshotPublisher,
        control_operations: ControlOperations,
        generation: str,
        supervisor_generation: str,
        clock: Callable[[], int],
        spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]],
    ) -> None:
        self.lifecycle = lifecycle
        self.control = control
        self.incident_state = incidents
        self.metadata_state = metadata_state
        self.supervisor_state = supervisor_state
        self.limit_state = limit_state
        self.cleanup = cleanup
        self.metadata = metadata
        self.trial_logs = trial_logs
        self.spikeglx = spikeglx
        self.publisher = publisher
        self.control_operations = control_operations
        self.generation = generation
        self.supervisor_generation = supervisor_generation
        self.clock = clock
        self.spawn = spawn

    async def interrupt(
        self, attempt: Attempt, reason: str, *, issued_ns: int | None = None
    ) -> None:
        closure = attempt.closure
        async with self.lifecycle.lock:
            if self.lifecycle.attempt is not attempt:
                return
            if self.lifecycle.session.phase == pb.SESSION_PHASE_ENDED:
                # A completed session is never relabelled; recorded commands settle.
                if not closure.done:
                    closure.done = True
                    closure.clean = self.lifecycle.session.cleanup_confirmed
                self.cleanup.settle_operations(attempt)
                self.publisher.publish()
                return
            if attempt.interrupted:
                # Idempotent join: recorded IDs settle when the one closure ends.
                self.cleanup.settle_operations(attempt)
                joined = closure.task
                first = False
            else:
                joined = closure.task
                first = True
                attempt.interrupted = True
                closure.reason = closure.reason or reason
                attempt.interruption_issued_ns = (
                    self.clock() if issued_ns is None else issued_ns
                )
                if not attempt.activated and joined is None:
                    attempt.cancel_requested = True
                    self.publisher.publish()
        if joined is not None:
            await self._join(joined)
            return
        if not first:
            return
        activated = attempt.activated
        if (
            attempt.start_task is not None
            and attempt.start_task is not asyncio.current_task()
        ):
            attempt.start_task.cancel()
            await asyncio.gather(attempt.start_task, return_exceptions=True)
        if not activated:
            await self.cleanup.cancel_attempt(attempt)
            return
        async with self.lifecycle.lock:
            if closure.task is not None:
                joined = closure.task
            else:
                self.lifecycle.session.phase = pb.SESSION_PHASE_FINALIZING
                self.lifecycle.session.outcome = pb.SESSION_OUTCOME_INTERRUPTED
                self.lifecycle.session.interruption_reason.CopyFrom(
                    pb.Failure(code="INTERRUPTED", message=reason)
                )
                if not attempt.finalization_deadline_ns:
                    attempt.finalization_deadline_ns = (
                        attempt.interruption_issued_ns
                        + self.limit_state.current.stop_evidence_ns
                        + self.limit_state.current.finished_ns
                        + self.limit_state.current.setup_cancel_ns
                    )
                if (
                    self.lifecycle.trial.phase
                    in (
                        pb.TRIAL_PHASE_RUNNING,
                        pb.TRIAL_PHASE_STARTING,
                        pb.TRIAL_PHASE_FINALIZING,
                    )
                    and (attempt.started or attempt.trial_closure.released)
                    and not attempt.trial_log_finished
                ):
                    # E05: once release was issued the trial exists, whether or not
                    # any Started report was accepted.
                    self.lifecycle.trial.phase = pb.TRIAL_PHASE_FINALIZING
                    self.lifecycle.trial.outcome = pb.TRIAL_OUTCOME_INTERRUPTED
                    self.lifecycle.trial.interruption_issued_monotonic_ns = (
                        attempt.interruption_issued_ns
                    )
                    attempt.finished_deadline_ns = (
                        attempt.interruption_issued_ns
                        + self.limit_state.current.finished_ns
                    )
                self.publisher.publish()
                joined = None
        if joined is not None:
            await self._join(joined)
            return
        trial_metadata_clean = False
        try:
            trial_metadata_clean = await self._stop_backends_and_trial(attempt, reason)
        except Exception as exc:
            # Finalization must still run, or later interrupts would only join a
            # closure that never started.
            async with self.lifecycle.lock:
                self.control.warnings.append(
                    pb.Warning(
                        warning_id=str(uuid.uuid4()),
                        component="interruption",
                        message=f"pre-finalization step failed: {exc}",
                    )
                )
                self.control.warnings = self.control.warnings[-256:]
                self.publisher.publish()
        finally:
            await self.finalize(
                attempt, metadata_clean=trial_metadata_clean, from_interrupt=True
            )

    async def _stop_backends_and_trial(self, attempt: Attempt, reason: str) -> bool:
        stop_deadline_ns = (
            attempt.interruption_issued_ns + self.limit_state.current.stop_evidence_ns
        )
        if (
            attempt.trial_task is not None
            and attempt.trial_task is not asyncio.current_task()
        ):
            attempt.trial_task.cancel()
            await asyncio.gather(attempt.trial_task, return_exceptions=True)
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    *(
                        backend.interrupt_session(
                            self.interrupt_request(attempt, backend, reason),
                            deadline_ns=stop_deadline_ns,
                        )
                        for backend in attempt.required.values()
                    ),
                    return_exceptions=True,
                ),
                max(0, (stop_deadline_ns - self.clock()) / 1e9),
            )
        except TimeoutError:
            pass
        return await self.trial_logs.finish_interrupted_trial(attempt)

    @staticmethod
    async def _join(task: asyncio.Task[None]) -> None:
        """Wait for the owned finalize task; its failure belongs to its first caller."""
        await asyncio.gather(asyncio.shield(task), return_exceptions=True)

    async def authority_loss(self, reason: str, issued_ns: int) -> None:
        async with self.lifecycle.lock:
            if self.lifecycle.authority_lost:
                return
            self.lifecycle.authority_lost = True
            self.lifecycle.shutdown_intent_ns = (
                min(self.lifecycle.shutdown_intent_ns, issued_ns)
                if self.lifecycle.shutdown_intent_ns
                else issued_ns
            )
            self.lifecycle.session.shutdown_requested = True
            attempt = self.lifecycle.attempt
            if attempt is not None and not attempt.interruption_issued_ns:
                attempt.interruption_issued_ns = issued_ns
            self.control.owner = None
            self.publisher.publish()
        if attempt is not None:
            # This dispatch is independent of an older CancelSetup/cleanup task that
            # may be waiting on the now-lost supervisor. Admission is not stop proof.
            emergency = self.spawn(self.authority_emergency_interrupt(attempt, reason))
            await self.interrupt(attempt, reason, issued_ns=issued_ns)
            await asyncio.gather(emergency, return_exceptions=True)

    async def authority_emergency_interrupt(
        self, attempt: Attempt, reason: str
    ) -> None:
        stop_deadline_ns = (
            attempt.interruption_issued_ns + self.limit_state.current.stop_evidence_ns
        )
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    *(
                        backend.interrupt_session(
                            self.interrupt_request(attempt, backend, reason),
                            deadline_ns=stop_deadline_ns,
                        )
                        for backend in attempt.required.values()
                    ),
                    return_exceptions=True,
                ),
                max(0, (stop_deadline_ns - self.clock()) / 1e9),
            )
        except TimeoutError:
            pass

    async def report_interruption(
        self, report: svc.InterruptionReport
    ) -> pb.ReportReceipt:
        async with self.lifecycle.lock:
            attempt = self.lifecycle.attempt
            if (
                attempt is None
                or report.controller_generation != self.generation
                or report.supervisor.role != "supervisor"
                or report.supervisor.generation != self.supervisor_generation
                or not report.interruption_id
            ):
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(
                        code="IDENTITY", message="interruption identity mismatch"
                    ),
                )
            work_kind = report.work.WhichOneof("work")
            if work_kind == "session":
                valid_work = report.work.session == attempt.context
            elif work_kind == "trial" and attempt.trial_index >= 0:
                valid_work = (
                    report.work.trial
                    == attempt.prepared.trials[attempt.trial_index].context
                )
            else:
                valid_work = False
            if not valid_work:
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(
                        code="STALE", message="interruption work mismatch"
                    ),
                )
            canonical = report.SerializeToString(deterministic=True)
            old = self.supervisor_state.interruption_ids.get(report.interruption_id)
            if old is not None:
                if old != canonical:
                    return pb.ReportReceipt(
                        result=pb.COMMAND_RESULT_REJECTED,
                        failure=pb.Failure(
                            code="CONFLICT", message="interruption ID changed payload"
                        ),
                    )
                return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
            if len(self.supervisor_state.interruption_ids) >= 256:
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(
                        code="CAPACITY", message="interruption accounting exhausted"
                    ),
                )
            self.supervisor_state.interruption_ids[report.interruption_id] = canonical
            self.control.errors.append(
                pb.ErrorReport(
                    error_id=report.interruption_id,
                    source=report.supervisor,
                    work=report.work,
                    occurred_monotonic_ns=report.issued_monotonic_ns,
                    failure=report.reason,
                )
            )
            if len(self.control.errors) > 256:
                self.control.errors = self.control.errors[-256:]
            self.publisher.publish()
        self.spawn(
            self.interrupt(
                attempt, report.reason.message, issued_ns=report.issued_monotonic_ns
            )
        )
        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    def interrupt_request(
        self, attempt: Attempt, backend: BackendPort, reason: str
    ) -> svc.InterruptSessionRequest:
        request = svc.InterruptSessionRequest(
            issued_monotonic_ns=attempt.interruption_issued_ns,
            reason=pb.Failure(code="INTERRUPTED", message=reason),
        )
        request.command.CopyFrom(self.cleanup.backend_command(attempt, backend))
        return request

    async def finalize(
        self,
        attempt: Attempt,
        *,
        metadata_clean: bool = True,
        from_interrupt: bool = False,
    ) -> None:
        """Join the attempt's one finalization task, creating it on first use."""
        async with self.lifecycle.lock:
            if self.lifecycle.attempt is not attempt:
                return
            closure = attempt.closure
            if closure.task is None:
                if attempt.interrupted and not from_interrupt:
                    return  # the interruption owns finalization
                attempt.finalizing = True
                closure.task = self.spawn(self._finalize(attempt, metadata_clean))
            task = closure.task
        # A cancelled caller (e.g. the trial task) never cancels finalization.
        await asyncio.shield(task)

    async def _finalize(self, attempt: Attempt, metadata_clean: bool) -> None:
        async with self.lifecycle.lock:
            if self.lifecycle.session.phase != pb.SESSION_PHASE_FINALIZING:
                self.lifecycle.session.phase = pb.SESSION_PHASE_FINALIZING
                self.lifecycle.session.outcome = pb.SESSION_OUTCOME_COMPLETED
                self.publisher.publish()
            outcome = (
                pb.SessionOutcome.Name(self.lifecycle.session.outcome)
                .removeprefix("SESSION_OUTCOME_")
                .lower()
            )
            if not attempt.finalization_deadline_ns:
                attempt.finalization_deadline_ns = (
                    self.clock() + self.limit_state.current.setup_cancel_ns
                )
            cleanup_deadline = attempt.finalization_deadline_ns
        clean = metadata_clean
        if attempt.paired:
            try:
                if self.spikeglx is None or not await asyncio.wait_for(
                    self.spikeglx.stop_expected_run(),
                    max(0, (cleanup_deadline - self.clock()) / 1e9),
                ):
                    clean = False
                else:
                    attempt.spikeglx_stopped = True
                    await self.metadata.log_event(
                        attempt,
                        "spikeglx_stopped",
                        details={"run_name": attempt.prepared.spikeglx.run_name},
                    )
            except Exception:
                clean = False
        if attempt.writer is not None:
            # The receipt for every accepted late Finished is paired with an owned
            # recovery event task before releasing the state lock. Close that
            # admission gate and join those writes before sealing the writer.
            async with self.lifecycle.lock:
                attempt.recovery_log_closed = True
                recovery_logs = tuple(attempt.recovery_log_tasks)
            if recovery_logs:
                try:
                    recovery_results = await asyncio.wait_for(
                        asyncio.gather(*recovery_logs, return_exceptions=True),
                        max(0, (cleanup_deadline - self.clock()) / 1e9),
                    )
                    if any(
                        isinstance(result, BaseException) for result in recovery_results
                    ):
                        clean = False
                except TimeoutError:
                    clean = False
            if attempt.recovery_log_failed or any(
                result.state
                in (pb.METADATA_PERSISTENCE_FAILED, pb.METADATA_PERSISTENCE_UNCONFIRMED)
                for result in self.metadata_state.results.values()
            ):
                clean = False
            try:
                await asyncio.wait_for(
                    self.metadata.log_event(attempt, "session_ended", outcome=outcome),
                    max(0, (cleanup_deadline - self.clock()) / 1e9),
                )
            except (StorageError, TimeoutError):
                clean = False
            try:
                sealed = await asyncio.wait_for(
                    asyncio.to_thread(
                        attempt.writer.seal,
                        max(0, (cleanup_deadline - self.clock()) / 1e9),
                    ),
                    max(0, (cleanup_deadline - self.clock()) / 1e9),
                )
            except (TimeoutError, StorageError, OSError):
                sealed = False
            if not sealed:
                clean = False
            else:
                attempt.writer_closed = True
        else:
            attempt.writer_closed = True
        try:
            requests = {
                name: self.cleanup.backend_command(attempt, backend)
                for name, backend in attempt.required.items()
            }
            attempt.cleanup_commands.update(
                {name: request.command_id for name, request in requests.items()}
            )
            fenced = (
                await self.cleanup.register_cleanup_fences(
                    attempt, requests, cleanup_deadline
                )
                if not self.lifecycle.authority_lost
                else False
            )
            clean = clean and fenced
            if fenced or self.lifecycle.authority_lost:
                results = await asyncio.wait_for(
                    asyncio.gather(
                        *(
                            backend.cleanup(
                                requests[name], deadline_ns=cleanup_deadline
                            )
                            for name, backend in attempt.required.items()
                        ),
                        return_exceptions=True,
                    ),
                    max(0, (cleanup_deadline - self.clock()) / 1e9),
                )
                if not all(
                    isinstance(result, pb.CommandAdmission)
                    and result.result == pb.COMMAND_RESULT_ACCEPTED
                    for result in results
                ):
                    clean = False
        except TimeoutError:
            clean = False
        clean = await self.cleanup.await_cleanups(attempt, cleanup_deadline) and clean
        if (
            attempt.reservation_registration_started
            and not attempt.reservation_registered
        ):
            clean = False
        if clean and not self.lifecycle.authority_lost:
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(attempt.reservation.complete),
                    max(0, (cleanup_deadline - self.clock()) / 1e9),
                )
                clean = await self.cleanup.release_reservation_pointer(
                    attempt, cleanup_deadline
                )
            except (StorageError, OSError, TimeoutError):
                clean = False
        async with self.lifecycle.lock:
            self.lifecycle.session.phase = pb.SESSION_PHASE_ENDED
            self.lifecycle.session.cleanup_confirmed = (
                clean and not self.lifecycle.authority_lost
            )
            if not clean:
                self.lifecycle.session.outcome = pb.SESSION_OUTCOME_INTERRUPTED
            if attempt.incidents is not None:
                try:
                    attempt.incidents.end_session()
                except IncidentCapacityError:
                    self.lifecycle.session.outcome = pb.SESSION_OUTCOME_INTERRUPTED
                    self.control.warnings.append(
                        pb.Warning(
                            warning_id=str(uuid.uuid4()),
                            component="incidents",
                            message="terminal incident accounting capacity exhausted",
                        )
                    )
            for prompt_id, (prompt, owner) in list(
                self.incident_state.incident_prompts.items()
            ):
                if owner is attempt and "acknowledge" not in prompt.permitted_choices:
                    self.incident_state.incident_prompts.pop(prompt_id)
            attempt.closure.done = True
            attempt.closure.clean = clean
            self.cleanup.settle_operations(attempt)
            self.publisher.publish()
