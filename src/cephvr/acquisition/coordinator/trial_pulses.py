"""Trial-bound MCU boundary execution and delivery (A05/A06)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from uuid import uuid4

from cephvr.acquisition.coordinator.manual_pulse_observation import (
    retain_applied_pulse_state,
)
from cephvr.acquisition.coordinator.trial_helpers import _external_roles
from cephvr.acquisition.coordinator.trial_lifecycle import TrialLifecycleReports
from cephvr.acquisition.ports import SerialOwnerPort
from cephvr.acquisition.state import (
    CoordinatorIdentity,
    PulseRecord,
    SessionRecord,
    TrialRecord,
    WorkerRecord,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns


class TrialPulseBoundaries:
    """Own bounded serial actions and exact worker evidence fanout for a trial."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        workers: dict[int, WorkerRecord],
        serial: SerialOwnerPort,
        pulse: PulseRecord,
        lifecycle: TrialLifecycleReports,
        serial_ack_timeout_ns: int,
        start_evidence_allowance_ns: int,
        lifecycle_delivery_ns: int,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.workers = workers
        self.serial = serial
        self.pulse = pulse
        self.lifecycle = lifecycle
        self.serial_ack_timeout_ns = serial_ack_timeout_ns
        self.start_evidence_allowance_ns = start_evidence_allowance_ns
        self.lifecycle_delivery_ns = lifecycle_delivery_ns
        self.clock = clock

    async def ensure_outputs_off(
        self, session: SessionRecord, deadline_ns: int
    ) -> None:
        if not _external_roles(session):
            return
        observation = await self.serial.status(deadline_ns=deadline_ns)
        if (
            not observation.HasField("state")
            or not observation.state.HasField("configuration_valid")
            or not observation.state.configuration_valid
        ):
            raise RuntimeError("MCU state is not valid before trial preparation")
        self.pulse.observation = mcu.MicrocontrollerObservation.FromString(
            observation.SerializeToString(deterministic=True)
        )
        now = self.clock()
        off_deadline_ns = min(deadline_ns, now + self.serial_ack_timeout_ns)
        off = await self.serial.off(
            (camera.CAMERA_ROLE_BEHAVIORAL, camera.CAMERA_ROLE_TRACKING),
            scheduled_boundary_ns=None,
            stop_issued_ns=now,
            deadline_ns=off_deadline_ns,
        )
        if (
            off.outcome != mcu.PULSE_COMMAND_OUTCOME_APPLIED
            or not off.HasField("resulting_state")
            or not _outputs_proven_off(off.resulting_state)
        ):
            raise RuntimeError(
                "MCU outputs are not confirmed OFF before trial preparation"
            )
        retain_applied_pulse_state(self.pulse, off, deadline_ns=off_deadline_ns)

    async def execute(
        self,
        session: SessionRecord,
        trial: TrialRecord,
        selected_roles: tuple[int, ...],
        *,
        command: mcu.PulseBoundaryCommand,
        boundary_ns: int,
    ) -> None:
        remaining = max(0, boundary_ns - self.clock()) / 1_000_000_000
        if remaining:
            await asyncio.sleep(remaining)
        cancelled_on = command == mcu.PULSE_BOUNDARY_COMMAND_ON and (
            session.interrupted or trial.interrupted or session.setup_cancelled
        )
        ack_deadline_ns = boundary_ns + self.serial_ack_timeout_ns
        delivery_deadline_ns = boundary_ns + (
            self.start_evidence_allowance_ns
            if command == mcu.PULSE_BOUNDARY_COMMAND_ON
            else self.lifecycle_delivery_ns
        )
        if command == mcu.PULSE_BOUNDARY_COMMAND_OFF:
            trial.pulse_delivery_deadline_ns = delivery_deadline_ns
        try:
            if cancelled_on:
                evidence = _failure_evidence(
                    selected_roles,
                    command,
                    boundary_ns,
                    mcu.PULSE_COMMAND_OUTCOME_NOT_DISPATCHED,
                )
                trial.pulse_on = evidence
            elif command == mcu.PULSE_BOUNDARY_COMMAND_ON:
                evidence = await self.serial.on(
                    selected_roles,
                    scheduled_boundary_ns=boundary_ns,
                    deadline_ns=ack_deadline_ns,
                )
                trial.pulse_on = evidence
            else:
                evidence = await self.serial.off(
                    selected_roles,
                    scheduled_boundary_ns=boundary_ns,
                    stop_issued_ns=None,
                    deadline_ns=ack_deadline_ns,
                )
                trial.pulse_off = evidence
        except TimeoutError:
            evidence = _failure_evidence(
                selected_roles,
                command,
                boundary_ns,
                mcu.PULSE_COMMAND_OUTCOME_TIMED_OUT,
            )
            _retain_boundary_result(trial, command, evidence)
            trial.interrupted = True
        except Exception:
            evidence = _failure_evidence(
                selected_roles,
                command,
                boundary_ns,
                mcu.PULSE_COMMAND_OUTCOME_TRANSPORT_FAILED,
            )
            _retain_boundary_result(trial, command, evidence)
            trial.interrupted = True

        if evidence.outcome == mcu.PULSE_COMMAND_OUTCOME_APPLIED:
            retain_applied_pulse_state(
                self.pulse, evidence, deadline_ns=ack_deadline_ns
            )
        await self.send_evidence(trial, evidence, delivery_deadline_ns)
        if evidence.outcome != mcu.PULSE_COMMAND_OUTCOME_APPLIED:
            trial.interrupted = True
        if command == mcu.PULSE_BOUNDARY_COMMAND_ON:
            trial.pulse_on_ready.set()
        else:
            trial.pulse_off_ready.set()
        await self.lifecycle.pulse_evidence_changed(trial)

    async def send_evidence(
        self,
        trial: TrialRecord,
        evidence: mcu.PulseCommandEvidence,
        deadline_ns: int,
    ) -> None:
        calls = []
        for worker in self.workers.values():
            if worker.port is None or worker.trial is None:
                continue
            command_id = str(uuid4())
            command = acq.WorkerCommand(
                command_id=command_id,
                issuer=self.identity.process,
                target=worker.context,
                parent_operation=trial.schedule
                or control.OperationContext(command_id=command_id),
            )
            command.target.work.CopyFrom(trial.work)
            pulse = acq.WorkerPulseEvidence(
                command=command,
                camera=worker.context.camera,
                evidence=evidence,
            )
            calls.append(
                worker.port.record_pulse_evidence(pulse, deadline_ns=deadline_ns)
            )
        if not calls:
            return
        results = await asyncio.gather(*calls, return_exceptions=True)
        if any(
            isinstance(result, BaseException)
            or result.result != control.COMMAND_RESULT_ACCEPTED
            for result in results
        ):
            trial.interrupted = True


def _retain_boundary_result(
    trial: TrialRecord,
    command: mcu.PulseBoundaryCommand,
    evidence: mcu.PulseCommandEvidence,
) -> None:
    if command == mcu.PULSE_BOUNDARY_COMMAND_ON:
        trial.pulse_on = evidence
    else:
        trial.pulse_off = evidence


def _failure_evidence(
    selected_roles: tuple[int, ...],
    command: mcu.PulseBoundaryCommand,
    boundary_ns: int,
    outcome: mcu.PulseCommandOutcome,
) -> mcu.PulseCommandEvidence:
    return mcu.PulseCommandEvidence(
        command=command,
        behavioral_selected=(camera.CAMERA_ROLE_BEHAVIORAL in selected_roles),
        tracking_selected=(camera.CAMERA_ROLE_TRACKING in selected_roles),
        scheduled_boundary_monotonic_ns=boundary_ns,
        outcome=outcome,
    )


def _outputs_proven_off(state: mcu.MicrocontrollerState) -> bool:
    return all(
        state.HasField(role)
        and getattr(state, role).HasField("running")
        and not getattr(state, role).running
        for role in ("behavioral", "tracking")
    )
