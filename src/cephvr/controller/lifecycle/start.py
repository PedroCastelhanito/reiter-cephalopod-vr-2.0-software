"""E05 Start activation and first trial release preconditions."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Mapping
from typing import Any

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.operations import ControlOperations
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.device.spikeglx_monitor import SpikeGLXProgressMonitor
from cephvr.controller.lifecycle.interruption import InterruptionWorkflow
from cephvr.controller.lifecycle.preparation_context import PreparationContext
from cephvr.controller.lifecycle.trials import TrialExecution
from cephvr.controller.metadata.coordination import MetadataCoordinator
from cephvr.controller.metadata.documents import (
    active_configuration_document,
    message_dict,
)
from cephvr.controller.metadata.writer import MetadataWriter
from cephvr.controller.ports import SpikeGLXPort, SupervisorPort
from cephvr.controller.state import Attempt, ControlState, LifecycleState, LimitsState


class StartActivation:
    """Freeze and sync session metadata before activated trial work."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        control: ControlState,
        limit_state: LimitsState,
        clock: Callable[[], int],
        publisher: SnapshotPublisher,
        control_operations: ControlOperations,
        metadata: MetadataCoordinator,
        preparation_context: PreparationContext,
        trials: TrialExecution,
        interruption: InterruptionWorkflow,
        supervisor: SupervisorPort | None,
        spikeglx: SpikeGLXPort | None,
        spikeglx_monitor: SpikeGLXProgressMonitor | None,
        schema_factory: Callable[[pb.PreparedSession], dict[str, object]] | None,
        output_planner: Callable[
            [pb.PreparedSession, Mapping[str, pb.ReadyReport]], list[pb.OutputPlan]
        ]
        | None,
        generation: str,
        spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]],
    ) -> None:
        self.lifecycle = lifecycle
        self.control = control
        self.limit_state = limit_state
        self.clock = clock
        self.publisher = publisher
        self.control_operations = control_operations
        self.metadata = metadata
        self.preparation_context = preparation_context
        self.trials = trials
        self.interruption = interruption
        self.supervisor = supervisor
        self.spikeglx = spikeglx
        self.spikeglx_monitor = spikeglx_monitor
        self.schema_factory = schema_factory
        self.output_planner = output_planner
        self.generation = generation
        self.spawn = spawn

    async def start_session(self, command: svc.OperatorCommand) -> pb.CommandAdmission:
        command_id = command.operator.command_id
        async with self.lifecycle.lock:
            error = self.control_operations.authorized(command, targets_work=True)
            attempt = self.lifecycle.attempt
            if (
                error
                or self.lifecycle.startup_blocker
                or attempt is None
                or self.lifecycle.session.phase != pb.SESSION_PHASE_READY
            ):
                return self.control_operations.admission(
                    command_id,
                    error=error
                    or self.lifecycle.startup_blocker
                    or "Start requires this attempt's Ready state",
                )
            if (
                attempt.prepared.configuration_revision
                != self.control_operations.configuration_state.revision
                or attempt.cancel_requested
            ):
                return self.control_operations.admission(
                    command_id,
                    error="Start requires the Ready configuration revision to be current",
                )
            if self.schema_factory is None or self.output_planner is None:
                return self.control_operations.admission(
                    command_id, error="writer schema or output contract unavailable"
                )
            self.lifecycle.session.phase = pb.SESSION_PHASE_STARTING
            self.control.operations[command_id] = pb.OperationState(
                context=pb.OperationContext(command_id=command_id),
                command="StartSession",
                work=pb.WorkContext(session=attempt.context),
                progress="freezing configuration and metadata",
            )
            attempt.closure.start_command_id = command_id
            self.publisher.publish()
            attempt.start_task = self.spawn(self.run_start(attempt, command_id))
            return self.control_operations.admission(command_id)

    async def run_start(self, attempt: Attempt, command_id: str) -> None:
        try:
            start_deadline_ns = self.clock() + self.limit_state.current.setup_ns
            if attempt.cancel_requested:
                raise RuntimeError("attempt cancelled")
            schema = (
                self.schema_factory(attempt.prepared) if self.schema_factory else None
            )
            if not isinstance(schema, dict) or schema.get("schema_version") != 1:
                raise RuntimeError("versioned writer schema unavailable")
            writer = MetadataWriter(
                attempt.reservation.protocol_directory,
                max_operations=self.limit_state.current.max_metadata_operations,
                max_bytes=self.limit_state.current.max_metadata_bytes,
                clock=self.clock,
                session_id=attempt.context.session_id,
            )
            attempt.writer = writer
            session_document: dict[str, object] = {
                "schema_version": 1,
                "session_id": attempt.context.session_id,
                "controller_generation": self.generation,
                "session_setup_wall_time": attempt.prepared.anchor_wall_time,
                "session_setup_monotonic_ns": attempt.prepared.anchor_monotonic_ns,
                "local_timezone": attempt.prepared.local_timezone,
                "configuration_revision": attempt.prepared.configuration_revision,
                "configuration": active_configuration_document(
                    attempt.prepared.configuration
                ),
                "trials": [message_dict(plan) for plan in attempt.prepared.trials],
                "outputs": [message_dict(plan) for plan in attempt.prepared.outputs],
            }
            if attempt.paired:
                session_document["spikeglx"] = message_dict(attempt.prepared.spikeglx)
            # From the first write on, an unactivated cancel keeps the files (E06).
            attempt.closure.metadata_written = True
            await self.metadata.persist(
                attempt, "SESSION_CONFIG.json", "create_json", session_document
            )
            await self.metadata.persist(attempt, "SCHEMA.json", "create_json", schema)
            if self.clock() >= start_deadline_ns:
                raise TimeoutError(
                    "Start preparation deadline elapsed before registration"
                )
            if self.supervisor is None:
                raise RuntimeError("supervisor unavailable")
            registration = await asyncio.wait_for(
                self.supervisor.register_context(
                    self.preparation_context.registration(attempt, command_id)
                ),
                max(
                    0,
                    min(
                        start_deadline_ns - self.clock(),
                        self.limit_state.current.registration_ns,
                    )
                    / 1e9,
                ),
            )
            if (
                registration.admission.result != pb.COMMAND_RESULT_ACCEPTED
                or registration.registered.work.session != attempt.context
            ):
                raise RuntimeError("Start registration unconfirmed")
            async with self.lifecycle.lock:
                if self.lifecycle.attempt is not attempt or attempt.cancel_requested:
                    raise RuntimeError("attempt retired before activation")
                attempt.activated = True
                self.lifecycle.session.activated = True
                self.publisher.publish()
            await self.metadata.log_event(attempt, "session_started")
            if attempt.paired:
                if self.clock() >= start_deadline_ns:
                    raise TimeoutError("Start writing gate deadline elapsed")
                if (
                    self.spikeglx is None
                    or not await asyncio.wait_for(
                        self.spikeglx.verify_before_start(start_deadline_ns),
                        max(0, (start_deadline_ns - self.clock()) / 1e9),
                    )
                    or not await asyncio.wait_for(
                        self.spikeglx.start_and_verify_writing(start_deadline_ns),
                        max(0, (start_deadline_ns - self.clock()) / 1e9),
                    )
                ):
                    raise RuntimeError("SpikeGLX writing gate failed")
                await self.metadata.log_event(
                    attempt,
                    "spikeglx_started",
                    details={"run_name": attempt.prepared.spikeglx.run_name},
                )
            async with self.lifecycle.lock:
                if (
                    self.lifecycle.attempt is not attempt
                    or attempt.interrupted
                    or self.lifecycle.session.phase != pb.SESSION_PHASE_STARTING
                ):
                    raise RuntimeError("Start retired before Running transition")
                self.lifecycle.session.phase = pb.SESSION_PHASE_RUNNING
                self.control_operations.complete_operation(
                    command_id, success=True, progress="session activated"
                )
                self.publisher.publish()
            if attempt.paired and self.spikeglx_monitor is not None:
                self.spawn(self.spikeglx_monitor.run(attempt))
            attempt.trial_task = self.spawn(self.trials.run_trials(attempt))
        except Exception as exc:
            async with self.lifecycle.lock:
                self.control_operations.complete_operation(
                    command_id, success=False, progress="Start failed", error=str(exc)
                )
                self.publisher.publish()
            await self.interruption.interrupt(attempt, f"Start failed: {exc}")
