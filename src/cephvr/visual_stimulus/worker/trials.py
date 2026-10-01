"""Trial clock, graphics activity evidence and asynchronous output finalization."""

from __future__ import annotations

import threading
from collections.abc import Callable

from cephvr.control.v1 import types_pb2 as pb
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus
from cephvr.visual_stimulus.v1 import runtime_pb2 as vp

from .ports import EnginePort, FeedbackPort, RecordingPort
from .state import DriverState
from .timing import OutputTiming


class TrialExecution:
    def __init__(
        self,
        *,
        state: DriverState,
        worker: pb.ProcessIdentity,
        backend: pb.BackendContext,
        policies: pb.ControlPolicies,
        engine: EnginePort,
        recording: RecordingPort,
        feedback: FeedbackPort | None = None,
        cancelled: threading.Event,
        clock: Callable[[], int],
        emit: Callable[[pb.LifecycleReport, int], None],
    ) -> None:
        self.state, self.worker, self.backend, self.policies = (
            state,
            worker,
            backend,
            policies,
        )
        self.engine, self.recording, self.feedback, self.cancelled, self.clock = (
            engine,
            recording,
            feedback,
            cancelled,
            clock,
        )
        self.lifecycle = emit

    def context(self, command: visual_stimulus.WorkerCommand) -> pb.ReportContext:
        return pb.ReportContext(
            backend=self.backend,
            work=command.target.work,
            operation=pb.OperationContext(command_id=command.command_id),
        )

    def advance(self, now_ns: int) -> int | None:
        trial = self.state.trial
        self._drain_diagnostics()
        if trial is None or trial.release is None or trial.stopped:
            return None
        release = trial.release
        if self.cancelled.is_set():
            self.stop(now_ns, release.command)
            return None if trial.finished else now_ns + 1_000_000
        if now_ns < release.start_monotonic_ns:
            return release.start_monotonic_ns
        if not trial.started and now_ns >= (
            release.start_monotonic_ns + self.policies.start_evidence_allowance_ns
        ):
            raise TimeoutError("required outputs supplied no timely start evidence")
        if now_ns >= release.normal_end_monotonic_ns:
            self.stop(now_ns, release.command)
            return None if trial.finished else now_ns + 1_000_000
        if not trial.begun:
            self.engine.begin_trial(
                trial.prepared.trial.context.trial_id, release.start_monotonic_ns
            )
            if self.feedback is not None:
                self.feedback.begin_trial(trial.prepared.trial.context.trial_id)
            trial.begun = True
        saving = (
            self.state.setup is not None
            and self.state.setup.settings.save_visual_stimulus_data
        )
        if saving:
            self.recording.before_render()
        feedback_batch = (
            self.feedback.capture_batch() if self.feedback is not None else ()
        )
        update = self.engine.render_tick(now_ns, feedback_batch)
        trial.groups += 1
        for output in trial.artifact.artifact.display.outputs:
            trial.timing.setdefault(output.output_id, OutputTiming()).observe(
                output.output_id, update
            )
        if saving:
            self.recording.rendered(update)
        for activity in update.group.outputs:
            if activity.error:
                raise RuntimeError(activity.error)
            if activity.output_id not in trial.activities:
                evidence = pb.ActivityEvidence(
                    kind="visual_stimulus_presentation_call",
                    observed_monotonic_ns=activity.swap_return_ns,
                )
                evidence.device_evidence.visual_stimulus_output.CopyFrom(
                    vp.OutputActivity(
                        output_id=activity.output_id,
                        render_group_id=update.group.group_id,
                        swap_entry_ns=activity.swap_entry_ns,
                        swap_return_ns=activity.swap_return_ns,
                        submission=vp.SUBMISSION_OUTCOME_RETURNED,
                    )
                )
                trial.activities[activity.output_id] = evidence
        if not trial.started and set(trial.activities) == {
            x.output_id for x in trial.artifact.artifact.display.outputs
        }:
            limit = (
                release.start_monotonic_ns + self.policies.start_evidence_allowance_ns
            )
            if any(x.observed_monotonic_ns > limit for x in trial.activities.values()):
                raise TimeoutError("required output missed start liveness")
            trial.started = True
            self.lifecycle(
                pb.LifecycleReport(
                    started=pb.StartedReport(
                        context=self.context(release.command),
                        actual_start_monotonic_ns=min(
                            x.observed_monotonic_ns for x in trial.activities.values()
                        ),
                        first_required_activity=list(trial.activities.values()),
                    )
                ),
                limit,
            )
        return self.clock()

    def _drain_diagnostics(self) -> None:
        trial = self.state.trial
        records = self.engine.poll_diagnostics()
        if not records:
            return
        if trial is None or not trial.begun:
            raise RuntimeError("GPU diagnostics arrived outside a begun trial")
        outputs = {item.output_id for item in trial.artifact.artifact.display.outputs}
        for record in records:
            if record.output_id not in outputs or record.group_id >= trial.groups:
                raise RuntimeError(
                    "GPU diagnostics name an unknown output/render group"
                )
            trial.timing.setdefault(record.output_id, OutputTiming()).diagnostic(record)
        if (
            self.state.setup is not None
            and self.state.setup.settings.save_visual_stimulus_data
        ):
            self.recording.diagnostics(records)

    def stop(self, cutoff_ns: int, command: visual_stimulus.WorkerCommand) -> None:
        trial = self.state.trial
        if trial is None or trial.stopped:
            return
        if trial.schedule is not None:
            # E11: late wakeups and interruption cannot enlarge sample membership.
            cutoff_ns = min(cutoff_ns, trial.schedule.normal_end_monotonic_ns)
        idle = self.engine.stop_trial(cutoff_ns)
        if self.feedback is not None:
            self.feedback.discard_pending()
        if {x.output_id for x in idle} != {
            x.output_id for x in trial.artifact.artifact.display.outputs
        } or any(x.error or x.swap_return_ns < x.swap_entry_ns for x in idle):
            raise RuntimeError("renderer could not confirm Idle on every output")
        if any(
            item.swap_return_ns > cutoff_ns + self.policies.stop_evidence_allowance_ns
            for item in idle
        ):
            raise TimeoutError("Idle confirmation exceeded the original stop allowance")
        trial.stopped = True
        trial.cutoff_ns = cutoff_ns
        actual = trial.release.command if trial.release else command
        limit = cutoff_ns + self.policies.trial_finished.initial_ns
        trial.finish_deadline_ns = limit
        trial.stop_command = actual
        if trial.begun:
            stopped = pb.StoppedReport(
                context=self.context(actual),
                actual_stop_monotonic_ns=cutoff_ns,
                trial_activity_stopped=True,
                visual_stimulus_idle=True,
                recording_interval_sealed=True,
            )
            stopped.producer_ends.add(
                producer=self.worker, source_id="renderer", end_monotonic_ns=cutoff_ns
            )
            self.lifecycle(
                pb.LifecycleReport(stopped=stopped),
                cutoff_ns + self.policies.stop_evidence_allowance_ns,
            )
        saving = (
            self.state.setup is not None
            and self.state.setup.settings.save_visual_stimulus_data
        )
        if saving:
            if not trial.begun:
                self.recording.begin_cancel(limit)
        self.finalize()

    def finalize(self) -> None:
        trial = self.state.trial
        if trial is None or not trial.stopped or trial.finished:
            return
        self._drain_diagnostics()
        if trial.begun and (
            self.engine.diagnostics_pending
            or any(
                trial.timing.get(output.output_id, OutputTiming()).diagnostics_count
                != trial.groups
                for output in trial.artifact.artifact.display.outputs
            )
        ):
            if (
                trial.finish_deadline_ns is not None
                and self.clock() >= trial.finish_deadline_ns
            ):
                raise TimeoutError(
                    "required GPU diagnostics missed the original finalization deadline"
                )
            return
        saving = (
            self.state.setup is not None
            and self.state.setup.settings.save_visual_stimulus_data
        )
        if saving:
            if trial.begun and not trial.recording_finish_started:
                assert (
                    trial.cutoff_ns is not None and trial.finish_deadline_ns is not None
                )
                self.recording.begin_finish(trial.cutoff_ns, trial.finish_deadline_ns)
                trial.recording_finish_started = True
            results = self.recording.poll_finished()
            if results is None:
                if (
                    trial.finish_deadline_ns is not None
                    and self.clock() >= trial.finish_deadline_ns
                ):
                    raise TimeoutError(
                        "recording closure missed the retained finalization deadline"
                    )
                return
            trial.outputs = results
            self.state.outputs.update((item.output_key, item) for item in results)
        actual = trial.stop_command
        limit = trial.finish_deadline_ns
        if actual is None or limit is None:
            raise RuntimeError("trial finalization lacks retained stop context")
        trial.finished = True
        if trial.begun:
            assert trial.release is not None and trial.cutoff_ns is not None
            elapsed_epochs = {
                epoch.occurrence_index
                for epoch in trial.artifact.artifact.epochs
                if epoch.start_ns < trial.cutoff_ns - trial.release.start_monotonic_ns
            }
            self.lifecycle(
                pb.LifecycleReport(
                    finished=pb.FinishedReport(
                        context=self.context(actual),
                        trial_activity_stopped=True,
                        outputs=trial.outputs,
                        visual_stimulus_review_summary=self.recording.review_summary()
                        if saving
                        else None,
                        visual_stimulus_timing_summaries=[
                            trial.timing.get(o.output_id, OutputTiming()).report(
                                trial.prepared.trial.context.trial_id,
                                o.output_id,
                                trial.groups,
                                elapsed_epochs,
                            )
                            for o in trial.artifact.artifact.display.outputs
                        ],
                    )
                ),
                limit,
            )
