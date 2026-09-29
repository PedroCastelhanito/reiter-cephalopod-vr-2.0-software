from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.clock import describe_host_clock, host_time_ns
from cephvr.shared.incidents import IncidentEvidenceError, IncidentTopology
from cephvr.shared.recovery import ApplicationExitReceipt, RecoveryStore
from cephvr.supervisor.runtime import SupervisorRuntime


class Native:
    def __init__(self) -> None:
        self.jobs: dict[str, list[tuple[int, int, str]]] = {}

    def create_launch_job(self, name: str) -> None:
        self.jobs[name] = []

    def inspect_launch_job(self, name: str) -> list[tuple[int, int, str]]:
        return list(self.jobs[name])

    def process_running(self, pid: int, creation_time_100ns: int) -> bool:
        return any(
            (pid, creation_time_100ns) == member[:2]
            for members in self.jobs.values()
            for member in members
        )

    def terminate_exact(self, pid: int, creation_time_100ns: int) -> None:
        for members in self.jobs.values():
            members[:] = [
                member for member in members if member[:2] != (pid, creation_time_100ns)
            ]

    def close_launch_job(self, name: str) -> None:
        del self.jobs[name]

    def release_process(self, pid: int, creation_time_100ns: int) -> None:
        pass

    def retain_exact(
        self, pid: int, creation_time_100ns: int, executable: str
    ) -> object:
        return object()


class Outbound:
    def __init__(self) -> None:
        self.interruptions: list[wire.InterruptionReport] = []
        self.statuses: list[wire.SupervisorStatusReport] = []
        self.heartbeats: list[types.HeartbeatReport] = []
        self.fail_status_once = False

    async def report_interruption(self, report: wire.InterruptionReport) -> None:
        self.interruptions.append(report)

    async def report_status(self, report: wire.SupervisorStatusReport) -> None:
        if self.fail_status_once:
            self.fail_status_once = False
            self.statuses.append(
                wire.SupervisorStatusReport.FromString(report.SerializeToString())
            )
            raise ConnectionError("controller temporarily unavailable")
        self.statuses.append(report)

    async def interrupt_backend(
        self, target: types.BackendContext, request: wire.InterruptSessionRequest
    ) -> None:
        pass

    async def shutdown_backend(
        self, target: types.BackendContext, request: wire.BackendCommand
    ) -> None:
        pass

    async def cleanup_backend(
        self, target: types.BackendContext, request: wire.BackendCommand
    ) -> None:
        pass

    async def notify_launcher_shutdown(self, deadline_ns: int, cause: str) -> None:
        pass

    async def report_heartbeat(self, report: types.HeartbeatReport) -> None:
        self.heartbeats.append(
            types.HeartbeatReport.FromString(report.SerializeToString())
        )


class Context:
    def __init__(self, role: str, generation: str, token: str) -> None:
        self.metadata = (
            ("x-cephvr-role", role),
            ("x-cephvr-generation", generation),
            ("x-cephvr-token", token),
        )

    def peer(self) -> str:
        return "ipv4:127.0.0.1:51000"

    def invocation_metadata(self) -> tuple[tuple[str, str], ...]:
        return self.metadata

    async def abort(self, code: object, details: str) -> None:
        raise PermissionError(details)


def make_runtime(tmp_path: Path) -> tuple[SupervisorRuntime, Native, Outbound, Context]:
    supervisor = types.ProcessIdentity(role="supervisor", generation=str(uuid4()))
    controller = types.ProcessIdentity(role="controller", generation=str(uuid4()))
    native, outbound = Native(), Outbound()
    runtime = SupervisorRuntime(
        identity=supervisor,
        controller=controller,
        credentials={(controller.role, controller.generation): "controller-secret"},
        native=native,
        outbound=outbound,
        software_root=tmp_path,
    )
    return (
        runtime,
        native,
        outbound,
        Context("controller", controller.generation, "controller-secret"),
    )


@pytest.mark.asyncio
async def test_pre_session_error_without_isolation_proof_fences_safety(
    tmp_path: Path,
) -> None:
    runtime, _, outbound, caller = make_runtime(tmp_path)
    report = types.ErrorReport(
        error_id=str(uuid4()),
        source=runtime.controller,
        occurred_monotonic_ns=host_time_ns(),
        failure=types.Failure(code="PREPARE_FAILED", message="preparation failed"),
    )
    receipt = await runtime.ReportError(report, caller)
    assert receipt.result == types.COMMAND_RESULT_ACCEPTED
    assert runtime._interruption is not None
    assert runtime._safety_task is not None
    await runtime._safety_task
    assert len(outbound.interruptions) == 1
    report_path = next((tmp_path / "reports").glob("emergency-*.json"))
    assert json.loads(report_path.read_text())["spikeglx_stop_unconfirmed"] is False


@pytest.mark.asyncio
async def test_prior_application_exit_requires_exact_private_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, _, _, caller = make_runtime(tmp_path)
    runtime_root = tmp_path / "runtime"
    monkeypatch.setattr(
        "cephvr.supervisor.runtime.default_runtime_root", lambda: runtime_root
    )
    previous_controller = str(uuid4())
    previous_supervisor = str(uuid4())
    query = wire.RecoveryQuery(
        expected_supervisor=runtime.identity,
        prior_controller_generation=previous_controller,
    )
    missing = await runtime.GetRecoveryState(query, caller)
    assert not missing.HasField("prior_application_exit")
    RecoveryStore(runtime_root).write_exit_receipt(
        ApplicationExitReceipt(
            controller_generation=previous_controller,
            supervisor_generation=previous_supervisor,
            observed_monotonic_ns=host_time_ns(),
            all_owned_processes_absent=True,
        )
    )
    verified = await runtime.GetRecoveryState(query, caller)
    assert verified.prior_application_exit.controller_generation == previous_controller
    assert verified.prior_application_exit.supervisor_generation == previous_supervisor
    assert verified.prior_application_exit.all_owned_processes_absent
    assert verified.prior_application_exit.format_version == 1
    other = wire.RecoveryQuery(
        expected_supervisor=runtime.identity,
        prior_controller_generation=str(uuid4()),
    )
    assert not (await runtime.GetRecoveryState(other, caller)).HasField(
        "prior_application_exit"
    )


@pytest.mark.asyncio
async def test_unclassified_error_fences_safety(tmp_path: Path) -> None:
    runtime, _, outbound, caller = make_runtime(tmp_path)
    work = types.WorkContext(
        session=types.SessionContext(
            controller_generation=runtime.controller.generation,
            session_id=str(uuid4()),
        )
    )
    runtime.context = wire.RegisteredContext(
        controller=runtime.controller,
        supervisor=runtime.identity,
        work=work,
        paired_spikeglx=True,
        policies=types.ControlPolicies(recovery_ns=1_000_000),
    )
    report = types.ErrorReport(
        error_id=str(uuid4()),
        source=runtime.controller,
        work=work,
        occurred_monotonic_ns=host_time_ns(),
        failure=types.Failure(code="UNRECOGNIZED", message="unknown control failure"),
    )
    receipt = await runtime.ReportError(report, caller)
    assert receipt.result == types.COMMAND_RESULT_ACCEPTED
    assert runtime._interruption is None
    monitor = asyncio.create_task(runtime.monitor(period_s=0.001))
    await asyncio.sleep(0.03)
    monitor.cancel()
    assert runtime._interruption is not None
    await runtime._safety_task
    assert len(outbound.interruptions) == 1
    assert (tmp_path / "reports").is_dir()
    report_path = next((tmp_path / "reports").glob("emergency-*.json"))
    assert json.loads(report_path.read_text())["spikeglx_stop_unconfirmed"] is True


@pytest.mark.asyncio
async def test_new_session_requires_verified_prior_cleanup(tmp_path: Path) -> None:
    runtime, native, outbound, controller_context = make_runtime(tmp_path)
    vr = types.ProcessIdentity(role="vr", generation=str(uuid4()))
    runtime.credentials[(vr.role, vr.generation)] = "vr-secret"
    planned = wire.PlanLaunchRequest(
        command_id=str(uuid4()),
        owner=runtime.identity,
        child=vr,
        executable="C:\\Python311\\python.exe",
        python_worker=True,
        stop_method="grpc_shutdown",
    )
    state = runtime.registry.plan(planned)
    native.jobs[state.containment_job_name] = [(25, 100, planned.executable)]
    os_stage = wire.ConfirmLaunchRequest(
        command_id=str(uuid4()),
        launch_command_id=planned.command_id,
        owner=planned.owner,
        child=vr,
        pid=25,
        creation_time_100ns=100,
    )
    runtime.registry.confirm(os_stage, runtime.clock)
    endpoint = wire.ConfirmLaunchRequest.FromString(os_stage.SerializeToString())
    endpoint.command_id = str(uuid4())
    endpoint.endpoint = "127.0.0.1:50054"
    descriptor = describe_host_clock()
    endpoint.host_clock.clock_id = descriptor.clock_id
    endpoint.host_clock.implementation = descriptor.implementation
    endpoint.host_clock.monotonic = descriptor.monotonic
    endpoint.host_clock.adjustable = descriptor.adjustable
    endpoint.host_clock.resolution_s = descriptor.resolution_s
    runtime.registry.confirm(endpoint, runtime.clock)

    def registration(session_id: str) -> wire.RegisterContextRequest:
        return wire.RegisterContextRequest(
            command_id=str(uuid4()),
            context=wire.RegisteredContext(
                controller=runtime.controller,
                supervisor=runtime.identity,
                paired_spikeglx=False,
                work=types.WorkContext(
                    session=types.SessionContext(
                        controller_generation=runtime.controller.generation,
                        session_id=session_id,
                    )
                ),
                required_participants=[
                    types.BackendContext(
                        backend_name="vr",
                        backend_generation=vr.generation,
                    )
                ],
                prepared_functions=[
                    types.PreparedFunctionScope(
                        resource_id="vr.control",
                        owner=vr,
                        affected_closure_resource_ids=["vr.control"],
                        essential_to_stimulus_control=True,
                        feedback_hold_required_on_loss=False,
                        bounded_uncertainty_supported=False,
                        lifecycle_sources=["renderer"],
                    )
                ],
                cleanup_resources=[
                    types.ResourceObligation(owner=vr, resource="vr.control")
                ],
            ),
        )

    first = registration(str(uuid4()))
    preliminary = wire.RegisterContextRequest.FromString(first.SerializeToString())
    preliminary.command_id = str(uuid4())
    preliminary.context.ClearField("prepared_functions")
    preliminary.context.ClearField("cleanup_resources")
    assert (
        await runtime.RegisterContext(preliminary, controller_context)
    ).admission.result == types.COMMAND_RESULT_ACCEPTED
    vr_context = Context("vr", vr.generation, "vr-secret")
    empty_catalogue = types.HeartbeatReport(
        source=vr,
        work=first.context.work,
        sent_monotonic_ns=host_time_ns(),
        session_phase=types.SESSION_PHASE_SETTING_UP,
        cleanup_resources_revision=0,
    )
    assert (
        await runtime.ReportHeartbeat(empty_catalogue, vr_context)
    ).result == types.COMMAND_RESULT_ACCEPTED
    resource_catalogue = types.HeartbeatReport.FromString(
        empty_catalogue.SerializeToString()
    )
    resource_catalogue.cleanup_resources_revision = 1
    resource_catalogue.cleanup_resources.add(owner=vr, resource="vr.control")
    assert (
        await runtime.ReportHeartbeat(resource_catalogue, vr_context)
    ).result == types.COMMAND_RESULT_ACCEPTED
    if runtime._status_task is not None:
        await runtime._status_task
    process = next(
        process for process in outbound.statuses[-1].processes if process.process == vr
    )
    assert process.launch_owner == runtime.identity
    assert process.last_heartbeat == resource_catalogue
    accepted = await runtime.RegisterContext(first, controller_context)
    assert accepted.admission.result == types.COMMAND_RESULT_ACCEPTED
    assert await runtime.RegisterContext(first, controller_context) == accepted
    second = registration(str(uuid4()))
    second.context.ClearField("prepared_functions")
    second.context.ClearField("cleanup_resources")
    blocked = await runtime.RegisterContext(second, controller_context)
    assert blocked.admission.result == types.COMMAND_RESULT_REJECTED

    cleanup_command_id = str(uuid4())
    fenced = wire.RegisterContextRequest.FromString(first.SerializeToString())
    fenced.command_id = str(uuid4())
    fenced.context.cleanup_commands.add(
        target=vr,
        work=first.context.work,
        operation=types.OperationContext(command_id=cleanup_command_id),
    )
    assert (
        await runtime.RegisterContext(fenced, controller_context)
    ).admission.result == types.COMMAND_RESULT_ACCEPTED

    cleanup = types.LifecycleReport(
        cleanup=types.CleanupReport(
            source=vr,
            work=first.context.work,
            operation=types.OperationContext(command_id=cleanup_command_id),
            verified_monotonic_ns=host_time_ns(),
            trial_activity_stopped=True,
            cleanup_resources_revision=1,
            resources=[types.ResourceRelease(resource="vr.control", released=True)],
        )
    )
    receipt = await runtime.ReportLifecycle(
        cleanup, Context("vr", vr.generation, "vr-secret")
    )
    assert receipt.result == types.COMMAND_RESULT_ACCEPTED
    assert (
        await runtime.RegisterContext(second, controller_context)
    ).admission.result == types.COMMAND_RESULT_ACCEPTED


@pytest.mark.asyncio
async def test_worker_incident_ancestry_uses_exact_launch_owner_chain(
    tmp_path: Path,
) -> None:
    runtime, native, _, controller_context = make_runtime(tmp_path)
    vr = types.ProcessIdentity(role="vr", generation=str(uuid4()))
    renderer_worker = types.ProcessIdentity(
        role="renderer-worker", generation=str(uuid4())
    )
    nested_worker = types.ProcessIdentity(
        role="nested-renderer-worker", generation=str(uuid4())
    )
    gui = types.ProcessIdentity(role="gui", generation=str(uuid4()))
    foreign_worker = types.ProcessIdentity(
        role="renderer-worker", generation=str(uuid4())
    )

    def launch(
        owner: types.ProcessIdentity,
        child: types.ProcessIdentity,
        pid: int,
        *,
        python_worker: bool = False,
    ) -> None:
        plan = wire.PlanLaunchRequest(
            command_id=str(uuid4()),
            owner=owner,
            child=child,
            executable="C:\\Python311\\python.exe",
            python_worker=python_worker,
            stop_method="grpc_shutdown",
        )
        state = runtime.registry.plan(plan)
        native.jobs[state.containment_job_name] = [(pid, 100 + pid, plan.executable)]
        confirmed = wire.ConfirmLaunchRequest(
            command_id=str(uuid4()),
            launch_command_id=plan.command_id,
            owner=owner,
            child=child,
            pid=pid,
            creation_time_100ns=100 + pid,
        )
        runtime.registry.confirm(confirmed, runtime.clock)
        confirmed.command_id = str(uuid4())
        if python_worker:
            confirmed.endpoint = f"127.0.0.1:{50000 + pid}"
            descriptor = describe_host_clock()
            confirmed.host_clock.clock_id = descriptor.clock_id
            confirmed.host_clock.implementation = descriptor.implementation
            confirmed.host_clock.monotonic = descriptor.monotonic
            confirmed.host_clock.adjustable = descriptor.adjustable
            confirmed.host_clock.resolution_s = descriptor.resolution_s
        runtime.registry.confirm(confirmed, runtime.clock)

    launch(runtime.identity, vr, 41, python_worker=True)
    launch(vr, renderer_worker, 42)
    launch(renderer_worker, nested_worker, 43)
    launch(runtime.identity, gui, 44)
    launch(gui, foreign_worker, 45)
    worker_backend = runtime._worker_backend_ancestry({("vr", vr.generation)})
    assert worker_backend == {
        (renderer_worker.role, renderer_worker.generation): "vr",
        (nested_worker.role, nested_worker.generation): "vr",
    }

    runtime.credentials[(vr.role, vr.generation)] = "vr-secret"
    work = types.WorkContext(
        session=types.SessionContext(
            controller_generation=runtime.controller.generation,
            session_id=str(uuid4()),
        )
    )
    prepared = wire.RegisteredContext(
        controller=runtime.controller,
        supervisor=runtime.identity,
        paired_spikeglx=False,
        work=work,
        required_participants=[
            types.BackendContext(backend_name="vr", backend_generation=vr.generation)
        ],
    )
    preliminary = wire.RegisterContextRequest(command_id=str(uuid4()), context=prepared)
    assert (
        await runtime.RegisterContext(preliminary, controller_context)
    ).admission.result == types.COMMAND_RESULT_ACCEPTED
    assert (
        await runtime.ReportHeartbeat(
            types.HeartbeatReport(
                source=vr,
                work=work,
                sent_monotonic_ns=host_time_ns(),
                session_phase=types.SESSION_PHASE_SETTING_UP,
                cleanup_resources_revision=0,
            ),
            Context("vr", vr.generation, "vr-secret"),
        )
    ).result == types.COMMAND_RESULT_ACCEPTED

    prepared.prepared_functions.extend(
        [
            types.PreparedFunctionScope(
                resource_id="renderer",
                owner=vr,
                affected_closure_resource_ids=["renderer"],
                essential_to_stimulus_control=True,
                feedback_hold_required_on_loss=False,
                bounded_uncertainty_supported=False,
                lifecycle_sources=["renderer"],
            ),
            types.PreparedFunctionScope(
                resource_id="worker-monitor",
                owner=nested_worker,
                affected_closure_resource_ids=["worker-monitor"],
                essential_to_stimulus_control=False,
                feedback_hold_required_on_loss=False,
                bounded_uncertainty_supported=False,
            ),
        ]
    )
    forged = wire.RegisteredContext.FromString(prepared.SerializeToString())
    forged.prepared_functions[1].owner.CopyFrom(foreign_worker)
    rejected = await runtime.RegisterContext(
        wire.RegisterContextRequest(command_id=str(uuid4()), context=forged),
        controller_context,
    )
    assert rejected.admission.result == types.COMMAND_RESULT_REJECTED

    accepted = await runtime.RegisterContext(
        wire.RegisterContextRequest(command_id=str(uuid4()), context=prepared),
        controller_context,
    )
    assert accepted.admission.result == types.COMMAND_RESULT_ACCEPTED
    assert runtime._prepared_worker_backend == worker_backend
    runtime.last_heartbeat[("controller", runtime.controller.generation)] = (
        host_time_ns()
    )
    error = types.ErrorReport(
        error_id=str(uuid4()),
        source=nested_worker,
        work=work,
        occurred_monotonic_ns=host_time_ns(),
        failure=types.Failure(code="WORKER_FAULT", message="worker unavailable"),
    )
    assert runtime._classification(error, host_time_ns() + 1_000_000_000) == "pending"


@pytest.mark.asyncio
async def test_status_retry_preserves_revision_and_timestamp(tmp_path: Path) -> None:
    runtime, _, outbound, _ = make_runtime(tmp_path)
    outbound.fail_status_once = True
    runtime._changed()
    assert runtime._status_task is not None
    await runtime._status_task
    assert runtime._pending_status is not None
    await runtime._send_status()
    assert len(outbound.statuses) == 2
    assert outbound.statuses[0] == outbound.statuses[1]
    assert runtime._pending_status is None


@pytest.mark.asyncio
async def test_supervisor_heartbeat_does_not_depend_on_status_change(
    tmp_path: Path,
) -> None:
    runtime, _, outbound, _ = make_runtime(tmp_path)
    runtime.heartbeat_interval_ns = 1_000_000
    loop = asyncio.create_task(runtime.heartbeat_loop())
    await asyncio.sleep(0.01)
    loop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loop
    assert len(outbound.heartbeats) >= 2
    assert runtime.status_revision == 0


@pytest.mark.asyncio
async def test_confirmed_controller_without_first_heartbeat_times_out(
    tmp_path: Path,
) -> None:
    runtime, native, outbound, _ = make_runtime(tmp_path)
    runtime.credentials[("supervisor", runtime.identity.generation)] = (
        "supervisor-secret"
    )
    runtime.graceful_exit_ns = 1
    runtime.terminate_exit_ns = 1
    plan = wire.PlanLaunchRequest(
        command_id=str(uuid4()),
        owner=runtime.identity,
        child=runtime.controller,
        executable="C:\\Python311\\python.exe",
        python_worker=True,
        stop_method="grpc_shutdown",
    )
    state = runtime.registry.plan(plan)
    native.jobs[state.containment_job_name] = [(100, 200, plan.executable)]
    receipt = await runtime.ConfirmLaunch(
        wire.ConfirmLaunchRequest(
            command_id=str(uuid4()),
            launch_command_id=plan.command_id,
            owner=runtime.identity,
            child=runtime.controller,
            pid=100,
            creation_time_100ns=200,
        ),
        Context("supervisor", runtime.identity.generation, "supervisor-secret"),
    )
    assert receipt.admission.result == types.COMMAND_RESULT_ACCEPTED
    endpoint = wire.ConfirmLaunchRequest(
        command_id=str(uuid4()),
        launch_command_id=plan.command_id,
        owner=runtime.identity,
        child=runtime.controller,
        pid=100,
        creation_time_100ns=200,
        endpoint="127.0.0.1:50051",
    )
    descriptor = describe_host_clock()
    endpoint.host_clock.clock_id = descriptor.clock_id
    endpoint.host_clock.implementation = descriptor.implementation
    endpoint.host_clock.monotonic = descriptor.monotonic
    endpoint.host_clock.adjustable = descriptor.adjustable
    endpoint.host_clock.resolution_s = descriptor.resolution_s
    receipt = await runtime.ConfirmLaunch(
        endpoint,
        Context("controller", runtime.controller.generation, "controller-secret"),
    )
    assert receipt.state.phase == wire.LAUNCH_PHASE_OPERATIONAL
    assert ("controller", runtime.controller.generation) in runtime.last_heartbeat
    seeded = runtime.last_heartbeat[("controller", runtime.controller.generation)]
    replay = await runtime.ConfirmLaunch(
        endpoint,
        Context("controller", runtime.controller.generation, "controller-secret"),
    )
    assert replay.admission.result == types.COMMAND_RESULT_ACCEPTED
    assert (
        runtime.last_heartbeat[("controller", runtime.controller.generation)] == seeded
    )
    # Exercise the monitor with a confirmed identity even if the first application
    # heartbeat never arrives; no OS exit is needed to trigger loss.
    runtime.last_heartbeat[("controller", runtime.controller.generation)] = (
        host_time_ns() - 16_000_000_000
    )
    monitor = asyncio.create_task(runtime.monitor(period_s=0.001))
    await asyncio.sleep(0.03)
    monitor.cancel()
    assert runtime._interruption is not None
    assert runtime._interruption.reason.code == "CONTROLLER_LOST"
    assert runtime._safety_task is not None
    await runtime._safety_task
    assert outbound.interruptions


@pytest.mark.asyncio
async def test_explicit_shutdown_progresses_without_waiting_for_controller_exit(
    tmp_path: Path,
) -> None:
    runtime, _, _, caller = make_runtime(tmp_path)
    command_id = str(uuid4())
    request = wire.ApplicationShutdownRequest(
        command_id=command_id,
        controller=runtime.controller,
        supervisor=runtime.identity,
        operator=types.OperatorContext(command_id=command_id),
        controller_operation=types.OperationContext(command_id=command_id),
        issued_monotonic_ns=host_time_ns(),
    )
    receipt = await runtime.RequestApplicationShutdown(request, caller)
    assert receipt.result == types.COMMAND_RESULT_ACCEPTED
    assert runtime._shutdown_task is not None
    await runtime._shutdown_task
    assert runtime.shutdown_complete.is_set()
    assert (await runtime.RequestApplicationShutdown(request, caller)) == receipt


def test_controller_cannot_claim_backend_prepared_function(tmp_path: Path) -> None:
    runtime, _, _, _ = make_runtime(tmp_path)
    vr = types.ProcessIdentity(role="vr", generation=str(uuid4()))
    work = types.WorkContext(
        session=types.SessionContext(
            controller_generation=runtime.controller.generation, session_id=str(uuid4())
        )
    )
    runtime.context = wire.RegisteredContext(
        controller=runtime.controller,
        supervisor=runtime.identity,
        work=work,
        required_participants=[
            types.BackendContext(backend_name="vr", backend_generation=vr.generation)
        ],
        policies=types.ControlPolicies(recovery_ns=100_000_000),
        prepared_functions=[
            types.PreparedFunctionScope(
                resource_id="stimulus.control",
                owner=runtime.controller,
                affected_closure_resource_ids=["stimulus.control"],
                essential_to_stimulus_control=True,
                feedback_hold_required_on_loss=False,
                bounded_uncertainty_supported=False,
                lifecycle_sources=["renderer"],
            ),
        ],
    )
    with pytest.raises(IncidentEvidenceError, match="no backend ancestry"):
        IncidentTopology.from_registered(runtime.context)
