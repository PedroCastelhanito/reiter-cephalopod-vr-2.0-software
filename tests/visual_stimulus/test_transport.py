"""Real coordinator/renderer gRPC transport with a narrow GL-device adapter."""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
from uuid import uuid4

import grpc
import pytest
from tests.visual_stimulus.support import (
    Clock,
    Graphics,
    Preparation,
    Recorder,
    Reports,
    fixture_source,
    make_prepared_trial,
    valid_display_json,
)

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.auth import Principal
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger
from cephvr.visual_stimulus.coordinator.state import Identity
from cephvr.visual_stimulus.runtime import VisualStimulusCoordinatorRuntime
from cephvr.visual_stimulus.transport.peers import Peer
from cephvr.visual_stimulus.transport.server import serve
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus
from cephvr.visual_stimulus.worker.lifecycle import LifecycleDriver
from cephvr.visual_stimulus.worker.owner import RenderOwner
from cephvr.visual_stimulus.worker.runtime import VisualStimulusWorkerRuntime


def ledger(generation: str) -> CommandLedger:
    return CommandLedger(
        generation,
        300_000_000_000,
        max_records=64,
        max_bytes=4_000_000,
        result_reservation_bytes=65536,
        safety_reserve_records=8,
        safety_reserve_bytes=131072,
    )


class Device:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.thread_ids: list[int] = []

    def execute(self, method, request, deadline_ns):
        self.commands.append(method)
        self.thread_ids.append(threading.get_ident())

    def advance(self, now_ns):
        return None

    def fail(self, error):
        raise error


class ReportSink:
    def __init__(self):
        self.messages = []

    async def receipt(self, method, request, *, deadline_ns):
        self.messages.append((method, request))
        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)


class LifecycleDevice:
    """Small device boundary; the real LifecycleDriver and compiler own behavior."""

    def __init__(self, driver):
        self.driver = driver
        self.commands = []

    def execute(self, method, request, deadline_ns):
        self.commands.append(method)
        return self.driver.execute(method, request, deadline_ns)

    def advance(self, now_ns):
        return self.driver.advance(now_ns)

    def fail(self, error):
        self.driver.fail(error)


class LifecycleReports(Reports):
    async def receipt(self, method, request, *, deadline_ns):
        self.send(method, request, deadline_ns)
        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)


@pytest.mark.asyncio
async def test_worker_accepts_first_use_calibration_revision_and_recovers_after_close():
    identity = Identity(
        *(
            pb.ProcessIdentity(role=role, generation=str(uuid4()))
            for role in (
                "visual_stimulus",
                "controller",
                "supervisor",
                "visual_stimulus_renderer",
            )
        )
    )
    device = Device()
    owner = RenderOwner(lambda _: device)
    reports = ReportSink()
    worker = VisualStimulusWorkerRuntime(
        visual_stimulus.WorkerContext(worker=identity.worker, owner=identity.process),
        identity.supervisor,
        owner,
        reports,
        ledger(identity.worker.generation),
    )
    worker.interrupted = True
    owner.cancelled.set()

    async def diagnostic_request(method: str):
        command = visual_stimulus.WorkerCommand(
            command_id=str(uuid4()),
            issuer=identity.process,
            target=visual_stimulus.WorkerContext(
                worker=identity.worker,
                owner=identity.process,
                configuration_revision=8,
            ),
            deadline_monotonic_ns=host_time_ns() + 5_000_000_000,
        )
        request_type = (
            visual_stimulus.OpenDisplayCalibrationCommand
            if method == "OpenDisplayCalibration"
            else visual_stimulus.CloseDisplayCalibrationCommand
        )
        request = request_type(command=command, diagnostic_id=str(uuid4()))
        worker.ledger.admit(
            command.command_id,
            request.SerializeToString(deterministic=True),
            host_time_ns(),
            work_key=str(uuid4()),
            deadline_ns=command.deadline_monotonic_ns,
        )
        return await worker.execute(
            method, request, deadline_ns=command.deadline_monotonic_ns
        )

    deadline = host_time_ns() + 1_000_000_000
    try:
        opened = await diagnostic_request("OpenDisplayCalibration")
        assert opened.result == pb.COMMAND_RESULT_ACCEPTED
        assert not worker.interrupted and not owner.cancelled.is_set()
        assert device.commands == ["OpenDisplayCalibration"]
        worker.interrupted = True
        owner.cancelled.set()
        closed = await diagnostic_request("CloseDisplayCalibration")
        assert closed.result == pb.COMMAND_RESULT_ACCEPTED
        assert not worker.interrupted and not owner.cancelled.is_set()
        assert device.commands == [
            "OpenDisplayCalibration",
            "CloseDisplayCalibration",
        ]
    finally:
        await owner.close(deadline)


@pytest.mark.asyncio
async def test_authenticated_first_use_calibration_repeat_and_close_recovery(tmp_path):
    import hashlib
    from types import SimpleNamespace

    from cephvr.shared.transport_deadlines import deadline_metadata
    from cephvr.visual_stimulus.config.models.display_profile import parse_display_json
    from cephvr.visual_stimulus.rendering.types import (
        OutputActivity,
        ResourceReleaseReport,
    )
    from cephvr.visual_stimulus.v1 import runtime_pb2 as vp
    from cephvr.visual_stimulus.worker.reporting import ReportBridge

    identity = Identity(
        *(
            pb.ProcessIdentity(role=role, generation=str(uuid4()))
            for role in (
                "visual_stimulus",
                "controller",
                "supervisor",
                "visual_stimulus_renderer",
            )
        )
    )
    token = "sessionless-calibration-test"
    sink = ReportSink()
    provisional = Peer(
        "127.0.0.1:1",
        Principal("visual_stimulus", identity.process.generation, token),
        2_000_000,
        kind="worker",
    )
    command_ledger = ledger(identity.process.generation)
    coordinator = VisualStimulusCoordinatorRuntime(
        identity=identity,
        worker=provisional,
        controller=sink,
        supervisor=sink,
        ledger=command_ledger,
    )
    coordinator_listener = await serve(
        coordinator,
        {
            ("controller", identity.controller.generation): token,
            ("visual_stimulus_renderer", identity.worker.generation): token,
        },
        coordinator.ledger,
        port=0,
        max_message_bytes=2_000_000,
        testing=True,
    )
    worker_reports = Peer(
        f"127.0.0.1:{coordinator_listener.port}",
        Principal("visual_stimulus_renderer", identity.worker.generation, token),
        2_000_000,
        kind="coordinator",
    )
    bridge = ReportBridge(
        asyncio.get_running_loop(),
        worker_reports,
        sink,
        failed=lambda error: pytest.fail(str(error)),
        maximum_bytes=4_000_000,
    )
    profile_json = valid_display_json()
    profile = parse_display_json(profile_json, max_bytes=1_000_000)
    worker_id = identity.worker
    controller_id = identity.controller
    backend = identity.backend
    artifact = make_prepared_trial()
    graphics = Graphics(Clock(), artifact)
    graphics.close_failure_once = False
    graphics.presented_calibrations = 0
    graphics.cleanup = lambda: ResourceReleaseReport(())

    def activities():
        now = host_time_ns()
        return (OutputActivity("projector/main", now, now + 1, 1),)

    def present_display_calibration(selected, prepared):
        assert selected == profile
        graphics.presented_calibrations += 1
        return activities()

    def close_display_calibration(selected, prepared):
        assert selected == profile
        if graphics.close_failure_once:
            graphics.close_failure_once = False
            return activities(), False
        return activities(), True

    graphics.present_display_calibration = present_display_calibration
    graphics.close_display_calibration = close_display_calibration

    class CalibrationPreparation(Preparation):
        def __init__(self, artifact):
            super().__init__(artifact)
            self.block_next_prepare = False
            self.prepare_started = threading.Event()
            self.allow_prepare = threading.Event()

        def prepare_display_calibration(self, request, announce, deadline_ns):
            if self.block_next_prepare:
                self.block_next_prepare = False
                self.prepare_started.set()
                if not self.allow_prepare.wait(2):
                    raise TimeoutError("test preparation release was not signaled")
            return SimpleNamespace(
                display=parse_display_json(
                    request.profile_json,
                    max_bytes=request.policies.limits.max_document_bytes,
                ),
                previous_display=None,
                previous_calibration=None,
                arena=object(),
            )

        def release_display_calibration(self, prepared):
            return True

    preparation = CalibrationPreparation(artifact)
    driver = LifecycleDriver(
        worker=worker_id,
        owner=identity.process,
        controller=controller_id,
        policies=pb.ControlPolicies(recovery_ns=5_000_000_000),
        engine=graphics,
        preparation=preparation,
        recording=Recorder(),
        reports=bridge,
        cancelled=threading.Event(),
        clock=host_time_ns,
        shutdown=lambda: None,
    )
    renderer = RenderOwner(lambda _: LifecycleDevice(driver))
    worker_runtime = VisualStimulusWorkerRuntime(
        visual_stimulus.WorkerContext(worker=worker_id, owner=identity.process),
        identity.supervisor,
        renderer,
        worker_reports,
        ledger(worker_id.generation),
    )
    bridge.retain_lifecycle = worker_runtime.retain_and_report
    bridge.observe_display = worker_runtime.display.CopyFrom
    worker_listener = await serve(
        worker_runtime,
        {("visual_stimulus", identity.process.generation): token},
        worker_runtime.ledger,
        port=0,
        max_message_bytes=2_000_000,
        worker=True,
    )
    remote = Peer(
        f"127.0.0.1:{worker_listener.port}",
        Principal("visual_stimulus", identity.process.generation, token),
        2_000_000,
        kind="worker",
    )
    coordinator.worker = remote
    command_peer = Peer(
        f"127.0.0.1:{coordinator_listener.port}",
        Principal("controller", identity.controller.generation, token),
        2_000_000,
        kind="controller",
    )
    from cephvr.control.v1 import services_pb2 as wire_services
    from cephvr.control.v1 import services_pb2_grpc as rpc

    stub = rpc.VisualStimulusConfigurationServiceStub(command_peer.channel)
    metadata = command_peer.principal.metadata()
    arena = b"calibration arena"
    (tmp_path / "arena.glb").write_bytes(arena)
    policies = vp.VisualStimulusFilePolicies(contract_version=1)
    policies.limits.max_document_bytes = 1_000_000
    policies.limits.max_asset_cpu_bytes = 1_000_000
    policies.limits.max_asset_gpu_bytes = 1_000_000

    async def open_calibration(diagnostic_id):
        deadline = host_time_ns() + 5_000_000_000
        request = wire_services.VisualStimulusDisplayCalibrationOpenRequest(
            command_id=str(uuid4()),
            issuer=controller_id,
            target=backend,
            configuration_revision=8,
            diagnostic_id=diagnostic_id,
            deadline_monotonic_ns=deadline,
            profile_json=profile_json,
            profile_sha256=hashlib.sha256(profile_json.encode()).hexdigest(),
            asset_root=str(tmp_path),
            arena_relative_path="arena.glb",
            arena_size_bytes=len(arena),
            arena_sha256=hashlib.sha256(arena).hexdigest(),
            policies=policies,
        )
        return await stub.OpenDisplayCalibration(
            request,
            metadata=(*metadata, deadline_metadata(deadline)),
            timeout=5,
        )

    close_command_ids = {}

    async def close_calibration(diagnostic_id):
        deadline = host_time_ns() + 5_000_000_000
        request = wire_services.VisualStimulusDisplayCalibrationCloseRequest(
            command_id=str(uuid4()),
            issuer=controller_id,
            target=backend,
            configuration_revision=8,
            diagnostic_id=diagnostic_id,
            deadline_monotonic_ns=deadline,
        )
        close_command_ids[diagnostic_id] = request.command_id
        return await stub.CloseDisplayCalibration(
            request,
            metadata=(*metadata, deadline_metadata(deadline)),
            timeout=5,
        )

    async def wait_calibration(diagnostic_id, expected_state):
        stop = asyncio.get_running_loop().time() + 2
        while asyncio.get_running_loop().time() < stop:
            current = coordinator.state.display
            if (
                current is not None
                and current.HasField("calibration")
                and current.calibration.diagnostic_id == diagnostic_id
                and current.calibration.state == expected_state
            ):
                return current
            await asyncio.sleep(0.005)
        raise AssertionError(
            f"renderer did not publish {expected_state} for {diagnostic_id}"
        )

    deadline = host_time_ns() + 10_000_000_000
    try:
        pending = str(uuid4())
        preparation.block_next_prepare = True
        open_pending = asyncio.create_task(open_calibration(pending))
        assert await asyncio.to_thread(preparation.prepare_started.wait, 2)
        close_pending = asyncio.create_task(close_calibration(pending))
        closed_pending = await close_pending
        assert closed_pending.result == pb.COMMAND_RESULT_ACCEPTED
        close_command_id = ""
        stop = asyncio.get_running_loop().time() + 2
        while asyncio.get_running_loop().time() < stop:
            close_link = next(
                (
                    link
                    for link in coordinator.state.links.values()
                    if link.method == "CloseDisplayCalibration"
                    and link.parent.command_id == close_command_ids[pending]
                ),
                None,
            )
            if close_link is not None:
                close_command_id = close_link.child.command_id
            job = driver.display_calibration.job
            if (
                job is not None
                and job.cleanup_command is not None
                and close_command_id
                and job.cleanup_command.command_id == close_command_id
                and driver.display_calibration.active_id == pending
            ):
                break
            await asyncio.sleep(0.005)
        else:
            raise AssertionError(
                "worker did not apply pending Close: "
                f"links={[(key, item.method, item.parent.command_id) for key, item in coordinator.state.links.items()]} "
                f"commands={worker_runtime.command_ids} "
                f"job={driver.display_calibration.job!r} "
                f"active={driver.display_calibration.active_id}"
            )
        preparation.allow_prepare.set()
        assert (await open_pending).result == pb.COMMAND_RESULT_ACCEPTED
        idle_pending = await wait_calibration(
            pending, vp.DISPLAY_CALIBRATION_STATE_IDLE
        )
        await bridge.drain(deadline)
        assert idle_pending.calibration.resources_closed
        assert not idle_pending.calibration.presented
        assert graphics.presented_calibrations == 0

        first = str(uuid4())
        opened = await open_calibration(first)
        assert opened.result == pb.COMMAND_RESULT_ACCEPTED
        active = await wait_calibration(first, vp.DISPLAY_CALIBRATION_STATE_ACTIVE)
        await bridge.drain(deadline)
        assert active.calibration.presented
        assert graphics.presented_calibrations == 1
        closed = await close_calibration(first)
        assert closed.result == pb.COMMAND_RESULT_ACCEPTED
        idle = await wait_calibration(first, vp.DISPLAY_CALIBRATION_STATE_IDLE)
        await bridge.drain(deadline)
        assert idle.calibration.resources_closed

        second = str(uuid4())
        reopened = await open_calibration(second)
        assert reopened.result == pb.COMMAND_RESULT_ACCEPTED
        active = await wait_calibration(second, vp.DISPLAY_CALIBRATION_STATE_ACTIVE)
        await bridge.drain(deadline)
        assert active.calibration.presented
        assert graphics.presented_calibrations == 2
        graphics.close_failure_once = True
        failed_close = await close_calibration(second)
        assert failed_close.result == pb.COMMAND_RESULT_ACCEPTED
        unknown = await wait_calibration(second, vp.DISPLAY_CALIBRATION_STATE_UNKNOWN)
        await bridge.drain(deadline)
        assert worker_runtime.interrupted
        assert unknown.calibration.state == vp.DISPLAY_CALIBRATION_STATE_UNKNOWN

        recovered = await close_calibration(second)
        assert recovered.result == pb.COMMAND_RESULT_ACCEPTED
        idle = await wait_calibration(second, vp.DISPLAY_CALIBRATION_STATE_IDLE)
        await bridge.drain(deadline)
        assert not worker_runtime.interrupted
        assert idle.calibration.resources_closed

        third = str(uuid4())
        reopened = await open_calibration(third)
        assert reopened.result == pb.COMMAND_RESULT_ACCEPTED
        active = await wait_calibration(third, vp.DISPLAY_CALIBRATION_STATE_ACTIVE)
        assert active.calibration.presented
        cleanup_deadline = host_time_ns() + 5_000_000_000
        cleanup = wire.BackendCommand(
            command_id=str(uuid4()),
            issuer=controller_id,
            target=backend,
        )
        command_ledger.admit(
            cleanup.command_id,
            cleanup.SerializeToString(),
            host_time_ns(),
            work_key=cleanup.command_id,
            deadline_ns=cleanup_deadline,
            priority=True,
        )
        cleanup_admission = await coordinator.execute(
            "Shutdown", cleanup, deadline_ns=cleanup_deadline
        )
        assert cleanup_admission.result == pb.COMMAND_RESULT_ACCEPTED
        command_ledger.complete(
            cleanup.command_id, cleanup_admission.SerializeToString(), host_time_ns()
        )
        idle = await wait_calibration(third, vp.DISPLAY_CALIBRATION_STATE_IDLE)
        assert idle.calibration.resources_closed
        cleanup_stop = asyncio.get_running_loop().time() + 2
        while (
            not driver.state.cleaned
            and asyncio.get_running_loop().time() < cleanup_stop
        ):
            await asyncio.sleep(0.005)
        link = next(
            item
            for item in coordinator.state.links.values()
            if item.parent.command_id == cleanup.command_id
        )
        record = worker_runtime.ledger.get(link.child.command_id)
        assert record is not None and record.executor_result
        outcome = pb.OperationState.FromString(record.executor_result)
        assert outcome.succeeded, outcome.failure.message
        assert driver.state.cleaned
        assert coordinator.shutdown_requested.is_set()
    finally:
        await coordinator_listener.close(deadline)
        await worker_listener.close(deadline)
        await renderer.close(deadline)
        for peer in (provisional, remote, worker_reports, command_peer):
            await peer.close()


@pytest.mark.asyncio
async def test_authenticated_coordinator_renderer_replay_and_stale_generation():
    identity = Identity(
        *(
            pb.ProcessIdentity(role=role, generation=str(uuid4()))
            for role in (
                "visual_stimulus",
                "controller",
                "supervisor",
                "visual_stimulus_renderer",
            )
        )
    )
    token = "local-test-secret"
    sink = ReportSink()
    provisional = Peer(
        "127.0.0.1:1",
        Principal("visual_stimulus", identity.process.generation, token),
        1_000_000,
        kind="worker",
    )
    coordinator = VisualStimulusCoordinatorRuntime(
        identity=identity,
        worker=provisional,
        controller=sink,
        supervisor=sink,
        ledger=ledger(identity.process.generation),
    )
    listener = await serve(
        coordinator,
        {
            ("controller", identity.controller.generation): token,
            ("visual_stimulus_renderer", identity.worker.generation): token,
        },
        coordinator.ledger,
        port=0,
        max_message_bytes=1_000_000,
        testing=True,
    )
    reports = Peer(
        f"127.0.0.1:{listener.port}",
        Principal("visual_stimulus_renderer", identity.worker.generation, token),
        1_000_000,
        kind="coordinator",
    )
    device = Device()
    owner = RenderOwner(lambda _: device)
    worker = VisualStimulusWorkerRuntime(
        visual_stimulus.WorkerContext(worker=identity.worker, owner=identity.process),
        identity.supervisor,
        owner,
        reports,
        ledger(identity.worker.generation),
    )
    worker_listener = await serve(
        worker,
        {("visual_stimulus", identity.process.generation): token},
        worker.ledger,
        port=0,
        max_message_bytes=1_000_000,
        worker=True,
    )
    remote = Peer(
        f"127.0.0.1:{worker_listener.port}",
        Principal("visual_stimulus", identity.process.generation, token),
        1_000_000,
        kind="worker",
    )
    coordinator.worker = remote
    client = Peer(
        f"127.0.0.1:{listener.port}",
        Principal("controller", identity.controller.generation, token),
        1_000_000,
        kind="controller",
    )
    from cephvr.control.v1 import services_pb2_grpc as rpc
    from cephvr.shared.transport_deadlines import deadline_metadata

    stub = rpc.VisualStimulusConfigurationServiceStub(client.channel)
    deadline = host_time_ns() + 5_000_000_000
    request = wire.VisualStimulusDisplayInitializationRequest(
        command_id=str(uuid4()),
        issuer=identity.controller,
        target=identity.backend,
        configuration_revision=3,
        deadline_monotonic_ns=deadline,
    )
    metadata = (*client.principal.metadata(), deadline_metadata(deadline))
    try:
        first = await stub.InitializeDisplay(request, metadata=metadata, timeout=2)
        retry = await stub.InitializeDisplay(request, metadata=metadata, timeout=2)
        assert first == retry
        assert first.result == pb.COMMAND_RESULT_ACCEPTED
        for _ in range(100):
            if sink.messages:
                break
            await asyncio.sleep(0.01)
        assert device.commands == ["InitializeDisplay"]
        assert device.thread_ids == [owner.thread.ident]
        assert any(
            msg.operation.operation.complete
            for method, msg in sink.messages
            if method == "ReportLifecycle"
        )
        changed = wire.VisualStimulusDisplayInitializationRequest.FromString(
            request.SerializeToString()
        )
        changed.configuration_revision += 1
        rejected = await stub.InitializeDisplay(changed, metadata=metadata, timeout=2)
        assert rejected.result == pb.COMMAND_RESULT_REJECTED
        changed.command_id = str(uuid4())
        changed.target.backend_generation = str(uuid4())
        rejected = await stub.InitializeDisplay(changed, metadata=metadata, timeout=2)
        assert rejected.result == pb.COMMAND_RESULT_REJECTED
        forged = Principal("controller", identity.controller.generation, "wrong")
        with pytest.raises(grpc.aio.AioRpcError):
            await stub.InitializeDisplay(
                request,
                metadata=(*forged.metadata(), deadline_metadata(deadline)),
                timeout=2,
            )
        assert device.commands == ["InitializeDisplay"]
        assert (
            coordinator.state.display is None
        )  # Operation completion cannot fabricate Idle.
    finally:
        await listener.close(deadline)
        await worker_listener.close(deadline)
        await owner.close(deadline)
        for peer in (provisional, reports, remote, client):
            await peer.close()


@pytest.mark.asyncio
async def test_authenticated_supervisor_interrupt_cleanup_and_exact_worker_state(
    tmp_path,
):
    from tests.supervisor.support import make_runtime

    from cephvr.supervisor.outbound import GrpcOutbound

    supervisor, native, _, _ = make_runtime(tmp_path)
    identity = Identity(
        pb.ProcessIdentity(role="visual_stimulus", generation=str(uuid4())),
        supervisor.controller,
        supervisor.identity,
        pb.ProcessIdentity(role="visual_stimulus_renderer", generation=str(uuid4())),
    )
    token = "local-test-secret"
    sink = ReportSink()
    session = pb.SessionContext(
        controller_generation=identity.controller.generation, session_id=str(uuid4())
    )
    work = pb.WorkContext(session=session)
    context = visual_stimulus.WorkerContext(
        worker=identity.worker,
        owner=identity.process,
        work=work,
        configuration_revision=7,
    )
    device = Device()
    owner = RenderOwner(lambda _: device)
    worker = VisualStimulusWorkerRuntime(
        context,
        identity.supervisor,
        owner,
        sink,
        ledger(identity.worker.generation),
    )
    listener = await serve(
        worker,
        {("supervisor", identity.supervisor.generation): token},
        worker.ledger,
        port=0,
        max_message_bytes=1_000_000,
        worker=True,
    )
    outbound = GrpcOutbound(identity.supervisor, token, 1, -1, 1_000_000, {})
    outbound.bind_registry(supervisor.registry)
    control = supervisor.shutdown.visual_stimulus_worker_control
    control.outbound = outbound
    # Native process/job inspection is the only unavailable supervisor boundary.
    # The real renderer launch occurs at startup, before any work is assigned.
    plan = wire.PlanLaunchRequest(
        command_id=str(uuid4()),
        owner=identity.process,
        child=identity.worker,
        executable=r"C:\Python311\python.exe",
        python_worker=True,
        stop_method="grpc_shutdown",
    )
    planned = supervisor.registry.plan(plan)
    native.jobs[planned.containment_job_name] = [(11, 111, plan.executable)]
    confirm = wire.ConfirmLaunchRequest(
        command_id=str(uuid4()),
        launch_command_id=plan.command_id,
        owner=identity.process,
        child=identity.worker,
        pid=11,
        creation_time_100ns=111,
    )
    supervisor.registry.confirm(confirm, supervisor.clock)
    confirm.command_id = str(uuid4())
    confirm.endpoint = f"127.0.0.1:{listener.port}"
    confirm.host_clock.clock_id = supervisor.clock.clock_id
    confirm.host_clock.implementation = supervisor.clock.implementation
    confirm.host_clock.monotonic = supervisor.clock.monotonic
    confirm.host_clock.adjustable = supervisor.clock.adjustable
    confirm.host_clock.resolution_s = supervisor.clock.resolution_s
    supervisor.registry.confirm(confirm, supervisor.clock)
    supervisor.registration.state.context = wire.RegisteredContext(
        work=work,
        required_participants=[identity.backend],
    )
    deadline = host_time_ns() + 5_000_000_000
    try:
        targets = control.registered_workers(work)
        assert len(targets) == 1
        launch, target = targets[0]
        report = wire.InterruptionReport(
            issued_monotonic_ns=host_time_ns(),
            reason=pb.Failure(code="TEST_INTERRUPT", message="test safety stop"),
        )
        await control.interrupt_worker(launch, target, report, deadline)
        await control.cleanup_worker(launch, target, deadline)
        # Retrying with a later caller deadline reuses the original payload/deadline.
        await control.cleanup_worker(launch, target, deadline + 1_000_000_000)
        command_id = control.cleanup_commands[
            (identity.worker.role, identity.worker.generation)
        ]
        retained = await outbound.get_visual_stimulus_worker_state(
            launch,
            visual_stimulus.WorkerQuery(target=target, command_id=command_id),
            deadline_ns=deadline,
        )
        assert retained.command_known and retained.operation.succeeded
        assert control.retained_commands[command_id].deadline_monotonic_ns == deadline
        assert device.commands == ["InterruptSession", "Cleanup"]
        assert len(set(device.thread_ids)) == 1
        stale = visual_stimulus.WorkerContext.FromString(target.SerializeToString())
        stale.work.session.session_id = str(uuid4())
        with pytest.raises(RuntimeError, match="exact registered launch"):
            await control.cleanup_worker(launch, stale, deadline)
    finally:
        await listener.close(deadline)
        await owner.close(deadline)
        await outbound.close()


@pytest.mark.asyncio
async def test_authenticated_setup_compiles_and_hands_off_exact_prepared_trial():
    identity = Identity(
        *(
            pb.ProcessIdentity(role=role, generation=str(uuid4()))
            for role in (
                "visual_stimulus",
                "controller",
                "supervisor",
                "visual_stimulus_renderer",
            )
        )
    )
    token = "prepared-handoff-test"
    revision = 11
    session = pb.SessionContext(
        controller_generation=identity.controller.generation, session_id=str(uuid4())
    )
    trial = pb.TrialContext(session=session, trial_id=str(uuid4()))
    work = pb.WorkContext(session=session)
    context = visual_stimulus.WorkerContext(
        worker=identity.worker,
        owner=identity.process,
        work=work,
        configuration_revision=revision,
    )
    artifact = make_prepared_trial(
        session_id=session.session_id, trial_id=trial.trial_id
    )
    reports = LifecycleReports()
    recorder = Recorder()
    graphics_clock = Clock()
    graphics = Graphics(graphics_clock, artifact)
    driver = LifecycleDriver(
        worker=identity.worker,
        owner=identity.process,
        controller=identity.controller,
        policies=pb.ControlPolicies(
            start_evidence_allowance_ns=1_000_000,
            stop_evidence_allowance_ns=1_000_000,
            recovery_ns=10_000_000,
        ),
        engine=graphics,
        preparation=Preparation(artifact),
        recording=recorder,
        reports=reports,
        cancelled=threading.Event(),
        clock=host_time_ns,
        shutdown=lambda: None,
    )
    device = LifecycleDevice(driver)
    owner = RenderOwner(lambda _: device)
    worker = VisualStimulusWorkerRuntime(
        context,
        identity.supervisor,
        owner,
        reports,
        ledger(identity.worker.generation),
    )
    listener = await serve(
        worker,
        {("visual_stimulus", identity.process.generation): token},
        worker.ledger,
        port=0,
        max_message_bytes=2_000_000,
        worker=True,
    )
    client = Peer(
        f"127.0.0.1:{listener.port}",
        Principal("visual_stimulus", identity.process.generation, token),
        2_000_000,
        kind="worker",
    )
    deadline = host_time_ns() + 8_000_000_000

    def worker_command(
        target: visual_stimulus.WorkerContext,
    ) -> visual_stimulus.WorkerCommand:
        command_id = str(uuid4())
        return visual_stimulus.WorkerCommand(
            command_id=command_id,
            issuer=identity.process,
            target=target,
            parent_operation=pb.OperationContext(command_id=command_id),
            deadline_monotonic_ns=deadline,
        )

    setup = visual_stimulus.WorkerSetup()
    setup.command.CopyFrom(worker_command(context))
    setup.session.context.CopyFrom(session)
    setup.session.configuration_revision = revision
    source_trial = setup.session.trials.add(context=trial)
    source_trial.definition.trial_number = 1
    source_trial.definition.stimulus.program.program_json = fixture_source()
    source_trial.definition.stimulus.stimulus_seed_decimal = "17"
    source_trial.definition.stimulus.arena_boundaries.boundaries_json = json.dumps(
        {"format_version": 1, "bindings": []}
    )
    setup.settings.display.profile_json = valid_display_json()
    setup.policies.contract_version = 1
    setup.policies.limits.max_document_bytes = 1_000_000

    try:
        from cephvr.visual_stimulus.v1 import runtime_pb2 as vp

        initialize = visual_stimulus.InitializeDisplay(
            command=worker_command(context),
            display=vp.DisplayConfiguration(profile_json=valid_display_json()),
            limits=vp.ResourceLimits(
                max_document_bytes=1_000_000,
                max_asset_cpu_bytes=1_000_000,
                max_asset_gpu_bytes=1_000_000,
            ),
        )
        initialized = await client.command(
            "InitializeDisplay", initialize, deadline_ns=deadline
        )
        assert initialized.result == pb.COMMAND_RESULT_ACCEPTED
        assert "display:projector/main" in driver.state.pending_resources
        assert not any(
            method == "ReportWorkerHeartbeat" for method, _, _ in reports.records
        )
        admission = await client.command("SetupSession", setup, deadline_ns=deadline)
        assert admission.result == pb.COMMAND_RESULT_ACCEPTED
        for _ in range(100):
            if any(
                method == "ReportWorkerHeartbeat" for method, _, _ in reports.records
            ):
                break
            await asyncio.sleep(0.005)
        promoted = next(
            message
            for method, message, _ in reports.records
            if method == "ReportWorkerHeartbeat"
        )
        assert promoted.work == work
        assert "display:projector/main" in {
            item.resource for item in promoted.cleanup_resources
        }
        assert not driver.state.pending_resources
        for _ in range(200):
            if any(
                method == "ReportWorkerLifecycle"
                and message.report.WhichOneof("report") == "ready"
                for method, message, _ in reports.records
            ):
                break
            await asyncio.sleep(0.01)
        assert any(
            method == "ReportWorkerLifecycle"
            and message.report.WhichOneof("report") == "ready"
            for method, message, _ in reports.records
        ), (
            device.commands,
            reports.records,
            driver.state,
            driver.preparation_job.result.done() if driver.preparation_job else None,
            recorder.calls,
            owner.failure,
        )
        ready = next(
            message.report.ready
            for method, message, _ in reports.records
            if method == "ReportWorkerLifecycle"
            and message.report.WhichOneof("report") == "ready"
        )
        assert ready.configuration_revision == revision
        resolved_trial = ready.resolved_trials[0]
        handle = resolved_trial.resolved_stimulus.prepared
        prepared_reports = [
            message
            for method, message, _ in reports.records
            if method == "ReportWorkerOperation"
            and message.HasField("prepared_artifact")
        ]
        assert len(prepared_reports) == 1
        payload = prepared_reports[0].prepared_artifact.prepared_trial_json.encode()
        assert hashlib.sha256(payload).hexdigest() == handle.plan_sha256
        assert json.loads(payload)["identity"]["trial_id"] == trial.trial_id
        assert prepared_reports[0].prepared_artifact.sha256 == handle.plan_sha256

        trial_context = visual_stimulus.WorkerContext(
            worker=identity.worker,
            owner=identity.process,
            work=pb.WorkContext(trial=trial),
            configuration_revision=revision,
        )
        prepare = visual_stimulus.WorkerPrepareTrial(
            command=worker_command(trial_context), prepared=handle
        )
        prepare.trial.CopyFrom(resolved_trial)
        admission = await client.command("PrepareTrial", prepare, deadline_ns=deadline)
        assert admission.result == pb.COMMAND_RESULT_ACCEPTED
        for _ in range(100):
            if any(
                method == "ReportWorkerLifecycle"
                and message.report.WhichOneof("report") == "ready"
                and message.report.ready.context.operation.command_id
                == prepare.command.command_id
                for method, message, _ in reports.records
            ):
                break
            await asyncio.sleep(0.01)
        prepare_ready = next(
            message.report.ready
            for method, message, _ in reports.records
            if method == "ReportWorkerLifecycle"
            and message.report.WhichOneof("report") == "ready"
            and message.report.ready.context.operation.command_id
            == prepare.command.command_id
        )
        assert prepare_ready.configuration_revision == revision
        assert len(prepare_ready.resolved_trials) == 1
        handed_off = prepare_ready.resolved_trials[0]
        assert handed_off.context.trial_id == trial.trial_id
        assert handed_off.resolved_stimulus.prepared.plan_sha256 == handle.plan_sha256
        assert graphics.artifact.identity == artifact.identity
        assert any(
            method == "ReportWorkerLifecycle"
            and message.report.WhichOneof("report") == "ready"
            and message.report.ready.configuration_revision == revision
            for method, message, _ in reports.records
        )

        stale_target = visual_stimulus.WorkerContext.FromString(
            trial_context.SerializeToString()
        )
        stale_target.configuration_revision += 1
        stale = visual_stimulus.WorkerPrepareTrial(
            command=worker_command(stale_target), prepared=handle
        )
        stale.trial.CopyFrom(resolved_trial)
        stale_admission = await client.command(
            "PrepareTrial", stale, deadline_ns=deadline
        )
        assert stale_admission.result == pb.COMMAND_RESULT_REJECTED
        expired = worker_command(trial_context)
        expired.deadline_monotonic_ns = host_time_ns() - 1
        overdue = visual_stimulus.WorkerPrepareTrial(command=expired, prepared=handle)
        overdue.trial.CopyFrom(resolved_trial)
        overdue_admission = await client.command(
            "PrepareTrial", overdue, deadline_ns=deadline
        )
        assert overdue_admission.result == pb.COMMAND_RESULT_REJECTED
    finally:
        await listener.close(deadline)
        await owner.close(deadline)
        await client.close()


@pytest.mark.asyncio
async def test_completed_worker_outcome_survives_report_receipt_loss():
    identity = Identity(
        *(
            pb.ProcessIdentity(role=role, generation=str(uuid4()))
            for role in (
                "visual_stimulus",
                "controller",
                "supervisor",
                "visual_stimulus_renderer",
            )
        )
    )

    class LostReceipt:
        async def receipt(self, method, request, *, deadline_ns):
            raise ConnectionError("coordinator receipt lost")

    device = Device()
    owner = RenderOwner(lambda _: device)
    failures = []
    commands = ledger(identity.worker.generation)
    runtime = VisualStimulusWorkerRuntime(
        visual_stimulus.WorkerContext(worker=identity.worker, owner=identity.process),
        identity.supervisor,
        owner,
        LostReceipt(),
        commands,
        delivery_failed=failures.append,
    )
    deadline = host_time_ns() + 5_000_000_000
    request = visual_stimulus.WorkerCommand(
        command_id=str(uuid4()),
        issuer=identity.process,
        target=runtime.context,
        deadline_monotonic_ns=deadline,
    )
    commands.admit(
        request.command_id,
        request.SerializeToString(),
        host_time_ns(),
        work_key=request.command_id,
        deadline_ns=deadline,
    )
    try:
        result = await runtime.execute("Shutdown", request, deadline_ns=deadline)
        outcome = pb.OperationState.FromString(
            commands.get(request.command_id).executor_result
        )
        assert outcome.complete and outcome.succeeded
        assert result.result == pb.COMMAND_RESULT_ACCEPTED
        assert runtime.interrupted and owner.cancelled.is_set()
        assert len(failures) == 1 and isinstance(failures[0], ConnectionError)
        assert device.commands == ["Shutdown"]
    finally:
        await owner.close(deadline)
