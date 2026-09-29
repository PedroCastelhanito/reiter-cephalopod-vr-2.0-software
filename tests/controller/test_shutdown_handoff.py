"""E08 shutdown keeps the first intent's launcher deadline and owned handles."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from cephvr.control.v1 import services_pb2_grpc as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller import main
from cephvr.controller.configuration import SupervisorStartup
from cephvr.controller.runtime import ControllerRuntime
from cephvr.platform.windows.jobs import WindowsJobs
from cephvr.shared.auth import Principal


class _Clock:
    def __init__(self, now: int = 1_000) -> None:
        self.now = now

    def __call__(self) -> int:
        return self.now


class _Runtime:
    def __init__(self, clock: _Clock, *, handoff_complete: bool) -> None:
        self.generation = str(uuid4())
        self.supervisor_generation = str(uuid4())
        self.clock = clock
        self._shutdown_intent_ns = clock.now
        self._supervisor_last_seen_ns = clock.now
        self._operations = {
            str(uuid4()): pb.OperationState(
                command="ShutdownApplication", complete=handoff_complete
            )
        }
        self.session = pb.SessionState(
            phase=pb.SESSION_PHASE_CONFIGURATION, cleanup_confirmed=True
        )
        self.attempt = None
        self._lock = asyncio.Lock()
        self._warnings: list[pb.Warning] = []

    def _publish(self) -> None:
        pass


class _Native:
    def __init__(self) -> None:
        self.terminated: list[tuple[int, int]] = []

    def process_running(self, pid: int, created: int) -> bool:
        return True

    def terminate_exact(self, pid: int, created: int) -> None:
        self.terminated.append((pid, created))


def _startup() -> SupervisorStartup:
    return SupervisorStartup(
        port=50052,
        heartbeat_interval_ns=10_000_000_000,
        silence_timeout_ns=10_000_000_000,
        emergency_timeout_ns=1_000,
        graceful_exit_ns=100,
        terminate_exit_ns=100,
        application_backstop_ns=500,
    )


async def _run(runtime: _Runtime, native: _Native, path: Path) -> None:
    await main._authority_loop(
        cast(ControllerRuntime, runtime),
        cast(rpc.SupervisorServiceStub, object()),
        Principal("controller", runtime.generation, "test-token"),
        supervisor_pid=41,
        supervisor_creation=100,
        startup=_startup(),
        native=cast(WindowsJobs, native),
        managed_jobs=(),
        backends={},
        launcher_descriptor=1,
        software_root=path,
    )


@pytest.mark.asyncio
async def test_shutdown_notifies_launcher_with_original_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _Clock()
    runtime = _Runtime(clock, handoff_complete=True)
    native = _Native()
    notices: list[tuple[int, str]] = []

    async def notify(_descriptor: int, **kwargs: object) -> None:
        notices.append((cast(int, kwargs["deadline_ns"]), cast(str, kwargs["cause"])))

    monkeypatch.setattr(main, "notify_launcher", notify)
    await asyncio.wait_for(_run(runtime, native, tmp_path), timeout=1)
    assert notices == [(1_500, "OPERATOR_SHUTDOWN")]
    assert native.terminated == []


@pytest.mark.asyncio
async def test_clean_controller_waits_for_shutdown_handoff_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _Clock()
    runtime = _Runtime(clock, handoff_complete=False)
    native = _Native()
    notified = asyncio.Event()

    async def notify(_descriptor: int, **_kwargs: object) -> None:
        notified.set()

    monkeypatch.setattr(main, "notify_launcher", notify)
    task = asyncio.create_task(_run(runtime, native, tmp_path))
    try:
        await asyncio.wait_for(notified.wait(), timeout=1)
        await asyncio.sleep(0)
        assert not task.done()
        next(iter(runtime._operations.values())).complete = True
        await asyncio.wait_for(task, timeout=1)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert native.terminated == []


@pytest.mark.asyncio
async def test_failed_launcher_delivery_uses_first_deadline_for_exact_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _Clock()
    runtime = _Runtime(clock, handoff_complete=True)
    native = _Native()
    attempted = asyncio.Event()
    deadlines: list[int] = []

    async def fail_notify(_descriptor: int, **kwargs: object) -> None:
        assert kwargs["deadline_ns"] == 1_500
        attempted.set()
        raise OSError("pipe unavailable")

    async def shutdown_jobs(
        _native: object, _jobs: object, **kwargs: object
    ) -> tuple[str, ...]:
        deadlines.append(cast(int, kwargs["absolute_deadline_ns"]))
        return ()

    monkeypatch.setattr(main, "notify_launcher", fail_notify)
    monkeypatch.setattr(main, "shutdown_owned_jobs", shutdown_jobs)
    task = asyncio.create_task(_run(runtime, native, tmp_path))
    try:
        await asyncio.wait_for(attempted.wait(), timeout=1)
        await asyncio.sleep(0)
        assert not task.done()
        clock.now = 1_500
        await asyncio.wait_for(task, timeout=1)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert deadlines == [1_500]
    assert native.terminated == [(41, 100)]
    assert len(runtime._warnings) == 1
