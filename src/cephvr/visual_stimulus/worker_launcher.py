"""Registered Windows renderer creation under the existing E08 containment path."""

from __future__ import annotations

import asyncio
import base64
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.platform.windows.bootstrap import (
    close_handle,
    create_bootstrap_pipe,
    run_pipe_io_daemon,
    write_bootstrap,
)
from cephvr.platform.windows.jobs import SuspendedProcess, WindowsJobs
from cephvr.platform.windows.python_runtime import (
    module_arguments,
    resolve_python_executable,
)
from cephvr.shared.auth import Principal
from cephvr.shared.backend_bootstrap import BackendBootstrap
from cephvr.shared.clock import host_time_ns
from cephvr.visual_stimulus.coordinator.ports import PeerPort
from cephvr.visual_stimulus.transport.peers import Peer
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus


@dataclass
class RendererLaunch:
    command_id: str
    child: SuspendedProcess
    job_name: str
    identity: pb.ProcessIdentity
    token: str
    peer: Peer


def release_renderer_handles(
    launch: RendererLaunch, native: WindowsJobs, deadline_ns: int
) -> bool:
    """Release handles only after exact child and contained descendant exit proof."""
    remaining_ms = max(0, min(0xFFFFFFFE, (deadline_ns - host_time_ns()) // 1_000_000))
    if not native.wait_process_exit(
        launch.child.pid, launch.child.creation_time_100ns, remaining_ms
    ) or native.inspect_launch_job(launch.job_name):
        return False
    native.release_process(launch.child.pid, launch.child.creation_time_100ns)
    native.close_launch_job(launch.job_name)
    return True


async def launch_renderer(
    bootstrap: BackendBootstrap,
    supervisor: PeerPort,
    native: WindowsJobs,
    credentials: dict[tuple[str, str], str],
    deadline_ns: int,
    *,
    identity: pb.ProcessIdentity | None = None,
) -> RendererLaunch:
    identity = identity or pb.ProcessIdentity(
        role="visual_stimulus_renderer", generation=str(uuid4())
    )
    interpreter = resolve_python_executable(Path(sys.executable))
    command_id = str(uuid4())
    token = secrets.token_urlsafe(32)
    planned = await supervisor.call(
        "PlanLaunch",
        wire.PlanLaunchRequest(
            command_id=command_id,
            owner=bootstrap.identity,
            child=identity,
            executable=str(interpreter),
            python_worker=True,
            stop_method="grpc_shutdown",
        ),
        deadline_ns=deadline_ns,
        metadata=(("x-cephvr-child-token", token),),
    )
    if (
        not isinstance(planned, wire.LaunchReceipt)
        or planned.admission.result != pb.COMMAND_RESULT_ACCEPTED
        or planned.state.phase != wire.LAUNCH_PHASE_PLANNED
    ):
        raise RuntimeError("supervisor did not plan renderer containment")
    job_name = planned.state.containment_job_name
    native.open_launch_job(job_name)
    read, write = create_bootstrap_pipe()
    try:
        child = native.launch_suspended(
            str(interpreter),
            module_arguments(
                "cephvr.visual_stimulus.worker.main", ["--bootstrap-handle", str(read)]
            ),
            [job_name],
            (read,),
        )
    except BaseException as exc:
        close_handle(read)
        close_handle(write)
        if native.inspect_launch_job(job_name) == []:
            await supervisor.call(
                "ConfirmLaunch",
                wire.ConfirmLaunchRequest(
                    command_id=str(uuid4()),
                    launch_command_id=command_id,
                    owner=bootstrap.identity,
                    child=identity,
                    creation_failed_without_child=True,
                    failure=pb.Failure(code="RENDERER_CREATE", message=str(exc)[:2048]),
                ),
                deadline_ns=deadline_ns,
            )
        raise
    writing_started = False
    try:
        confirmed = await supervisor.call(
            "ConfirmLaunch",
            wire.ConfirmLaunchRequest(
                command_id=str(uuid4()),
                launch_command_id=command_id,
                owner=bootstrap.identity,
                child=identity,
                pid=child.pid,
                creation_time_100ns=child.creation_time_100ns,
            ),
            deadline_ns=deadline_ns,
        )
        if (
            not isinstance(confirmed, wire.LaunchReceipt)
            or confirmed.admission.result != pb.COMMAND_RESULT_ACCEPTED
            or confirmed.state.phase != wire.LAUNCH_PHASE_OS_CONFIRMED
        ):
            raise RuntimeError("renderer OS identity was not accepted")
        credentials[(identity.role, identity.generation)] = token
        descriptor = {
            "role": identity.role,
            "generation": identity.generation,
            "token": token,
            "owner_generation": bootstrap.identity.generation,
            "owner_token": bootstrap.token,
            "supervisor_generation": bootstrap.supervisor.generation,
            "supervisor_token": bootstrap.supervisor_token,
            "controller_generation": bootstrap.controller.generation,
            "owner_pid": bootstrap.pid,
            "owner_creation_time_100ns": bootstrap.creation_time_100ns,
            "supervisor_pid": bootstrap.supervisor_pid,
            "supervisor_creation_time_100ns": bootstrap.supervisor_creation_time_100ns,
            "coordinator_endpoint": f"127.0.0.1:{bootstrap.endpoint_port}",
            "supervisor_endpoint": f"127.0.0.1:{bootstrap.supervisor_port}",
            "launch_command_id": command_id,
            "pid": child.pid,
            "creation_time_100ns": child.creation_time_100ns,
            "registration_deadline_ns": deadline_ns,
            "max_message_bytes": bootstrap.max_message_bytes,
            "heartbeat_interval_ns": bootstrap.heartbeat_interval_ns,
            "health_silence_ns": bootstrap.health_silence_ns,
            "software_root": str(bootstrap.software_root),
            "context": base64.b64encode(
                visual_stimulus.WorkerContext(
                    worker=identity, owner=bootstrap.identity
                ).SerializeToString()
            ).decode("ascii"),
            "control_policies": base64.b64encode(
                bootstrap.policies.SerializeToString()
            ).decode("ascii"),
        }
        native.resume(child)
        writing_started = True
        await run_pipe_io_daemon(
            lambda: write_bootstrap(write, descriptor),
            timeout_s=max(0, (deadline_ns - host_time_ns()) / 1e9),
        )
        close_handle(read)
        read = -1
        while host_time_ns() < deadline_ns:
            state = await supervisor.call(
                "GetLaunchState",
                wire.LaunchQuery(
                    requester=bootstrap.identity, launch_command_id=command_id
                ),
                deadline_ns=deadline_ns,
            )
            if not isinstance(state, wire.LaunchState):
                raise TypeError("invalid renderer launch state")
            if state.phase == wire.LAUNCH_PHASE_OPERATIONAL:
                if not state.endpoint:
                    raise RuntimeError("renderer registration lacks endpoint")
                return RendererLaunch(
                    command_id,
                    child,
                    job_name,
                    identity,
                    token,
                    Peer(
                        state.endpoint,
                        Principal(
                            "visual_stimulus",
                            bootstrap.identity.generation,
                            bootstrap.token,
                        ),
                        bootstrap.max_message_bytes,
                        kind="worker",
                    ),
                )
            if state.phase in {
                wire.LAUNCH_PHASE_CLEANUP_REQUIRED,
                wire.LAUNCH_PHASE_RELEASED,
            }:
                raise RuntimeError("renderer startup failed; cleanup remains tracked")
            await asyncio.sleep(min(0.01, max(0, (deadline_ns - host_time_ns()) / 1e9)))
        raise TimeoutError("renderer registration missed its original deadline")
    finally:
        if read >= 0:
            close_handle(read)
        if not writing_started:
            close_handle(write)
        # Once dispatched, write_bootstrap retains and closes the handle.
