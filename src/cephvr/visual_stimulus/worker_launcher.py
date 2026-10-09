"""Registered Windows renderer creation under the existing E08 containment path."""

from __future__ import annotations

import base64
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.platform.windows.bootstrap import (
    BootstrapPipeWrite,
    create_bootstrap_pipe,
)
from cephvr.platform.windows.jobs import SuspendedProcess, WindowsJobs
from cephvr.platform.windows.python_runtime import (
    module_arguments,
    resolve_python_executable,
)
from cephvr.platform.windows.worker_launch import (
    BootstrapPipeHandles,
    launch_registered_worker,
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
    pending_bootstrap_writes: list[BootstrapPipeWrite],
    identity: pb.ProcessIdentity | None = None,
) -> RendererLaunch:
    identity = identity or pb.ProcessIdentity(
        role="visual_stimulus_renderer", generation=str(uuid4())
    )
    interpreter = resolve_python_executable(Path(sys.executable))
    command_id = str(uuid4())
    token = secrets.token_urlsafe(32)
    request = wire.PlanLaunchRequest(
        command_id=command_id,
        owner=bootstrap.identity,
        child=identity,
        executable=str(interpreter),
        python_worker=True,
        stop_method="grpc_shutdown",
    )
    job_name = ""
    launched_children: list[SuspendedProcess] = []
    pipes: BootstrapPipeHandles | None = None

    def make_pipes() -> BootstrapPipeHandles:
        nonlocal pipes
        pipes = BootstrapPipeHandles(*create_bootstrap_pipe())
        return pipes

    async def plan_launch(plan: wire.PlanLaunchRequest) -> wire.LaunchState:
        nonlocal job_name
        receipt = await supervisor.call(
            "PlanLaunch",
            plan,
            deadline_ns=deadline_ns,
            metadata=(("x-cephvr-child-token", token),),
        )
        if (
            not isinstance(receipt, wire.LaunchReceipt)
            or receipt.admission.result != pb.COMMAND_RESULT_ACCEPTED
        ):
            raise RuntimeError("supervisor did not plan renderer containment")
        job_name = receipt.state.containment_job_name
        return receipt.state

    def create_suspended(
        planned: wire.LaunchState, handles: BootstrapPipeHandles
    ) -> SuspendedProcess:
        native.open_launch_job(planned.containment_job_name)
        child = native.launch_suspended(
            str(interpreter),
            module_arguments(
                "cephvr.visual_stimulus.worker.main",
                ["--bootstrap-handle", str(handles.read_handle)],
            ),
            [planned.containment_job_name],
            (handles.read_handle,),
        )
        launched_children.append(child)
        return child

    async def confirm(child_process: SuspendedProcess) -> wire.LaunchState:
        receipt = await supervisor.call(
            "ConfirmLaunch",
            wire.ConfirmLaunchRequest(
                command_id=str(uuid4()),
                launch_command_id=command_id,
                owner=bootstrap.identity,
                child=identity,
                pid=child_process.pid,
                creation_time_100ns=child_process.creation_time_100ns,
            ),
            deadline_ns=deadline_ns,
        )
        if (
            not isinstance(receipt, wire.LaunchReceipt)
            or receipt.admission.result != pb.COMMAND_RESULT_ACCEPTED
        ):
            raise RuntimeError("renderer OS identity was not accepted")
        return receipt.state

    def build_descriptor(child_process: SuspendedProcess) -> dict[str, object]:
        return {
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
            "pid": child_process.pid,
            "creation_time_100ns": child_process.creation_time_100ns,
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

    def register(_child: SuspendedProcess, _document: dict[str, object]) -> None:
        credentials[(identity.role, identity.generation)] = token

    def retain_writer(attempt: BootstrapPipeWrite) -> None:
        pending_bootstrap_writes.append(attempt)

    def finish_writer(attempt: BootstrapPipeWrite) -> None:
        pending_bootstrap_writes.remove(attempt)

    async def get_launch_state() -> wire.LaunchState:
        state = await supervisor.call(
            "GetLaunchState",
            wire.LaunchQuery(
                requester=bootstrap.identity, launch_command_id=command_id
            ),
            deadline_ns=deadline_ns,
        )
        if not isinstance(state, wire.LaunchState):
            raise TypeError("invalid renderer launch state")
        return state

    try:
        child, state = await launch_registered_worker(
            request=request,
            create_pipes=make_pipes,
            plan=plan_launch,
            create_suspended=create_suspended,
            process_identity=lambda process: (
                process.pid,
                process.creation_time_100ns,
            ),
            confirm=confirm,
            descriptor=build_descriptor,
            register_peer=register,
            resume=native.resume,
            retain_writer=retain_writer,
            finish_writer=finish_writer,
            get_state=get_launch_state,
            deadline_ns=deadline_ns,
        )
    except BaseException as exc:
        if not launched_children and job_name:
            try:
                no_members = native.inspect_launch_job(job_name) == []
            except BaseException:
                no_members = False
            if no_members:
                await supervisor.call(
                    "ConfirmLaunch",
                    wire.ConfirmLaunchRequest(
                        command_id=str(uuid4()),
                        launch_command_id=command_id,
                        owner=bootstrap.identity,
                        child=identity,
                        creation_failed_without_child=True,
                        failure=pb.Failure(
                            code="RENDERER_CREATE", message=str(exc)[:2048]
                        ),
                    ),
                    deadline_ns=deadline_ns,
                )
        raise
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
