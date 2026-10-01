"""Registered renderer worker discovery and direct safety commands (V01/E08)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.clock import host_time_ns
from cephvr.supervisor.ports import SupervisorOutbound
from cephvr.supervisor.receipts import require_accepted
from cephvr.supervisor.registration import RegistrationCoordinator
from cephvr.supervisor.registry import LIVE_PHASES, LaunchRegistry
from cephvr.supervisor.worker_context import launch_work_matches
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus


class VisualStimulusWorkerControl:
    """Operate only the exact registered Visual Stimulus renderer owned by this generation."""

    def __init__(
        self,
        *,
        registration: RegistrationCoordinator,
        registry: LaunchRegistry,
        outbound: SupervisorOutbound,
        issuer: types.ProcessIdentity,
        interrupt_commands: dict[tuple[str, str], str],
        cleanup_commands: dict[tuple[str, str], str],
    ) -> None:
        self.registration = registration
        self.registry = registry
        self.outbound = outbound
        self.issuer = types.ProcessIdentity.FromString(
            issuer.SerializeToString(deterministic=True)
        )
        self.interrupt_commands = interrupt_commands
        self.cleanup_commands = cleanup_commands
        self.retained_commands: dict[str, visual_stimulus.WorkerCommand] = {}

    def registered_workers(
        self, work: types.WorkContext
    ) -> list[tuple[wire.LaunchState, visual_stimulus.WorkerContext]]:
        participant = next(
            (
                p
                for p in (
                    self.registration.state.context.required_participants
                    if self.registration.state.context
                    else ()
                )
                if p.backend_name == "visual_stimulus"
            ),
            None,
        )
        if participant is None:
            return []
        result = []
        for launch in self.registry.states(tolerant=True):
            plan = launch.plan
            if (
                plan.owner.generation != participant.backend_generation
                or plan.owner.role != "visual_stimulus"
                or plan.child.role != "visual_stimulus_renderer"
                or launch.phase not in LIVE_PHASES
            ):
                continue
            # The persistent V19 renderer may have been launched before Setup.
            if plan.HasField("work") and not launch_work_matches(plan, work):
                continue
            context = visual_stimulus.WorkerContext(
                worker=plan.child, owner=plan.owner, work=work
            )
            result.append((launch, context))
        return result

    def _command(
        self,
        worker: visual_stimulus.WorkerContext,
        deadline_ns: int,
        command_id: str | None = None,
    ) -> visual_stimulus.WorkerCommand:
        resolved = command_id or str(uuid4())
        if resolved in self.retained_commands:
            return visual_stimulus.WorkerCommand.FromString(
                self.retained_commands[resolved].SerializeToString()
            )
        command = visual_stimulus.WorkerCommand(
            command_id=resolved,
            issuer=self.issuer,
            target=worker,
            parent_operation=types.OperationContext(command_id=resolved),
            deadline_monotonic_ns=deadline_ns,
        )
        self.retained_commands[resolved] = command
        return visual_stimulus.WorkerCommand.FromString(command.SerializeToString())

    async def _current_context(
        self,
        launch: wire.LaunchState,
        worker: visual_stimulus.WorkerContext,
        deadline_ns: int,
    ) -> visual_stimulus.WorkerContext:
        state = await self.outbound.get_visual_stimulus_worker_state(
            launch, visual_stimulus.WorkerQuery(target=worker), deadline_ns=deadline_ns
        )
        observed_work = state.context.work
        requested_kind = worker.work.WhichOneof("work")
        observed_kind = observed_work.WhichOneof("work")
        same_work = (
            requested_kind is None
            or observed_kind is None
            or observed_work == worker.work
            or (
                requested_kind == "trial"
                and observed_kind == "session"
                and worker.work.trial.session == observed_work.session
            )
            or (
                requested_kind == "session"
                and observed_kind == "trial"
                and worker.work.session == observed_work.trial.session
            )
        )
        if (
            state.context.worker != worker.worker
            or state.context.owner != worker.owner
            or not same_work
        ):
            raise RuntimeError(
                "Visual Stimulus worker state differs from its exact registered launch"
            )
        return visual_stimulus.WorkerContext.FromString(
            state.context.SerializeToString(deterministic=True)
        )

    async def interrupt_worker(
        self,
        launch: wire.LaunchState,
        worker: visual_stimulus.WorkerContext,
        report: wire.InterruptionReport,
        deadline_ns: int,
    ) -> None:
        worker = await self._current_context(launch, worker, deadline_ns)
        key = (worker.worker.role, worker.worker.generation)
        command_id = self.interrupt_commands.setdefault(key, str(uuid4()))
        request = visual_stimulus.WorkerStop(
            command=self._command(worker, deadline_ns, command_id),
            issued_monotonic_ns=report.issued_monotonic_ns,
            cause=report.reason,
        )
        admission = await self.outbound.interrupt_visual_stimulus_worker(
            launch, request, deadline_ns=deadline_ns
        )
        require_accepted(admission, "Visual Stimulus worker interruption")

    async def cleanup_worker(
        self,
        launch: wire.LaunchState,
        worker: visual_stimulus.WorkerContext,
        deadline_ns: int,
    ) -> None:
        worker = await self._current_context(launch, worker, deadline_ns)
        key = (worker.worker.role, worker.worker.generation)
        command_id = self.cleanup_commands.setdefault(key, str(uuid4()))
        request = self._command(worker, deadline_ns, command_id)
        admission = await self.outbound.cleanup_visual_stimulus_worker(
            launch, request, deadline_ns=deadline_ns
        )
        require_accepted(admission, "Visual Stimulus worker cleanup")
        # Admission is not executor completion. Reconcile the retained operation
        # within its original deadline without dispatching another cleanup.
        deadline_ns = min(deadline_ns, request.deadline_monotonic_ns)
        while True:
            state = await self.outbound.get_visual_stimulus_worker_state(
                launch,
                visual_stimulus.WorkerQuery(target=worker, command_id=command_id),
                deadline_ns=deadline_ns,
            )
            if state.HasField("operation") and state.operation.complete:
                break
            remaining = (deadline_ns - host_time_ns()) / 1e9
            if remaining <= 0:
                raise TimeoutError(
                    "Visual Stimulus cleanup missed its original deadline"
                )
            await asyncio.sleep(min(0.01, remaining))
        if (
            state.context.worker != worker.worker
            or state.context.owner != worker.owner
            or state.context.work != worker.work
            or not state.HasField("command_known")
            or not state.command_known
            or not state.HasField("operation")
            or state.operation.context.command_id != command_id
            or not state.operation.complete
            or not state.operation.HasField("succeeded")
            or not state.operation.succeeded
        ):
            raise RuntimeError(
                "Visual Stimulus worker cleanup lacks exact retained success evidence"
            )

    async def shutdown_worker(
        self,
        launch: wire.LaunchState,
        worker: visual_stimulus.WorkerContext,
        deadline_ns: int,
    ) -> None:
        worker = await self._current_context(launch, worker, deadline_ns)
        request = self._command(worker, deadline_ns)
        admission = await self.outbound.shutdown_visual_stimulus_worker(
            launch, request, deadline_ns=deadline_ns
        )
        require_accepted(admission, "Visual Stimulus worker shutdown")
