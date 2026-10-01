"""Prepared local trial clock and aggregate evidence on the single GL owner."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future
from uuid import uuid4

from google.protobuf.message import Message

from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.clock import host_time_ns
from cephvr.visual_stimulus.config.models.display_profile import (
    DisplayProfile,
    parse_display_json,
)
from cephvr.visual_stimulus.config.models.program_model import Program
from cephvr.visual_stimulus.rendering.types import DisplayInitialization
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus
from cephvr.visual_stimulus.v1 import runtime_pb2 as vp

from .cleanup import cleanup_resources
from .display_initialization import (
    DisplayPreparationJob,
    begin_display_preparation,
    complete_display_preparation,
)
from .ports import EnginePort, FeedbackPort, PreparationPort, RecordingPort, ReportPort
from .preparation import PreparationJob, begin
from .state import DriverState, TrialArtifact
from .trial_admissions import TrialAdmissions
from .trials import TrialExecution


def _program_has_feedback(program: Program) -> bool:
    pending = list(program.sequence)
    while pending:
        node = pending.pop()
        if hasattr(node, "body"):
            pending.extend(node.body)
        elif any(setting.feedback for setting in node.settings):
            return True
    return False


class LifecycleDriver:
    def __init__(
        self,
        *,
        worker: pb.ProcessIdentity,
        owner: pb.ProcessIdentity,
        controller: pb.ProcessIdentity,
        policies: pb.ControlPolicies,
        engine: EnginePort,
        preparation: PreparationPort,
        recording: RecordingPort,
        feedback: FeedbackPort | None = None,
        reports: ReportPort,
        cancelled: threading.Event,
        clock: Callable[[], int] = host_time_ns,
        shutdown: Callable[[], None],
    ) -> None:
        self.worker, self.owner, self.controller = worker, owner, controller
        self.backend = pb.BackendContext(
            backend_name="visual_stimulus", backend_generation=owner.generation
        )
        (
            self.policies,
            self.engine,
            self.preparation,
            self.recording,
            self.feedback,
            self.reports,
        ) = (
            policies,
            engine,
            preparation,
            recording,
            feedback,
            reports,
        )
        self.cancelled, self.clock, self.shutdown = cancelled, clock, shutdown
        self.state = DriverState()
        self.admissions = TrialAdmissions(
            self.state,
            self.backend,
            policies,
            engine,
            recording,
            feedback,
            clock,
            self.lifecycle,
        )
        self.trials = TrialExecution(
            state=self.state,
            worker=worker,
            backend=self.backend,
            policies=policies,
            engine=engine,
            recording=recording,
            feedback=feedback,
            cancelled=cancelled,
            clock=clock,
            emit=self.lifecycle,
        )
        self.command: visual_stimulus.WorkerCommand | None = None
        self.deadline_ns = 0
        self.preparation_job: PreparationJob | None = None
        self.display_job: DisplayPreparationJob | None = None
        self.catalogue_lock = threading.RLock()
        self.pending_cleanup: list[
            tuple[visual_stimulus.WorkerCommand, int, bool, Future[None]]
        ] = []

    def execute(
        self, method: str, request: Message, deadline_ns: int
    ) -> Future[None] | None:
        from cephvr.visual_stimulus.transport.messages import worker_command

        self.command = worker_command(request)
        self.deadline_ns = deadline_ns
        if isinstance(request, visual_stimulus.InitializeDisplay):
            return self.initialize(request)
        elif isinstance(request, visual_stimulus.WorkerSetup):
            return self.setup(request)
        elif isinstance(request, visual_stimulus.WorkerPrepareTrial):
            self.prepare(request)
        elif isinstance(request, visual_stimulus.WorkerSchedule):
            return self.schedule(request)
        elif isinstance(request, visual_stimulus.WorkerRelease):
            self.release(request)
        elif isinstance(request, visual_stimulus.WorkerRecipePublication):
            self._recipe_publication(request)
        elif method in {"StopTrial", "InterruptSession"}:
            if method == "InterruptSession":
                self.state.interrupted = True
            self.trials.stop(self.clock(), self.command)
        elif method in {"CancelSetup", "Cleanup", "Shutdown"}:
            self.state.interrupted = True
            self.trials.stop(self.clock(), self.command)
            if (
                self.preparation_job is not None
                or (self.state.trial is not None and not self.state.trial.finished)
                or self.display_job is not None
            ):
                future: Future[None] = Future()
                self.pending_cleanup.append(
                    (self.command, deadline_ns, method == "Shutdown", future)
                )
                return future
            self.cleanup(self.command)
            if method == "Shutdown":
                self.shutdown()
        else:
            raise ValueError(f"unsupported renderer operation {method}")
        return None

    def _recipe_publication(
        self, request: visual_stimulus.WorkerRecipePublication
    ) -> None:
        """Validate mandatory recipe output before notifying optional video recording."""
        trial = self.state.trial
        if trial is None:
            raise RuntimeError("recipe publication has no current trial")
        if not request.published:
            message = (
                request.failure.message
                if request.HasField("failure")
                else "publication failed"
            )
            raise RuntimeError(f"required trial recipe was not published: {message}")
        if request.prepared != trial.artifact.handle:
            raise RuntimeError(
                "recipe publication names a different prepared trial handle"
            )
        outputs = {
            item.output_tag: item
            for item in (trial.schedule.outputs if trial.schedule is not None else ())
        }
        recipe_output = outputs.get("stimulus_LOG")
        if recipe_output is None or request.path != recipe_output.path:
            raise RuntimeError(
                "recipe publication path differs from the reserved trial output"
            )
        self.recording.publication(request)

    def initialize(self, request: visual_stimulus.InitializeDisplay) -> Future[None]:
        if self.display_job is not None or self.state.display_ready:
            raise RuntimeError("display initialization is already pending or complete")
        display = parse_display_json(
            request.display.profile_json, max_bytes=request.limits.max_document_bytes
        )
        for output in display.outputs:
            self.announce("display:" + output.output_id, None)
        command = visual_stimulus.WorkerCommand.FromString(
            request.command.SerializeToString()
        )
        deadline_ns = self.deadline_ns
        self.display_job = begin_display_preparation(
            request,
            display,
            self.preparation,
            lambda key, path: self.announce_for(command, deadline_ns, key, path),
            deadline_ns,
        )
        return self.display_job.completion

    def _report_display(
        self,
        request: visual_stimulus.InitializeDisplay,
        display: DisplayProfile,
        observed: DisplayInitialization,
        deadline_ns: int,
    ) -> None:
        activities = {x.output_id: x for x in observed.idle_activity}
        bits = {x[0]: x[1:] for x in observed.observed_rgb_bits}
        intervals = dict(observed.requested_swap_intervals)
        if set(activities) != {x.output_id for x in display.outputs} or any(
            x.error or x.swap_return_ns < x.swap_entry_ns for x in activities.values()
        ):
            raise RuntimeError("Idle submission missing for required display output")
        view = pb.VisualStimulusDisplayView(
            source=self.worker,
            backend=self.backend,
            controller=self.controller,
            command_id=request.command.command_id,
            requested_revision=request.command.target.configuration_revision,
            applied_revision=request.command.target.configuration_revision,
            observed_monotonic_ns=self.clock(),
            complete=True,
        )
        for output in display.outputs:
            observed_output = activities[output.output_id]
            view.outputs.add(
                output_id=output.output_id,
                resources_ready=True,
                requested_rgb_bits=output.rgb_bits_per_channel,
                observed_rgb_bits=bits[output.output_id],
                requested_swap_interval=intervals[output.output_id],
                idle_swap_entry_ns=observed_output.swap_entry_ns,
                idle_swap_return_ns=observed_output.swap_return_ns,
                idle_submission=vp.SUBMISSION_OUTCOME_RETURNED,
            )
        self.state.display_ready = True
        self.reports.send("ReportDisplay", view, deadline_ns)

    def announce(self, key: str, path: str | None) -> None:
        self.announce_for(self.command, self.deadline_ns, key, path)

    def announce_for(
        self,
        command: visual_stimulus.WorkerCommand | None,
        deadline_ns: int,
        key: str,
        path: str | None,
    ) -> None:
        with self.catalogue_lock:
            if self.state.ready:
                raise RuntimeError("cannot add resources after Ready")
            obligation = pb.ResourceObligation(owner=self.worker, resource=key)
            if path is not None:
                obligation.path = path
            previous = self.state.resources.get(key)
            if previous is not None:
                if previous != obligation:
                    raise ValueError("native resource identity changed")
                return
            self.state.resources[key] = obligation
            self.state.catalogue_revision += 1
            work = command.target.work if command else pb.WorkContext()
            heartbeat = pb.HeartbeatReport(
                source=self.worker,
                work=work,
                sent_monotonic_ns=self.clock(),
                cleanup_resources_revision=self.state.catalogue_revision,
                cleanup_resources=list(self.state.resources.values()),
            )
            self.reports.confirm("ReportWorkerHeartbeat", heartbeat, deadline_ns)

    def setup(self, request: visual_stimulus.WorkerSetup) -> Future[None]:
        from cephvr.visual_stimulus.coordinator.obligations import output_plans

        if self.state.setup is not None:
            raise RuntimeError("previous renderer session not cleaned")
        if self.state.cleaned:
            self.state.resources.clear()
            self.state.released_threads.clear()
            self.state.artifacts.clear()
            self.state.outputs.clear()
            self.state.trial = None
            self.state.cleaned = False
        self.cancelled.clear()
        self.state.interrupted = False
        self.state.failure_deadline_ns = None
        self.state.setup = request
        self.state.outputs = {
            output.output_key: pb.OutputResult(
                output_key=output.output_key,
                closure=pb.OUTPUT_CLOSURE_NOT_STARTED,
                artifact_present=False,
            )
            for output in output_plans(
                self.backend,
                list(request.session.trials),
                request.settings.save_visual_stimulus_data,
            )
            if output.output_tag != "stimulus_LOG"
        }
        display = parse_display_json(
            request.settings.display.profile_json,
            max_bytes=request.policies.limits.max_document_bytes,
        )
        display.require_trial_marker()
        for output in display.outputs:
            self.announce("display:" + output.output_id, None)
        # Keep the previous, validated Idle visible while Setup loads and
        # validates the adopted calibration on its CPU worker. prepare_graphics
        # replaces the display only after that protected preparation succeeds.
        self.state.display_ready = False
        self.recording.configure(request, self.announce, self.deadline_ns)
        command = visual_stimulus.WorkerCommand.FromString(
            request.command.SerializeToString()
        )
        deadline = self.deadline_ns
        self.preparation_job = begin(
            request,
            self.preparation,
            self.recording,
            self.reports,
            lambda key, path: self.announce_for(command, deadline, key, path),
            deadline,
            self.clock,
        )
        return self.preparation_job.completion

    def complete_setup(
        self,
        request: visual_stimulus.WorkerSetup,
        records: tuple[TrialArtifact, ...],
        deadline_ns: int,
    ) -> None:
        if self.cancelled.is_set() or self.state.interrupted:
            raise InterruptedError("Setup cancelled before graphics preparation")
        self.preparation.prepare_graphics(tuple(record.artifact for record in records))
        if not self.state.display_ready:
            self.state.display_ready = True
        has_feedback = any(
            _program_has_feedback(record.artifact.source) for record in records
        )
        if request.HasField("feedback_attachment"):
            if not has_feedback or self.feedback is None:
                raise RuntimeError(
                    "feedback attachment has no declared renderer consumer"
                )
            command = visual_stimulus.WorkerCommand.FromString(
                request.command.SerializeToString()
            )
            self.feedback.configure(
                request.feedback_attachment,
                tuple(record.artifact for record in records),
                lambda key: self.announce_for(command, deadline_ns, key, None),
                deadline_ns,
                request.policies.max_result_age_ns,
            )
        elif has_feedback:
            raise RuntimeError(
                "closed-loop program has no authenticated feedback attachment"
            )
        ready = pb.ReadyReport(
            context=self.context(request.command),
            configuration_revision=request.command.target.configuration_revision,
            required_checks_passed=True,
            resolved_settings=pb.BackendSettings(
                backend_name="visual_stimulus",
                enabled=True,
                visual_stimulus=request.settings,
            ),
            cleanup_resources=list(self.state.resources.values()),
        )
        for record in records:
            artifact, handle = record.artifact, record.handle
            self.state.artifacts[artifact.identity.trial_id] = record
            source = next(
                item
                for item in request.session.trials
                if item.context.trial_id == artifact.identity.trial_id
            )
            resolved = ready.resolved_trials.add()
            resolved.CopyFrom(source)
            resolved.resolved_duration_ns = artifact.resolved_duration_ns
            resolved.resolved_stimulus.prepared.CopyFrom(handle)
            resolved.resolved_stimulus.seed_decimal = artifact.seed_decimal
            for epoch in artifact.epochs:
                item = resolved.resolved_stimulus.occurrences.add(
                    index=epoch.occurrence_index,
                    epoch_id=epoch.source_epoch_id,
                    scene_id=epoch.scene_id,
                    start_offset_ns=epoch.start_ns,
                    duration_ns=epoch.end_ns - epoch.start_ns,
                )
                for visit in epoch.lineage:
                    item.lineage.add(
                        group_id=visit.group_id,
                        repetition_index=visit.repetition_index,
                        unit_id=visit.unit_id,
                        visit_index=visit.visit_index,
                    )
        from cephvr.visual_stimulus.coordinator.obligations import (
            function_scopes,
            output_plans,
        )

        planned = output_plans(
            self.backend,
            list(request.session.trials),
            request.settings.save_visual_stimulus_data,
        )
        ready.prepared_functions.extend(
            function_scopes(self.owner, self.worker, planned)
        )
        self.state.ready = True
        self.lifecycle(pb.LifecycleReport(ready=ready), deadline_ns)

    def prepare(self, request: visual_stimulus.WorkerPrepareTrial) -> None:
        self.admissions.prepare(request, self.deadline_ns)

    def schedule(self, request: visual_stimulus.WorkerSchedule) -> Future[None] | None:
        return self.admissions.schedule(request)

    def release(self, request: visual_stimulus.WorkerRelease) -> None:
        self.admissions.release(request)

    def advance(self, now_ns: int) -> int | None:
        windows_active = self.engine.service_display()
        display_job = self.display_job
        if display_job is not None:
            try:
                done = complete_display_preparation(
                    display_job,
                    self.preparation,
                    now_ns=now_ns,
                    report=lambda display, observed: self._report_display(
                        display_job.request,
                        display,
                        observed,
                        display_job.deadline_ns,
                    ),
                )
                if not done:
                    return now_ns + 1_000_000
                self.state.released_threads.add(display_job.resource_key)
                self.display_job = None
            except BaseException as exc:
                if display_job.thread is None or not display_job.thread.is_alive():
                    self.state.released_threads.add(display_job.resource_key)
                self.display_job = None
                self.fail(exc)
        job = self.preparation_job
        if job is not None:
            if not job.result.done() or (
                job.thread is not None and job.thread.is_alive()
            ):
                return now_ns + 1_000_000
            self.preparation_job = None
            self.state.released_threads.add(job.resource_key)
            try:
                self.complete_setup(job.request, job.result.result(), job.deadline_ns)
                job.completion.set_result(None)
            except BaseException as exc:
                job.completion.set_exception(exc)
                self.fail(exc)
        trial = self.state.trial
        if trial is not None and trial.stopped and not trial.finished:
            self.trials.finalize()
            if not trial.finished:
                return now_ns + 1_000_000
        if self.pending_cleanup:
            pending, self.pending_cleanup = self.pending_cleanup, []
            for command, deadline, shutdown, future in pending:
                try:
                    self.deadline_ns = min(deadline, self.deadline_ns)
                    if now_ns >= deadline:
                        raise TimeoutError("cleanup missed its retained deadline")
                    self.cleanup(command)
                    future.set_result(None)
                    if shutdown:
                        self.shutdown()
                except BaseException as exc:
                    future.set_exception(exc)
                    self.fail(exc)
        due = self.trials.advance(now_ns)
        if windows_active:
            return (
                min(due, now_ns + 10_000_000)
                if due is not None
                else now_ns + 10_000_000
            )
        return due

    def cleanup(self, command: visual_stimulus.WorkerCommand) -> None:
        cleanup_resources(
            self.state,
            command,
            worker=self.worker,
            deadline_ns=self.deadline_ns,
            clock=self.clock,
            recording=self.recording,
            preparation=self.preparation,
            engine=self.engine,
            feedback=self.feedback,
            emit=self.lifecycle,
        )

    def context(self, command: visual_stimulus.WorkerCommand) -> pb.ReportContext:
        return pb.ReportContext(
            backend=self.backend,
            work=command.target.work,
            operation=pb.OperationContext(command_id=command.command_id),
        )

    def lifecycle(self, report: pb.LifecycleReport, deadline_ns: int) -> None:
        self.reports.send(
            "ReportWorkerLifecycle",
            visual_stimulus.WorkerLifecycle(source=self.worker, report=report),
            deadline_ns,
        )

    def fail(self, error: BaseException) -> None:
        self.state.failure_deadline_ns = (
            self.state.failure_deadline_ns or self.clock() + self.policies.recovery_ns
        )
        self.state.interrupted = True
        self.cancelled.set()
        self.reports.send(
            "ReportError",
            pb.ErrorReport(
                error_id=str(uuid4()),
                source=self.worker,
                work=self.command.target.work if self.command else pb.WorkContext(),
                occurred_monotonic_ns=self.clock(),
                failure=pb.Failure(
                    code="VISUAL_STIMULUS_RENDERER", message=str(error)[:2048]
                ),
            ),
            self.state.failure_deadline_ns,
        )
