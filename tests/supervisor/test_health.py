"""Heartbeat admission, safety fences and supervised background work."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.clock import describe_host_clock, host_time_ns
from tests.supervisor.support import Context, make_runtime

from .support import (
    _worker_and_helper,
    launch,
)


async def _eventually(predicate: Callable[[], bool], *, timeout_s: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while not predicate() and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.005)
    assert predicate(), "expected supervisor state did not arrive"


def heartbeat(source: types.ProcessIdentity) -> types.HeartbeatReport:
    return types.HeartbeatReport(
        source=source,
        sent_monotonic_ns=host_time_ns(),
        session_phase=types.SESSION_PHASE_CONFIGURATION,
    )


def error(source: types.ProcessIdentity, code: str) -> types.ErrorReport:
    return types.ErrorReport(
        error_id=str(uuid4()),
        source=source,
        occurred_monotonic_ns=host_time_ns(),
        failure=types.Failure(code=code, message="test"),
    )


async def test_unreadable_job_does_not_fail_another_sources_heartbeat(
    tmp_path: Path,
) -> None:
    runtime, native, _, _ = make_runtime(tmp_path)
    healthy = types.ProcessIdentity(role="visual_stimulus", generation=str(uuid4()))
    blocked = types.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    launch(runtime, native, runtime.identity, healthy, 51)
    launch(runtime, native, runtime.identity, blocked, 52)
    job = next(
        state.containment_job_name
        for state in runtime.registry.states()
        if state.plan.child == blocked
    )
    del native.jobs[job]  # inspection of this one job now fails
    ok = await runtime.health.report_heartbeat(heartbeat(healthy), host_time_ns())
    assert ok.result == types.COMMAND_RESULT_ACCEPTED
    rejected = await runtime.health.report_heartbeat(heartbeat(blocked), host_time_ns())
    assert rejected.failure.code == "WRONG_CONTEXT"


async def test_worker_heartbeat_rejected_coordinator_heartbeat_accepted(
    tmp_path: Path,
) -> None:
    runtime, native, _, _ = make_runtime(tmp_path)
    visual_stimulus = types.ProcessIdentity(
        role="visual_stimulus", generation=str(uuid4())
    )
    worker = types.ProcessIdentity(role="renderer-worker", generation=str(uuid4()))
    launch(runtime, native, runtime.identity, visual_stimulus, 41)
    launch(runtime, native, visual_stimulus, worker, 42)
    ok = await runtime.health.report_heartbeat(
        heartbeat(visual_stimulus), host_time_ns()
    )
    assert ok.result == types.COMMAND_RESULT_ACCEPTED
    bad = await runtime.health.report_heartbeat(heartbeat(worker), host_time_ns())
    assert bad.result == types.COMMAND_RESULT_REJECTED
    assert bad.failure.code == "WRONG_CONTEXT"


async def test_worker_error_admission_and_reserved_codes(tmp_path: Path) -> None:
    runtime, native, _, _ = make_runtime(tmp_path)
    visual_stimulus = types.ProcessIdentity(
        role="visual_stimulus", generation=str(uuid4())
    )
    worker = types.ProcessIdentity(role="renderer-worker", generation=str(uuid4()))
    launch(runtime, native, runtime.identity, visual_stimulus, 41)
    launch(runtime, native, visual_stimulus, worker, 42)
    runtime.shutdown.graceful_exit_ns = runtime.shutdown.terminate_exit_ns = 1
    reserved = await runtime.health.report_error(error(worker, "CONTROLLER_LOST"))
    assert reserved.result == types.COMMAND_RESULT_REJECTED
    assert reserved.failure.code == "INVALID_SOURCE"
    assert runtime.shutdown_state.interruption is None
    ordinary = await runtime.health.report_error(error(worker, "RENDER_FAULT"))
    assert ordinary.result == types.COMMAND_RESULT_ACCEPTED
    coordinator = await runtime.health.report_error(
        error(visual_stimulus, "CONTROLLER_LOST")
    )
    assert coordinator.result == types.COMMAND_RESULT_ACCEPTED
    assert runtime.shutdown_state.interruption is not None
    await runtime.shutdown_state.safety_task


async def test_supervisor_tasks_are_retained_and_cancelled(tmp_path: Path) -> None:
    runtime, _, _, _ = make_runtime(tmp_path)
    started = asyncio.Event()

    async def never() -> None:
        started.set()
        await asyncio.Event().wait()

    task = runtime.tasks.spawn("recovery", never())
    await started.wait()
    assert task in runtime.tasks._tasks
    runtime.stop_background()
    await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()
    assert runtime.status_state.warnings == {}


async def test_monitor_triggers_one_background_reconcile(tmp_path: Path) -> None:
    runtime, native, _, _ = make_runtime(tmp_path)
    _worker_and_helper(runtime, native)
    release = asyncio.Event()
    calls = 0

    async def blocked(deadline_ns: int) -> list[str]:
        nonlocal calls
        calls += 1
        await release.wait()
        return ["ffmpeg:x released without worker closure evidence"]

    runtime.health.reconcile_helpers = blocked
    monitor = asyncio.create_task(runtime.health.monitor(period_s=0.001))
    try:
        await _eventually(lambda: calls == 1)
        assert not monitor.done()
        await asyncio.sleep(0.05)
        assert calls == 1
        release.set()
        await _eventually(
            lambda: any(
                "ffmpeg:x" in warning.message
                for warning in runtime.status_state.warnings.values()
            )
        )
    finally:
        release.set()
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)


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
    receipt = await runtime.service.ReportError(report, caller)
    assert receipt.result == types.COMMAND_RESULT_ACCEPTED
    assert runtime.shutdown_state.interruption is not None
    assert runtime.shutdown_state.safety_task is not None
    await runtime.shutdown_state.safety_task
    assert len(outbound.interruptions) == 1
    report_path = next((tmp_path / "reports").glob("emergency-*.json"))
    assert json.loads(report_path.read_text())["spikeglx_stop_unconfirmed"] is False


async def test_unclassified_error_fences_safety(tmp_path: Path) -> None:
    runtime, _, outbound, caller = make_runtime(tmp_path)
    work = types.WorkContext(
        session=types.SessionContext(
            controller_generation=runtime.controller.generation,
            session_id=str(uuid4()),
        )
    )
    runtime.registration_state.context = wire.RegisteredContext(
        controller=runtime.controller,
        supervisor=runtime.identity,
        work=work,
        paired_spikeglx=True,
        # Long enough that machine load cannot expire it before the first assertion.
        policies=types.ControlPolicies(recovery_ns=200_000_000),
    )
    report = types.ErrorReport(
        error_id=str(uuid4()),
        source=runtime.controller,
        work=work,
        occurred_monotonic_ns=host_time_ns(),
        failure=types.Failure(code="UNRECOGNIZED", message="unknown control failure"),
    )
    receipt = await runtime.service.ReportError(report, caller)
    assert receipt.result == types.COMMAND_RESULT_ACCEPTED
    assert runtime.shutdown_state.interruption is None
    monitor = asyncio.create_task(runtime.health.monitor(period_s=0.001))
    try:
        await _eventually(lambda: runtime.shutdown_state.interruption is not None)
    finally:
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)
    await runtime.shutdown_state.safety_task
    assert len(outbound.interruptions) == 1
    assert (tmp_path / "reports").is_dir()
    report_path = next((tmp_path / "reports").glob("emergency-*.json"))
    assert json.loads(report_path.read_text())["spikeglx_stop_unconfirmed"] is True


async def test_confirmed_controller_without_first_heartbeat_times_out(
    tmp_path: Path,
) -> None:
    runtime, native, outbound, _ = make_runtime(tmp_path)
    runtime.credentials[("supervisor", runtime.identity.generation)] = (
        "supervisor-secret"
    )
    runtime.shutdown.graceful_exit_ns = 1
    runtime.shutdown.terminate_exit_ns = 1
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
    receipt = await runtime.service.ConfirmLaunch(
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
    receipt = await runtime.service.ConfirmLaunch(
        endpoint,
        Context("controller", runtime.controller.generation, "controller-secret"),
    )
    assert receipt.state.phase == wire.LAUNCH_PHASE_OPERATIONAL
    assert (
        "controller",
        runtime.controller.generation,
    ) in runtime.health_state.last_heartbeat
    seeded = runtime.health_state.last_heartbeat[
        ("controller", runtime.controller.generation)
    ]
    replay = await runtime.service.ConfirmLaunch(
        endpoint,
        Context("controller", runtime.controller.generation, "controller-secret"),
    )
    assert replay.admission.result == types.COMMAND_RESULT_ACCEPTED
    assert (
        runtime.health_state.last_heartbeat[
            ("controller", runtime.controller.generation)
        ]
        == seeded
    )
    # Exercise the monitor with a confirmed identity even if the first application
    # heartbeat never arrives; no OS exit is needed to trigger loss.
    runtime.health_state.last_heartbeat[
        ("controller", runtime.controller.generation)
    ] = host_time_ns() - 16_000_000_000
    monitor = asyncio.create_task(runtime.health.monitor(period_s=0.001))
    try:
        await _eventually(lambda: runtime.shutdown_state.interruption is not None)
    finally:
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)
    assert runtime.shutdown_state.interruption.reason.code == "CONTROLLER_LOST"
    assert runtime.shutdown_state.safety_task is not None
    await runtime.shutdown_state.safety_task
    assert outbound.interruptions
