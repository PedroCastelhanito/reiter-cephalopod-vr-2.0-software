"""Managed Tracking entry point; native processing remains on its owning threads."""

from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import uuid4

from cephvr.control.v1 import services_pb2 as wire
from cephvr.platform.windows.bootstrap import read_bootstrap
from cephvr.platform.windows.guard import SingleInstanceGuard
from cephvr.platform.windows.jobs import WindowsJobs
from cephvr.shared.auth import Principal
from cephvr.shared.backend_bootstrap import BackendBootstrap, decode_backend_bootstrap
from cephvr.shared.backend_registration import register_backend_endpoint
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger
from cephvr.tracking.coordinator.state import Identity
from cephvr.tracking.runtime import TrackingRuntime
from cephvr.tracking.transport.peers import Peer
from cephvr.tracking.transport.server import serve


async def run(bootstrap: BackendBootstrap) -> None:
    if sys.platform != "win32":
        raise RuntimeError("managed Tracking native runtime requires Windows")
    native = WindowsJobs()
    principal = Principal("tracking", bootstrap.identity.generation, bootstrap.token)
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
    ledger = CommandLedger(
        bootstrap.identity.generation,
        bootstrap.policies.command_retention_after_finalization_ns,
        max_records=1024,
        max_bytes=max(64 * 1024 * 1024, 4 * bootstrap.max_message_bytes),
        result_reservation_bytes=64 * 1024,
        safety_reserve_records=16,
        safety_reserve_bytes=2 * 1024 * 1024,
    )
    runtime = TrackingRuntime(
        Identity(bootstrap.identity, bootstrap.controller, bootstrap.supervisor),
        controller,
        supervisor,
        ledger,
    )
    credentials = {
        (
            bootstrap.controller.role,
            bootstrap.controller.generation,
        ): bootstrap.controller_token,
        (
            bootstrap.supervisor.role,
            bootstrap.supervisor.generation,
        ): bootstrap.supervisor_token,
    }
    listener = await serve(
        runtime,
        credentials,
        ledger,
        port=bootstrap.endpoint_port,
        max_message_bytes=bootstrap.max_message_bytes,
    )
    watch = asyncio.create_task(watch_authorities(bootstrap, native, runtime))
    try:
        await register_backend_endpoint(bootstrap)
        await runtime.shutdown_requested.wait()
    finally:
        watch.cancel()
        await asyncio.gather(watch, return_exceptions=True)
        deadline = (
            runtime.recovery_deadline or host_time_ns() + bootstrap.policies.recovery_ns
        )
        await listener.close(deadline)
        runtime.executor.shutdown(wait=False, cancel_futures=False)
        await controller.close()
        await supervisor.close()


async def watch_authorities(
    bootstrap: BackendBootstrap, native: WindowsJobs, runtime: TrackingRuntime
) -> None:
    while not runtime.shutdown_requested.is_set():
        deadline = host_time_ns() + bootstrap.health_silence_ns
        lost = None
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
                if not await asyncio.to_thread(native.process_running, pid, creation):
                    lost = f"registered {role} exited"
            except Exception as exc:
                lost = f"cannot verify {role}: {exc}"
            if lost:
                break
        if lost:
            runtime.state.interrupted = True
            runtime.gate.seal(host_time_ns())
            command = wire.BackendCommand(
                command_id=str(uuid4()),
                issuer=bootstrap.supervisor,
                target=runtime.identity.backend,
                work=runtime.state.work(),
            )
            try:
                recovery = host_time_ns() + bootstrap.policies.recovery_ns
                try:
                    if runtime.trials is not None and runtime.state.trial is not None:
                        await runtime.trials.stop(recovery)
                finally:
                    await runtime.cleanup(command, recovery)
            finally:
                runtime.shutdown_requested.set()
            return
        try:
            await runtime.poll(deadline)
        except Exception:
            # OS authority checks remain independent of a temporarily failed report RPC.
            pass
        ledger = runtime.ledger
        ledger.prune(host_time_ns())
        await asyncio.sleep(bootstrap.heartbeat_interval_ns / 1e9)


def main() -> None:
    parser = argparse.ArgumentParser(prog="cephvr-tracking")
    parser.add_argument("--bootstrap-handle", type=int, required=True)
    args = parser.parse_args()
    bootstrap = decode_backend_bootstrap(
        read_bootstrap(args.bootstrap_handle), expected_role="tracking"
    )
    with SingleInstanceGuard("tracking"):
        asyncio.run(run(bootstrap))


if __name__ == "__main__":
    main()
