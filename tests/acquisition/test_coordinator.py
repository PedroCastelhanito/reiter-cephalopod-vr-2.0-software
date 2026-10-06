"""Coordinator bootstrap identity, partial launch retention and health reports."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from cephvr.acquisition.coordinator.health import AcquisitionHealth
from cephvr.acquisition.coordinator.workers import WorkerRegistry
from cephvr.acquisition.ports import (
    SerialOwnerPort,
    SupervisorPort,
    WorkerBootstrapPort,
    WorkerLaunchResult,
    WorkerLaunchSpec,
)
from cephvr.acquisition.startup import decode_acquisition_bootstrap
from cephvr.acquisition.state import (
    CoordinatorIdentity,
    LaunchRecord,
    PulseRecord,
    SessionRecord,
    SessionSlot,
    TrialRecord,
    WorkerRecord,
)
from cephvr.acquisition.v1 import camera_pb2, microcontroller_pb2, runtime_pb2
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger


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
        pulse=PulseRecord(),
        supervisor=cast(SupervisorPort, supervisor),
        serial=cast(SerialOwnerPort, object()),
        heartbeat_interval_ns=10,
        health_silence_ns=100,
        recovery_ns=100,
        serial_keepalive_interval_ns=10,
        serial_communication_timeout_ns=20,
        serial_ack_timeout_ns=1,
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


@pytest.mark.asyncio
@pytest.mark.parametrize("running", [False, True, None])
async def test_connection_only_keepalive_requires_proven_stopped_outputs(
    monkeypatch: pytest.MonkeyPatch, running: bool | None
) -> None:
    shutdown = asyncio.Event()
    observation = microcontroller_pb2.MicrocontrollerObservation(
        connection_id=_id(), observed_monotonic_ns=1
    )
    observation.state.configuration_valid = False
    observation.state.watchdog_ms = 0
    if running is not None:
        observation.state.behavioral.running = running
        observation.state.tracking.running = False
    failures = []
    waits = []

    async def wait(_shutdown: asyncio.Event, delay: int) -> None:
        waits.append(delay)
        shutdown.set()

    async def fail(source, work, failure, deadline) -> None:
        failures.append(failure.code)
        shutdown.set()

    monkeypatch.setattr("cephvr.acquisition.coordinator.health._wait", wait)
    health = AcquisitionHealth(
        identity=CoordinatorIdentity(
            backend=control.BackendContext(
                backend_name="acquisition", backend_generation=_id()
            ),
            process=control.ProcessIdentity(role="acquisition", generation=_id()),
            controller=control.ProcessIdentity(role="controller", generation=_id()),
            supervisor=control.ProcessIdentity(role="supervisor", generation=_id()),
            tracking=control.ProcessIdentity(role="tracking", generation=_id()),
        ),
        workers={},
        commands=CommandLedger(
            _id(),
            300_000_000_000,
            max_records=32,
            max_bytes=2 * 1024 * 1024,
            result_reservation_bytes=64 * 1024,
        ),
        session_slot=SessionSlot(),
        pulse=PulseRecord(observation=observation),
        supervisor=cast(SupervisorPort, object()),
        serial=cast(SerialOwnerPort, object()),
        heartbeat_interval_ns=10,
        health_silence_ns=100,
        recovery_ns=100,
        serial_keepalive_interval_ns=10,
        serial_communication_timeout_ns=20,
        serial_ack_timeout_ns=1,
        catalogue_lock=asyncio.Lock(),
        failure_handler=fail,
        clock=lambda: 100,
    )

    await health._keepalive_loop(shutdown)

    assert failures == (
        [] if running is False else ["MICROCONTROLLER_KEEPALIVE_WINDOW_EXHAUSTED"]
    )
    assert bool(waits) is (running is False)


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
