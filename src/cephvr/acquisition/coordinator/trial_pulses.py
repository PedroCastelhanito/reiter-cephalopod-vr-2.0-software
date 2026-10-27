"""Trial-bound MCU boundary execution and delivery (A05/A06)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from cephvr.acquisition.coordinator.commands import retain_worker_command
from cephvr.acquisition.coordinator.manual_pulse_observation import (
    invalidate_released_idle_proof,
    retain_applied_pulse_state,
    retain_observation,
)
from cephvr.acquisition.coordinator.session_pulses import (
    capture_output_roles,
    capture_outputs_running,
)
from cephvr.acquisition.coordinator.trial_helpers import _trial_output_roles
from cephvr.acquisition.coordinator.trial_lifecycle import TrialLifecycleReports
from cephvr.acquisition.ports import SerialOwnerPort
from cephvr.acquisition.state import (
    CoordinatorIdentity,
    PulseRecord,
    SessionRecord,
    SessionSlot,
    TrialRecord,
    WorkerRecord,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns
from cephvr.shared.deadlines import wait_until_ns


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
        session_slot: SessionSlot,
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
        self.session_slot = session_slot
        self.serial_ack_timeout_ns = serial_ack_timeout_ns
        self.start_evidence_allowance_ns = start_evidence_allowance_ns
        self.lifecycle_delivery_ns = lifecycle_delivery_ns
        self.clock = clock

    async def ensure_outputs_off(
        self, session: SessionRecord, deadline_ns: int
    ) -> None:
        if not _trial_output_roles(session) and not capture_output_roles(session):
            return
        observation = await self.serial.status(deadline_ns=deadline_ns)
        if (
            not observation.HasField("state")
            or not observation.state.HasField("configuration_valid")
            or not observation.state.configuration_valid
            or not capture_outputs_running(session, observation.state)
        ):
            raise RuntimeError("MCU state is not valid before trial preparation")
        settings = session.confirmed_settings
        if settings is not None and settings.pulses.trial_state_enabled:
            output = observation.state.trial_state
            if (
                not output.HasField("enabled")
                or not output.enabled
                or output.pin != settings.pulses.trial_state_pin
                or observation.state.watchdog_stopped
            ):
                raise RuntimeError("Trial state output differs from locked settings")
        retain_observation(
            self.pulse,
            mcu.MicrocontrollerObservation.FromString(
                observation.SerializeToString(deterministic=True)
            ),
        )
        if not _trial_output_roles(session):
            return
        now = self.clock()
        off_deadline_ns = min(deadline_ns, now + self.serial_ack_timeout_ns)
        invalidate_released_idle_proof(self.pulse)
        off = await self.serial.off(
            ("trial_state",),
            scheduled_boundary_ns=None,
            stop_issued_ns=now,
            deadline_ns=off_deadline_ns,
        )
        if (
            off.outcome != mcu.PULSE_COMMAND_OUTCOME_APPLIED
            or not off.applied
            or not off.trial_state_selected
            or off.behavioral_selected
            or off.tracking_selected
            or off.eye_tracking_selected
            or not off.HasField("resulting_state")
            or not _outputs_proven_off(off.resulting_state)
            or not capture_outputs_running(session, off.resulting_state)
        ):
            raise RuntimeError(
                "MCU Trial state is not confirmed LOW before trial preparation"
            )
        retain_applied_pulse_state(self.pulse, off, deadline_ns=off_deadline_ns)

    async def execute(
        self,
        session: SessionRecord,
        trial: TrialRecord,
        selected_roles: tuple[int | str, ...],
        *,
        command: mcu.PulseBoundaryCommand,
        boundary_ns: int,
    ) -> None:
        await wait_until_ns(boundary_ns, clock=self.clock)
        if not self._current_boundary(session, trial):
            return
        ack_deadline_ns = boundary_ns + self.serial_ack_timeout_ns
        delivery_deadline_ns = boundary_ns + (
            self.start_evidence_allowance_ns
            if command == mcu.PULSE_BOUNDARY_COMMAND_ON
            else self.lifecycle_delivery_ns
        )
        try:
            if command == mcu.PULSE_BOUNDARY_COMMAND_ON:
                invalidate_released_idle_proof(self.pulse)
                evidence = await self.serial.on(
                    selected_roles,
                    scheduled_boundary_ns=boundary_ns,
                    deadline_ns=ack_deadline_ns,
                )
            else:
                invalidate_released_idle_proof(self.pulse)
                evidence = await self.serial.off(
                    selected_roles,
                    scheduled_boundary_ns=boundary_ns,
                    stop_issued_ns=None,
                    deadline_ns=ack_deadline_ns,
                )
        except TimeoutError:
            evidence = _failure_evidence(
                selected_roles,
                command,
                boundary_ns,
                mcu.PULSE_COMMAND_OUTCOME_TIMED_OUT,
            )
        except Exception:
            evidence = _failure_evidence(
                selected_roles,
                command,
                boundary_ns,
                mcu.PULSE_COMMAND_OUTCOME_TRANSPORT_FAILED,
            )

        if not self._current_boundary(session, trial):
            return
        if command == mcu.PULSE_BOUNDARY_COMMAND_OFF:
            trial.pulse_delivery_deadline_ns = delivery_deadline_ns
        _retain_boundary_result(trial, command, evidence)

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

    def _current_boundary(self, session: SessionRecord, trial: TrialRecord) -> bool:
        return bool(
            self.session_slot.current is session
            and session.trial is trial
            and not session.interrupted
            and not session.setup_cancelled
            and not trial.interrupted
            and trial.stop is None
        )

    async def send_evidence(
        self,
        trial: TrialRecord,
        evidence: mcu.PulseCommandEvidence,
        deadline_ns: int,
    ) -> None:
        calls = []
        for worker in self.workers.values():
            if (
                worker.port is None
                or worker.trial is None
                or not evidence.trial_state_selected
            ):
                continue
            command, _operation, port = retain_worker_command(
                worker,
                work=trial.work,
                parent_operation=trial.schedule or trial.preparation,
                kind="record_pulse_evidence",
                deadline_ns=deadline_ns,
                configuration_revision=trial.configuration_revision,
            )
            pulse = acq.WorkerPulseEvidence(
                command=command,
                camera=worker.context.camera,
                evidence=evidence,
            )
            calls.append(port.record_pulse_evidence(pulse, deadline_ns=deadline_ns))
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
    selected_roles: tuple[int | str, ...],
    command: mcu.PulseBoundaryCommand,
    boundary_ns: int,
    outcome: mcu.PulseCommandOutcome,
) -> mcu.PulseCommandEvidence:
    return mcu.PulseCommandEvidence(
        command=command,
        behavioral_selected=(camera.CAMERA_ROLE_BEHAVIORAL in selected_roles),
        tracking_selected=(camera.CAMERA_ROLE_TRACKING in selected_roles),
        eye_tracking_selected=(camera.CAMERA_ROLE_EYE_TRACKING in selected_roles),
        trial_state_selected="trial_state" in selected_roles,
        scheduled_boundary_monotonic_ns=boundary_ns,
        outcome=outcome,
    )


def _outputs_proven_off(state: mcu.MicrocontrollerState) -> bool:
    return all(
        state.HasField(role)
        and getattr(state, role).HasField("running")
        and not getattr(state, role).running
        for role in ("trial_state",)
    )
