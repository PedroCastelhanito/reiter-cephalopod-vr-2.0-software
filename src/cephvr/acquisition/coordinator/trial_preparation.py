"""Trial admission, preparation, and prior-output closure gate (A02/A03/E05)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from uuid import UUID

from cephvr.acquisition.coordinator.commands import (
    retain_worker_command,
    wait_child_operation,
)
from cephvr.acquisition.coordinator.trial_helpers import (
    _camera_output_keys,
    _continuation_incidents_match,
    _rejected,
    _trial_finished,
)
from cephvr.acquisition.coordinator.trial_pulses import TrialPulseBoundaries
from cephvr.acquisition.ports import ControllerPort
from cephvr.acquisition.state import (
    CoordinatorIdentity,
    ResourceRecord,
    SessionRecord,
    SessionSlot,
    TrialRecord,
    WorkerRecord,
    WorkerTrial,
)
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns
from cephvr.shared.identity import require_uuid4


class TrialPreparation:
    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        session_slot: SessionSlot,
        workers: dict[int, WorkerRecord],
        resources: dict[str, ResourceRecord],
        controller: ControllerPort,
        prior_completion_confirmed: Callable[[TrialRecord], bool],
        pulse_boundaries: TrialPulseBoundaries,
        lock: asyncio.Lock,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.session_slot = session_slot
        self.workers = workers
        self.resources = resources
        self.controller = controller
        self.prior_completion_confirmed = prior_completion_confirmed
        self.pulse_boundaries = pulse_boundaries
        self.lock = lock
        self.clock = clock

    async def prepare(
        self, request: wire.PrepareTrialRequest, *, deadline_ns: int
    ) -> control.CommandAdmission:
        session = self.session_slot.current
        if not self.valid_command(request.command, session, deadline_ns):
            return _rejected(
                request.command.command_id,
                "TRIAL_IDENTITY",
                "trial Setup identity is stale",
            )
        assert session is not None
        if (
            session is None
            or session.ready_report is None
            or session.setup_cancelled
            or session.interrupted
            or session.confirmed_revision is None
            or request.configuration_revision != session.confirmed_revision
            or not request.HasField("plan")
            or request.plan.context.session.session_id
            != session.work.session.session_id
            or request.command.work.WhichOneof("work") != "trial"
            or request.command.work.trial != request.plan.context
            or not request.plan.HasField("resolved_duration_ns")
            or request.plan.resolved_duration_ns <= 0
            or not _continuation_incidents_match(
                session.confirmed_incidents, request.plan.continuation_incidents
            )
        ):
            return _rejected(
                request.command.command_id,
                "TRIAL_PREPARATION",
                "trial plan or confirmed Setup revision differs",
            )
        try:
            require_uuid4(request.plan.context.trial_id)
        except ValueError as exc:
            return _rejected(request.command.command_id, "TRIAL_ID", str(exc))
        async with self.lock:
            if self.session_slot.current is not session or session.interrupted:
                return _rejected(
                    request.command.command_id,
                    "TRIAL_STALE",
                    "session changed during trial admission",
                )
            previous = session.trial
            if previous is not None and not _trial_finished(previous):
                return _rejected(
                    request.command.command_id,
                    "PRIOR_TRIAL_OPEN",
                    "prior trial output closure remains unresolved",
                )
            prior_complete = previous is None or self.prior_completion_confirmed(
                previous
            )
            if not prior_complete:
                return _rejected(
                    request.command.command_id,
                    "PRIOR_CONSUMER_OPEN",
                    "prior producer and consumer completion is unconfirmed",
                )
            work = control.WorkContext(trial=request.plan.context)
            trial = TrialRecord(
                work=work,
                plan=control.TrialPlan.FromString(
                    request.plan.SerializeToString(deterministic=True)
                ),
                preparation=control.OperationContext(
                    command_id=request.command.command_id
                ),
                configuration_revision=session.confirmed_revision,
                outputs=[
                    control.OutputPlan.FromString(item.SerializeToString())
                    for item in request.outputs
                ],
                ready_deadline_ns=deadline_ns,
            )
            session.trial = trial
        try:
            await self.pulse_boundaries.ensure_outputs_off(session, deadline_ns)
            self._bind_session_rings(session, trial, deadline_ns, prior_complete)
            await self._prepare_workers(session, trial, request, deadline_ns)
            remaining = max(0, deadline_ns - self.clock()) / 1_000_000_000
            if remaining <= 0:
                raise TimeoutError("trial readiness missed its original deadline")
            await asyncio.wait_for(trial.ready_confirmed.wait(), remaining)
            if session.interrupted or session.setup_cancelled:
                raise RuntimeError("session was interrupted during trial preparation")
            receipt = await self.controller.report_lifecycle(
                control.LifecycleReport(
                    operation=control.BackendOperationReport(
                        source=self.identity.backend,
                        operation=control.OperationState(
                            context=trial.preparation,
                            command="PrepareTrial",
                            work=trial.work,
                            complete=True,
                            succeeded=True,
                        ),
                    )
                ),
                deadline_ns=deadline_ns,
            )
            if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError("controller rejected aggregate trial readiness")
            return control.CommandAdmission(
                result=control.COMMAND_RESULT_ACCEPTED,
                command_id=request.command.command_id,
            )
        except (TimeoutError, RuntimeError, ValueError) as exc:
            trial.interrupted = True
            return _rejected(
                request.command.command_id, "TRIAL_PREPARATION_FAILED", str(exc)
            )

    def _bind_session_rings(
        self,
        session: SessionRecord,
        trial: TrialRecord,
        deadline_ns: int,
        prior_completion_confirmed: bool,
    ) -> None:
        if self.clock() >= deadline_ns:
            raise TimeoutError("trial ring reset missed its original deadline")
        for resource in self.resources.values():
            descriptor = resource.attachment.buffer
            if (
                not descriptor.HasField("session")
                or descriptor.session != session.work.session
            ):
                continue
            if resource.ring is None:
                raise RuntimeError(
                    "ring allocation is incomplete and remains a cleanup blocker"
                )
            resource.ring.reset_quiescent(
                UUID(require_uuid4(trial.work.trial.trial_id)),
                prior_completion_confirmed=prior_completion_confirmed,
            )

    async def _prepare_workers(
        self,
        session: SessionRecord,
        trial: TrialRecord,
        request: wire.PrepareTrialRequest,
        deadline_ns: int,
    ) -> None:
        selected = [
            (role, self.workers.get(role)) for role in sorted(session.required_cameras)
        ]
        if any(worker is None or worker.port is None for _role, worker in selected):
            raise RuntimeError("registered camera worker is unavailable")
        dispatch = []
        for role, candidate in selected:
            assert candidate is not None and candidate.port is not None
            worker = candidate
            child, operation, port = retain_worker_command(
                worker,
                work=trial.work,
                parent_operation=control.OperationContext(
                    command_id=request.command.command_id
                ),
                kind="prepare_trial",
                deadline_ns=deadline_ns,
                configuration_revision=trial.configuration_revision,
            )
            worker.trial = WorkerTrial(
                configuration_revision=trial.configuration_revision,
                preparation=control.OperationContext(command_id=operation.command_id),
            )
            camera_prepare = acq.CameraWorkerTrialPreparation(
                allocation_ids=sorted(session.expected_attachments.get(role, set())),
            )
            camera_prepare.outputs.extend(
                item
                for item in request.outputs
                if item.backend == self.identity.backend
                and item.output_key in _camera_output_keys(trial, role)
            )
            dispatch.append(
                (
                    port,
                    acq.WorkerPrepareTrial(
                        command=child,
                        camera=camera_prepare,
                        required_configuration_revision=trial.configuration_revision,
                    ),
                )
            )
        calls = [
            port.prepare_trial(payload, deadline_ns=deadline_ns)
            for port, payload in dispatch
        ]
        results = await asyncio.gather(*calls, return_exceptions=True)
        if any(
            isinstance(item, BaseException)
            or item.result != control.COMMAND_RESULT_ACCEPTED
            for item in results
        ):
            raise RuntimeError("one or more camera workers rejected trial preparation")
        for _role, prepared_worker in selected:
            assert prepared_worker is not None and prepared_worker.trial is not None
            preparation = prepared_worker.trial.preparation
            if preparation is None:
                raise RuntimeError("camera trial preparation was not retained")
            result = await wait_child_operation(
                prepared_worker.child_operations[preparation.command_id],
                deadline_ns,
                self.lock,
                self.clock,
            )
            if not result.succeeded:
                raise RuntimeError(
                    f"camera role {prepared_worker.context.camera} trial preparation failed: "
                    f"{result.failure.code}: {result.failure.message}"
                )

    def valid_command(
        self,
        command: wire.BackendCommand,
        session: SessionRecord | None,
        deadline_ns: int,
    ) -> bool:
        return bool(
            session is not None
            and self.clock() < deadline_ns
            and command.command_id
            and command.issuer == self.identity.controller
            and command.target == self.identity.backend
            and command.work.WhichOneof("work") is not None
            and command.work.WhichOneof("work") == "trial"
            and command.work.trial.session.session_id == session.work.session.session_id
            and not session.setup_cancelled
            and not session.interrupted
        )
