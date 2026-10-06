"""Windows acquisition coordinator entry point and concrete process assembly."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import grpc

from cephvr.acquisition.buffers.resource_port import WindowsResourcePort
from cephvr.acquisition.configuration import load_defaults, load_file_policies
from cephvr.acquisition.coordinator.workers import WorkerRegistry
from cephvr.acquisition.executables import PythonWorkerExecutables
from cephvr.acquisition.microcontroller.lazy_owner import LazySerialOwner
from cephvr.acquisition.runtime import AcquisitionCoordinatorRuntime
from cephvr.acquisition.startup import (
    AcquisitionBootstrap,
    decode_acquisition_bootstrap,
)
from cephvr.acquisition.state import (
    ConfigurationRecord,
    CoordinatorIdentity,
    WorkerRecord,
)
from cephvr.acquisition.transport.grpc_ports import (
    GrpcControllerPort,
    GrpcSupervisorPort,
)
from cephvr.acquisition.transport.server import (
    AcquisitionServer,
    start_acquisition_server,
)
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.worker_launcher import WindowsWorkerBootstrapPort
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.bootstrap import read_bootstrap
from cephvr.platform.windows.guard import SingleInstanceGuard
from cephvr.platform.windows.jobs import WindowsJobs
from cephvr.platform.windows.python_runtime import resolve_python_executable
from cephvr.platform.windows.resource_ledger import NativeResourceLedger
from cephvr.shared.auth import Principal
from cephvr.shared.backend_registration import register_backend_endpoint
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger


async def run_acquisition(bootstrap: AcquisitionBootstrap) -> None:
    if sys.platform != "win32":
        raise RuntimeError("managed acquisition requires Windows")
    root = bootstrap.software_root
    settings = load_defaults(root)
    file_policies = load_file_policies(root)
    configuration = ConfigurationRecord(settings, file_policies)
    identity = CoordinatorIdentity(
        backend=control.BackendContext(
            backend_name="acquisition", backend_generation=bootstrap.identity.generation
        ),
        process=bootstrap.identity,
        controller=bootstrap.controller,
        supervisor=bootstrap.supervisor,
        tracking=bootstrap.tracking,
    )
    credentials: dict[tuple[str, str], str] = {
        (
            bootstrap.controller.role,
            bootstrap.controller.generation,
        ): bootstrap.controller_token,
        (
            bootstrap.supervisor.role,
            bootstrap.supervisor.generation,
        ): bootstrap.supervisor_token,
    }
    principal = Principal(
        bootstrap.identity.role, bootstrap.identity.generation, bootstrap.token
    )
    options = (
        ("grpc.max_send_message_length", bootstrap.max_message_bytes),
        ("grpc.max_receive_message_length", bootstrap.max_message_bytes),
    )
    controller_channel = grpc.aio.insecure_channel(
        f"127.0.0.1:{bootstrap.controller_port}", options=options
    )
    supervisor_channel = grpc.aio.insecure_channel(
        f"127.0.0.1:{bootstrap.supervisor_port}", options=options
    )
    controller = GrpcControllerPort(controller_channel, principal)
    supervisor = GrpcSupervisorPort(supervisor_channel, principal)
    native = WindowsJobs()
    resource_port = WindowsResourcePort()
    resource_ledger = NativeResourceLedger(
        max_resources=64, max_transfers_per_resource=8
    )
    commands = CommandLedger(
        bootstrap.identity.generation,
        bootstrap.policies.command_retention_after_finalization_ns,
        max_records=1024,
        max_bytes=max(64 * 1024 * 1024, 4 * bootstrap.max_message_bytes),
        result_reservation_bytes=64 * 1024,
        safety_reserve_records=16,
        safety_reserve_bytes=2 * 1024 * 1024,
    )
    endpoint = f"127.0.0.1:{bootstrap.endpoint_port}"
    bootstrap_port = WindowsWorkerBootstrapPort(
        native=native,
        supervisor=supervisor,
        owner=bootstrap.identity,
        owner_token=bootstrap.token,
        supervisor_identity=bootstrap.supervisor,
        supervisor_token=bootstrap.supervisor_token,
        supervisor_endpoint=f"127.0.0.1:{bootstrap.supervisor_port}",
        coordinator_endpoint=endpoint,
        python_executable=resolve_python_executable(Path(sys.executable)),
        max_message_bytes=bootstrap.max_message_bytes,
        register_peer=lambda process, token: credentials.__setitem__(
            (process.role, process.generation), token
        ),
        revoke_peer=lambda process: _revoke_peer(credentials, process),
    )
    registry = WorkerRegistry(
        workers={},
        launches={},
        commands=commands,
        owner=bootstrap.identity,
        policies=bootstrap.policies,
        file_policies=file_policies,
        coordinator_endpoint=endpoint,
        heartbeat_interval_ns=bootstrap.heartbeat_interval_ns,
        health_silence_ns=bootstrap.health_silence_ns,
        bootstrap=bootstrap_port,
        executables=PythonWorkerExecutables(
            resolve_python_executable(Path(sys.executable))
        ),
        supervisor=supervisor,
        cleanup_complete=_worker_cleanup_complete,
    )
    lazy_serial = LazySerialOwner(
        configuration.settings, configuration.file_policies, lambda _bridge: None
    )
    runtime_instance = AcquisitionCoordinatorRuntime(
        identity=identity,
        configuration=configuration,
        control_policies=bootstrap.policies,
        commands=commands,
        resource_ledger=resource_ledger,
        workers=registry,
        controller=controller,
        supervisor=supervisor,
        serial=lazy_serial,
        resource_port=resource_port,
        session_config_reference=lambda request: request.plan.session_directory,
    )
    server = await start_acquisition_server(
        runtime_instance,
        credentials,
        commands,
        port=bootstrap.endpoint_port,
        max_message_bytes=bootstrap.max_message_bytes,
        max_concurrent_rpcs=1024,
    )
    authority_watch = asyncio.create_task(
        _watch_authorities(native, bootstrap, runtime_instance)
    )
    health_watch: asyncio.Task[None] | None = None
    try:
        await register_backend_endpoint(bootstrap)
        health_watch = asyncio.create_task(_supervise_health(runtime_instance))
        await runtime_instance.shutdown_requested.wait()
    finally:
        authority_watch.cancel()
        if health_watch is not None:
            health_watch.cancel()
        await asyncio.gather(
            authority_watch,
            *([health_watch] if health_watch is not None else []),
            return_exceptions=True,
        )
        deadline = host_time_ns() + bootstrap.policies.recovery_ns
        await _close(
            server,
            runtime_instance,
            resource_port,
            controller_channel,
            supervisor_channel,
            deadline,
        )


async def _watch_authorities(
    native: WindowsJobs,
    bootstrap: AcquisitionBootstrap,
    runtime: AcquisitionCoordinatorRuntime,
) -> None:
    """Watch only the exact registered OS processes; no heartbeat/snapshot probes."""
    interval = bootstrap.heartbeat_interval_ns / 1_000_000_000
    while not runtime.shutdown_requested.is_set():
        await asyncio.sleep(interval)
        if runtime.shutdown_requested.is_set():
            return
        for role, pid, created in (
            (
                "controller",
                bootstrap.controller_pid,
                bootstrap.controller_creation_time_100ns,
            ),
            (
                "supervisor",
                bootstrap.supervisor_pid,
                bootstrap.supervisor_creation_time_100ns,
            ),
        ):
            try:
                running = await asyncio.to_thread(native.process_running, pid, created)
            except Exception:
                deadline_ns = host_time_ns() + bootstrap.policies.recovery_ns
                try:
                    await runtime.authority_lost(
                        role, deadline_ns=deadline_ns, observation_failed=True
                    )
                except Exception:
                    runtime.shutdown_requested.set()
                return
            if not running:
                deadline_ns = host_time_ns() + bootstrap.policies.recovery_ns
                try:
                    await runtime.authority_lost(role, deadline_ns=deadline_ns)
                except Exception:
                    runtime.shutdown_requested.set()
                return


async def _supervise_health(runtime: AcquisitionCoordinatorRuntime) -> None:
    """Turn an unexpected monitor failure into bounded acquisition cleanup."""
    try:
        await runtime.health.run(runtime.shutdown_requested)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        session = runtime.state.session_slot.current
        work = control.WorkContext()
        if session is not None:
            if session.trial is not None:
                work.CopyFrom(session.trial.work)
            else:
                work.CopyFrom(session.work)
        try:
            await runtime.health_failure(
                runtime.identity,
                work,
                control.Failure(
                    code="HEALTH_MONITOR_FAILED",
                    message=f"acquisition health supervision failed: {exc}"[:2048],
                ),
                host_time_ns() + runtime.control_policies.recovery_ns,
            )
        except Exception:
            runtime.shutdown_requested.set()


async def _close(
    server: AcquisitionServer,
    runtime: AcquisitionCoordinatorRuntime,
    resources: WindowsResourcePort,
    controller_channel: grpc.aio.Channel,
    supervisor_channel: grpc.aio.Channel,
    deadline_ns: int,
) -> None:
    try:
        await server.close(deadline_ns=deadline_ns)
    finally:
        try:
            await runtime.serial.close(deadline_ns=deadline_ns)
        finally:
            for allocation_id_value, record in tuple(runtime.state.resources.items()):
                try:
                    if runtime.resource_ledger.may_close_owner(record.ledger_key):
                        resources.release_ring(allocation_id_value)
                        runtime.resource_ledger.confirm_owner_release(record.ledger_key)
                except Exception:
                    # The runtime retains the exact partial/native record until
                    # process exit; close failure is never converted to proof.
                    continue
            await controller_channel.close()
            await supervisor_channel.close()


def _revoke_peer(
    credentials: dict[tuple[str, str], str], process: control.ProcessIdentity
) -> None:
    credentials.pop((process.role, process.generation), None)


def _worker_cleanup_complete(
    worker: WorkerRecord, evidence: acq.WorkerCleanupEvidence
) -> bool:
    expected = (
        {item.resource_id for item in worker.setup_ready.attached_resources}
        if worker.setup_ready is not None
        else set()
    )
    if worker.preview is not None and worker.preview.allocation_id is not None:
        expected.add(worker.preview.allocation_id)
    expected.add(f"camera-device:{worker.launch.worker.generation}")
    releases = {item.resource: item for item in evidence.resources}
    if (
        len(releases) != len(evidence.resources)
        or not expected <= set(releases)
        or any(
            not item.released
            or item.failure.code
            or item.failure.message
            or item.HasField("path")
            for item in releases.values()
        )
    ):
        return False
    if len({item.output_key for item in evidence.outputs}) != len(evidence.outputs):
        return False
    for item in evidence.outputs:
        if not item.output_key or not item.HasField("artifact_present"):
            return False
        if item.closure == control.OUTPUT_CLOSURE_CLOSED:
            if not item.artifact_present or item.failure.ByteSize():
                return False
        elif item.closure == control.OUTPUT_CLOSURE_FAILED:
            if not item.failure.code or not item.failure.message:
                return False
        elif item.closure == control.OUTPUT_CLOSURE_NOT_STARTED:
            if (
                item.artifact_present
                or item.failure.ByteSize()
                or item.camera_video_content
                not in {
                    control.CAMERA_VIDEO_CONTENT_UNSPECIFIED,
                    control.CAMERA_VIDEO_CONTENT_NO_FRAMES,
                }
            ):
                return False
        else:
            return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(prog="cephvr-acquisition")
    parser.add_argument("--bootstrap-handle", type=int, required=True)
    args = parser.parse_args()
    descriptor = read_bootstrap(args.bootstrap_handle)
    bootstrap = decode_acquisition_bootstrap(descriptor)
    with SingleInstanceGuard("acquisition"):
        asyncio.run(run_acquisition(bootstrap))


if __name__ == "__main__":
    main()
