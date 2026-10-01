"""Shutdown deadlines, controller loss and retained worker closure evidence."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.clock import host_time_ns
from cephvr.supervisor.acquisition_worker import lifecycle_payload_matches
from cephvr.supervisor.process_exit import ProcessExitEvidence, stop_owned_processes
from cephvr.supervisor.registry import LaunchRegistry
from cephvr.supervisor.runtime import SupervisorRuntime
from cephvr.supervisor.state import ShutdownState
from tests.supervisor.support import Native, Outbound, make_runtime

from .support import EXE, _identity, _launch, _worker_and_helper, launch


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


async def _registered_visual_stimulus(
    tmp_path: Path,
) -> tuple[SupervisorRuntime, Native, Outbound, types.ProcessIdentity]:
    runtime, native, outbound, controller_context = make_runtime(tmp_path)
    visual_stimulus = types.ProcessIdentity(
        role="visual_stimulus", generation=str(uuid4())
    )
    launch(runtime, native, runtime.identity, visual_stimulus, 41)
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
                        backend_name="visual_stimulus",
                        backend_generation=visual_stimulus.generation,
                    )
                ],
            ),
        ),
        controller_context,
    )
    assert receipt.admission.result == types.COMMAND_RESULT_ACCEPTED
    return runtime, native, outbound, visual_stimulus


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
    runtime, _, outbound, _ = await _registered_visual_stimulus(tmp_path)
    _controller_silent(runtime, types.SESSION_PHASE_RUNNING)
    monitor = asyncio.create_task(runtime.health.monitor(period_s=0.001))
    await asyncio.sleep(0.03)
    monitor.cancel()
    await asyncio.gather(monitor, return_exceptions=True)
    assert runtime.shutdown_state.interruption is None
    assert not (tmp_path / "reports").exists()
    assert outbound.interruptions == []


async def test_lost_controller_with_active_session_interrupts_before_shutdown(
    tmp_path: Path,
) -> None:
    runtime, _, outbound, visual_stimulus = await _registered_visual_stimulus(tmp_path)
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
    assert calls == [
        "interrupt:visual_stimulus:CONTROLLER_LOST_DURING_SHUTDOWN",
        "shutdown:visual_stimulus",
    ]
    assert runtime.shutdown_state.interruption is None
    assert not (tmp_path / "reports").exists()


async def test_lost_controller_without_active_session_is_not_interrupted(
    tmp_path: Path,
) -> None:
    runtime, _, outbound, _ = await _registered_visual_stimulus(tmp_path)
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


@pytest.mark.parametrize("failure", ["error", "timeout"])
async def test_safety_delivery_failure_does_not_gate_other_deliveries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    runtime, _, outbound, _ = await _registered_visual_stimulus(tmp_path)
    participant_done = asyncio.Event()
    controller_cancelled = asyncio.Event()
    calls: list[str] = []
    deadline = host_time_ns() + 50_000_000
    runtime.shutdown_state.shutdown_deadline_ns = deadline

    async def controller(report: wire.InterruptionReport) -> None:
        await participant_done.wait()
        if failure == "error":
            raise ConnectionError("controller unavailable")
        try:
            await asyncio.Event().wait()
        finally:
            controller_cancelled.set()

    async def participant(*args: object, **kwargs: object) -> None:
        calls.append("participant")
        assert kwargs["deadline_ns"] == deadline
        participant_done.set()

    async def launcher(deadline_ns: int, cause: str) -> None:
        assert deadline_ns == deadline
        calls.append("launcher")

    async def emergency(*args: object, **kwargs: object) -> None:
        calls.append("emergency")

    async def shutdown() -> None:
        calls.append("shutdown")

    monkeypatch.setattr(outbound, "report_interruption", controller)
    monkeypatch.setattr(outbound, "interrupt_backend", participant)
    monkeypatch.setattr(outbound, "notify_launcher_shutdown", launcher)
    monkeypatch.setattr("cephvr.supervisor.shutdown.write_emergency_report", emergency)
    monkeypatch.setattr(runtime.shutdown, "shutdown_owned", shutdown)
    await runtime.shutdown.deliver_safety(wire.InterruptionReport())
    await asyncio.sleep(0)
    assert set(calls) == {"participant", "launcher", "emergency", "shutdown"}
    assert calls[-1] == "shutdown"
    assert controller_cancelled.is_set() is (failure == "timeout")
    assert runtime.shutdown_state.shutdown_deadline_ns == deadline
    warnings = [item.message for item in runtime.status_state.warnings.values()]
    assert len(warnings) == 1
    assert "interruption report unconfirmed" in warnings[0]
    assert ("TimeoutError" if failure == "timeout" else "ConnectionError") in warnings[
        0
    ]


class _ExitNative(Native):
    def __init__(self) -> None:
        super().__init__()
        self.terminated: list[tuple[int, int]] = []
        self.unreadable: set[str] = set()
        self.fail_once: set[str] = set()
        self.stuck: set[tuple[int, int]] = set()

    def inspect_launch_job(self, name: str) -> list[tuple[int, int, str]]:
        if name in self.fail_once:
            self.fail_once.remove(name)
            raise OSError("temporary inspection failure")
        if name in self.unreadable:
            raise OSError("job unreadable")
        return super().inspect_launch_job(name)

    def terminate_exact(self, pid: int, creation_time_100ns: int) -> None:
        self.terminated.append((pid, creation_time_100ns))
        if (pid, creation_time_100ns) in self.stuck:
            raise OSError("termination unconfirmed")
        super().terminate_exact(pid, creation_time_100ns)


class _ExitClock:
    now = 1_000_000_000

    async def sleep(self, seconds: float) -> None:
        self.now += round(seconds * 1e9)


@pytest.fixture
def exit_clock(monkeypatch: pytest.MonkeyPatch) -> _ExitClock:
    clock = _ExitClock()
    monkeypatch.setattr(
        "cephvr.supervisor.process_exit.host_time_ns", lambda: clock.now
    )
    monkeypatch.setattr(
        "cephvr.supervisor.process_exit.asyncio", SimpleNamespace(sleep=clock.sleep)
    )
    return clock


async def test_process_exit_orders_groups_and_deduplicates_exact_members(
    exit_clock: _ExitClock,
) -> None:
    native = _ExitNative()
    registry = LaunchRegistry(native, 15_000_000_000)
    launches = [
        _launch(
            registry, native, _identity("supervisor"), _identity(role), pid, python=True
        )
        for role, pid in [
            ("controller", 1),
            ("gui", 2),
            ("visual_stimulus", 3),
            ("acquisition", 4),
        ]
    ]
    # Both backend jobs contain the same nested child. Failed termination must
    # not produce duplicate attempts within the group or stop other members.
    for state in launches[2:]:
        native.jobs[state.containment_job_name].append((12, 112, EXE))
    native.stuck.add((12, 112))
    native.jobs["unrelated"] = [(3, 999, EXE)]  # reused PID, unrelated creation time
    shutdown = ShutdownState(shutdown_deadline_ns=exit_clock.now + 500_000_000)
    evidence = await stop_owned_processes(
        registry=registry,
        native=native,
        shutdown=shutdown,
        graceful_exit_ns=50_000_000,
        terminate_exit_ns=50_000_000,
    )
    assert native.terminated == [(3, 103), (12, 112), (4, 104), (1, 101), (2, 102)]
    assert set(evidence.remaining) == {(12, 112, EXE)}
    assert not evidence.unconfirmed_jobs
    assert native.jobs["unrelated"] == [(3, 999, EXE)]
    assert not shutdown.shutdown_complete.is_set()  # coordinator owns completion


@pytest.mark.parametrize("persistent", [False, True])
async def test_final_inspection_controls_unconfirmed_exit_evidence(
    exit_clock: _ExitClock,
    persistent: bool,
) -> None:
    native = _ExitNative()
    registry = LaunchRegistry(native, 15_000_000_000)
    bad = _launch(
        registry,
        native,
        _identity("supervisor"),
        _identity("visual_stimulus"),
        1,
        python=True,
    )
    _launch(
        registry,
        native,
        _identity("supervisor"),
        _identity("acquisition"),
        2,
        python=True,
    )
    failures = native.unreadable if persistent else native.fail_once
    failures.add(bad.containment_job_name)
    evidence = await stop_owned_processes(
        registry=registry,
        native=native,
        shutdown=ShutdownState(),
        graceful_exit_ns=0,
        terminate_exit_ns=0,
    )
    assert (2, 102) in native.terminated
    assert evidence.unconfirmed_jobs == (
        frozenset({bad.containment_job_name}) if persistent else frozenset()
    )
    assert not evidence.remaining


async def test_process_exit_uses_original_outer_deadline(
    exit_clock: _ExitClock,
) -> None:
    native = _ExitNative()
    registry = LaunchRegistry(native, 15_000_000_000)
    for role, pid in [("visual_stimulus", 1), ("controller", 2)]:
        _launch(
            registry, native, _identity("supervisor"), _identity(role), pid, python=True
        )
    native.stuck.update({(1, 101), (2, 102)})
    original_deadline = exit_clock.now + 100_000_000
    shutdown = ShutdownState(shutdown_deadline_ns=original_deadline)
    evidence = await stop_owned_processes(
        registry=registry,
        native=native,
        shutdown=shutdown,
        graceful_exit_ns=5_000_000_000,
        terminate_exit_ns=2_000_000_000,
    )
    assert exit_clock.now == original_deadline
    assert shutdown.shutdown_deadline_ns == original_deadline
    assert native.terminated == [(1, 101), (2, 102)]
    assert len(evidence.remaining) == 2


@pytest.mark.parametrize("blocker", ["none", "process", "inspection", "cleanup"])
async def test_shutdown_completion_keeps_exit_and_cleanup_evidence_distinct(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    blocker: str,
) -> None:
    runtime, _, _, _ = make_runtime(tmp_path)
    command_id = str(uuid4())
    runtime.shutdown_state.shutdown_request = wire.ApplicationShutdownRequest(
        command_id=command_id
    ).SerializeToString()
    operation = types.OperationState(
        context=types.OperationContext(command_id=command_id)
    )
    runtime.recovery_state.operations[command_id] = operation

    async def exits(**kwargs: object) -> ProcessExitEvidence:
        assert kwargs["shutdown"] is runtime.shutdown_state
        return ProcessExitEvidence(
            ((1, 101, EXE),) if blocker == "process" else (),
            frozenset({"job"}) if blocker == "inspection" else frozenset(),
        )

    monkeypatch.setattr("cephvr.supervisor.shutdown.stop_owned_processes", exits)
    monkeypatch.setattr(
        runtime.recovery,
        "cleanup_blockers",
        lambda: [types.CleanupBlocker()] if blocker == "cleanup" else [],
    )
    await runtime.shutdown.shutdown_owned()
    assert operation.complete
    assert operation.succeeded is (blocker == "none")
    assert runtime.shutdown_state.shutdown_complete.is_set() is (
        blocker in {"none", "cleanup"}
    )
    if blocker != "none":
        assert operation.failure.code == "SHUTDOWN_UNCONFIRMED"
