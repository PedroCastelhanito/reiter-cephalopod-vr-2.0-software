"""Late device and lifecycle evidence retain original admission boundaries."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from typing import cast

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.ports import BackendPort
from cephvr.controller.state import CameraOperation
from tests.controller.support_components import (
    _attempt,
    _id,
    _RetainedPeer,
    _runtime,
    bind_ledger,
)


async def test_late_camera_completion_reconciles_blocker_without_reviving_success(
    tmp_path: Path,
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _runtime(tmp_path, backend)
    bind_ledger(runtime)
    parent, child = _id(), _id()
    runtime.control_operations.operation(parent, "ExecuteCameraCommand")
    operation = CameraOperation(
        parent,
        child,
        1,
        1,
        svc.CAMERA_COMMAND_KIND_START_PREVIEW,
        pb.WorkContext(),
        999,
        False,
    )
    runtime.camera.status_retention.reserve(operation)
    runtime.device_state.camera_operation = operation

    await runtime.camera._camera_timeout(child, 999)
    # No terminal report and no retained result: the slot is freed unconfirmed.
    assert runtime.device_state.camera_operation is None
    assert runtime.control.operations[parent].complete
    assert not runtime.control.operations[parent].succeeded

    status = svc.AcquisitionDeviceStatusReport()
    status.views.source.CopyFrom(backend)
    status.views.state_revision = 1
    status.views.observed_monotonic_ns = 1_000
    status.views.behavioral.preview_running = True
    status.views.behavioral.preview_run_id = _id()
    status.views.behavioral.device_open = True
    status.operation.command_id = child
    status.result.context.command_id = child
    status.result.complete = True
    status.result.succeeded = True
    receipt = await runtime.report_projection("devices", status, ingress_ns=1_000)

    assert receipt.result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime.device_state.camera_operation is None
    assert runtime.control.operations[parent].complete
    assert not runtime.control.operations[parent].succeeded
    assert runtime.projections.devices is not None
    assert runtime.projections.devices.behavioral.preview_running


async def test_ready_recovery_queries_frozen_missing_peer_once_without_accepting_ungated_push(
    tmp_path: Path,
) -> None:
    context = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _runtime(tmp_path, context)
    runtime.clock = time.monotonic_ns
    runtime.evidence_waiter.clock = runtime.clock
    runtime.limit_state.current = replace(runtime.limits, recovery_ns=200_000_000)
    attempt = _attempt(runtime, tmp_path, {})
    command_id = _id()
    attempt.setup_operations["acquisition"] = command_id
    attempt.setup_deadline_ns = runtime.clock() - 1_000_000
    ready = pb.ReadyReport(configuration_revision=1, required_checks_passed=True)
    ready.context.backend.CopyFrom(context)
    ready.context.work.session.CopyFrom(attempt.context)
    ready.context.operation.command_id = command_id
    retained = svc.RetainedResult(
        found=True,
        backend=context,
        work=pb.WorkContext(session=attempt.context),
        ready=ready,
    )
    peer = _RetainedPeer(context, retained)
    attempt.required["acquisition"] = cast(BackendPort, peer)
    runtime.lifecycle.attempt = attempt
    runtime.lifecycle.session = pb.SessionState(
        phase=pb.SESSION_PHASE_SETTING_UP, context=attempt.context
    )

    late_push = await runtime.report_lifecycle(
        pb.LifecycleReport(ready=ready), runtime.clock()
    )
    assert late_push.result == pb.COMMAND_RESULT_REJECTED
    assert not attempt.ready

    recovered = await runtime.evidence_waiter.wait_lifecycle_with_recovery(
        attempt, "setup_ready", frozenset({"acquisition"}), attempt.setup_deadline_ns
    )
    assert recovered
    assert len(peer.queries) == 1
    assert peer.queries[0].command_id == command_id
    assert attempt.ready["acquisition"] == ready
    post_recovery_push = await runtime.report_lifecycle(
        pb.LifecycleReport(ready=ready), runtime.clock()
    )
    assert post_recovery_push.result == pb.COMMAND_RESULT_REJECTED


async def test_finished_recovery_keeps_exact_trial_identity_and_original_cutoff(
    tmp_path: Path,
) -> None:
    context = pb.BackendContext(backend_name="tracking", backend_generation=_id())
    runtime = _runtime(tmp_path, context)
    runtime.clock = time.monotonic_ns
    runtime.evidence_waiter.clock = runtime.clock
    runtime.limit_state.current = replace(runtime.limits, recovery_ns=200_000_000)
    attempt = _attempt(runtime, tmp_path, {})
    trial = pb.TrialContext(session=attempt.context, trial_id=_id(), trial_number=1)
    attempt.prepared.trials.add(context=trial)
    attempt.trial_index = 0
    attempt.trial_operation = _id()
    attempt.target_ns = runtime.clock() - 10_000_000
    attempt.end_ns = runtime.clock() - 2_000_000
    attempt.finished_deadline_ns = runtime.clock() - 1_000_000
    finished = pb.FinishedReport(trial_activity_stopped=True)
    finished.context.backend.CopyFrom(context)
    finished.context.work.trial.CopyFrom(trial)
    finished.context.operation.command_id = attempt.trial_operation
    retained = svc.RetainedResult(
        found=True, backend=context, work=pb.WorkContext(trial=trial), finished=finished
    )
    peer = _RetainedPeer(context, retained)
    attempt.required["tracking"] = cast(BackendPort, peer)
    attempt.trial_participants["tracking"] = cast(BackendPort, peer)
    runtime.lifecycle.attempt = attempt
    runtime.lifecycle.session = pb.SessionState(
        phase=pb.SESSION_PHASE_RUNNING, context=attempt.context
    )
    runtime.lifecycle.trial = pb.TrialState(
        phase=pb.TRIAL_PHASE_FINALIZING, context=trial
    )

    late_push = await runtime.report_lifecycle(
        pb.LifecycleReport(finished=finished), runtime.clock()
    )
    assert late_push.result == pb.COMMAND_RESULT_REJECTED
    recovered = await runtime.evidence_waiter.wait_lifecycle_with_recovery(
        attempt, "finished", frozenset({"tracking"}), attempt.finished_deadline_ns
    )
    assert recovered
    assert len(peer.queries) == 1
    assert peer.queries[0].query.work.trial == trial
    assert attempt.finished["tracking"] == finished
    post_recovery_push = await runtime.report_lifecycle(
        pb.LifecycleReport(finished=finished), runtime.clock()
    )
    assert post_recovery_push.result == pb.COMMAND_RESULT_REJECTED
