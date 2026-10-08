"""Protected Windows acquisition worker entrypoint (A02/E08)."""

from __future__ import annotations

import argparse
import asyncio
import sys

import grpc

from cephvr.acquisition.camera.basler import BaslerCameraAdapter
from cephvr.acquisition.recording.encoder import SupervisedEncoderLauncher
from cephvr.acquisition.worker.limits import AcquisitionControlLimits
from cephvr.acquisition.worker.recording_runtime import WorkerRecordingRuntime
from cephvr.acquisition.worker.recording_thread import RecordingOwnerThread
from cephvr.control.v1 import services_pb2_grpc as control_rpc
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.bootstrap import read_bootstrap
from cephvr.platform.windows.file_sync import (
    WindowsFileSyncOwner,
    WindowsVideoSyncFactory,
)
from cephvr.platform.windows.jobs import WindowsJobs
from cephvr.platform.windows.nvenc_capabilities import NvencProbeOwner
from cephvr.shared.auth import Principal
from cephvr.shared.clock import host_time_ns
from cephvr.shared.transport_deadlines import remaining_seconds

from .bootstrap import decode_worker_bootstrap
from .capture_runtime import WorkerCaptureResources
from .execution import WorkerOperationExecutor
from .owner import SerializedCameraOwner
from .registration import SupervisorEndpointRegistration
from .reports import CoordinatorReportClient, SupervisorErrorClient
from .server import serve_registered_worker
from .state import WorkerState


def main() -> int:
    args = _arguments()
    if sys.platform != "win32":
        raise RuntimeError("acquisition camera workers require Windows")
    document = read_bootstrap(args.bootstrap_handle)
    bootstrap = decode_worker_bootstrap(document)
    limits = AcquisitionControlLimits.from_message_limit(bootstrap.max_message_bytes)
    state = WorkerState.create(
        bootstrap,
        retention_ns=bootstrap.control_policies.command_retention_after_finalization_ns,
        limits=limits,
    )
    asyncio.run(_serve(bootstrap, state, limits))
    return 0


async def _serve(
    bootstrap: object, state: WorkerState, limits: AcquisitionControlLimits
) -> None:
    # The typed bootstrap is validated before reaching this internal entry point.
    from .state import WorkerBootstrap

    if not isinstance(bootstrap, WorkerBootstrap):
        raise TypeError("worker bootstrap was not validated")
    loop = asyncio.get_running_loop()
    shutdown_requested = asyncio.Event()
    deadline_value: list[int | None] = [None]
    adapter = BaslerCameraAdapter()  # Native control event only; no SDK import/open.
    supervisor_channel = grpc.insecure_channel(
        bootstrap.supervisor_endpoint,
        options=(
            ("grpc.max_send_message_length", limits.max_message_bytes),
            ("grpc.max_receive_message_length", limits.max_message_bytes),
        ),
    )
    supervisor_stub = control_rpc.SupervisorServiceStub(  # type: ignore[no-untyped-call]
        supervisor_channel
    )
    file_sync_owner = WindowsFileSyncOwner()
    worker_principal = Principal(
        bootstrap.context.worker.role,
        bootstrap.context.worker.generation,
        bootstrap.worker_credential,
    )
    launcher = SupervisedEncoderLauncher(
        supervisor=supervisor_stub,
        owner=worker_principal,
        owner_identity=bootstrap.context.worker,
        windows_jobs=WindowsJobs(),
        file_sync_owner=file_sync_owner,
    )
    recording = WorkerRecordingRuntime(
        worker=bootstrap.context,
        file_sync_owner=file_sync_owner,
        video_sync_factory=WindowsVideoSyncFactory(file_sync_owner),
        launcher=launcher,
        writer=RecordingOwnerThread(limits.max_records),
        nvenc=NvencProbeOwner(),
        trial_finished_allowance_ns=(
            bootstrap.control_policies.trial_finished.initial_ns
        ),
    )
    captures = WorkerCaptureResources(
        adapter,
        bootstrap.context,
        warning_occurrence=lambda occurrence: (
            executor_holder[0].warning_occurrence(occurrence)
            if executor_holder
            else _record_warning(state, occurrence)
        ),
    )
    reports = CoordinatorReportClient(
        bootstrap.coordinator_endpoint,
        Principal(
            bootstrap.context.worker.role,
            bootstrap.context.worker.generation,
            bootstrap.worker_credential,
        ),
        limits.max_message_bytes,
    )
    supervisor_errors = SupervisorErrorClient(
        bootstrap.supervisor_endpoint,
        Principal(
            bootstrap.context.worker.role,
            bootstrap.context.worker.generation,
            bootstrap.worker_credential,
        ),
        limits.max_message_bytes,
    )
    owner_holder: list[SerializedCameraOwner] = []
    executor_holder: list[WorkerOperationExecutor] = []
    executor = WorkerOperationExecutor(
        bootstrap,
        state,
        adapter,
        captures,
        reports,
        loop,
        shutdown_requested,
        lambda deadline: deadline_value.__setitem__(0, deadline),
        recording,
        lambda: owner_holder[0].external_wake() if owner_holder else None,
        supervisor_errors,
    )
    executor_holder.append(executor)
    captures.set_first_trial_frame_callback(executor.camera_first_frame)
    owner = SerializedCameraOwner(
        capacity=limits.max_records - limits.safety_reserve_records,
        safety_capacity=limits.safety_reserve_records,
        execute=executor.execute,
        capture_once=captures.capture_once,
        capture_active=lambda: captures.active,
        next_deadline_ns=executor.next_deadline_ns,
        advance_due_stages=executor.advance_due_stages,
        wait_control=lambda timeout: _wait_control(adapter, timeout),
        wake_control=adapter.wake_control,
        clear_control=adapter.clear_control_wake,
        operation_failed=executor.failed,
        owner_failed=executor.owner_failed,
        idle_maintenance_interval_ns=bootstrap.heartbeat_interval_ns,
    )
    owner_holder.append(owner)
    captures.set_capture_handoff(owner.capture_handoff)
    registration = SupervisorEndpointRegistration(bootstrap)
    health_task = asyncio.create_task(
        _health_loop(bootstrap, state, reports, executor),
        name="cephvr-acquisition-worker-health",
    )

    def supervise_health_task(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        failure = task.exception()
        if failure is not None:
            executor.coordinator_lost(details=f"heartbeat loop failed: {failure}")
            executor.owner_failed(failure)

    health_task.add_done_callback(supervise_health_task)
    try:
        await serve_registered_worker(
            "127.0.0.1:0",
            state,
            owner,
            {
                bootstrap.context.owner.role: (
                    bootstrap.context.owner.generation,
                    bootstrap.owner_credential,
                ),
                bootstrap.supervisor.role: (
                    bootstrap.supervisor.generation,
                    bootstrap.supervisor_credential,
                ),
            },
            registration,
            max_message_bytes=limits.max_message_bytes,
            max_concurrent_rpcs=limits.max_records,
            teardown_budget_ns=bootstrap.control_policies.recovery_ns,
            shutdown_requested=shutdown_requested,
            shutdown_deadline_ns=lambda: deadline_value[0],
        )
    finally:
        health_task.cancel()
        await asyncio.gather(health_task, return_exceptions=True)
        await registration.close()
        teardown_deadline = deadline_value[0]
        if teardown_deadline is None:
            teardown_deadline = host_time_ns() + bootstrap.control_policies.recovery_ns
        recording_closed = await asyncio.to_thread(
            recording.close,
            remaining_seconds(teardown_deadline),
        )
        if not recording_closed:
            raise RuntimeError("recording thread resources remain unreconciled")
        reports_drained = await executor.report_dispatcher.drain(teardown_deadline)
        supervisor_channel.close()
        await reports.close()
        await supervisor_errors.close()
        # Device release is serialized before shutdown. The control event remains
        # alive until the owner has joined so its final wake cannot target a closed
        # native handle.
        if owner.stopped:
            adapter.close_control()
        if not reports_drained:
            raise RuntimeError(
                "worker report tasks remain unresolved at teardown deadline"
            )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="cephvr-acquisition-worker")
    parser.add_argument("--bootstrap-handle", type=int, required=True)
    return parser.parse_args()


def _record_warning(state: WorkerState, occurrence: object) -> None:
    from .warnings import WarningOccurrence

    if not isinstance(occurrence, WarningOccurrence) or state.warnings is None:
        return
    state.warnings.observe(occurrence)


def _wait_control(adapter: BaslerCameraAdapter, timeout_ns: int) -> None:
    adapter.wait_for_control(timeout_ns)


async def _health_loop(
    bootstrap: object,
    state: WorkerState,
    reports: CoordinatorReportClient,
    executor: WorkerOperationExecutor,
) -> None:
    from .state import WorkerBootstrap

    if not isinstance(bootstrap, WorkerBootstrap):
        raise TypeError("worker health loop requires a validated bootstrap")
    interval_s = bootstrap.heartbeat_interval_ns / 1_000_000_000
    last_accepted_ns = host_time_ns()
    while True:
        await asyncio.sleep(interval_s)
        with state.lock:
            if not state.registered:
                continue
        sent_ns = host_time_ns()
        deadline_ns = min(
            sent_ns + bootstrap.heartbeat_interval_ns,
            last_accepted_ns + bootstrap.health_silence_ns,
        )
        report = state.heartbeat_report(
            sent_ns, health_silence_ns=bootstrap.health_silence_ns
        )
        try:
            receipt = await reports.report_heartbeat(report, deadline_ns=deadline_ns)
            if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                executor.coordinator_lost(
                    details=f"heartbeat rejected: {receipt.failure.code}: "
                    f"{receipt.failure.message}"
                )
                return
            last_accepted_ns = host_time_ns()
            executor.flush_warnings(deadline_ns)
        except Exception as exc:
            if host_time_ns() - last_accepted_ns >= bootstrap.health_silence_ns:
                executor.coordinator_lost(details=f"heartbeat receipt failed: {exc}")
                return
            continue


if __name__ == "__main__":
    raise SystemExit(main())
