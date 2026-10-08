"""Worker function scopes, terminal admission and evidence capacity reserves."""

from __future__ import annotations

import asyncio
from threading import Event, RLock
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import grpc
import pytest

from cephvr.acquisition.state import LaunchRecord, WorkerRecord
from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.worker.cleanup_lifecycle import WorkerCleanupLifecycle
from cephvr.acquisition.worker.execution import WorkerOperationExecutor
from cephvr.acquisition.worker.function_scopes import validate_camera_function_scopes
from cephvr.acquisition.worker.limits import AcquisitionControlLimits
from cephvr.acquisition.worker.ports import WorkerOperationTicket
from cephvr.acquisition.worker.service import AcquisitionWorkerService
from cephvr.acquisition.worker.state import WorkerState
from cephvr.acquisition.worker.terminal_scope import terminal_target_matches
from cephvr.acquisition.worker.trial_lifecycle import WorkerTrialLifecycle
from cephvr.acquisition.worker.trial_state import WorkerTrialState
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandCapacityError, CommandLedger


@pytest.mark.parametrize("trial", [False, True])
async def test_warning_flush_binds_each_view_to_its_exact_work(trial: bool) -> None:
    from cephvr.acquisition.worker.health import WorkerHealthReporter
    from cephvr.acquisition.worker.warnings import (
        WarningOccurrence,
        WorkerWarningLedger,
    )

    source = acq.WorkerContext(
        worker=control.ProcessIdentity(
            role="acquisition_tracking_worker", generation="worker"
        ),
        owner=control.ProcessIdentity(role="acquisition", generation="owner"),
        camera=camera_pb2.CAMERA_ROLE_TRACKING,
        work=control.WorkContext(session=control.SessionContext(session_id="session")),
    )
    work = control.WorkContext()
    work.CopyFrom(source.work)
    if trial:
        work.trial.CopyFrom(
            control.TrialContext(session=source.work.session, trial_id="trial")
        )
    warnings = WorkerWarningLedger(source)
    warnings.begin_scope(work, configuration_revision=3)
    state = SimpleNamespace(warnings=warnings)
    reports = []
    pending = []

    async def deliver(report, *, deadline_ns):
        reports.append(report)
        assert deadline_ns == 100
        return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)

    health = WorkerHealthReporter(
        SimpleNamespace(context=source),
        state,
        SimpleNamespace(report_warnings=deliver),
        None,
        pending.append,
        lambda: None,
    )
    health.warning_occurrence(WarningOccurrence("NATIVE_TIMESTAMP_UNAVAILABLE", 50))
    health.flush(100)
    await asyncio.gather(*pending)
    assert len(reports) == 1
    assert reports[0].source.work == reports[0].view.work == work
    assert reports[0].source.worker == source.worker
    assert reports[0].source.camera == source.camera
    assert source.work.WhichOneof("work") == "session"


def _scope(
    resource_id: str,
    closure: tuple[str, ...],
    owner: control.ProcessIdentity,
    reporter: control.ProcessIdentity,
    *,
    lifecycle_source: str | None = None,
) -> control.PreparedFunctionScope:
    scope = control.PreparedFunctionScope(
        resource_id=resource_id,
        owner=owner,
        affected_closure_resource_ids=closure,
        authorized_reporters=[reporter],
    )
    if lifecycle_source is not None:
        scope.lifecycle_sources.append(lifecycle_source)
    return scope


def _setup_payload(
    *, omit_recording_output_from_capture: bool = False
) -> tuple[acq.CameraWorkerSetupPayload, acq.WorkerContext]:
    worker = control.ProcessIdentity(
        role="acquisition_behavioral_worker", generation="worker-generation"
    )
    owner = control.ProcessIdentity(role="acquisition", generation="owner-generation")
    context = acq.WorkerContext(
        worker=worker,
        owner=owner,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
    )
    payload = acq.CameraWorkerSetupPayload()
    payload.recording.ffmpeg_executable = "ffmpeg"
    capture_closure = (
        ("behavioral.capture", "behavioral.recording", "behavioral_video")
        if not omit_recording_output_from_capture
        else ("behavioral.capture", "behavioral.recording")
    )
    payload.owned_functions.extend(
        (
            _scope(
                "behavioral.capture",
                capture_closure,
                owner,
                worker,
                lifecycle_source="behavioral",
            ),
            _scope(
                "behavioral.recording",
                ("behavioral.recording", "behavioral_video"),
                owner,
                worker,
            ),
            _scope("behavioral_video", ("behavioral_video",), owner, worker),
        )
    )
    return payload, context


def test_setup_catalogue_retains_exact_worker_output_fault_closure() -> None:
    payload, context = _setup_payload()

    scopes = validate_camera_function_scopes(payload, context)

    assert tuple(scope.resource_id for scope in scopes) == (
        "behavioral.capture",
        "behavioral.recording",
        "behavioral_video",
    )
    assert tuple(scopes[1].affected_closure_resource_ids) == (
        "behavioral.recording",
        "behavioral_video",
    )


def test_setup_catalogue_rejects_an_incomplete_transitive_recording_closure() -> None:
    payload, context = _setup_payload(omit_recording_output_from_capture=True)

    with pytest.raises(ValueError, match="incomplete closure"):
        validate_camera_function_scopes(payload, context)


def test_stop_pulse_and_cleanup_evidence_fit_safety_reserve_after_normal_saturation() -> (
    None
):
    worker = control.ProcessIdentity(
        role="acquisition_behavioral_worker", generation=str(uuid4())
    )
    owner = control.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    work = control.WorkContext(session=control.SessionContext(session_id=str(uuid4())))
    source = acq.WorkerContext(
        worker=worker,
        owner=owner,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
        work=work,
    )
    ledger = CommandLedger(
        worker.generation,
        60_000,
        max_records=20,
        max_bytes=4 * 1024 * 1024,
        result_reservation_bytes=64 * 1024,
        safety_reserve_records=16,
        safety_reserve_bytes=2 * 1024 * 1024,
    )

    def admit_and_complete(command_id: str, label: str, *, priority: bool) -> None:
        ledger.admit(
            command_id,
            label.encode("ascii"),
            1,
            work_key=work.session.session_id,
            result_reservation_bytes=64 * 1024,
            priority=priority,
        )
        operation = control.OperationState(
            context=control.OperationContext(command_id=command_id),
            command=label,
            complete=True,
            succeeded=True,
        )
        report = acq.WorkerOperationReport(source=source, operation=operation)
        ledger.complete(command_id, report.SerializeToString(deterministic=True), 2)

    for _ in range(4):
        admit_and_complete(str(uuid4()), "ordinary", priority=False)

    safety_commands = {
        label: str(uuid4())
        for label in ("StopTrial", "PulseOn", "PulseOff", "Cleanup", "Shutdown")
    }
    for label, command_id in safety_commands.items():
        admit_and_complete(command_id, label, priority=True)

    state = WorkerState(
        source,
        control.ProcessIdentity(role="supervisor", generation=str(uuid4())),
        ledger,
    )
    revision = 0
    for command_label, evidence_kind in (
        ("StopTrial", "stopped"),
        ("StopTrial", "finished"),
        ("Cleanup", "cleanup"),
        ("Shutdown", "cleanup"),
    ):
        revision += 1
        evidence = acq.WorkerLifecycleEvidence(
            source=source,
            state_revision=revision,
        )
        evidence.operation.command_id = safety_commands[command_label]
        if evidence_kind == "stopped":
            evidence.stopped.activity_stopped = True
            evidence.stopped.recording_interval_sealed = True
            evidence.stopped.actual_stop_monotonic_ns = 20
        elif evidence_kind == "finished":
            evidence.finished.activity_stopped = True
            evidence.finished.outputs.add(
                output_key="camera-output",
                path="C:/trial.mp4",
                closure=control.OUTPUT_CLOSURE_CLOSED,
                artifact_present=True,
            )
        else:
            evidence.cleanup.resources.add(
                resource="camera-device:generation", released=True
            )
        state.retain_lifecycle(evidence)

    assert len(state.lifecycle) == 4
    assert ledger.retained_bytes < ledger.max_bytes


def test_ordinary_coordinator_evidence_cannot_consume_reserved_cleanup_capacity() -> (
    None
):
    generation = str(uuid4())
    owner_generation = str(uuid4())
    session_id = str(uuid4())
    operation_id = str(uuid4())
    worker = control.ProcessIdentity(
        role="acquisition_behavioral_worker", generation=generation
    )
    owner = control.ProcessIdentity(role="acquisition", generation=owner_generation)
    work = control.WorkContext(session=control.SessionContext(session_id=session_id))
    source = acq.WorkerContext(
        worker=worker,
        owner=owner,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
        work=work,
    )
    ledger = CommandLedger(
        owner_generation,
        60_000,
        max_records=32,
        max_bytes=4 * 1024 * 1024,
        result_reservation_bytes=64 * 1024,
        safety_reserve_records=16,
        safety_reserve_bytes=2 * 1024 * 1024,
    )
    for _ in range(16):
        ledger.reserve_payload(
            f"ordinary:{uuid4()}", 64, work_key=session_id, priority=False
        )
    record = WorkerRecord(
        context=source,
        port=None,
        launch=LaunchRecord(
            command_id=str(uuid4()),
            worker=worker,
            owner=owner,
            work=work,
            camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
            parent_operation=control.OperationContext(command_id=str(uuid4())),
            planned_ns=1,
        ),
        commands=ledger,
    )
    ordinary = acq.WorkerLifecycleEvidence(
        source=source,
        operation=control.OperationContext(command_id=operation_id),
        state_revision=1,
    )
    ordinary.ready.required_checks_passed = True
    with pytest.raises(CommandCapacityError):
        record.preflight_lifecycle(ordinary, commands=ledger)

    safety = acq.WorkerLifecycleEvidence(
        source=source,
        operation=control.OperationContext(command_id=operation_id),
        state_revision=1,
    )
    safety.cleanup.resources.add(resource=f"camera-device:{generation}", released=True)
    record.preflight_lifecycle(safety, commands=ledger)


@pytest.mark.asyncio
@pytest.mark.parametrize("supervisor_cleanup", [False, True])
async def test_finalized_cleanup_allows_retained_shutdown_but_rejects_new_normal_work(
    supervisor_cleanup: bool,
) -> None:
    generation = str(uuid4())
    owner = control.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    supervisor = control.ProcessIdentity(role="supervisor", generation=str(uuid4()))
    session_id = str(uuid4())
    work = control.WorkContext(session=control.SessionContext(session_id=session_id))
    context = acq.WorkerContext(
        worker=control.ProcessIdentity(
            role="acquisition_behavioral_worker", generation=generation
        ),
        owner=owner,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
        work=work,
    )
    limits = AcquisitionControlLimits.from_message_limit(1024 * 1024)
    commands = CommandLedger(
        generation,
        60_000_000_000,
        max_records=limits.max_records,
        max_bytes=limits.max_bytes,
        result_reservation_bytes=limits.normal_result_reservation_bytes,
        safety_reserve_records=limits.safety_reserve_records,
        safety_reserve_bytes=limits.safety_reserve_bytes,
    )
    state = WorkerState(
        context,
        supervisor,
        commands,
        max_retained_views=limits.max_records,
        limits=limits,
        registered=True,
    )
    queue = _QueueOwner()
    service = _AdmissionService(state, queue, {})
    grpc_context = cast(grpc.aio.ServicerContext, object())

    initial = _command(context, owner)
    initial_admission = await service._admit(
        "ResolveCameraConfiguration", initial, initial, grpc_context
    )
    assert initial_admission.result == control.COMMAND_RESULT_ACCEPTED
    initial_ns = host_time_ns()
    state.complete_operation(
        initial.command_id,
        succeeded=True,
        progress="complete",
        now_ns=initial_ns,
    )
    retained_initial = commands.get(initial.command_id)
    assert retained_initial is not None and retained_initial.result is not None
    initial_report = acq.WorkerOperationReport.FromString(retained_initial.result)
    assert initial_report.source == context
    assert initial_report.operation == state.operations[initial.command_id]

    cleanup = _command(context, supervisor if supervisor_cleanup else owner)
    cleanup_admission = await service._admit("Cleanup", cleanup, cleanup, grpc_context)
    assert cleanup_admission.result == control.COMMAND_RESULT_ACCEPTED
    cleanup_ns = host_time_ns()
    assert (cleanup.command_id in state.supervisor_command_ids) == supervisor_cleanup
    deliveries: list[object] = []
    releases = []
    trial = object.__new__(WorkerTrialLifecycle)
    trial.trial_state = WorkerTrialState()
    trial.stop_finalizer = SimpleNamespace(stop_trial=lambda *args, **kwargs: None)
    executor = object.__new__(WorkerOperationExecutor)
    executor.state = state
    executor.bootstrap = SimpleNamespace(context=context)
    executor._coordinator_loss_handled = False
    executor._cancelled = Event()
    executor.trial = trial
    executor.report_dispatcher = SimpleNamespace(
        operation=lambda report, deadline: deliveries.append(report),
        lifecycle=lambda report, deadline: deliveries.append(report),
    )
    executor.cleanup = WorkerCleanupLifecycle(
        state,
        SimpleNamespace(release_device=lambda: releases.append("camera")),
        SimpleNamespace(release=lambda: releases.append("buffers") or ()),
        None,
        capacity=16,
        extra_resources=lambda: {},
        report_lifecycle=executor._report_lifecycle,
        report_operation=executor._report,
        shutdown=lambda deadline: None,
        recording_reconciled=lambda: None,
        external_wake=lambda: None,
    )
    executor.execute("Cleanup", cleanup, cleanup_ns + 1_000_000_000)
    assert state.operations[cleanup.command_id].succeeded
    assert releases == ["buffers", "camera"]
    assert len(deliveries) == (0 if supervisor_cleanup else 2)
    assert (cleanup.command_id, "cleanup") in state.lifecycle
    executor.captures = SimpleNamespace(capture=None, active=False)
    executor._session_ready = True
    executor._refresh_health_snapshot()
    assert state.health_work == work
    assert state.health_session_phase == control.SESSION_PHASE_ENDED
    saved_lifecycle = dict(state.lifecycle)
    state.lifecycle.clear()
    executor._refresh_health_snapshot()
    assert state.health_session_phase == control.SESSION_PHASE_ENDED
    state.lifecycle.update(saved_lifecycle)
    state.finalize_scope(work, cleanup_ns)
    assert state.finalize_terminal_command(cleanup.command_id, cleanup_ns)

    shutdown = _command(context, owner)
    admitted = await service._admit("Shutdown", shutdown, shutdown, grpc_context)
    assert admitted.result == control.COMMAND_RESULT_ACCEPTED

    shutdown_ns = host_time_ns()
    state.complete_operation(
        shutdown.command_id,
        succeeded=True,
        progress="complete",
        now_ns=shutdown_ns,
    )
    assert state.finalize_terminal_command(shutdown.command_id, shutdown_ns)
    retried = await service._admit("Shutdown", shutdown, shutdown, grpc_context)
    assert retried.result == control.COMMAND_RESULT_ACCEPTED
    assert len(queue.tickets) == 3
    retained_shutdown = commands.get(shutdown.command_id)
    assert retained_shutdown is not None
    assert terminal_target_matches(retained_shutdown, shutdown.command_id, context)
    other_work = acq.WorkerContext()
    other_work.CopyFrom(context)
    other_work.work.session.session_id = str(uuid4())
    assert not terminal_target_matches(
        retained_shutdown, shutdown.command_id, other_work
    )

    ordinary = _command(context, owner)
    rejected = await service._admit(
        "ResolveCameraConfiguration", ordinary, ordinary, grpc_context
    )
    assert rejected.result == control.COMMAND_RESULT_REJECTED
    assert len(queue.tickets) == 4
    assert queue.tickets[-1].cancelled


def _command(
    context: acq.WorkerContext, issuer: control.ProcessIdentity
) -> acq.WorkerCommand:
    return acq.WorkerCommand(
        command_id=str(uuid4()),
        issuer=issuer,
        target=context,
        parent_operation=control.OperationContext(command_id=str(uuid4())),
    )


async def test_repeated_connection_checks_leave_capacity_for_pfs_and_release() -> None:
    owner = control.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    context = acq.WorkerContext(
        worker=control.ProcessIdentity(
            role="acquisition_behavioral_worker", generation=str(uuid4())
        ),
        owner=owner,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
    )
    limits = AcquisitionControlLimits.from_message_limit(16 * 1024 * 1024)
    commands = CommandLedger(
        context.worker.generation,
        60_000_000_000,
        max_records=limits.max_records,
        max_bytes=limits.max_bytes,
        result_reservation_bytes=limits.normal_result_reservation_bytes,
        safety_reserve_records=limits.safety_reserve_records,
        safety_reserve_bytes=limits.safety_reserve_bytes,
    )
    state = WorkerState(
        context,
        control.ProcessIdentity(role="supervisor", generation=str(uuid4())),
        commands,
        max_retained_views=limits.max_records,
        limits=limits,
        registered=True,
    )
    service = _AdmissionService(state, _QueueOwner(), {})
    kinds = [acq.CAMERA_EDIT_KIND_TEST_CONNECTION] * 8 + [
        acq.CAMERA_EDIT_KIND_IMPORT_PFS,
        acq.CAMERA_EDIT_KIND_FINISH_EDITING,
    ]
    for kind in kinds:
        command = _command(context, owner)
        request = acq.WorkerEditCamera(command=command, kind=kind)
        receipt = await service._admit(
            "EditCamera", request, command, cast(grpc.aio.ServicerContext, object())
        )
        assert receipt.result == control.COMMAND_RESULT_ACCEPTED, (
            receipt.failure.message
        )
        retained = commands.get(command.command_id)
        assert retained is not None
        assert retained.result_reservation_bytes == (
            limits.large_result_reservation_bytes
            if kind == acq.CAMERA_EDIT_KIND_IMPORT_PFS
            else limits.normal_result_reservation_bytes
        )
        state.complete_operation(
            command.command_id,
            succeeded=True,
            progress="complete",
            now_ns=host_time_ns(),
        )


class _Ticket(WorkerOperationTicket):
    def __init__(self) -> None:
        self.committed = False
        self.cancelled = False

    def commit(self) -> None:
        self.committed = True

    def cancel(self) -> None:
        self.cancelled = True


class _QueueOwner:
    def __init__(self) -> None:
        self.tickets: list[_Ticket] = []

    def reserve(self, operation: str, request: object, deadline_ns: int) -> _Ticket:
        del operation, request, deadline_ns
        ticket = _Ticket()
        self.tickets.append(ticket)
        return ticket


class _AdmissionService(AcquisitionWorkerService):
    async def _authenticate(
        self, context: grpc.aio.ServicerContext, issuer: control.ProcessIdentity
    ) -> int:
        del context, issuer
        return host_time_ns() + 10_000_000_000


@pytest.mark.parametrize("outcome", ("accepted", "rejected", "exception"))
async def test_worker_report_failure_preserves_reason_and_drains(outcome):
    from cephvr.acquisition.worker.health import WorkerHealthReporter
    from cephvr.acquisition.worker.report_dispatch import WorkerReportDispatcher
    from cephvr.acquisition.worker.reports import CoordinatorReportClient

    source = acq.WorkerContext(
        worker=control.ProcessIdentity(
            role="acquisition_tracking_worker", generation=str(uuid4())
        )
    )
    state = cast(
        WorkerState, SimpleNamespace(lock=RLock(), interrupted=False, context=source)
    )
    failures = []

    async def deliver(report, *, deadline_ns):
        assert report.source == source and deadline_ns > host_time_ns()
        if outcome == "exception":
            raise RuntimeError("report transport failed")
        return control.ReportReceipt(
            result=control.COMMAND_RESULT_ACCEPTED
            if outcome == "accepted"
            else control.COMMAND_RESULT_REJECTED,
            failure=control.Failure(
                code="INVALID_EVIDENCE", message="wrong preparation" * 200
            ),
        )

    reports = cast(CoordinatorReportClient, SimpleNamespace(report_lifecycle=deliver))
    dispatcher = WorkerReportDispatcher(
        asyncio.get_running_loop(), state, reports, 1, failures.append
    )
    deadline = host_time_ns() + 1_000_000_000
    dispatcher.lifecycle(acq.WorkerLifecycleEvidence(source=source), deadline)
    assert await dispatcher.drain(deadline)
    assert not dispatcher._pending
    assert state.interrupted == (outcome != "accepted")
    if outcome == "accepted":
        assert not failures
        return
    assert len(failures) == 1
    assert failures[0].startswith(
        "worker report rejected: INVALID_EVIDENCE:"
        if outcome == "rejected"
        else "worker report failed: report transport failed"
    )

    errors = []

    async def report_error(request, *, deadline_ns):
        assert deadline_ns > host_time_ns()
        errors.append(request)
        return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)

    pending = []
    health = WorkerHealthReporter(
        SimpleNamespace(
            context=source,
            control_policies=control.ControlPolicies(recovery_ns=1_000_000_000),
        ),
        state,
        reports,
        SimpleNamespace(report_error=report_error),
        pending.append,
        lambda: None,
    )
    health.coordinator_lost(details=failures[0])
    await asyncio.gather(*pending)
    assert len(errors) == 1
    assert errors[0].source == source.worker
    assert errors[0].failure.code == "COORDINATOR_HEALTH_LOST"
    assert errors[0].failure.message == failures[0][:2048]
