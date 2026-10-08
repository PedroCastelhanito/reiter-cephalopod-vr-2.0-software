"""Visual Stimulus coordinator assembly and explicit lifecycle operations (V01/E08)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from uuid import uuid4

from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger
from cephvr.visual_stimulus.coordinator.commands import (
    bind_command,
    validate,
    wait_schedule_completion,
)
from cephvr.visual_stimulus.coordinator.incidents import validate_incident
from cephvr.visual_stimulus.coordinator.ports import PeerPort
from cephvr.visual_stimulus.coordinator.projection import project
from cephvr.visual_stimulus.coordinator.recipes import RecipeOwner
from cephvr.visual_stimulus.coordinator.reports import Reports
from cephvr.visual_stimulus.coordinator.state import Identity, State
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus


class VisualStimulusCoordinatorRuntime:
    def __init__(
        self,
        *,
        identity: Identity,
        worker: PeerPort,
        controller: PeerPort,
        supervisor: PeerPort,
        ledger: CommandLedger,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity, self.worker, self.controller, self.supervisor = (
            identity,
            worker,
            controller,
            supervisor,
        )
        self.ledger, self.clock = ledger, clock
        self.state = State()
        self.reports = Reports(
            identity, self.state, ledger, controller, supervisor, clock
        )
        self.shutdown_requested = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.recipes = RecipeOwner(
            identity, self.state, worker, supervisor, self.cancelled, clock, ledger
        )
        self.reports.release_result = self.recipes.release_result
        self.lock = asyncio.Lock()
        self.recovery_deadline_ns: int | None = None

    def validate_command(self, method: str, request: Message) -> None:
        validate(self.identity, self.state, method, request)

    async def execute(
        self, method: str, request: Message, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        self.validate_command(method, request)
        if isinstance(request, wire.IncidentScopeRequest):
            return await self.apply_incident(request, deadline_ns)
        async with self.lock:
            forwarded, link = bind_command(
                self.identity, self.state, method, request, deadline_ns
            )
            self.state.links[link.child.command_id] = link
            if isinstance(request, wire.SetupSessionRequest):
                if self.state.cleanup is not None:
                    self.state.resources.clear()
                    self.state.prepared.clear()
                    self.state.recipe_results.clear()
                    self.state.incident_revisions.clear()
                    self.state.schedule = None
                    self.state.release = None
                    self.recovery_deadline_ns = None
                self.state.setup = wire.SetupSessionRequest.FromString(
                    request.SerializeToString()
                )
                self.state.interrupted = False
                self.state.cleanup = None
                self.state.sealed = False
                self.cancelled.clear()
            elif method in {"OpenDisplayCalibration", "CloseDisplayCalibration"}:
                if self.state.setup is not None:
                    raise ValueError(
                        "display calibration is unavailable during a session"
                    )
                self.state.interrupted = False
                self.cancelled.clear()
            if method in {"InterruptSession", "CancelSetup", "Cleanup", "Shutdown"}:
                self.state.interrupted = True
                self.cancelled.set()
                self.recipes.wake.set()
                if self.state.active_trial is not None:
                    self.recipes.cancel_trial(self.state.active_trial)
                self.recovery_deadline_ns = min(
                    self.recovery_deadline_ns or deadline_ns, deadline_ns
                )
            if isinstance(request, wire.PrepareTrialRequest):
                self.state.active_trial = request.plan.context.trial_id
            if isinstance(request, wire.ScheduleTrialRequest):
                self.state.schedule = wire.ScheduleTrialRequest.FromString(
                    request.SerializeToString()
                )
            if isinstance(request, wire.ReleaseTrialRequest):
                self.state.release = wire.ReleaseTrialRequest.FromString(
                    request.SerializeToString()
                )
            if (
                method in {"StopTrial", "AbortTrial"}
                and self.state.active_trial is not None
            ):
                self.recipes.cancel_trial(self.state.active_trial)
        if isinstance(request, wire.SetupSessionRequest):
            async with self.reports.catalogue_lock:
                await self.recipes.prepare(request, deadline_ns)
        if isinstance(request, wire.ScheduleTrialRequest):
            self.recipes.scheduled(request)
        if isinstance(request, wire.ReleaseTrialRequest):
            assert isinstance(forwarded, visual_stimulus.WorkerRelease)
            scheduled = self.state.links[forwarded.schedule_operation.command_id]
            await wait_schedule_completion(
                self.ledger,
                scheduled.parent.command_id,
                scheduled.parent.work,
                min(deadline_ns, scheduled.deadline_ns),
                self.clock,
            )
        result = await self.worker.command(
            "StopTrial" if method == "AbortTrial" else method,
            forwarded,
            deadline_ns=deadline_ns,
        )
        if result.result != pb.COMMAND_RESULT_ACCEPTED:
            return pb.CommandAdmission(
                result=result.result,
                command_id=link.parent.command_id,
                failure=result.failure,
            )
        if isinstance(request, wire.ReleaseTrialRequest):
            if self.state.setup is None:
                raise RuntimeError("Release has no retained Setup")
            self.recipes.start(
                request,
                request.start_monotonic_ns
                + self.state.setup.plan.policies.start_evidence_allowance_ns,
                deadline_ns,
            )
        return pb.CommandAdmission(
            result=pb.COMMAND_RESULT_ACCEPTED, command_id=link.parent.command_id
        )

    async def report(
        self, method: str, request: Message, *, ingress_ns: int
    ) -> pb.ReportReceipt:
        if method == "ReportWorkerHeartbeat" and isinstance(
            request, pb.HeartbeatReport
        ):
            await self.reports.heartbeat(request, ingress_ns)
        elif method == "ReportWorkerOperation" and isinstance(
            request, visual_stimulus.WorkerOperation
        ):
            await self.reports.operation(request)
            link = self.state.links.get(request.operation.context.command_id)
            if (
                link is not None
                and link.method == "Shutdown"
                and request.operation.complete
            ):
                self.shutdown_requested.set()
        elif method == "ReportDisplay" and isinstance(
            request, pb.VisualStimulusDisplayView
        ):
            await self.reports.display(request)
        elif method == "ReportWorkerLifecycle" and isinstance(
            request, visual_stimulus.WorkerLifecycle
        ):
            kind = request.report.WhichOneof("report")
            if kind == "finished":
                task = self.recipes.tasks.get(
                    request.report.finished.context.work.trial.trial_id
                )
                if task is not None:
                    await asyncio.shield(task)
            if kind == "cleanup":
                link = self.state.links.get(request.report.cleanup.operation.command_id)
                if link is None:
                    raise ValueError("cleanup command unknown")
                await self.recipes.drain(link.deadline_ns)
                self.recipes.cleanup_results()
            await self.reports.lifecycle(request)
        else:
            raise ValueError("unsupported Visual Stimulus report")
        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    async def query(self, method: str, request: Message) -> Message:
        return project(self.identity, self.state, self.ledger, request)

    async def apply_incident(
        self, request: wire.IncidentScopeRequest, deadline_ns: int
    ) -> pb.CommandAdmission:
        continuing = validate_incident(self.state, request)
        self.state.incident_revisions[request.incident.incident_id] = (
            request.incident.revision
        )
        if not continuing:
            stop = wire.InterruptSessionRequest(
                command=request.command,
                issued_monotonic_ns=self.clock(),
                reason=pb.Failure(
                    code="VISUAL_STIMULUS_INCIDENT",
                    message=request.incident.consequence
                    or "Visual Stimulus scope cannot safely continue",
                ),
            )
            return await self.execute("InterruptSession", stop, deadline_ns=deadline_ns)
        operation = pb.OperationState(
            context=pb.OperationContext(command_id=request.command.command_id),
            command="ApplyIncidentScope",
            work=request.command.work,
            complete=True,
            succeeded=True,
        )
        self.ledger.complete_executor(
            request.command.command_id, operation.SerializeToString(), self.clock()
        )
        await self.controller.receipt(
            "ReportLifecycle",
            pb.LifecycleReport(
                operation=pb.BackendOperationReport(
                    source=self.identity.backend, operation=operation
                )
            ),
            deadline_ns=deadline_ns,
        )
        return pb.CommandAdmission(
            result=pb.COMMAND_RESULT_ACCEPTED, command_id=request.command.command_id
        )

    async def authority_lost(self, reason: str, deadline_ns: int) -> None:
        self.recovery_deadline_ns = min(
            self.recovery_deadline_ns or deadline_ns, deadline_ns
        )
        deadline_ns = self.recovery_deadline_ns
        self.state.interrupted = True
        self.cancelled.set()
        self.recipes.interrupt()
        work = pb.WorkContext()
        if self.state.setup is not None:
            work.session.CopyFrom(self.state.setup.plan.context)
        command = wire.BackendCommand(
            command_id=str(uuid4()),
            issuer=self.identity.process,
            target=self.identity.backend,
            work=work,
        )
        self.ledger.admit(
            command.command_id,
            command.SerializeToString(),
            self.clock(),
            work_key=command.command_id,
            deadline_ns=deadline_ns,
            priority=True,
        )
        self.ledger.complete(
            command.command_id,
            pb.CommandAdmission(
                result=pb.COMMAND_RESULT_ACCEPTED, command_id=command.command_id
            ).SerializeToString(),
            self.clock(),
        )
        forwarded, link = bind_command(
            self.identity, self.state, "Shutdown", command, deadline_ns
        )
        self.state.links[link.child.command_id] = link
        try:
            result = await self.worker.command(
                "Shutdown", forwarded, deadline_ns=deadline_ns
            )
            if result.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(result.failure.message)
            async with asyncio.timeout(max(0, (deadline_ns - self.clock()) / 1e9)):
                await self.shutdown_requested.wait()
        except Exception as exc:
            try:
                await self.supervisor.receipt(
                    "ReportError",
                    pb.ErrorReport(
                        error_id=str(uuid4()),
                        source=self.identity.process,
                        work=work,
                        occurred_monotonic_ns=self.clock(),
                        failure=pb.Failure(
                            code="VISUAL_STIMULUS_AUTHORITY_LOSS",
                            message=f"{reason}; cleanup unconfirmed: {exc}"[:2048],
                        ),
                    ),
                    deadline_ns=deadline_ns,
                )
            finally:
                self.shutdown_requested.set()

    async def failed_command(
        self,
        method: str,
        command: wire.BackendCommand,
        outcome: pb.OperationState,
        deadline_ns: int,
    ) -> None:
        self.state.interrupted = True
        self.cancelled.set()
        self.recipes.interrupt()
        await asyncio.gather(
            self.controller.receipt(
                "ReportLifecycle",
                pb.LifecycleReport(
                    operation=pb.BackendOperationReport(
                        source=self.identity.backend, operation=outcome
                    )
                ),
                deadline_ns=deadline_ns,
            ),
            self.supervisor.receipt(
                "ReportError",
                pb.ErrorReport(
                    error_id=str(uuid4()),
                    source=self.identity.process,
                    work=command.work,
                    operation=outcome.context,
                    occurred_monotonic_ns=self.clock(),
                    failure=outcome.failure,
                ),
                deadline_ns=deadline_ns,
            ),
            return_exceptions=True,
        )

    def prune_retained(self) -> None:
        self.ledger.prune(self.clock())
        self.state.links = {
            key: value
            for key, value in self.state.links.items()
            if self.ledger.get(value.parent.command_id) is not None
        }
        self.state.reports = {
            key: value
            for key, value in self.state.reports.items()
            if self.ledger.get(key[1]) is not None
        }
