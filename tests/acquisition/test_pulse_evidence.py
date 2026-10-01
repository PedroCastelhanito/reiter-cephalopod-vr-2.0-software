"""Pulse observation provenance, acknowledgements and terminal evidence."""

from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest

from cephvr.acquisition.coordinator.manual_pulse_observation import (
    retain_applied_pulse_state,
)
from cephvr.acquisition.coordinator.trial_lifecycle import TrialLifecycleReports
from cephvr.acquisition.coordinator.trial_pulses import TrialPulseBoundaries
from cephvr.acquisition.ports import SerialOwnerPort
from cephvr.acquisition.recording.session_contracts import PulseEvidence
from cephvr.acquisition.state import CoordinatorIdentity, PulseRecord, SessionRecord
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.acquisition.worker.pulse_evidence import TrialPulseEvidence
from cephvr.control.v1 import types_pb2 as control


@pytest.mark.parametrize(
    "enabled",
    [True, False],
)
def test_applied_command_updates_only_state_on_same_mcu_observation(
    enabled: bool,
) -> None:
    current = mcu.MicrocontrollerObservation(
        connection_id="connection-1",
        request_id="status-1",
        observed_monotonic_ns=50,
        state=mcu.MicrocontrollerState(
            behavioral=mcu.PulseOutputState(enabled=not enabled, running=not enabled)
        ),
        capabilities=mcu.MicrocontrollerCapabilities(
            protocol_version=1, firmware="rig-fw", pins=["A", "B"]
        ),
        capabilities_observed_monotonic_ns=40,
    )
    pulse = PulseRecord(observation=current)
    evidence = mcu.PulseCommandEvidence(
        connection_id="connection-1",
        request_id="cmd-2",
        dispatched_monotonic_ns=60,
        acknowledged_monotonic_ns=70,
        applied=True,
        outcome=mcu.PULSE_COMMAND_OUTCOME_APPLIED,
        resulting_state=mcu.MicrocontrollerState(
            behavioral=mcu.PulseOutputState(enabled=enabled, running=enabled)
        ),
    )

    retain_applied_pulse_state(pulse, evidence, deadline_ns=100)

    assert pulse.observation is not None
    assert pulse.observation.connection_id == "connection-1"
    assert pulse.observation.request_id == "status-1"
    assert pulse.observation.observed_monotonic_ns == 50
    assert pulse.observation.capabilities.firmware == "rig-fw"
    assert list(pulse.observation.capabilities.pins) == ["A", "B"]
    assert pulse.observation.capabilities_observed_monotonic_ns == 40
    assert pulse.observation.state.behavioral.enabled is enabled
    assert pulse.observation.state.behavioral.running is enabled


def test_unmatched_connection_or_non_applied_outcome_is_not_adopted() -> None:
    pulse = PulseRecord(
        observation=mcu.MicrocontrollerObservation(
            connection_id="connection-1",
            request_id="status-1",
            state=mcu.MicrocontrollerState(),
        )
    )
    assert pulse.observation is not None
    before = mcu.MicrocontrollerObservation.FromString(
        pulse.observation.SerializeToString(deterministic=True)
    )
    evidence = mcu.PulseCommandEvidence(
        connection_id="connection-2",
        request_id="cmd-2",
        dispatched_monotonic_ns=60,
        acknowledged_monotonic_ns=70,
        applied=True,
        outcome=mcu.PULSE_COMMAND_OUTCOME_APPLIED,
        resulting_state=mcu.MicrocontrollerState(),
    )

    with pytest.raises(RuntimeError, match="exact timely APPLIED/ACK"):
        retain_applied_pulse_state(pulse, evidence, deadline_ns=100)

    assert pulse.observation == before


@pytest.mark.parametrize("outcome", ("rejected", "timed_out", "failed"))
def test_required_pulse_evidence_needs_applied_on_and_off(outcome: str) -> None:
    evidence = PulseEvidence(
        on_outcome="PULSE_COMMAND_OUTCOME_APPLIED",
        on_dispatched_monotonic_ns=1,
        on_acknowledged_monotonic_ns=2,
        off_outcome=outcome,
        off_dispatched_monotonic_ns=3,
        off_acknowledged_monotonic_ns=4,
        required=True,
    )
    assert not evidence.complete()


def test_required_pulse_evidence_requires_both_acknowledgements() -> None:
    assert not PulseEvidence(
        on_outcome="applied",
        on_dispatched_monotonic_ns=1,
        on_acknowledged_monotonic_ns=2,
        off_outcome="PULSE_COMMAND_OUTCOME_APPLIED",
        off_dispatched_monotonic_ns=3,
        required=True,
    ).complete()
    assert PulseEvidence(required=False).complete()


class _StatusSerial:
    def __init__(self) -> None:
        self.observation = mcu.MicrocontrollerObservation(
            port="COM9",
            connection_id="connection-1",
            request_id="status-1",
            observed_monotonic_ns=123,
            capabilities_observed_monotonic_ns=122,
        )
        self.observation.state.configuration_valid = True
        self.observation.state.watchdog_stopped = False
        self.observation.state.watchdog_ms = 3000
        self.observation.capabilities.protocol_version = 1

    async def status(self, *, deadline_ns: int) -> mcu.MicrocontrollerObservation:
        assert deadline_ns > 0
        return mcu.MicrocontrollerObservation.FromString(
            self.observation.SerializeToString(deterministic=True)
        )

    async def off(
        self,
        selected_roles: tuple[int, ...],
        *,
        scheduled_boundary_ns: int | None,
        stop_issued_ns: int | None,
        deadline_ns: int,
    ) -> mcu.PulseCommandEvidence:
        assert selected_roles == (
            camera.CAMERA_ROLE_BEHAVIORAL,
            camera.CAMERA_ROLE_TRACKING,
        )
        assert scheduled_boundary_ns is None
        assert stop_issued_ns is not None
        assert deadline_ns > stop_issued_ns
        result = mcu.MicrocontrollerState(
            configuration_valid=True,
            watchdog_stopped=False,
            watchdog_ms=3000,
        )
        result.behavioral.running = False
        result.tracking.running = False
        return mcu.PulseCommandEvidence(
            connection_id=self.observation.connection_id,
            request_id="off-1",
            dispatched_monotonic_ns=201,
            outcome=mcu.PULSE_COMMAND_OUTCOME_APPLIED,
            applied=True,
            resulting_state=result,
            acknowledged_monotonic_ns=205,
        )


@pytest.mark.asyncio
async def test_off_ack_does_not_forge_a_full_status_timestamp() -> None:
    serial = _StatusSerial()
    pulse = PulseRecord()
    identity = CoordinatorIdentity(
        backend=control.BackendContext(
            backend_name="acquisition", backend_generation="a-1"
        ),
        process=control.ProcessIdentity(role="acquisition", generation="a-1"),
        controller=control.ProcessIdentity(role="controller", generation="c-1"),
        supervisor=control.ProcessIdentity(role="supervisor", generation="s-1"),
        tracking=control.ProcessIdentity(role="tracking", generation="t-1"),
    )
    boundaries = TrialPulseBoundaries(
        identity=identity,
        workers={},
        serial=cast(SerialOwnerPort, serial),
        pulse=pulse,
        lifecycle=cast(TrialLifecycleReports, object()),
        serial_ack_timeout_ns=10,
        start_evidence_allowance_ns=100,
        lifecycle_delivery_ns=100,
        clock=lambda: 200,
    )
    settings = control.AcquisitionSettings()
    settings.behavioral.device.frame_timing = camera.FRAME_TIMING_EXTERNAL_TRIGGER
    session = SessionRecord(
        work=control.WorkContext(session=control.SessionContext(session_id="s-1")),
        operation=control.OperationContext(command_id="setup-1"),
        configuration_revision=1,
        required_cameras={camera.CAMERA_ROLE_BEHAVIORAL},
        confirmed_settings=settings,
    )

    await boundaries.ensure_outputs_off(session, deadline_ns=500)

    assert pulse.observation is not None
    assert pulse.observation.observed_monotonic_ns == 123
    assert pulse.observation.capabilities_observed_monotonic_ns == 122
    assert pulse.observation.request_id == "status-1"
    assert pulse.observation.state.behavioral.running is False


def _trial_work() -> control.WorkContext:
    work = control.WorkContext()
    work.trial.session.session_id = str(uuid4())
    work.trial.trial_id = str(uuid4())
    work.trial.trial_number = 1
    return work


def _schedule(work: control.WorkContext) -> acq.WorkerSchedule:
    request = acq.WorkerSchedule(start_monotonic_ns=100, end_monotonic_ns=200)
    request.command.target.work.CopyFrom(work)
    return request


def _pulse(
    work: control.WorkContext, *, applied: bool, command_id: str
) -> acq.WorkerPulseEvidence:
    request = acq.WorkerPulseEvidence(
        camera=camera.CAMERA_ROLE_BEHAVIORAL,
        command=acq.WorkerCommand(command_id=command_id),
    )
    request.command.target.work.CopyFrom(work)
    request.evidence.connection_id = "mcu-generation"
    request.evidence.request_id = "pulse-request"
    request.evidence.command = mcu.PULSE_BOUNDARY_COMMAND_ON
    request.evidence.outcome = (
        mcu.PULSE_COMMAND_OUTCOME_APPLIED
        if applied
        else mcu.PULSE_COMMAND_OUTCOME_REJECTED
    )
    request.evidence.behavioral_selected = True
    request.evidence.scheduled_boundary_monotonic_ns = 100
    request.evidence.dispatched_monotonic_ns = 90
    request.evidence.acknowledged_monotonic_ns = 95
    request.evidence.applied = applied
    return request


def test_terminal_pulse_retry_is_idempotent_and_conflict_cannot_replace_it() -> None:
    work = _trial_work()
    schedule = _schedule(work)
    accepted = _pulse(work, applied=True, command_id="first-command")
    tracker = TrialPulseEvidence()
    tracker.reset(required=True)
    tracker.record(accepted, schedule, camera.CAMERA_ROLE_BEHAVIORAL)
    retained = tracker.combined()

    tracker.record(accepted, schedule, camera.CAMERA_ROLE_BEHAVIORAL)
    assert tracker.combined() == retained

    conflict = _pulse(work, applied=False, command_id="changed-command")
    with pytest.raises(ValueError, match="terminal pulse evidence changed"):
        tracker.record(conflict, schedule, camera.CAMERA_ROLE_BEHAVIORAL)
    assert tracker.combined() == retained
    assert tracker.connection_id == "mcu-generation"


def test_unspecified_terminal_pulse_does_not_mutate_retained_evidence() -> None:
    work = _trial_work()
    request = _pulse(work, applied=True, command_id="pulse")
    request.evidence.ClearField("outcome")
    tracker = TrialPulseEvidence()
    tracker.reset(required=True)
    with pytest.raises(ValueError, match="selected terminal outcome"):
        tracker.record(request, _schedule(work), camera.CAMERA_ROLE_BEHAVIORAL)
    assert tracker.connection_id is None
    assert tracker.on is None
