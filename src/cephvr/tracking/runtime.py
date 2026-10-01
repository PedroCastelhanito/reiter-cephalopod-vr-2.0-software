"""Tracking public runtime: retained control facts and independent native owners."""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger
from cephvr.shared.transport_deadlines import remaining_seconds
from cephvr.tracking.coordinator.commands import validate
from cephvr.tracking.coordinator.ports import FeedbackPort, SessionPort
from cephvr.tracking.coordinator.reports import PeerPort, Reports
from cephvr.tracking.coordinator.state import Identity, State
from cephvr.tracking.coordinator.trials import RecordSink, Trials
from cephvr.tracking.feedback.delivery import FeedbackDelivery
from cephvr.tracking.feedback.transport import FeedbackTransport
from cephvr.tracking.processing.gate import TrialGate
from cephvr.tracking.processing.session import NativeSession, SessionSpec
from cephvr.tracking.transport.boundary import command_of
from cephvr.tracking.types import PrivateFrame
from cephvr.tracking.v1 import services_pb2 as tracking
from cephvr.visual_stimulus.v1.runtime_pb2 import FeedbackAttachment

SessionFactory = Callable[
    [SessionSpec, TrialGate, FeedbackDelivery | None], SessionPort
]
FeedbackFactory = Callable[
    [FeedbackAttachment, str, FeedbackDelivery, int, int], FeedbackPort
]


class TrackingRuntime:
    def __init__(
        self,
        identity: Identity,
        controller: PeerPort,
        supervisor: PeerPort,
        ledger: CommandLedger,
        *,
        session_factory: SessionFactory = NativeSession,
        feedback_factory: FeedbackFactory = FeedbackTransport,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity, self.ledger, self.clock = identity, ledger, clock
        self.state = State()
        self.reports = Reports(
            identity, self.state, controller, supervisor, ledger, clock
        )
        self.session_factory, self.feedback_factory = session_factory, feedback_factory
        self.executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="tracking-movement"
        )
        self.engine: SessionPort | None = None
        self.feedback: FeedbackPort | None = None
        self.delivery: FeedbackDelivery | None = None
        self.sink = RecordSink()
        self.gate = TrialGate(self.sink.admit)
        self.trials: Trials | None = None
        self.bound = asyncio.Event()
        self.shutdown_requested = asyncio.Event()
        self.cleanup_lock = asyncio.Lock()
        self.binding_lock = asyncio.Lock()
        self.recovery_deadline: int | None = None
        self.setup_deadline = 0

    def validate_command(self, method: str, request: Message) -> None:
        validate(self.identity, self.state, method, request, self.clock())

    async def execute(
        self, method: str, request: Message, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        self.validate_command(method, request)
        command = command_of(request)
        if isinstance(request, wire.IncidentScopeRequest):
            self.state.incident_revisions[request.incident.incident_id] = (
                request.incident.revision
            )
        if isinstance(request, wire.SetupSessionRequest):
            await self._setup(request, deadline_ns)
        elif isinstance(request, tracking.TrackingDataBinding):
            await self._bind(request, deadline_ns)
        elif isinstance(request, wire.PrepareTrialRequest):
            assert self.trials is not None
            self.trials.prepare(request)
        elif isinstance(request, wire.ScheduleTrialRequest):
            assert self.trials is not None
            self.trials.schedule(request)
        elif isinstance(request, wire.ReleaseTrialRequest):
            assert self.trials is not None
            self.trials.release(request)
        elif method in ("StopTrial", "AbortTrial"):
            if method == "AbortTrial":
                self.state.interrupted = True
            if self.trials is not None:
                await self.trials.stop(deadline_ns)
        elif method in (
            "InterruptSession",
            "CancelSetup",
            "Cleanup",
            "Shutdown",
            "ApplyIncidentScope",
        ):
            self.state.interrupted = True
            self.bound.set()
            self.gate.seal(self.clock())
            self.recovery_deadline = min(
                deadline_ns, self.recovery_deadline or deadline_ns
            )
            try:
                if self.trials is not None and self.state.trial is not None:
                    await self.trials.stop(self.recovery_deadline)
            finally:
                if method in (
                    "CancelSetup",
                    "Cleanup",
                    "Shutdown",
                    "ApplyIncidentScope",
                ):
                    await self.cleanup(command, self.recovery_deadline)
            if method == "Shutdown":
                self.shutdown_requested.set()
        else:
            raise ValueError("unsupported Tracking command")
        await self.reports.operation(method, command, deadline_ns)
        return pb.CommandAdmission(
            command_id=command.command_id, result=pb.COMMAND_RESULT_ACCEPTED
        )

    async def _setup(self, request: wire.SetupSessionRequest, deadline: int) -> None:
        state = self.state
        state.setup = wire.SetupSessionRequest.FromString(request.SerializeToString())
        state.cleanup = state.ready = state.error = None
        state.trial = state.schedule = state.release = None
        state.interrupted = False
        state.incident_revisions.clear()
        state.resources.clear()
        state.resource_revision = 0
        state.preparation.Clear()
        state.preparation.preparation_generation = str(uuid4())
        state.preparation.configuration_revision = request.plan.configuration_revision
        state.preparation_report = None
        state.frames_digest = None
        state.session_phase = pb.SESSION_PHASE_SETTING_UP
        self.setup_deadline = deadline
        self.recovery_deadline = None
        self.bound.clear()
        self.sink.saving = request.settings.tracking.save_tracking_data
        self.engine = self.feedback = self.delivery = self.trials = None
        # E08 establishes an explicit empty catalogue before registering creations.
        await self.reports.heartbeat(deadline)
        names = [("tracking-native", None)]
        if self.sink.saving:
            names.append(("tracking-writer", None))
        closed = request.plan.configuration.mode == pb.SESSION_MODE_CLOSED_LOOP
        if closed:
            if (
                request.feedback_consumer.role != "visual_stimulus_renderer"
                or not request.feedback_consumer.generation
            ):
                raise ValueError(
                    "closed-loop Setup requires the exact registered renderer generation"
                )
            names.append(("tracking-feedback", None))
        await self.reports.resources(tuple(names), deadline)
        if closed:
            attachment = FeedbackAttachment(
                attachment_generation=str(uuid4()),
                source_process_instance_id=self.identity.process.generation,
                startup_nonce=secrets.token_bytes(32),
                stream_ids=[request.settings.tracking.pipeline_id],
                queue_capacity=request.tracking_policies.result_capacity,
            )
            from cephvr.tracking.config.models.methods import FileLimits

            limits = FileLimits.model_validate_json(
                request.tracking_policies.limits_json
            )
            attachment.maximum_message_bytes = limits.maximum_message_bytes
            attachment.result_pipe = (
                rf"\\.\pipe\cephvr-{attachment.attachment_generation}-result"
            )
            attachment.credit_pipe = (
                rf"\\.\pipe\cephvr-{attachment.attachment_generation}-credit"
            )
            self.delivery = FeedbackDelivery(
                attachment.attachment_generation,
                request.settings.tracking.pipeline_id,
                attachment.queue_capacity,
                attachment.maximum_message_bytes,
                self.gate,
            )
            self.feedback = self.feedback_factory(
                attachment,
                request.feedback_consumer.generation,
                self.delivery,
                deadline,
                request.plan.policies.recovery_ns,
            )
            await asyncio.to_thread(self.feedback.prepare)
            state.preparation.feedback.CopyFrom(attachment)
        await self.reports.preparation(deadline)
        await asyncio.wait_for(self.bound.wait(), remaining_seconds(deadline))
        if (
            state.interrupted
            or self.engine is None
            or not state.preparation.data_attached
        ):
            raise RuntimeError("Setup was cancelled or source preparation failed")
        while self.feedback is not None and not self.feedback.connected:
            if self.feedback.failure is not None:
                raise RuntimeError(
                    "feedback attachment failed"
                ) from self.feedback.failure
            if state.interrupted or self.clock() >= deadline:
                raise TimeoutError("feedback attachment missed original Setup deadline")
            await asyncio.sleep(0.01)
        state.ready = pb.ReadyReport(
            context=self.reports.context(request.command),
            configuration_revision=request.plan.configuration_revision,
            required_checks_passed=True,
            resolved_settings=request.settings,
            cleanup_resources=state.resources,
        )
        state.ready.prepared_functions.add(
            resource_id="tracking",
            owner=self.identity.process,
            affected_closure_resource_ids=["tracking"],
            essential_to_stimulus_control=False,
            feedback_hold_required_on_loss=closed,
            bounded_uncertainty_supported=True,
            lifecycle_sources=["tracking"],
        )
        state.session_phase = pb.SESSION_PHASE_READY
        await self.reports.lifecycle(pb.LifecycleReport(ready=state.ready), deadline)

    async def _bind(self, request: tracking.TrackingDataBinding, deadline: int) -> None:
        async with self.binding_lock:
            state = self.state
            self.validate_command("BindData", request)
            if state.preparation.data_attached:
                return
            assert state.setup is not None
            state.frames_digest = request.frames.SerializeToString(deterministic=True)
            await self.reports.resources(
                ((request.frames.buffer.allocation_id, None),),
                min(deadline, self.setup_deadline),
            )
            spec = SessionSpec(
                state.setup.settings.tracking,
                state.setup.tracking_policies,
                self.identity.process,
                state.preparation.preparation_generation,
                state.setup.plan.configuration_revision,
                state.setup.plan.configuration.asset_root,
                min(deadline, self.setup_deadline),
                self._first,
            )
            self.engine = self.session_factory(spec, self.gate, self.delivery)
            future = asyncio.get_running_loop().run_in_executor(
                self.executor, self.engine.prepare, request.frames
            )
            methods = await asyncio.wait_for(
                asyncio.shield(future), remaining_seconds(spec.deadline)
            )
            if state.interrupted:
                raise RuntimeError("native preparation completed after cancellation")
            state.preparation.methods.methods_json = methods.model_dump_json()
            state.preparation.data_attached = True
            state.preparation.attached_input.resource_id = (
                request.frames.buffer.allocation_id
            )
            state.preparation.attached_input.transfer_id = (
                request.frames.sync.transfer_id
            )
            self.trials = Trials(
                self.identity,
                state,
                self.engine,
                self.executor,
                self.gate,
                self.sink,
                self.reports,
                self.clock,
            )
            await self.reports.preparation(spec.deadline)
            self.bound.set()

    def _first(self, frame: PrivateFrame, disposition: str, now: int) -> None:
        if self.trials is None:
            raise RuntimeError("first evaluation without trial owner")
        self.trials.first_evaluation(frame, disposition, now)

    async def cleanup(self, command: wire.BackendCommand, deadline: int) -> None:
        self.recovery_deadline = (
            deadline
            if self.recovery_deadline is None
            else min(deadline, self.recovery_deadline)
        )
        deadline = self.recovery_deadline
        async with self.cleanup_lock:
            native = True
            if self.engine is not None and not self.engine.closed:
                try:
                    native = await asyncio.wait_for(
                        asyncio.shield(
                            asyncio.get_running_loop().run_in_executor(
                                self.executor, self.engine.close, deadline
                            )
                        ),
                        remaining_seconds(deadline),
                    )
                except Exception:
                    native = False
            feedback = self.feedback is None
            if self.feedback is not None:
                try:
                    feedback = await asyncio.to_thread(self.feedback.close, deadline)
                except Exception:
                    feedback = False
            writer = self.sink.writer
            writer_closed = writer is None or writer.closed
            resources = [
                pb.ResourceRelease(
                    resource=item.resource,
                    path=item.path if item.HasField("path") else None,
                    released=feedback
                    if item.resource == "tracking-feedback"
                    else writer_closed
                    if item.resource == "tracking-writer"
                    else native,
                )
                for item in self.state.resources
            ]
            self.state.cleanup = pb.CleanupReport(
                source=self.identity.process,
                work=command.work,
                operation=pb.OperationContext(command_id=command.command_id),
                verified_monotonic_ns=self.clock(),
                trial_activity_stopped=native,
                resources=resources,
                outputs=self.state.outputs,
                cleanup_resources_revision=self.state.resource_revision,
            )
            await self.reports.lifecycle(
                pb.LifecycleReport(cleanup=self.state.cleanup), deadline
            )
            if not native or not feedback or not writer_closed:
                raise RuntimeError(
                    "Tracking cleanup retains native or output obligations"
                )
            self.state.session_phase = pb.SESSION_PHASE_ENDED

    async def failed_command(
        self,
        method: str,
        command: wire.BackendCommand,
        outcome: pb.OperationState,
        deadline_ns: int,
    ) -> None:
        self.state.interrupted = True
        self.bound.set()
        self.gate.seal(self.clock())
        self.state.error = pb.ErrorReport(
            error_id=str(uuid4()),
            source=self.identity.process,
            work=command.work,
            operation=pb.OperationContext(command_id=command.command_id),
            occurred_monotonic_ns=self.clock(),
            failure=outcome.failure,
        )
        try:
            await self.reports.supervisor.receipt(
                "ReportError", self.state.error, deadline_ns=deadline_ns
            )
        finally:
            await self.reports.lifecycle(
                pb.LifecycleReport(
                    operation=pb.BackendOperationReport(
                        source=self.identity.backend, operation=outcome
                    )
                ),
                deadline_ns,
            )

    async def poll(self, deadline: int) -> None:
        self.reports.prune()
        failure = (
            None if self.engine is None else self.engine.progress_failure(self.clock())
        )
        if self.feedback is not None and self.feedback.failure is not None:
            failure = str(self.feedback.failure)
        writer = self.sink.writer
        if writer is not None and (
            writer.failure is not None or writer.stalled(self.clock())
        ):
            failure = str(writer.failure or "tracking writer progress deadline expired")
        if (
            self.trials is not None
            and self.trials.task is not None
            and self.trials.task.done()
        ):
            exception = self.trials.task.exception()
            if exception is not None:
                failure = str(exception)
        if self.trials is not None and self.trials.first_task is not None:
            first = self.trials.first_task
            if first.done() and not first.cancelled() and first.exception() is not None:
                failure = str(first.exception())
        if (
            failure is not None
            and self.state.error is None
            and self.state.setup is not None
        ):
            command = (
                self.state.release.command
                if self.state.release is not None
                else self.state.setup.command
            )
            outcome = pb.OperationState(
                context=pb.OperationContext(command_id=command.command_id),
                command="TrackingActivity",
                work=command.work,
                complete=True,
                succeeded=False,
                failure=pb.Failure(code="TRACKING_ACTIVITY", message=failure),
            )
            await self.failed_command("TrackingActivity", command, outcome, deadline)
        await self.reports.heartbeat(deadline)

    async def query(self, method: str, request: Message) -> Message:
        from cephvr.tracking.coordinator.projection import project

        return project(self.identity, self.state, self.ledger, method, request)
