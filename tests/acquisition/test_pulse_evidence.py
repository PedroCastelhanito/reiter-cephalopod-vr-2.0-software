"""Pulse observation provenance, acknowledgements and terminal evidence."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from cephvr.acquisition.coordinator.manual_pulse_observation import (
    retain_applied_pulse_state,
)
from cephvr.acquisition.coordinator.trial_lifecycle import TrialLifecycleReports
from cephvr.acquisition.coordinator.trial_pulses import TrialPulseBoundaries
from cephvr.acquisition.ports import SerialOwnerPort, WorkerPort
from cephvr.acquisition.recording.session_contracts import PulseEvidence
from cephvr.acquisition.state import (
    CoordinatorIdentity,
    LaunchRecord,
    PulseRecord,
    SessionRecord,
    SessionSlot,
    TrialRecord,
    WorkerRecord,
    WorkerTrial,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.acquisition.worker.pulse_evidence import TrialPulseEvidence
from cephvr.acquisition.worker.trial_lifecycle import WorkerTrialLifecycle
from cephvr.acquisition.worker.trial_state import WorkerTrialState
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.commands import CommandLedger


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
            camera.CAMERA_ROLE_EYE_TRACKING,
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
        result.eye_tracking.running = False
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
        session_slot=SessionSlot(),
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


@pytest.mark.parametrize(
    "command", [mcu.PULSE_BOUNDARY_COMMAND_ON, mcu.PULSE_BOUNDARY_COMMAND_OFF]
)
@pytest.mark.parametrize(
    "retired",
    [
        "live",
        "interrupted",
        "replaced_session",
        "replaced_trial",
        "cancelled",
        "stopped",
        "during_io",
    ],
)
async def test_scheduled_boundary_never_actuates_or_forwards_for_retired_owner(
    monkeypatch: pytest.MonkeyPatch, command: int, retired: str
) -> None:
    from cephvr.acquisition.coordinator import trial_pulses

    wake, entered, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def wait_boundary(boundary, *, clock):
        await wake.wait()

    monkeypatch.setattr(trial_pulses, "wait_until_ns", wait_boundary)
    work = _trial_work()
    trial = TrialRecord(
        work=work,
        plan=control.TrialPlan(),
        preparation=control.OperationContext(command_id="prepare"),
        schedule=control.OperationContext(command_id="schedule"),
        configuration_revision=1,
    )
    session = SessionRecord(
        work=control.WorkContext(session=work.trial.session),
        operation=control.OperationContext(command_id="setup"),
        configuration_revision=1,
        required_cameras=set(),
        trial=trial,
    )
    slot = SessionSlot(current=session)
    calls, changes = [], []

    async def serial_call(roles, *, scheduled_boundary_ns, deadline_ns, **kwargs):
        calls.append((command, scheduled_boundary_ns, deadline_ns))
        entered.set()
        if retired == "during_io":
            await release.wait()
        return mcu.PulseCommandEvidence(
            command=command,
            connection_id="connection-1",
            request_id="boundary",
            outcome=mcu.PULSE_COMMAND_OUTCOME_APPLIED,
            applied=True,
            dispatched_monotonic_ns=100,
            acknowledged_monotonic_ns=101,
            resulting_state=mcu.MicrocontrollerState(),
        )

    async def changed(value):
        changes.append(value)

    observation = mcu.MicrocontrollerObservation(connection_id="connection-1")
    pulse = PulseRecord(observation=observation)
    owner = TrialPulseBoundaries(
        identity=cast(CoordinatorIdentity, object()),
        workers={},
        serial=cast(SerialOwnerPort, SimpleNamespace(on=serial_call, off=serial_call)),
        pulse=pulse,
        lifecycle=cast(
            TrialLifecycleReports, SimpleNamespace(pulse_evidence_changed=changed)
        ),
        session_slot=slot,
        serial_ack_timeout_ns=10,
        start_evidence_allowance_ns=20,
        lifecycle_delivery_ns=30,
        clock=lambda: 100,
    )
    task = asyncio.create_task(
        owner.execute(session, trial, (), command=command, boundary_ns=100)
    )
    await asyncio.sleep(0)
    if retired == "interrupted":
        session.interrupted = trial.interrupted = True
    elif retired == "replaced_session":
        new_work = _trial_work()
        new_trial = replace(trial, work=new_work)
        slot.current = replace(
            session,
            work=control.WorkContext(session=new_work.trial.session),
            trial=new_trial,
        )
    elif retired == "replaced_trial":
        session.trial = replace(trial)
    elif retired == "cancelled":
        session.setup_cancelled = True
    elif retired == "stopped":
        trial.stop = control.OperationContext(command_id="stop")
    wake.set()
    if retired == "during_io":
        await entered.wait()
        slot.current = replace(session)
        release.set()
    await task
    assert calls == ([(command, 100, 110)] if retired in {"live", "during_io"} else [])
    assert changes == ([trial] if retired == "live" else [])
    assert (trial.pulse_on is not None) == (
        retired == "live" and command == mcu.PULSE_BOUNDARY_COMMAND_ON
    )
    assert (trial.pulse_off is not None) == (
        retired == "live" and command == mcu.PULSE_BOUNDARY_COMMAND_OFF
    )
    assert trial.pulse_on_ready.is_set() == (
        retired == "live" and command == mcu.PULSE_BOUNDARY_COMMAND_ON
    )
    assert trial.pulse_off_ready.is_set() == (
        retired == "live" and command == mcu.PULSE_BOUNDARY_COMMAND_OFF
    )
    if retired != "live":
        assert (
            pulse.observation == observation
            and trial.pulse_delivery_deadline_ns is None
        )
    if retired == "replaced_session":
        current = slot.current
        assert current is not None and current.trial is not None
        assert current.work != session.work and current.trial.work != trial.work
        assert current.trial.pulse_on is None and current.trial.pulse_off is None
        # Crossing the retired boundary must leave this same owner's next session
        # usable, with evidence attached only to the fresh trial.
        await owner.execute(
            current, current.trial, (), command=command, boundary_ns=100
        )
        assert calls == [(command, 100, 110)]
        assert changes == [current.trial]
        assert (current.trial.pulse_on is not None) == (
            command == mcu.PULSE_BOUNDARY_COMMAND_ON
        )
        assert (current.trial.pulse_off is not None) == (
            command == mcu.PULSE_BOUNDARY_COMMAND_OFF
        )
        assert trial.pulse_on is None and trial.pulse_off is None


def _schedule(work: control.WorkContext) -> acq.WorkerSchedule:
    request = acq.WorkerSchedule(start_monotonic_ns=100, end_monotonic_ns=200)
    request.command.target.work.CopyFrom(work)
    return request


def _pulse(
    work: control.WorkContext,
    *,
    applied: bool,
    command_id: str,
    role: int = camera.CAMERA_ROLE_BEHAVIORAL,
) -> acq.WorkerPulseEvidence:
    request = acq.WorkerPulseEvidence(
        camera=role,
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
    request.evidence.behavioral_selected = role == camera.CAMERA_ROLE_BEHAVIORAL
    request.evidence.tracking_selected = role == camera.CAMERA_ROLE_TRACKING
    request.evidence.eye_tracking_selected = role == camera.CAMERA_ROLE_EYE_TRACKING
    request.evidence.scheduled_boundary_monotonic_ns = 100
    request.evidence.dispatched_monotonic_ns = 90
    request.evidence.acknowledged_monotonic_ns = 95
    request.evidence.applied = applied
    return request


@pytest.mark.parametrize(
    "role",
    [
        camera.CAMERA_ROLE_BEHAVIORAL,
        camera.CAMERA_ROLE_TRACKING,
        camera.CAMERA_ROLE_EYE_TRACKING,
    ],
)
@pytest.mark.parametrize(
    "boundary", [mcu.PULSE_BOUNDARY_COMMAND_ON, mcu.PULSE_BOUNDARY_COMMAND_OFF]
)
def test_terminal_pulse_retry_is_idempotent_and_conflict_cannot_replace_it(
    role: int,
    boundary: int,
) -> None:
    work = _trial_work()
    schedule = _schedule(work)
    accepted = _pulse(work, applied=True, command_id="first-command", role=role)
    if boundary == mcu.PULSE_BOUNDARY_COMMAND_OFF:
        accepted.evidence.command = boundary
        accepted.evidence.scheduled_boundary_monotonic_ns = schedule.end_monotonic_ns
        accepted.evidence.dispatched_monotonic_ns = schedule.end_monotonic_ns
        accepted.evidence.acknowledged_monotonic_ns = schedule.end_monotonic_ns + 5
    tracker = TrialPulseEvidence()
    tracker.reset(required=True)
    tracker.record(accepted, schedule, role)
    retained = tracker.combined()

    tracker.record(accepted, schedule, role)
    assert tracker.combined() == retained

    forwarded = acq.WorkerPulseEvidence.FromString(accepted.SerializeToString())
    forwarded.command.command_id = "fresh-forwarding-command"
    tracker.record(forwarded, schedule, role)
    assert tracker.combined() == retained

    conflict = acq.WorkerPulseEvidence.FromString(forwarded.SerializeToString())
    conflict.evidence.outcome = mcu.PULSE_COMMAND_OUTCOME_REJECTED
    conflict.evidence.applied = False
    with pytest.raises(ValueError, match="terminal pulse evidence changed"):
        tracker.record(conflict, schedule, role)
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


@pytest.mark.asyncio
@pytest.mark.parametrize("scheduled", [False, True])
@pytest.mark.parametrize(
    "pulse_command", [mcu.PULSE_BOUNDARY_COMMAND_ON, mcu.PULSE_BOUNDARY_COMMAND_OFF]
)
async def test_pulse_delivery_retains_exact_child_before_worker_ack(
    scheduled: bool, pulse_command: int
) -> None:
    work = _trial_work()
    owner = control.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    process = control.ProcessIdentity(
        role="acquisition_behavioral_worker", generation=str(uuid4())
    )
    preparation = control.OperationContext(command_id=str(uuid4()))
    schedule = control.OperationContext(command_id=str(uuid4())) if scheduled else None
    trial = TrialRecord(
        work=work,
        plan=control.TrialPlan(context=work.trial),
        preparation=preparation,
        schedule=schedule,
        configuration_revision=2,
    )
    context = acq.WorkerContext(
        worker=process,
        owner=owner,
        camera=camera.CAMERA_ROLE_BEHAVIORAL,
        work=control.WorkContext(session=work.trial.session),
    )
    launch = LaunchRecord(
        command_id=str(uuid4()),
        worker=process,
        owner=owner,
        work=context.work,
        camera=context.camera,
        parent_operation=preparation,
        planned_ns=1,
    )
    ledger = CommandLedger(
        str(uuid4()),
        300_000_000_000,
        max_records=32,
        max_bytes=2 * 1024 * 1024,
        result_reservation_bytes=64 * 1024,
    )
    observed = []

    async def deliver(
        request: acq.WorkerPulseEvidence, *, deadline_ns: int
    ) -> control.CommandAdmission:
        child = workers[request.camera].child_operations[request.command.command_id]
        assert child.work == work and request.command.target.work == work
        assert child.parent_operation == (schedule or preparation)
        assert (
            child.kind == "record_pulse_evidence" and child.configuration_revision == 2
        )
        assert child.deadline_ns == deadline_ns == 100
        assert child.retention_key and child.retention_key.endswith(":safety")
        assert ledger.has_payload(child.retention_key)
        if scheduled:
            retained_schedule = _schedule(work)
            retained_schedule.command.command_id = "distinct-worker-schedule-child"
            retained_schedule.command.parent_operation.CopyFrom(schedule)
            interruption = acq.WorkerInterrupt()
            interruption.command.target.work.session.CopyFrom(work.trial.session)
            lifecycle = object.__new__(WorkerTrialLifecycle)
            lifecycle.trial_state = WorkerTrialState(
                stopped_schedule=retained_schedule, stop_request=interruption
            )
            assert lifecycle._interrupted_schedule_matches(request, retained_schedule)
            retained_schedule.command.parent_operation.command_id = "stale-schedule"
            assert not lifecycle._interrupted_schedule_matches(
                request, retained_schedule
            )
        observed.append(request)
        return control.CommandAdmission(result=control.COMMAND_RESULT_ACCEPTED)

    worker = WorkerRecord(
        context=context,
        launch=launch,
        port=cast(WorkerPort, SimpleNamespace(record_pulse_evidence=deliver)),
        commands=ledger,
        trial=WorkerTrial(configuration_revision=2),
    )
    tracking_context = acq.WorkerContext.FromString(context.SerializeToString())
    tracking_context.camera = camera.CAMERA_ROLE_TRACKING
    tracking_context.worker.role = "acquisition_tracking_worker"
    tracking_context.worker.generation = str(uuid4())
    tracking_worker = WorkerRecord(
        context=tracking_context,
        launch=replace(
            launch,
            command_id=str(uuid4()),
            worker=tracking_context.worker,
            camera=tracking_context.camera,
        ),
        port=cast(WorkerPort, SimpleNamespace(record_pulse_evidence=deliver)),
        commands=ledger,
        trial=WorkerTrial(configuration_revision=2),
    )
    workers = {context.camera: worker, tracking_context.camera: tracking_worker}
    boundaries = cast(
        TrialPulseBoundaries,
        SimpleNamespace(
            workers={
                **workers,
                camera.CAMERA_ROLE_EYE_TRACKING: SimpleNamespace(
                    context=SimpleNamespace(camera=camera.CAMERA_ROLE_EYE_TRACKING),
                    port=object(),
                    trial=object(),
                ),
            }
        ),
    )
    await TrialPulseBoundaries.send_evidence(
        boundaries,
        trial,
        mcu.PulseCommandEvidence(
            applied=True,
            behavioral_selected=True,
            tracking_selected=True,
            command=pulse_command,
        ),
        100,
    )
    assert {request.camera for request in observed} == {
        camera.CAMERA_ROLE_BEHAVIORAL,
        camera.CAMERA_ROLE_TRACKING,
    }
    assert len(observed) == 2 and not trial.interrupted
