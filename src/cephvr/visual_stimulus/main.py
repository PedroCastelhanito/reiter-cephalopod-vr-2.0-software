"""Managed Windows stimulus coordinator; configuration imports remain lightweight."""

from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import uuid4

from cephvr.control.v1 import types_pb2 as pb
from cephvr.platform.windows.bootstrap import read_bootstrap
from cephvr.platform.windows.guard import SingleInstanceGuard
from cephvr.platform.windows.jobs import WindowsJobs
from cephvr.shared.auth import Principal
from cephvr.shared.backend_bootstrap import BackendBootstrap, decode_backend_bootstrap
from cephvr.shared.backend_registration import register_backend_endpoint
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger
from cephvr.visual_stimulus.coordinator.state import Identity
from cephvr.visual_stimulus.runtime import VisualStimulusCoordinatorRuntime
from cephvr.visual_stimulus.transport.peers import Peer
from cephvr.visual_stimulus.transport.pending import PendingPeer
from cephvr.visual_stimulus.transport.server import serve
from cephvr.visual_stimulus.worker_launcher import (
    launch_renderer,
    release_renderer_handles,
)


def command_ledger(generation: str, retention_ns: int, maximum: int) -> CommandLedger:
    return CommandLedger(
        generation,
        retention_ns,
        max_records=1024,
        max_bytes=max(64 * 1024 * 1024, 4 * maximum),
        result_reservation_bytes=64 * 1024,
        safety_reserve_records=16,
        safety_reserve_bytes=2 * 1024 * 1024,
    )


async def run(bootstrap: BackendBootstrap) -> None:
    if sys.platform != "win32":
        raise RuntimeError("managed Visual Stimulus native runtime requires Windows")
    native = WindowsJobs()
    principal = Principal(
        "visual_stimulus", bootstrap.identity.generation, bootstrap.token
    )
    controller = Peer(
        f"127.0.0.1:{bootstrap.controller_port}",
        principal,
        bootstrap.max_message_bytes,
        kind="controller",
    )
    supervisor = Peer(
        f"127.0.0.1:{bootstrap.supervisor_port}",
        principal,
        bootstrap.max_message_bytes,
        kind="supervisor",
    )
    worker = pb.ProcessIdentity(
        role="visual_stimulus_renderer", generation=str(uuid4())
    )
    credentials = {
        ("controller", bootstrap.controller.generation): bootstrap.controller_token,
        ("supervisor", bootstrap.supervisor.generation): bootstrap.supervisor_token,
    }
    ledger = command_ledger(
        bootstrap.identity.generation,
        bootstrap.policies.command_retention_after_finalization_ns,
        bootstrap.max_message_bytes,
    )
    endpoint = PendingPeer()
    runtime = VisualStimulusCoordinatorRuntime(
        identity=Identity(
            bootstrap.identity, bootstrap.controller, bootstrap.supervisor, worker
        ),
        worker=endpoint,
        controller=controller,
        supervisor=supervisor,
        ledger=ledger,
    )
    listener = await serve(
        runtime,
        credentials,
        ledger,
        port=bootstrap.endpoint_port,
        max_message_bytes=bootstrap.max_message_bytes,
    )
    launch = None
    watch = None
    try:
        await register_backend_endpoint(bootstrap)
        launch = await launch_renderer(
            bootstrap,
            supervisor,
            native,
            credentials,
            host_time_ns() + bootstrap.policies.supervisor_registration.initial_ns,
            identity=worker,
        )
        endpoint.attach(launch.peer)
        runtime.state.worker_ingress_ns = host_time_ns()
        watch = asyncio.create_task(watch_authorities(bootstrap, native, runtime))
        await runtime.shutdown_requested.wait()
    finally:
        if watch is not None:
            watch.cancel()
            await asyncio.gather(watch, return_exceptions=True)
        deadline = (
            runtime.recovery_deadline_ns
            or host_time_ns() + bootstrap.policies.recovery_ns
        )
        try:
            await listener.close(deadline)
        finally:
            if launch is not None:
                await launch.peer.close()
                cleanup = runtime.state.cleanup
                if cleanup is not None and all(
                    item.released for item in cleanup.resources
                ):
                    await asyncio.to_thread(
                        release_renderer_handles, launch, native, deadline
                    )
                # Unknown child/descendant release remains in the supervisor's catalogue.
            await controller.close()
            await supervisor.close()


async def watch_authorities(
    bootstrap: BackendBootstrap,
    native: WindowsJobs,
    runtime: VisualStimulusCoordinatorRuntime,
) -> None:
    while not runtime.shutdown_requested.is_set():
        await asyncio.sleep(bootstrap.heartbeat_interval_ns / 1e9)
        failure: str | None = None
        for role, pid, creation in (
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
                running = await asyncio.to_thread(native.process_running, pid, creation)
                if not running:
                    failure = f"registered {role} process exited"
            except Exception as exc:
                failure = f"cannot verify registered {role}: {exc}"
            if failure is not None:
                break
        last = runtime.state.worker_ingress_ns
        if last is not None and host_time_ns() - last >= bootstrap.health_silence_ns:
            failure = "renderer health silence exceeded its original bound"
        if failure is not None:
            await runtime.authority_lost(
                failure, host_time_ns() + bootstrap.policies.recovery_ns
            )
            return
        runtime.prune_retained()


def main() -> None:
    parser = argparse.ArgumentParser(prog="cephvr-visual-stimulus")
    parser.add_argument("--bootstrap-handle", type=int, required=True)
    args = parser.parse_args()
    bootstrap = decode_backend_bootstrap(
        read_bootstrap(args.bootstrap_handle), expected_role="visual_stimulus"
    )
    with SingleInstanceGuard("visual_stimulus"):
        asyncio.run(run(bootstrap))


if __name__ == "__main__":
    main()
