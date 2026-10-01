"""Trial lifecycle evidence, stop cutoffs and safety fanout."""

from __future__ import annotations

import asyncio
from typing import cast
from uuid import uuid4

import pytest

from cephvr.acquisition.coordinator.trial_delivery import TrialReportDelivery
from cephvr.acquisition.coordinator.trial_lifecycle import TrialLifecycleReports
from cephvr.acquisition.coordinator.trial_pulses import TrialPulseBoundaries
from cephvr.acquisition.coordinator.trial_termination import TrialTermination
from cephvr.acquisition.coordinator.trial_validation import (
    TrialLifecycleValidation,
    empty_video_exception,
    finished_cutoff_ns,
    finished_is_timely,
    valid_pulse,
)
from cephvr.acquisition.ports import ControllerPort, SerialOwnerPort, WorkerPort
from cephvr.acquisition.state import (
    ChildOperation,
    CoordinatorIdentity,
    LaunchRecord,
    PulseRecord,
    SessionRecord,
    SessionSlot,
    TrialRecord,
    WorkerRecord,
    WorkerTrial,
)
from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.commands import CommandLedger


class _Serial:
    def __init__(self) -> None:
        self.cancel_called = False
        self.off_called = False

    async def cancel_on_reservations(self, *, deadline_ns: int) -> None:
        self.cancel_called = True
        raise RuntimeError("serial cancellation uncertain")

    async def off(
        self,
        selected_roles: tuple[int | str, ...],
        *,
        scheduled_boundary_ns: int | None,
        stop_issued_ns: int | None,
        deadline_ns: int,
    ) -> mcu.PulseCommandEvidence:
        _ = selected_roles, scheduled_boundary_ns, stop_issued_ns, deadline_ns
        self.off_called = True
        raise RuntimeError("OFF transport failed")


class _Worker:
    def __init__(self) -> None:
        self.interrupt_calls = 0
        self.stop_calls = 0

    async def interrupt_session(
        self, request: acq.WorkerInterrupt, *, deadline_ns: int
    ) -> control.CommandAdmission:
        _ = request, deadline_ns
        self.interrupt_calls += 1
        return control.CommandAdmission(
            result=control.COMMAND_RESULT_ACCEPTED,
            command_id=request.command.command_id,
        )

    async def stop_trial(
        self, request: acq.WorkerStop, *, deadline_ns: int
    ) -> control.CommandAdmission:
        _ = deadline_ns
        self.stop_calls += 1
        return control.CommandAdmission(
            result=control.COMMAND_RESULT_ACCEPTED,
            command_id=request.command.command_id,
        )


@pytest.mark.parametrize("interrupt", [False, True])
def test_safety_fanout_survives_off_failure_and_missing_worker(
    interrupt: bool,
) -> None:
    session_id = str(uuid4())
    session_work = control.WorkContext(
        session=control.SessionContext(session_id=session_id)
    )
    backend = control.BackendContext(
        backend_name="acquisition", backend_generation=str(uuid4())
    )
    coordinator = control.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    controller = control.ProcessIdentity(role="controller", generation=str(uuid4()))
    supervisor = control.ProcessIdentity(role="supervisor", generation=str(uuid4()))
    tracking = control.ProcessIdentity(role="tracking", generation=str(uuid4()))
    identity = CoordinatorIdentity(
        backend, coordinator, controller, supervisor, tracking
    )
    settings = control.AcquisitionSettings()
    settings.behavioral.device.frame_timing = camera.FRAME_TIMING_EXTERNAL_TRIGGER
    session = SessionRecord(
        work=session_work,
        operation=control.OperationContext(command_id=str(uuid4())),
        configuration_revision=7,
        required_cameras={
            camera.CAMERA_ROLE_BEHAVIORAL,
            camera.CAMERA_ROLE_TRACKING,
        },
        confirmed_settings=settings,
    )
    trial_work = control.WorkContext(
        trial=control.TrialContext(
            session=session_work.session,
            trial_id=str(uuid4()),
            trial_number=1,
        )
    )
    trial = TrialRecord(
        work=trial_work,
        plan=control.TrialPlan(),
        preparation=control.OperationContext(command_id=str(uuid4())),
        configuration_revision=7,
        schedule=control.OperationContext(command_id=str(uuid4())),
        end_monotonic_ns=80,
    )
    session.trial = trial
    owner_generation = str(uuid4())
    worker_identity = control.ProcessIdentity(
        role="acquisition_behavioral_worker", generation=owner_generation
    )
    launch = LaunchRecord(
        command_id=str(uuid4()),
        worker=worker_identity,
        owner=coordinator,
        work=session_work,
        camera=camera.CAMERA_ROLE_BEHAVIORAL,
        parent_operation=session.operation,
        planned_ns=1,
    )
    worker_port = _Worker()
    ledger = CommandLedger(
        owner_generation,
        retention_ns=10_000,
        max_records=32,
        max_bytes=1_000_000,
        result_reservation_bytes=4096,
    )
    worker_record = WorkerRecord(
        context=acq.WorkerContext(
            worker=worker_identity,
            owner=coordinator,
            camera=camera.CAMERA_ROLE_BEHAVIORAL,
        ),
        port=cast(WorkerPort, worker_port),
        launch=launch,
        commands=ledger,
        trial=WorkerTrial(
            configuration_revision=7,
            schedule=control.OperationContext(command_id=str(uuid4())),
        ),
    )
    serial = _Serial()
    termination = TrialTermination(
        identity=identity,
        session_slot=SessionSlot(current=session),
        workers={camera.CAMERA_ROLE_BEHAVIORAL: worker_record},
        serial=cast(SerialOwnerPort, serial),
        pulse=PulseRecord(),
        pulse_boundaries=cast(TrialPulseBoundaries, object()),
        stop_evidence_allowance_ns=100,
        start_evidence_allowance_ns=100,
        lifecycle_delivery_ns=100,
        valid_command=lambda _command, _session, _deadline: True,
        lock=asyncio.Lock(),
        clock=lambda: 10,
    )
    command = wire.BackendCommand(
        command_id=str(uuid4()), issuer=controller, target=backend
    )
    if interrupt:
        command.work.CopyFrom(session_work)
        interrupt_request = wire.InterruptSessionRequest(
            command=command, issued_monotonic_ns=10
        )
        admission = asyncio.run(
            termination.interrupt_session(interrupt_request, deadline_ns=100)
        )
    else:
        command.work.CopyFrom(trial_work)
        stop_request = wire.StopTrialRequest(
            command=command,
            issued_monotonic_ns=10,
            reason=control.Failure(code="TEST", message="prepared case"),
        )
        admission = asyncio.run(termination.stop(stop_request, deadline_ns=100))

    assert admission.result == control.COMMAND_RESULT_REJECTED
    assert serial.cancel_called and serial.off_called
    assert worker_port.interrupt_calls == int(interrupt)
    assert worker_port.stop_calls == int(not interrupt)


def _trial() -> TrialRecord:
    work = control.WorkContext(
        trial=control.TrialContext(
            session=control.SessionContext(session_id=str(uuid4())),
            trial_id=str(uuid4()),
            trial_number=1,
        )
    )
    return TrialRecord(
        work=work,
        plan=control.TrialPlan(),
        preparation=control.OperationContext(command_id=str(uuid4())),
        configuration_revision=1,
        end_monotonic_ns=1_000,
        stop_issued_ns=1_200,
    )


def test_finished_cutoff_uses_retained_early_stop_time() -> None:
    trial = _trial()
    cutoff = finished_cutoff_ns(trial, 250, 1_500)
    assert cutoff == 1_450
    assert finished_is_timely(trial, 250, 1_450)
    assert not finished_is_timely(trial, 250, 1_451)


def test_terminal_pulse_acceptance_requires_exact_boundary_and_ack() -> None:
    evidence = mcu.PulseCommandEvidence(
        command=mcu.PULSE_BOUNDARY_COMMAND_OFF,
        outcome=mcu.PULSE_COMMAND_OUTCOME_APPLIED,
        applied=True,
        scheduled_boundary_monotonic_ns=2_000,
        acknowledged_monotonic_ns=2_001,
    )
    assert valid_pulse(
        evidence,
        command=mcu.PULSE_BOUNDARY_COMMAND_OFF,
        boundary_ns=2_000,
    )
    evidence.scheduled_boundary_monotonic_ns = 2_002
    assert not valid_pulse(
        evidence,
        command=mcu.PULSE_BOUNDARY_COMMAND_OFF,
        boundary_ns=2_000,
    )


def test_no_frames_video_exception_requires_closed_exact_frame_log() -> None:
    backend = control.BackendContext(
        backend_name="acquisition", backend_generation=str(uuid4())
    )
    trial = control.TrialContext(
        session=control.SessionContext(session_id=str(uuid4())),
        trial_id=str(uuid4()),
        trial_number=1,
    )
    video = control.OutputPlan(
        backend=backend,
        output_key="video",
        path="C:/data/trial.mp4",
        trial=trial,
        output_tag="behavioral_cam",
        extension="mp4",
    )
    log = control.OutputPlan(
        backend=backend,
        output_key="frame-log",
        path="C:/data/trial.jsonl",
        trial=trial,
        output_tag="behavioral_cam_frames",
        extension="jsonl",
    )
    no_video = control.OutputResult(
        output_key="video",
        path=video.path,
        closure=control.OUTPUT_CLOSURE_NOT_STARTED,
        artifact_present=False,
        camera_video_content=control.CAMERA_VIDEO_CONTENT_NO_FRAMES,
    )
    closed_log = control.OutputResult(
        output_key="frame-log",
        path=log.path,
        closure=control.OUTPUT_CLOSURE_CLOSED,
        artifact_present=True,
    )

    assert empty_video_exception([video, log], [no_video, closed_log], no_video)
    assert not empty_video_exception([video], [no_video], no_video)
    closed_log.artifact_present = False
    assert not empty_video_exception([video, log], [no_video, closed_log], no_video)


def _started_case(
    *, recording_unavailable: bool
) -> tuple[
    TrialLifecycleValidation,
    WorkerRecord,
    acq.WorkerLifecycleEvidence,
    SessionRecord,
    TrialRecord,
]:
    role = camera_pb2.CAMERA_ROLE_BEHAVIORAL
    work = control.WorkContext(
        trial=control.TrialContext(
            session=control.SessionContext(session_id=str(uuid4())),
            trial_id=str(uuid4()),
            trial_number=1,
        )
    )
    worker_identity = control.ProcessIdentity(
        role="acquisition_behavioral_worker", generation=str(uuid4())
    )
    owner = control.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    source = acq.WorkerContext(
        worker=worker_identity, owner=owner, work=work, camera=role
    )
    operation = control.OperationContext(command_id=str(uuid4()))
    parent = control.OperationContext(command_id=str(uuid4()))
    launch = LaunchRecord(
        command_id=str(uuid4()),
        worker=worker_identity,
        owner=owner,
        work=work,
        camera=role,
        parent_operation=parent,
        planned_ns=1,
    )
    worker = WorkerRecord(source, None, launch)
    worker.trial = WorkerTrial(configuration_revision=1, schedule=operation)
    worker.child_operations[operation.command_id] = ChildOperation(
        command_id=operation.command_id,
        camera=role,
        work=work,
        parent_operation=parent,
        kind="schedule_trial",
    )
    settings = control.AcquisitionSettings()
    settings.behavioral.enabled = True
    settings.behavioral.save_video = True
    session = SessionRecord(
        work=control.WorkContext(
            session=control.SessionContext(session_id=work.trial.session.session_id)
        ),
        operation=parent,
        configuration_revision=1,
        required_cameras={role},
        confirmed_settings=settings,
    )
    if recording_unavailable:
        session.unavailable_resources.add("behavioral.recording")
    trial = TrialRecord(
        work=work,
        plan=control.TrialPlan(),
        preparation=parent,
        configuration_revision=1,
        schedule=operation,
        start_monotonic_ns=100,
    )
    session.trial = trial
    evidence = acq.WorkerLifecycleEvidence(source=source, state_revision=1)
    evidence.operation.CopyFrom(operation)
    evidence.started.actual_start_monotonic_ns = 100
    activity = evidence.started.first_activity.add(
        kind="camera_callback", observed_monotonic_ns=100
    )
    activity.device_evidence.camera = role
    activity.device_evidence.producer.CopyFrom(worker_identity)
    return TrialLifecycleValidation(), worker, evidence, session, trial


def test_saved_started_requires_recording_activity_until_exact_scope_is_fenced() -> (
    None
):
    validator, worker, evidence, session, trial = _started_case(
        recording_unavailable=False
    )
    with pytest.raises(ValueError, match="recording activity"):
        validator.validate_started(
            worker,
            evidence,
            session,
            trial,
            ingress_ns=120,
            allowance_ns=250,
        )

    validator, worker, evidence, session, trial = _started_case(
        recording_unavailable=True
    )
    validator.validate_started(
        worker,
        evidence,
        session,
        trial,
        ingress_ns=120,
        allowance_ns=250,
    )


@pytest.mark.parametrize("kind", ["started", "stopped", "finished"])
@pytest.mark.parametrize("failure", ["rejection", "transport", "exhausted"])
async def test_trial_delivery_retains_evidence_and_original_retry_budget(
    kind: str, failure: str
) -> None:
    _, worker, _, session, trial = _started_case(recording_unavailable=False)
    ledger = CommandLedger(
        str(uuid4()),
        1_000,
        max_records=16,
        max_bytes=1_000_000,
        result_reservation_bytes=4096,
    )
    command_id = str(uuid4())
    ledger.admit(command_id, b"trial", 1, work_key=trial.work.trial.trial_id)
    ledger.complete(command_id, b"done", 2)
    worker.commands = ledger
    wire_report = control.LifecycleReport()
    report = getattr(wire_report, kind)
    report.context.work.CopyFrom(trial.work)
    if kind == "finished":
        session.reserved_outputs.append(
            control.OutputPlan(
                output_key="camera", output_tag="behavioral_cam", trial=trial.work.trial
            )
        )
        report.outputs.add(output_key="camera", closure=control.OUTPUT_CLOSURE_CLOSED)
    setattr(trial, "pending_" + kind + "_report", report)
    calls: list[int] = []

    class Controller:
        async def report_lifecycle(
            self, item: control.LifecycleReport, *, deadline_ns: int
        ) -> control.ReportReceipt:
            calls.append(deadline_ns)
            assert item == wire_report
            if kind == "finished":
                assert session.output_results["camera"] == report.outputs[0]
            if len(calls) < 3 or failure == "exhausted":
                if failure == "transport":
                    raise OSError("controller unavailable")
                return control.ReportReceipt(result=control.COMMAND_RESULT_REJECTED)
            return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)

    delivery = TrialReportDelivery(
        session_slot=SessionSlot(current=session),
        workers={worker.context.camera: worker},
        controller=cast(ControllerPort, Controller()),
        commands=ledger,
        clock=lambda: 100,
    )
    for _ in range(3):
        try:
            await delivery.deliver(trial, kind, report, 500)
        except OSError:
            assert failure == "transport"
        if len(calls) < 3 or failure == "exhausted":
            assert getattr(trial, kind + "_report") is None
            assert getattr(trial, "pending_" + kind + "_report") == report
    assert calls == [500, 500, 500]
    assert trial.lifecycle_report_attempts[kind] == 3
    if failure == "exhausted":
        result = await delivery.deliver(trial, kind, report, 500)
        assert result.failure.code == "LIFECYCLE_UNCONFIRMED"
    else:
        assert getattr(trial, kind + "_report") == report
        assert getattr(trial, "pending_" + kind + "_report") is None
        report.context.operation.command_id = "mutated caller copy"
        assert getattr(trial, kind + "_report") != report
    retained = ledger.get(command_id)
    assert retained is not None
    assert (retained.finalized_ns is not None) == (
        kind == "finished" and failure != "exhausted"
    )
    assert (
        await delivery.deliver(trial, kind, report, 99)
    ).failure.code == "LIFECYCLE_CUTOFF"
    assert len(calls) == 3


@pytest.mark.parametrize("stale", ["session", "trial", "report", "no_session"])
async def test_finished_delivery_rejects_stale_scope_before_output_retention(
    stale: str,
) -> None:
    _, worker, _, session, trial = _started_case(recording_unavailable=False)
    report = control.FinishedReport(context=control.ReportContext(work=trial.work))
    slot = SessionSlot(current=session)
    if stale == "session":
        session.work.session.controller_generation = str(uuid4())
    elif stale == "trial":
        session.trial = None
    elif stale == "report":
        report.context.work.trial.trial_id = str(uuid4())
    else:
        slot.current = None
    delivery = TrialReportDelivery(
        session_slot=slot,
        workers={worker.context.camera: worker},
        controller=cast(ControllerPort, object()),
        commands=CommandLedger(
            str(uuid4()),
            1_000,
            max_records=16,
            max_bytes=1_000_000,
            result_reservation_bytes=4096,
        ),
        clock=lambda: 100,
    )
    assert (
        await delivery.deliver(trial, "finished", report, 500)
    ).failure.code == "STALE_FINISHED"
    assert not session.output_results and trial.finished_report is None


async def test_finished_aggregation_delivers_current_trial_once() -> None:
    _, worker, evidence, session, trial = _started_case(recording_unavailable=False)
    assert worker.trial is not None and session.confirmed_settings is not None
    session.confirmed_settings.behavioral.save_video = False
    worker.trial.stop = evidence.operation
    worker.child_operations[evidence.operation.command_id].kind = "stop_trial"
    trial.stop = evidence.operation
    evidence.finished.activity_stopped = True
    worker.lifecycle_evidence[
        (trial.work.trial.trial_id, evidence.operation.command_id, "finished")
    ] = evidence
    policies = control.ControlPolicies()
    policies.trial_finished.initial_ns = 250
    calls: list[control.LifecycleReport] = []

    class Controller:
        async def report_lifecycle(
            self, report: control.LifecycleReport, *, deadline_ns: int
        ) -> control.ReportReceipt:
            assert deadline_ns == 370
            calls.append(report)
            return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)

    owner = TrialLifecycleReports(
        identity=CoordinatorIdentity(
            control.BackendContext(
                backend_name="acquisition", backend_generation=str(uuid4())
            ),
            worker.context.owner,
            control.ProcessIdentity(),
            control.ProcessIdentity(),
            control.ProcessIdentity(),
        ),
        session_slot=SessionSlot(current=session),
        workers={worker.context.camera: worker},
        controller=cast(ControllerPort, Controller()),
        policies=policies,
        commands=CommandLedger(
            str(uuid4()),
            1_000,
            max_records=16,
            max_bytes=1_000_000,
            result_reservation_bytes=4096,
        ),
        lock=asyncio.Lock(),
        clock=lambda: 120,
    )
    for _ in range(2):
        receipt = await owner.report(worker, evidence, ingress_ns=120)
        assert receipt.result == control.COMMAND_RESULT_ACCEPTED
    assert len(calls) == 1
    assert calls[0].finished.context.work == trial.work
    assert trial.finished_report == calls[0].finished
    assert trial.pending_finished_report is None
