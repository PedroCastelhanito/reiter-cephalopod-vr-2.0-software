"""Cleanup evidence, recovery admission and bounded retry (E06/E08)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.platform.windows.bootstrap import run_pipe_io_daemon
from cephvr.shared.cleanup_outputs import cleanup_output_discharged
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandCapacityError, CommandConflict, CommandLedger
from cephvr.shared.credentials import default_runtime_root
from cephvr.shared.identity import require_uuid4
from cephvr.shared.recovery import RecoveryStore
from cephvr.shared.resources import ResourceCatalogueError, cleanup_command_fenced
from cephvr.supervisor.ports import SupervisorOutbound
from cephvr.supervisor.receipts import (
    accepted,
    rejected,
    report_accepted,
    report_rejected,
)
from cephvr.supervisor.registration import RegistrationCoordinator
from cephvr.supervisor.registry import LaunchError
from cephvr.supervisor.state import (
    HealthState,
    RecoveryState,
    StatusState,
    SupervisorTasks,
)


class RecoveryCoordinator:
    def __init__(
        self,
        *,
        state: RecoveryState,
        registration: RegistrationCoordinator,
        health: HealthState,
        status: StatusState,
        identity: types.ProcessIdentity,
        controller: types.ProcessIdentity,
        commands: CommandLedger,
        outbound: SupervisorOutbound,
        lock: asyncio.Lock,
        emergency_timeout_ns: int,
        max_retained_entries: int,
        tasks: SupervisorTasks,
        begin_safety: Callable[[types.Failure], None],
        changed: Callable[[], None],
    ) -> None:
        self.state = state
        self.registration = registration
        self.health = health
        self.status = status
        self.identity = identity
        self.controller = controller
        self.commands = commands
        self.outbound = outbound
        self.lock = lock
        self.emergency_timeout_ns = emergency_timeout_ns
        self.max_retained_entries = max_retained_entries
        self.tasks = tasks
        self.begin_safety = begin_safety
        self.changed = changed

    async def report_lifecycle(
        self,
        request: types.LifecycleReport,
        *,
        deadline_ns: int,
        ingress_ns: int,
    ) -> types.ReportReceipt:
        if request.WhichOneof("report") != "cleanup":
            return report_rejected(
                "INVALID_LIFECYCLE", "supervisor accepts top-level Cleanup only"
            )
        report = request.cleanup
        if (
            ingress_ns > deadline_ns
            or host_time_ns() > deadline_ns
            or report.source.role not in self.registration.required_backends()
            or not self.registration.source_registered(report.source)
            or not self.registration.same_work(report.work)
        ):
            return report_rejected(
                "WRONG_CONTEXT", "cleanup source/work is not registered"
            )
        if report.verified_monotonic_ns <= 0 or not report.operation.command_id:
            return report_rejected(
                "INVALID_CLEANUP", "verification time and operation required"
            )
        try:
            require_uuid4(report.operation.command_id)
        except ValueError as exc:
            return report_rejected("INVALID_CLEANUP", str(exc))
        key = report.source.role, report.source.generation
        async with self.lock:
            if not self.registration.same_work(
                report.work
            ) or not self.cleanup_verified(report):
                return report_rejected(
                    "INCOMPLETE_CLEANUP",
                    "registered output/resource obligations or cleanup fence are unverified",
                )
            previous = self.state.cleanup.get(key)
            if (
                previous
                and previous.operation == report.operation
                and previous != report
            ):
                return report_rejected(
                    "CHANGED_CLEANUP", "same operation changed evidence"
                )
            self.state.cleanup[key] = types.CleanupReport.FromString(
                report.SerializeToString()
            )
            event = self.state.cleanup_events.get(report.operation.command_id)
            if event is not None:
                event.set()
        self.changed()
        if report.source.role == "tracking":
            return await self._forward_tracking_release(report, deadline_ns=deadline_ns)
        return report_accepted()

    async def _forward_tracking_release(
        self, report: types.CleanupReport, *, deadline_ns: int
    ) -> types.ReportReceipt:
        context = self.registration.state.context
        if context is None:
            return report_rejected(
                "TRACKING_CLEANUP_CONTEXT", "registered context is absent"
            )
        acquisition_contexts = [
            participant
            for participant in context.required_participants
            if participant.backend_name == "acquisition"
        ]
        tracking_contexts = [
            participant
            for participant in context.required_participants
            if participant.backend_name == "tracking"
        ]
        if (
            len(acquisition_contexts) != 1
            or len(tracking_contexts) != 1
            or report.source.generation != tracking_contexts[0].backend_generation
        ):
            return report_rejected(
                "TRACKING_INPUT_RELEASE",
                "cleanup source is not the registered tracking participant",
            )
        admission = wire.TrackingInputConfirmation(
            command=wire.BackendCommand(
                command_id=report.operation.command_id,
                issuer=self.identity,
                target=acquisition_contexts[0],
                work=report.work,
                parent_operation=report.operation,
            ),
            tracking_cleanup=report,
        )
        delay_s = 0.01
        while host_time_ns() < deadline_ns:
            try:
                receipt = await self.outbound.confirm_tracking_cleanup(
                    admission, deadline_ns=deadline_ns
                )
                if receipt.result == types.COMMAND_RESULT_ACCEPTED:
                    return report_accepted()
                if receipt.failure.code not in {"UNAVAILABLE", "RETRY"}:
                    return report_rejected(
                        receipt.failure.code or "TRACKING_RELEASE",
                        receipt.failure.message
                        or "acquisition rejected tracking release",
                    )
            except (TimeoutError, OSError, RuntimeError):
                pass
            remaining = max(0.0, (deadline_ns - host_time_ns()) / 1_000_000_000)
            if remaining <= 0:
                break
            await asyncio.sleep(min(delay_s, remaining))
            delay_s = min(delay_s * 2, 0.1)
        return report_rejected(
            "TRACKING_RELEASE_UNCONFIRMED",
            "acquisition did not confirm tracking transfer release before its deadline",
        )

    def cleanup_verified(self, report: types.CleanupReport) -> bool:
        if not self.registration.state.context or not report.trial_activity_stopped:
            return False
        catalogue = self.registration.state.catalogues.get(
            (report.source.role, report.source.generation)
        )
        if catalogue is None:
            return False
        fenced = cleanup_command_fenced(
            report,
            self.registration.state.context,
            supervisor_command=self.state.issued_cleanup_commands.get(
                report.operation.command_id
            ),
        )
        try:
            catalogue.verify_cleanup(report, cleanup_command_fenced=fenced)
        except ResourceCatalogueError:
            return False
        expected = {
            output.output_key
            for output in self.registration.state.context.outputs
            if output.backend.backend_name == report.source.role
            and output.backend.backend_generation == report.source.generation
        }
        observed = {output.output_key: output for output in report.outputs}
        if expected != observed.keys() or len(observed) != len(report.outputs):
            return False
        if any(not cleanup_output_discharged(observed[key]) for key in expected):
            return False
        return True

    async def get_recovery_state(
        self, request: wire.RecoveryQuery
    ) -> wire.RecoverySnapshot:
        if (
            request.expected_supervisor != self.identity
            or not self.registration.same_work(request.work)
        ):
            raise ValueError("recovery query context mismatch")
        prior_receipt = None
        if request.HasField("prior_controller_generation"):
            try:
                prior_generation = require_uuid4(request.prior_controller_generation)
                if (
                    prior_generation == self.controller.generation
                    or self.registration.state.context is not None
                    or request.work.WhichOneof("work")
                ):
                    raise ValueError("prior exit proof is available only at startup")
                prior_receipt = await run_pipe_io_daemon(
                    lambda: RecoveryStore(default_runtime_root()).read_exit_receipt(
                        prior_generation
                    ),
                    timeout_s=min(self.emergency_timeout_ns / 1e9, 5.0),
                )
            except (ValueError, TimeoutError, RuntimeError, OSError) as exc:
                raise ValueError(
                    f"prior exit proof is unavailable or unsafe: {exc}"
                ) from exc
        response = wire.RecoverySnapshot(
            supervisor=self.identity,
            captured_monotonic_ns=host_time_ns(),
            recoveries=list(self.state.recoveries.values()),
            operations=list(self.state.operations.values()),
            errors=list(self.health.errors.values()),
            status_revision=self.status.revision,
            warnings=list(self.status.warnings.values()),
            cleanup_blockers=self.cleanup_blockers(),
        )
        if prior_receipt is not None:
            response.prior_application_exit.CopyFrom(
                wire.PriorApplicationExitReceipt(
                    controller_generation=prior_receipt.controller_generation,
                    supervisor_generation=prior_receipt.supervisor_generation,
                    observed_monotonic_ns=prior_receipt.observed_monotonic_ns,
                    all_owned_processes_absent=prior_receipt.all_owned_processes_absent,
                    format_version=prior_receipt.format_version,
                )
            )
        return response

    async def execute_recovery_action(
        self, request: wire.RecoveryActionRequest
    ) -> types.CommandAdmission:
        if request.supervisor != self.identity or not self.registration.same_work(
            request.work
        ):
            return rejected(
                request.command_id,
                LaunchError("WRONG_CONTEXT", "recovery target/context differs"),
            )
        if request.action != wire.RECOVERY_ACTION_RETRY_GRACEFUL_CLEANUP:
            return rejected(
                request.command_id,
                LaunchError(
                    "INVALID_ACTION", "only retry graceful cleanup is available"
                ),
            )
        if self.registration.state.context is None or (
            request.target.role,
            request.target.generation,
        ) not in {
            (x.backend_name, x.backend_generation)
            for x in self.registration.state.context.required_participants
        }:
            return rejected(
                request.command_id,
                LaunchError("WRONG_TARGET", "target generation is not registered"),
            )
        try:
            require_uuid4(request.operator.client_id)
            require_uuid4(request.operator.control_generation)
            require_uuid4(request.operator.command_id)
            if request.operator.command_id != request.command_id:
                raise ValueError("controller-verified operator command ID mismatch")
            if (
                len(self.state.operations) >= self.max_retained_entries
                and request.command_id not in self.state.operations
            ):
                self.begin_safety(
                    types.Failure(
                        code="OPERATION_CAPACITY",
                        message="required operation accounting exhausted",
                    )
                )
                raise CommandCapacityError("operation accounting exhausted")
            if (
                len(self.state.recoveries) >= self.max_retained_entries
                and request.command_id not in self.state.recoveries
            ):
                self.begin_safety(
                    types.Failure(
                        code="RECOVERY_CAPACITY",
                        message="required recovery accounting exhausted",
                    )
                )
                raise CommandCapacityError("recovery accounting exhausted")
            admitted = self.commands.admit(
                request.command_id,
                request.SerializeToString(deterministic=True),
                host_time_ns(),
                work_key=self.registration.work_key(request.work),
            )
            if admitted.replayed:
                return (
                    types.CommandAdmission.FromString(admitted.record.result)
                    if admitted.record.result
                    else accepted(request.command_id)
                )
            target = types.BackendContext(
                backend_name=request.target.role,
                backend_generation=request.target.generation,
            )
            command = wire.BackendCommand(
                command_id=request.command_id,
                issuer=self.identity,
                target=target,
                work=request.work,
            )
            self.state.operations[request.command_id] = types.OperationState(
                context=types.OperationContext(command_id=request.command_id),
                command="Retry graceful cleanup",
                work=request.work,
                progress="accepted",
            )
            start_ns = host_time_ns()
            budget_ns = max(0, self.registration.state.context.policies.recovery_ns)
            recovery = types.RecoveryState(
                attempt_id=request.command_id,
                affected=request.target,
                work=request.work,
                trigger=types.Failure(
                    code="RETRY_REQUESTED", message="operator retry graceful cleanup"
                ),
                action="retry_graceful_cleanup",
                start_monotonic_ns=start_ns,
                deadline_monotonic_ns=start_ns + budget_ns,
                progress="cleanup admission pending",
            )
            self.state.recoveries[request.command_id] = recovery
            self.state.issued_cleanup_commands[request.command_id] = command
            self.state.cleanup_events[request.command_id] = asyncio.Event()
            self.tasks.spawn("cleanup recovery", self.run_recovery(target, command))
            receipt = accepted(request.command_id)
            self.commands.complete(
                request.command_id,
                receipt.SerializeToString(deterministic=True),
                host_time_ns(),
            )
            self.changed()
            return receipt
        except (ValueError, CommandConflict, CommandCapacityError) as exc:
            return rejected(request.command_id, exc)

    async def run_recovery(
        self, target: types.BackendContext, command: wire.BackendCommand
    ) -> None:
        operation = self.state.operations[command.command_id]
        recovery = self.state.recoveries[command.command_id]
        try:
            remaining_s = max(
                0.0, (recovery.deadline_monotonic_ns - host_time_ns()) / 1e9
            )
            await asyncio.wait_for(
                self.outbound.cleanup_backend(
                    target, command, deadline_ns=recovery.deadline_monotonic_ns
                ),
                timeout=remaining_s,
            )
            operation.progress = "cleanup admitted; awaiting verified Cleanup evidence"
            recovery.progress = operation.progress
            remaining_s = max(
                0.0, (recovery.deadline_monotonic_ns - host_time_ns()) / 1e9
            )
            await asyncio.wait_for(
                self.state.cleanup_events[command.command_id].wait(),
                timeout=remaining_s,
            )
            operation.complete = True
            operation.succeeded = True
            operation.progress = "verified Cleanup evidence received"
            recovery.progress = operation.progress
            recovery.completion_monotonic_ns = host_time_ns()
            recovery.outcome = types.RECOVERY_OUTCOME_COMPLETED
            recovery.evidence = "matching top-level Cleanup report verified"
        except Exception as exc:
            operation.complete = True
            operation.succeeded = False
            operation.progress = "cleanup unconfirmed within retained deadline"
            code = (
                "CLEANUP_TIMEOUT"
                if isinstance(exc, TimeoutError)
                else "CLEANUP_ADMISSION_FAILED"
            )
            operation.failure.CopyFrom(types.Failure(code=code, message=str(exc)))
            recovery.progress = operation.progress
            recovery.completion_monotonic_ns = host_time_ns()
            recovery.outcome = types.RECOVERY_OUTCOME_FAILED
            recovery.failure.CopyFrom(operation.failure)
        finally:
            self.state.cleanup_events.pop(command.command_id, None)
        self.changed()

    def cleanup_blockers(self) -> list[types.CleanupBlocker]:
        if not self.registration.state.context:
            return []
        blockers = []
        for participant in self.registration.state.context.required_participants:
            if (
                participant.backend_name,
                participant.backend_generation,
            ) not in self.state.cleanup:
                blockers.append(
                    types.CleanupBlocker(
                        responsible=types.ProcessIdentity(
                            role=participant.backend_name,
                            generation=participant.backend_generation,
                        ),
                        work=self.registration.state.context.work,
                        resource="backend_cleanup",
                        reason=types.Failure(
                            code="MISSING_CLEANUP",
                            message="verified Cleanup report absent",
                        ),
                        recovery_action="retry_graceful_cleanup",
                    )
                )
        return blockers
