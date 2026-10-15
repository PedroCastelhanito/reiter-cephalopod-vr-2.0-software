"""Session preparation validation and manual-owner handoff."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from cephvr.acquisition.coordinator.evidence_telemetry import WorkerTelemetryReports
from cephvr.acquisition.coordinator.session import SessionSetup
from cephvr.acquisition.coordinator.session_preparation import SessionPreparation
from cephvr.acquisition.coordinator.session_validation import validate_setup_request
from cephvr.acquisition.coordinator.trial_preparation import TrialPreparation
from cephvr.acquisition.state import (
    ChildOperation,
    ConfigurationRecord,
    CoordinatorIdentity,
    LaunchRecord,
    PulseRecord,
    SessionRecord,
    SessionSlot,
    TrialRecord,
    WorkerRecord,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.acquisition.v1 import runtime_pb2 as runtime
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.commands import CommandLedger


class _SerialOwner:
    def __init__(self) -> None:
        self.closed = False

    async def close(self, *, deadline_ns: int) -> None:
        assert deadline_ns == 500
        self.closed = True


def test_session_handoff_closes_manual_serial_owner_without_camera_workers() -> None:
    owner = _SerialOwner()
    pulse = PulseRecord(observation=mcu.MicrocontrollerObservation(port="COM7"))
    preparation = cast(
        SessionPreparation,
        SimpleNamespace(
            workers=SimpleNamespace(workers={}),
            pulse=pulse,
            serial=owner,
            clock=lambda: 100,
        ),
    )

    asyncio.run(SessionPreparation.retire_manual_workers(preparation, deadline_ns=500))

    assert owner.closed
    assert pulse.observation is None


def _setup_request(
    *, tracking_backend: bool = False
) -> tuple[wire.SetupSessionRequest, ConfigurationRecord, CoordinatorIdentity]:
    controller = control.ProcessIdentity(role="controller", generation="controller-1")
    supervisor = control.ProcessIdentity(role="supervisor", generation="supervisor-1")
    tracking = control.ProcessIdentity(role="tracking", generation="tracking-1")
    backend = control.BackendContext(
        backend_name="acquisition", backend_generation="acquisition-1"
    )
    session = control.SessionContext(session_id="session-1")
    policies = runtime.AcquisitionFilePolicies(contract_version=11)
    settings = control.AcquisitionSettings()
    settings.behavioral.enabled = True
    request = wire.SetupSessionRequest(
        command=wire.BackendCommand(
            command_id="setup-1",
            issuer=controller,
            target=backend,
            work=control.WorkContext(session=session),
        ),
        settings=control.BackendSettings(
            backend_name="acquisition", enabled=True, acquisition=settings
        ),
        acquisition_policies=policies,
        plan=control.PreparedSession(
            context=session,
            configuration_revision=0,
        ),
    )
    if tracking_backend:
        request.plan.configuration.backends.add(backend_name="tracking", enabled=True)
    configuration = ConfigurationRecord(
        settings=control.AcquisitionSettings(), file_policies=policies
    )
    identity = CoordinatorIdentity(
        backend=backend,
        process=control.ProcessIdentity(role="acquisition", generation="acquisition-1"),
        controller=controller,
        supervisor=supervisor,
        tracking=tracking,
    )
    return request, configuration, identity


def test_setup_accepts_zero_revision_when_tracking_is_inactive() -> None:
    request, configuration, identity = _setup_request()
    result = validate_setup_request(
        request,
        100,
        identity=identity,
        configuration=configuration,
        clock=lambda: 1,
    )
    assert result.configuration_revision == 0
    assert not result.tracking_required


def test_setup_requires_tracking_camera_only_for_enabled_tracking_backend() -> None:
    request, configuration, identity = _setup_request(tracking_backend=True)
    with pytest.raises(ValueError, match="requires the tracking camera"):
        validate_setup_request(
            request,
            100,
            identity=identity,
            configuration=configuration,
            clock=lambda: 1,
        )


def test_tracking_camera_alone_does_not_imply_a_tracking_consumer() -> None:
    request, configuration, identity = _setup_request()
    request.settings.acquisition.tracking.enabled = True
    result = validate_setup_request(
        request,
        100,
        identity=identity,
        configuration=configuration,
        clock=lambda: 1,
    )
    assert camera.CAMERA_ROLE_TRACKING in result.required_cameras
    assert not result.tracking_required


def test_setup_retains_exact_acquisition_output_reservations() -> None:
    request, configuration, identity = _setup_request()
    request.settings.acquisition.behavioral.save_video = True
    trial = request.plan.trials.add(
        context=control.TrialContext(
            session=request.plan.context,
            trial_id="trial-1",
            trial_number=1,
        )
    )
    del trial
    for tag, extension in (
        ("behavioral_cam", "mp4"),
        ("behavioral_cam_frames", "jsonl"),
    ):
        request.plan.outputs.add(
            backend=identity.backend,
            output_key=f"trial-1:acquisition:{tag}",
            trial=request.plan.trials[0].context,
            output_tag=tag,
            extension=extension,
        )

    result = validate_setup_request(
        request,
        100,
        identity=identity,
        configuration=configuration,
        clock=lambda: 1,
    )

    assert [item.output_key for item in result.reserved_outputs] == [
        "trial-1:acquisition:behavioral_cam",
        "trial-1:acquisition:behavioral_cam_frames",
    ]


def test_setup_rejects_incomplete_output_closure_before_ready() -> None:
    request, configuration, identity = _setup_request()
    request.settings.acquisition.behavioral.save_video = True
    request.plan.trials.add(
        context=control.TrialContext(
            session=request.plan.context,
            trial_id="trial-1",
            trial_number=1,
        )
    )
    request.plan.outputs.add(
        backend=identity.backend,
        output_key="trial-1:acquisition:behavioral_cam",
        trial=request.plan.trials[0].context,
        output_tag="behavioral_cam",
        extension="mp4",
    )

    with pytest.raises(ValueError, match="reservations differ"):
        validate_setup_request(
            request,
            100,
            identity=identity,
            configuration=configuration,
            clock=lambda: 1,
        )


@pytest.mark.parametrize("ingress_ns", (50, 101))
def test_setup_surfaces_retained_camera_failure_under_original_deadline(
    ingress_ns: int,
) -> None:
    async def scenario() -> None:
        operation = control.OperationContext(command_id="camera-setup")
        child = ChildOperation(
            command_id=operation.command_id,
            camera=camera.CAMERA_ROLE_BEHAVIORAL,
            work=control.WorkContext(),
            parent_operation=control.OperationContext(command_id="parent"),
            kind="setup_session",
            deadline_ns=100,
        )
        child.report = control.OperationState(
            context=operation,
            complete=True,
            succeeded=False,
            failure=control.Failure(code="ENCODER", message="unsupported input"),
        )
        child.report_ingress_ns = ingress_ns
        worker = cast(
            WorkerRecord,
            SimpleNamespace(
                setup_operation=operation,
                child_operations={operation.command_id: child},
                context=SimpleNamespace(camera=camera.CAMERA_ROLE_BEHAVIORAL),
            ),
        )
        setup = cast(
            SessionSetup, SimpleNamespace(lock=asyncio.Lock(), clock=lambda: 1)
        )
        error = RuntimeError if ingress_ns <= 100 else TimeoutError
        match = "ENCODER: unsupported input" if ingress_ns <= 100 else "deadline"
        with pytest.raises(error, match=match):
            await SessionSetup._wait_worker_setup(setup, (worker,), 100)

    asyncio.run(scenario())


def test_trial_preparation_surfaces_exact_worker_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cephvr.acquisition.coordinator import trial_preparation as module

    async def scenario() -> None:
        work = control.WorkContext(trial=control.TrialContext(trial_id="trial"))
        child = ChildOperation(
            command_id="prepare",
            camera=camera.CAMERA_ROLE_BEHAVIORAL,
            work=work,
            parent_operation=control.OperationContext(command_id="parent"),
            kind="prepare_trial",
            deadline_ns=100,
        )
        child.report = control.OperationState(
            context=control.OperationContext(command_id=child.command_id),
            work=work,
            complete=True,
            succeeded=False,
            failure=control.Failure(code="WRITER", message="cannot prepare output"),
        )
        child.report_ingress_ns = 50

        async def prepare(payload, *, deadline_ns):
            assert deadline_ns == 100 and payload.command.command_id == child.command_id
            return control.CommandAdmission(result=control.COMMAND_RESULT_ACCEPTED)

        port = SimpleNamespace(prepare_trial=prepare)
        worker = SimpleNamespace(
            port=port,
            child_operations={child.command_id: child},
            context=SimpleNamespace(camera=camera.CAMERA_ROLE_BEHAVIORAL),
        )
        monkeypatch.setattr(
            module,
            "retain_worker_command",
            lambda *args, **kwargs: (
                acq.WorkerCommand(command_id=child.command_id),
                child,
                port,
            ),
        )
        preparation = cast(
            module.TrialPreparation,
            SimpleNamespace(
                workers={camera.CAMERA_ROLE_BEHAVIORAL: worker},
                lock=asyncio.Lock(),
                clock=lambda: 1,
            ),
        )
        with pytest.raises(RuntimeError, match="WRITER: cannot prepare output"):
            await module.TrialPreparation._prepare_workers(
                preparation,
                SimpleNamespace(
                    required_cameras={camera.CAMERA_ROLE_BEHAVIORAL},
                    expected_attachments={},
                ),
                SimpleNamespace(work=work, configuration_revision=1),
                wire.PrepareTrialRequest(
                    command=wire.BackendCommand(command_id="parent")
                ),
                100,
            )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "change",
    ["none", "session", "trial", "interrupted", "cancelled", "deadline", "concurrent"],
)
async def test_trial_publication_preserves_ready_heartbeat_during_off_preflight(
    change: str,
) -> None:
    setup, _, identity = _setup_request()
    setup.command.work.session.session_id = str(uuid4())
    session = SessionRecord(
        work=setup.command.work,
        operation=control.OperationContext(command_id="setup"),
        configuration_revision=1,
        confirmed_revision=1,
        required_cameras={camera.CAMERA_ROLE_BEHAVIORAL},
        ready_report=control.ReadyReport(),
    )
    slot = SessionSlot(current=session)
    lock = asyncio.Lock()
    clock = [100]
    entered, release = asyncio.Event(), asyncio.Event()
    off_calls = []
    generation = str(uuid4())
    worker_context = acq.WorkerContext(
        worker=control.ProcessIdentity(
            role="acquisition_behavioral_worker", generation=generation
        ),
        owner=identity.process,
        work=session.work,
        camera=camera.CAMERA_ROLE_BEHAVIORAL,
    )
    ledger = CommandLedger(
        generation,
        60_000,
        max_records=32,
        max_bytes=1024 * 1024,
        result_reservation_bytes=4096,
    )
    worker = WorkerRecord(
        context=worker_context,
        port=None,
        launch=LaunchRecord(
            command_id=str(uuid4()),
            worker=worker_context.worker,
            owner=identity.process,
            work=session.work,
            camera=worker_context.camera,
            parent_operation=session.operation,
            planned_ns=1,
        ),
        commands=ledger,
    )
    telemetry = WorkerTelemetryReports(
        backend=identity.backend,
        workers={worker_context.camera: worker},
        commands=ledger,
        current_session=lambda: slot.current,
        controller=cast(object, object()),
        lock=lock,
    )

    async def heartbeat(stamp, *, wrong=False):
        message = control.HeartbeatReport(
            source=worker_context.worker,
            work=session.work,
            session_phase=control.SESSION_PHASE_READY,
            sent_monotonic_ns=stamp,
        )
        if wrong:
            message.work.session.session_id = "unowned-session"
        return await telemetry.report_heartbeat(
            message, ingress_ns=100, deadline_ns=500
        )

    async def ensure_off(value, deadline):
        assert value is session and deadline == 500
        assert session.trial is None and worker.trial is None
        off_calls.append(deadline)
        entered.set()
        await release.wait()

    async def camera_prepare(payload, *, deadline_ns):
        assert deadline_ns == 500
        trial = session.trial
        assert trial is not None and worker.trial is not None
        child = worker.child_operations[worker.trial.preparation.command_id]
        assert child.work == trial.work and child.parent_operation == trial.preparation
        assert (await heartbeat(200)).result == control.COMMAND_RESULT_ACCEPTED
        child.report = control.OperationState(
            context=control.OperationContext(command_id=payload.command.command_id),
            work=trial.work,
            complete=True,
            succeeded=True,
        )
        child.report_ingress_ns = 100
        trial.ready_confirmed.set()
        return control.CommandAdmission(result=control.COMMAND_RESULT_ACCEPTED)

    worker.port = SimpleNamespace(prepare_trial=camera_prepare)

    async def controller_report(*args, **kwargs):
        return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)

    preparation = TrialPreparation(
        identity=identity,
        session_slot=slot,
        workers={worker_context.camera: worker},
        resources={},
        controller=SimpleNamespace(report_lifecycle=controller_report),
        prior_completion_confirmed=lambda previous: True,
        pulse_boundaries=SimpleNamespace(ensure_outputs_off=ensure_off),
        lock=lock,
        clock=lambda: clock[0],
    )
    context = control.TrialContext(
        session=session.work.session, trial_id=str(uuid4()), trial_number=1
    )
    request = wire.PrepareTrialRequest(
        command=wire.BackendCommand(
            command_id=str(uuid4()),
            issuer=identity.controller,
            target=identity.backend,
            work=control.WorkContext(trial=context),
        ),
        configuration_revision=1,
        plan=control.TrialPlan(context=context, resolved_duration_ns=1_000_000_000),
    )
    first = asyncio.create_task(preparation.prepare(request, deadline_ns=500))
    await entered.wait()
    assert (await heartbeat(100)).result == control.COMMAND_RESULT_ACCEPTED
    assert (await heartbeat(101, wrong=True)).result == control.COMMAND_RESULT_REJECTED
    second = None
    if change == "concurrent":
        another = wire.PrepareTrialRequest.FromString(request.SerializeToString())
        another.command.command_id = str(uuid4())
        another.plan.context.trial_id = str(uuid4())
        another.command.work.trial.CopyFrom(another.plan.context)
        second = asyncio.create_task(preparation.prepare(another, deadline_ns=500))
        await asyncio.sleep(0)
        assert not second.done() and off_calls == [500]
    elif change == "session":
        slot.current = replace(session)
    elif change == "trial":
        session.trial = TrialRecord(
            work=control.WorkContext(trial=context),
            plan=request.plan,
            preparation=control.OperationContext(command_id="other"),
            configuration_revision=1,
        )
    elif change == "interrupted":
        session.interrupted = True
    elif change == "cancelled":
        session.setup_cancelled = True
    elif change == "deadline":
        clock[0] = 500
    release.set()
    result = await first
    assert result.result == (
        control.COMMAND_RESULT_ACCEPTED
        if change in {"none", "concurrent"}
        else control.COMMAND_RESULT_REJECTED
    )
    if change not in {"none", "concurrent"}:
        assert worker.trial is None and not worker.child_operations
    if second is not None:
        assert (await second).result == control.COMMAND_RESULT_REJECTED
        assert off_calls == [500]


def test_setup_rejects_required_tracking_without_a_launched_identity():
    request, configuration, identity = _setup_request(tracking_backend=True)
    request.settings.acquisition.tracking.enabled = True
    identity.tracking.Clear()
    with pytest.raises(ValueError, match="no launched Tracking identity"):
        validate_setup_request(
            request,
            100,
            identity=identity,
            configuration=configuration,
            clock=lambda: 1,
        )


async def test_required_tracking_identity_is_checked_before_any_ring_allocation():
    from cephvr.acquisition.coordinator.session_resources import allocate_camera_outputs

    with pytest.raises(ValueError, match="no launched Tracking identity"):
        await allocate_camera_outputs(
            session=None,
            worker=None,
            resolved=camera.CameraResolvedState(),
            tracking_consumer=control.ProcessIdentity(),
            tracking_required=True,
            settings=control.AcquisitionSettings(),
            resources={},
            ledger=None,
            port=None,
            declare_resource=None,
        )
