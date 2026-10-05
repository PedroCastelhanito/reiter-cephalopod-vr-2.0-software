"""Registered renderer process with independent health and graphics ownership."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable
from uuid import uuid4

import grpc

from cephvr.control.v1 import services_pb2_grpc as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.platform.windows.bootstrap import read_bootstrap
from cephvr.platform.windows.jobs import WindowsJobs
from cephvr.shared.auth import Principal
from cephvr.shared.clock import host_time_ns
from cephvr.visual_stimulus.main import command_ledger
from cephvr.visual_stimulus.transport.peers import Peer
from cephvr.visual_stimulus.transport.server import serve
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus

from .bootstrap import WorkerBootstrap, decode
from .owner import RenderOwner
from .registration import register
from .reporting import ReportBridge
from .runtime import VisualStimulusWorkerRuntime


async def run(bootstrap: WorkerBootstrap) -> None:
    if sys.platform != "win32":
        raise RuntimeError("managed renderer requires Windows")
    from .native import assemble_driver

    loop = asyncio.get_running_loop()
    native = WindowsJobs()
    principal = Principal(
        "visual_stimulus_renderer", bootstrap.context.worker.generation, bootstrap.token
    )
    coordinator = Peer(
        bootstrap.coordinator_endpoint,
        principal,
        bootstrap.max_message_bytes,
        kind="coordinator",
    )
    supervisor = Peer(
        bootstrap.supervisor_endpoint,
        principal,
        bootstrap.max_message_bytes,
        kind="supervisor",
    )
    ledger = command_ledger(
        bootstrap.context.worker.generation,
        bootstrap.policies.command_retention_after_finalization_ns,
        bootstrap.max_message_bytes,
    )
    shutdown = asyncio.Event()
    recovery: asyncio.Task[None] | None = None
    recovery_deadline: int | None = None

    async def recover(error: BaseException) -> None:
        nonlocal recovery_deadline
        recovery_deadline = (
            recovery_deadline or host_time_ns() + bootstrap.policies.recovery_ns
        )
        runtime.interrupted = True
        owner.cancel()
        error_report = pb.ErrorReport(
            error_id=str(uuid4()),
            source=bootstrap.context.worker,
            work=runtime.context.work,
            occurred_monotonic_ns=host_time_ns(),
            failure=pb.Failure(
                code="VISUAL_STIMULUS_WORKER_FAILURE", message=str(error)[:2048]
            ),
        )
        delivery = asyncio.create_task(
            supervisor.receipt(
                "ReportError",
                error_report,
                deadline_ns=recovery_deadline,
            )
        )
        command = visual_stimulus.WorkerCommand(
            command_id=str(uuid4()),
            issuer=bootstrap.context.worker,
            target=runtime.context,
            deadline_monotonic_ns=recovery_deadline,
        )
        # A local safety operation does not impersonate an authenticated remote caller.
        try:
            async with asyncio.timeout(
                max(0, (recovery_deadline - host_time_ns()) / 1e9)
            ):
                await owner.submit("Shutdown", command, recovery_deadline)
        finally:
            shutdown.set()
            await asyncio.gather(delivery, return_exceptions=True)

    def failed(error: BaseException) -> None:
        def start() -> None:
            nonlocal recovery
            if recovery is None:
                recovery = asyncio.create_task(recover(error))

        loop.call_soon_threadsafe(start)

    bridge = ReportBridge(
        loop,
        coordinator,
        supervisor,
        failed=failed,
        maximum_bytes=max(4 * bootstrap.max_message_bytes, 16 * 1024 * 1024),
    )

    def signal_shutdown() -> None:
        loop.call_soon_threadsafe(shutdown.set)

    encoder_channel = grpc.insecure_channel(
        bootstrap.supervisor_endpoint,
        options=(
            ("grpc.max_send_message_length", bootstrap.max_message_bytes),
            ("grpc.max_receive_message_length", bootstrap.max_message_bytes),
        ),
    )
    encoder_supervisor = rpc.SupervisorServiceStub(encoder_channel)  # type: ignore[no-untyped-call]
    owner = RenderOwner(
        lambda cancelled: assemble_driver(
            bootstrap,
            bridge,
            cancelled,
            signal_shutdown,
            encoder_supervisor,
        )
    )
    runtime = VisualStimulusWorkerRuntime(
        bootstrap.context,
        bootstrap.supervisor,
        owner,
        coordinator,
        ledger,
        delivery_failed=failed,
    )
    bridge.retain_lifecycle = runtime.retain_and_report
    bridge.observe_display = runtime.display.CopyFrom
    credentials = {
        ("visual_stimulus", bootstrap.context.owner.generation): bootstrap.owner_token,
        ("supervisor", bootstrap.supervisor.generation): bootstrap.supervisor_token,
    }
    listener = await serve(
        runtime,
        credentials,
        ledger,
        port=0,
        max_message_bytes=bootstrap.max_message_bytes,
        worker=True,
    )
    health = None
    try:
        await register(bootstrap, supervisor, listener.port)
        health = asyncio.create_task(
            health_loop(bootstrap, native, runtime, owner, bridge, coordinator, failed)
        )
        await shutdown.wait()
    finally:
        if health is not None:
            health.cancel()
            await asyncio.gather(health, return_exceptions=True)
        deadline = (
            recovery_deadline
            or runtime.shutdown_deadline_ns
            or host_time_ns() + bootstrap.policies.recovery_ns
        )
        try:
            await owner.close(deadline)
            await bridge.drain(deadline)
            await listener.close(deadline)
        finally:
            encoder_channel.close()
            await coordinator.close()
            await supervisor.close()
        if recovery is not None:
            await asyncio.gather(recovery, return_exceptions=True)


async def health_loop(
    bootstrap: WorkerBootstrap,
    native: WindowsJobs,
    runtime: VisualStimulusWorkerRuntime,
    owner: RenderOwner,
    bridge: ReportBridge,
    coordinator: Peer,
    failed: Callable[[BaseException], None],
) -> None:
    last_accepted = host_time_ns()
    while True:
        now = host_time_ns()
        if owner.failure is not None:
            failed(owner.failure)
            return
        for pid, creation in (
            (bootstrap.owner_pid, bootstrap.owner_creation_time_100ns),
            (bootstrap.supervisor_pid, bootstrap.supervisor_creation_time_100ns),
        ):
            try:
                alive = await asyncio.to_thread(native.process_running, pid, creation)
                if not alive:
                    raise RuntimeError("registered renderer authority exited")
            except Exception as exc:
                failed(exc)
                return
        report = pb.HeartbeatReport.FromString(bridge.catalogue.SerializeToString())
        report.source.CopyFrom(bootstrap.context.worker)
        report.work.CopyFrom(runtime.context.work)
        report.sent_monotonic_ns = now
        report.workers.add(
            worker="renderer",
            progress_required=owner.progress_required,
            last_progress_monotonic_ns=owner.last_progress_ns,
        )
        try:
            await coordinator.receipt(
                "ReportWorkerHeartbeat",
                report,
                deadline_ns=min(
                    now + bootstrap.heartbeat_interval_ns,
                    last_accepted + bootstrap.health_silence_ns,
                ),
            )
            last_accepted = host_time_ns()
        except Exception as exc:
            if host_time_ns() - last_accepted >= bootstrap.health_silence_ns:
                failed(exc)
                return
        runtime.prune_retained()
        await asyncio.sleep(bootstrap.heartbeat_interval_ns / 1e9)


def main() -> None:
    parser = argparse.ArgumentParser(prog="cephvr-visual-stimulus-worker")
    parser.add_argument("--bootstrap-handle", type=int, required=True)
    args = parser.parse_args()
    bootstrap = decode(read_bootstrap(args.bootstrap_handle))
    asyncio.run(run(bootstrap))


if __name__ == "__main__":
    main()
