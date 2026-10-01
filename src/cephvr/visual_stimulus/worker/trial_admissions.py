"""Exact trial admissions over focused prepared state and graphics/recording ports."""

from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass

from cephvr.control.v1 import types_pb2 as pb
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus

from .ports import EnginePort, FeedbackPort, RecordingPort
from .state import DriverState, Trial


@dataclass
class TrialAdmissions:
    state: DriverState
    backend: pb.BackendContext
    policies: pb.ControlPolicies
    engine: EnginePort
    recording: RecordingPort
    feedback: FeedbackPort | None
    clock: Callable[[], int]
    lifecycle: Callable[[pb.LifecycleReport, int], None]

    def context(self, command: visual_stimulus.WorkerCommand) -> pb.ReportContext:
        return pb.ReportContext(
            backend=self.backend,
            work=command.target.work,
            operation=pb.OperationContext(command_id=command.command_id),
        )

    def prepare(
        self, request: visual_stimulus.WorkerPrepareTrial, deadline_ns: int
    ) -> None:
        if not self.state.ready or self.state.interrupted:
            raise RuntimeError("renderer not session-ready")
        previous = self.state.trial
        if previous is not None and not previous.finished:
            raise RuntimeError("preceding trial not finalized")
        artifact = self.state.artifacts.get(request.trial.context.trial_id)
        if (
            artifact is None
            or artifact.handle != request.prepared
            or request.trial.resolved_duration_ns
            != artifact.artifact.resolved_duration_ns
        ):
            raise ValueError("prepared trial identity/duration mismatch")
        self.engine.prepare_trial(artifact.artifact)
        if (
            self.feedback is not None
            and self.state.setup is not None
            and self.state.setup.HasField("feedback_attachment")
        ):
            self.engine.set_feedback_applier(
                self.feedback.prepare_trial(artifact.artifact)
            )
        else:
            self.engine.set_feedback_applier(None)
        self.state.trial = Trial(request, artifact)
        self.lifecycle(
            pb.LifecycleReport(
                ready=pb.ReadyReport(
                    context=self.context(request.command),
                    configuration_revision=request.command.target.configuration_revision,
                    required_checks_passed=True,
                    resolved_trials=[request.trial],
                )
            ),
            deadline_ns,
        )

    def schedule(self, request: visual_stimulus.WorkerSchedule) -> Future[None] | None:
        trial = self.require_trial(request.command)
        if trial.schedule is not None:
            raise ValueError("trial already scheduled")
        if (
            request.prepared != trial.artifact.handle
            or request.normal_end_monotonic_ns - request.start_monotonic_ns
            != trial.artifact.artifact.resolved_duration_ns
        ):
            raise ValueError("schedule differs from retained epoch sum")
        if (
            self.clock()
            >= request.start_monotonic_ns - self.policies.backend_release_offset_ns
        ):
            raise TimeoutError("schedule arrives beyond release cutoff")
        if self.state.setup is None:
            raise RuntimeError("Setup missing")
        if self.state.setup.settings.save_visual_stimulus_data:
            for output in request.outputs:
                if output.output_key not in self.state.outputs:
                    continue
                self.state.outputs[output.output_key] = pb.OutputResult(
                    output_key=output.output_key,
                    path=output.path,
                    closure=pb.OUTPUT_CLOSURE_UNCONFIRMED,
                )
            trial.schedule_completion = self.recording.schedule(
                request, trial.artifact.artifact
            )
        trial.schedule = request
        return trial.schedule_completion

    def release(self, request: visual_stimulus.WorkerRelease) -> None:
        trial = self.require_trial(request.command)
        schedule = trial.schedule
        if trial.schedule_completion is not None:
            if not trial.schedule_completion.done():
                raise ValueError("recording Schedule launch remains pending")
            trial.schedule_completion.result()
        if (
            schedule is None
            or request.schedule_operation.command_id != schedule.command.command_id
            or (request.start_monotonic_ns, request.normal_end_monotonic_ns)
            != (schedule.start_monotonic_ns, schedule.normal_end_monotonic_ns)
        ):
            raise ValueError("release differs from retained schedule")
        if (
            self.clock()
            >= request.start_monotonic_ns - self.policies.backend_release_offset_ns
        ):
            raise TimeoutError("late renderer release")
        trial.release = request

    def require_trial(self, command: visual_stimulus.WorkerCommand) -> Trial:
        trial = self.state.trial
        if (
            trial is None
            or command.target.work.WhichOneof("work") != "trial"
            or command.target.work.trial != trial.prepared.trial.context
        ):
            raise ValueError("renderer has no matching trial")
        return trial
