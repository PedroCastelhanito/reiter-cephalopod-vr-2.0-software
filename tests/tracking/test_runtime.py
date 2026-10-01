"""Authenticated loopback lifecycle using real runtime/movement and hardware adapters."""

from __future__ import annotations

import asyncio
import threading
from uuid import uuid4

import grpc
import numpy as np
import pytest

from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import (
    services_pb2 as wire,
)
from cephvr.control.v1 import (
    services_pb2_grpc as rpc,
)
from cephvr.control.v1 import (
    types_pb2 as pb,
)
from cephvr.platform.windows.nvidia_device import NvidiaDevice
from cephvr.shared.auth import Principal
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger
from cephvr.shared.transport_deadlines import deadline_metadata
from cephvr.tracking.config.models.records import SourceFrame
from cephvr.tracking.configuration import load_file_policies
from cephvr.tracking.coordinator.state import Identity
from cephvr.tracking.processing.frames import FramePool
from cephvr.tracking.runtime import TrackingRuntime
from cephvr.tracking.transport.server import serve
from cephvr.tracking.types import ImageLayout
from cephvr.tracking.v1 import (
    services_pb2 as tracking,
)
from cephvr.tracking.v1 import (
    services_pb2_grpc as tracking_rpc,
)

from .support import ROOT, manual_settings


class Peer:
    def __init__(self):
        self.reports = []

    async def receipt(self, method, request, *, deadline_ns):
        self.reports.append(
            (method, type(request).FromString(request.SerializeToString()))
        )
        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)


class Clock:
    def __init__(self):
        self.now = host_time_ns()

    def __call__(self):
        return self.now


class CameraBoundary:
    def __init__(self, frames, identity, maximum):
        self.layout = ImageLayout(
            100, 100, 100, "gray", "uint8", 8, "lsb", 0, 255, "camera"
        )
        self.pool = FramePool(self.layout, 4, maximum)
        self.frames = []
        self.lock = threading.Lock()

    def open(self, identity):
        pass

    def begin(self):
        pass

    def latest(self):
        with self.lock:
            self.frames[:] = self.frames[-1:]

    def feed(self, index, now):
        with self.lock:
            self.frames.append((index, now))

    def read(self, work, generation):
        with self.lock:
            if not self.frames:
                return None, False
            index, now = self.frames.pop(0)
        acquired = self.pool.acquire()
        assert acquired is not None
        slot, storage = acquired
        storage[:] = bytes(10000)
        return self.pool.publish(
            slot, SourceFrame(frame_id=index, host_receipt_ns=now), work, generation
        ), False

    def close(self):
        return self.pool.idle()


class FlowBoundary:
    def prepare(self, settings, layout, maximum):
        self.data = np.zeros(
            (
                (layout.height + settings.output_grid_px - 1)
                // settings.output_grid_px,
                (layout.width + settings.output_grid_px - 1) // settings.output_grid_px,
                2,
            ),
            dtype="<i2",
        )

    def upload(self, image, *, baseline):
        pass

    def complete(self):
        return True

    def views(self, cells):
        return memoryview(self.data).toreadonly(), None

    def reset(self):
        pass

    def close(self):
        pass


async def until(predicate):
    for _ in range(300):
        if predicate():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("expected retained state did not arrive")


@pytest.fixture
async def rig_boundary(monkeypatch):
    from cephvr.tracking.methods import nvidia
    from cephvr.tracking.processing import session

    monkeypatch.setattr(session, "RingSource", CameraBoundary)
    monkeypatch.setattr(nvidia, "NativeFlow", FlowBoundary)
    monkeypatch.setattr(
        nvidia,
        "verify_tracking_device",
        lambda ordinal: NvidiaDevice(
            ordinal, "GPU-" + str(uuid4()), "NVIDIA GeForce RTX 5060 Ti"
        ),
    )
    identity = Identity(
        pb.ProcessIdentity(role="tracking", generation=str(uuid4())),
        pb.ProcessIdentity(role="controller", generation=str(uuid4())),
        pb.ProcessIdentity(role="supervisor", generation=str(uuid4())),
    )
    peer = Peer()
    clock = Clock()
    ledger = CommandLedger(
        identity.process.generation,
        10_000_000_000,
        max_records=128,
        max_bytes=16 * 1024 * 1024,
        result_reservation_bytes=65536,
        safety_reserve_records=8,
        safety_reserve_bytes=1024 * 1024,
    )
    runtime = TrackingRuntime(identity, peer, peer, ledger, clock=clock)
    # Inject time only at the processing clock boundary; preserve timing rules.
    monkeypatch.setattr(session, "host_time_ns", clock)
    original = session.Movement
    monkeypatch.setattr(session, "Movement", lambda ports: original(ports, clock=clock))
    listener = await serve(
        runtime,
        {
            ("controller", identity.controller.generation): "token",
            ("supervisor", identity.supervisor.generation): "safety",
        },
        ledger,
        port=0,
        max_message_bytes=4 * 1024 * 1024,
        testing=True,
    )
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{listener.port}")
    metadata = Principal(
        "controller", identity.controller.generation, "token"
    ).metadata()
    deadline = host_time_ns() + 30_000_000_000
    metadata = (*metadata, deadline_metadata(deadline))
    yield (
        runtime,
        clock,
        rpc.BackendServiceStub(channel),
        tracking_rpc.TrackingPreparationServiceStub(channel),
        metadata,
        peer,
    )
    runtime.gate.seal(clock())
    if runtime.engine is not None:
        await asyncio.get_running_loop().run_in_executor(
            runtime.executor, runtime.engine.close, host_time_ns() + 5_000_000_000
        )
    runtime.executor.shutdown(wait=True)
    await channel.close()
    await listener.close(host_time_ns() + 2_000_000_000)


def command(runtime, work, parent=""):
    return wire.BackendCommand(
        command_id=str(uuid4()),
        issuer=runtime.identity.controller,
        target=runtime.identity.backend,
        work=work,
        parent_operation=pb.OperationContext(command_id=parent),
    )


async def setup_runtime(fixture, tmp_path, before_setup=None, *, saving=False):
    runtime, clock, stub, preparation, metadata, peer = fixture
    session = pb.SessionContext(
        controller_generation=runtime.identity.controller.generation,
        session_id=str(uuid4()),
    )
    trial = pb.TrialContext(session=session, trial_id=str(uuid4()), trial_number=1)
    plan = pb.PreparedSession(
        context=session, configuration_revision=1, session_directory=str(tmp_path)
    )
    plan.configuration.asset_root = str(tmp_path)
    plan.configuration.mode = pb.SESSION_MODE_OPEN_LOOP
    plan.policies.start_evidence_allowance_ns = 2_000_000_000
    plan.policies.stop_evidence_allowance_ns = 2_000_000_000
    plan.policies.trial_finished.initial_ns = 2_000_000_000
    plan.policies.recovery_ns = 2_000_000_000
    plan.trials.add(context=trial)
    settings = manual_settings()
    settings.save_tracking_data = saving
    request = wire.SetupSessionRequest(
        command=command(runtime, pb.WorkContext(session=session)),
        plan=plan,
        settings=pb.BackendSettings(
            backend_name="tracking", enabled=True, tracking=settings
        ),
        tracking_policies=load_file_policies(ROOT),
    )
    if before_setup is not None:
        await before_setup(request)
    reply = await stub.SetupSession(request, metadata=metadata)
    assert reply.result == pb.COMMAND_RESULT_ACCEPTED
    await until(
        lambda: (
            runtime.state.preparation_report is not None
            or runtime.state.error is not None
        )
    )
    assert runtime.state.error is None, runtime.state.error
    query = tracking.TrackingPreparationQuery(
        command=command(runtime, pb.WorkContext(session=session))
    )
    status = await preparation.GetPreparation(query, metadata=metadata)
    assert not status.data_attached and runtime.state.ready is None
    frames = acq.FrameBufferAttachment()
    frames.buffer.allocation_id = str(uuid4())
    frames.buffer.consumer.CopyFrom(runtime.identity.process)
    frames.buffer.session.CopyFrom(session)
    frames.buffer.configuration_revision = 1
    frames.buffer.camera = settings.input_camera_role
    frames.buffer.kind = acq.FRAME_BUFFER_KIND_TRACKING
    frames.buffer.image.width = frames.buffer.image.height = 100
    frames.sync.target.CopyFrom(runtime.identity.process)
    frames.sync.transfer_id = str(uuid4())
    binding = tracking.TrackingDataBinding(
        command=command(
            runtime, pb.WorkContext(session=session), request.command.command_id
        ),
        configuration_revision=1,
        preparation_generation=status.preparation_generation,
        frames=frames,
    )
    admitted = await preparation.BindData(binding, metadata=metadata)
    assert admitted.result == pb.COMMAND_RESULT_ACCEPTED
    await until(
        lambda: runtime.state.ready is not None or runtime.state.error is not None
    )
    assert runtime.state.error is None, runtime.state.error
    return request, trial, binding


async def test_authenticated_setup_duplicate_conflict_stale_and_cleanup(
    rig_boundary, tmp_path
):
    runtime, clock, stub, preparation, metadata, peer = rig_boundary
    request, trial, binding = await setup_runtime(rig_boundary, tmp_path)
    assert (
        runtime.state.preparation.data_attached
        and runtime.state.ready.required_checks_passed
    )
    assert (
        await stub.SetupSession(request, metadata=metadata)
    ).result == pb.COMMAND_RESULT_ACCEPTED
    conflict = wire.SetupSessionRequest.FromString(request.SerializeToString())
    conflict.plan.configuration_revision = 2
    assert (
        await stub.SetupSession(conflict, metadata=metadata)
    ).result == pb.COMMAND_RESULT_REJECTED
    bad = command(runtime, request.command.work)
    bad.target.backend_generation = str(uuid4())
    assert (
        await stub.Cleanup(bad, metadata=metadata)
    ).result == pb.COMMAND_RESULT_REJECTED
    with pytest.raises(grpc.aio.AioRpcError) as error:
        await stub.GetState(wire.BackendQuery(target=runtime.identity.backend))
    assert error.value.code() == grpc.StatusCode.PERMISSION_DENIED
    cleanup = command(runtime, request.command.work)
    assert (
        await stub.Cleanup(cleanup, metadata=metadata)
    ).result == pb.COMMAND_RESULT_ACCEPTED
    await until(lambda: runtime.state.cleanup is not None)
    assert all(item.released for item in runtime.state.cleanup.resources)


@pytest.mark.parametrize("saving", [False, True])
async def test_real_movement_baseline_start_and_separate_stop_finish(
    rig_boundary, tmp_path, saving
):
    runtime, clock, stub, preparation, metadata, peer = rig_boundary
    setup, trial, _ = await setup_runtime(rig_boundary, tmp_path, saving=saving)
    work = pb.WorkContext(trial=trial)
    prepare = wire.PrepareTrialRequest(
        command=command(runtime, work),
        configuration_revision=1,
        plan=pb.TrialPlan(context=trial, resolved_duration_ns=1_000_000_000),
    )
    if saving:
        prepare.outputs.add(
            output_key="tracking", backend=runtime.identity.backend, trial=trial
        )
        (tmp_path / "protocol-data").mkdir()
    await stub.PrepareTrial(prepare, metadata=metadata)
    await until(lambda: runtime.state.trial is not None)
    start = clock() + 100_000_000
    schedule = wire.ScheduleTrialRequest(
        command=command(runtime, work),
        start_monotonic_ns=start,
        normal_end_monotonic_ns=start + 1_000_000_000,
        trial_file_prefix="trial",
    )
    if saving:
        schedule.outputs.add(
            output_key="tracking",
            backend=runtime.identity.backend,
            trial=trial,
            path=str(tmp_path / "protocol-data/trial_tracking.jsonl"),
        )
    await stub.ScheduleTrial(schedule, metadata=metadata)
    await until(lambda: runtime.state.schedule is not None)
    release = wire.ReleaseTrialRequest(
        command=command(runtime, work),
        schedule_operation=pb.OperationContext(command_id=schedule.command.command_id),
        start_monotonic_ns=start,
        normal_end_monotonic_ns=schedule.normal_end_monotonic_ns,
    )
    await stub.ReleaseTrial(release, metadata=metadata)
    await until(lambda: runtime.state.release is not None)
    assert runtime.state.started is None
    clock.now = start
    await until(lambda: runtime.trials.native is not None)
    runtime.engine.source.feed(0, start)
    await until(lambda: runtime.state.started is not None)
    assert (
        runtime.state.started.first_required_activity[
            0
        ].device_evidence.tracking_evaluation.disposition
        == "baseline_only"
    )
    clock.now = start + 10_000_000
    runtime.engine.source.feed(1, clock())
    await until(lambda: runtime.engine.movement.result_sequence == 2)
    clock.now = schedule.normal_end_monotonic_ns
    await until(lambda: runtime.state.finished is not None)
    reports = [
        r.WhichOneof("report") for m, r in peer.reports if m == "ReportLifecycle"
    ]
    assert (
        reports.index("started") < reports.index("stopped") < reports.index("finished")
    )
    assert (
        runtime.state.stopped.producer_ends[0].end_monotonic_ns
        == schedule.normal_end_monotonic_ns
    )
    if saving:
        import json

        assert runtime.state.outputs[0].closure == pb.OUTPUT_CLOSURE_CLOSED
        records = [
            json.loads(line)["record"]
            for line in (tmp_path / "protocol-data/trial_tracking.jsonl")
            .read_text()
            .splitlines()
        ]
        assert records[0]["kind"] == "header" and records[-1]["kind"] == "completion"
        assert records[-1]["result_records"] == 2
        assert (
            json.loads(records[0]["prepared_methods_json"])["flow_sample_convention"]
            == "native_block_estimate_at_footprint_centre"
        )
        assert {item["stage_id"] for item in records[-2]["stage_evidence"]} == {
            "geometry",
            "estimator",
        }
    else:
        assert not runtime.state.outputs


async def test_preonset_stop_never_opens_recording_or_reports_started(
    rig_boundary, tmp_path
):
    runtime, clock, stub, _, metadata, _ = rig_boundary
    _, trial, _ = await setup_runtime(rig_boundary, tmp_path)
    work = pb.WorkContext(trial=trial)
    prepare = wire.PrepareTrialRequest(
        command=command(runtime, work),
        configuration_revision=1,
        plan=pb.TrialPlan(context=trial, resolved_duration_ns=10**9),
    )
    await stub.PrepareTrial(prepare, metadata=metadata)
    await until(lambda: runtime.state.trial is not None)
    start = clock() + 10**9
    schedule = wire.ScheduleTrialRequest(
        command=command(runtime, work),
        start_monotonic_ns=start,
        normal_end_monotonic_ns=start + 10**9,
        trial_file_prefix="cancelled",
    )
    await stub.ScheduleTrial(schedule, metadata=metadata)
    await until(lambda: runtime.state.schedule is not None)
    release = wire.ReleaseTrialRequest(
        command=command(runtime, work),
        schedule_operation=pb.OperationContext(command_id=schedule.command.command_id),
        start_monotonic_ns=start,
        normal_end_monotonic_ns=start + 10**9,
    )
    await stub.ReleaseTrial(release, metadata=metadata)
    await until(lambda: runtime.state.release is not None)
    await stub.AbortTrial(
        wire.StopTrialRequest(command=command(runtime, work)), metadata=metadata
    )
    await until(lambda: runtime.state.finished is not None)
    assert runtime.state.started is None and runtime.sink.writer is None
    assert runtime.state.stopped.producer_ends[0].end_monotonic_ns < start
    assert not list(tmp_path.glob("*tracking*"))
    # Retained release evidence survives replacement of the current projection.
    runtime.state.started = runtime.state.stopped = runtime.state.finished = None
    retained = await stub.GetRetainedResult(
        wire.RetainedResultQuery(
            query=wire.BackendQuery(target=runtime.identity.backend, work=work),
            command_id=release.command.command_id,
        ),
        metadata=metadata,
    )
    assert retained.HasField("stopped") and retained.HasField("finished")


async def test_cleanup_failure_retains_catalogue_and_prevents_new_setup(
    rig_boundary, tmp_path, monkeypatch
):
    runtime, clock, stub, _, metadata, _ = rig_boundary
    setup, _, _ = await setup_runtime(rig_boundary, tmp_path)

    def failure(deadline):
        raise RuntimeError("native handle still owned")

    with monkeypatch.context() as patch:
        patch.setattr(runtime.engine, "close", failure)
        await stub.Cleanup(command(runtime, setup.command.work), metadata=metadata)
        await until(lambda: runtime.state.cleanup is not None)
        assert not runtime.state.cleanup.trial_activity_stopped
        assert any(not item.released for item in runtime.state.cleanup.resources)
        again = wire.SetupSessionRequest.FromString(setup.SerializeToString())
        again.command.command_id = str(uuid4())
        assert (
            await stub.SetupSession(again, metadata=metadata)
        ).result == pb.COMMAND_RESULT_REJECTED


async def test_supervisor_accepts_real_tracking_heartbeat_catalogue(
    rig_boundary, tmp_path
):
    from cephvr.supervisor.runtime import SupervisorRuntime
    from cephvr.tracking.transport.peers import Peer as GrpcPeer
    from tests.supervisor.support import Native, Outbound, launch

    runtime, _, _, _, _, _ = rig_boundary
    native = Native()
    supervisor = SupervisorRuntime(
        identity=runtime.identity.supervisor,
        controller=runtime.identity.controller,
        credentials={
            ("tracking", runtime.identity.process.generation): "tracking-token",
            ("controller", runtime.identity.controller.generation): "controller-token",
        },
        native=native,
        outbound=Outbound(),
        software_root=tmp_path,
    )
    launch(
        supervisor, native, runtime.identity.supervisor, runtime.identity.process, 51
    )
    stimulus = pb.ProcessIdentity(role="visual_stimulus", generation=str(uuid4()))
    launch(supervisor, native, runtime.identity.supervisor, stimulus, 52)
    server = grpc.aio.server()
    rpc.add_SupervisorServiceServicer_to_server(supervisor.service, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    peer = GrpcPeer(
        f"127.0.0.1:{port}",
        Principal("tracking", runtime.identity.process.generation, "tracking-token"),
        1024 * 1024,
        kind="supervisor",
    )
    runtime.reports.supervisor = peer

    async def register(setup):
        context = wire.RegisteredContext(
            controller=runtime.identity.controller,
            supervisor=runtime.identity.supervisor,
            work=setup.command.work,
            operation=pb.OperationContext(command_id=setup.command.command_id),
            required_participants=[
                runtime.identity.backend,
                pb.BackendContext(
                    backend_name=stimulus.role, backend_generation=stimulus.generation
                ),
            ],
            session_directory=str(tmp_path),
            policies=setup.plan.policies,
            paired_spikeglx=False,
        )
        channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
        try:
            receipt = await rpc.SupervisorServiceStub(channel).RegisterContext(
                wire.RegisterContextRequest(command_id=str(uuid4()), context=context),
                metadata=Principal(
                    "controller",
                    runtime.identity.controller.generation,
                    "controller-token",
                ).metadata(),
            )
            assert receipt.admission.result == pb.COMMAND_RESULT_ACCEPTED, (
                receipt.failure
            )
        finally:
            await channel.close()

    try:
        await setup_runtime(rig_boundary, tmp_path, register)
        await runtime.reports.heartbeat(host_time_ns() + 2 * 10**9)
        assert runtime.state.resource_revision == 2
        status = supervisor.health
        assert (
            status is not None
        )  # The real service accepted generation/catalogue checks.
    finally:
        await peer.close()
        await server.stop(0)
