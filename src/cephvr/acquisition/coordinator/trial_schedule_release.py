"""Exact trial Schedule/Release fanout and pulse boundary arming (A02/A05)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from cephvr.acquisition.coordinator.commands import (
    retain_worker_command,
    wait_child_operation,
)
from cephvr.acquisition.coordinator.manual_pulse_observation import (
    invalidate_released_idle_proof,
)
from cephvr.acquisition.coordinator.trial_helpers import (
    _camera_output_keys,
    _external_roles,
    _outputs_match,
    _rejected,
)
from cephvr.acquisition.coordinator.trial_termination import (
    NormalEndRunner,
    PulseBoundaryRunner,
)
from cephvr.acquisition.ports import SerialOwnerPort
from cephvr.acquisition.state import (
    CoordinatorIdentity,
    PulseRecord,
    SessionRecord,
    SessionSlot,
    WorkerRecord,
)
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns


class TrialScheduleRelease:
    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        session_slot: SessionSlot,
        workers: dict[int, WorkerRecord],
        serial: SerialOwnerPort,
        pulse: PulseRecord,
        serial_ack_timeout_ns: int,
        start_evidence_allowance_ns: int,
        lifecycle_delivery_ns: int,
        valid_command: Callable[[wire.BackendCommand, SessionRecord | None, int], bool],
        run_pulse_boundary: PulseBoundaryRunner,
        run_normal_end: NormalEndRunner,
        lock: asyncio.Lock,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.session_slot = session_slot
        self.workers = workers
        self.serial = serial
        self.pulse = pulse
        self.serial_ack_timeout_ns = serial_ack_timeout_ns
        self.start_evidence_allowance_ns = start_evidence_allowance_ns
        self.lifecycle_delivery_ns = lifecycle_delivery_ns
        self._valid_command = valid_command
        self._run_pulse_boundary = run_pulse_boundary
        self._run_normal_end = run_normal_end
        self.lock = lock
        self.clock = clock

    async def schedule(
        self, request: wire.ScheduleTrialRequest, *, deadline_ns: int
    ) -> control.CommandAdmission:
        session = self.session_slot.current
        trial = session.trial if session is not None else None
        if (
            not self._valid_command(request.command, session, deadline_ns)
            or trial is None
        ):
            return _rejected(
                request.command.command_id, "TRIAL_IDENTITY", "no live prepared trial"
            )
        assert session is not None
        if (
            not trial.ready_confirmed.is_set()
            or trial.schedule is not None
            or request.command.work != trial.work
            or not trial.plan.HasField("resolved_duration_ns")
            or request.start_monotonic_ns <= 0
            or request.normal_end_monotonic_ns - request.start_monotonic_ns
            != trial.plan.resolved_duration_ns
            or request.trial_file_prefix == ""
        ):
            return _rejected(
                request.command.command_id,
                "TRIAL_SCHEDULE",
                "schedule differs from exact prepared trial duration or state",
            )
        if self.clock() >= deadline_ns:
            return _rejected(
                request.command.command_id, "DEADLINE", "schedule deadline expired"
            )
        if not _outputs_match(trial.outputs, request.outputs, self.identity.backend):
            return _rejected(
                request.command.command_id,
                "TRIAL_OUTPUTS",
                "scheduled outputs differ from prepared camera output plans",
            )
        session.dispatched_output_keys.update(
            item.output_key
            for item in request.outputs
            if item.backend == self.identity.backend
        )
        worker_pairs = [
            (role, self.workers.get(role)) for role in sorted(session.required_cameras)
        ]
        if any(
            worker is None or worker.port is None or worker.trial is None
            for _role, worker in worker_pairs
        ):
            return _rejected(
                request.command.command_id,
                "WORKER_MISSING",
                "registered camera worker or trial preparation is unavailable",
            )
        selected = _external_roles(session)
        dispatch = []
        for role, candidate in worker_pairs:
            assert candidate is not None and candidate.port is not None
            worker = candidate
            child, operation, port = retain_worker_command(
                worker,
                work=trial.work,
                parent_operation=control.OperationContext(
                    command_id=request.command.command_id
                ),
                kind="schedule_trial",
                deadline_ns=deadline_ns,
                configuration_revision=trial.configuration_revision,
            )
            worker_trial = worker.trial
            assert worker_trial is not None
            worker_trial.schedule = control.OperationContext(
                command_id=operation.command_id
            )
            outputs = [
                item
                for item in request.outputs
                if item.backend == self.identity.backend
                and item.output_key in _camera_output_keys(trial, role)
            ]
            payload = acq.WorkerSchedule(
                command=child,
                start_monotonic_ns=request.start_monotonic_ns,
                end_monotonic_ns=request.normal_end_monotonic_ns,
                trial_file_prefix=request.trial_file_prefix,
                outputs=outputs,
            )
            dispatch.append((port, payload))
        # Retain the exact intent before awaits: Release may be admitted while
        # MCU reservations and worker Schedule executors are still in progress.
        trial.schedule = control.OperationContext(command_id=request.command.command_id)
        trial.start_monotonic_ns = request.start_monotonic_ns
        trial.end_monotonic_ns = request.normal_end_monotonic_ns
        trial.outputs = [
            control.OutputPlan.FromString(item.SerializeToString())
            for item in request.outputs
            if item.backend == self.identity.backend
        ]
        if selected:
            try:
                invalidate_released_idle_proof(self.pulse)
                await self.serial.reserve_boundary(
                    request.start_monotonic_ns,
                    mcu.PULSE_BOUNDARY_COMMAND_ON,
                    selected_roles=selected,
                    deadline_ns=deadline_ns,
                )
                await self.serial.reserve_boundary(
                    request.normal_end_monotonic_ns,
                    mcu.PULSE_BOUNDARY_COMMAND_OFF,
                    selected_roles=selected,
                    deadline_ns=deadline_ns,
                )
            except (ValueError, TimeoutError, RuntimeError) as exc:
                try:
                    await self.serial.cancel_on_reservations(deadline_ns=deadline_ns)
                except (TimeoutError, RuntimeError):
                    pass
                return _rejected(request.command.command_id, "PULSE_BOUNDARY", str(exc))
        tasks = [
            port.schedule_trial(payload, deadline_ns=deadline_ns)
            for port, payload in dispatch
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        if any(
            isinstance(item, BaseException)
            or item.result != control.COMMAND_RESULT_ACCEPTED
            for item in responses
        ):
            if selected:
                try:
                    await self.serial.cancel_on_reservations(deadline_ns=deadline_ns)
                except (TimeoutError, RuntimeError):
                    pass
            return _rejected(
                request.command.command_id,
                "WORKER_SCHEDULE",
                "one or more camera workers rejected Schedule",
            )
        trial.pulse_delivery_deadline_ns = (
            request.normal_end_monotonic_ns + self.lifecycle_delivery_ns
        )
        trial.trial_file_prefix = request.trial_file_prefix
        return control.CommandAdmission(
            result=control.COMMAND_RESULT_ACCEPTED,
            command_id=request.command.command_id,
        )

    async def release(
        self, request: wire.ReleaseTrialRequest, *, deadline_ns: int
    ) -> control.CommandAdmission:
        session = self.session_slot.current
        trial = session.trial if session is not None else None
        if (
            not self._valid_command(request.command, session, deadline_ns)
            or trial is None
        ):
            return _rejected(
                request.command.command_id, "TRIAL_IDENTITY", "no live scheduled trial"
            )
        assert session is not None
        if (
            trial.schedule is None
            or trial.release is not None
            or request.command.work != trial.work
            or request.schedule_operation != trial.schedule
            or request.start_monotonic_ns != trial.start_monotonic_ns
            or request.normal_end_monotonic_ns != trial.end_monotonic_ns
        ):
            return _rejected(
                request.command.command_id,
                "TRIAL_RELEASE",
                "release does not exactly match the retained schedule",
            )
        worker_pairs = [
            (role, self.workers.get(role)) for role in sorted(session.required_cameras)
        ]
        if any(
            worker is None or worker.port is None or worker.trial is None
            for _role, worker in worker_pairs
        ):
            return _rejected(
                request.command.command_id,
                "WORKER_MISSING",
                "scheduled camera worker is unavailable",
            )
        dispatch = []
        for _role, candidate in worker_pairs:
            assert candidate is not None and candidate.port is not None
            worker = candidate
            assert worker.trial is not None
            scheduled = worker.trial.schedule
            if scheduled is None:
                return _rejected(
                    request.command.command_id,
                    "WORKER_SCHEDULE",
                    "camera has no retained Schedule",
                )
            child_schedule = worker.child_operations[scheduled.command_id]
            outcome = await wait_child_operation(
                child_schedule,
                min(deadline_ns, child_schedule.deadline_ns or deadline_ns),
                self.lock,
                self.clock,
            )
            if not outcome.succeeded:
                return _rejected(
                    request.command.command_id,
                    "WORKER_SCHEDULE",
                    outcome.failure.message,
                )
            child, operation, port = retain_worker_command(
                worker,
                work=trial.work,
                parent_operation=control.OperationContext(
                    command_id=request.command.command_id
                ),
                kind="release_trial",
                deadline_ns=deadline_ns,
                configuration_revision=trial.configuration_revision,
            )
            worker.trial.release = control.OperationContext(
                command_id=operation.command_id
            )
            dispatch.append(
                (
                    port,
                    acq.WorkerRelease(
                        command=child,
                        schedule_operation=worker.trial.schedule,
                        start_monotonic_ns=request.start_monotonic_ns,
                        end_monotonic_ns=request.normal_end_monotonic_ns,
                    ),
                )
            )
        calls = [
            port.release_trial(payload, deadline_ns=deadline_ns)
            for port, payload in dispatch
        ]
        results = await asyncio.gather(*calls, return_exceptions=True)
        if any(
            isinstance(item, BaseException)
            or item.result != control.COMMAND_RESULT_ACCEPTED
            for item in results
        ):
            return _rejected(
                request.command.command_id,
                "WORKER_RELEASE",
                "one or more camera workers rejected Release",
            )
        trial.release = control.OperationContext(command_id=request.command.command_id)
        for worker in self.workers.values():
            if worker.trial is not None:
                worker.trial.released = True
        selected_roles = _external_roles(session)
        if selected_roles:
            if trial.start_monotonic_ns is None or trial.end_monotonic_ns is None:
                return _rejected(
                    request.command.command_id,
                    "PULSE_SCHEDULE_MISSING",
                    "external trigger trial has no retained pulse boundaries",
                )
            trial.pulse_on_task = asyncio.create_task(
                self._run_pulse_boundary(
                    session,
                    trial,
                    selected_roles,
                    command=mcu.PULSE_BOUNDARY_COMMAND_ON,
                    boundary_ns=trial.start_monotonic_ns,
                )
            )
            trial.pulse_off_task = asyncio.create_task(
                self._run_pulse_boundary(
                    session,
                    trial,
                    selected_roles,
                    command=mcu.PULSE_BOUNDARY_COMMAND_OFF,
                    boundary_ns=trial.end_monotonic_ns,
                )
            )
        trial.normal_end_task = asyncio.create_task(
            self._run_normal_end(session, trial)
        )
        return control.CommandAdmission(
            result=control.COMMAND_RESULT_ACCEPTED,
            command_id=request.command.command_id,
        )
