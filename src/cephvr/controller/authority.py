"""E08 controller-side authority monitoring and survivor shutdown.

Only pre-registered inner jobs are accessible here. The launcher alone owns the
outer kill-on-close job and verifies final application absence.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.backend import GrpcBackendPort
from cephvr.controller.configuration import SupervisorStartup
from cephvr.controller.runtime import ControllerRuntime
from cephvr.platform.windows.bootstrap import run_pipe_io_daemon
from cephvr.shared.clock import host_time_ns
from cephvr.shared.identity import require_uuid4


@dataclass(frozen=True)
class ManagedJob:
    role: str
    generation: str
    job_name: str


def managed_jobs_from_bootstrap(value: object) -> tuple[ManagedJob, ...]:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("bootstrap must identify four exact top-level inner jobs")
    jobs = []
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"role", "generation", "job_name"}
            or any(not isinstance(v, str) for v in item.values())
            or item["role"] not in {"acquisition", "vr", "tracking", "gui"}
        ):
            raise ValueError("managed job descriptor is invalid")
        require_uuid4(item["generation"])
        prefix = "Local\\CephVR2-"
        if not item["job_name"].startswith(prefix):
            raise ValueError("managed job is not a registered CephVR inner job")
        require_uuid4(item["job_name"][len(prefix) :])
        jobs.append(ManagedJob(**item))
    if len({job.role for job in jobs}) != 4 or len({job.job_name for job in jobs}) != 4:
        raise ValueError("managed job descriptors repeat a role or native job")
    return tuple(jobs)


class NativeMonitor(Protocol):
    def inspect_launch_job(self, name: str) -> list[tuple[int, int, str]]: ...

    def retain_exact(
        self, pid: int, creation_time_100ns: int, executable: str
    ) -> object: ...

    def process_running(self, pid: int, creation_time_100ns: int) -> bool: ...

    def terminate_exact(self, pid: int, creation_time_100ns: int) -> None: ...


async def notify_launcher(
    descriptor: int,
    *,
    supervisor_generation: str,
    controller_generation: str,
    deadline_ns: int,
    cause: str,
    timeout_s: float,
) -> None:
    """One protected, controller-only pipe; no shared-write framing race."""
    packet = (
        json.dumps(
            {
                "kind": "shutdown",
                "supervisor_generation": supervisor_generation,
                "controller_generation": controller_generation,
                "deadline_monotonic_ns": deadline_ns,
                "cause": cause,
            },
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )
    if len(packet) > 8192:
        raise ValueError("launcher notification exceeds its frame limit")

    def send() -> None:
        offset = 0
        while offset < len(packet):
            count = os.write(descriptor, packet[offset:])
            if count <= 0:
                raise OSError("launcher control pipe closed")
            offset += count

    await run_pipe_io_daemon(send, timeout_s=timeout_s)


async def shutdown_owned_jobs(
    native: NativeMonitor,
    jobs: Sequence[ManagedJob],
    *,
    absolute_deadline_ns: int,
    graceful_exit_ns: int,
    terminate_exit_ns: int,
    clock: Callable[[], int] = host_time_ns,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> tuple[str, ...]:
    """Bound two exit groups and retain unknown/remaining membership as failures."""
    failures: list[str] = []

    def remember(message: str) -> None:
        if len(failures) < 16 and message not in failures:
            failures.append(message)

    def members(group: Sequence[ManagedJob]) -> list[tuple[int, int, str]] | None:
        found: dict[tuple[int, int], tuple[int, int, str]] = {}
        try:
            for job in group:
                for pid, created, executable in native.inspect_launch_job(job.job_name):
                    native.retain_exact(pid, created, executable)
                    found[(pid, created)] = (pid, created, executable)
        except Exception as exc:
            remember(f"owned process membership unconfirmed: {exc}")
            return None
        return list(found.values())

    async def wait_until(group: Sequence[ManagedJob], deadline: int) -> None:
        while clock() < deadline:
            current = members(group)
            if current == []:
                return
            await sleep(min(0.05, (deadline - clock()) / 1e9))

    for roles in ({"acquisition", "vr", "tracking"}, {"gui"}):
        group = [job for job in jobs if job.role in roles]
        await wait_until(group, min(absolute_deadline_ns, clock() + graceful_exit_ns))
        current = members(group)
        if current is not None:
            for pid, created, _ in current:
                try:
                    if native.process_running(pid, created):
                        native.terminate_exact(pid, created)
                except Exception as exc:
                    remember(f"exact process {pid}/{created} exit unconfirmed: {exc}")
        await wait_until(group, min(absolute_deadline_ns, clock() + terminate_exit_ns))
        remaining = members(group)
        if remaining:
            remember(f"{len(remaining)} owned processes remain for launcher backstop")
    # Repeated observations cannot grow an error history with polling duration.
    return tuple(failures)


async def handle_authority_loss(
    runtime: ControllerRuntime,
    *,
    cause: str,
    issued_ns: int,
    startup: SupervisorStartup,
    native: NativeMonitor,
    jobs: Sequence[ManagedJob],
    backends: Mapping[str, GrpcBackendPort],
    launcher_descriptor: int,
    software_root: str,
    notify_backstop: bool = True,
) -> None:
    """Notify the independent backstop before doing bounded local finalization."""
    from pathlib import Path

    from cephvr.shared.emergency import write_emergency_report

    first_intent_ns = (
        min(issued_ns, runtime._shutdown_intent_ns)
        if runtime._shutdown_intent_ns
        else issued_ns
    )
    outer_deadline = first_intent_ns + startup.application_backstop_ns
    cleanup_budget = (
        runtime.limits.finished_ns
        if runtime.attempt is not None and runtime.attempt.activated
        else runtime.limits.setup_cancel_ns
    ) + runtime.limits.recovery_ns
    cleanup_deadline = min(outer_deadline, issued_ns + cleanup_budget)
    failures: list[str] = []
    # Start fencing immediately; pipe delivery cannot delay the safety handler.
    cleanup = asyncio.create_task(runtime.authority_loss(cause, issued_ns))
    try:
        if notify_backstop:
            await notify_launcher(
                launcher_descriptor,
                supervisor_generation=runtime.supervisor_generation,
                controller_generation=runtime.generation,
                deadline_ns=outer_deadline,
                cause=cause,
                timeout_s=max(
                    0,
                    min(startup.emergency_timeout_ns, cleanup_deadline - host_time_ns())
                    / 1e9,
                ),
            )
    except Exception as exc:
        failures.append(f"launcher notification unconfirmed: {exc}")
    try:
        await asyncio.wait_for(
            asyncio.shield(cleanup), max(0, (cleanup_deadline - host_time_ns()) / 1e9)
        )
    except Exception as exc:
        failures.append(f"authority cleanup unconfirmed: {exc}")
    attempt = runtime.attempt
    work = pb.WorkContext(session=attempt.context) if attempt else pb.WorkContext()
    try:
        await write_emergency_report(
            Path(software_root),
            cause=cause,
            supervisor=pb.ProcessIdentity(
                role="supervisor", generation=runtime.supervisor_generation
            ),
            controller=pb.ProcessIdentity(
                role="controller", generation=runtime.generation
            ),
            work=work,
            errors=[
                pb.ErrorReport(failure=pb.Failure(code="UNCONFIRMED", message=message))
                for message in failures
            ],
            timeout_ns=min(
                startup.emergency_timeout_ns, max(1, outer_deadline - host_time_ns())
            ),
            spikeglx_stop_unconfirmed=bool(
                attempt and attempt.paired and not attempt.spikeglx_stopped
            ),
        )
    except Exception:
        # File I/O cannot block safety exit. The unfinished reservation is retained.
        pass
    graceful_deadline = min(outer_deadline, host_time_ns() + startup.graceful_exit_ns)

    async def request_exit(backend: GrpcBackendPort) -> None:
        request = svc.BackendCommand(
            command_id=str(uuid.uuid4()),
            issuer=pb.ProcessIdentity(role="controller", generation=runtime.generation),
            target=backend.context,
            work=work,
        )
        try:
            await asyncio.wait_for(
                backend.shutdown(request),
                max(0, (graceful_deadline - host_time_ns()) / 1e9),
            )
        except Exception:
            pass  # Exact job/process observation below determines exit, never admission.

    # Delivery and exit observation consume one shared graceful deadline.
    requests = asyncio.gather(*(request_exit(backend) for backend in backends.values()))
    await shutdown_owned_jobs(
        native,
        jobs,
        absolute_deadline_ns=outer_deadline,
        graceful_exit_ns=startup.graceful_exit_ns,
        terminate_exit_ns=startup.terminate_exit_ns,
    )
    await requests
    if not cleanup.done():
        cleanup.cancel()
    await asyncio.gather(cleanup, return_exceptions=True)
