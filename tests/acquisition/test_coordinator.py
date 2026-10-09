"""Coordinator bootstrap identity, partial launch retention and health reports."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from cephvr.acquisition.coordinator.evidence_telemetry import WorkerTelemetryReports
from cephvr.acquisition.coordinator.health import AcquisitionHealth
from cephvr.acquisition.coordinator.workers import (
    WorkerRegistry,
    _adopt_retained_operation,
)
from cephvr.acquisition.ports import (
    SupervisorPort,
    WorkerBootstrapPort,
    WorkerLaunchResult,
    WorkerLaunchSpec,
)
from cephvr.acquisition.startup import decode_acquisition_bootstrap
from cephvr.acquisition.state import (
    ChildOperation,
    CoordinatorIdentity,
    LaunchRecord,
    SessionRecord,
    SessionSlot,
    TrialRecord,
    WorkerRecord,
)
from cephvr.acquisition.v1 import camera_pb2, runtime_pb2
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["plain", "evidence", "expired", "trial_seen"])
async def test_camera_heartbeat_handoff_preserves_trial_evidence_fence(
    case: str,
) -> None:
    session_work = control.WorkContext(
        session=control.SessionContext(session_id="session")
    )
    trial_work = control.WorkContext(
        trial=control.TrialContext(session=session_work.session, trial_id="trial")
    )
    parent = control.OperationContext(command_id="trial-prepare")
    child = ChildOperation(
        command_id="worker-prepare",
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
        work=trial_work,
        parent_operation=parent,
        kind="prepare_trial",
        deadline_ns=100,
    )
    worker = control.ProcessIdentity(
        role="acquisition_behavioral_worker", generation="worker"
    )
    record = SimpleNamespace(
        launch=SimpleNamespace(worker=worker, work=session_work),
        trial=SimpleNamespace(
            preparation=control.OperationContext(command_id=child.command_id)
        ),
        child_operations={child.command_id: child},
        heartbeat=None,
    )
    session = SimpleNamespace(
        work=session_work,
        trial=SimpleNamespace(work=trial_work, preparation=parent),
        cleanup_complete=False,
        cleanup_command_id=None,
    )
    reports = cast(
        WorkerTelemetryReports,
        SimpleNamespace(
            workers={1: record}, current_session=lambda: session, lock=asyncio.Lock()
        ),
    )
    heartbeat = control.HeartbeatReport(
        source=worker,
        work=session_work,
        sent_monotonic_ns=50,
        session_phase=control.SESSION_PHASE_READY,
    )
    if case == "evidence":
        heartbeat.continuing_functions.add(
            resource_id="behavioral.capture", functioning=True
        )
    if case == "trial_seen":
        record.heartbeat = control.HeartbeatReport(
            source=worker, work=trial_work, sent_monotonic_ns=40
        )
    receipt = await WorkerTelemetryReports.report_heartbeat(
        reports, heartbeat, deadline_ns=200, ingress_ns=101 if case == "expired" else 50
    )
    assert receipt.result == (
        control.COMMAND_RESULT_ACCEPTED
        if case == "plain"
        else control.COMMAND_RESULT_REJECTED
    )
    if case == "plain":
        heartbeat.work.CopyFrom(trial_work)
        heartbeat.sent_monotonic_ns = 60
        assert (
            await WorkerTelemetryReports.report_heartbeat(
                reports, heartbeat, deadline_ns=200, ingress_ns=60
            )
        ).result == control.COMMAND_RESULT_ACCEPTED
        heartbeat.work.CopyFrom(session_work)
        heartbeat.sent_monotonic_ns = 70
        assert (
            await WorkerTelemetryReports.report_heartbeat(
                reports, heartbeat, deadline_ns=200, ingress_ns=70
            )
        ).result == control.COMMAND_RESULT_REJECTED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", ["pending", "complete", "expired", "wrong_parent", "active", "ready"]
)
async def test_camera_cleanup_heartbeat_requires_exact_quiet_terminal_scope(
    case: str,
) -> None:
    work = control.WorkContext(session=control.SessionContext(session_id="session"))
    trial = control.WorkContext(
        trial=control.TrialContext(session=work.session, trial_id="trial")
    )
    worker = control.ProcessIdentity(
        role="acquisition_behavioral_worker", generation="worker"
    )
    child = ChildOperation(
        command_id="child",
        camera=1,
        work=work,
        parent_operation=control.OperationContext(
            command_id="other" if case == "wrong_parent" else "cleanup"
        ),
        kind="cleanup",
        deadline_ns=100,
    )
    record = SimpleNamespace(
        launch=SimpleNamespace(worker=worker, work=work),
        trial=None,
        child_operations={"child": child},
        heartbeat=control.HeartbeatReport(
            source=worker, work=trial, sent_monotonic_ns=40
        ),
    )
    session = SimpleNamespace(
        work=work,
        trial=SimpleNamespace(work=trial),
        cleanup_complete=case == "complete",
        cleanup_command_id="cleanup",
    )
    reports = cast(
        WorkerTelemetryReports,
        SimpleNamespace(
            workers={1: record}, current_session=lambda: session, lock=asyncio.Lock()
        ),
    )
    heartbeat = control.HeartbeatReport(
        source=worker,
        work=work,
        sent_monotonic_ns=50,
        session_phase=control.SESSION_PHASE_READY
        if case == "ready"
        else control.SESSION_PHASE_ENDED,
    )
    if case == "active":
        heartbeat.continuing_functions.add(resource_id="capture", functioning=True)
    receipt = await WorkerTelemetryReports.report_heartbeat(
        reports,
        heartbeat,
        deadline_ns=300,
        ingress_ns=200 if case in ("complete", "expired") else 50,
    )
    assert receipt.result == (
        control.COMMAND_RESULT_ACCEPTED
        if case in ("complete", "pending")
        else control.COMMAND_RESULT_REJECTED
    )
    assert session.cleanup_complete == (case == "complete")


class _HeartbeatSupervisor:
    def __init__(self, shutdown: asyncio.Event) -> None:
        self.shutdown = shutdown
        self.reports: list[control.HeartbeatReport] = []

    async def report_heartbeat(
        self, request: control.HeartbeatReport, *, deadline_ns: int
    ) -> control.ReportReceipt:
        assert deadline_ns > request.sent_monotonic_ns
        saved = control.HeartbeatReport.FromString(request.SerializeToString())
        self.reports.append(saved)
        self.shutdown.set()
        return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)


@pytest.mark.asyncio
async def test_trial_heartbeat_sets_only_trial_lifecycle_oneof() -> None:
    shutdown = asyncio.Event()
    supervisor = _HeartbeatSupervisor(shutdown)
    controller = control.ProcessIdentity(role="controller", generation="c-1")
    supervisor_id = control.ProcessIdentity(role="supervisor", generation="s-1")
    backend = control.BackendContext(
        backend_name="acquisition", backend_generation="a-1"
    )
    identity = CoordinatorIdentity(
        backend=backend,
        process=control.ProcessIdentity(role="acquisition", generation="a-1"),
        controller=controller,
        supervisor=supervisor_id,
        tracking=control.ProcessIdentity(role="tracking", generation="t-1"),
    )
    session_work = control.WorkContext(
        session=control.SessionContext(session_id="session-1")
    )
    trial_work = control.WorkContext(
        trial=control.TrialContext(
            session=session_work.session,
            trial_id="trial-1",
            trial_number=1,
        )
    )
    session = SessionRecord(
        work=session_work,
        operation=control.OperationContext(command_id="setup-1"),
        configuration_revision=1,
        required_cameras=set(),
        trial=TrialRecord(
            work=trial_work,
            plan=control.TrialPlan(context=trial_work.trial),
            preparation=control.OperationContext(command_id="prepare-1"),
            configuration_revision=1,
        ),
    )
    health = AcquisitionHealth(
        identity=identity,
        workers={},
        commands=CommandLedger(
            str(uuid4()),
            300_000_000_000,
            max_records=32,
            max_bytes=2 * 1024 * 1024,
            result_reservation_bytes=64 * 1024,
        ),
        session_slot=SessionSlot(current=session),
        supervisor=cast(SupervisorPort, supervisor),
        heartbeat_interval_ns=10,
        health_silence_ns=100,
        recovery_ns=100,
        catalogue_lock=asyncio.Lock(),
        failure_handler=_unexpected_health_failure,
        clock=lambda: 1,
    )

    await health._heartbeat_loop(shutdown)

    assert len(supervisor.reports) == 1
    report = supervisor.reports[0]
    assert report.WhichOneof("lifecycle") == "trial_phase"
    assert report.work == trial_work


async def _unexpected_health_failure(
    _source: control.ProcessIdentity,
    _work: control.WorkContext,
    _failure: control.Failure,
    _deadline_ns: int,
) -> None:
    raise AssertionError("heartbeat success must not invoke the failure handler")


def _id() -> str:
    return str(uuid4())


def test_launch_intent_survives_endpoint_registration_timeout() -> None:
    async def run() -> None:
        owner = control.ProcessIdentity(role="acquisition", generation=_id())
        launches: dict[str, LaunchRecord] = {}
        workers: dict[int, WorkerRecord] = {}
        bootstrap = _FailingBootstrap()
        policies = runtime_pb2.AcquisitionFilePolicies()
        policies.cameras.add(camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL)
        registry = WorkerRegistry(
            workers=workers,
            launches=launches,
            commands=CommandLedger(
                owner.generation,
                300_000_000_000,
                max_records=64,
                max_bytes=4 * 1024 * 1024,
                result_reservation_bytes=64 * 1024,
            ),
            owner=owner,
            policies=control.ControlPolicies(),
            file_policies=policies,
            coordinator_endpoint="127.0.0.1:42000",
            heartbeat_interval_ns=100_000_000,
            health_silence_ns=1_000_000_000,
            bootstrap=bootstrap,
            executables=_ExecutableResolver(),
            supervisor=cast(SupervisorPort, object()),
            cleanup_complete=lambda _worker, _evidence: False,
        )
        with pytest.raises(TimeoutError):
            await registry.launch(
                camera_pb2.CAMERA_ROLE_BEHAVIORAL,
                None,
                control.OperationContext(command_id=_id()),
                deadline_ns=host_time_ns() + 1_000_000_000,
            )
        assert len(launches) == 1
        intent = next(iter(launches.values()))
        assert intent.failure is not None
        assert intent.process_confirmed is False
        assert intent.endpoint_confirmed is False
        assert workers[camera_pb2.CAMERA_ROLE_BEHAVIORAL].port is None

    asyncio.run(run())


@pytest.mark.asyncio
@pytest.mark.parametrize("session_scoped", [False, True])
@pytest.mark.parametrize("process_exits", [False, True])
async def test_camera_retirement_confirms_exact_cleanup_proof(
    session_scoped: bool, process_exits: bool
) -> None:
    owner = control.ProcessIdentity(role="acquisition", generation=_id())
    worker = control.ProcessIdentity(
        role="acquisition_behavioral_worker", generation=_id()
    )
    work = (
        control.WorkContext(session=control.SessionContext(session_id=_id()))
        if session_scoped
        else control.WorkContext()
    )
    context = acq.WorkerContext(
        worker=worker,
        owner=owner,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
    )
    if session_scoped:
        context.work.CopyFrom(work)
    launch = LaunchRecord(
        command_id=_id(),
        worker=worker,
        owner=owner,
        work=work,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
        parent_operation=control.OperationContext(command_id=_id()),
        planned_ns=1,
        pid=71,
        creation_time_100ns=171,
    )
    commands = CommandLedger(
        owner.generation,
        300_000_000_000,
        max_records=64,
        max_bytes=1024 * 1024,
        result_reservation_bytes=64 * 1024,
    )
    record = WorkerRecord(context=context, port=None, launch=launch, commands=commands)

    class Supervisor:
        def __init__(self) -> None:
            self.requests: list[wire.ConfirmLaunchRequest] = []
            self.deadlines: list[int] = []

        async def confirm_launch(self, request, *, deadline_ns):  # type: ignore[no-untyped-def]
            self.requests.append(request)
            self.deadlines.append(deadline_ns)
            phase = (
                wire.LAUNCH_PHASE_OPERATIONAL
                if len(self.requests) == 1
                else wire.LAUNCH_PHASE_RELEASED
            )
            return wire.LaunchReceipt(
                admission=control.CommandAdmission(
                    result=control.COMMAND_RESULT_ACCEPTED,
                    command_id=request.command_id,
                ),
                state=wire.LaunchState(phase=phase),
            )

    class Bootstrap:
        def __init__(self) -> None:
            self.deadlines: list[int] = []
            self.process_exits = process_exits

        async def wait_process_exit(self, _worker, *, deadline_ns):  # type: ignore[no-untyped-def]
            self.deadlines.append(deadline_ns)
            return self.process_exits

        async def retire(self, _worker, *, deadline_ns):  # type: ignore[no-untyped-def]
            del deadline_ns

    class WorkerPort:
        def __init__(self) -> None:
            self.context = context
            self.completion_task: asyncio.Task[None] | None = None

        async def cleanup(self, request, *, deadline_ns):  # type: ignore[no-untyped-def]
            del deadline_ns
            child = record.child_operations[request.command_id]
            state = control.OperationState(
                context=control.OperationContext(command_id=request.command_id),
                command="Cleanup",
                work=work,
                complete=True,
                succeeded=True,
            )
            evidence = acq.WorkerLifecycleEvidence(
                source=context,
                operation=control.OperationContext(command_id=request.command_id),
                state_revision=1,
            )
            evidence.cleanup.resources.add(resource="camera-device", released=True)
            record.retain_lifecycle(evidence, commands=commands)

            async def complete_operation() -> None:
                await asyncio.sleep(0.01)
                child.report = state
                child.report_ingress_ns = host_time_ns()
                child.report_revision = 1
                child.updated.set()

            self.completion_task = asyncio.create_task(complete_operation())
            return control.CommandAdmission(
                result=control.COMMAND_RESULT_ACCEPTED,
                command_id=request.command_id,
            )

        async def get_retained_result(self, _request, *, deadline_ns):  # type: ignore[no-untyped-def]
            del deadline_ns
            return acq.WorkerRetainedResult()

        async def shutdown(self, request, *, deadline_ns):  # type: ignore[no-untyped-def]
            del deadline_ns
            assert len(supervisor.requests) == 1
            return control.CommandAdmission(
                result=control.COMMAND_RESULT_ACCEPTED,
                command_id=request.command_id,
            )

        async def close(self) -> None:
            pass

    record.port = WorkerPort()
    supervisor = Supervisor()
    registry = WorkerRegistry.__new__(WorkerRegistry)
    registry.workers = {camera_pb2.CAMERA_ROLE_BEHAVIORAL: record}
    registry.launches = {launch.command_id: launch}
    registry.owner = owner
    registry.supervisor = supervisor
    bootstrap = Bootstrap()
    registry.bootstrap = bootstrap
    registry.commands = commands
    registry.cleanup_complete = lambda _record, _evidence: True
    registry.policies = control.ControlPolicies(
        command_retention_after_finalization_ns=300_000_000_000
    )
    registry.max_launch_records = 16
    registry._lock = asyncio.Lock()
    deadline = host_time_ns() + 1_000_000_000

    if session_scoped:
        child_id = _id()
        child = ChildOperation(
            command_id=child_id,
            camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
            work=work,
            parent_operation=launch.parent_operation,
            kind="cleanup",
        )
        child.report = control.OperationState(
            context=control.OperationContext(command_id=child_id),
            command="Cleanup",
            work=work,
            complete=True,
            succeeded=True,
        )
        evidence = acq.WorkerLifecycleEvidence(
            source=context,
            operation=control.OperationContext(command_id=child_id),
            state_revision=1,
        )
        evidence.cleanup.resources.add(resource="camera-device", released=True)
        record.child_operations[child_id] = child
        record.lifecycle_evidence[(work.session.session_id, child_id, "cleanup")] = (
            evidence
        )
        retire = registry.retire_completed_session(work, deadline_ns=deadline)
    else:
        retire = registry.retire_sessionless_worker(
            camera_pb2.CAMERA_ROLE_BEHAVIORAL, deadline_ns=deadline
        )

    if process_exits:
        confirmed = await retire
    else:
        with pytest.raises(RuntimeError, match="process/job release is unconfirmed"):
            await retire
        assert len(supervisor.requests) == 1
        assert supervisor.deadlines == [deadline]
        assert bootstrap.deadlines == [deadline]
        if record.port.completion_task is not None:
            await record.port.completion_task
        return

    assert confirmed is None
    assert len(supervisor.requests) == 2
    assert supervisor.requests[0].SerializeToString(
        deterministic=True
    ) == supervisor.requests[1].SerializeToString(deterministic=True)
    assert supervisor.deadlines == [deadline, deadline]
    assert bootstrap.deadlines == [deadline]
    proof = supervisor.requests[0].acquisition_worker_cleanup
    assert proof.cleanup.source == context
    assert proof.operation.source == context
    assert proof.cleanup.source.work == work
    if record.port.completion_task is not None:
        await record.port.completion_task


def test_retained_cleanup_query_cannot_replace_conflicting_local_terminal_report() -> (
    None
):
    owner = control.ProcessIdentity(role="acquisition", generation=_id())
    worker = control.ProcessIdentity(
        role="acquisition_behavioral_worker", generation=_id()
    )
    context = acq.WorkerContext(
        worker=worker,
        owner=owner,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
    )
    command_id = _id()
    child = ChildOperation(
        command_id=command_id,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
        work=control.WorkContext(),
        parent_operation=control.OperationContext(command_id=_id()),
        kind="cleanup",
        report=control.OperationState(
            context=control.OperationContext(command_id=command_id),
            command="Cleanup",
            complete=True,
            succeeded=False,
        ),
        report_revision=2,
    )
    record = WorkerRecord(
        context=context,
        port=None,
        launch=LaunchRecord(
            command_id=_id(),
            worker=worker,
            owner=owner,
            work=control.WorkContext(),
            camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
            parent_operation=control.OperationContext(command_id=_id()),
            planned_ns=1,
        ),
    )
    retained = acq.WorkerRetainedResult(
        found=True,
        source=context,
        admission=control.CommandAdmission(
            result=control.COMMAND_RESULT_ACCEPTED, command_id=command_id
        ),
        operation=acq.WorkerOperationReport(
            source=context,
            operation=control.OperationState(
                context=control.OperationContext(command_id=command_id),
                command="Cleanup",
                complete=True,
                succeeded=True,
            ),
            state_revision=3,
        ),
    )

    with pytest.raises(RuntimeError, match="differs from local terminal"):
        _adopt_retained_operation(record, child, command_id, retained)
    assert child.report is not None and not child.report.succeeded


class _FailingBootstrap(WorkerBootstrapPort):
    async def launch(
        self, spec: WorkerLaunchSpec, *, deadline_ns: int
    ) -> WorkerLaunchResult:
        del spec, deadline_ns
        raise TimeoutError("endpoint registration timed out")

    async def retire(
        self, worker: control.ProcessIdentity, *, deadline_ns: int
    ) -> None:
        del worker, deadline_ns

    async def wait_process_exit(
        self, worker: control.ProcessIdentity, *, deadline_ns: int
    ) -> bool:
        del worker, deadline_ns
        return False


class _ExecutableResolver:
    def resolve_worker(self, role: int) -> tuple[Path, bool, str]:
        del role
        return Path("/python.exe"), True, "grpc_shutdown"


def _document() -> dict[str, object]:
    policies = control.ControlPolicies(
        setup=control.WaitPolicy(initial_ns=1),
        setup_cancel=control.WaitPolicy(initial_ns=1),
        trial_ready=control.WaitPolicy(initial_ns=1),
        trial_finished=control.WaitPolicy(initial_ns=1),
        supervisor_registration=control.WaitPolicy(initial_ns=1),
        start_lead_ns=1,
        controller_release_offset_ns=1,
        backend_release_offset_ns=1,
        start_evidence_allowance_ns=1,
        stop_evidence_allowance_ns=1,
        metadata_timeout_ns=1,
        command_retention_after_finalization_ns=1,
        recovery_ns=1,
        trial_command_transport_retries=1,
    )
    return {
        "role": "acquisition",
        "generation": _id(),
        "controller_generation": _id(),
        "supervisor_generation": _id(),
        "tracking_generation": _id(),
        "launch_command_id": _id(),
        "pid": 1,
        "creation_time_100ns": 1,
        "controller_pid": 2,
        "controller_creation_time_100ns": 2,
        "supervisor_pid": 3,
        "supervisor_creation_time_100ns": 3,
        "endpoint_port": 20_001,
        "controller_port": 20_002,
        "supervisor_port": 20_003,
        "max_message_bytes": 1_000_000,
        "heartbeat_interval_ns": 5_000_000_000,
        "health_silence_ns": 15_000_000_000,
        "software_root": ".",
        "token": "worker-token",
        "controller_token": "controller-token",
        "supervisor_token": "supervisor-token",
        "control_policies": base64.b64encode(
            policies.SerializeToString(deterministic=True)
        ).decode("ascii"),
    }


def test_acquisition_bootstrap_retains_exact_startup_policy_and_identities() -> None:
    decoded = decode_acquisition_bootstrap(_document())
    assert decoded.identity.role == "acquisition"
    assert decoded.controller.role == "controller"
    assert decoded.tracking.role == "tracking"
    assert decoded.policies.setup.initial_ns == 1
    assert decoded.max_message_bytes == 1_000_000


@pytest.mark.parametrize(
    "name",
    [
        "setup",
        "setup_cancel",
        "trial_ready",
        "trial_finished",
        "supervisor_registration",
    ],
)
@pytest.mark.parametrize("value", [0, -1])
def test_bootstrap_rejects_missing_or_nonpositive_wait(name: str, value: int) -> None:
    document = _document()
    policies = control.ControlPolicies.FromString(
        base64.b64decode(str(document["control_policies"]))
    )
    getattr(policies, name).initial_ns = value
    document["control_policies"] = base64.b64encode(
        policies.SerializeToString()
    ).decode()
    with pytest.raises(ValueError, match=name + r"\.initial_ns"):
        decode_acquisition_bootstrap(document)


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("control_policies", "not-base64"),
        ("max_message_bytes", 0),
        ("endpoint_port", 65_536),
    ),
)
def test_acquisition_bootstrap_rejects_invalid_protected_values(
    key: str, value: object
) -> None:
    document = _document()
    document[key] = value
    with pytest.raises(ValueError):
        decode_acquisition_bootstrap(document)


async def _retained_operation_test_owner(*, late_started: bool = False):
    from cephvr.acquisition.coordinator.configuration_resolution import (
        ConfigurationResolution,
    )
    from cephvr.acquisition.coordinator.evidence import WorkerEvidenceCoordinator
    from cephvr.acquisition.coordinator.manual_device_recovery import (
        ManualDeviceRecovery,
    )
    from cephvr.acquisition.state import (
        ConfigurationRecord,
        CoordinatorIdentity,
        PulseRecord,
    )
    from cephvr.platform.windows.resource_ledger import NativeResourceLedger

    backend = control.BackendContext(
        backend_name="acquisition", backend_generation=_id()
    )
    owner = control.ProcessIdentity(
        role="acquisition", generation=backend.backend_generation
    )
    controller_identity = control.ProcessIdentity(role="controller", generation=_id())
    identity = CoordinatorIdentity(
        backend=backend,
        process=owner,
        controller=controller_identity,
        supervisor=control.ProcessIdentity(role="supervisor", generation=_id()),
        tracking=control.ProcessIdentity(role="tracking", generation=_id()),
    )
    settings = control.AcquisitionSettings()
    configuration = ConfigurationRecord(
        settings=settings,
        file_policies=runtime_pb2.AcquisitionFilePolicies(),
        revision=1,
    )
    lock = asyncio.Lock()
    controller = SimpleNamespace(resolutions=[], lifecycles=[])

    async def report_resolution(report, *, deadline_ns):
        controller.resolutions.append((report, deadline_ns))
        return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)

    async def report_lifecycle(report, *, deadline_ns):
        controller.lifecycles.append((report, deadline_ns))
        return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)

    controller.report_acquisition_resolution = report_resolution
    controller.report_lifecycle = report_lifecycle
    resolution = ConfigurationResolution(
        identity=identity,
        configuration=configuration,
        controller=controller,
        lock=lock,
        clock=lambda: 50,
    )
    parent_id = _id()
    operation = await resolution.begin(
        wire.BackendCommand(
            command_id=parent_id,
            issuer=controller_identity,
            target=backend,
            parent_operation=control.OperationContext(command_id=parent_id),
        ),
        expected_cameras={camera_pb2.CAMERA_ROLE_BEHAVIORAL},
        request_revision=1,
        deadline_ns=100,
    )
    child_id = _id()
    work = control.WorkContext()
    context = acq.WorkerContext(
        worker=control.ProcessIdentity(
            role="acquisition_behavioral_worker", generation=_id()
        ),
        owner=owner,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
        work=work,
    )
    child = ChildOperation(
        command_id=child_id,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
        work=work,
        parent_operation=operation,
        kind="start_preview" if late_started else "apply_camera",
        configuration_revision=1,
        requested_device_id=None if late_started else "CAM-1",
        deadline_ns=100,
    )
    worker_record = WorkerRecord(
        context=context,
        port=None,
        launch=LaunchRecord(
            command_id=_id(),
            worker=context.worker,
            owner=owner,
            work=work,
            camera=context.camera,
            parent_operation=operation,
            planned_ns=1,
        ),
        child_operations={child_id: child},
    )
    if late_started:
        from cephvr.acquisition.coordinator.state import WorkerPreview

        worker_record.preview = WorkerPreview(
            run_id=_id(),
            configuration_revision=1,
            start_operation=control.OperationContext(command_id=child_id),
        )
    workers = {context.camera: worker_record}
    ledger = CommandLedger(
        backend.backend_generation,
        10_000,
        max_records=16,
        max_bytes=1_000_000,
        result_reservation_bytes=4096,
    )
    evidence = WorkerEvidenceCoordinator(
        backend=backend,
        owner=owner,
        settings=settings,
        workers=workers,
        resources={},
        resource_ledger=NativeResourceLedger(
            max_resources=8, max_transfers_per_resource=4
        ),
        commands=ledger,
        current_session=lambda: None,
        controller=controller,
        lock=lock,
        configuration_resolution=resolution,
    )
    recovery = ManualDeviceRecovery(
        workers=SimpleNamespace(workers=workers),
        resolution=resolution,
        pulse=PulseRecord(),
        serial=SimpleNamespace(),
        clock=lambda: 500,
    )
    resolution._pending.device_work_quiescent = lambda: recovery.device_work_quiescent(
        parent_command_id=operation.command_id
    )
    await resolution.cancel(operation)
    return SimpleNamespace(
        backend=backend,
        child=child,
        child_id=child_id,
        context=context,
        controller=controller,
        evidence=evidence,
        identity=identity,
        operation=operation,
        recovery=recovery,
        record=worker_record,
        resolution=resolution,
        settings=settings,
        workers=workers,
        late_started=late_started,
    )


def _retained_operation_report(owner, *, late_started: bool = False):
    if late_started:
        operation = control.OperationState(
            context=control.OperationContext(command_id=owner.child_id),
            command="StartPreview",
            work=owner.child.work,
            complete=True,
            succeeded=False,
            failure=control.Failure(code="START_FAILED", message="late start"),
        )
        resolved = None
    else:
        operation = control.OperationState(
            context=control.OperationContext(command_id=owner.child_id),
            command="ApplyCameraSettings",
            work=owner.child.work,
            complete=True,
            succeeded=True,
        )
        resolved = camera_pb2.CameraResolvedState(configuration_revision=1)
        resolved.device.configured_id = "CAM-1"
        resolved.applied.device_id = "CAM-1"
    report = acq.WorkerOperationReport(
        source=owner.context,
        operation=operation,
        state_revision=1,
    )
    if resolved is not None:
        report.resolved_camera.CopyFrom(resolved)
    retained = acq.WorkerRetainedResult(
        found=True,
        source=owner.context,
        admission=control.CommandAdmission(
            result=control.COMMAND_RESULT_ACCEPTED,
            command_id=owner.child_id,
        ),
        operation=report,
    )
    if late_started:
        retained.lifecycle.add(
            source=owner.context,
            operation=control.OperationContext(command_id=owner.child_id),
            state_revision=1,
            started=acq.WorkerStartedEvidence(actual_start_monotonic_ns=90),
        )
    return retained


@pytest.mark.asyncio
async def test_retained_late_apply_query_retains_terminal_without_readback_adoption() -> (
    None
):
    owner = await _retained_operation_test_owner()

    class Port:
        async def get_retained_result(self, request, *, deadline_ns):
            assert request.query.target == owner.context
            assert request.command_id == owner.child_id
            assert deadline_ns == 900
            return _retained_operation_report(owner)

    owner.record.port = Port()
    owner.recovery.bind_retained_operation_reconciler(
        lambda record, child, retained, deadline, ingress: (
            owner.evidence.reconcile_retained_operation(
                record,
                child,
                retained,
                deadline_ns=deadline,
                ingress_ns=ingress,
            )
        )
    )
    await owner.recovery.recover_failed_device_work(900)

    assert owner.child.report is not None and owner.child.report.complete
    assert owner.child.report.succeeded
    assert owner.child.report_ingress_ns == 500 > owner.child.deadline_ns
    assert owner.child.resolved_camera is not None
    assert owner.settings == control.AcquisitionSettings()
    assert owner.resolution.configuration.revision == 1
    assert owner.controller.resolutions == []
    assert owner.controller.lifecycles == []
    assert owner.resolution._pending is None
    fresh = await owner.resolution.begin(
        wire.BackendCommand(
            command_id=_id(),
            issuer=owner.identity.controller,
            target=owner.backend,
            parent_operation=control.OperationContext(command_id=_id()),
        ),
        expected_cameras=set(),
        request_revision=1,
        deadline_ns=900,
        allow_empty=True,
        accepted_base_revision=1,
        accepted_base_settings=owner.settings,
        preexisting_work_quiescent=owner.recovery.prior_device_work_quiescent,
    )
    assert fresh.command_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mismatch", ["source", "child", "kind", "work", "revision", "conflict", "lifecycle"]
)
async def test_retained_query_rejects_mismatched_terminal_without_local_adoption(
    mismatch: str,
) -> None:
    owner = await _retained_operation_test_owner()
    retained = _retained_operation_report(owner)
    if mismatch == "source":
        retained.operation.source.worker.generation = _id()
    elif mismatch == "child":
        retained.operation.operation.context.command_id = _id()
    elif mismatch == "kind":
        retained.operation.operation.command = "StopPreview"
    elif mismatch == "work":
        retained.operation.operation.work.session.session_id = _id()
    elif mismatch == "revision":
        owner.child.report_revision = 2
    elif mismatch == "conflict":
        owner.child.report_revision = 1
        owner.child.report = control.OperationState(
            context=control.OperationContext(command_id=owner.child_id),
            command="ApplyCameraSettings",
            complete=True,
            succeeded=False,
        )
    else:
        retained.lifecycle.add(
            source=owner.context,
            operation=control.OperationContext(command_id=_id()),
            state_revision=1,
            stopped=acq.WorkerStoppedEvidence(),
        )

    accepted = await owner.evidence.reconcile_retained_operation(
        owner.record,
        owner.child,
        retained,
        deadline_ns=900,
        ingress_ns=500,
    )
    assert not accepted
    if mismatch != "conflict":
        assert owner.child.report is None
    assert owner.resolution.configuration.revision == 1
    assert owner.controller.resolutions == []


@pytest.mark.asyncio
async def test_retained_late_started_evidence_does_not_mark_preview_quiet() -> None:
    owner = await _retained_operation_test_owner(late_started=True)
    retained = _retained_operation_report(owner, late_started=True)
    accepted = await owner.evidence.reconcile_retained_operation(
        owner.record,
        owner.child,
        retained,
        deadline_ns=900,
        ingress_ns=500,
    )

    assert accepted
    assert owner.child.report is not None and owner.child.report.complete
    assert owner.record.preview is not None
    assert not owner.record.preview.started
    assert not owner.record.preview.started_event.is_set()
    assert owner.resolution._pending is not None
    assert owner.controller.resolutions == []


@pytest.mark.asyncio
async def test_retained_late_ready_is_skipped_but_prepare_terminal_is_retained() -> (
    None
):
    owner = await _retained_operation_test_owner(late_started=True)
    owner.child.kind = "prepare_preview"
    preview = owner.record.preview
    assert preview is not None
    preview.preparation = preview.start_operation
    preview.start_operation = None
    retained = _retained_operation_report(owner, late_started=True)
    retained.operation.operation.command = "PreparePreview"
    retained.ClearField("lifecycle")
    retained.lifecycle.add(
        source=owner.context,
        operation=retained.operation.operation.context,
        state_revision=1,
        ready=acq.WorkerReadyEvidence(
            configuration_revision=1, required_checks_passed=True
        ),
    )

    accepted = await owner.evidence.reconcile_retained_operation(
        owner.record,
        owner.child,
        retained,
        deadline_ns=900,
        ingress_ns=500,
    )

    assert accepted
    assert owner.child.report is not None and owner.child.report.complete
    assert not preview.started and not preview.started_event.is_set()
    assert owner.record.setup_ready is None
    assert owner.resolution._pending is not None
    assert owner.controller.lifecycles == []

    retained.ClearField("lifecycle")
    repeated = await owner.evidence.reconcile_retained_operation(
        owner.record,
        owner.child,
        retained,
        deadline_ns=900,
        ingress_ns=500,
    )
    assert repeated
    assert owner.child.report is not None
    assert owner.resolution._pending is not None
