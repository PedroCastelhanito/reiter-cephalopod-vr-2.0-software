"""Cleanup fanout, exact output evidence and retained terminal results."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from cephvr.acquisition.coordinator.cleanup import CoordinatorCleanup
from cephvr.acquisition.coordinator.cleanup_diagnostics import (
    missing_worker_cleanup_failure,
    worker_cleanup_failure,
)
from cephvr.acquisition.coordinator.manual_device_status import (
    ManualDeviceStatusReporter,
)
from cephvr.acquisition.coordinator.queries import CoordinatorQueries
from cephvr.acquisition.coordinator.sessionless_cleanup import SessionlessCleanup
from cephvr.acquisition.coordinator.shutdown import CoordinatorShutdown
from cephvr.acquisition.ports import (
    ControllerPort,
    ResourcePort,
    SerialOwnerPort,
    SupervisorPort,
)
from cephvr.acquisition.runtime import AcquisitionCoordinatorRuntime
from cephvr.acquisition.state import (
    CoordinatorIdentity,
    LaunchRecord,
    PulseRecord,
    SessionRecord,
    SessionSlot,
    WorkerRecord,
)
from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.resource_ledger import NativeResourceLedger
from cephvr.shared.commands import CommandLedger


@pytest.mark.parametrize(
    "case",
    [
        "before_setup",
        "ready",
        "missing_device",
        "wrong_device",
        "failed_release",
        "setup_sent",
        "expected_ring",
        "allocated_ring",
        "wrong_work",
        "wrong_role",
        "unexpected_output",
        "unexpected_resource",
        "missing_commands",
        "prepared_empty",
        "prepared_ring",
        "prepared_ring_attached",
        "prepared_ring_missing_release",
        "prepared_ring_wrong_peer",
        "prepared_ring_wrong_transfer",
        "prepared_ring_wrong_target",
        "prepared_ring_wrong_work",
    ],
)
def test_worker_cleanup_before_setup_requires_exact_device_only_proof(case):
    from cephvr.acquisition.coordinator.evidence_cleanup import WorkerCleanupEvidence
    from cephvr.acquisition.state import ChildOperation, ResourceRecord
    from cephvr.platform.windows.resource_ledger import ResourceKey

    work = control.WorkContext(session=control.SessionContext(session_id=str(uuid4())))
    role = camera_pb2.CAMERA_ROLE_BEHAVIORAL
    identity = control.ProcessIdentity(generation=str(uuid4()), role="camera")
    owner = control.ProcessIdentity(generation=str(uuid4()), role="acquisition")
    commands = CommandLedger(
        str(uuid4()),
        1_000_000,
        max_records=100,
        max_bytes=1_000_000,
        result_reservation_bytes=1024,
    )
    session = SessionRecord(
        work=work,
        operation=control.OperationContext(command_id=str(uuid4())),
        configuration_revision=1,
        required_cameras={role},
    )
    worker = WorkerRecord(
        context=acq.WorkerContext(camera=role, worker=identity, work=work),
        port=None,
        launch=LaunchRecord(
            command_id=str(uuid4()),
            worker=identity,
            owner=owner,
            work=work,
            camera=role,
            parent_operation=session.operation,
            planned_ns=1,
        ),
        commands=commands,
    )
    cleanup = acq.WorkerCleanupEvidence()
    release = cleanup.resources.add(
        resource=f"camera-device:{identity.generation}",
        released=True,
    )
    resources = {}
    ledger = NativeResourceLedger(max_resources=10, max_transfers_per_resource=4)
    if case.startswith("prepared_"):
        session.setup_cancelled = True
        worker.setup_operation = control.OperationContext(command_id=str(uuid4()))
        worker.child_operations[worker.setup_operation.command_id] = ChildOperation(
            command_id=worker.setup_operation.command_id,
            camera=role,
            work=control.WorkContext.FromString(work.SerializeToString()),
            parent_operation=session.operation,
            kind="setup_session",
        )
        if case == "prepared_ring_wrong_work":
            worker.child_operations[
                worker.setup_operation.command_id
            ].work.session.session_id = str(uuid4())
        if case != "prepared_empty":
            transfer_id = str(uuid4())
            attachment = acq.FrameBufferAttachment()
            attachment.buffer.producer.CopyFrom(identity)
            attachment.buffer.owner.CopyFrom(owner)
            attachment.sync.target.CopyFrom(identity)
            attachment.sync.transfer_id = transfer_id
            key = ResourceKey("ring", owner.generation)
            resources["ring"] = ResourceRecord(
                attachment=attachment, ring=None, ledger_key=key
            )
            session.expected_attachments[role] = {"ring"}
            ledger.register(key, kind="ring")
            peer_id = (
                str(uuid4())
                if case == "prepared_ring_wrong_peer"
                else identity.generation
            )
            ledger.expect_attachment(
                key, peer_instance_id=peer_id, transfer_id=transfer_id
            )
            if case == "prepared_ring_attached":
                ledger.confirm_attachment(
                    key, peer_instance_id=peer_id, transfer_id=transfer_id
                )
            if case == "prepared_ring_wrong_transfer":
                attachment.sync.transfer_id = str(uuid4())
            if case == "prepared_ring_wrong_target":
                attachment.sync.target.generation = str(uuid4())
            if case != "prepared_ring_missing_release":
                cleanup.resources.add(resource="ring", released=True)
    if case == "ready":
        worker.setup_ready = acq.WorkerReadyEvidence(required_checks_passed=True)
    elif case == "missing_device":
        cleanup.ClearField("resources")
    elif case == "wrong_device":
        release.resource = f"camera-device:{uuid4()}"
    elif case == "failed_release":
        release.released = False
    elif case == "setup_sent":
        worker.setup_operation = control.OperationContext(command_id=str(uuid4()))
    elif case == "expected_ring":
        session.expected_attachments[role] = {"ring"}
    elif case == "allocated_ring":
        attachment = acq.FrameBufferAttachment()
        attachment.buffer.producer.CopyFrom(identity)
        resources["ring"] = ResourceRecord(
            attachment=attachment,
            ring=None,
            ledger_key=ResourceKey("ring", owner.generation),
        )
    elif case == "wrong_work":
        worker.context.work.session.session_id = str(uuid4())
    elif case == "wrong_role":
        session.required_cameras.clear()
    elif case == "unexpected_output":
        cleanup.outputs.add(output_key="unexpected", artifact_present=False)
    elif case == "unexpected_resource":
        cleanup.resources.add(resource="unknown", released=True)
    elif case == "missing_commands":
        worker.commands = None
    evidence = WorkerCleanupEvidence(
        resources=resources,
        resource_ledger=ledger,
        commands=commands,
    )
    if case in {
        "before_setup",
        "ready",
        "prepared_empty",
        "prepared_ring",
        "prepared_ring_attached",
    }:
        evidence.retain(session, worker, cleanup)
        evidence.retain(session, worker, cleanup)
        assert (worker.setup_ready is None) == (case != "ready")
        if "ring" in resources:
            snapshot = ledger.snapshot(resources["ring"].ledger_key)
            assert snapshot.transfers[0].released
            assert snapshot.transfers[0].attached == (case == "prepared_ring_attached")
            assert ledger.may_close_owner(resources["ring"].ledger_key)
    else:
        with pytest.raises(ValueError):
            evidence.retain(session, worker, cleanup)
        if "ring" in resources and case.startswith("prepared_"):
            assert (
                not ledger.snapshot(resources["ring"].ledger_key).transfers[0].released
            )


@pytest.mark.parametrize(
    "case", ["closed", "delivery_pending", "resources_pending", "wrong_work"]
)
async def test_shutdown_preserves_delivered_session_cleanup_identity(case: str) -> None:
    work = control.WorkContext(session=control.SessionContext(session_id=str(uuid4())))
    session = SessionRecord(
        work=work,
        operation=control.OperationContext(command_id=str(uuid4())),
        configuration_revision=1,
        required_cameras=set(),
    )
    session.cleanup_complete = case != "resources_pending"
    session.cleanup_delivery_complete = case != "delivery_pending"
    owner = object.__new__(CoordinatorShutdown)
    owner.session_slot = SessionSlot(current=session)
    owner.shutdown_requested = asyncio.Event()
    owner.cleanup_session = AsyncMock(
        return_value=control.CommandAdmission(result=control.COMMAND_RESULT_REJECTED)
    )
    command = wire.BackendCommand(command_id=str(uuid4()), work=work)
    if case == "wrong_work":
        command.work.session.session_id = str(uuid4())
    result = await owner.request_shutdown(command, deadline_ns=100)
    if case == "closed":
        owner.cleanup_session.assert_not_awaited()
        assert result.result == control.COMMAND_RESULT_ACCEPTED
        assert result.command_id == command.command_id
        assert owner.shutdown_requested.is_set()
    else:
        owner.cleanup_session.assert_awaited_once_with(command, deadline_ns=100)
        assert result.result == control.COMMAND_RESULT_REJECTED
        assert not owner.shutdown_requested.is_set()


async def test_unconfirmed_preview_release_still_attempts_capture_and_pulse_cleanup() -> (
    None
):
    owner = CoordinatorCleanup.__new__(CoordinatorCleanup)
    owner._active = False
    owner.close_firmware = None
    owner.close_preview_windows = AsyncMock(
        side_effect=RuntimeError("viewer still owned")
    )
    owner._execute = AsyncMock(
        return_value=control.CommandAdmission(result=control.COMMAND_RESULT_ACCEPTED)
    )
    command = wire.BackendCommand(command_id=str(uuid4()))
    result = await owner.execute(command, deadline_ns=100)
    owner._execute.assert_awaited_once_with(command, deadline_ns=100)
    assert result.result == control.COMMAND_RESULT_REJECTED
    assert result.failure.code == "PREVIEW_RELEASE_UNCONFIRMED"
    assert not owner._active


@pytest.mark.parametrize(
    "cleanup_result",
    [control.COMMAND_RESULT_ACCEPTED, control.COMMAND_RESULT_REJECTED],
)
async def test_cancel_setup_runs_aggregate_cleanup_and_returns_its_admission(
    cleanup_result: int,
) -> None:
    cleanup = _cleanup_owner()
    work = control.WorkContext(session=control.SessionContext(session_id=str(uuid4())))
    session = SimpleNamespace(work=work, cleanup_deadline_ns=None)

    class SessionCancellation:
        async def cancel(self, current: object, *, deadline_ns: int) -> None:
            assert current is session
            session.cleanup_deadline_ns = deadline_ns

    request = wire.BackendCommand(
        command_id=str(uuid4()),
        issuer=cleanup.identity.controller,
        target=cleanup.identity.backend,
        work=work,
    )
    admission = control.CommandAdmission(
        result=cleanup_result, command_id=request.command_id
    )
    cleanup.execute = AsyncMock(return_value=admission)
    runtime = object.__new__(AcquisitionCoordinatorRuntime)
    runtime.state = SimpleNamespace(session_slot=SessionSlot(current=session))
    runtime.coordinator_identity = cleanup.identity
    runtime.clock = lambda: 1
    runtime.session = SessionCancellation()
    runtime.cleanup_owner = cleanup

    result = await runtime.cancel_setup(request, deadline_ns=100)

    assert session.cleanup_deadline_ns == 100
    cleanup.execute.assert_awaited_once_with(request, deadline_ns=100)
    assert result is admission


def _cleanup_owner() -> CoordinatorCleanup:
    generation = "00000000-0000-4000-8000-000000000001"
    identity = CoordinatorIdentity(
        backend=control.BackendContext(
            backend_name="acquisition", backend_generation=generation
        ),
        process=control.ProcessIdentity(role="acquisition", generation=generation),
        controller=control.ProcessIdentity(
            role="controller", generation="00000000-0000-4000-8000-000000000002"
        ),
        supervisor=control.ProcessIdentity(
            role="supervisor", generation="00000000-0000-4000-8000-000000000003"
        ),
        tracking=control.ProcessIdentity(
            role="tracking", generation="00000000-0000-4000-8000-000000000004"
        ),
    )
    return CoordinatorCleanup(
        identity=identity,
        session_slot=SessionSlot(),
        workers={},
        resources={},
        pulse=PulseRecord(),
        resource_ledger=NativeResourceLedger(
            max_resources=8, max_transfers_per_resource=4
        ),
        commands=CommandLedger(
            generation,
            300_000_000_000,
            max_records=32,
            max_bytes=2 * 1024 * 1024,
            result_reservation_bytes=64 * 1024,
        ),
        resource_port=cast(ResourcePort, object()),
        serial=cast(SerialOwnerPort, object()),
        controller=cast(ControllerPort, object()),
        supervisor=cast(SupervisorPort, object()),
        worker_cleanup_complete=lambda _worker, _evidence: True,
        lock=asyncio.Lock(),
        clock=lambda: 10,
    )


def _session() -> SessionRecord:
    work = control.WorkContext(
        session=control.SessionContext(
            session_id="00000000-0000-4000-8000-000000000005"
        )
    )
    return SessionRecord(
        work=work,
        operation=control.OperationContext(
            command_id="00000000-0000-4000-8000-000000000006"
        ),
        configuration_revision=1,
        required_cameras=set(),
        reserved_outputs=[
            control.OutputPlan(
                output_key="00000000-0000-4000-8000-000000000007:acquisition:behavioral_cam",
                output_tag="behavioral_cam",
                extension="mp4",
            )
        ],
        cleanup_resources_revision=1,
    )


@pytest.mark.parametrize(
    ("evidence", "expected_reason"),
    [
        (
            acq.WorkerCleanupEvidence(),
            "behavioral camera worker generation camera-generation cleanup is missing native resource release evidence for camera-device:camera-generation",
        ),
        (
            acq.WorkerCleanupEvidence(
                resources=[
                    control.ResourceRelease(
                        resource="camera-device:camera-generation", released=False
                    )
                ]
            ),
            "behavioral camera worker generation camera-generation cleanup native resource remains unreleased: camera-device:camera-generation",
        ),
        (
            acq.WorkerCleanupEvidence(
                resources=[
                    control.ResourceRelease(
                        resource="camera-device:camera-generation", released=True
                    )
                ],
                outputs=[
                    control.OutputResult(
                        output_key="behavioral_video",
                        closure=control.OUTPUT_CLOSURE_CLOSED,
                        artifact_present=False,
                    )
                ],
            ),
            "behavioral camera worker generation camera-generation cleanup is missing the closed output artifact behavioral_video",
        ),
    ],
)
def test_worker_cleanup_failure_identifies_missing_proof(evidence, expected_reason):
    worker = SimpleNamespace(
        context=SimpleNamespace(camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL),
        launch=SimpleNamespace(
            worker=control.ProcessIdentity(
                role="camera", generation="camera-generation"
            )
        ),
        setup_ready=None,
        preview=None,
    )

    assert worker_cleanup_failure(worker, evidence) == expected_reason


def test_missing_retained_cleanup_reason_is_exact_and_worker_scoped():
    worker = SimpleNamespace(
        launch=SimpleNamespace(
            worker=control.ProcessIdentity(
                role="camera", generation="camera-generation"
            )
        ),
    )
    assert missing_worker_cleanup_failure(worker) == (
        "camera camera worker generation camera-generation cleanup retained evidence is missing"
    )


def test_failed_output_with_retained_reason_remains_valid_cleanup_evidence():
    worker = SimpleNamespace(
        context=SimpleNamespace(camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL),
        launch=SimpleNamespace(
            worker=control.ProcessIdentity(
                role="camera", generation="camera-generation"
            )
        ),
        setup_ready=None,
        preview=None,
    )
    evidence = acq.WorkerCleanupEvidence(
        resources=[
            control.ResourceRelease(
                resource="camera-device:camera-generation", released=True
            )
        ],
        outputs=[
            control.OutputResult(
                output_key="behavioral_video",
                closure=control.OUTPUT_CLOSURE_FAILED,
                artifact_present=False,
                failure=control.Failure(code="ENCODER_FAILED", message="close failed"),
            )
        ],
    )

    assert worker_cleanup_failure(worker, evidence) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "transport", "rejected"])
@pytest.mark.parametrize("cancel_failed", [False, True])
async def test_cleanup_delivers_terminal_off_failure_without_claiming_release(
    monkeypatch, failure, cancel_failed
):
    from cephvr.acquisition.worker.trial_lifecycle import WorkerTrialLifecycle

    owner, session = _cleanup_owner(), _session()
    session.cleanup_resources.append(
        control.ResourceObligation(resource="microcontroller-claim:COM8")
    )
    owner.pulse.observation = mcu.MicrocontrollerObservation(connection_id="exact")
    evidence = mcu.PulseCommandEvidence(
        connection_id="exact",
        request_id="known-rejected-request",
        command=mcu.PULSE_BOUNDARY_COMMAND_OFF,
        behavioral_selected=True,
        outcome=mcu.PULSE_COMMAND_OUTCOME_REJECTED,
    )
    serial = SimpleNamespace(
        cancel_on_reservations=AsyncMock(
            side_effect=RuntimeError("cancel failed") if cancel_failed else None
        ),
        off=AsyncMock(
            return_value=evidence,
            side_effect=TimeoutError("OFF timeout")
            if failure == "timeout"
            else RuntimeError("OFF transport failed")
            if failure == "transport"
            else None,
        ),
        close=AsyncMock(),
    )
    owner.serial = serial
    capture = SimpleNamespace(session_pulse_off=None)
    context = acq.WorkerContext(
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL, work=session.work
    )
    worker = SimpleNamespace(
        bootstrap=SimpleNamespace(context=context), captures=capture
    )

    async def deliver(actual_session, workers, pulse, **kwargs):
        assert actual_session is session and kwargs["deadline_ns"] == 100
        WorkerTrialLifecycle._record_session_off(
            worker,
            acq.WorkerPulseEvidence(
                command=acq.WorkerCommand(target=context),
                camera=context.camera,
                evidence=pulse,
            ),
        )

    monkeypatch.setattr(
        "cephvr.acquisition.coordinator.cleanup.deliver_session_pulse_evidence",
        deliver,
    )
    failures = []
    assert not await owner._stop_and_close_serial(session, 100, failures)
    assert failures and not session.serial_owner_released
    assert capture.session_pulse_off is not None
    assert capture.session_pulse_off.connection_id == "exact"
    assert not capture.session_pulse_off.applied
    if failure != "rejected":
        assert capture.session_pulse_off.stop_issued_monotonic_ns == 10
        assert not capture.session_pulse_off.request_id
        assert not capture.session_pulse_off.HasField("scheduled_boundary_monotonic_ns")
        assert not capture.session_pulse_off.HasField("dispatched_monotonic_ns")
        assert not capture.session_pulse_off.HasField("acknowledged_monotonic_ns")
    serial.off.assert_awaited_once()
    serial.close.assert_not_awaited()


def test_cleanup_reports_never_dispatched_output_as_explicit_absence() -> None:
    report = _cleanup_owner().report_builder.build(
        _session(), "00000000-0000-4000-8000-000000000008", {}, True
    )

    assert len(report.outputs) == 1
    output = report.outputs[0]
    assert output.closure == control.OUTPUT_CLOSURE_NOT_STARTED
    assert output.HasField("artifact_present")
    assert not output.artifact_present
    assert output.camera_video_content == control.CAMERA_VIDEO_CONTENT_NO_FRAMES


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_port", [False, True])
async def test_session_off_delivery_failure_does_not_skip_other_workers(
    monkeypatch, missing_port
):
    from cephvr.acquisition.coordinator.session_pulses import (
        deliver_session_pulse_evidence,
        session_off_failure,
    )

    session = _session()
    session.required_cameras = {
        camera_pb2.CAMERA_ROLE_BEHAVIORAL,
        camera_pb2.CAMERA_ROLE_TRACKING,
    }
    workers = {}
    for role in session.required_cameras:
        workers[role] = SimpleNamespace(
            context=acq.WorkerContext(camera=role, work=session.work),
            setup_operation=control.OperationContext(command_id=str(uuid4())),
            port=SimpleNamespace(
                record_pulse_evidence=AsyncMock(
                    return_value=control.CommandAdmission(
                        result=control.COMMAND_RESULT_REJECTED
                        if role == camera_pb2.CAMERA_ROLE_BEHAVIORAL
                        else control.COMMAND_RESULT_ACCEPTED
                    )
                )
            ),
        )
    if missing_port:
        workers[camera_pb2.CAMERA_ROLE_BEHAVIORAL].port = None
    monkeypatch.setattr(
        "cephvr.acquisition.coordinator.session_pulses.retain_worker_command",
        lambda worker, **kwargs: (
            acq.WorkerCommand(target=worker.context),
            object(),
            worker.port,
        ),
    )
    monkeypatch.setattr(
        "cephvr.acquisition.coordinator.session_pulses.wait_child_operation",
        AsyncMock(return_value=control.OperationState(complete=True, succeeded=True)),
    )
    evidence = session_off_failure(
        tuple(session.required_cameras),
        "exact",
        10,
        mcu.PULSE_COMMAND_OUTCOME_TRANSPORT_FAILED,
    )
    with pytest.raises(
        RuntimeError,
        match="endpoint is unavailable" if missing_port else "worker rejected",
    ):
        await deliver_session_pulse_evidence(
            session,
            workers,
            evidence,
            deadline_ns=100,
            lock=asyncio.Lock(),
            clock=lambda: 10,
        )
    for worker in workers.values():
        if worker.port is not None:
            worker.port.record_pulse_evidence.assert_awaited_once()


def test_cleanup_cannot_invent_never_started_for_dispatched_output() -> None:
    session = _session()
    session.dispatched_output_keys.add(session.reserved_outputs[0].output_key)

    with pytest.raises(ValueError, match="dispatched output"):
        _cleanup_owner().report_builder.build(
            session, "00000000-0000-4000-8000-000000000008", {}, True
        )


def test_cleanup_preserves_exact_worker_output_result() -> None:
    session = _session()
    retained = control.OutputResult(
        output_key=session.reserved_outputs[0].output_key,
        closure=control.OUTPUT_CLOSURE_FAILED,
        artifact_present=False,
        failure=control.Failure(code="ENCODER_FAILED", message="close failed"),
    )
    session.output_results[retained.output_key] = retained

    report = _cleanup_owner().report_builder.build(
        session, "00000000-0000-4000-8000-000000000008", {}, True
    )

    assert report.outputs[0].SerializeToString(
        deterministic=True
    ) == retained.SerializeToString(deterministic=True)


def test_cleanup_reports_keep_terminal_command_retention_after_session_expiry() -> None:
    session = _session()
    ledger = _cleanup_owner().commands
    session.reserve_cleanup_evidence(ledger)
    first_id = "00000000-0000-4000-8000-000000000008"
    ledger.admit(first_id, b"Cleanup", 1, work_key=first_id, priority=True)
    ledger.complete(first_id, b"accepted", 2)
    ledger.finalize_work(first_id, 3)
    session.prepare_cleanup_command(first_id, ledger)
    first = control.CleanupReport(
        work=session.work,
        operation=control.OperationContext(command_id=first_id),
        verified_monotonic_ns=10,
        trial_activity_stopped=True,
        cleanup_resources_revision=1,
    )
    session.retain_cleanup_report(first, ledger)
    first_key = f"acquisition-cleanup-report:{first_id}"
    assert ledger.has_payload(first_key)
    assert ledger.has_payload(
        f"acquisition-cleanup-proof:{session.work.session.session_id}"
    )

    session.archive_cleanup_report(ledger)
    second_id = "00000000-0000-4000-8000-000000000009"
    ledger.admit(second_id, b"Cleanup", 4, work_key=second_id, priority=True)
    ledger.complete(second_id, b"accepted", 5)
    ledger.finalize_work(second_id, 6)
    session.prepare_cleanup_command(second_id, ledger)
    second = control.CleanupReport(
        work=session.work,
        operation=control.OperationContext(command_id=second_id),
        verified_monotonic_ns=10,
        trial_activity_stopped=True,
        cleanup_resources_revision=1,
    )
    session.retain_cleanup_report(second, ledger)

    assert ledger.has_retained_work(first_id)
    assert ledger.has_retained_work(second_id)
    assert session.cleanup_report_history[first_id].operation.command_id == first_id
    assert session.pending_cleanup_report is not None
    assert session.pending_cleanup_report.operation.command_id == second_id


@pytest.mark.asyncio
async def test_cleanup_attempts_both_recipients_even_if_first_delivery_fails() -> None:
    class _Recipient:
        def __init__(self, *, fails: bool) -> None:
            self.fails = fails
            self.calls = 0

        async def report_lifecycle(
            self, _request: control.LifecycleReport, *, deadline_ns: int
        ) -> control.ReportReceipt:
            self.calls += 1
            assert deadline_ns == 20
            if self.fails:
                raise TimeoutError("controller receipt was lost")
            return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)

    owner = _cleanup_owner()
    session = _session()
    session.cleanup_command_id = "00000000-0000-4000-8000-000000000008"
    session.cleanup_attempt_deadline_ns = 20
    session.pending_cleanup_report = control.CleanupReport(
        work=session.work,
        operation=control.OperationContext(command_id=session.cleanup_command_id),
        verified_monotonic_ns=10,
        trial_activity_stopped=True,
        cleanup_resources_revision=1,
    )
    owner.session_slot.current = session
    controller = _Recipient(fails=True)
    supervisor = _Recipient(fails=False)
    owner.controller = cast(ControllerPort, controller)
    owner.supervisor = cast(SupervisorPort, supervisor)

    receipt = await owner._deliver(session, 20)

    assert receipt.result == control.COMMAND_RESULT_REJECTED
    assert controller.calls == 1
    assert supervisor.calls == 1
    assert session.cleanup_report_recipients == {"supervisor"}


@pytest.mark.asyncio
async def test_retained_cleanup_query_survives_original_session_expiry() -> None:
    owner = _cleanup_owner()
    session = _session()
    session_id = session.work.session.session_id
    setup_id = session.operation.command_id
    cleanup_id = "00000000-0000-4000-8000-000000000010"
    ledger = CommandLedger(
        owner.identity.process.generation,
        100,
        max_records=32,
        max_bytes=1_000_000,
        result_reservation_bytes=64 * 1024,
        safety_reserve_records=8,
        safety_reserve_bytes=256 * 1024,
    )
    ledger.admit(setup_id, b"SetupSession", 1, work_key=session_id)
    ledger.complete(setup_id, b"ready", 2)
    session.reserve_cleanup_evidence(ledger)

    command = wire.BackendCommand(
        command_id=cleanup_id,
        target=owner.identity.backend,
        work=session.work,
    )
    canonical = b"Cleanup\0" + command.SerializeToString(deterministic=True)
    ledger.admit(cleanup_id, canonical, 20, work_key=cleanup_id, priority=True)
    session.prepare_cleanup_command(cleanup_id, ledger)
    ledger.complete(
        cleanup_id,
        control.CommandAdmission(
            result=control.COMMAND_RESULT_ACCEPTED, command_id=cleanup_id
        ).SerializeToString(deterministic=True),
        21,
    )
    ledger.complete_executor(
        cleanup_id,
        control.OperationState(
            context=control.OperationContext(command_id=cleanup_id),
            command="Cleanup",
            work=session.work,
            complete=True,
            succeeded=True,
        ).SerializeToString(deterministic=True),
        21,
    )
    report = control.CleanupReport(
        work=session.work,
        operation=control.OperationContext(command_id=cleanup_id),
        verified_monotonic_ns=21,
        trial_activity_stopped=True,
        cleanup_resources_revision=1,
    )
    session.retain_cleanup_report(report, ledger)
    session.archive_cleanup_report(ledger)
    session.handoff_cleanup_proof(ledger)
    session.cleanup_complete = True
    ledger.finalize_work(session_id, 10)
    ledger.finalize_work(cleanup_id, 22)

    slot = SessionSlot(completed={session_id: session})

    class _Status:
        def get_report(self, _command_id: str) -> None:
            return None

    queries = CoordinatorQueries(
        identity=owner.identity,
        session_slot=slot,
        workers={},
        commands=ledger,
        device_status=cast(ManualDeviceStatusReporter, _Status()),
        current_error=lambda: None,
        clock=lambda: 113,
    )
    request = wire.RetainedResultQuery(
        query=wire.BackendQuery(target=owner.identity.backend, work=session.work),
        command_id=cleanup_id,
    )

    result = await queries.get_retained_result(request, deadline_ns=120)

    assert result.found
    assert result.operation.context.command_id == cleanup_id
    assert session_id in slot.completed
    state = await queries.get_state(request.query, deadline_ns=120)
    assert state.session_phase == control.SESSION_PHASE_CONFIGURATION
    assert state.cleanup.operation.command_id == cleanup_id
    assert state.cleanup.work == session.work

    wrong_work = wire.RetainedResultQuery(
        query=wire.BackendQuery(target=owner.identity.backend),
        command_id=cleanup_id,
    )
    unrelated = await queries.get_retained_result(wrong_work, deadline_ns=120)
    assert not unrelated.found


@pytest.mark.asyncio
async def test_current_local_cleanup_proof_outlives_replay_payload_only() -> None:
    owner = _cleanup_owner()
    session = _session()
    session_id = session.work.session.session_id
    cleanup_id = "00000000-0000-4000-8000-000000000011"
    ledger = CommandLedger(
        owner.identity.process.generation,
        100,
        max_records=32,
        max_bytes=1_000_000,
        result_reservation_bytes=64 * 1024,
        safety_reserve_records=8,
        safety_reserve_bytes=256 * 1024,
    )
    session.reserve_cleanup_evidence(ledger)
    command = wire.BackendCommand(
        command_id=cleanup_id,
        target=owner.identity.backend,
        work=session.work,
    )
    ledger.admit(
        cleanup_id,
        b"Cleanup\0" + command.SerializeToString(deterministic=True),
        10,
        work_key=cleanup_id,
        priority=True,
    )
    session.prepare_cleanup_command(cleanup_id, ledger)
    ledger.complete(cleanup_id, b"accepted", 11)
    ledger.complete_executor(cleanup_id, b"complete", 11)
    session.retain_cleanup_report(
        control.CleanupReport(
            work=session.work,
            operation=control.OperationContext(command_id=cleanup_id),
            verified_monotonic_ns=11,
            trial_activity_stopped=True,
            cleanup_resources_revision=1,
        ),
        ledger,
    )
    session.cleanup_complete = True
    ledger.finalize_work(cleanup_id, 12)
    owner.session_slot.current = session

    class _Status:
        def get_report(self, _command_id: str) -> None:
            return None

    queries = CoordinatorQueries(
        identity=owner.identity,
        session_slot=owner.session_slot,
        workers={},
        commands=ledger,
        device_status=cast(ManualDeviceStatusReporter, _Status()),
        current_error=lambda: None,
        clock=lambda: 113,
    )
    query = wire.BackendQuery(target=owner.identity.backend, work=session.work)

    state = await queries.get_state(query, deadline_ns=120)
    retained = await queries.get_retained_result(
        wire.RetainedResultQuery(query=query, command_id=cleanup_id),
        deadline_ns=120,
    )

    assert not state.HasField("cleanup")
    assert not retained.found
    assert cleanup_id not in session.cleanup_report_history
    assert session.pending_cleanup_report is not None
    assert ledger.has_payload(f"acquisition-cleanup-proof:{session_id}")


@pytest.mark.asyncio
async def test_sessionless_cleanup_attempts_serial_off_while_worker_is_stalled() -> (
    None
):
    generation = str(uuid4())
    owner = control.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    worker = control.ProcessIdentity(
        role="acquisition_behavioral_worker", generation=generation
    )
    context = acq.WorkerContext(
        worker=worker,
        owner=owner,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
    )
    record = WorkerRecord(
        context=context,
        port=None,
        launch=LaunchRecord(
            command_id=str(uuid4()),
            worker=worker,
            owner=owner,
            work=control.WorkContext(),
            camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
            parent_operation=control.OperationContext(command_id=str(uuid4())),
            planned_ns=1,
        ),
    )
    worker_finished = asyncio.Event()
    serial_attempted = asyncio.Event()

    class _Cleanup(SessionlessCleanup):
        async def _cleanup_worker(
            self,
            _record: WorkerRecord,
            _request: wire.BackendCommand,
            _deadline_ns: int,
        ) -> WorkerRecord:
            await worker_finished.wait()
            return record

        async def _stop_serial(self, _deadline_ns: int, _failures: list[str]) -> bool:
            serial_attempted.set()
            return True

    ledger = CommandLedger(
        generation,
        300_000_000_000,
        max_records=16,
        max_bytes=2 * 1024 * 1024,
        result_reservation_bytes=64 * 1024,
    )
    cleanup = _Cleanup(
        workers={camera_pb2.CAMERA_ROLE_BEHAVIORAL: record},
        resources={},
        pulse=PulseRecord(observation=mcu.MicrocontrollerObservation()),
        resource_ledger=NativeResourceLedger(
            max_resources=8, max_transfers_per_resource=4
        ),
        commands=ledger,
        resource_port=cast(ResourcePort, object()),
        serial=cast(SerialOwnerPort, object()),
        cleanup_complete=lambda _record, _evidence: True,
        lock=asyncio.Lock(),
        clock=lambda: 10,
    )
    request = wire.BackendCommand(command_id=str(uuid4()))

    pending = asyncio.create_task(cleanup.execute(request, deadline_ns=20))
    await asyncio.wait_for(serial_attempted.wait(), timeout=1)
    assert not pending.done()
    worker_finished.set()
    result = await pending

    assert result.result == control.COMMAND_RESULT_ACCEPTED
