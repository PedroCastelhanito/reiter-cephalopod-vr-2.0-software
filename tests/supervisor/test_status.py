"""Status retry ordering, released-process views and warning replacement."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from cephvr.control.v1 import services_pb2 as wire
from tests.supervisor.support import make_runtime

from .support import (
    _worker_and_helper,
)


async def test_failed_status_send_is_resent_on_heartbeat_tick(tmp_path: Path) -> None:
    runtime, _, outbound, _ = make_runtime(tmp_path)
    outbound.fail_status_once = True
    runtime.status.changed()
    await runtime.status_state.status_task
    assert runtime.status_state.acknowledged_revision == 0
    runtime.health.heartbeat_interval_ns = 1_000_000
    loop = asyncio.create_task(runtime.heartbeat_loop())
    await asyncio.sleep(0.05)
    loop.cancel()
    await asyncio.gather(loop, return_exceptions=True)
    assert runtime.status_state.acknowledged_revision == 1
    assert outbound.statuses[-1].status_revision == 1


async def test_change_during_failing_send_is_not_lost(tmp_path: Path) -> None:
    runtime, _, outbound, _ = make_runtime(tmp_path)
    gate = asyncio.Event()
    sent: list[int] = []

    async def report_status(report: wire.SupervisorStatusReport) -> None:
        sent.append(report.status_revision)
        if len(sent) == 1:
            await gate.wait()
            raise ConnectionError("down")

    outbound.report_status = report_status  # type: ignore[method-assign]
    runtime.status.changed()
    await asyncio.sleep(0)
    runtime.status.changed()  # in flight: no new task
    gate.set()
    await runtime.status_state.status_task
    assert sent == [1, 2]
    assert runtime.status_state.acknowledged_revision == 2


async def test_status_never_probes_a_released_helper_pid(tmp_path: Path) -> None:
    runtime, native, _, _ = make_runtime(tmp_path)
    _, helper = _worker_and_helper(runtime, native)
    native.jobs[helper.containment_job_name] = []
    runtime.registry.release(helper.plan.command_id, obligations_met=True)
    probe = native.process_running

    def reused_pid_guard(pid: int, creation_time_100ns: int) -> bool:
        if pid == helper.pid:
            raise RuntimeError("PID creation time differs")  # reused PID on Windows
        return probe(pid, creation_time_100ns)

    native.process_running = reused_pid_guard  # type: ignore[method-assign]
    runtime.status.changed()
    await runtime.status_state.status_task
    assert runtime.shutdown_state.interruption is None


async def test_repeated_task_failure_replaces_its_warning(tmp_path: Path) -> None:
    runtime, _, _, _ = make_runtime(tmp_path)
    for attempt in range(300):  # beyond the warning capacity
        runtime.tasks.report_failure("helper reconcile", RuntimeError(str(attempt)))
    warnings = list(runtime.status_state.warnings.values())
    assert len(warnings) == 1 and "299" in warnings[0].message
    assert runtime.shutdown_state.interruption is None


async def test_status_retry_preserves_revision_and_timestamp(tmp_path: Path) -> None:
    runtime, _, outbound, _ = make_runtime(tmp_path)
    outbound.fail_status_once = True
    runtime.status.changed()
    assert runtime.status_state.status_task is not None
    await runtime.status_state.status_task
    assert runtime.status_state.pending_status is not None
    await runtime.status.send_status()
    assert len(outbound.statuses) == 2
    assert outbound.statuses[0] == outbound.statuses[1]
    assert runtime.status_state.pending_status is None


async def test_supervisor_heartbeat_does_not_depend_on_status_change(
    tmp_path: Path,
) -> None:
    runtime, _, outbound, _ = make_runtime(tmp_path)
    runtime.health.heartbeat_interval_ns = 1_000_000
    loop = asyncio.create_task(runtime.heartbeat_loop())
    await asyncio.sleep(0.01)
    loop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loop
    assert len(outbound.heartbeats) >= 2
    assert runtime.status_state.revision == 0
