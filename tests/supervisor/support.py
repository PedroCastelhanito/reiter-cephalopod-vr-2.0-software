"""Shared supervisor fixtures for native ownership, peers and registered launches."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from cephvr.acquisition.identity import FFMPEG_ROLE, process_role_for_camera
from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.clock import describe_host_clock
from cephvr.supervisor.registry import LaunchRegistry
from cephvr.supervisor.runtime import SupervisorRuntime


class Native:
    def __init__(self) -> None:
        self.jobs: dict[str, list[tuple[int, int, str]]] = {}

    def create_launch_job(self, name: str) -> None:
        self.jobs[name] = []

    def inspect_launch_job(self, name: str) -> list[tuple[int, int, str]]:
        return list(self.jobs[name])

    def process_running(self, pid: int, creation_time_100ns: int) -> bool:
        return any(
            (pid, creation_time_100ns) == member[:2]
            for members in self.jobs.values()
            for member in members
        )

    def terminate_exact(self, pid: int, creation_time_100ns: int) -> None:
        for members in self.jobs.values():
            members[:] = [
                member for member in members if member[:2] != (pid, creation_time_100ns)
            ]

    def close_launch_job(self, name: str) -> None:
        del self.jobs[name]

    def release_process(self, pid: int, creation_time_100ns: int) -> None:
        pass

    def retain_exact(
        self, pid: int, creation_time_100ns: int, executable: str
    ) -> object:
        return object()


class Outbound:
    def __init__(self) -> None:
        self.interruptions: list[wire.InterruptionReport] = []
        self.statuses: list[wire.SupervisorStatusReport] = []
        self.heartbeats: list[types.HeartbeatReport] = []
        self.fail_status_once = False

    async def report_interruption(self, report: wire.InterruptionReport) -> None:
        self.interruptions.append(report)

    async def report_status(self, report: wire.SupervisorStatusReport) -> None:
        if self.fail_status_once:
            self.fail_status_once = False
            self.statuses.append(
                wire.SupervisorStatusReport.FromString(report.SerializeToString())
            )
            raise ConnectionError("controller temporarily unavailable")
        self.statuses.append(report)

    async def interrupt_backend(
        self,
        target: types.BackendContext,
        request: wire.InterruptSessionRequest,
        *,
        deadline_ns: int,
    ) -> None:
        pass

    async def shutdown_backend(
        self,
        target: types.BackendContext,
        request: wire.BackendCommand,
        *,
        deadline_ns: int,
    ) -> None:
        pass

    async def cleanup_backend(
        self,
        target: types.BackendContext,
        request: wire.BackendCommand,
        *,
        deadline_ns: int,
    ) -> None:
        pass

    async def notify_launcher_shutdown(self, deadline_ns: int, cause: str) -> None:
        pass

    async def report_heartbeat(self, report: types.HeartbeatReport) -> None:
        self.heartbeats.append(
            types.HeartbeatReport.FromString(report.SerializeToString())
        )

    async def interrupt_worker(
        self,
        launch: wire.LaunchState,
        request: acq.WorkerInterrupt,
        *,
        deadline_ns: int,
    ) -> types.CommandAdmission:
        return types.CommandAdmission(
            result=types.COMMAND_RESULT_ACCEPTED,
            command_id=request.command.command_id,
        )

    async def cleanup_worker(
        self,
        launch: wire.LaunchState,
        request: acq.WorkerCommand,
        *,
        deadline_ns: int,
    ) -> types.CommandAdmission:
        return types.CommandAdmission(
            result=types.COMMAND_RESULT_ACCEPTED,
            command_id=request.command_id,
        )

    async def shutdown_worker(
        self,
        launch: wire.LaunchState,
        request: acq.WorkerCommand,
        *,
        deadline_ns: int,
    ) -> types.CommandAdmission:
        return types.CommandAdmission(
            result=types.COMMAND_RESULT_ACCEPTED,
            command_id=request.command_id,
        )

    async def get_worker_state(
        self,
        launch: wire.LaunchState,
        request: acq.WorkerQuery,
        *,
        deadline_ns: int,
    ) -> acq.WorkerState:
        return acq.WorkerState()

    async def get_worker_retained_result(
        self,
        launch: wire.LaunchState,
        request: acq.WorkerRetainedResultQuery,
        *,
        deadline_ns: int,
    ) -> acq.WorkerRetainedResult:
        return acq.WorkerRetainedResult()

    async def confirm_tracking_cleanup(
        self, request: wire.TrackingInputConfirmation, *, deadline_ns: int
    ) -> types.CommandAdmission:
        return types.CommandAdmission(
            result=types.COMMAND_RESULT_ACCEPTED,
            command_id=request.command.command_id,
        )


class Context:
    def __init__(self, role: str, generation: str, token: str) -> None:
        self.metadata = (
            ("x-cephvr-role", role),
            ("x-cephvr-generation", generation),
            ("x-cephvr-token", token),
        )

    def peer(self) -> str:
        return "ipv4:127.0.0.1:51000"

    def invocation_metadata(self) -> tuple[tuple[str, str], ...]:
        return self.metadata

    async def abort(self, code: object, details: str) -> None:
        raise PermissionError(details)


def make_runtime(tmp_path: Path) -> tuple[SupervisorRuntime, Native, Outbound, Context]:
    supervisor = types.ProcessIdentity(role="supervisor", generation=str(uuid4()))
    controller = types.ProcessIdentity(role="controller", generation=str(uuid4()))
    native, outbound = Native(), Outbound()
    runtime = SupervisorRuntime(
        identity=supervisor,
        controller=controller,
        credentials={(controller.role, controller.generation): "controller-secret"},
        native=native,
        outbound=outbound,
        software_root=tmp_path,
    )
    return (
        runtime,
        native,
        outbound,
        Context("controller", controller.generation, "controller-secret"),
    )


def launch(
    runtime: SupervisorRuntime,
    native: Native,
    owner: types.ProcessIdentity,
    child: types.ProcessIdentity,
    pid: int,
) -> None:
    plan = wire.PlanLaunchRequest(
        command_id=str(uuid4()),
        owner=owner,
        child=child,
        executable="C:\\Python311\\python.exe",
        python_worker=True,
        stop_method="grpc_shutdown",
    )
    state = runtime.registry.plan(plan)
    native.jobs[state.containment_job_name] = [(pid, 100 + pid, plan.executable)]
    confirmed = wire.ConfirmLaunchRequest(
        command_id=str(uuid4()),
        launch_command_id=plan.command_id,
        owner=owner,
        child=child,
        pid=pid,
        creation_time_100ns=100 + pid,
    )
    runtime.registry.confirm(confirmed, runtime.clock)
    confirmed.command_id = str(uuid4())
    confirmed.endpoint = f"127.0.0.1:{50000 + pid}"
    descriptor = describe_host_clock()
    confirmed.host_clock.clock_id = descriptor.clock_id
    confirmed.host_clock.implementation = descriptor.implementation
    confirmed.host_clock.monotonic = descriptor.monotonic
    confirmed.host_clock.adjustable = descriptor.adjustable
    confirmed.host_clock.resolution_s = descriptor.resolution_s
    runtime.registry.confirm(confirmed, runtime.clock)


WORKER_ROLE = process_role_for_camera(camera_pb2.CAMERA_ROLE_BEHAVIORAL)


EXE = "C:\\Python311\\python.exe"


WORK = types.WorkContext(session=types.SessionContext(session_id=str(uuid4())))


def _identity(role: str) -> types.ProcessIdentity:
    return types.ProcessIdentity(role=role, generation=str(uuid4()))


def _launch(
    registry: LaunchRegistry,
    native: Native,
    owner: types.ProcessIdentity,
    child: types.ProcessIdentity,
    pid: int,
    *,
    python: bool,
) -> wire.LaunchState:
    plan = wire.PlanLaunchRequest(
        command_id=str(uuid4()),
        owner=owner,
        child=child,
        executable=EXE,
        python_worker=python,
        stop_method="grpc_shutdown" if python else "owner_stdin_eof",
        work=WORK,
        parent_operation=types.OperationContext(command_id=str(uuid4())),
    )
    state = registry.plan(plan)
    native.jobs[state.containment_job_name] = [(pid, 100 + pid, EXE)]
    confirm = wire.ConfirmLaunchRequest(
        command_id=str(uuid4()),
        launch_command_id=plan.command_id,
        owner=owner,
        child=child,
        pid=pid,
        creation_time_100ns=100 + pid,
    )
    clock = describe_host_clock()
    registry.confirm(confirm, clock)
    confirm.command_id = str(uuid4())
    if python:
        confirm.endpoint = f"127.0.0.1:{50000 + pid}"
        confirm.host_clock.clock_id = clock.clock_id
        confirm.host_clock.implementation = clock.implementation
        confirm.host_clock.monotonic = clock.monotonic
        confirm.host_clock.adjustable = clock.adjustable
        confirm.host_clock.resolution_s = clock.resolution_s
    return registry.confirm(confirm, clock)


def _worker_and_helper(
    runtime: SupervisorRuntime, native: Native
) -> tuple[wire.LaunchState, wire.LaunchState]:
    acquisition = _identity("acquisition")
    worker = _launch(
        runtime.registry,
        native,
        acquisition,
        _identity(WORKER_ROLE),
        11,
        python=True,
    )
    helper = _launch(
        runtime.registry,
        native,
        worker.plan.child,
        _identity(FFMPEG_ROLE),
        12,
        python=False,
    )
    return worker, helper


def _phase(runtime: SupervisorRuntime, launch: wire.LaunchState) -> int:
    return int(runtime.registry.refresh(launch.plan.command_id).phase)
