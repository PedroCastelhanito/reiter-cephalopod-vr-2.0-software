"""Worker RPC identity, command admission and channel retirement."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cephvr.acquisition.identity import process_role_for_camera
from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.clock import host_time_ns
from cephvr.supervisor.acquisition_worker import AcquisitionWorkerControl
from cephvr.supervisor.worker_context import launch_work_matches
from cephvr.supervisor.worker_outbound import GrpcWorkerOutbound
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus
from tests.supervisor.support import Outbound, make_runtime

from .support import WORK, WORKER_ROLE, _identity, _worker_and_helper

# Rejected worker admissions remain failures.


class _Rejecting(Outbound):
    async def interrupt_worker(self, launch, request, *, deadline_ns):  # type: ignore[no-untyped-def]
        return types.CommandAdmission(result=types.COMMAND_RESULT_REJECTED)

    async def shutdown_worker(self, launch, request, *, deadline_ns):  # type: ignore[no-untyped-def]
        return types.CommandAdmission(result=types.COMMAND_RESULT_REJECTED)

    async def cleanup_worker(self, launch, request, *, deadline_ns):  # type: ignore[no-untyped-def]
        return types.CommandAdmission(result=types.COMMAND_RESULT_REJECTED)


async def test_rejected_worker_commands_raise(tmp_path: Path) -> None:
    runtime, native, _, _ = make_runtime(tmp_path)
    worker, _ = _worker_and_helper(runtime, native)
    target = acq.WorkerContext(
        worker=worker.plan.child,
        owner=worker.plan.owner,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
        work=WORK,
    )
    shutdown = runtime.shutdown.acquisition_worker_control
    shutdown.outbound = _Rejecting()
    deadline = host_time_ns() + 5_000_000_000
    report = wire.InterruptionReport(issued_monotonic_ns=1)
    with pytest.raises(RuntimeError, match="interrupt"):
        await shutdown.interrupt_worker(worker, target, report, deadline)
    with pytest.raises(RuntimeError, match="shutdown"):
        await shutdown.shutdown_worker(worker, target, deadline)
    cleanup = AcquisitionWorkerControl(
        registration=runtime.registration,
        registry=runtime.registry,
        outbound=_Rejecting(),
        issuer=runtime.identity,
        interrupt_commands={},
        cleanup_commands={},
    )
    with pytest.raises(RuntimeError, match="cleanup"):
        await cleanup.cleanup_worker(worker, target, deadline)


# Released worker generations retire their channels.


class _Closing(Outbound):
    def __init__(self) -> None:
        super().__init__()
        self.retired: list[tuple[str, str]] = []
        self.closed = 0

    async def retire_worker_generation(self, role: str, generation: str) -> None:
        self.retired.append((role, generation))

    async def close(self) -> None:
        self.closed += 1


async def test_release_retires_worker_channel_and_close_closes_outbound(
    tmp_path: Path,
) -> None:
    runtime, native, _, _ = make_runtime(tmp_path)
    outbound = _Closing()
    runtime.outbound = outbound
    worker, _ = _worker_and_helper(runtime, native)
    native.jobs[worker.containment_job_name] = []
    runtime.registry.release(worker.plan.command_id, obligations_met=True)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert outbound.retired == [(WORKER_ROLE, worker.plan.child.generation)]
    await runtime.close_outbound()
    assert outbound.closed == 1


async def test_grpc_worker_outbound_close_and_retire_close_channels() -> None:
    outbound = GrpcWorkerOutbound(
        supervisor=_identity("supervisor"), token="t", max_message_bytes=4096
    )
    closed: list[str] = []

    class Channel:
        def __init__(self, name: str) -> None:
            self.name = name

        async def close(self) -> None:
            closed.append(self.name)

    outbound.channels[("e", "r", "g1")] = Channel("g1")  # type: ignore[assignment]
    outbound.channels[("e", "r", "g2")] = Channel("g2")  # type: ignore[assignment]
    await outbound.retire_worker_generation("r", "g1")
    assert closed == ["g1"]
    await outbound.close()
    assert closed == ["g1", "g2"] and not outbound.channels


# Current registry state gates the channel.


def _stub_setup(
    phase: int, endpoint: str
) -> tuple[GrpcWorkerOutbound, wire.LaunchState, acq.WorkerContext]:
    outbound = GrpcWorkerOutbound(
        supervisor=_identity("supervisor"), token="t", max_message_bytes=4096
    )
    worker = _identity(WORKER_ROLE)
    owner = _identity("acquisition")
    launch = wire.LaunchState(
        plan=wire.PlanLaunchRequest(
            command_id=str(uuid4()), owner=owner, child=worker, work=WORK
        ),
        phase=wire.LAUNCH_PHASE_OPERATIONAL,
        pid=1,
        creation_time_100ns=1,
        endpoint="127.0.0.1:1",
    )
    current = wire.LaunchState.FromString(launch.SerializeToString())
    current.phase = phase
    current.endpoint = endpoint
    outbound.bind_registry(SimpleNamespace(refresh=lambda _id: current))  # type: ignore[arg-type]
    target = acq.WorkerContext(
        worker=worker, owner=owner, camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL, work=WORK
    )
    return outbound, launch, target


@pytest.mark.parametrize(
    ("phase", "endpoint"),
    [
        (wire.LAUNCH_PHASE_RELEASED, "127.0.0.1:1"),
        (wire.LAUNCH_PHASE_OPERATIONAL, "127.0.0.1:2"),
    ],
)
def test_stub_rejects_stale_launch_and_caches_nothing(
    phase: int, endpoint: str
) -> None:
    outbound, launch, target = _stub_setup(phase, endpoint)
    with pytest.raises(RuntimeError, match="changed"):
        outbound._stub(launch, target)
    assert not outbound.channels


def test_stub_requires_bound_registry() -> None:
    outbound, launch, target = _stub_setup(wire.LAUNCH_PHASE_OPERATIONAL, "127.0.0.1:1")
    outbound._registry = None
    with pytest.raises(RuntimeError, match="registry"):
        outbound._stub(launch, target)


class _Registry:
    """Stands in for LaunchRegistry.refresh: serves the launch as currently held."""

    def __init__(self, launch: wire.LaunchState) -> None:
        self.launch = launch

    def refresh(self, command_id: str) -> wire.LaunchState:
        return self.launch

    def states(self, *, tolerant: bool = False) -> list[wire.LaunchState]:
        return [self.launch]


def _bind(outbound: GrpcWorkerOutbound, launch: wire.LaunchState) -> None:
    outbound.bind_registry(_Registry(launch))  # type: ignore[arg-type]


def _worker_launch() -> tuple[wire.LaunchState, acq.WorkerContext]:
    worker = types.ProcessIdentity(
        role=process_role_for_camera(camera_pb2.CAMERA_ROLE_BEHAVIORAL),
        generation=str(uuid4()),
    )
    owner = types.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    session = types.SessionContext(session_id=str(uuid4()))
    work = types.WorkContext(session=session)
    launch = wire.LaunchState(
        plan=wire.PlanLaunchRequest(
            command_id=str(uuid4()),
            owner=owner,
            child=worker,
            work=work,
            executable=r"C:\CephVR\python.exe",
            python_worker=True,
            stop_method="grpc_shutdown",
        ),
        phase=wire.LAUNCH_PHASE_OPERATIONAL,
        pid=1234,
        creation_time_100ns=7,
        endpoint="127.0.0.1:43210",
    )
    target = acq.WorkerContext(
        worker=worker,
        owner=owner,
        work=work,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
    )
    return launch, target


async def test_worker_outbound_uses_registered_supervisor_principal_and_deadline() -> (
    None
):
    supervisor = types.ProcessIdentity(role="supervisor", generation=str(uuid4()))
    outbound = GrpcWorkerOutbound(
        supervisor=supervisor, token="supervisor-token", max_message_bytes=4096
    )
    launch, target = _worker_launch()
    _bind(outbound, launch)
    outbound._stub(launch, target)
    metadata = dict(outbound._metadata(host_time_ns() + 1_000_000_000))
    assert metadata["x-cephvr-role"] == "supervisor"
    assert metadata["x-cephvr-generation"] == supervisor.generation
    assert metadata["x-cephvr-token"] == "supervisor-token"
    assert int(metadata["x-cephvr-deadline-ns"]) > host_time_ns()


def test_worker_outbound_rejects_camera_context_from_another_launch() -> None:
    supervisor = types.ProcessIdentity(role="supervisor", generation=str(uuid4()))
    outbound = GrpcWorkerOutbound(
        supervisor=supervisor, token="supervisor-token", max_message_bytes=4096
    )
    launch, target = _worker_launch()
    _bind(outbound, launch)
    target.camera = camera_pb2.CAMERA_ROLE_TRACKING
    with pytest.raises(RuntimeError, match="exact launch"):
        outbound._stub(launch, target)


async def test_visual_stimulus_worker_outbound_accepts_exact_renderer_and_session_trial_work() -> (
    None
):
    supervisor = types.ProcessIdentity(role="supervisor", generation=str(uuid4()))
    outbound = GrpcWorkerOutbound(
        supervisor=supervisor, token="supervisor-token", max_message_bytes=4096
    )
    owner = types.ProcessIdentity(role="visual_stimulus", generation=str(uuid4()))
    renderer = types.ProcessIdentity(
        role="visual_stimulus_renderer", generation=str(uuid4())
    )
    session = types.SessionContext(session_id=str(uuid4()))
    session_work = types.WorkContext(session=session)
    trial_work = types.WorkContext(
        trial=types.TrialContext(session=session, trial_id=str(uuid4()))
    )
    launch = wire.LaunchState(
        plan=wire.PlanLaunchRequest(
            command_id=str(uuid4()), owner=owner, child=renderer, work=session_work
        ),
        phase=wire.LAUNCH_PHASE_OPERATIONAL,
        pid=11,
        endpoint="127.0.0.1:1",
    )
    _bind(outbound, launch)
    target = visual_stimulus.WorkerContext(
        worker=renderer, owner=owner, work=trial_work
    )
    assert outbound._visual_stimulus_stub(launch, target)
    await outbound.close()


def test_visual_stimulus_worker_outbound_rejects_wrong_renderer_role() -> None:
    outbound = GrpcWorkerOutbound(
        supervisor=_identity("supervisor"), token="t", max_message_bytes=4096
    )
    owner = _identity("visual_stimulus")
    renderer = _identity("other")
    launch = wire.LaunchState(
        plan=wire.PlanLaunchRequest(
            command_id=str(uuid4()), owner=owner, child=renderer
        ),
        phase=wire.LAUNCH_PHASE_OPERATIONAL,
        pid=1,
        endpoint="127.0.0.1:1",
    )
    _bind(outbound, launch)
    with pytest.raises(RuntimeError, match="Visual Stimulus renderer"):
        outbound._visual_stimulus_stub(
            launch, visual_stimulus.WorkerContext(worker=renderer, owner=owner)
        )


def test_worker_outbound_keeps_trial_work_inside_registered_session() -> None:
    launch, target = _worker_launch()
    target.work.CopyFrom(
        types.WorkContext(
            trial=types.TrialContext(
                session=launch.plan.work.session,
                trial_number=1,
                trial_id=str(uuid4()),
            )
        )
    )
    assert launch_work_matches(launch.plan, target.work)
    target.work.trial.session.session_id = str(uuid4())
    assert not launch_work_matches(launch.plan, target.work)


def _stub_for_launch(
    outbound: GrpcWorkerOutbound, launch: wire.LaunchState, work: types.WorkContext
) -> object:
    if launch.plan.owner.role == "visual_stimulus":
        return outbound._visual_stimulus_stub(
            launch,
            visual_stimulus.WorkerContext(
                worker=launch.plan.child, owner=launch.plan.owner, work=work
            ),
        )
    return outbound._stub(
        launch,
        acq.WorkerContext(
            worker=launch.plan.child,
            owner=launch.plan.owner,
            work=work,
            camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
        ),
    )


@pytest.mark.parametrize("backend", ["acquisition", "visual_stimulus"])
@pytest.mark.parametrize(
    ("scope", "requested", "camera_accepts", "visual_stimulus_accepts"),
    [
        ("absent", "empty", True, True),
        ("absent", "session", False, True),
        ("absent", "trial", False, True),
        ("empty", "empty", True, True),
        ("empty", "session", False, False),
        ("empty", "trial", False, False),
        ("session", "empty", False, False),
        ("session", "session", True, True),
        ("session", "trial", True, True),
        ("session", "other_session", False, False),
        ("session", "foreign_trial", False, False),
        ("trial", "trial", True, True),
        ("trial", "other_trial", False, False),
        ("trial", "session", False, False),
    ],
)
async def test_worker_discovery_and_transport_agree_on_work(
    tmp_path: Path,
    backend: str,
    scope: str,
    requested: str,
    camera_accepts: bool,
    visual_stimulus_accepts: bool,
) -> None:
    runtime, _, _, _ = make_runtime(tmp_path)
    launch, _ = _worker_launch()
    if backend == "visual_stimulus":
        launch.plan.owner.role = "visual_stimulus"
        launch.plan.child.role = "visual_stimulus_renderer"
    session = launch.plan.work.session
    other = types.SessionContext(session_id=str(uuid4()))
    works = {
        "empty": types.WorkContext(),
        "session": types.WorkContext(session=session),
        "other_session": types.WorkContext(session=other),
        "trial": types.WorkContext(
            trial=types.TrialContext(session=session, trial_id=str(uuid4()))
        ),
        "other_trial": types.WorkContext(
            trial=types.TrialContext(session=session, trial_id=str(uuid4()))
        ),
        "foreign_trial": types.WorkContext(
            trial=types.TrialContext(session=other, trial_id=str(uuid4()))
        ),
    }
    launch.plan.ClearField("work")
    if scope != "absent":
        launch.plan.work.CopyFrom(works[scope])
    runtime.registration_state.context = wire.RegisteredContext(
        required_participants=[
            types.BackendContext(
                backend_name=backend, backend_generation=launch.plan.owner.generation
            )
        ]
    )
    registry = _Registry(launch)
    control = runtime.shutdown
    if backend == "visual_stimulus":
        control.visual_stimulus_worker_control.registry = registry  # type: ignore[assignment]
        discovered = control.visual_stimulus_worker_control.registered_workers(
            works[requested]
        )
    else:
        control.acquisition_worker_control.registry = registry  # type: ignore[assignment]
        discovered = control.acquisition_worker_control.registered_workers(
            works[requested]
        )
    expected = (
        visual_stimulus_accepts if backend == "visual_stimulus" else camera_accepts
    )
    assert bool(discovered) is expected
    outbound = GrpcWorkerOutbound(
        supervisor=runtime.identity, token="t", max_message_bytes=4096
    )
    _bind(outbound, launch)
    try:
        if expected:
            assert _stub_for_launch(outbound, launch, works[requested])
        else:
            with pytest.raises(RuntimeError, match="exact launch"):
                _stub_for_launch(outbound, launch, works[requested])
            assert not outbound.channels
    finally:
        await outbound.close()


@pytest.mark.parametrize("backend", ["acquisition", "visual_stimulus"])
@pytest.mark.parametrize("stale", ["endpoint", "released"])
async def test_cached_worker_channel_revalidates_launch_at_capacity(
    backend: str,
    stale: str,
) -> None:
    outbound = GrpcWorkerOutbound(
        supervisor=_identity("supervisor"), token="t", max_message_bytes=4096
    )
    launch, _ = _worker_launch()
    if backend == "visual_stimulus":
        launch.plan.owner.role = "visual_stimulus"
        launch.plan.child.role = "visual_stimulus_renderer"
    current = wire.LaunchState.FromString(launch.SerializeToString())
    _bind(outbound, current)
    outbound.MAX_CHANNELS = 1
    try:
        _stub_for_launch(outbound, launch, launch.plan.work)
        original = next(iter(outbound.channels.values()))
        _stub_for_launch(outbound, launch, launch.plan.work)
        assert list(outbound.channels.values()) == [original]
        if stale == "endpoint":
            current.endpoint = "127.0.0.1:43211"
        else:
            current.phase = wire.LAUNCH_PHASE_RELEASED
        with pytest.raises(RuntimeError, match="changed"):
            _stub_for_launch(outbound, launch, launch.plan.work)
        current.CopyFrom(launch)
        current.plan.child.generation = str(uuid4())
        with pytest.raises(RuntimeError, match="capacity"):
            _stub_for_launch(outbound, current, current.plan.work)
        await outbound.retire_worker_generation(
            launch.plan.child.role, current.plan.child.generation
        )
        assert list(outbound.channels.values()) == [original]
        await outbound.retire_worker_generation(
            launch.plan.child.role, launch.plan.child.generation
        )
        assert not outbound.channels
        _stub_for_launch(outbound, current, current.plan.work)
        assert len(outbound.channels) == 1
        assert next(iter(outbound.channels.values())) is not original
    finally:
        await outbound.close()


async def test_camera_cleanup_waits_for_exact_executor_after_admission(
    tmp_path: Path,
) -> None:
    runtime, native, _, _ = make_runtime(tmp_path)
    worker, _ = _worker_and_helper(runtime, native)
    target = acq.WorkerContext(
        worker=worker.plan.child,
        owner=worker.plan.owner,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
        work=WORK,
    )
    outbound = Outbound()
    queries = []

    async def retained(launch, request, *, deadline_ns):
        queries.append(request.command_id)
        operation = types.OperationState(
            context=types.OperationContext(command_id=request.command_id),
            complete=len(queries) > 1,
        )
        if operation.complete:
            operation.succeeded = True
        return acq.WorkerRetainedResult(
            found=True,
            source=target,
            operation=acq.WorkerOperationReport(source=target, operation=operation),
        )

    outbound.get_worker_retained_result = retained
    cleanup = AcquisitionWorkerControl(
        registration=runtime.registration,
        registry=runtime.registry,
        outbound=outbound,
        issuer=runtime.identity,
        interrupt_commands={},
        cleanup_commands={},
    )
    await cleanup.cleanup_worker(worker, target, host_time_ns() + 1_000_000_000)
    assert len(queries) == 2 and len(set(queries)) == 1
