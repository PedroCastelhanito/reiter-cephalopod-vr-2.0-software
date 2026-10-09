"""Start, normal completion, and interrupted completion of trial metadata."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.lifecycle.activity import activity_backends
from cephvr.controller.lifecycle.evidence_wait import EvidenceWaiter
from cephvr.controller.metadata.coordination import MetadataCoordinator
from cephvr.controller.metadata.documents import message_dict
from cephvr.controller.metadata.types import StorageError
from cephvr.controller.state import Attempt, ControlState, LifecycleState, LimitsState
from cephvr.shared.deadlines import remaining_seconds


def _trial_log_document(
    attempt: Attempt, plan: pb.TrialPlan, /, *, complete: bool, **extra: object
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "session_id": attempt.context.session_id,
        "trial_id": plan.context.trial_id,
        "trial_number": plan.context.trial_number,
        "session_config": "SESSION_CONFIG.json",
        "complete": complete,
        **extra,
    }


def _actual_stop_ns(attempt: Attempt, active_backends: frozenset[str]) -> int | None:
    if active_backends <= attempt.stopped.keys() and attempt.stopped:
        return max(
            report.actual_stop_monotonic_ns for report in attempt.stopped.values()
        )
    return None


def _interrupted_output_results(
    attempt: Attempt, plan: pb.TrialPlan
) -> list[dict[str, object]]:
    # A missing Finished report leaves every corresponding reserved output
    # explicitly unknown. A reported closure is retained exactly as sent.
    reported = {
        result.output_key: result
        for finished in attempt.finished.values()
        for result in finished.outputs
    }
    reported.update(
        {result.output_key: result for result in attempt.unavailable_outputs}
    )
    output_results: list[dict[str, object]] = []
    for output in attempt.prepared.outputs:
        if output.trial != plan.context:
            continue
        result = reported.get(output.output_key)
        if result is None:
            result = pb.OutputResult(
                output_key=output.output_key,
                path=output.path,
                closure=pb.OUTPUT_CLOSURE_UNCONFIRMED,
                failure=pb.Failure(
                    code="OUTPUT_CLOSURE_UNCONFIRMED",
                    message="no exact Finished closure by original interruption deadline",
                ),
            )
        output_results.append(message_dict(result))
    return output_results


class TrialLogs:
    """Own one trial's durable log stages without owning lifecycle authority."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        control: ControlState,
        limits: LimitsState,
        metadata: MetadataCoordinator,
        evidence_waiter: EvidenceWaiter,
        clock: Callable[[], int],
        spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]],
        publish: Callable[[], None],
    ) -> None:
        self.lifecycle = lifecycle
        self.control = control
        self.limits = limits
        self.metadata = metadata
        self.evidence_waiter = evidence_waiter
        self.clock = clock
        self.spawn = spawn
        self.publish = publish

    async def start_trial_log(self, attempt: Attempt, plan: pb.TrialPlan) -> None:
        if attempt.writer is None or not attempt.trial_log_name:
            raise StorageError("trial metadata writer unavailable")
        attempt.writer.reserve_trial_log(attempt.trial_log_name)
        await self.metadata.persist(
            attempt,
            attempt.trial_log_name,
            "create_json",
            _trial_log_document(attempt, plan, complete=False, plan=message_dict(plan)),
        )
        await self.metadata.log_event(
            attempt,
            "trial_started",
            at_ns=attempt.target_ns,
            trial_number=plan.context.trial_number,
        )

    async def finish_normal_trial_log(
        self, attempt: Attempt, plan: pb.TrialPlan
    ) -> None:
        if attempt.interrupted:
            raise RuntimeError("normal trial closure superseded by interruption")
        outputs = [
            message_dict(result)
            for finished in attempt.finished.values()
            for result in finished.outputs
        ]
        outputs.extend(message_dict(result) for result in attempt.unavailable_outputs)
        # Once issued, interruption must not replace this LOG or repeat the event.
        attempt.trial_closure.finish_append_issued = True
        await self.metadata.persist(
            attempt,
            attempt.trial_log_name,
            "replace_json",
            _trial_log_document(
                attempt,
                plan,
                complete=True,
                outcome="completed",
                plan=message_dict(plan),
                outputs=outputs,
            ),
        )
        await self.metadata.log_event(
            attempt,
            "trial_finished",
            at_ns=attempt.end_ns,
            trial_number=plan.context.trial_number,
            outcome="completed",
        )
        attempt.trial_log_finished = True
        await self.metadata.retire_completed_trial_metadata(
            attempt, attempt.trial_log_name
        )

    async def finish_interrupted_trial(self, attempt: Attempt) -> bool:
        closure = attempt.trial_closure
        if (
            attempt.trial_index < 0
            or not (attempt.started or closure.released)
            or attempt.trial_log_finished
        ):
            return True
        plan = attempt.prepared.trials[attempt.trial_index]
        deadline_ns = attempt.finalization_deadline_ns
        try:
            start_task = attempt.trial_log_start_task
            if start_task is None:
                start_task = self.spawn(self.start_trial_log(attempt, plan))
                attempt.trial_log_start_task = start_task
            await asyncio.wait_for(
                asyncio.shield(start_task),
                remaining_seconds(deadline_ns, clock=self.clock),
            )
            normal_finish = attempt.trial_log_finish_task
            if normal_finish is not None:
                await asyncio.wait_for(
                    asyncio.gather(normal_finish, return_exceptions=True),
                    remaining_seconds(deadline_ns, clock=self.clock),
                )
                if attempt.trial_log_finished:
                    async with self.lifecycle.lock:
                        if self.lifecycle.attempt is attempt:
                            self.lifecycle.trial.phase = pb.TRIAL_PHASE_ENDED
                            self.lifecycle.trial.outcome = pb.TRIAL_OUTCOME_COMPLETED
                            self.publish()
                    return True
            if closure.finish_append_issued:
                # The normal path already issued its LOG/trial_finished write: never
                # replace the LOG or append a second trial_finished (E06).
                raise StorageError("normal trial_finished append unconfirmed")
            active_backends = activity_backends(attempt)
            try:
                await self.evidence_waiter.wait_evidence(
                    lambda: active_backends <= attempt.stopped.keys(),
                    attempt.interruption_issued_ns
                    + self.limits.current.stop_evidence_ns,
                    attempt,
                )
            except TimeoutError:
                pass
            try:
                await self.evidence_waiter.wait_lifecycle_with_recovery(
                    attempt,
                    "finished",
                    frozenset(attempt.trial_participants),
                    attempt.finished_deadline_ns,
                    closure_only=True,
                )
            except TimeoutError:
                pass
            output_results = _interrupted_output_results(attempt, plan)
            await asyncio.wait_for(
                self.metadata.persist(
                    attempt,
                    attempt.trial_log_name,
                    "replace_json",
                    _trial_log_document(
                        attempt,
                        plan,
                        complete=True,
                        outcome="interrupted",
                        participants_started=sorted(attempt.started),
                        start_unconfirmed=sorted(
                            closure.released - attempt.started.keys()
                        ),
                        plan=message_dict(plan),
                        outputs=output_results,
                    ),
                ),
                remaining_seconds(deadline_ns, clock=self.clock),
            )
            if not attempt.trial_log_finished:
                actual_end_ns = _actual_stop_ns(attempt, active_backends)
                await asyncio.wait_for(
                    self.metadata.log_event(
                        attempt,
                        "trial_finished",
                        trial_number=plan.context.trial_number,
                        outcome="interrupted",
                        details={
                            "output_closure_confirmed": frozenset(
                                attempt.trial_participants
                            )
                            <= attempt.finished.keys(),
                            "start_unconfirmed": sorted(
                                closure.released - attempt.started.keys()
                            ),
                            "actual_end_monotonic_ns": actual_end_ns,
                            "interruption_issued_monotonic_ns": attempt.interruption_issued_ns,
                        },
                    ),
                    remaining_seconds(deadline_ns, clock=self.clock),
                )
                attempt.trial_log_finished = True
            async with self.lifecycle.lock:
                if self.lifecycle.attempt is attempt:
                    self.lifecycle.trial.phase = pb.TRIAL_PHASE_ENDED
                    self.lifecycle.trial.outcome = pb.TRIAL_OUTCOME_INTERRUPTED
                    stop_ns = _actual_stop_ns(attempt, active_backends)
                    if stop_ns is not None:
                        self.lifecycle.trial.actual_end_monotonic_ns = stop_ns
                    self.publish()
            await self.metadata.retire_completed_trial_metadata(
                attempt, attempt.trial_log_name
            )
            return True
        except (StorageError, TimeoutError, RuntimeError) as exc:
            async with self.lifecycle.lock:
                self.control.add_warning(
                    "interrupted_trial",
                    f"interrupted trial log or closure unconfirmed: {exc}",
                )
                self.publish()
            return False
