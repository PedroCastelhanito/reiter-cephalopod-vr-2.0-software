"""Shared registered-worker handshake and bootstrap handle ownership (E08)."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass

import pytest

import cephvr.platform.windows.bootstrap as bootstrap
import cephvr.platform.windows.worker_launch as worker_launch
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.jobs import WindowsLaunchError
from cephvr.shared.clock import host_time_ns


@dataclass(frozen=True)
class _Child:
    pid: int = 41
    creation_time_100ns: int = 99


def _request() -> wire.PlanLaunchRequest:
    return wire.PlanLaunchRequest(
        command_id="launch-1",
        owner=control.ProcessIdentity(role="acquisition", generation="owner-1"),
        child=control.ProcessIdentity(
            role="acquisition_behavioral_worker", generation="worker-1"
        ),
        parent_operation=control.OperationContext(command_id="setup-1"),
        executable="C:/python.exe",
        python_worker=True,
        stop_method="grpc_shutdown",
    )


@pytest.mark.asyncio
async def test_registered_worker_handshake_keeps_order_and_one_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    order: list[object] = []
    closed: list[int] = []
    expected_deadline = host_time_ns() + 2_000_000_000
    plan_state = wire.LaunchState(
        phase=wire.LAUNCH_PHASE_PLANNED,
        containment_job_name="job-1",
        plan=request,
    )
    operational = wire.LaunchState(
        phase=wire.LAUNCH_PHASE_OPERATIONAL,
        containment_job_name="job-1",
        endpoint="127.0.0.1:4567",
        pid=41,
        creation_time_100ns=99,
        plan=request,
    )
    monkeypatch.setattr(worker_launch, "close_handle", closed.append)
    monkeypatch.setattr(bootstrap, "close_handle", closed.append)

    def write(handle: int, document: dict[str, object]) -> None:
        order.append(("write", handle, document))

    monkeypatch.setattr(bootstrap, "write_bootstrap", write)

    async def plan(actual: wire.PlanLaunchRequest) -> wire.LaunchState:
        assert actual == request
        order.append(("plan", expected_deadline))
        return plan_state

    def make_pipes() -> worker_launch.BootstrapPipeHandles:
        order.append("pipes")
        return worker_launch.BootstrapPipeHandles(7, 8)

    def create(
        state: wire.LaunchState, pipes: worker_launch.BootstrapPipeHandles
    ) -> _Child:
        assert state == plan_state
        assert (pipes.read_handle, pipes.write_handle) == (7, 8)
        order.append("create")
        return _Child()

    async def confirm(child: _Child) -> wire.LaunchState:
        assert child == _Child()
        order.append("confirm")
        return wire.LaunchState(
            phase=wire.LAUNCH_PHASE_OS_CONFIRMED,
            containment_job_name="job-1",
            pid=41,
            creation_time_100ns=99,
            plan=request,
        )

    def register(_child: _Child, document: dict[str, object]) -> None:
        order.append(("register", document))

    def resume(_child: _Child) -> None:
        order.append("resume")

    def retain(_attempt: bootstrap.BootstrapPipeWrite) -> None:
        order.append("retain_writer")

    def finish(_attempt: bootstrap.BootstrapPipeWrite) -> None:
        order.append("finish_writer")

    async def get_state() -> wire.LaunchState:
        order.append(("get_state", expected_deadline))
        return operational

    child, state = await worker_launch.launch_registered_worker(
        request=request,
        create_pipes=make_pipes,
        plan=plan,
        create_suspended=create,
        process_identity=lambda process: (process.pid, process.creation_time_100ns),
        confirm=confirm,
        descriptor=lambda _child: {"generation": "worker-1"},
        register_peer=register,
        resume=resume,
        retain_writer=retain,
        finish_writer=finish,
        get_state=get_state,
        deadline_ns=expected_deadline,
    )
    assert child == _Child()
    assert state == operational
    assert closed == [7]
    plan_index = next(
        i
        for i, item in enumerate(order)
        if isinstance(item, tuple) and item[0] == "plan"
    )
    assert (
        plan_index
        < order.index("pipes")
        < order.index("create")
        < order.index("confirm")
        < order.index(("register", {"generation": "worker-1"}))
        < order.index("resume")
        < order.index("retain_writer")
    )
    assert order.index("finish_writer") < next(
        i
        for i, item in enumerate(order)
        if isinstance(item, tuple) and item[0] == "get_state"
    )
    assert any(isinstance(item, tuple) and item[0] == "write" for item in order)


@pytest.mark.asyncio
async def test_rejected_os_confirmation_closes_untransferred_pipes_without_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    closed: list[int] = []
    monkeypatch.setattr(worker_launch, "close_handle", closed.append)
    monkeypatch.setattr(bootstrap, "close_handle", closed.append)
    events: list[str] = []
    planned = wire.LaunchState(
        phase=wire.LAUNCH_PHASE_PLANNED,
        containment_job_name="job-1",
        plan=request,
    )

    async def plan(_request: wire.PlanLaunchRequest) -> wire.LaunchState:
        return planned

    async def confirm(_child: _Child) -> wire.LaunchState:
        return wire.LaunchState(
            phase=wire.LAUNCH_PHASE_CLEANUP_REQUIRED,
            containment_job_name="job-1",
            pid=41,
            creation_time_100ns=99,
            plan=request,
        )

    with pytest.raises(WindowsLaunchError, match="confirm the exact worker"):
        await worker_launch.launch_registered_worker(
            request=request,
            create_pipes=lambda: worker_launch.BootstrapPipeHandles(17, 18),
            plan=plan,
            create_suspended=lambda _state, _pipes: _Child(),
            process_identity=lambda child: (child.pid, child.creation_time_100ns),
            confirm=confirm,
            descriptor=lambda _child: {},
            register_peer=lambda _child, _document: events.append("register"),
            resume=lambda _child: events.append("resume"),
            retain_writer=lambda _attempt: events.append("writer"),
            finish_writer=lambda _attempt: None,
            get_state=lambda: pytest.fail("state query after confirmation failure"),
            deadline_ns=host_time_ns() + 2_000_000_000,
        )
    assert events == []
    assert closed == [17, 18]


@pytest.mark.asyncio
async def test_registered_state_must_keep_confirmed_os_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    closed: list[int] = []
    monkeypatch.setattr(worker_launch, "close_handle", closed.append)
    monkeypatch.setattr(bootstrap, "close_handle", closed.append)
    monkeypatch.setattr(bootstrap, "write_bootstrap", lambda *_args: None)

    async def plan(_request: wire.PlanLaunchRequest) -> wire.LaunchState:
        return wire.LaunchState(
            phase=wire.LAUNCH_PHASE_PLANNED,
            containment_job_name="job-identity",
            plan=request,
        )

    async def confirm(_child: _Child) -> wire.LaunchState:
        return wire.LaunchState(
            phase=wire.LAUNCH_PHASE_OS_CONFIRMED,
            pid=41,
            creation_time_100ns=99,
            plan=request,
        )

    async def get_state() -> wire.LaunchState:
        return wire.LaunchState(
            phase=wire.LAUNCH_PHASE_OPERATIONAL,
            endpoint="127.0.0.1:4567",
            pid=42,
            creation_time_100ns=99,
            plan=request,
        )

    with pytest.raises(WindowsLaunchError, match="confirmed worker"):
        await worker_launch.launch_registered_worker(
            request=request,
            create_pipes=lambda: worker_launch.BootstrapPipeHandles(47, 48),
            plan=plan,
            create_suspended=lambda _state, _pipes: _Child(),
            process_identity=lambda child: (child.pid, child.creation_time_100ns),
            confirm=confirm,
            descriptor=lambda _child: {},
            register_peer=lambda _child, _document: None,
            resume=lambda _child: None,
            retain_writer=lambda _attempt: None,
            finish_writer=lambda _attempt: None,
            get_state=get_state,
            deadline_ns=host_time_ns() + 2_000_000_000,
        )
    assert closed == [47]


@pytest.mark.asyncio
async def test_writer_thread_start_failure_releases_attempt_and_both_parent_handles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    closed: list[int] = []
    retained: list[bootstrap.BootstrapPipeWrite] = []
    resumed: list[bool] = []
    monkeypatch.setattr(worker_launch, "close_handle", closed.append)
    monkeypatch.setattr(bootstrap, "close_handle", closed.append)
    monkeypatch.setattr(
        bootstrap.BootstrapPipeWrite,
        "start",
        lambda _self: (_ for _ in ()).throw(RuntimeError("thread start failed")),
    )
    planned = wire.LaunchState(
        phase=wire.LAUNCH_PHASE_PLANNED,
        containment_job_name="job-1",
        plan=request,
    )

    async def plan(_request: wire.PlanLaunchRequest) -> wire.LaunchState:
        return planned

    async def confirm(_child: _Child) -> wire.LaunchState:
        return wire.LaunchState(
            phase=wire.LAUNCH_PHASE_OS_CONFIRMED,
            pid=41,
            creation_time_100ns=99,
            plan=request,
        )

    def retain(attempt: bootstrap.BootstrapPipeWrite) -> None:
        retained.append(attempt)

    with pytest.raises(RuntimeError, match="thread start failed"):
        await worker_launch.launch_registered_worker(
            request=request,
            create_pipes=lambda: worker_launch.BootstrapPipeHandles(27, 28),
            plan=plan,
            create_suspended=lambda _state, _pipes: _Child(),
            process_identity=lambda child: (child.pid, child.creation_time_100ns),
            confirm=confirm,
            descriptor=lambda _child: {},
            register_peer=lambda _child, _document: None,
            resume=lambda _child: resumed.append(True),
            retain_writer=retain,
            finish_writer=lambda attempt: retained.remove(attempt),
            get_state=lambda: pytest.fail("failed writer must block state query"),
            deadline_ns=host_time_ns() + 2_000_000_000,
        )
    assert len(retained) == 0
    assert resumed == [True]
    assert closed == [27, 28]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "launch_mode", ["success", "writer_timeout", "create_unknown", "create_empty"]
)
async def test_acquisition_launcher_wrapper_uses_registered_native_sequence(
    monkeypatch: pytest.MonkeyPatch,
    launch_mode: str,
) -> None:
    from pathlib import Path
    from types import SimpleNamespace

    from cephvr.acquisition import worker_launcher as acquisition_launcher
    from cephvr.acquisition.ports import WorkerLaunchSpec
    from cephvr.acquisition.v1 import camera_pb2, messages_pb2, runtime_pb2

    events: list[object] = []
    deadlines: list[int] = []
    handles_closed: list[int] = []
    block_writer = launch_mode == "writer_timeout"
    writer_started = threading.Event()
    release_writer = threading.Event()
    request_state: dict[str, wire.PlanLaunchRequest] = {}
    owner = control.ProcessIdentity(role="acquisition", generation="owner-2")
    worker = control.ProcessIdentity(
        role="acquisition_behavioral_worker", generation="worker-2"
    )
    context = messages_pb2.WorkerContext(
        worker=worker,
        owner=owner,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
    )
    executable = Path("/portable/python.exe")
    spec = WorkerLaunchSpec(
        launch_command_id="launch-2",
        parent_operation=control.OperationContext(command_id="setup-2"),
        context=context,
        file_policy=runtime_pb2.CameraFilePolicy(
            camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL
        ),
        control_policies=control.ControlPolicies(),
        coordinator_endpoint="127.0.0.1:20002",
        heartbeat_interval_ns=10,
        health_silence_ns=50,
        executable=executable,
        python_worker=True,
        stop_method="grpc_shutdown",
    )
    planned = wire.LaunchState(phase=wire.LAUNCH_PHASE_PLANNED)
    confirmed = wire.LaunchState(phase=wire.LAUNCH_PHASE_OS_CONFIRMED)
    operational = wire.LaunchState(
        phase=wire.LAUNCH_PHASE_OPERATIONAL,
        endpoint="127.0.0.1:4568",
        pid=51,
        creation_time_100ns=99,
    )

    class Supervisor:
        async def plan_launch(self, request, *, deadline_ns, child_token):
            deadlines.append(deadline_ns)
            events.append("plan")
            request_state["request"] = request
            planned.CopyFrom(
                wire.LaunchState(
                    phase=wire.LAUNCH_PHASE_PLANNED,
                    containment_job_name="acq-job",
                    plan=request,
                )
            )
            return wire.LaunchReceipt(
                admission=control.CommandAdmission(
                    result=control.COMMAND_RESULT_ACCEPTED
                ),
                state=planned,
            )

        async def confirm_launch(self, request, *, deadline_ns):
            deadlines.append(deadline_ns)
            if request.creation_failed_without_child:
                events.append("creation_failure")
                return wire.LaunchReceipt(
                    admission=control.CommandAdmission(
                        result=control.COMMAND_RESULT_ACCEPTED
                    ),
                    state=wire.LaunchState(),
                )
            events.append("confirm")
            confirmed.CopyFrom(
                wire.LaunchState(
                    phase=wire.LAUNCH_PHASE_OS_CONFIRMED,
                    containment_job_name="acq-job",
                    pid=request.pid,
                    creation_time_100ns=request.creation_time_100ns,
                    plan=request_state["request"],
                )
            )
            return wire.LaunchReceipt(
                admission=control.CommandAdmission(
                    result=control.COMMAND_RESULT_ACCEPTED
                ),
                state=confirmed,
            )

        async def get_launch_state(self, _request, *, deadline_ns):
            deadlines.append(deadline_ns)
            events.append("state")
            operational.plan.CopyFrom(request_state["request"])
            return operational

    child = SimpleNamespace(pid=51, creation_time_100ns=99)

    class Native:
        def open_launch_job(self, name):
            events.append(("open_job", name))

        def launch_suspended(self, *args, **kwargs):
            events.append("create_suspended")
            if launch_mode in {"create_unknown", "create_empty"}:
                raise OSError("native process creation failed")
            return child

        def inspect_launch_job(self, _name):
            events.append("inspect_job")
            if launch_mode == "create_unknown":
                raise OSError("job inspection failed")
            return []

        def resume(self, _child):
            events.append("resume")

    monkeypatch.setattr(acquisition_launcher, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(
        acquisition_launcher, "resolve_python_executable", lambda _path: executable
    )
    monkeypatch.setattr(acquisition_launcher, "create_bootstrap_pipe", lambda: (71, 72))
    monkeypatch.setattr(
        acquisition_launcher, "GrpcWorkerPort", lambda *args: "worker-port"
    )
    monkeypatch.setattr(
        acquisition_launcher.grpc.aio,
        "insecure_channel",
        lambda *args, **kwargs: "channel",
    )
    monkeypatch.setattr(worker_launch, "close_handle", handles_closed.append)
    monkeypatch.setattr(bootstrap, "close_handle", handles_closed.append)

    def write(handle: int, _document: dict[str, object]) -> None:
        events.append("write")
        writer_started.set()
        if block_writer:
            assert release_writer.wait(timeout=2)
        handles_closed.append(handle)

    monkeypatch.setattr(bootstrap, "write_bootstrap", write)
    original_wait = bootstrap.BootstrapPipeWrite.wait
    if block_writer:

        async def wait_for_blocked_writer(
            attempt: bootstrap.BootstrapPipeWrite, _deadline_ns: int
        ) -> None:
            assert await asyncio.to_thread(writer_started.wait, 1)
            raise TimeoutError("worker bootstrap pipe write remains in progress")

        monkeypatch.setattr(
            bootstrap.BootstrapPipeWrite, "wait", wait_for_blocked_writer
        )
    registered: list[tuple[str, str]] = []
    launcher = acquisition_launcher.WindowsWorkerBootstrapPort(
        native=Native(),
        supervisor=Supervisor(),
        owner=owner,
        owner_token="owner-token",
        supervisor_identity=control.ProcessIdentity(
            role="supervisor", generation="supervisor-2"
        ),
        supervisor_token="supervisor-token",
        supervisor_endpoint="127.0.0.1:20001",
        coordinator_endpoint="127.0.0.1:20002",
        python_executable=executable,
        max_message_bytes=1024,
        register_peer=lambda identity, _token: registered.append(
            (identity.role, identity.generation)
        ),
        revoke_peer=lambda _identity: None,
    )
    deadline = host_time_ns() + 2_000_000_000
    if launch_mode in {"create_unknown", "create_empty"}:
        with pytest.raises(OSError, match="native process creation failed"):
            await launcher.launch(spec, deadline_ns=deadline)
        assert deadlines == (
            [deadline, deadline] if launch_mode == "create_empty" else [deadline]
        )
        assert events.index("plan") < events.index("create_suspended")
        assert events.index("create_suspended") < events.index("inspect_job")
        assert ("creation_failure" in events) is (launch_mode == "create_empty")
        assert not launcher._retained_processes
        assert launcher._pending_bootstrap_writes == []
        assert set(handles_closed) == {71, 72}
        assert not {"confirm", "resume", "write", "state"}.intersection(events)
        return

    if block_writer:
        with pytest.raises(TimeoutError, match="remains in progress"):
            await launcher.launch(spec, deadline_ns=deadline)
        assert events.index("resume") < events.index("write")
        assert "state" not in events
        assert deadlines == [deadline, deadline]
        assert len(launcher._pending_bootstrap_writes) == 1
        assert launcher._retained_processes[worker.generation] == (
            "acq-job",
            51,
            99,
        )
        assert 71 in handles_closed
        assert 72 not in handles_closed
        monkeypatch.setattr(bootstrap.BootstrapPipeWrite, "wait", original_wait)
        release_writer.set()
        attempt = launcher._pending_bootstrap_writes[0]
        assert await asyncio.to_thread(attempt.completed.wait, 1)
        await launcher.drain_bootstrap_writes(host_time_ns() + 2_000_000_000)
        assert launcher._pending_bootstrap_writes == []
        assert 72 in handles_closed
        return

    result = await launcher.launch(spec, deadline_ns=deadline)

    assert (result.pid, result.creation_time_100ns, result.endpoint) == (
        51,
        99,
        "127.0.0.1:4568",
    )
    assert result.port == "worker-port"
    assert registered == [(worker.role, worker.generation)]
    assert deadlines == [deadline, deadline, deadline]
    assert events.index("plan") < events.index("create_suspended")
    assert events.index("confirm") < events.index("resume") < events.index("write")
    assert events.index("write") < events.index("state")
    assert set(handles_closed) == {71, 72}
    assert launcher._retained_processes[worker.generation] == (
        "acq-job",
        51,
        99,
    )


@pytest.mark.asyncio
async def test_visual_stimulus_launcher_wrapper_keeps_exact_registered_child(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from pathlib import Path
    from types import SimpleNamespace

    from cephvr.visual_stimulus import worker_launcher as visual_launcher

    events: list[object] = []
    deadlines: list[int] = []
    closed: list[int] = []
    request_state: dict[str, wire.PlanLaunchRequest] = {}
    owner = control.ProcessIdentity(role="visual_stimulus", generation="owner-3")
    controller = control.ProcessIdentity(role="controller", generation="controller-3")
    supervisor_identity = control.ProcessIdentity(
        role="supervisor", generation="supervisor-3"
    )
    worker = control.ProcessIdentity(
        role="visual_stimulus_renderer", generation="renderer-3"
    )
    executable = Path("/portable/visual-python.exe")
    policy = control.ControlPolicies()
    managed_bootstrap = SimpleNamespace(
        software_root=tmp_path,
        identity=owner,
        controller=controller,
        supervisor=supervisor_identity,
        token="owner-token",
        controller_token="controller-token",
        supervisor_token="supervisor-token",
        endpoint_port=20002,
        controller_port=20003,
        supervisor_port=20001,
        max_message_bytes=1024,
        heartbeat_interval_ns=10,
        health_silence_ns=50,
        pid=30,
        creation_time_100ns=31,
        supervisor_pid=40,
        supervisor_creation_time_100ns=41,
        policies=policy,
    )
    planned = wire.LaunchState()
    confirmed = wire.LaunchState()
    operational = wire.LaunchState(
        phase=wire.LAUNCH_PHASE_OPERATIONAL,
        endpoint="127.0.0.1:4569",
        pid=61,
        creation_time_100ns=199,
    )

    class Supervisor:
        async def call(self, method, request, *, deadline_ns, metadata=()):
            deadlines.append(deadline_ns)
            events.append(method)
            if method == "PlanLaunch":
                request_state["request"] = request
                planned.CopyFrom(
                    wire.LaunchState(
                        phase=wire.LAUNCH_PHASE_PLANNED,
                        containment_job_name="vs-job",
                        plan=request,
                    )
                )
                return wire.LaunchReceipt(
                    admission=control.CommandAdmission(
                        result=control.COMMAND_RESULT_ACCEPTED
                    ),
                    state=planned,
                )
            if method == "ConfirmLaunch":
                confirmed.CopyFrom(
                    wire.LaunchState(
                        phase=wire.LAUNCH_PHASE_OS_CONFIRMED,
                        containment_job_name="vs-job",
                        pid=request.pid,
                        creation_time_100ns=request.creation_time_100ns,
                        plan=request_state["request"],
                    )
                )
                return wire.LaunchReceipt(
                    admission=control.CommandAdmission(
                        result=control.COMMAND_RESULT_ACCEPTED
                    ),
                    state=confirmed,
                )
            assert method == "GetLaunchState"
            operational.plan.CopyFrom(request_state["request"])
            return operational

    child = SimpleNamespace(pid=61, creation_time_100ns=199)

    class Native:
        def open_launch_job(self, name):
            events.append(("open_job", name))

        def launch_suspended(self, *args, **kwargs):
            events.append("create_suspended")
            return child

        def resume(self, _child):
            events.append("resume")

    class Credentials(dict):
        def __setitem__(self, key, value):
            events.append("register")
            super().__setitem__(key, value)

    monkeypatch.setattr(
        visual_launcher,
        "sys",
        SimpleNamespace(platform="win32", executable=str(executable)),
    )
    monkeypatch.setattr(
        visual_launcher, "resolve_python_executable", lambda _path: executable
    )
    monkeypatch.setattr(visual_launcher, "create_bootstrap_pipe", lambda: (81, 82))
    monkeypatch.setattr(
        visual_launcher,
        "Peer",
        lambda *args, **kwargs: SimpleNamespace(endpoint=args[0]),
    )
    monkeypatch.setattr(worker_launch, "close_handle", closed.append)
    monkeypatch.setattr(bootstrap, "close_handle", closed.append)

    def write(handle: int, _document: dict[str, object]) -> None:
        events.append("write")
        closed.append(handle)

    monkeypatch.setattr(bootstrap, "write_bootstrap", write)
    credentials = Credentials()
    retained: list[bootstrap.BootstrapPipeWrite] = []
    deadline = host_time_ns() + 2_000_000_000
    result = await visual_launcher.launch_renderer(
        managed_bootstrap,
        Supervisor(),
        Native(),
        credentials,
        deadline,
        pending_bootstrap_writes=retained,
        identity=worker,
    )

    assert (result.child.pid, result.child.creation_time_100ns) == (61, 199)
    assert result.job_name == "vs-job"
    assert result.peer.endpoint == "127.0.0.1:4569"
    assert deadlines == [deadline, deadline, deadline]
    assert credentials[(worker.role, worker.generation)] == result.token
    assert events.index("ConfirmLaunch") < events.index("register")
    assert events.index("register") < events.index("resume") < events.index("write")
    assert events.index("write") < events.index("GetLaunchState")
    assert retained == []
    assert set(closed) == {81, 82}
