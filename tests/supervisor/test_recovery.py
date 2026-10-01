"""Prior-exit receipts and evidence-driven native helper reconciliation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.clock import host_time_ns
from cephvr.shared.recovery import ApplicationExitReceipt, RecoveryStore
from cephvr.supervisor.acquisition_worker import AcquisitionWorkerControl
from tests.supervisor.support import Outbound, make_runtime

from .support import (
    WORK,
    _phase,
    _worker_and_helper,
)


async def test_concurrent_reconciles_are_serialized(tmp_path: Path) -> None:
    runtime, native, outbound, _ = make_runtime(tmp_path)
    _worker_and_helper(runtime, native)
    active = 0
    peak = 0

    async def slow_state(launch, request, *, deadline_ns):  # type: ignore[no-untyped-def]
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return acq.WorkerState()

    outbound.get_worker_state = slow_state  # type: ignore[method-assign]
    reconciler = runtime.shutdown.acquisition_worker_control
    deadline = host_time_ns() + 5_000_000_000
    await asyncio.gather(
        reconciler.reconcile_native_helper_exits(deadline),
        reconciler.reconcile_native_helper_exits(deadline),
    )
    assert peak == 1


async def test_owner_cleanup_required_releases_empty_helper_as_unconfirmed(
    tmp_path: Path,
) -> None:
    runtime, native, outbound, _ = make_runtime(tmp_path)
    worker, helper = _worker_and_helper(runtime, native)
    native.jobs[worker.containment_job_name] = []  # owner exited
    assert _phase(runtime, worker) == wire.LAUNCH_PHASE_CLEANUP_REQUIRED
    deadline = host_time_ns() + 5_000_000_000
    reconciler = runtime.shutdown.acquisition_worker_control
    # Helper process still running: not released, not recorded as an error.
    assert await reconciler.reconcile_native_helper_exits(deadline) == []
    assert _phase(runtime, helper) == wire.LAUNCH_PHASE_OPERATIONAL
    native.jobs[helper.containment_job_name] = []
    messages = await reconciler.reconcile_native_helper_exits(deadline)
    assert len(messages) == 1
    assert f"ffmpeg:{helper.plan.command_id}" in messages[0]
    assert _phase(runtime, helper) == wire.LAUNCH_PHASE_RELEASED


async def test_unreachable_live_owner_records_error_and_keeps_helper(
    tmp_path: Path,
) -> None:
    runtime, native, outbound, _ = make_runtime(tmp_path)
    worker, helper = _worker_and_helper(runtime, native)
    native.jobs[helper.containment_job_name] = []

    async def down(launch, request, *, deadline_ns):  # type: ignore[no-untyped-def]
        raise ConnectionError("worker down")

    outbound.get_worker_state = down  # type: ignore[method-assign]
    reconciler = runtime.shutdown.acquisition_worker_control
    assert (
        await reconciler.reconcile_native_helper_exits(host_time_ns() + 5_000_000_000)
        == []
    )
    assert "GetState" in reconciler.helper_errors[helper.plan.command_id]
    assert _phase(runtime, helper) == wire.LAUNCH_PHASE_OPERATIONAL


def _closure_evidence(
    worker: wire.LaunchState, helper: wire.LaunchState, output: types.OutputResult
) -> list[acq.WorkerLifecycleEvidence]:
    source = acq.WorkerContext(
        worker=worker.plan.child,
        owner=worker.plan.owner,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
        work=helper.plan.work,
    )
    finished = acq.WorkerLifecycleEvidence(source=source, state_revision=1)
    finished.operation.command_id = str(uuid4())
    finished.finished.activity_stopped = True
    finished.finished.outputs.add().CopyFrom(output)
    cleanup = acq.WorkerLifecycleEvidence(source=source, state_revision=2)
    cleanup.operation.command_id = str(uuid4())
    cleanup.cleanup.resources.add(
        resource=f"ffmpeg:{helper.plan.command_id}", released=True
    )
    cleanup.cleanup.outputs.add().CopyFrom(output)
    return [finished, cleanup]


@pytest.mark.parametrize(
    ("closure", "released"),
    [
        (types.OUTPUT_CLOSURE_NOT_STARTED, True),
        (types.OUTPUT_CLOSURE_CLOSED, True),
        (types.OUTPUT_CLOSURE_UNCONFIRMED, False),
    ],
)
async def test_helper_release_uses_shared_output_discharge(
    tmp_path: Path, closure: int, released: bool
) -> None:
    runtime, native, outbound, _ = make_runtime(tmp_path)
    worker, helper = _worker_and_helper(runtime, native)
    native.jobs[helper.containment_job_name] = []
    output = types.OutputResult(output_key="behavioral.camera", closure=closure)
    if closure == types.OUTPUT_CLOSURE_NOT_STARTED:
        output.artifact_present = False
    else:
        output.artifact_present = True
    evidence = _closure_evidence(worker, helper, output)

    async def state(launch, request, *, deadline_ns):  # type: ignore[no-untyped-def]
        return acq.WorkerState(lifecycle=evidence)

    async def retained(launch, request, *, deadline_ns):  # type: ignore[no-untyped-def]
        found = [
            item for item in evidence if item.operation.command_id == request.command_id
        ]
        return acq.WorkerRetainedResult(
            found=True, source=request.query.target, lifecycle=found
        )

    outbound.get_worker_state = state  # type: ignore[method-assign]
    outbound.get_worker_retained_result = retained  # type: ignore[method-assign]
    messages = (
        await runtime.shutdown.acquisition_worker_control.reconcile_native_helper_exits(
            host_time_ns() + 5_000_000_000
        )
    )
    assert messages == []  # confirmed evidence is never an unconfirmed release
    expected = wire.LAUNCH_PHASE_RELEASED if released else wire.LAUNCH_PHASE_OPERATIONAL
    assert _phase(runtime, helper) == expected


async def test_cleanup_reconcile_incomplete_retained_result_raises(
    tmp_path: Path,
) -> None:
    runtime, native, _, _ = make_runtime(tmp_path)
    worker, _ = _worker_and_helper(runtime, native)
    target = acq.WorkerContext(
        worker=worker.plan.child,
        owner=worker.plan.owner,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
        work=WORK,
    )
    cleanup = AcquisitionWorkerControl(
        registration=runtime.registration,
        registry=runtime.registry,
        outbound=Outbound(),
        issuer=runtime.identity,
        interrupt_commands={},
        cleanup_commands={},
    )
    with pytest.raises(RuntimeError, match="not retained"):
        await cleanup.cleanup_worker(worker, target, host_time_ns() + 5_000_000_000)


async def test_prior_application_exit_requires_exact_private_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, _, _, caller = make_runtime(tmp_path)
    runtime_root = tmp_path / "runtime"
    monkeypatch.setattr(
        "cephvr.supervisor.recovery.default_runtime_root", lambda: runtime_root
    )
    previous_controller = str(uuid4())
    previous_supervisor = str(uuid4())
    query = wire.RecoveryQuery(
        expected_supervisor=runtime.identity,
        prior_controller_generation=previous_controller,
    )
    missing = await runtime.service.GetRecoveryState(query, caller)
    assert not missing.HasField("prior_application_exit")
    RecoveryStore(runtime_root).write_exit_receipt(
        ApplicationExitReceipt(
            controller_generation=previous_controller,
            supervisor_generation=previous_supervisor,
            observed_monotonic_ns=host_time_ns(),
            all_owned_processes_absent=True,
        )
    )
    verified = await runtime.service.GetRecoveryState(query, caller)
    assert verified.prior_application_exit.controller_generation == previous_controller
    assert verified.prior_application_exit.supervisor_generation == previous_supervisor
    assert verified.prior_application_exit.all_owned_processes_absent
    assert verified.prior_application_exit.format_version == 1
    other = wire.RecoveryQuery(
        expected_supervisor=runtime.identity,
        prior_controller_generation=str(uuid4()),
    )
    assert not (await runtime.service.GetRecoveryState(other, caller)).HasField(
        "prior_application_exit"
    )
