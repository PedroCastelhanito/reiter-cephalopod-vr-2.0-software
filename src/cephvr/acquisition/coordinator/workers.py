"""Registered camera-worker ownership and restart boundaries (A02/E08)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from cephvr.acquisition.coordinator.commands import (
    retain_worker_command,
    wait_child_operation,
)
from cephvr.acquisition.identity import process_role_for_camera
from cephvr.acquisition.ports import (
    ExecutableResolver,
    SupervisorPort,
    WorkerBootstrapPort,
    WorkerLaunchSpec,
)
from cephvr.acquisition.state import ChildOperation, LaunchRecord, WorkerRecord
from cephvr.acquisition.v1 import camera_pb2, runtime_pb2
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger
from cephvr.shared.deadlines import remaining_seconds


class WorkerRegistry:
    """Own the sole camera-role -> WorkerRecord catalogue for a coordinator."""

    def __init__(
        self,
        *,
        workers: dict[int, WorkerRecord],
        launches: dict[str, LaunchRecord],
        commands: CommandLedger,
        owner: control.ProcessIdentity,
        policies: control.ControlPolicies,
        file_policies: runtime_pb2.AcquisitionFilePolicies,
        coordinator_endpoint: str,
        heartbeat_interval_ns: int,
        health_silence_ns: int,
        bootstrap: WorkerBootstrapPort,
        executables: ExecutableResolver,
        supervisor: SupervisorPort,
        cleanup_complete: Callable[[WorkerRecord, acq.WorkerCleanupEvidence], bool],
        max_launch_records: int = 1024,
    ) -> None:
        self.workers = workers
        self.launches = launches
        self.commands = commands
        self.owner = control.ProcessIdentity.FromString(owner.SerializeToString())
        self.policies = control.ControlPolicies.FromString(policies.SerializeToString())
        self.file_policies = runtime_pb2.AcquisitionFilePolicies.FromString(
            file_policies.SerializeToString()
        )
        if not coordinator_endpoint:
            raise ValueError("worker bootstrap requires coordinator endpoint")
        self.coordinator_endpoint = coordinator_endpoint
        if heartbeat_interval_ns <= 0 or health_silence_ns <= heartbeat_interval_ns:
            raise ValueError("worker health cadence must fit its silence bound")
        self.heartbeat_interval_ns = heartbeat_interval_ns
        self.health_silence_ns = health_silence_ns
        self.bootstrap = bootstrap
        self.executables = executables
        if max_launch_records <= 0:
            raise ValueError("worker launch retention bound must be positive")
        self.supervisor = supervisor
        self.cleanup_complete = cleanup_complete
        self.max_launch_records = max_launch_records
        self._lock = asyncio.Lock()

    async def launch(
        self,
        camera: camera_pb2.CameraRole,
        work: control.WorkContext | None,
        parent_operation: control.OperationContext,
        *,
        deadline_ns: int,
        policies: control.ControlPolicies | None = None,
        file_policy: runtime_pb2.CameraFilePolicy | None = None,
    ) -> WorkerRecord:
        """Retain exact launch intent before process creation can partially succeed."""
        if host_time_ns() >= deadline_ns:
            raise TimeoutError("worker launch deadline expired before admission")
        role = process_role_for_camera(camera)
        selected_file_policy = (
            self._file_policy(camera) if file_policy is None else file_policy
        )
        executable, python_worker, stop_method = self.executables.resolve_worker(camera)
        generation = str(uuid4())
        command_id = str(uuid4())
        worker_identity = control.ProcessIdentity(role=role, generation=generation)
        context = acq.WorkerContext(
            worker=worker_identity, owner=self.owner, camera=camera
        )
        if work is not None:
            context.work.CopyFrom(work)
        if not parent_operation.command_id:
            raise ValueError("worker launch requires its parent operation")
        work_copy = control.WorkContext()
        if work is not None:
            work_copy.CopyFrom(work)
        launch = LaunchRecord(
            command_id=command_id,
            worker=worker_identity,
            owner=self.owner,
            work=work_copy,
            camera=camera,
            parent_operation=control.OperationContext(
                command_id=parent_operation.command_id
            ),
            planned_ns=host_time_ns(),
        )
        record = WorkerRecord(
            context=context, port=None, launch=launch, commands=self.commands
        )
        async with self._lock:
            if camera in self.workers:
                raise RuntimeError("camera role already has a retained worker")
            self._prune_launches_locked()
            if len(self.launches) >= self.max_launch_records:
                raise RuntimeError("retained worker launch capacity exhausted")
            self.launches[command_id] = launch
            self.workers[camera] = record
        selected_policies = self.policies if policies is None else policies
        spec = WorkerLaunchSpec(
            launch_command_id=command_id,
            parent_operation=launch.parent_operation,
            context=context,
            file_policy=runtime_pb2.CameraFilePolicy.FromString(
                selected_file_policy.SerializeToString(deterministic=True)
            ),
            control_policies=selected_policies,
            coordinator_endpoint=self.coordinator_endpoint,
            heartbeat_interval_ns=self.heartbeat_interval_ns,
            health_silence_ns=self.health_silence_ns,
            executable=Path(executable),
            python_worker=python_worker,
            stop_method=stop_method,
        )
        try:
            result = await self.bootstrap.launch(spec, deadline_ns=deadline_ns)
            if (
                result.context != context
                or result.pid <= 0
                or result.creation_time_100ns <= 0
                or not result.endpoint
            ):
                raise RuntimeError("worker launcher returned another registration")
        except BaseException as exc:
            launch.failure = control.Failure(
                code="WORKER_LAUNCH_UNCONFIRMED", message=str(exc)[:2048]
            )
            raise
        async with self._lock:
            launch.process_confirmed = True
            launch.endpoint_confirmed = True
            launch.pid = result.pid
            launch.creation_time_100ns = result.creation_time_100ns
            launch.endpoint = result.endpoint
            record.port = result.port
            record.alive = True
        return record

    async def retire_sessionless_worker(
        self, camera: camera_pb2.CameraRole, *, deadline_ns: int
    ) -> None:
        """Close a Configuration worker before creating a session-bound worker."""
        async with self._lock:
            record = self.workers.get(camera)
        if record is None:
            return
        if record.context.HasField("work"):
            raise RuntimeError("session-bound worker cannot be retired as a preview")
        if record.port is None:
            raise RuntimeError("partial worker launch remains a cleanup blocker")
        request, child, port = retain_worker_command(
            record,
            work=None,
            parent_operation=control.OperationContext(command_id=str(uuid4())),
            kind="cleanup",
            deadline_ns=deadline_ns,
        )
        command_id = request.command_id
        receipt = await port.cleanup(request, deadline_ns=deadline_ns)
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError("configuration worker cleanup was not admitted")
        cleanup = await _wait_cleanup_evidence(record, child, deadline_ns=deadline_ns)
        if cleanup is None or child.report is None or not child.report.complete:
            retained = await record.port.get_retained_result(
                acq.WorkerRetainedResultQuery(
                    query=acq.WorkerQuery(target=record.context), command_id=command_id
                ),
                deadline_ns=deadline_ns,
            )
            if cleanup is None:
                cleanup = _retained_cleanup(record, command_id, retained)
            _adopt_retained_operation(record, child, command_id, retained)
        if cleanup is None:
            raise RuntimeError(
                "configuration worker cleanup completion remains unconfirmed"
            )
        operation = await wait_child_operation(child, deadline_ns, self._lock)
        if (
            not operation.complete
            or not operation.HasField("succeeded")
            or not operation.succeeded
            or operation.command != "Cleanup"
            or operation.failure.code
            or operation.failure.message
        ):
            raise RuntimeError("configuration worker Cleanup operation is unconfirmed")
        if not self.cleanup_complete(record, cleanup.cleanup):
            raise RuntimeError(
                "configuration worker still has unresolved cleanup obligations"
            )
        cleanup_proof = wire.AcquisitionWorkerCleanupProof(
            operation=acq.WorkerOperationReport(
                source=record.context, operation=child.report
            ),
            cleanup=cleanup,
        )
        confirmation = self._worker_cleanup_confirmation(record, cleanup_proof)
        acknowledged = await self._confirm_worker_cleanup(
            record, confirmation, deadline_ns
        )
        if acknowledged.phase != wire.LAUNCH_PHASE_OPERATIONAL:
            raise RuntimeError("configuration worker cleanup acknowledgement failed")
        shutdown_id = str(uuid4())
        shutdown = acq.WorkerCommand(
            command_id=shutdown_id,
            issuer=self.owner,
            target=record.context,
            parent_operation=control.OperationContext(command_id=shutdown_id),
        )
        receipt = await record.port.shutdown(shutdown, deadline_ns=deadline_ns)
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError("configuration worker shutdown was not admitted")
        if not await self.bootstrap.wait_process_exit(
            record.launch.worker, deadline_ns=deadline_ns
        ):
            raise RuntimeError(
                "configuration worker process/job release is unconfirmed"
            )
        launch_state = await self._confirm_worker_cleanup(
            record, confirmation, deadline_ns
        )
        if launch_state.phase != wire.LAUNCH_PHASE_RELEASED:
            raise RuntimeError(
                "configuration worker process/job release is unconfirmed"
            )
        close = getattr(record.port, "close", None)
        if callable(close):
            await close()
        await self.bootstrap.retire(record.launch.worker, deadline_ns=deadline_ns)
        async with self._lock:
            record.launch.terminal_ns = host_time_ns()
            record.alive = False
            self.workers.pop(camera, None)
            self._prune_launches_locked()

    async def retire_completed_session(
        self, work: control.WorkContext, *, deadline_ns: int
    ) -> None:
        """Retire exact session workers only after accepted aggregate cleanup."""
        if work.WhichOneof("work") != "session":
            raise ValueError("worker retirement requires an exact session context")
        async with self._lock:
            selected = [
                (role, record)
                for role, record in self.workers.items()
                if record.context.work == work
            ]
        for role, record in selected:
            if record.port is None:
                raise RuntimeError("completed session worker endpoint is unavailable")
            cleanup_evidence = next(
                (
                    item
                    for item in record.lifecycle_evidence.values()
                    if item.source.work == work
                    and item.WhichOneof("evidence") == "cleanup"
                ),
                None,
            )
            cleanup_child = (
                record.child_operations.get(cleanup_evidence.operation.command_id)
                if cleanup_evidence is not None
                else None
            )
            if (
                cleanup_evidence is None
                or cleanup_child is None
                or cleanup_child.report is None
                or not cleanup_child.report.complete
                or not cleanup_child.report.HasField("succeeded")
                or not cleanup_child.report.succeeded
                or not self.cleanup_complete(record, cleanup_evidence.cleanup)
            ):
                raise RuntimeError("session worker cleanup is not fully retained")
            cleanup_proof = wire.AcquisitionWorkerCleanupProof(
                operation=acq.WorkerOperationReport(
                    source=record.context, operation=cleanup_child.report
                ),
                cleanup=cleanup_evidence,
            )
            confirmation = self._worker_cleanup_confirmation(record, cleanup_proof)
            acknowledged = await self._confirm_worker_cleanup(
                record, confirmation, deadline_ns
            )
            if acknowledged.phase != wire.LAUNCH_PHASE_OPERATIONAL:
                raise RuntimeError("session worker cleanup acknowledgement failed")
            parent = cleanup_child.parent_operation
            shutdown_request, _child, port = retain_worker_command(
                record,
                work=work,
                parent_operation=parent,
                kind="shutdown",
                deadline_ns=deadline_ns,
                configuration_revision=cleanup_child.configuration_revision,
            )
            receipt = await port.shutdown(shutdown_request, deadline_ns=deadline_ns)
            if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError("completed session worker rejected Shutdown")
            if not await self.bootstrap.wait_process_exit(
                record.launch.worker, deadline_ns=deadline_ns
            ):
                raise RuntimeError("session worker process/job release is unconfirmed")
            launch_state = await self._confirm_worker_cleanup(
                record, confirmation, deadline_ns
            )
            if launch_state.phase != wire.LAUNCH_PHASE_RELEASED:
                raise RuntimeError("session worker containment release is unconfirmed")
            close = getattr(port, "close", None)
            if callable(close):
                await close()
            await self.bootstrap.retire(record.launch.worker, deadline_ns=deadline_ns)
            async with self._lock:
                record.launch.terminal_ns = host_time_ns()
                record.alive = False
                self.workers.pop(role, None)
                self._prune_launches_locked()

    def _worker_cleanup_confirmation(
        self,
        record: WorkerRecord,
        proof: wire.AcquisitionWorkerCleanupProof,
    ) -> wire.ConfirmLaunchRequest:
        if record.launch.pid is None or record.launch.creation_time_100ns is None:
            raise RuntimeError("camera worker exact process identity is unavailable")
        return wire.ConfirmLaunchRequest(
            command_id=str(uuid4()),
            launch_command_id=record.launch.command_id,
            owner=self.owner,
            child=record.launch.worker,
            pid=record.launch.pid,
            creation_time_100ns=record.launch.creation_time_100ns,
            acquisition_worker_cleanup=proof,
        )

    async def _confirm_worker_cleanup(
        self,
        record: WorkerRecord,
        request: wire.ConfirmLaunchRequest,
        deadline_ns: int,
    ) -> wire.LaunchState:
        """Retain or reconcile the same exact owner-verified Cleanup proof."""
        receipt = await self.supervisor.confirm_launch(
            request,
            deadline_ns=deadline_ns,
        )
        if receipt.admission.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError(
                "camera worker containment release was rejected: "
                f"{receipt.admission.failure.code if receipt.admission.HasField('failure') else 'unknown'}"
            )
        return receipt.state

    def _prune_launches_locked(self) -> None:
        """Retire only terminal facts after the configured E08 retention window."""
        now = host_time_ns()
        retention = self.policies.command_retention_after_finalization_ns
        terminal = sorted(
            (
                item
                for item in self.launches.values()
                if item.terminal_ns is not None and now > item.terminal_ns + retention
            ),
            key=lambda item: item.terminal_ns or 0,
        )
        while len(self.launches) >= self.max_launch_records and terminal:
            expired = terminal.pop(0)
            self.launches.pop(expired.command_id, None)

    def _file_policy(
        self, camera: camera_pb2.CameraRole
    ) -> runtime_pb2.CameraFilePolicy:
        matches = [item for item in self.file_policies.cameras if item.camera == camera]
        if len(matches) != 1:
            raise ValueError("file policies do not contain exactly one camera role")
        result = runtime_pb2.CameraFilePolicy()
        result.CopyFrom(matches[0])
        return result


async def _wait_cleanup_evidence(
    record: WorkerRecord, child: ChildOperation, *, deadline_ns: int
) -> acq.WorkerLifecycleEvidence | None:
    while True:
        evidence = _find_cleanup_evidence(record, child.command_id)
        if evidence is not None:
            return evidence
        remaining = remaining_seconds(deadline_ns, clock=host_time_ns)
        if remaining <= 0:
            return None
        child.updated.clear()
        try:
            await asyncio.wait_for(child.updated.wait(), remaining)
        except TimeoutError:
            return None


def _find_cleanup_evidence(
    record: WorkerRecord, command_id: str
) -> acq.WorkerLifecycleEvidence | None:
    candidates = [
        evidence
        for evidence in record.lifecycle_evidence.values()
        if evidence.operation.command_id == command_id
        and evidence.WhichOneof("evidence") == "cleanup"
    ]
    if len(candidates) > 1:
        raise RuntimeError("cleanup command has duplicate retained lifecycle evidence")
    return (
        None
        if not candidates
        else acq.WorkerLifecycleEvidence.FromString(
            candidates[0].SerializeToString(deterministic=True)
        )
    )


def _retained_cleanup(
    record: WorkerRecord,
    command_id: str,
    retained: acq.WorkerRetainedResult,
) -> acq.WorkerLifecycleEvidence | None:
    if (
        not retained.found
        or retained.source != record.context
        or retained.admission.result != control.COMMAND_RESULT_ACCEPTED
    ):
        return None
    matches = [
        item
        for item in retained.lifecycle
        if item.operation.command_id == command_id
        and item.WhichOneof("evidence") == "cleanup"
    ]
    if len(matches) != 1 or matches[0].source != record.context:
        return None
    local = _find_cleanup_evidence(record, command_id)
    if local is not None and local.SerializeToString(deterministic=True) != matches[
        0
    ].SerializeToString(deterministic=True):
        raise RuntimeError("retained cleanup differs from accepted worker evidence")
    return acq.WorkerLifecycleEvidence.FromString(
        matches[0].SerializeToString(deterministic=True)
    )


def _retained_operation(
    record: WorkerRecord,
    command_id: str,
    retained: acq.WorkerRetainedResult,
) -> acq.WorkerOperationReport | None:
    if (
        not retained.found
        or retained.source != record.context
        or retained.admission.result != control.COMMAND_RESULT_ACCEPTED
        or not retained.HasField("operation")
        or retained.operation.source != record.context
        or retained.operation.operation.context.command_id != command_id
        or retained.operation.operation.command != "Cleanup"
        or not retained.operation.operation.complete
        or not retained.operation.operation.HasField("succeeded")
        or not retained.operation.operation.succeeded
        or retained.operation.operation.failure.code
        or retained.operation.operation.failure.message
        or not retained.operation.HasField("state_revision")
        or retained.operation.operation.work != record.context.work
    ):
        return None
    return acq.WorkerOperationReport.FromString(
        retained.operation.SerializeToString(deterministic=True)
    )


def _adopt_retained_operation(
    record: WorkerRecord,
    child: ChildOperation,
    command_id: str,
    retained: acq.WorkerRetainedResult,
) -> None:
    """Adopt exact query recovery without replacing conflicting local evidence."""
    report = _retained_operation(record, command_id, retained)
    if report is None:
        return
    state = report.operation
    revision = report.state_revision
    if child.report is not None and child.report.complete:
        if child.report.SerializeToString(
            deterministic=True
        ) != state.SerializeToString(deterministic=True):
            raise RuntimeError("retained Cleanup differs from local terminal operation")
        if revision >= child.report_revision:
            child.report_revision = revision
        return
    if revision < child.report_revision:
        return
    if (
        revision == child.report_revision
        and child.report is not None
        and child.report.SerializeToString(deterministic=True)
        != state.SerializeToString(deterministic=True)
    ):
        raise RuntimeError("retained Cleanup conflicts at the local operation revision")
    child.report = control.OperationState.FromString(
        state.SerializeToString(deterministic=True)
    )
    child.report_ingress_ns = host_time_ns()
    child.report_revision = revision
    child.updated.set()
