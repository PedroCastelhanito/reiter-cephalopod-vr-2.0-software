"""Shutdown deadlines, controller loss and retained worker closure evidence."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.clock import host_time_ns
from cephvr.supervisor.acquisition_shutdown import lifecycle_payload_matches
from cephvr.supervisor.runtime import SupervisorRuntime
from tests.supervisor.support import Native, Outbound, make_runtime

from .support import _worker_and_helper, launch


def _finished(closure: int) -> acq.WorkerLifecycleEvidence:
    evidence = acq.WorkerLifecycleEvidence(
        source=acq.WorkerContext(
            worker=control.ProcessIdentity(
                role="acquisition_behavioral_worker", generation=str(uuid4())
            ),
            owner=control.ProcessIdentity(role="acquisition", generation=str(uuid4())),
            camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
            work=control.WorkContext(
                session=control.SessionContext(session_id=str(uuid4()))
            ),
        ),
        state_revision=7,
    )
    evidence.operation.command_id = str(uuid4())
    evidence.finished.activity_stopped = True
    evidence.finished.outputs.add(
        output_key="behavioral.camera",
        path="C:/data/trial.mp4",
        closure=closure,
        artifact_present=True,
    )
    return evidence


def test_retained_finished_evidence_must_match_complete_output_payload() -> None:
    observed = _finished(control.OUTPUT_CLOSURE_CLOSED)
    retained = acq.WorkerLifecycleEvidence.FromString(
        observed.SerializeToString(deterministic=True)
    )
    assert lifecycle_payload_matches(observed, retained)

    retained.finished.outputs[0].closure = control.OUTPUT_CLOSURE_FAILED
    assert not lifecycle_payload_matches(observed, retained)


async def _registered_vr(
    tmp_path: Path,
) -> tuple[SupervisorRuntime, Native, Outbound, types.ProcessIdentity]:
    runtime, native, outbound, controller_context = make_runtime(tmp_path)
    vr = types.ProcessIdentity(role="vr", generation=str(uuid4()))
    launch(runtime, native, runtime.identity, vr, 41)
    receipt = await runtime.service.RegisterContext(
        wire.RegisterContextRequest(
            command_id=str(uuid4()),
            context=wire.RegisteredContext(
                controller=runtime.controller,
                supervisor=runtime.identity,
                paired_spikeglx=False,
                work=types.WorkContext(
                    session=types.SessionContext(
                        controller_generation=runtime.controller.generation,
                        session_id=str(uuid4()),
                    )
                ),
                required_participants=[
                    types.BackendContext(
                        backend_name="vr", backend_generation=vr.generation
                    )
                ],
            ),
        ),
        controller_context,
    )
    assert receipt.admission.result == types.COMMAND_RESULT_ACCEPTED
    return runtime, native, outbound, vr


def _controller_silent(runtime: SupervisorRuntime, phase: int) -> None:
    key = ("controller", runtime.controller.generation)
    runtime.health_state.last_heartbeat[key] = 1
    runtime.health_state.heartbeat_reports[key] = types.HeartbeatReport(
        source=runtime.controller, sent_monotonic_ns=1, session_phase=phase
    )
    runtime.shutdown_state.shutdown_request = wire.ApplicationShutdownRequest(
        command_id=str(uuid4())
    ).SerializeToString()


async def test_controller_silence_after_shutdown_is_not_a_safety_fault(
    tmp_path: Path,
) -> None:
    runtime, _, outbound, _ = await _registered_vr(tmp_path)
    _controller_silent(runtime, types.SESSION_PHASE_RUNNING)
    monitor = asyncio.create_task(runtime.monitor(period_s=0.001))
    await asyncio.sleep(0.03)
    monitor.cancel()
    await asyncio.gather(monitor, return_exceptions=True)
    assert runtime.shutdown_state.interruption is None
    assert not (tmp_path / "reports").exists()
    assert outbound.interruptions == []


async def test_lost_controller_with_active_session_interrupts_before_shutdown(
    tmp_path: Path,
) -> None:
    runtime, _, outbound, vr = await _registered_vr(tmp_path)
    calls: list[str] = []

    async def interrupt_backend(target, request, *, deadline_ns) -> None:  # type: ignore[no-untyped-def]
        calls.append(f"interrupt:{target.backend_name}:{request.reason.code}")

    async def shutdown_backend(target, request, *, deadline_ns) -> None:  # type: ignore[no-untyped-def]
        calls.append(f"shutdown:{target.backend_name}")

    outbound.interrupt_backend = interrupt_backend  # type: ignore[attr-defined]
    outbound.shutdown_backend = shutdown_backend  # type: ignore[attr-defined]
    _controller_silent(runtime, types.SESSION_PHASE_RUNNING)
    runtime.shutdown_state.shutdown_deadline_ns = host_time_ns() + 2 * 10**8
    runtime.shutdown_state.cleanup_deadline_ns = host_time_ns() + 2 * 10**8
    runtime.shutdown.graceful_exit_ns = 1
    runtime.shutdown.terminate_exit_ns = 1
    await runtime.shutdown.shutdown_owned()
    assert calls == ["interrupt:vr:CONTROLLER_LOST_DURING_SHUTDOWN", "shutdown:vr"]
    assert runtime.shutdown_state.interruption is None
    assert not (tmp_path / "reports").exists()


async def test_lost_controller_without_active_session_is_not_interrupted(
    tmp_path: Path,
) -> None:
    runtime, _, outbound, _ = await _registered_vr(tmp_path)
    calls: list[str] = []

    async def interrupt_backend(target, request, *, deadline_ns) -> None:  # type: ignore[no-untyped-def]
        calls.append("interrupt")

    outbound.interrupt_backend = interrupt_backend  # type: ignore[attr-defined]
    _controller_silent(runtime, types.SESSION_PHASE_READY)
    await runtime.shutdown.interrupt_if_controller_lost()
    assert calls == []


async def test_failed_launcher_notification_is_reported_unconfirmed(
    tmp_path: Path,
) -> None:
    runtime, _, outbound, _ = make_runtime(tmp_path)

    async def notify(deadline_ns: int, cause: str) -> None:
        raise ConnectionError("launcher pipe closed")

    outbound.notify_launcher_shutdown = notify  # type: ignore[method-assign]
    task = runtime.tasks.spawn(
        "launcher shutdown notification", outbound.notify_launcher_shutdown(1, "x")
    )
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)
    assert any(
        "launcher shutdown notification unconfirmed" in warning.message
        for warning in runtime.status_state.warnings.values()
    )
    assert runtime.tasks._tasks == set()


# Final audit: released entries stay retained but are never re-inspected.


async def test_shutdown_completes_after_a_helper_was_released(tmp_path: Path) -> None:
    runtime, native, _, caller = make_runtime(tmp_path)
    worker, helper = _worker_and_helper(runtime, native)
    native.jobs[helper.containment_job_name] = []
    runtime.registry.release(helper.plan.command_id, obligations_met=True)
    native.jobs[worker.containment_job_name] = []  # worker already exited
    command_id = str(uuid4())
    request = wire.ApplicationShutdownRequest(
        command_id=command_id,
        controller=runtime.controller,
        supervisor=runtime.identity,
        operator=types.OperatorContext(command_id=command_id),
        controller_operation=types.OperationContext(command_id=command_id),
        issued_monotonic_ns=host_time_ns(),
    )
    receipt = await runtime.service.RequestApplicationShutdown(request, caller)
    assert receipt.result == types.COMMAND_RESULT_ACCEPTED
    assert runtime.shutdown_state.shutdown_task is not None
    await runtime.shutdown_state.shutdown_task
    assert runtime.shutdown_state.shutdown_complete.is_set()


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
    receipt = await runtime.service.RequestApplicationShutdown(request, caller)
    assert receipt.result == types.COMMAND_RESULT_ACCEPTED
    assert runtime.shutdown_state.shutdown_task is not None
    await runtime.shutdown_state.shutdown_task
    assert runtime.shutdown_state.shutdown_complete.is_set()
    assert (
        await runtime.service.RequestApplicationShutdown(request, caller)
    ) == receipt
