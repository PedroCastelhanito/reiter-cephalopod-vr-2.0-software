"""Windows supervisor process bootstrap and loopback gRPC hosting."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import secrets
import sys
from functools import partial
from pathlib import Path
from uuid import uuid4

import grpc

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import services_pb2_grpc
from cephvr.control.v1 import types_pb2 as types
from cephvr.platform.windows.bootstrap import (
    close_handle,
    create_bootstrap_pipe,
    read_bootstrap,
    run_pipe_io_daemon,
    write_bootstrap,
)
from cephvr.platform.windows.guard import SingleInstanceGuard
from cephvr.platform.windows.jobs import WindowsJobs, WindowsLaunchError
from cephvr.shared.clock import host_time_ns
from cephvr.supervisor.runtime import SupervisorRuntime, start_supervisor_server


class GrpcOutbound:
    def __init__(
        self,
        identity: types.ProcessIdentity,
        token: str,
        controller_port: int,
        control_handle: int,
        max_message_bytes: int,
        backend_ports: dict[str, int],
    ) -> None:
        self.identity = identity
        self.metadata = (
            ("x-cephvr-role", identity.role),
            ("x-cephvr-generation", identity.generation),
            ("x-cephvr-token", token),
        )
        options = [
            ("grpc.max_send_message_length", max_message_bytes),
            ("grpc.max_receive_message_length", max_message_bytes),
        ]
        self.controller_channel = grpc.aio.insecure_channel(
            f"127.0.0.1:{controller_port}", options=options
        )
        self.controller = services_pb2_grpc.ExperimentControllerServiceStub(
            self.controller_channel
        )  # type: ignore[no-untyped-call]
        self.backend_ports = backend_ports
        self.options = options
        self.backend_channels: dict[str, grpc.aio.Channel] = {}
        self.control_handle = control_handle
        self.control_lock = asyncio.Lock()

    async def report_interruption(self, report: wire.InterruptionReport) -> None:
        receipt = await self.controller.ReportInterruption(
            report, metadata=self.metadata, timeout=5
        )
        if receipt.result != types.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError(
                f"controller rejected interruption: {receipt.failure.code}"
            )

    async def report_status(self, report: wire.SupervisorStatusReport) -> None:
        receipt = await self.controller.ReportSupervisorStatus(
            report, metadata=self.metadata, timeout=5
        )
        if receipt.result != types.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError(f"controller rejected status: {receipt.failure.code}")

    async def report_heartbeat(self, report: types.HeartbeatReport) -> None:
        receipt = await self.controller.ReportHeartbeat(
            report, metadata=self.metadata, timeout=5
        )
        if receipt.result != types.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError(
                f"controller rejected supervisor heartbeat: {receipt.failure.code}"
            )

    def _backend(
        self, target: types.BackendContext
    ) -> services_pb2_grpc.BackendServiceStub:
        if target.backend_name not in self.backend_ports:
            raise RuntimeError(
                f"no declared backend endpoint for {target.backend_name}"
            )
        channel = self.backend_channels.get(target.backend_name)
        if channel is None:
            channel = grpc.aio.insecure_channel(
                f"127.0.0.1:{self.backend_ports[target.backend_name]}",
                options=self.options,
            )
            self.backend_channels[target.backend_name] = channel
        return services_pb2_grpc.BackendServiceStub(channel)  # type: ignore[no-untyped-call]

    async def interrupt_backend(
        self, target: types.BackendContext, request: wire.InterruptSessionRequest
    ) -> None:
        receipt = await self._backend(target).InterruptSession(
            request, metadata=self.metadata, timeout=5
        )
        if receipt.result != types.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError(
                f"backend {target.backend_name} rejected interruption: {receipt.failure.code}"
            )

    async def shutdown_backend(
        self, target: types.BackendContext, request: wire.BackendCommand
    ) -> None:
        receipt = await self._backend(target).Shutdown(
            request, metadata=self.metadata, timeout=5
        )
        if receipt.result != types.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError(
                f"backend {target.backend_name} rejected shutdown: {receipt.failure.code}"
            )

    async def cleanup_backend(
        self, target: types.BackendContext, request: wire.BackendCommand
    ) -> None:
        receipt = await self._backend(target).Cleanup(
            request, metadata=self.metadata, timeout=5
        )
        if receipt.result != types.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError(
                f"backend {target.backend_name} rejected cleanup: {receipt.failure.code}"
            )

    async def notify_launcher_shutdown(self, deadline_ns: int, cause: str) -> None:
        document = {
            "kind": "shutdown",
            "supervisor_generation": self.identity.generation,
            "deadline_monotonic_ns": deadline_ns,
            "cause": cause,
        }
        await self._notify(document)

    async def register_controller(
        self, controller: types.ProcessIdentity, pid: int, created: int
    ) -> None:
        await self._notify(
            {
                "kind": "register_controller",
                "supervisor_generation": self.identity.generation,
                "controller_generation": controller.generation,
                "pid": pid,
                "creation_time_100ns": created,
            }
        )

    async def _notify(self, document: dict[str, object]) -> None:
        encoded = json.dumps(document, separators=(",", ":")).encode() + b"\n"
        if len(encoded) > 8192:
            raise RuntimeError("launcher notification too large")
        async with self.control_lock:
            offset = 0
            while offset < len(encoded):
                written = await run_pipe_io_daemon(
                    partial(os.write, self.control_handle, encoded[offset:]),
                    timeout_s=5,
                )
                if written <= 0:
                    raise RuntimeError("launcher control pipe closed")
                offset += written


async def run_supervisor(
    bootstrap: dict[str, object],
    control_handle: int,
    ack_handle: int,
    controller_control_handle: int,
) -> None:
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
        "silence_timeout_ns",
        "emergency_timeout_ns",
        "graceful_exit_ns",
        "terminate_exit_ns",
        "application_backstop_ns",
        "heartbeat_interval_ns",
    )
    if any(key not in bootstrap for key in required):
        raise WindowsLaunchError("bootstrap descriptor is incomplete")
    required_modules = {
        "acquisition": "cephvr.acquisition.main",
        "vr": "cephvr.vr.main",
        "tracking": "cephvr.tracking.main",
        "gui": "cephvr.gui.main",
    }
    missing = []
    for role, module in required_modules.items():
        try:
            present = importlib.util.find_spec(module) is not None
        except ModuleNotFoundError:
            present = False
        if not present:
            missing.append(role)
    if missing:
        raise WindowsLaunchError(
            "required managed bootstrap modules are unavailable: " + ", ".join(missing)
        )
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
        "vr",
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
    server = await start_supervisor_server(
        runtime, int(str(bootstrap["supervisor_port"]))
    )
    monitor = asyncio.create_task(runtime.monitor())
    heartbeat = asyncio.create_task(runtime.heartbeat_loop())
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
        plan = wire.PlanLaunchRequest(
            command_id=str(uuid4()),
            owner=identity,
            child=controller,
            executable=str(bootstrap["interpreter"]),
            python_worker=True,
            stop_method="grpc_shutdown",
        )
        state = runtime.registry.plan(plan)
        pipe_read, pipe_write = create_bootstrap_pipe()
        try:
            child = native.launch_suspended(
                str(bootstrap["interpreter"]),
                ["-m", "cephvr.controller.main", "--bootstrap-handle", str(pipe_read)],
                [state.containment_job_name],
                (pipe_read, controller_control_handle),
            )
            runtime.registry.confirm(
                wire.ConfirmLaunchRequest(
                    command_id=str(uuid4()),
                    launch_command_id=plan.command_id,
                    owner=identity,
                    child=controller,
                    pid=child.pid,
                    creation_time_100ns=child.creation_time_100ns,
                ),
                runtime.clock,
            )
            native.resume(child)
            close_handle(pipe_read)
            close_handle(controller_control_handle)
            controller_descriptor = {
                "software_root": str(software_root),
                "supervisor_generation": identity.generation,
                "controller_generation": controller.generation,
                "controller_token": str(bootstrap["controller_token"]),
                "supervisor_token": str(bootstrap["supervisor_token"]),
                "supervisor_port": int(str(bootstrap["supervisor_port"])),
                "controller_port": int(str(bootstrap["controller_port"])),
                "max_message_bytes": max_message_bytes,
                "backends": [
                    {
                        "backend_name": role,
                        "backend_generation": role_bootstrap[role][0],
                        "endpoint": f"127.0.0.1:{outbound.backend_ports[role]}",
                        "token": role_bootstrap[role][1],
                        "launch_confirmed": False,
                    }
                    for role in ("acquisition", "vr", "tracking")
                ],
                "launch_command_id": plan.command_id,
                "pid": child.pid,
                "creation_time_100ns": child.creation_time_100ns,
                "supervisor_pid": int(str(bootstrap["supervisor_pid"])),
                "supervisor_creation_time_100ns": int(
                    str(bootstrap["supervisor_creation_time_100ns"])
                ),
                "launcher_control_handle": controller_control_handle,
                "managed_jobs": [
                    {
                        "role": role,
                        "generation": role_bootstrap[role][0],
                        "job_name": role_states[role].containment_job_name,
                    }
                    for role in ("acquisition", "vr", "tracking", "gui")
                ],
            }
            await run_pipe_io_daemon(
                lambda: write_bootstrap(pipe_write, controller_descriptor),
                timeout_s=15,
            )
        finally:
            # On an exception, the dedicated job remains registered as a partial
            # child and the launcher's outer job supplies the final backstop.
            pass

        async def launch_role(role: str, module: str) -> None:
            generation, token = role_bootstrap[role]
            child_identity = types.ProcessIdentity(role=role, generation=generation)
            role_plan = role_plans[role]
            state = role_states[role]
            role_read, role_write = create_bootstrap_pipe()
            role_child = native.launch_suspended(
                str(bootstrap["interpreter"]),
                ["-m", module, "--bootstrap-handle", str(role_read)],
                [state.containment_job_name],
                (role_read,),
            )
            runtime.registry.confirm(
                wire.ConfirmLaunchRequest(
                    command_id=str(uuid4()),
                    launch_command_id=role_plan.command_id,
                    owner=identity,
                    child=child_identity,
                    pid=role_child.pid,
                    creation_time_100ns=role_child.creation_time_100ns,
                ),
                runtime.clock,
            )
            native.resume(role_child)
            close_handle(role_read)
            role_descriptor = {
                "role": role,
                "generation": generation,
                "token": token,
                "controller_token": str(bootstrap["controller_token"]),
                "supervisor_token": str(bootstrap["supervisor_token"]),
                "controller_generation": controller.generation,
                "supervisor_generation": identity.generation,
                "controller_port": int(str(bootstrap["controller_port"])),
                "supervisor_port": int(str(bootstrap["supervisor_port"])),
                "endpoint_port": outbound.backend_ports.get(role),
                "max_message_bytes": max_message_bytes,
                "launch_command_id": role_plan.command_id,
                "pid": role_child.pid,
                "creation_time_100ns": role_child.creation_time_100ns,
                "controller_pid": child.pid,
                "controller_creation_time_100ns": child.creation_time_100ns,
                "supervisor_pid": int(str(bootstrap["supervisor_pid"])),
                "supervisor_creation_time_100ns": int(
                    str(bootstrap["supervisor_creation_time_100ns"])
                ),
                "software_root": str(software_root),
            }
            await run_pipe_io_daemon(
                lambda: write_bootstrap(role_write, role_descriptor),
                timeout_s=15,
            )

        role_launches = asyncio.gather(
            *(launch_role(role, module) for role, module in required_modules.items())
        )
        await outbound.register_controller(
            controller, child.pid, child.creation_time_100ns
        )
        ack = await run_pipe_io_daemon(lambda: os.read(ack_handle, 1), timeout_s=15)
        if ack != b"A":
            raise WindowsLaunchError("launcher did not retain exact controller handle")
        runtime.acknowledge_controller_registration()
        await role_launches
        while not runtime.shutdown_complete.is_set():
            for task in (
                monitor,
                heartbeat,
                runtime._safety_task,
                runtime._shutdown_task,
            ):
                if task is not None and task.done():
                    failure = task.exception()
                    if failure is not None:
                        raise WindowsLaunchError(
                            "supervisor safety/monitor task failed; launcher backstop owns containment"
                        ) from failure
                    if task in (monitor, heartbeat):
                        raise WindowsLaunchError(
                            "supervisor authority loop stopped unexpectedly"
                        )
            if (
                runtime._shutdown_deadline_ns is not None
                and host_time_ns() >= runtime._shutdown_deadline_ns
            ):
                raise WindowsLaunchError(
                    "application backstop reached without verified process absence"
                )
            await asyncio.sleep(0.05)
    finally:
        monitor.cancel()
        heartbeat.cancel()
        await server.stop(grace=0)


def main() -> None:
    parser = argparse.ArgumentParser(description="CephVR supervisor")
    parser.add_argument("--bootstrap-handle", type=int, required=True)
    parser.add_argument("--launcher-control-handle", type=int, required=True)
    parser.add_argument("--launcher-controller-control-handle", type=int, required=True)
    parser.add_argument("--launcher-ack-handle", type=int, required=True)
    args = parser.parse_args()
    descriptor = read_bootstrap(args.bootstrap_handle)
    # The retained inherited handle is the local generation-bound launcher channel.
    import msvcrt

    control_fd = msvcrt.open_osfhandle(args.launcher_control_handle, os.O_WRONLY)
    ack_fd = msvcrt.open_osfhandle(args.launcher_ack_handle, os.O_RDONLY)
    with SingleInstanceGuard("supervisor"):
        asyncio.run(
            run_supervisor(
                descriptor,
                control_fd,
                ack_fd,
                args.launcher_controller_control_handle,
            )
        )


if __name__ == "__main__":
    main()
