"""Original deadline and single-query lifecycle evidence recovery gates."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, Literal

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.state import Attempt, ControlState, LifecycleState, LimitsState


class EvidenceWaiter:
    """Wait on one attempt and preserve its initial and recovery deadlines."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        control: ControlState,
        limits: LimitsState,
        clock: Callable[[], int],
        publisher: SnapshotPublisher,
        report: Callable[
            [pb.LifecycleReport, int], Coroutine[Any, Any, pb.ReportReceipt]
        ],
    ) -> None:
        self.lifecycle = lifecycle
        self.control = control
        self.limits = limits
        self.clock = clock
        self.publisher = publisher
        self.report = report

    async def wait_evidence(
        self, predicate: Callable[[], bool], deadline_ns: int, attempt: Attempt
    ) -> None:
        while True:
            async with self.lifecycle.lock:
                if self.lifecycle.attempt is not attempt or attempt.cancel_requested:
                    raise RuntimeError("attempt retired")
                remaining = (deadline_ns - self.clock()) / 1e9
                if predicate():
                    return
                if self.lifecycle.session.phase == pb.SESSION_PHASE_SETTING_UP:
                    for name, command_id in attempt.setup_operations.items():
                        outcome = attempt.scope_results.get(command_id)
                        if (
                            outcome is not None
                            and outcome.HasField("succeeded")
                            and not outcome.succeeded
                        ):
                            raise RuntimeError(
                                f"{name} Setup failed: {outcome.failure.code}: "
                                f"{outcome.failure.message}"
                            )
                if self.lifecycle.trial.phase == pb.TRIAL_PHASE_PREPARING:
                    for name, outcome in attempt.trial_results.items():
                        if outcome.HasField("succeeded") and not outcome.succeeded:
                            raise RuntimeError(
                                f"{name} PrepareTrial failed: {outcome.failure.code}: "
                                f"{outcome.failure.message}"
                            )
                if remaining <= 0:
                    break
                attempt.changed.clear()
            try:
                await asyncio.wait_for(attempt.changed.wait(), remaining)
            except TimeoutError:
                break
        raise TimeoutError("required lifecycle evidence missing by deadline")

    async def wait_lifecycle_with_recovery(
        self,
        attempt: Attempt,
        kind: Literal["setup_ready", "trial_ready", "finished"],
        expected: frozenset[str],
        initial_deadline_ns: int,
        *,
        closure_only: bool = False,
    ) -> bool:
        def received_names() -> set[str]:
            if kind == "setup_ready":
                return set(attempt.ready)
            if kind == "trial_ready":
                return set(attempt.trial_ready)
            return set(attempt.finished)

        def predicate() -> bool:
            return expected <= received_names()

        try:
            await self.wait_evidence(predicate, initial_deadline_ns, attempt)
            return False
        except TimeoutError as exc:
            initial_error = exc
        recovery_deadline_ns = initial_deadline_ns + self.limits.current.recovery_ns
        if closure_only:
            if (
                kind != "finished"
                or not attempt.interrupted
                or not attempt.finalization_deadline_ns
            ):
                raise initial_error
            recovery_deadline_ns = min(
                recovery_deadline_ns, attempt.finalization_deadline_ns
            )
        async with self.lifecycle.lock:
            if (
                self.lifecycle.attempt is not attempt
                or attempt.interrupted
                and not closure_only
                or attempt.cancel_requested
                or self.clock() >= recovery_deadline_ns
                or kind == "setup_ready"
                and self.lifecycle.session.phase != pb.SESSION_PHASE_SETTING_UP
                or kind == "trial_ready"
                and self.lifecycle.trial.phase != pb.TRIAL_PHASE_PREPARING
                or kind == "finished"
                and self.lifecycle.trial.phase != pb.TRIAL_PHASE_FINALIZING
            ):
                raise initial_error
            missing = frozenset(expected - received_names())
            attempt.recovering_evidence = kind
            attempt.recovery_deadline_ns = recovery_deadline_ns
            self.control.add_warning(
                "lifecycle_recovery",
                f"{kind} initial evidence deadline expired; querying the frozen missing set",
            )
            self.publisher.publish()

        async def query(name: str) -> None:
            backend = attempt.required[name]
            work = (
                pb.WorkContext(session=attempt.context)
                if kind == "setup_ready"
                else pb.WorkContext(
                    trial=attempt.prepared.trials[attempt.trial_index].context
                )
            )
            command_id = (
                attempt.setup_operations[name]
                if kind == "setup_ready"
                else attempt.trial_operation
            )
            request = svc.RetainedResultQuery(
                query=svc.BackendQuery(target=backend.context, work=work),
                command_id=command_id,
            )
            try:
                retained = await asyncio.wait_for(
                    backend.get_retained_result(
                        request, deadline_ns=recovery_deadline_ns
                    ),
                    max(0, (recovery_deadline_ns - self.clock()) / 1e9),
                )
                if (
                    not retained.found
                    or retained.backend != backend.context
                    or retained.work != work
                ):
                    return
                if (
                    kind != "finished"
                    and retained.operation.complete
                    and retained.operation.context.command_id == command_id
                    and retained.operation.work == work
                    and retained.operation.HasField("succeeded")
                    and not retained.operation.succeeded
                ):
                    lifecycle = pb.LifecycleReport(
                        operation=pb.BackendOperationReport(
                            source=backend.context, operation=retained.operation
                        )
                    )
                elif kind == "finished":
                    if retained.finished.context.operation.command_id != command_id:
                        return
                    lifecycle = pb.LifecycleReport(finished=retained.finished)
                else:
                    if retained.ready.context.operation.command_id != command_id:
                        return
                    lifecycle = pb.LifecycleReport(ready=retained.ready)
                await self.report(lifecycle, self.clock())
            except Exception:
                return

        try:
            await asyncio.gather(*(query(name) for name in missing))
            await self.wait_evidence(predicate, recovery_deadline_ns, attempt)
            return True
        except TimeoutError as exc:
            raise TimeoutError(
                f"{kind} missing after one bounded recovery query"
            ) from exc
        finally:
            async with self.lifecycle.lock:
                if (
                    self.lifecycle.attempt is attempt
                    and attempt.recovering_evidence == kind
                ):
                    attempt.recovering_evidence = ""
                    attempt.recovery_deadline_ns = 0
