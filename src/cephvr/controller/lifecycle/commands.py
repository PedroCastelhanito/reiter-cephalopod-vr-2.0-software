"""E05/E06 operator stop, abort, new-session and application shutdown commands."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, Literal

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.operations import ControlOperations
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.lifecycle.cleanup import CleanupWorkflow
from cephvr.controller.lifecycle.interruption import InterruptionWorkflow
from cephvr.controller.ports import SupervisorPort
from cephvr.controller.projections import ProjectionStore
from cephvr.controller.state import (
    Attempt,
    ConfigurationState,
    ControlState,
    LifecycleState,
    LimitsState,
    MetadataState,
)

_ABORT_UNAVAILABLE = "Abort unavailable"


class SessionCommands:
    """Apply accepted operator commands to the current session authority."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        configuration: ConfigurationState,
        control: ControlState,
        metadata_state: MetadataState,
        limit_state: LimitsState,
        cleanup: CleanupWorkflow,
        interruption: InterruptionWorkflow,
        publisher: SnapshotPublisher,
        operations: ControlOperations,
        projections: ProjectionStore,
        supervisor: SupervisorPort | None,
        generation: str,
        supervisor_generation: str,
        clock: Callable[[], int],
        spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]],
    ) -> None:
        self.lifecycle = lifecycle
        self.configuration_state = configuration
        self.control = control
        self.metadata_state = metadata_state
        self.limit_state = limit_state
        self.cleanup = cleanup
        self.interruption = interruption
        self.publisher = publisher
        self.control_operations = operations
        self.projections = projections
        self.supervisor = supervisor
        self.generation = generation
        self.supervisor_generation = supervisor_generation
        self.clock = clock
        self.spawn = spawn

    async def stop_after_trial(
        self, command: svc.OperatorCommand, *, cancel: bool = False
    ) -> pb.CommandAdmission:
        async with self.lifecycle.lock:
            error = self.control_operations.authorized(command, targets_work=True)
            phase = self.lifecycle.session.phase
            attempt = self.lifecycle.attempt
            starting = (
                not cancel
                and attempt is not None
                and phase == pb.SESSION_PHASE_STARTING
            )
            if error or not (phase == pb.SESSION_PHASE_RUNNING or starting):
                return self.control_operations.admission(
                    command.operator.command_id, error=error or "no running session"
                )
            if starting and attempt is not None and not attempt.activated:
                # E06: before activation Stop cancels the pending Start like Abort.
                attempt.abort_command_ids.append(command.operator.command_id)
                self.control_operations.operation(
                    command.operator.command_id,
                    "StopAfterTrial",
                    attempt=attempt,
                    progress="pending start cancelled",
                )
                self.spawn(
                    self.interruption.interrupt(
                        attempt, "operator Stop before session activation"
                    )
                )
                return self.control_operations.admission(command.operator.command_id)
            if (
                cancel
                and self.lifecycle.trial.HasField("scheduled_end_monotonic_ns")
                and self.clock() > self.lifecycle.trial.scheduled_end_monotonic_ns
            ):
                return self.control_operations.admission(
                    command.operator.command_id,
                    error="stop withdrawal is past trial boundary",
                )
            self.lifecycle.session.stop_after_trial = not cancel
            if cancel and attempt is not None:
                self.interruption.cancel_spikeglx_stop(attempt)
            if not cancel and attempt is not None and attempt.end_ns:
                self.interruption.arm_spikeglx_stop(
                    attempt,
                    stopped_deadline_ns=(
                        attempt.end_ns + self.limit_state.current.stop_evidence_ns
                    ),
                    final_trial=False,
                )
            self.control_operations.operation(
                command.operator.command_id,
                "CancelStopAfterTrial" if cancel else "StopAfterTrial",
                attempt=self.lifecycle.attempt,
                progress="stop preference updated",
                complete=True,
                succeeded=True,
            )
            self.publisher.publish()
            return self.control_operations.admission(command.operator.command_id)

    def _safety_refusal(
        self, command: svc.OperatorCommand, kind: Literal["abort", "shutdown"]
    ) -> str | None:
        """Refusal text for an Abort or Shutdown command; call with the lock held."""
        error = self.control_operations.authorized(command, safety=kind)
        if kind == "abort":
            if (
                error
                or self.lifecycle.attempt is None
                or self.lifecycle.session.phase
                not in (pb.SESSION_PHASE_STARTING, pb.SESSION_PHASE_RUNNING)
            ):
                return error or _ABORT_UNAVAILABLE
            return None
        if error or self.lifecycle.session.shutdown_requested:
            return error or "shutdown already requested"
        return None

    async def safety_precondition(
        self, command: svc.OperatorCommand, kind: Literal["abort", "shutdown"]
    ) -> str | None:
        async with self.lifecycle.lock:
            return self._safety_refusal(command, kind)

    async def abort_now(self, command: svc.OperatorCommand) -> pb.CommandAdmission:
        async with self.lifecycle.lock:
            refusal = self._safety_refusal(command, "abort")
            attempt = self.lifecycle.attempt
            if refusal is not None or attempt is None:
                return self.control_operations.admission(
                    command.operator.command_id, error=refusal or _ABORT_UNAVAILABLE
                )
            attempt.abort_command_ids.append(command.operator.command_id)
            self.control_operations.operation(
                command.operator.command_id,
                "AbortNow",
                attempt=attempt,
                progress="interruption in progress",
                safety="abort",
            )
            self.spawn(self.interruption.interrupt(attempt, "operator Abort now"))
            return self.control_operations.admission(command.operator.command_id)

    async def new_session(self, command: svc.OperatorCommand) -> pb.CommandAdmission:
        async with self.lifecycle.lock:
            error = self.control_operations.authorized(command, targets_work=True)
            if (
                error
                or self.lifecycle.session.phase != pb.SESSION_PHASE_ENDED
                or not self.lifecycle.session.cleanup_confirmed
            ):
                return self.control_operations.admission(
                    command.operator.command_id,
                    error=error or "New session requires confirmed cleanup",
                )
            self.lifecycle.attempt = None
            self.lifecycle.session = pb.SessionState(
                phase=pb.SESSION_PHASE_CONFIGURATION, cleanup_confirmed=True
            )
            self.lifecycle.trial = pb.TrialState(phase=pb.TRIAL_PHASE_PENDING)
            self.projections.set_scope(
                pb.WorkContext(), self.configuration_state.revision
            )
            self.metadata_state.results.clear()
            self.metadata_state.latest_synced.clear()
            self.control_operations.operation(
                command.operator.command_id,
                "NewSession",
                progress="new configuration session created",
                complete=True,
                succeeded=True,
            )
            self.publisher.publish()
            return self.control_operations.admission(command.operator.command_id)

    async def shutdown_application(
        self, command: svc.OperatorCommand
    ) -> pb.CommandAdmission:
        async with self.lifecycle.lock:
            refusal = self._safety_refusal(command, "shutdown")
            if refusal is not None:
                return self.control_operations.admission(
                    command.operator.command_id, error=refusal
                )
            attempt = self.lifecycle.attempt
            issued_ns = self.clock()
            self.lifecycle.shutdown_intent_ns = issued_ns
            self.lifecycle.session.shutdown_requested = True
            self.control_operations.operation(
                command.operator.command_id,
                "ShutdownApplication",
                attempt=attempt,
                progress="shutdown intent retained",
                safety="shutdown",
            )
            if attempt is not None:
                attempt.shutdown_command_ids.append(command.operator.command_id)
                attempt.closure.handoff_pending.add(command.operator.command_id)
            self.publisher.publish()
            request = svc.ApplicationShutdownRequest(
                command_id=command.operator.command_id,
                controller=pb.ProcessIdentity(
                    role="controller", generation=self.generation
                ),
                supervisor=pb.ProcessIdentity(
                    role="supervisor", generation=self.supervisor_generation
                ),
                operator=command.operator,
                controller_operation=pb.OperationContext(
                    command_id=command.operator.command_id
                ),
                issued_monotonic_ns=issued_ns,
            )
            if attempt is not None:
                request.work.session.CopyFrom(attempt.context)
        # E08: hand off intent before any cleanup; Abort-now interruption then starts
        # at once and runs beside the handoff.
        self.spawn(self._hand_off_shutdown(request, attempt))
        if attempt is not None:
            if attempt.activated or attempt.start_task is not None:
                self.spawn(self.interruption.interrupt(attempt, "application shutdown"))
            else:
                async with self.lifecycle.lock:
                    attempt.cancel_requested = True
                    attempt.closure.reason = attempt.closure.reason or (
                        "application shutdown"
                    )
                if attempt.handoff is not None:
                    attempt.handoff.retire()
                self.spawn(self.cleanup.cancel_attempt(attempt))
        return self.control_operations.admission(command.operator.command_id)

    async def _hand_off_shutdown(
        self, request: svc.ApplicationShutdownRequest, attempt: Attempt | None
    ) -> None:
        """Record the supervisor handoff result; complete once closure is known."""
        command_id = request.command_id
        failure = ""
        try:
            if self.supervisor is None:
                raise RuntimeError("no supervisor handoff available")
            receipt = await asyncio.wait_for(
                self.supervisor.request_shutdown(request),
                self.limit_state.current.registration_ns / 1e9,
            )
            if receipt.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(
                    receipt.failure.message or "supervisor rejected shutdown"
                )
        except Exception as exc:
            failure = str(exc) or type(exc).__name__
        async with self.lifecycle.lock:
            if failure:
                self.control.add_warning(
                    "shutdown", f"supervisor handoff unconfirmed: {failure}"
                )
            if attempt is None:
                self.control_operations.complete_operation(
                    command_id,
                    success=not failure,
                    progress="shutdown handoff accepted"
                    if not failure
                    else "shutdown handoff failed",
                    error=f"shutdown handoff failed: {failure}" if failure else "",
                )
            else:
                attempt.closure.handoff_pending.discard(command_id)
                if failure:
                    attempt.closure.handoff_failures[command_id] = failure
                self.cleanup.settle_operations(attempt)
            self.publisher.publish()
