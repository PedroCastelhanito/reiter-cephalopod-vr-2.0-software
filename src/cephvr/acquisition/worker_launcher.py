"""Contained worker launch, protected bootstrap and endpoint registration."""

from __future__ import annotations

import asyncio
import base64
import secrets
import sys
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import grpc

from cephvr.acquisition.identity import process_role_for_camera
from cephvr.acquisition.ports import (
    SupervisorPort,
    WorkerBootstrapPort,
    WorkerLaunchResult,
    WorkerLaunchSpec,
)
from cephvr.acquisition.transport.grpc_ports import GrpcWorkerPort
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.bootstrap import (
    BootstrapPipeWrite,
    create_bootstrap_pipe,
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
from cephvr.platform.windows.worker_launch import (
    BootstrapPipeHandles,
    launch_registered_worker,
)
from cephvr.shared.auth import Principal
from cephvr.shared.clock import host_time_ns

PeerRegistrar = Callable[[control.ProcessIdentity, str], None]
PeerRevoker = Callable[[control.ProcessIdentity], None]


class WindowsWorkerBootstrapPort(WorkerBootstrapPort):
    """Start one exact worker in the supervisor-planned containment job."""

    def __init__(
        self,
        *,
        native: WindowsJobs,
        supervisor: SupervisorPort,
        owner: control.ProcessIdentity,
        owner_token: str,
        supervisor_identity: control.ProcessIdentity,
        supervisor_token: str,
        supervisor_endpoint: str,
        coordinator_endpoint: str,
        python_executable: Path,
        max_message_bytes: int,
        register_peer: PeerRegistrar,
        revoke_peer: PeerRevoker,
    ) -> None:
        if sys.platform != "win32":
            raise WindowsLaunchError("acquisition worker launch requires Windows")
        if max_message_bytes <= 0:
            raise ValueError("worker gRPC message limit must be positive")
        self.native = native
        self.supervisor = supervisor
        self.owner = control.ProcessIdentity.FromString(owner.SerializeToString())
        self.owner_token = owner_token
        self.supervisor_identity = control.ProcessIdentity.FromString(
            supervisor_identity.SerializeToString()
        )
        self.supervisor_token = supervisor_token
        self.supervisor_endpoint = supervisor_endpoint
        self.coordinator_endpoint = coordinator_endpoint
        self.python_executable = resolve_python_executable(python_executable)
        self.max_message_bytes = max_message_bytes
        self.register_peer = register_peer
        self.revoke_peer = revoke_peer
        self._pending_bootstrap_writes: list[BootstrapPipeWrite] = []
        self._retained_processes: dict[str, tuple[str, int, int]] = {}

    async def launch(
        self, spec: WorkerLaunchSpec, *, deadline_ns: int
    ) -> WorkerLaunchResult:
        if host_time_ns() >= deadline_ns:
            raise TimeoutError("worker registration deadline expired before PlanLaunch")
        context = spec.context
        expected_role = process_role_for_camera(context.camera)
        if (
            context.worker.role != expected_role
            or context.owner != self.owner
            or spec.parent_operation.command_id == ""
            or spec.launch_command_id == ""
            or spec.executable != self.python_executable
            or not spec.python_worker
        ):
            raise ValueError(
                "worker launch specification is not the accepted exact role"
            )

        plan = wire.PlanLaunchRequest(
            command_id=spec.launch_command_id,
            owner=self.owner,
            child=context.worker,
            parent_operation=spec.parent_operation,
            executable=str(self.python_executable),
            python_worker=True,
            stop_method=spec.stop_method,
        )
        if context.work.WhichOneof("work") is not None:
            plan.work.CopyFrom(context.work)
        worker_token = secrets.token_urlsafe(32)
        planned_job_name = ""
        launched_children: list[SuspendedProcess] = []
        pipes: BootstrapPipeHandles | None = None

        def make_pipes() -> BootstrapPipeHandles:
            nonlocal pipes
            pipes = BootstrapPipeHandles(*create_bootstrap_pipe())
            return pipes

        async def plan_launch(
            request: wire.PlanLaunchRequest,
        ) -> wire.LaunchState:
            nonlocal planned_job_name
            receipt = await self.supervisor.plan_launch(
                request, deadline_ns=deadline_ns, child_token=worker_token
            )
            if receipt.admission.result != control.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(_admission_failure(receipt.admission))
            planned_job_name = receipt.state.containment_job_name
            return receipt.state

        def create_suspended(
            planned: wire.LaunchState, handles: BootstrapPipeHandles
        ) -> SuspendedProcess:
            self.native.open_launch_job(planned.containment_job_name)
            child = self.native.launch_suspended(
                str(self.python_executable),
                module_arguments(
                    "cephvr.acquisition.worker.main",
                    ["--bootstrap-handle", str(handles.read_handle)],
                ),
                [planned.containment_job_name],
                (handles.read_handle,),
            )
            self._retained_processes[context.worker.generation] = (
                planned.containment_job_name,
                child.pid,
                child.creation_time_100ns,
            )
            launched_children.append(child)
            return child

        async def confirm(child_process: SuspendedProcess) -> wire.LaunchState:
            receipt = await self.supervisor.confirm_launch(
                wire.ConfirmLaunchRequest(
                    command_id=str(uuid4()),
                    launch_command_id=spec.launch_command_id,
                    owner=self.owner,
                    child=context.worker,
                    pid=child_process.pid,
                    creation_time_100ns=child_process.creation_time_100ns,
                ),
                deadline_ns=deadline_ns,
            )
            if receipt.admission.result != control.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(_admission_failure(receipt.admission))
            return receipt.state

        def build_descriptor(child_process: SuspendedProcess) -> dict[str, object]:
            descriptor, _token = self._descriptor(
                spec,
                pid=child_process.pid,
                creation_time_100ns=child_process.creation_time_100ns,
                registration_deadline_ns=deadline_ns,
                worker_token=worker_token,
            )
            return descriptor

        def register(
            _child_process: SuspendedProcess, _descriptor: dict[str, object]
        ) -> None:
            self.register_peer(context.worker, worker_token)

        def retain_writer(attempt: BootstrapPipeWrite) -> None:
            self._pending_bootstrap_writes.append(attempt)

        def finish_writer(attempt: BootstrapPipeWrite) -> None:
            self._pending_bootstrap_writes.remove(attempt)

        try:
            child, state = await launch_registered_worker(
                request=plan,
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
                resume=self.native.resume,
                retain_writer=retain_writer,
                finish_writer=finish_writer,
                get_state=lambda: self.supervisor.get_launch_state(
                    wire.LaunchQuery(
                        requester=self.owner,
                        launch_command_id=spec.launch_command_id,
                    ),
                    deadline_ns=deadline_ns,
                ),
                deadline_ns=deadline_ns,
            )
        except BaseException as exc:
            members: list[tuple[int, int, str]] | None = None
            if not launched_children and planned_job_name:
                try:
                    members = self.native.inspect_launch_job(planned_job_name)
                except BaseException:
                    pass
            if not launched_children and members == []:
                await self._confirm_creation_failure(spec, exc, deadline_ns)
            raise
        channel = grpc.aio.insecure_channel(
            state.endpoint,
            options=(
                ("grpc.max_send_message_length", self.max_message_bytes),
                ("grpc.max_receive_message_length", self.max_message_bytes),
            ),
        )
        worker_port = GrpcWorkerPort(
            channel,
            Principal(self.owner.role, self.owner.generation, self.owner_token),
            context,
        )
        return WorkerLaunchResult(
            context=context,
            port=worker_port,
            pid=child.pid,
            creation_time_100ns=child.creation_time_100ns,
            endpoint=state.endpoint,
        )

    async def retire(
        self, worker: control.ProcessIdentity, *, deadline_ns: int
    ) -> None:
        """Release local launch handles only after supervisor proves RELEASED."""
        if host_time_ns() >= deadline_ns:
            raise TimeoutError("worker launcher retirement deadline expired")
        retained = self._retained_processes.get(worker.generation)
        if retained is None:
            return
        job_name, pid, creation_time = retained
        self.revoke_peer(worker)
        self.native.release_process(pid, creation_time)
        self.native.close_launch_job(job_name)
        self._retained_processes.pop(worker.generation, None)

    async def wait_process_exit(
        self, worker: control.ProcessIdentity, *, deadline_ns: int
    ) -> bool:
        retained = self._retained_processes.get(worker.generation)
        if retained is None:
            return True
        _job_name, pid, creation_time = retained
        remaining_ms = max(0, (deadline_ns - host_time_ns()) // 1_000_000)
        if remaining_ms <= 0:
            return False
        return await asyncio.to_thread(
            self.native.wait_process_exit,
            pid,
            creation_time,
            min(int(remaining_ms), 0xFFFFFFFE),
        )

    async def drain_bootstrap_writes(self, deadline_ns: int) -> None:
        """Retain incomplete pipe writes as cleanup blockers until thread return."""
        for attempt in tuple(self._pending_bootstrap_writes):
            try:
                await attempt.wait(deadline_ns)
            finally:
                if attempt.completed.is_set():
                    self._pending_bootstrap_writes.remove(attempt)

    async def _confirm_creation_failure(
        self, spec: WorkerLaunchSpec, failure: BaseException, deadline_ns: int
    ) -> None:
        receipt = await self.supervisor.confirm_launch(
            wire.ConfirmLaunchRequest(
                command_id=str(uuid4()),
                launch_command_id=spec.launch_command_id,
                owner=self.owner,
                child=spec.context.worker,
                creation_failed_without_child=True,
                failure=control.Failure(
                    code="WORKER_PROCESS_CREATE_FAILED",
                    message=str(failure)[:2048],
                ),
            ),
            deadline_ns=deadline_ns,
        )
        if receipt.admission.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError(_admission_failure(receipt.admission)) from failure

    def _descriptor(
        self,
        spec: WorkerLaunchSpec,
        *,
        pid: int,
        creation_time_100ns: int,
        registration_deadline_ns: int,
        worker_token: str,
    ) -> tuple[dict[str, object], str]:
        context = spec.context
        descriptor: dict[str, object] = {
            "role": context.worker.role,
            "generation": context.worker.generation,
            "token": worker_token,
            "owner_role": self.owner.role,
            "owner_generation": self.owner.generation,
            "owner_token": self.owner_token,
            "supervisor_role": self.supervisor_identity.role,
            "supervisor_generation": self.supervisor_identity.generation,
            "supervisor_token": self.supervisor_token,
            "supervisor_endpoint": self.supervisor_endpoint,
            "coordinator_endpoint": self.coordinator_endpoint,
            "coordinator_token": worker_token,
            "launch_command_id": spec.launch_command_id,
            "pid": pid,
            "creation_time_100ns": creation_time_100ns,
            "registration_deadline_ns": registration_deadline_ns,
            "max_message_bytes": self.max_message_bytes,
            "heartbeat_interval_ns": spec.heartbeat_interval_ns,
            "health_silence_ns": spec.health_silence_ns,
            "worker_context": _encoded(context.SerializeToString(deterministic=True)),
            "control_policies": _encoded(
                spec.control_policies.SerializeToString(deterministic=True)
            ),
            "file_policy": _encoded(
                spec.file_policy.SerializeToString(deterministic=True)
            ),
        }
        return descriptor, worker_token


def _encoded(payload: bytes) -> str:
    return base64.b64encode(payload).decode("ascii")


def _admission_failure(admission: control.CommandAdmission) -> str:
    if admission.HasField("failure"):
        return f"{admission.failure.code}: {admission.failure.message}"
    return f"launch command rejected with result {admission.result}"
