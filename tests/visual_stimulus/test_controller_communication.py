"""Real controller/Visual Stimulus services with only display hardware injected (E15)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import grpc
import pytest
from tests.controller.support_components import _runtime

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import services_pb2_grpc as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.backend import BackendRegistration, GrpcBackendPort
from cephvr.controller.runtime import ControllerRuntime
from cephvr.controller.service import ExperimentControllerService
from cephvr.shared.auth import Principal
from cephvr.shared.clock import host_time_ns
from cephvr.visual_stimulus.configuration import validate_display_profile
from cephvr.visual_stimulus.coordinator.state import Identity
from cephvr.visual_stimulus.main import command_ledger
from cephvr.visual_stimulus.runtime import VisualStimulusCoordinatorRuntime
from cephvr.visual_stimulus.transport.peers import Peer
from cephvr.visual_stimulus.transport.pending import PendingPeer
from cephvr.visual_stimulus.transport.server import serve
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus
from cephvr.visual_stimulus.v1 import runtime_pb2 as vp
from cephvr.visual_stimulus.worker.lifecycle import LifecycleDriver
from cephvr.visual_stimulus.worker.owner import RenderOwner
from cephvr.visual_stimulus.worker.reporting import ReportBridge
from cephvr.visual_stimulus.worker.runtime import VisualStimulusWorkerRuntime

from .support import (
    Graphics,
    Preparation,
    Recorder,
    make_prepared_trial,
    valid_display_json,
)


class SupervisorReceipt:
    async def receipt(self, method, request, *, deadline_ns):
        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)


class UnavailableHardware:
    def __getattr__(self, name):
        raise AssertionError(f"configuration communication accessed hardware: {name}")


@pytest.mark.asyncio
async def test_controller_exposes_nonfatal_validation_without_invalidating_configuration(
    tmp_path,
):
    runtime = _runtime(
        tmp_path,
        pb.BackendContext(
            backend_name="visual_stimulus", backend_generation=str(uuid4())
        ),
    )
    result = pb.ValidationResult(
        component="visual_stimulus", completed=True, valid=True
    )
    result.issues.add(
        component="visual_stimulus",
        failure=pb.Failure(
            code="PREDICTABLE_CLIPPING", message="linear output may clip"
        ),
    )
    runtime.configuration_state.retain_validation([result])
    result.ClearField("issues")
    first = await runtime.snapshot()
    assert first.configuration.edit_validation[0].valid
    assert (
        first.configuration.edit_validation[0].configuration_revision
        == runtime.configuration_state.revision
    )
    assert first.warnings[-1].issues[0].failure.code == "PREDICTABLE_CLIPPING"
    second = await runtime.snapshot()
    assert first.warnings[-1].warning_id == second.warnings[-1].warning_id
    runtime.configuration_state.retain_validation([result])
    assert not (await runtime.snapshot()).warnings


def acquisition_runtime(identity):
    from cephvr.acquisition.coordinator.workers import WorkerRegistry
    from cephvr.acquisition.runtime import AcquisitionCoordinatorRuntime
    from cephvr.acquisition.state import ConfigurationRecord, CoordinatorIdentity
    from cephvr.acquisition.v1 import runtime_pb2 as acq
    from cephvr.platform.windows.resource_ledger import NativeResourceLedger

    process = pb.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    backend = pb.BackendContext(
        backend_name="acquisition", backend_generation=process.generation
    )
    ledger = command_ledger(process.generation, 10**12, 1_000_000)
    unavailable = UnavailableHardware()
    policies = pb.ControlPolicies(
        recovery_ns=10**9,
        start_evidence_allowance_ns=10**8,
        stop_evidence_allowance_ns=10**8,
    )
    policies.trial_finished.initial_ns = 10**9
    files = acq.AcquisitionFilePolicies(
        serial_ack_timeout_ns=1_000_000,
        serial_keepalive_interval_ns=10_000_000,
        serial_communication_timeout_ns=100_000_000,
    )
    workers = WorkerRegistry(
        workers={},
        launches={},
        commands=ledger,
        owner=process,
        policies=policies,
        file_policies=files,
        coordinator_endpoint="127.0.0.1:1",
        heartbeat_interval_ns=100_000_000,
        health_silence_ns=10**9,
        bootstrap=unavailable,
        executables=unavailable,
        supervisor=unavailable,
        cleanup_complete=lambda *_: False,
    )
    return AcquisitionCoordinatorRuntime(
        identity=CoordinatorIdentity(
            backend,
            process,
            identity.controller,
            identity.supervisor,
            pb.ProcessIdentity(role="tracking", generation=str(uuid4())),
        ),
        configuration=ConfigurationRecord(pb.AcquisitionSettings(), files),
        control_policies=policies,
        commands=ledger,
        resource_ledger=NativeResourceLedger(
            max_resources=32, max_transfers_per_resource=4
        ),
        workers=workers,
        controller=unavailable,
        supervisor=unavailable,
        serial=unavailable,
        resource_port=unavailable,
        session_config_reference=lambda _: "unused",
    )


@pytest.mark.asyncio
async def test_controller_port_queries_actual_acquisition_and_visual_stimulus_without_hardware():
    from cephvr.acquisition.transport.services import AcquisitionBackendService
    from cephvr.shared.admission import CommandAdmissionTransport

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
    token = "authenticated-backend-query"
    credentials = {("controller", identity.controller.generation): token}
    acquisition = acquisition_runtime(identity)
    admission = CommandAdmissionTransport(acquisition.commands)
    acq_server = grpc.aio.server()
    rpc.add_BackendServiceServicer_to_server(
        AcquisitionBackendService(acquisition, credentials, admission), acq_server
    )
    acq_port = acq_server.add_insecure_port("127.0.0.1:0")
    await acq_server.start()
    peer = SupervisorReceipt()
    visual_stimulus_runtime = VisualStimulusCoordinatorRuntime(
        identity=identity,
        worker=PendingPeer(),
        controller=peer,
        supervisor=peer,
        ledger=command_ledger(identity.process.generation, 10**12, 1_000_000),
    )
    visual_stimulus_server = await serve(
        visual_stimulus_runtime,
        credentials,
        visual_stimulus_runtime.ledger,
        port=0,
        max_message_bytes=1_000_000,
        testing=True,
    )
    ports = [
        GrpcBackendPort(
            BackendRegistration(name, generation, f"127.0.0.1:{port}", token),
            Principal("controller", identity.controller.generation, token),
            max_message_bytes=1_000_000,
        )
        for name, generation, port in (
            ("acquisition", acquisition.identity.generation, acq_port),
            (
                "visual_stimulus",
                identity.process.generation,
                visual_stimulus_server.port,
            ),
        )
    ]
    deadline = host_time_ns() + 5_000_000_000
    try:
        states = await asyncio.gather(
            *(
                port.get_state(
                    wire.BackendQuery(target=port.context), deadline_ns=deadline
                )
                for port in ports
            )
        )
        assert [item.process.role for item in states] == [
            "acquisition",
            "visual_stimulus",
        ]
        assert all(
            item.process_running and not item.HasField("ready") for item in states
        )
        assert acquisition.state.session_slot.current is None
        assert visual_stimulus_runtime.state.setup is None
    finally:
        await admission.close(deadline)
        await acq_server.stop(0)
        await visual_stimulus_server.close(deadline)
        for port in ports:
            await port.channel.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("startup_issue", [None, "monitor", "adapter", "assets"])
async def test_controller_initialize_display_retains_confirmed_idle_separately_from_ready(
    tmp_path,
    startup_issue,
):
    missing_output = startup_issue is not None
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
    token = "loopback-test-credential"
    sink = SupervisorReceipt()
    pending = PendingPeer()
    coordinator = VisualStimulusCoordinatorRuntime(
        identity=identity,
        worker=pending,
        controller=sink,
        supervisor=sink,
        ledger=command_ledger(identity.process.generation, 10**12, 1_000_000),
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
    backend = GrpcBackendPort(
        BackendRegistration(
            "visual_stimulus",
            identity.process.generation,
            f"127.0.0.1:{listener.port}",
            token,
        ),
        Principal("controller", identity.controller.generation, token),
        max_message_bytes=1_000_000,
    )
    configuration = pb.ExperimentConfiguration()
    configuration.backends.add(
        backend_name="visual_stimulus",
        enabled=True,
        visual_stimulus=pb.VisualStimulusSettings(
            display=vp.DisplayConfiguration(profile_json=valid_display_json())
        ),
    )
    policy = vp.VisualStimulusFilePolicies()
    policy.limits.max_document_bytes = 1_000_000
    limits = _runtime(tmp_path, identity.backend).limits
    controller = ControllerRuntime(
        generation=identity.controller.generation,
        configuration=configuration,
        limits=limits,
        validators={},
        backends={"visual_stimulus": backend},
        file_policy_loader=lambda active: {"visual_stimulus": policy},
        display_validator=validate_display_profile,
        supervisor_generation=identity.supervisor.generation,
    )

    async def no_operator(*_):
        raise AssertionError("test never authenticates an operator")

    service = ExperimentControllerService(
        controller,
        client_authentication=no_operator,
        peer_tokens={"visual_stimulus": (identity.process.generation, token)},
    )
    controller_server = grpc.aio.server()
    rpc.add_ExperimentControllerServiceServicer_to_server(service, controller_server)
    controller_port = controller_server.add_insecure_port("127.0.0.1:0")
    await controller_server.start()
    controller_peer = Peer(
        f"127.0.0.1:{controller_port}",
        Principal("visual_stimulus", identity.process.generation, token),
        1_000_000,
        kind="controller",
    )
    coordinator.controller = coordinator.reports.controller = controller_peer
    reports = Peer(
        f"127.0.0.1:{listener.port}",
        Principal("visual_stimulus_renderer", identity.worker.generation, token),
        1_000_000,
        kind="coordinator",
    )
    errors = []
    bridge = ReportBridge(
        asyncio.get_running_loop(),
        reports,
        sink,
        failed=errors.append,
        maximum_bytes=4_000_000,
    )
    artifact = make_prepared_trial()

    class StartupPreparation(Preparation):
        def prepare_display(self, request, announce, deadline_ns):
            if startup_issue == "assets":
                (tmp_path / "missing-assets").resolve(strict=True)
            return super().prepare_display(request, announce, deadline_ns)

        def initialize_display(self, display, calibration):
            if missing_output:
                from cephvr.visual_stimulus.rendering.native_display import (
                    DisplayGpuUnavailableError,
                    DisplayUnavailableError,
                )

                if startup_issue == "adapter":
                    raise DisplayGpuUnavailableError("OpenGL context uses AMD Radeon")
                raise DisplayUnavailableError(
                    "saved projector matched 0 active monitors"
                )
            return super().initialize_display(display, calibration)

    owner = RenderOwner(
        lambda cancelled: LifecycleDriver(
            worker=identity.worker,
            owner=identity.process,
            controller=identity.controller,
            policies=pb.ControlPolicies(),
            engine=Graphics(host_time_ns, artifact),
            preparation=StartupPreparation(artifact),
            recording=Recorder(),
            reports=bridge,
            cancelled=cancelled,
            shutdown=lambda: None,
        )
    )
    worker = VisualStimulusWorkerRuntime(
        visual_stimulus.WorkerContext(worker=identity.worker, owner=identity.process),
        identity.supervisor,
        owner,
        reports,
        command_ledger(identity.worker.generation, 10**12, 1_000_000),
    )
    bridge.retain_lifecycle = worker.retain_and_report
    worker_server = await serve(
        worker,
        {("visual_stimulus", identity.process.generation): token},
        worker.ledger,
        port=0,
        max_message_bytes=1_000_000,
        worker=True,
    )
    worker_peer = Peer(
        f"127.0.0.1:{worker_server.port}",
        Principal("visual_stimulus", identity.process.generation, token),
        1_000_000,
        kind="worker",
    )
    pending.attach(worker_peer)
    deadline = host_time_ns() + 5_000_000_000
    try:
        admission = await controller.initialize_display()
        assert admission.result == pb.COMMAND_RESULT_ACCEPTED, admission.failure.message
        for _ in range(200):
            if controller.projections.display is not None:
                break
            await asyncio.sleep(0.005)
        display = controller.projections.display
        assert display is not None, errors
        assert display.complete
        assert display.HasField("applied_revision") is not missing_output
        assert display.source == identity.process
        if missing_output:
            assert display.issues[0].failure.code == (
                "DISPLAY_ASSET_UNAVAILABLE"
                if startup_issue == "assets"
                else "DISPLAY_OUTPUT_UNAVAILABLE"
            )
            snapshot = await controller.snapshot()
            operation = next(
                item
                for item in snapshot.operations
                if item.context.command_id == admission.command_id
            )
            assert operation.complete and not operation.succeeded
            assert (
                "Protocol Assets"
                if startup_issue == "assets"
                else "RTX 5060 Ti"
                if startup_issue == "adapter"
                else "Check power/cables"
            ) in operation.failure.message
            assert display.resources and all(
                item.released for item in display.resources
            )
        else:
            assert display.outputs[0].idle_submission == vp.SUBMISSION_OUTCOME_RETURNED
        for _ in range(200):
            record = coordinator.ledger.get(admission.command_id)
            if record is not None and record.executor_result:
                break
            await asyncio.sleep(0.005)
        outcome = pb.OperationState.FromString(record.executor_result)
        assert outcome.complete and outcome.succeeded is not missing_output
        assert not coordinator.state.interrupted and not worker.interrupted
        assert not owner.cancelled.is_set()
        assert controller.lifecycle.session.phase == pb.SESSION_PHASE_CONFIGURATION
        assert controller.lifecycle.attempt is None
        assert not coordinator.state.reports
        assert not errors
    finally:
        for task in tuple(controller._tasks):
            task.cancel()
        await asyncio.gather(*controller._tasks, return_exceptions=True)
        await owner.close(deadline)
        await bridge.drain(deadline)
        await listener.close(deadline)
        await worker_server.close(deadline)
        await service.aclose()
        await controller_server.stop(0)
        await backend.channel.close()
        for peer in (controller_peer, reports, worker_peer):
            await peer.close()


@pytest.mark.parametrize(
    "calibration_view", ["frame_grid", "photodiode_placement", "blackout_placement"]
)
@pytest.mark.asyncio
async def test_authenticated_live_calibration_update_transport_and_exact_receipt(
    calibration_view,
):
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
    calls = []

    loop = asyncio.get_running_loop()

    class Driver:
        def __init__(self):
            self.failures = []

        def execute(self, method, request, deadline_ns):
            calls.append((method, request, deadline_ns))
            rejected = (
                request.adjustments and request.adjustments[0].mapping_id == "reject"
            ) or '"x": 999' in request.placement_json
            report = pb.VisualStimulusDisplayView(
                source=identity.worker,
                backend=identity.backend,
                controller=identity.controller,
                command_id=request.command.command_id,
                requested_revision=4,
                complete=True,
            )
            report.outputs.add(output_id="projector/main")
            report.calibration.CopyFrom(runtime.state.display.calibration)
            if rejected:
                report.calibration.failure_code = "CALIBRATION_ADJUSTMENT_REJECTED"
            else:
                report.calibration.adjustment_sequence = request.adjustment_sequence
                report.calibration.presented = True
                report.calibration.ClearField("failure_code")
            asyncio.run_coroutine_threadsafe(
                runtime.report("ReportDisplay", report, ingress_ns=host_time_ns()),
                loop,
            ).result(timeout=1)
            if rejected:
                from cephvr.visual_stimulus.config.calibration_adjustments import (
                    CalibrationAdjustmentRejected,
                )

                raise CalibrationAdjustmentRejected(
                    "stale mapping rejected before GL writes"
                )

        def advance(self, now_ns):
            return None

        def fail(self, error):
            self.failures.append(error)

    driver = Driver()
    owner = RenderOwner(lambda _: driver)
    worker = VisualStimulusWorkerRuntime(
        visual_stimulus.WorkerContext(worker=identity.worker, owner=identity.process),
        identity.supervisor,
        owner,
        SupervisorReceipt(),
        command_ledger(identity.worker.generation, 10**12, 1_000_000),
    )
    worker_token = "live-grid-renderer-test"
    worker_listener = await serve(
        worker,
        {("visual_stimulus", identity.process.generation): worker_token},
        worker.ledger,
        port=0,
        max_message_bytes=1_000_000,
        worker=True,
        testing=True,
    )
    worker_peer = Peer(
        f"127.0.0.1:{worker_listener.port}",
        Principal("visual_stimulus", identity.process.generation, worker_token),
        1_000_000,
        kind="worker",
    )

    receipt = SupervisorReceipt()
    runtime = VisualStimulusCoordinatorRuntime(
        identity=identity,
        worker=worker_peer,
        controller=receipt,
        supervisor=receipt,
        ledger=command_ledger(identity.process.generation, 10**12, 1_000_000),
    )
    runtime.state.display = pb.VisualStimulusDisplayView()
    runtime.state.display.outputs.add(output_id="projector/main")
    evidence = runtime.state.display.calibration
    evidence.diagnostic_id = str(uuid4())
    evidence.configuration_revision = 4
    evidence.controller_generation = identity.controller.generation
    evidence.renderer_generation = identity.worker.generation
    evidence.state = vp.DISPLAY_CALIBRATION_STATE_ACTIVE
    evidence.calibration_view = calibration_view
    token = "live-calibration-transport-test"
    listener = await serve(
        runtime,
        {("controller", identity.controller.generation): token},
        runtime.ledger,
        port=0,
        max_message_bytes=1_000_000,
        testing=True,
    )
    registration = BackendRegistration(
        "visual_stimulus",
        identity.process.generation,
        f"127.0.0.1:{listener.port}",
        token,
    )
    port = GrpcBackendPort(
        registration,
        Principal("controller", identity.controller.generation, token),
        max_message_bytes=1_000_000,
    )
    wrong_port = GrpcBackendPort(
        registration,
        Principal("controller", identity.controller.generation, "wrong-token"),
        max_message_bytes=1_000_000,
    )
    deadline = host_time_ns() + 5_000_000_000
    request = wire.VisualStimulusDisplayCalibrationUpdateRequest(
        command_id=str(uuid4()),
        issuer=identity.controller,
        target=identity.backend,
        configuration_revision=4,
        diagnostic_id=evidence.diagnostic_id,
        deadline_monotonic_ns=deadline,
        adjustment_sequence=1,
    )
    request.adjustments.add(
        mapping_id="diagnostic_front",
        destination_xy=[0.1, 0.1, 0.9, 0.1, 0.1, 0.9, 0.9, 0.9],
    )
    import json

    placement_value = dict(
        outputs=[dict(output_id="projector/main", blackout_zones=[])],
        **(
            dict(
                photodiode_output_id="projector/main",
                photodiode_patch=dict(
                    rect=dict(x=1, y=1, width=2, height=2),
                    high_linear_rgb=[1, 1, 1],
                    low_linear_rgb=[0, 0, 0],
                ),
            )
            if calibration_view == "photodiode_placement"
            else {}
        ),
    )
    if calibration_view != "frame_grid":
        request.ClearField("adjustments")
        request.placement_json = json.dumps(placement_value)
    try:
        with pytest.raises(grpc.aio.AioRpcError) as wrong:
            await wrong_port.update_display_calibration(request, deadline_ns=deadline)
        assert wrong.value.code() == grpc.StatusCode.PERMISSION_DENIED
        admission = await port.update_display_calibration(request, deadline_ns=deadline)
        assert admission.result == pb.COMMAND_RESULT_ACCEPTED
        for _ in range(200):
            if calls:
                break
            await asyncio.sleep(0.005)
        assert len(calls) == 1
        method, child, child_deadline = calls[0]
        assert method == "UpdateDisplayCalibration"
        assert child.diagnostic_id == request.diagnostic_id
        assert child.adjustment_sequence == 1
        assert child.placement_json == request.placement_json
        assert child_deadline <= deadline
        report = pb.VisualStimulusDisplayView(
            command_id=child.command.command_id,
            source=identity.worker,
            backend=identity.backend,
            controller=identity.controller,
            requested_revision=4,
        )
        report.outputs.add(output_id="projector/main")
        report.calibration.CopyFrom(evidence)
        report.calibration.presented = True
        report.calibration.adjustment_sequence = 0
        with pytest.raises(ValueError, match="sequence"):
            await runtime.report("ReportDisplay", report, ingress_ns=host_time_ns())
        report.calibration.adjustment_sequence = 1
        await runtime.report("ReportDisplay", report, ingress_ns=host_time_ns())
        await runtime.report(
            "ReportWorkerOperation",
            visual_stimulus.WorkerOperation(
                source=child.command.target,
                operation=pb.OperationState(
                    context=pb.OperationContext(command_id=child.command.command_id),
                    command=method,
                    complete=True,
                    succeeded=True,
                ),
            ),
            ingress_ns=host_time_ns(),
        )
        assert runtime.state.display.calibration.adjustment_sequence == 1
        request.command_id = str(uuid4())
        rejected = await port.update_display_calibration(request, deadline_ns=deadline)
        assert rejected.result == pb.COMMAND_RESULT_REJECTED
        assert len(calls) == 1
        request.command_id = str(uuid4())
        request.adjustment_sequence = 2
        if calibration_view == "frame_grid":
            request.adjustments[0].mapping_id = "reject"
        else:
            placement_value["outputs"][0]["blackout_zones"] = [
                dict(x=999, y=1, width=2, height=2)
            ]
            request.placement_json = json.dumps(placement_value)
        await port.update_display_calibration(request, deadline_ns=deadline)
        for _ in range(200):
            if len(calls) == 2:
                record = worker.ledger.get(calls[-1][1].command.command_id)
                if record is not None and record.executor_result:
                    break
            await asyncio.sleep(0.005)
        assert len(calls) == 2
        outcome = pb.OperationState.FromString(record.executor_result)
        assert outcome.complete and not outcome.succeeded
        assert outcome.failure.code == "CALIBRATION_ADJUSTMENT_REJECTED"
        assert not worker.interrupted and not worker.owner.cancelled.is_set()
        assert not runtime.state.interrupted
        assert not driver.failures
        assert runtime.state.display.calibration.adjustment_sequence == 1
        request.command_id = str(uuid4())
        if calibration_view == "frame_grid":
            request.adjustments[0].mapping_id = "diagnostic_front"
        else:
            placement_value["outputs"][0]["blackout_zones"] = []
            request.placement_json = json.dumps(placement_value)
        admission = await port.update_display_calibration(request, deadline_ns=deadline)
        assert admission.result == pb.COMMAND_RESULT_ACCEPTED
        for _ in range(200):
            if len(calls) == 3:
                record = worker.ledger.get(calls[-1][1].command.command_id)
                if record is not None and record.executor_result:
                    break
            await asyncio.sleep(0.005)
        assert len(calls) == 3
        assert pb.OperationState.FromString(record.executor_result).succeeded
        assert runtime.state.display.calibration.adjustment_sequence == 2
        assert not runtime.state.interrupted and not driver.failures
    finally:
        await owner.close(host_time_ns() + 2_000_000_000)
        await port.channel.close()
        await wrong_port.channel.close()
        await listener.close(host_time_ns() + 2_000_000_000)
        await worker_peer.channel.close()
        await worker_listener.close(host_time_ns() + 2_000_000_000)
