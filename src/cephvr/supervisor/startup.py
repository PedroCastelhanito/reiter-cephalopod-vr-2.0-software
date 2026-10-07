"""Windows supervisor process assembly and managed launch (E08)."""

from __future__ import annotations

import asyncio
import os
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.platform.windows.bootstrap import (
    close_handle,
    create_bootstrap_pipe,
    run_pipe_io_daemon,
    write_bootstrap,
)
from cephvr.platform.windows.jobs import (
    SuspendedProcess,
    WindowsJobs,
    WindowsLaunchError,
)
from cephvr.platform.windows.python_runtime import (
    module_arguments,
    resolve_python_executable,
)
from cephvr.shared.clock import HostClockDescriptor
from cephvr.shared.managed_modules import REQUIRED_MODULES, missing_roles
from cephvr.shared.transport_deadlines import remaining_seconds
from cephvr.supervisor.outbound import GrpcOutbound
from cephvr.supervisor.registry import LaunchRegistry
from cephvr.supervisor.runtime import SupervisorRuntime
from cephvr.supervisor.service import start_supervisor_server


@dataclass(frozen=True)
class LaunchInputs:
    bootstrap: dict[str, object]
    native: WindowsJobs
    registry: LaunchRegistry
    clock: HostClockDescriptor
    outbound: GrpcOutbound
    identity: types.ProcessIdentity
    controller: types.ProcessIdentity
    software_root: Path
    max_message_bytes: int
    role_bootstrap: dict[str, tuple[str, str]]
    role_plans: dict[str, wire.PlanLaunchRequest]
    role_states: dict[str, wire.LaunchState]


async def launch_controller(
    inputs: LaunchInputs, controller_control_handle: int
) -> SuspendedProcess:
    """Register and start the controller before releasing its bootstrap."""
    plan = wire.PlanLaunchRequest(
        command_id=str(uuid4()),
        owner=inputs.identity,
        child=inputs.controller,
        executable=str(inputs.bootstrap["interpreter"]),
        python_worker=True,
        stop_method="grpc_shutdown",
    )
    state = inputs.registry.plan(plan)
    pipe_read, pipe_write = create_bootstrap_pipe()
    # On an exception, the dedicated job remains registered as a partial
    # child and the launcher's outer job supplies the final backstop.
    child = inputs.native.launch_suspended(
        str(inputs.bootstrap["interpreter"]),
        module_arguments(
            "cephvr.controller.main", ["--bootstrap-handle", str(pipe_read)]
        ),
        [state.containment_job_name],
        (pipe_read, controller_control_handle),
    )
    inputs.registry.confirm(
        wire.ConfirmLaunchRequest(
            command_id=str(uuid4()),
            launch_command_id=plan.command_id,
            owner=inputs.identity,
            child=inputs.controller,
            pid=child.pid,
            creation_time_100ns=child.creation_time_100ns,
        ),
        inputs.clock,
    )
    inputs.native.resume(child)
    close_handle(pipe_read)
    close_handle(controller_control_handle)
    controller_descriptor = {
        "software_root": str(inputs.software_root),
        "supervisor_generation": inputs.identity.generation,
        "controller_generation": inputs.controller.generation,
        "controller_token": str(inputs.bootstrap["controller_token"]),
        "supervisor_token": str(inputs.bootstrap["supervisor_token"]),
        "supervisor_port": int(str(inputs.bootstrap["supervisor_port"])),
        "controller_port": int(str(inputs.bootstrap["controller_port"])),
        "max_message_bytes": inputs.max_message_bytes,
        "backends": [
            {
                "backend_name": role,
                "backend_generation": inputs.role_bootstrap[role][0],
                "endpoint": f"127.0.0.1:{inputs.outbound.backend_ports[role]}",
                "token": inputs.role_bootstrap[role][1],
                "launch_confirmed": False,
            }
            for role in ("acquisition", "visual_stimulus", "tracking")
        ],
        "launch_command_id": plan.command_id,
        "pid": child.pid,
        "creation_time_100ns": child.creation_time_100ns,
        "supervisor_pid": int(str(inputs.bootstrap["supervisor_pid"])),
        "supervisor_creation_time_100ns": int(
            str(inputs.bootstrap["supervisor_creation_time_100ns"])
        ),
        "launcher_control_handle": controller_control_handle,
        "managed_jobs": [
            {
                "role": role,
                "generation": inputs.role_bootstrap[role][0],
                "job_name": inputs.role_states[role].containment_job_name,
            }
            for role in ("acquisition", "visual_stimulus", "tracking", "gui")
        ],
    }
    await run_pipe_io_daemon(
        lambda: write_bootstrap(pipe_write, controller_descriptor),
        timeout_s=15,
    )

    return child


async def _launch_role_plan(
    inputs: LaunchInputs,
    role: str,
    module: str,
    controller_child: SuspendedProcess,
    generation: str,
    token: str,
    role_plan: wire.PlanLaunchRequest,
    state: wire.LaunchState,
    deadline_ns: int | None = None,
) -> SuspendedProcess:
    """Launch one exact supervisor-owned plan and release its one-use bootstrap."""

    def timeout() -> float:
        value = 15.0 if deadline_ns is None else remaining_seconds(deadline_ns)
        if value <= 0:
            raise TimeoutError("GUI relaunch deadline expired")
        return value

    timeout()
    child_identity = types.ProcessIdentity(role=role, generation=generation)
    role_read, role_write = create_bootstrap_pipe()
    role_child = inputs.native.launch_suspended(
        str(inputs.bootstrap["interpreter"]),
        module_arguments(module, ["--bootstrap-handle", str(role_read)]),
        [state.containment_job_name],
        (role_read,),
    )
    try:
        timeout()
    except TimeoutError:
        inputs.native.terminate_exact(role_child.pid, role_child.creation_time_100ns)
        close_handle(role_read)
        close_handle(role_write)
        raise
    inputs.registry.confirm(
        wire.ConfirmLaunchRequest(
            command_id=str(uuid4()),
            launch_command_id=role_plan.command_id,
            owner=inputs.identity,
            child=child_identity,
            pid=role_child.pid,
            creation_time_100ns=role_child.creation_time_100ns,
        ),
        inputs.clock,
    )
    inputs.native.resume(role_child)
    close_handle(role_read)
    role_descriptor = {
        "role": role,
        "generation": generation,
        "controller_generation": inputs.controller.generation,
        "supervisor_generation": inputs.identity.generation,
        "controller_port": int(str(inputs.bootstrap["controller_port"])),
        "supervisor_port": int(str(inputs.bootstrap["supervisor_port"])),
        "endpoint_port": inputs.outbound.backend_ports.get(role),
        "max_message_bytes": inputs.max_message_bytes,
        "heartbeat_interval_ns": int(str(inputs.bootstrap["heartbeat_interval_ns"])),
        "health_silence_ns": int(str(inputs.bootstrap["silence_timeout_ns"])),
        "launch_command_id": role_plan.command_id,
        "pid": role_child.pid,
        "creation_time_100ns": role_child.creation_time_100ns,
        "controller_pid": controller_child.pid,
        "controller_creation_time_100ns": controller_child.creation_time_100ns,
        "supervisor_pid": int(str(inputs.bootstrap["supervisor_pid"])),
        "supervisor_creation_time_100ns": int(
            str(inputs.bootstrap["supervisor_creation_time_100ns"])
        ),
        "software_root": str(inputs.software_root),
    }
    if role != "gui":
        role_descriptor["token"] = token
        role_descriptor["controller_token"] = str(inputs.bootstrap["controller_token"])
        role_descriptor["supervisor_token"] = str(inputs.bootstrap["supervisor_token"])
    if role in {"acquisition", "visual_stimulus", "tracking"}:
        policy_descriptor = inputs.bootstrap.get("control_policies")
        if not isinstance(policy_descriptor, str) or not policy_descriptor:
            raise WindowsLaunchError(
                "resolved ControlPolicies are missing from backend startup"
            )
        role_descriptor["control_policies"] = policy_descriptor
    if role == "acquisition":
        # Tracking's exact process generation is created and owned by this
        # supervisor launch plan. Acquisition needs only this identity to set the
        # TRACKING ring consumer; no token or second lookup authority is needed.
        role_descriptor["tracking_generation"] = inputs.role_bootstrap["tracking"][0]
    await run_pipe_io_daemon(
        lambda: write_bootstrap(role_write, role_descriptor),
        timeout_s=timeout(),
    )
    return role_child


async def launch_role(
    inputs: LaunchInputs, role: str, module: str, controller_child: SuspendedProcess
) -> None:
    """Start one preplanned role in its existing containment job."""
    generation, token = inputs.role_bootstrap[role]
    role_plan = inputs.role_plans[role]
    state = inputs.role_states[role]
    role_child = await _launch_role_plan(
        inputs,
        role,
        module,
        controller_child,
        generation,
        token,
        role_plan,
        state,
    )
    if role == "gui":
        await inputs.outbound.register_gui_launch(
            types.ProcessIdentity(role=role, generation=generation),
            role_plan.command_id,
            role_child.pid,
            role_child.creation_time_100ns,
        )


def validate_bootstrap(bootstrap: dict[str, object]) -> dict[str, str]:
    """Reject incomplete startup descriptors and unavailable managed roles."""
    if sys.platform != "win32":
        raise WindowsLaunchError("CephVR supervisor launch requires Windows")
    required = (
        "software_root",
        "supervisor_generation",
        "controller_generation",
        "supervisor_token",
        "controller_token",
        "supervisor_port",
        "controller_port",
        "supervisor_config",
        "interpreter",
        "backend_ports",
        "max_message_bytes",
        "max_retained_incidents",
        "command_retention_ns",
        "control_policies",
        "silence_timeout_ns",
        "emergency_timeout_ns",
        "graceful_exit_ns",
        "terminate_exit_ns",
        "application_backstop_ns",
        "heartbeat_interval_ns",
    )
    if any(key not in bootstrap for key in required):
        raise WindowsLaunchError("bootstrap descriptor is incomplete")
    if (
        not isinstance(bootstrap["control_policies"], str)
        or not bootstrap["control_policies"]
    ):
        raise WindowsLaunchError("resolved control policies are missing")
    missing = missing_roles()
    if missing:
        raise WindowsLaunchError(
            "required managed bootstrap modules are unavailable: " + ", ".join(missing)
        )
    bootstrap["interpreter"] = str(
        resolve_python_executable(Path(str(bootstrap["interpreter"])))
    )
    return REQUIRED_MODULES


async def run_supervisor(
    bootstrap: dict[str, object],
    control_handle: int,
    ack_handle: int,
    controller_control_handle: int,
) -> None:
    required_modules = validate_bootstrap(bootstrap)
    software_root = Path(str(bootstrap["software_root"]))
    identity = types.ProcessIdentity(
        role="supervisor", generation=str(bootstrap["supervisor_generation"])
    )
    controller = types.ProcessIdentity(
        role="controller", generation=str(bootstrap["controller_generation"])
    )
    native = WindowsJobs()
    raw_ports = bootstrap["backend_ports"]
    if not isinstance(raw_ports, dict) or set(raw_ports) != {
        "acquisition",
        "visual_stimulus",
        "tracking",
    }:
        raise WindowsLaunchError("backend port registry is invalid")
    backend_ports = {key: int(str(value)) for key, value in raw_ports.items()}
    max_message_bytes = int(str(bootstrap["max_message_bytes"]))
    outbound = GrpcOutbound(
        identity,
        str(bootstrap["supervisor_token"]),
        int(str(bootstrap["controller_port"])),
        control_handle,
        max_message_bytes,
        backend_ports,
    )
    runtime = SupervisorRuntime(
        identity=identity,
        controller=controller,
        credentials={
            ("supervisor", identity.generation): str(bootstrap["supervisor_token"]),
            ("controller", controller.generation): str(bootstrap["controller_token"]),
        },
        native=native,
        outbound=outbound,
        software_root=software_root,
        silence_timeout_ns=int(str(bootstrap["silence_timeout_ns"])),
        emergency_timeout_ns=int(str(bootstrap["emergency_timeout_ns"])),
        application_backstop_ns=int(str(bootstrap["application_backstop_ns"])),
        graceful_exit_ns=int(str(bootstrap["graceful_exit_ns"])),
        terminate_exit_ns=int(str(bootstrap["terminate_exit_ns"])),
        heartbeat_interval_ns=int(str(bootstrap["heartbeat_interval_ns"])),
        max_message_bytes=max_message_bytes,
        max_retained_entries=int(str(bootstrap["max_retained_incidents"])),
        command_retention_ns=int(str(bootstrap["command_retention_ns"])),
        gate_controller_ack=True,
    )
    outbound.bind_registry(runtime.registry)
    server = await start_supervisor_server(
        runtime.service, int(str(bootstrap["supervisor_port"]))
    )
    runtime.start_background()
    role_launches: asyncio.Future[list[None]] | None = None
    try:
        role_bootstrap: dict[str, tuple[str, str]] = {
            role: (str(uuid4()), secrets.token_urlsafe(48)) for role in required_modules
        }
        for role, (generation, token) in role_bootstrap.items():
            runtime.credentials[(role, generation)] = token
        role_plans: dict[str, wire.PlanLaunchRequest] = {}
        role_states: dict[str, wire.LaunchState] = {}
        for role, (generation, _) in role_bootstrap.items():
            role_plan = wire.PlanLaunchRequest(
                command_id=str(uuid4()),
                owner=identity,
                child=types.ProcessIdentity(role=role, generation=generation),
                executable=str(bootstrap["interpreter"]),
                python_worker=True,
                stop_method="grpc_shutdown",
            )
            role_plans[role] = role_plan
            role_states[role] = runtime.registry.plan(role_plan)
        inputs = LaunchInputs(
            bootstrap=bootstrap,
            native=native,
            registry=runtime.registry,
            clock=runtime.clock,
            outbound=outbound,
            identity=identity,
            controller=controller,
            software_root=software_root,
            max_message_bytes=max_message_bytes,
            role_bootstrap=role_bootstrap,
            role_plans=role_plans,
            role_states=role_states,
        )
        child = await launch_controller(inputs, controller_control_handle)
        role_launches = asyncio.gather(
            *(
                launch_role(inputs, role, module, child)
                for role, module in required_modules.items()
            )
        )
        await outbound.register_controller(
            controller, child.pid, child.creation_time_100ns
        )
        ack = await run_pipe_io_daemon(lambda: os.read(ack_handle, 1), timeout_s=15)
        if ack != b"A":
            raise WindowsLaunchError("launcher did not retain exact controller handle")
        runtime.acknowledge_controller_registration()
        await role_launches

        active_gui_command = {"command_id": role_plans["gui"].command_id}
        gui_launch_lock = asyncio.Lock()

        async def relaunch_gui(
            request: wire.PlanLaunchRequest,
            planned: wire.LaunchState,
            token: str,
            deadline_ns: int,
        ) -> wire.LaunchState:
            async with gui_launch_lock:
                if (
                    request.owner != identity
                    or request.child.role != "gui"
                    or request.executable != str(bootstrap["interpreter"])
                    or not request.python_worker
                    or request.stop_method != "grpc_shutdown"
                    or request.HasField("work")
                    or request.HasField("parent_operation")
                ):
                    raise WindowsLaunchError(
                        "GUI relaunch plan is outside launcher policy"
                    )
                if request.command_id == active_gui_command["command_id"]:
                    return runtime.registry.refresh(request.command_id)
                previous = runtime.registry.refresh(active_gui_command["command_id"])
                if previous.phase != wire.LAUNCH_PHASE_RELEASED:
                    raise WindowsLaunchError(
                        "prior GUI launch is not confirmed released"
                    )
                active_gui_command["command_id"] = request.command_id
                role_child = await _launch_role_plan(
                    inputs,
                    "gui",
                    "cephvr.gui.main",
                    child,
                    request.child.generation,
                    token,
                    request,
                    planned,
                    deadline_ns,
                )
                await outbound.register_gui_launch(
                    request.child,
                    request.command_id,
                    role_child.pid,
                    role_child.creation_time_100ns,
                )
                return runtime.registry.refresh(request.command_id)

        runtime.service.gui_launch_handler = relaunch_gui
        await runtime.wait_until_shutdown()
    finally:
        if role_launches is not None and not role_launches.done():
            # A failed controller registration must not leave role launches running.
            role_launches.cancel()
        if role_launches is not None:
            await asyncio.gather(role_launches, return_exceptions=True)
        runtime.stop_background()
        await server.stop(grace=0)
        await runtime.close_outbound()
