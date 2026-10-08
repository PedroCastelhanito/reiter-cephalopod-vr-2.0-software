"""E05 trial preparation, common target release and evidence boundaries."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from typing import Any

import grpc
from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.lifecycle.activity import (
    activity_backends,
    select_trial_participants,
)
from cephvr.controller.lifecycle.cleanup import CleanupWorkflow
from cephvr.controller.lifecycle.evidence_wait import EvidenceWaiter
from cephvr.controller.lifecycle.interruption import InterruptionWorkflow
from cephvr.controller.metadata.trial_logs import TrialLogs
from cephvr.controller.ports import BackendPort
from cephvr.controller.projections import ProjectionStore
from cephvr.controller.state import (
    Attempt,
    LifecycleState,
    LimitsState,
    TrialClosureState,
)


@dataclass(frozen=True)
class TrialSchedule:
    target_ns: int
    end_ns: int
    schedule_deadline_ns: int
    release_deadline_ns: int
    file_prefix: str


class TrialExecution:
    """Prepare each trial and release one immutable target T."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        limit_state: LimitsState,
        clock: Callable[[], int],
        projections: ProjectionStore,
        publisher: SnapshotPublisher,
        evidence_waiter: EvidenceWaiter,
        cleanup: CleanupWorkflow,
        trial_logs: TrialLogs,
        interruption: InterruptionWorkflow,
        spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]],
    ) -> None:
        self.lifecycle = lifecycle
        self.limit_state = limit_state
        self.clock = clock
        self.projections = projections
        self.publisher = publisher
        self.evidence_waiter = evidence_waiter
        self.cleanup = cleanup
        self.trial_logs = trial_logs
        self.interruption = interruption
        self.spawn = spawn

    async def run_trials(self, attempt: Attempt) -> None:
        for index, plan in enumerate(attempt.prepared.trials):
            async with self.lifecycle.lock:
                if (
                    self.lifecycle.attempt is not attempt
                    or self.lifecycle.session.phase != pb.SESSION_PHASE_RUNNING
                ):
                    return
                if self.lifecycle.session.stop_after_trial:
                    # E06: Stop before a trial starts ends the session with no trial.
                    self.lifecycle.session.phase = pb.SESSION_PHASE_FINALIZING
                    self.lifecycle.session.outcome = pb.SESSION_OUTCOME_STOPPED
                    self.publisher.publish()
                    break
                if (
                    set(attempt.incident_id_by_error.values())
                    - attempt.confirmed_incidents.keys()
                ):
                    pending = (
                        set(attempt.incident_id_by_error.values())
                        - attempt.confirmed_incidents.keys()
                    )
                    expired = [
                        error_id
                        for error_id, incident_id in attempt.incident_id_by_error.items()
                        if incident_id in pending
                        and self.clock() >= attempt.incident_deadlines.get(error_id, 0)
                    ]
                    if expired:
                        raise RuntimeError(
                            "incident isolation remained unconfirmed after its original recovery deadline"
                        )
                attempt.trial_index = index
                attempt.trial_operation = str(uuid.uuid4())
                attempt.trial_ready.clear()
                attempt.trial_results.clear()
                attempt.started.clear()
                attempt.stopped.clear()
                attempt.finished.clear()
                attempt.trial_closure = TrialClosureState()
                attempt.unavailable_outputs.clear()
                attempt.trial_participants = select_trial_participants(attempt, plan)
                self.lifecycle.trial = pb.TrialState(
                    context=plan.context, phase=pb.TRIAL_PHASE_PREPARING
                )
                self.projections.set_scope(
                    pb.WorkContext(trial=plan.context),
                    attempt.prepared.configuration_revision,
                )
                self.publisher.publish()
            try:
                await self.prepare_and_run_trial(attempt, plan)
            except Exception as exc:
                await self.interruption.interrupt(attempt, f"trial {index + 1}: {exc}")
                return
            async with self.lifecycle.lock:
                if self.lifecycle.session.stop_after_trial:
                    self.lifecycle.session.phase = pb.SESSION_PHASE_FINALIZING
                    self.lifecycle.session.outcome = pb.SESSION_OUTCOME_STOPPED
                    self.publisher.publish()
                    break
        await self.interruption.finalize(attempt)

    async def prepare_and_run_trial(self, attempt: Attempt, plan: pb.TrialPlan) -> None:
        await self._prepare_to_ready(attempt, plan)
        schedule = await self._plan_trial(attempt, plan)
        await self._schedule_participants(attempt, plan, schedule)
        await self._release_participants(attempt, plan, schedule)
        await self._observe_trial(attempt, plan, schedule)

    async def _prepare_to_ready(self, attempt: Attempt, plan: pb.TrialPlan) -> None:
        deadline = self.clock() + self.limit_state.current.ready_ns
        attempt.ready_deadline_ns = deadline
        request_by_name: dict[str, svc.PrepareTrialRequest] = {}
        for name, backend in attempt.trial_participants.items():
            request = svc.PrepareTrialRequest(
                configuration_revision=attempt.prepared.configuration_revision,
                plan=plan,
            )
            request.command.CopyFrom(self.cleanup.backend_command(attempt, backend))
            request.command.command_id = attempt.trial_operation
            request.command.work.trial.CopyFrom(plan.context)
            request.outputs.extend(
                output
                for output in attempt.prepared.outputs
                if output.trial == plan.context and output.backend.backend_name == name
            )
            request_by_name[name] = request
        replies = await asyncio.wait_for(
            asyncio.gather(
                *(
                    attempt.trial_participants[name].prepare_trial(
                        request, deadline_ns=deadline
                    )
                    for name, request in request_by_name.items()
                )
            ),
            max(0, (deadline - self.clock()) / 1e9),
        )
        if any(reply.result != pb.COMMAND_RESULT_ACCEPTED for reply in replies):
            raise RuntimeError("trial preparation rejected")
        await self.evidence_waiter.wait_lifecycle_with_recovery(
            attempt, "trial_ready", frozenset(attempt.trial_participants), deadline
        )
        async with self.lifecycle.lock:
            self.lifecycle.trial.phase = pb.TRIAL_PHASE_READY
            self.publisher.publish()

    async def _plan_trial(self, attempt: Attempt, plan: pb.TrialPlan) -> TrialSchedule:
        target = self.clock() + self.limit_state.current.lead_ns
        end = target + plan.resolved_duration_ns
        attempt.target_ns = target
        attempt.end_ns = end
        attempt.finished_deadline_ns = end + self.limit_state.current.finished_ns
        schedule_deadline = target - self.limit_state.current.controller_release_ns
        release_deadline = target - self.limit_state.current.backend_release_ns
        anchor = datetime.fromisoformat(attempt.prepared.anchor_wall_time)
        trial_wall = anchor + timedelta(
            microseconds=(target - attempt.prepared.anchor_monotonic_ns) / 1000
        )
        prefix = (
            f"{attempt.prepared.configuration.subject}_{trial_wall.strftime('%H%M%S')}"
        )
        attempt.trial_log_name = f"{prefix}_LOG.json"
        attempt.trial_log_finished = False
        attempt.trial_log_start_task = None
        attempt.trial_log_finish_task = None
        for output in attempt.prepared.outputs:
            if output.trial == plan.context:
                if (
                    not output.output_tag
                    or not output.extension
                    or "/" in output.output_tag
                    or "/" in output.extension
                    or "\\" in output.output_tag
                    or "\\" in output.extension
                ):
                    raise RuntimeError("unsafe output reservation name")
                output.path = str(
                    attempt.reservation.protocol_directory
                    / f"{prefix}_{output.output_tag}.{output.extension}"
                )
                if output.backend.backend_name not in attempt.trial_participants:
                    if output.output_key not in attempt.unavailable_resources():
                        raise RuntimeError(
                            "omitted backend has an unproven output obligation"
                        )
                    attempt.unavailable_outputs.append(
                        pb.OutputResult(
                            output_key=output.output_key,
                            path=output.path,
                            closure=pb.OUTPUT_CLOSURE_FAILED,
                            failure=pb.Failure(
                                code="INCIDENT_UNAVAILABLE",
                                message="owning function unavailable under confirmed E06 scope",
                            ),
                        )
                    )
        async with self.lifecycle.lock:
            self.lifecycle.trial.phase = pb.TRIAL_PHASE_STARTING
            self.lifecycle.trial.start_monotonic_ns = target
            self.lifecycle.trial.scheduled_end_monotonic_ns = end
            self.publisher.publish()
        return TrialSchedule(
            target,
            end,
            schedule_deadline,
            release_deadline,
            str(attempt.reservation.protocol_directory / prefix),
        )

    async def _schedule_participants(
        self, attempt: Attempt, plan: pb.TrialPlan, schedule: TrialSchedule
    ) -> None:
        for name, backend in attempt.trial_participants.items():
            schedule_request = svc.ScheduleTrialRequest(
                start_monotonic_ns=schedule.target_ns,
                normal_end_monotonic_ns=schedule.end_ns,
                trial_file_prefix=schedule.file_prefix,
            )
            schedule_request.command.CopyFrom(
                self.cleanup.backend_command(attempt, backend)
            )
            schedule_request.command.command_id = str(uuid.uuid4())
            schedule_request.command.work.trial.CopyFrom(plan.context)
            schedule_request.outputs.extend(
                output
                for output in attempt.prepared.outputs
                if output.trial == plan.context and output.backend.backend_name == name
            )
            attempt.schedule_operations[name] = schedule_request.command.command_id
            reply = await self.trial_command_with_retry(
                partial(
                    backend.schedule_trial,
                    deadline_ns=schedule.schedule_deadline_ns,
                ),
                schedule_request,
                schedule.schedule_deadline_ns,
                schedule.schedule_deadline_ns,
            )
            if reply.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(f"{name} schedule rejected")
        if self.clock() > schedule.schedule_deadline_ns:
            raise TimeoutError(
                "schedule acknowledgements missed controller release cutoff"
            )

    async def _release_participants(
        self, attempt: Attempt, plan: pb.TrialPlan, schedule: TrialSchedule
    ) -> None:
        releases: dict[str, tuple[BackendPort, svc.ReleaseTrialRequest]] = {}
        for name, backend in attempt.trial_participants.items():
            release_request = svc.ReleaseTrialRequest(
                start_monotonic_ns=schedule.target_ns,
                normal_end_monotonic_ns=schedule.end_ns,
            )
            release_request.command.CopyFrom(
                self.cleanup.backend_command(attempt, backend)
            )
            release_request.command.command_id = str(uuid.uuid4())
            release_request.command.work.trial.CopyFrom(plan.context)
            release_request.schedule_operation.command_id = attempt.schedule_operations[
                name
            ]
            releases[name] = backend, release_request
        if self.clock() > schedule.schedule_deadline_ns:
            raise TimeoutError("release dispatch missed controller cutoff")
        # From here a release may reach backends: interruption must close the trial.
        attempt.trial_closure.released = frozenset(releases)
        release_results = await asyncio.wait_for(
            asyncio.gather(
                *(
                    self.trial_command_with_retry(
                        partial(
                            backend.release_trial,
                            deadline_ns=schedule.release_deadline_ns,
                        ),
                        request,
                        schedule.schedule_deadline_ns,
                        schedule.release_deadline_ns,
                    )
                    for backend, request in releases.values()
                )
            ),
            max(0, (schedule.release_deadline_ns - self.clock()) / 1e9),
        )
        for name, reply in zip(releases, release_results, strict=True):
            if reply.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(f"{name} release rejected")
        if self.clock() > schedule.release_deadline_ns:
            raise TimeoutError("release acknowledgement missed backend cutoff")

    async def _observe_trial(
        self, attempt: Attempt, plan: pb.TrialPlan, schedule: TrialSchedule
    ) -> None:
        target = schedule.target_ns
        end = schedule.end_ns
        await asyncio.sleep(max(0, (target - self.clock()) / 1e9))
        async with self.lifecycle.lock:
            self.lifecycle.trial.phase = pb.TRIAL_PHASE_RUNNING
            self.publisher.publish()
        await self.evidence_waiter.wait_evidence(
            lambda: bool(attempt.started),
            target + self.limit_state.current.start_evidence_ns,
            attempt,
        )
        attempt.trial_log_start_task = self.spawn(
            self.trial_logs.start_trial_log(attempt, plan)
        )
        await asyncio.shield(attempt.trial_log_start_task)
        active_backends = activity_backends(attempt)
        await self.evidence_waiter.wait_evidence(
            lambda: active_backends <= attempt.started.keys(),
            target + self.limit_state.current.start_evidence_ns,
            attempt,
        )
        await asyncio.sleep(max(0, (end - self.clock()) / 1e9))
        async with self.lifecycle.lock:
            self.lifecycle.trial.phase = pb.TRIAL_PHASE_FINALIZING
            attempt.finished_deadline_ns = end + self.limit_state.current.finished_ns
            self.publisher.publish()
        stopped_deadline_ns = end + self.limit_state.current.stop_evidence_ns
        await self.evidence_waiter.wait_evidence(
            lambda: active_backends <= attempt.stopped.keys(),
            stopped_deadline_ns,
            attempt,
        )
        self.interruption.arm_spikeglx_stop(
            attempt,
            stopped_deadline_ns=stopped_deadline_ns,
            final_trial=attempt.trial_index == len(attempt.prepared.trials) - 1,
        )
        await self.evidence_waiter.wait_lifecycle_with_recovery(
            attempt,
            "finished",
            frozenset(attempt.trial_participants),
            end + self.limit_state.current.finished_ns,
        )
        attempt.trial_log_finish_task = self.spawn(
            self.trial_logs.finish_normal_trial_log(attempt, plan)
        )
        await asyncio.shield(attempt.trial_log_finish_task)
        async with self.lifecycle.lock:
            self.lifecycle.trial.phase = pb.TRIAL_PHASE_ENDED
            self.lifecycle.trial.outcome = pb.TRIAL_OUTCOME_COMPLETED
            self.lifecycle.trial.actual_end_monotonic_ns = end
            self.publisher.publish()
        gap = next(
            (
                item.minimum_duration_ns
                for item in attempt.prepared.configuration.gaps
                if item.after_trial_number == plan.context.trial_number
            ),
            0,
        )
        await asyncio.sleep(max(0, (end + gap - self.clock()) / 1e9))

    async def trial_command_with_retry(
        self,
        send: Callable[[Any], Coroutine[Any, Any, pb.CommandAdmission]],
        request: Message,
        dispatch_deadline_ns: int,
        receipt_deadline_ns: int,
    ) -> pb.CommandAdmission:
        for retry in range(2):
            if self.clock() > dispatch_deadline_ns:
                raise TimeoutError("trial command dispatch cutoff elapsed")
            try:
                return await asyncio.wait_for(
                    send(request), max(0, (receipt_deadline_ns - self.clock()) / 1e9)
                )
            except grpc.RpcError:
                if retry or self.clock() >= receipt_deadline_ns:
                    raise
        raise RuntimeError("trial command retry exhausted")
