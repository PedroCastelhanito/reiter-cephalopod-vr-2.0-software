"""E08 lifecycle evidence admission and E04 cleanup proof."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

import grpc

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.evidence import started_satisfied, stopped_satisfied
from cephvr.controller.lifecycle_completion import DetailedCompletion
from cephvr.controller.state import (
    Attempt,
    ConfigurationState,
    LifecycleState,
    LimitsState,
    SupervisorState,
)

ActivityRequirements = tuple[
    frozenset[int],
    frozenset[int],
    frozenset[str],
    frozenset[str],
    frozenset[tuple[str, str]],
]


@dataclass(frozen=True)
class ReportHooks:
    publish: Callable[[], None]
    spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]]
    late_cleanup: Callable[[Attempt], Coroutine[Any, Any, None]]
    log_event: Callable[..., Coroutine[Any, Any, None]]
    recovery_log_done: Callable[[Attempt, asyncio.Task[object]], None]
    activity_requirements: Callable[[Attempt, str], ActivityRequirements]
    source_producers: Callable[[Attempt, str], dict[str, tuple[str, str]]]
    clock: Callable[[], int]
    # Appends a controller warning for evidence forwarding that stayed unconfirmed.
    warn: Callable[[str], None] | None = None


class LifecycleReports:
    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        configuration: ConfigurationState,
        supervisor: SupervisorState,
        limits: LimitsState,
        hooks: ReportHooks,
    ) -> None:
        self.lifecycle = lifecycle
        self.configuration = configuration
        self.limits = limits
        self.hooks = hooks
        self.completion = DetailedCompletion(
            lifecycle=lifecycle, supervisor=supervisor, limits=limits, hooks=hooks
        )

    async def receive(
        self, report: pb.LifecycleReport, ingress_ns: int
    ) -> pb.ReportReceipt:
        kind = report.WhichOneof("report")
        if kind is None:
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(code="INVALID", message="empty lifecycle report"),
            )
        payload = getattr(report, kind)
        context = payload.context if kind not in {"cleanup", "operation"} else None
        async with self.lifecycle.lock:
            attempt = self.lifecycle.attempt
            if attempt is None:
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(code="STALE", message="no matching live work"),
                )
            if kind == "operation":
                return self._operation(attempt, payload)
            if kind == "cleanup":
                receipt = self.completion.cleanup(attempt, payload)
                if (
                    receipt.result == pb.COMMAND_RESULT_ACCEPTED
                    and payload.source.role == "tracking"
                ):
                    deadline_ns = attempt.finalization_deadline_ns
                    if deadline_ns > 0:
                        self.hooks.spawn(
                            self._forward_tracking_cleanup(
                                attempt, payload, deadline_ns
                            )
                        )
                    else:
                        self._warn_unconfirmed("no finalization deadline")
                return receipt
            if attempt.cancel_requested or context is None:
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(code="STALE", message="attempt retired"),
                )
            name = context.backend.backend_name
            backend = attempt.required.get(name)
            if backend is None or context.backend != backend.context:
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(
                        code="IDENTITY", message="unregistered backend generation"
                    ),
                )
            work_kind = context.work.WhichOneof("work")
            if (
                kind == "ready"
                and self.lifecycle.session.phase == pb.SESSION_PHASE_SETTING_UP
            ):
                failure = self._setup_ready(
                    attempt, payload, context, name, work_kind, ingress_ns
                )
            elif kind in {"ready", "started", "stopped", "finished"}:
                failure = self._trial(
                    attempt, payload, context, kind, name, work_kind, ingress_ns
                )
            else:
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(code="PHASE", message="report not applicable"),
                )
            if failure is not None:
                return failure
            self.hooks.publish()
            attempt.changed.set()
        async with self.lifecycle.changed:
            self.lifecycle.changed.notify_all()
        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    async def _forward_tracking_cleanup(
        self, attempt: Attempt, cleanup: pb.CleanupReport, deadline_ns: int
    ) -> None:
        """Forward accepted registered consumer release under its retained deadline."""
        acquisition = attempt.required.get("acquisition")
        if acquisition is None:
            return
        try:
            UUID(cleanup.operation.command_id)
        except ValueError:
            return
        request = svc.TrackingInputConfirmation(
            command=svc.BackendCommand(
                command_id=cleanup.operation.command_id,
                issuer=pb.ProcessIdentity(
                    role="controller",
                    generation=attempt.context.controller_generation,
                ),
                target=acquisition.context,
                work=pb.WorkContext(session=attempt.context),
                parent_operation=cleanup.operation,
            ),
            configuration_revision=attempt.prepared.configuration_revision,
            tracking_cleanup=cleanup,
        )
        delay_s = 0.01
        reason = "deadline reached"
        while self.hooks.clock() < deadline_ns:
            try:
                receipt = await acquisition.confirm_tracking_input(
                    request, deadline_ns=deadline_ns
                )
                if receipt.result == pb.COMMAND_RESULT_ACCEPTED:
                    return
                if receipt.failure.code not in {"UNAVAILABLE", "RETRY"}:
                    self._warn_unconfirmed(f"rejected: {receipt.failure.message}")
                    return
                reason = f"retryable rejection: {receipt.failure.message}"
            except (
                TimeoutError,
                OSError,
                RuntimeError,
                grpc.RpcError,
                grpc.aio.AioRpcError,
            ) as exc:
                reason = f"transport failure: {exc}"
            remaining_s = max(0.0, (deadline_ns - self.hooks.clock()) / 1_000_000_000)
            if remaining_s <= 0:
                break
            await asyncio.sleep(min(delay_s, remaining_s))
            delay_s = min(delay_s * 2, 0.1)
        self._warn_unconfirmed(reason)

    def _warn_unconfirmed(self, reason: str) -> None:
        if self.hooks.warn is not None:
            self.hooks.warn(
                f"tracking cleanup forwarding to acquisition unconfirmed: {reason}"
            )

    def _operation(
        self, attempt: Attempt, payload: pb.BackendOperationReport
    ) -> pb.ReportReceipt:
        operation = payload.operation
        expected_scope = attempt.scope_commands.get(operation.context.command_id)
        backend = attempt.required.get(payload.source.backend_name)
        if (
            expected_scope is None
            or backend is None
            or payload.source != backend.context
            or expected_scope[0] != payload.source.backend_name
            or operation.work.WhichOneof("work") != "session"
            or operation.work.session != attempt.context
            or not operation.complete
        ):
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="EVIDENCE",
                    message="unexpected backend operation result",
                ),
            )
        prior = attempt.scope_results.get(operation.context.command_id)
        if prior is not None and prior.SerializeToString(
            deterministic=True
        ) != operation.SerializeToString(deterministic=True):
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="CONFLICT",
                    message="changed backend operation completion",
                ),
            )
        attempt.scope_results[operation.context.command_id] = deepcopy(operation)
        attempt.changed.set()
        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    def _setup_ready(
        self,
        attempt: Attempt,
        payload: pb.ReadyReport,
        context: pb.ReportContext,
        name: str,
        work_kind: str | None,
        ingress_ns: int,
    ) -> pb.ReportReceipt | None:
        within_ready_gate = (
            ingress_ns <= attempt.setup_deadline_ns
            or attempt.recovering_evidence == "setup_ready"
            and ingress_ns <= attempt.recovery_deadline_ns
        )
        if (
            attempt.interrupted
            or not within_ready_gate
            or work_kind != "session"
            or context.work.session != attempt.context
            or context.operation.command_id != attempt.setup_operations.get(name)
            or payload.configuration_revision != self.configuration.revision
            or not payload.required_checks_passed
        ):
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="EVIDENCE",
                    message="Setup Ready identity/check mismatch",
                ),
            )
        old = attempt.ready.get(name)
        if old is not None and old.SerializeToString(
            deterministic=True
        ) != payload.SerializeToString(deterministic=True):
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="CONFLICT", message="changed duplicate Setup Ready"
                ),
            )
        attempt.ready[name] = deepcopy(payload)
        return None

    def _trial(
        self,
        attempt: Attempt,
        payload: pb.ReadyReport
        | pb.StartedReport
        | pb.StoppedReport
        | pb.FinishedReport,
        context: pb.ReportContext,
        kind: str,
        name: str,
        work_kind: str | None,
        ingress_ns: int,
    ) -> pb.ReportReceipt | None:
        if (
            attempt.trial_index < 0
            or work_kind != "trial"
            or context.work.trial
            != attempt.prepared.trials[attempt.trial_index].context
            or context.operation.command_id != attempt.trial_operation
        ):
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="EVIDENCE", message="trial report identity mismatch"
                ),
            )
        if name not in attempt.trial_participants:
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="EVIDENCE",
                    message="backend is not an active trial participant",
                ),
            )
        if kind == "ready":
            return self._trial_ready(
                attempt, cast(pb.ReadyReport, payload), name, ingress_ns
            )
        if kind == "started":
            return self._started(
                attempt, cast(pb.StartedReport, payload), name, ingress_ns
            )
        if kind == "stopped":
            return self._stopped(
                attempt, cast(pb.StoppedReport, payload), name, ingress_ns
            )
        return self.completion.finished(
            attempt, cast(pb.FinishedReport, payload), name, ingress_ns
        )

    def _trial_ready(
        self, attempt: Attempt, payload: pb.ReadyReport, name: str, ingress_ns: int
    ) -> pb.ReportReceipt | None:
        within_ready_gate = (
            ingress_ns <= attempt.ready_deadline_ns
            or attempt.recovering_evidence == "trial_ready"
            and ingress_ns <= attempt.recovery_deadline_ns
        )
        if (
            attempt.interrupted
            or self.lifecycle.trial.phase != pb.TRIAL_PHASE_PREPARING
            or not within_ready_gate
            or payload.configuration_revision != self.configuration.revision
            or not payload.required_checks_passed
        ):
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(code="EVIDENCE", message="trial readiness failed"),
            )
        old = attempt.trial_ready.get(name)
        if old is not None and old.SerializeToString(
            deterministic=True
        ) != payload.SerializeToString(deterministic=True):
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="CONFLICT", message="changed duplicate trial Ready"
                ),
            )
        attempt.trial_ready[name] = deepcopy(payload)
        return None

    def _started(
        self, attempt: Attempt, payload: pb.StartedReport, name: str, ingress_ns: int
    ) -> pb.ReportReceipt | None:
        camera_roles, external_roles, vr_outputs, sources, producers = (
            self.hooks.activity_requirements(attempt, name)
        )
        if (
            not sources
            or self.lifecycle.trial.phase
            not in (pb.TRIAL_PHASE_STARTING, pb.TRIAL_PHASE_RUNNING)
            or not started_satisfied(
                payload,
                target_ns=attempt.target_ns,
                ingress_ns=ingress_ns,
                allowance_ns=self.limits.current.start_evidence_ns,
                camera_roles=camera_roles,
                external_camera_roles=external_roles,
                allowed_producers=producers,
                source_producers=self.hooks.source_producers(attempt, name),
                vr_outputs=vr_outputs,
            )
        ):
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="LATE",
                    message="Started evidence late or incomplete",
                ),
            )
        old_started = attempt.started.get(name)
        if old_started is not None and old_started.SerializeToString(
            deterministic=True
        ) != payload.SerializeToString(deterministic=True):
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="CONFLICT", message="changed duplicate Started"
                ),
            )
        attempt.started[name] = deepcopy(payload)
        return None

    def _stopped(
        self, attempt: Attempt, payload: pb.StoppedReport, name: str, ingress_ns: int
    ) -> pb.ReportReceipt | None:
        _camera_roles, external_roles, _vr_outputs, sources, producers = (
            self.hooks.activity_requirements(attempt, name)
        )
        if (
            not sources
            or self.lifecycle.trial.phase
            not in (
                pb.TRIAL_PHASE_STARTING,
                pb.TRIAL_PHASE_RUNNING,
                pb.TRIAL_PHASE_FINALIZING,
            )
            or not stopped_satisfied(
                payload,
                target_ns=attempt.target_ns,
                end_ns=attempt.end_ns,
                ingress_ns=ingress_ns,
                allowance_ns=self.limits.current.stop_evidence_ns,
                interruption_issued_ns=attempt.interruption_issued_ns,
                expected_sources=sources,
                allowed_producers=producers,
                source_producers=self.hooks.source_producers(attempt, name),
                external_camera_roles=external_roles,
            )
        ):
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="EVIDENCE", message="Stopped conditions missing"
                ),
            )
        old_stopped = attempt.stopped.get(name)
        if old_stopped is not None and old_stopped.SerializeToString(
            deterministic=True
        ) != payload.SerializeToString(deterministic=True):
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(
                    code="CONFLICT", message="changed duplicate Stopped"
                ),
            )
        attempt.stopped[name] = deepcopy(payload)
        return None
