"""Exact session-bound trial command surface over focused trial stages."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from cephvr.acquisition.coordinator.trial_lifecycle import TrialLifecycleReports
from cephvr.acquisition.coordinator.trial_preparation import TrialPreparation
from cephvr.acquisition.coordinator.trial_pulses import TrialPulseBoundaries
from cephvr.acquisition.coordinator.trial_schedule_release import TrialScheduleRelease
from cephvr.acquisition.coordinator.trial_termination import TrialTermination
from cephvr.acquisition.ports import ControllerPort, SerialOwnerPort
from cephvr.acquisition.state import (
    CoordinatorIdentity,
    PulseRecord,
    ResourceRecord,
    SessionSlot,
    TrialRecord,
    WorkerRecord,
)
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns


class TrialCoordinator:
    """Expose trial admission/scheduling/termination over distinct owners."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        session_slot: SessionSlot,
        workers: dict[int, WorkerRecord],
        resources: dict[str, ResourceRecord],
        serial: SerialOwnerPort,
        pulse: PulseRecord,
        serial_ack_timeout_ns: int,
        start_evidence_allowance_ns: int,
        lifecycle_delivery_ns: int,
        stop_evidence_allowance_ns: int,
        controller: ControllerPort,
        lifecycle: TrialLifecycleReports,
        prior_completion_confirmed: Callable[[TrialRecord], bool],
        lock: asyncio.Lock,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        if (
            min(
                serial_ack_timeout_ns,
                start_evidence_allowance_ns,
                lifecycle_delivery_ns,
                stop_evidence_allowance_ns,
            )
            <= 0
        ):
            raise ValueError("trial timing allowances must be positive")
        boundaries = TrialPulseBoundaries(
            identity=identity,
            workers=workers,
            serial=serial,
            pulse=pulse,
            lifecycle=lifecycle,
            serial_ack_timeout_ns=serial_ack_timeout_ns,
            start_evidence_allowance_ns=start_evidence_allowance_ns,
            lifecycle_delivery_ns=lifecycle_delivery_ns,
            clock=clock,
        )
        self.preparation = TrialPreparation(
            identity=identity,
            session_slot=session_slot,
            workers=workers,
            resources=resources,
            controller=controller,
            prior_completion_confirmed=prior_completion_confirmed,
            pulse_boundaries=boundaries,
            lock=lock,
            clock=clock,
        )
        self.termination = TrialTermination(
            identity=identity,
            session_slot=session_slot,
            workers=workers,
            serial=serial,
            pulse=pulse,
            pulse_boundaries=boundaries,
            stop_evidence_allowance_ns=stop_evidence_allowance_ns,
            start_evidence_allowance_ns=start_evidence_allowance_ns,
            lifecycle_delivery_ns=lifecycle_delivery_ns,
            valid_command=self.preparation.valid_command,
            lock=lock,
            clock=clock,
        )
        self.scheduling = TrialScheduleRelease(
            identity=identity,
            session_slot=session_slot,
            workers=workers,
            serial=serial,
            serial_ack_timeout_ns=serial_ack_timeout_ns,
            start_evidence_allowance_ns=start_evidence_allowance_ns,
            lifecycle_delivery_ns=lifecycle_delivery_ns,
            valid_command=self.preparation.valid_command,
            run_pulse_boundary=self.termination.run_pulse_boundary,
            clock=clock,
        )

    async def prepare(
        self, request: wire.PrepareTrialRequest, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return await self.preparation.prepare(request, deadline_ns=deadline_ns)

    async def schedule(
        self, request: wire.ScheduleTrialRequest, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return await self.scheduling.schedule(request, deadline_ns=deadline_ns)

    async def release(
        self, request: wire.ReleaseTrialRequest, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return await self.scheduling.release(request, deadline_ns=deadline_ns)

    async def stop(
        self,
        request: wire.StopTrialRequest,
        *,
        deadline_ns: int,
        aborted: bool = False,
        internal: bool = False,
    ) -> control.CommandAdmission:
        return await self.termination.stop(
            request, deadline_ns=deadline_ns, aborted=aborted, internal=internal
        )

    async def interrupt_session(
        self, request: wire.InterruptSessionRequest, *, deadline_ns: int
    ) -> control.CommandAdmission:
        return await self.termination.interrupt_session(
            request, deadline_ns=deadline_ns
        )

    def control_pulse_failure_allowance(self, command: mcu.PulseBoundaryCommand) -> int:
        return self.termination.control_pulse_failure_allowance(command)
