"""Controller-side authority liveness and shutdown handoff."""

from __future__ import annotations

import asyncio
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path

import grpc

from cephvr.control.v1 import services_pb2_grpc as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.authority import (
    AuthorityControl,
    ManagedJob,
    handle_authority_loss,
    notify_launcher,
    shutdown_owned_jobs,
)
from cephvr.controller.backend import GrpcBackendPort
from cephvr.controller.configuration import (
    SupervisorStartup,
)
from cephvr.platform.windows.jobs import WindowsJobs
from cephvr.shared.auth import Principal


async def authority_loop(
    control: AuthorityControl,
    stub: rpc.SupervisorServiceStub,
    principal: Principal,
    supervisor_pid: int,
    supervisor_creation: int,
    startup: SupervisorStartup,
    native: WindowsJobs,
    managed_jobs: tuple[ManagedJob, ...],
    backends: Mapping[str, GrpcBackendPort],
    launcher_descriptor: int,
    software_root: Path,
) -> None:

    async def send_heartbeats() -> None:
        while True:
            await asyncio.sleep(startup.heartbeat_interval_ns / 1e9)
            observed = control.status()
            heartbeat = pb.HeartbeatReport(
                source=pb.ProcessIdentity(
                    role="controller", generation=control.generation
                ),
                sent_monotonic_ns=control.clock(),
                session_phase=observed.session_phase,
                health_summary="responsive",
            )
            if observed.work.WhichOneof("work") is not None:
                heartbeat.work.CopyFrom(observed.work)
            try:
                await asyncio.wait_for(
                    stub.ReportHeartbeat(heartbeat, metadata=principal.metadata()),
                    startup.heartbeat_interval_ns / 1e9,
                )
            except (TimeoutError, grpc.RpcError):
                pass

    sender = asyncio.create_task(send_heartbeats())
    launcher_attempted = False
    launcher_notified = False

    async def enforce_owned_exit(deadline: int) -> None:
        failures = await shutdown_owned_jobs(
            native,
            managed_jobs,
            absolute_deadline_ns=deadline,
            graceful_exit_ns=startup.graceful_exit_ns,
            terminate_exit_ns=startup.terminate_exit_ns,
        )
        for failure in failures:
            print(f"Shutdown remains unconfirmed: {failure}", file=sys.stderr)
        try:
            native.terminate_exact(supervisor_pid, supervisor_creation)
        except Exception as exc:
            print(f"Supervisor exit unconfirmed: {exc}", file=sys.stderr)

    try:
        while True:
            await asyncio.sleep(0.1)
            now = control.clock()
            observed = control.status()
            if observed.shutdown_intent_ns:
                allowance = (
                    control.limits.current.finished_ns
                    if observed.activated
                    else control.limits.current.setup_cancel_ns
                )
                control.bind_cleanup_deadline(
                    min(
                        observed.shutdown_intent_ns + startup.application_backstop_ns,
                        observed.shutdown_intent_ns
                        + allowance
                        + control.limits.current.recovery_ns,
                    )
                )
            if observed.shutdown_intent_ns and not launcher_attempted:
                launcher_attempted = True
                deadline = observed.shutdown_intent_ns + startup.application_backstop_ns
                try:
                    await notify_launcher(
                        launcher_descriptor,
                        supervisor_generation=control.supervisor_generation,
                        controller_generation=control.generation,
                        deadline_ns=deadline,
                        cause="OPERATOR_SHUTDOWN",
                        timeout_s=max(
                            0, min(startup.emergency_timeout_ns, deadline - now) / 1e9
                        ),
                    )
                    launcher_notified = True
                except Exception as exc:
                    await control.warn(
                        pb.Warning(
                            warning_id=str(uuid.uuid4()),
                            component="shutdown",
                            message=f"launcher handoff unconfirmed: {exc}",
                        )
                    )
                now = control.clock()
                observed = control.status()
            try:
                alive = native.process_running(supervisor_pid, supervisor_creation)
                cause = "SUPERVISOR_LOST" if not alive else "SUPERVISOR_SILENT"
            except Exception:
                alive = False
                cause = "SUPERVISOR_IDENTITY_UNCONFIRMED"
            if (
                sender.done()
                or not alive
                or now - observed.supervisor_last_seen_ns > startup.silence_timeout_ns
            ):
                await handle_authority_loss(
                    control,
                    cause=cause,
                    issued_ns=now,
                    startup=startup,
                    native=native,
                    jobs=managed_jobs,
                    backends=backends,
                    launcher_descriptor=launcher_descriptor,
                    software_root=str(software_root),
                    notify_backstop=not launcher_attempted,
                )
                if launcher_attempted and not launcher_notified:
                    deadline = (
                        observed.shutdown_intent_ns + startup.application_backstop_ns
                    )
                    # Deadline poll against the injectable clock; no event marks this deadline.
                    while control.clock() < deadline:  # noqa: ASYNC110
                        await asyncio.sleep(
                            max(0, min(0.1, (deadline - control.clock()) / 1e9))
                        )
                    await enforce_owned_exit(deadline)
                return
            if observed.shutdown_intent_ns:
                deadline = observed.shutdown_intent_ns + startup.application_backstop_ns
                handoff_complete = observed.handoff_complete
                if (
                    launcher_notified
                    and handoff_complete
                    and observed.session_phase
                    in (pb.SESSION_PHASE_CONFIGURATION, pb.SESSION_PHASE_ENDED)
                    and observed.cleanup_confirmed
                ):
                    return
                if now >= deadline:
                    if not launcher_notified:
                        # No fresh grace period follows an uncertain pipe handoff.
                        # The original bound has expired; use only retained owned
                        # jobs and the exact retained supervisor process handle.
                        await enforce_owned_exit(deadline)
                    return
    finally:
        sender.cancel()
        await asyncio.gather(sender, return_exceptions=True)
