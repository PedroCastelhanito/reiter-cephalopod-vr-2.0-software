"""Session registration, cleanup proof and partial startup cancellation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cephvr.acquisition.identity import FFMPEG_ROLE
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.clock import describe_host_clock, host_time_ns
from cephvr.shared.incidents import IncidentEvidenceError, IncidentTopology
from cephvr.shared.transport_deadlines import DEADLINE_METADATA_KEY, deadline_metadata
from cephvr.supervisor import startup
from tests.supervisor.support import Context, Native, make_runtime

from .support import (
    EXE,
    _identity,
    _worker_and_helper,
)

# PlanLaunch admission does not run reconciliation.


async def test_plan_launch_rejects_expired_deadline_and_never_reconciles(
    tmp_path: Path,
) -> None:
    runtime, native, _, _ = make_runtime(tmp_path)
    calls: list[int] = []

    async def spy(deadline_ns: int) -> list[str]:
        calls.append(deadline_ns)
        return []

    runtime.shutdown.acquisition_worker_control.reconcile_native_helper_exits = spy  # type: ignore[method-assign]
    worker, _ = _worker_and_helper(runtime, native)
    worker_key = (worker.plan.child.role, worker.plan.child.generation)
    runtime.credentials[worker_key] = "worker-secret"
    runtime.registration.source_registered = lambda *a, **k: True  # type: ignore[method-assign]
    request = wire.PlanLaunchRequest(
        command_id=str(uuid4()),
        owner=worker.plan.child,
        child=_identity(FFMPEG_ROLE),
        executable=EXE,
        stop_method="owner_stdin_eof",
    )

    def context(deadline_ns: int) -> Context:
        ctx = Context(worker_key[0], worker_key[1], "worker-secret")
        ctx.metadata = (
            *ctx.metadata,
            ("x-cephvr-child-token", "child-secret"),
            (DEADLINE_METADATA_KEY, str(deadline_ns)),
        )
        return ctx

    expired = await runtime.service.PlanLaunch(request, context(host_time_ns() - 1))  # type: ignore[arg-type]
    assert expired.admission.result == types.COMMAND_RESULT_REJECTED
    fresh = await runtime.service.PlanLaunch(
        request,
        context(host_time_ns() + 10_000_000_000),  # type: ignore[arg-type]
    )
    assert fresh.admission.result == types.COMMAND_RESULT_ACCEPTED
    assert calls == []


# Failed controller registration cancels role launches.


async def test_failed_controller_registration_cancels_role_launches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    supervisor_generation, controller_generation = str(uuid4()), str(uuid4())
    started: list[str] = []
    cancelled: list[str] = []
    state = {"closed": 0, "stopped": 0}

    class FakeOutbound:
        def __init__(self, *args: object) -> None:
            self.backend_ports = {"acquisition": 1, "visual_stimulus": 2, "tracking": 3}

        def bind_registry(self, registry: object) -> None:
            pass

        async def register_controller(self, *args: object) -> None:
            await asyncio.sleep(0.01)  # let the role launches start first
            raise RuntimeError("launcher pipe closed")

        async def retire_worker_generation(self, role: str, generation: str) -> None:
            pass

        async def close(self) -> None:
            state["closed"] += 1

    class FakeServer:
        async def stop(self, grace: int) -> None:
            state["stopped"] += 1

    async def fake_server(service: object, port: int) -> FakeServer:
        return FakeServer()

    async def fake_controller(inputs: object, handle: int) -> object:
        return SimpleNamespace(pid=1, creation_time_100ns=1)

    async def fake_role(inputs: object, role: str, module: str, child: object) -> None:
        started.append(role)
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.append(role)
            raise

    monkeypatch.setattr(
        startup,
        "validate_bootstrap",
        lambda bootstrap: {
            "acquisition": "a",
            "visual_stimulus": "v",
            "tracking": "t",
            "gui": "g",
        },
    )
    monkeypatch.setattr(startup, "WindowsJobs", Native)
    monkeypatch.setattr(startup, "GrpcOutbound", FakeOutbound)
    monkeypatch.setattr(startup, "start_supervisor_server", fake_server)
    monkeypatch.setattr(startup, "launch_controller", fake_controller)
    monkeypatch.setattr(startup, "launch_role", fake_role)
    bootstrap = {
        "software_root": str(tmp_path),
        "supervisor_generation": supervisor_generation,
        "controller_generation": controller_generation,
        "supervisor_token": "s",
        "controller_token": "c",
        "supervisor_port": 1,
        "controller_port": 2,
        "interpreter": EXE,
        "backend_ports": {"acquisition": 1, "visual_stimulus": 2, "tracking": 3},
        "max_message_bytes": 1 << 20,
        "max_retained_incidents": 16,
        "command_retention_ns": 1_000_000_000,
        "silence_timeout_ns": 15_000_000_000,
        "emergency_timeout_ns": 5_000_000_000,
        "graceful_exit_ns": 1_000_000_000,
        "terminate_exit_ns": 1_000_000_000,
        "application_backstop_ns": 90_000_000_000,
        "heartbeat_interval_ns": 5_000_000_000,
    }
    with pytest.raises(RuntimeError, match="launcher pipe closed"):
        await startup.run_supervisor(bootstrap, 0, 0, 0)
    assert (
        sorted(started)
        == sorted(cancelled)
        == ["acquisition", "gui", "tracking", "visual_stimulus"]
    )
    assert state == {"closed": 1, "stopped": 1}


async def test_new_session_requires_verified_prior_cleanup(tmp_path: Path) -> None:
    runtime, native, outbound, controller_context = make_runtime(tmp_path)
    visual_stimulus = types.ProcessIdentity(
        role="visual_stimulus", generation=str(uuid4())
    )
    runtime.credentials[(visual_stimulus.role, visual_stimulus.generation)] = (
        "visual-stimulus-secret"
    )
    planned = wire.PlanLaunchRequest(
        command_id=str(uuid4()),
        owner=runtime.identity,
        child=visual_stimulus,
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
        child=visual_stimulus,
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
                        backend_name="visual_stimulus",
                        backend_generation=visual_stimulus.generation,
                    )
                ],
                prepared_functions=[
                    types.PreparedFunctionScope(
                        resource_id="visual_stimulus.control",
                        owner=visual_stimulus,
                        affected_closure_resource_ids=["visual_stimulus.control"],
                        essential_to_stimulus_control=True,
                        feedback_hold_required_on_loss=False,
                        bounded_uncertainty_supported=False,
                        lifecycle_sources=["renderer"],
                    )
                ],
                cleanup_resources=[
                    types.ResourceObligation(
                        owner=visual_stimulus, resource="visual_stimulus.control"
                    )
                ],
            ),
        )

    first = registration(str(uuid4()))
    preliminary = wire.RegisterContextRequest.FromString(first.SerializeToString())
    preliminary.command_id = str(uuid4())
    preliminary.context.ClearField("prepared_functions")
    preliminary.context.ClearField("cleanup_resources")
    assert (
        await runtime.service.RegisterContext(preliminary, controller_context)
    ).admission.result == types.COMMAND_RESULT_ACCEPTED
    visual_stimulus_context = Context(
        "visual_stimulus", visual_stimulus.generation, "visual-stimulus-secret"
    )
    empty_catalogue = types.HeartbeatReport(
        source=visual_stimulus,
        work=first.context.work,
        sent_monotonic_ns=host_time_ns(),
        session_phase=types.SESSION_PHASE_SETTING_UP,
        cleanup_resources_revision=0,
    )
    assert (
        await runtime.service.ReportHeartbeat(empty_catalogue, visual_stimulus_context)
    ).result == types.COMMAND_RESULT_ACCEPTED
    resource_catalogue = types.HeartbeatReport.FromString(
        empty_catalogue.SerializeToString()
    )
    resource_catalogue.cleanup_resources_revision = 1
    resource_catalogue.cleanup_resources.add(
        owner=visual_stimulus, resource="visual_stimulus.control"
    )
    assert (
        await runtime.service.ReportHeartbeat(
            resource_catalogue, visual_stimulus_context
        )
    ).result == types.COMMAND_RESULT_ACCEPTED
    if runtime.status_state.status_task is not None:
        await runtime.status_state.status_task
    process = next(
        process
        for process in outbound.statuses[-1].processes
        if process.process == visual_stimulus
    )
    assert process.launch_owner == runtime.identity
    assert process.last_heartbeat == resource_catalogue
    accepted = await runtime.service.RegisterContext(first, controller_context)
    assert accepted.admission.result == types.COMMAND_RESULT_ACCEPTED
    assert await runtime.service.RegisterContext(first, controller_context) == accepted
    second = registration(str(uuid4()))
    second.context.ClearField("prepared_functions")
    second.context.ClearField("cleanup_resources")
    blocked = await runtime.service.RegisterContext(second, controller_context)
    assert blocked.admission.result == types.COMMAND_RESULT_REJECTED

    cleanup_command_id = str(uuid4())
    fenced = wire.RegisterContextRequest.FromString(first.SerializeToString())
    fenced.command_id = str(uuid4())
    fenced.context.cleanup_commands.add(
        target=visual_stimulus,
        work=first.context.work,
        operation=types.OperationContext(command_id=cleanup_command_id),
    )
    assert (
        await runtime.service.RegisterContext(fenced, controller_context)
    ).admission.result == types.COMMAND_RESULT_ACCEPTED

    cleanup = types.LifecycleReport(
        cleanup=types.CleanupReport(
            source=visual_stimulus,
            work=first.context.work,
            operation=types.OperationContext(command_id=cleanup_command_id),
            verified_monotonic_ns=host_time_ns(),
            trial_activity_stopped=True,
            cleanup_resources_revision=1,
            resources=[
                types.ResourceRelease(resource="visual_stimulus.control", released=True)
            ],
        )
    )
    cleanup_context = Context(
        "visual_stimulus", visual_stimulus.generation, "visual-stimulus-secret"
    )
    # Cleanup reports carry their original absolute deadline (E08).
    cleanup_context.metadata += (deadline_metadata(host_time_ns() + 10**10),)
    receipt = await runtime.service.ReportLifecycle(cleanup, cleanup_context)
    assert receipt.result == types.COMMAND_RESULT_ACCEPTED
    assert (
        await runtime.service.RegisterContext(second, controller_context)
    ).admission.result == types.COMMAND_RESULT_ACCEPTED


async def test_worker_incident_ancestry_uses_exact_launch_owner_chain(
    tmp_path: Path,
) -> None:
    runtime, native, _, controller_context = make_runtime(tmp_path)
    visual_stimulus = types.ProcessIdentity(
        role="visual_stimulus", generation=str(uuid4())
    )
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

    launch(runtime.identity, visual_stimulus, 41, python_worker=True)
    launch(visual_stimulus, renderer_worker, 42)
    launch(renderer_worker, nested_worker, 43)
    launch(runtime.identity, gui, 44)
    launch(gui, foreign_worker, 45)
    worker_backend = runtime.registration.worker_backend_ancestry(
        {("visual_stimulus", visual_stimulus.generation)}
    )
    assert worker_backend == {
        (renderer_worker.role, renderer_worker.generation): "visual_stimulus",
        (nested_worker.role, nested_worker.generation): "visual_stimulus",
    }

    runtime.credentials[(visual_stimulus.role, visual_stimulus.generation)] = (
        "visual-stimulus-secret"
    )
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
            types.BackendContext(
                backend_name="visual_stimulus",
                backend_generation=visual_stimulus.generation,
            )
        ],
    )
    preliminary = wire.RegisterContextRequest(command_id=str(uuid4()), context=prepared)
    assert (
        await runtime.service.RegisterContext(preliminary, controller_context)
    ).admission.result == types.COMMAND_RESULT_ACCEPTED
    assert (
        await runtime.service.ReportHeartbeat(
            types.HeartbeatReport(
                source=visual_stimulus,
                work=work,
                sent_monotonic_ns=host_time_ns(),
                session_phase=types.SESSION_PHASE_SETTING_UP,
                cleanup_resources_revision=0,
            ),
            Context(
                "visual_stimulus", visual_stimulus.generation, "visual-stimulus-secret"
            ),
        )
    ).result == types.COMMAND_RESULT_ACCEPTED

    prepared.prepared_functions.extend(
        [
            types.PreparedFunctionScope(
                resource_id="renderer",
                owner=visual_stimulus,
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
    rejected = await runtime.service.RegisterContext(
        wire.RegisterContextRequest(command_id=str(uuid4()), context=forged),
        controller_context,
    )
    assert rejected.admission.result == types.COMMAND_RESULT_REJECTED

    accepted = await runtime.service.RegisterContext(
        wire.RegisterContextRequest(command_id=str(uuid4()), context=prepared),
        controller_context,
    )
    assert accepted.admission.result == types.COMMAND_RESULT_ACCEPTED
    assert runtime.registration_state.prepared_worker_backend == worker_backend
    runtime.health_state.last_heartbeat[
        ("controller", runtime.controller.generation)
    ] = host_time_ns()
    error = types.ErrorReport(
        error_id=str(uuid4()),
        source=nested_worker,
        work=work,
        occurred_monotonic_ns=host_time_ns(),
        failure=types.Failure(code="WORKER_FAULT", message="worker unavailable"),
    )
    assert (
        runtime.health.classification(error, host_time_ns() + 1_000_000_000)
        == "pending"
    )


def test_controller_cannot_claim_backend_prepared_function(tmp_path: Path) -> None:
    runtime, _, _, _ = make_runtime(tmp_path)
    visual_stimulus = types.ProcessIdentity(
        role="visual_stimulus", generation=str(uuid4())
    )
    work = types.WorkContext(
        session=types.SessionContext(
            controller_generation=runtime.controller.generation, session_id=str(uuid4())
        )
    )
    runtime.registration_state.context = wire.RegisteredContext(
        controller=runtime.controller,
        supervisor=runtime.identity,
        work=work,
        required_participants=[
            types.BackendContext(
                backend_name="visual_stimulus",
                backend_generation=visual_stimulus.generation,
            )
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
        IncidentTopology.from_registered(runtime.registration_state.context)
