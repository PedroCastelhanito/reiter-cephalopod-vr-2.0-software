"""Camera and display admission under deadline and capacity pressure."""

from __future__ import annotations

import asyncio
import hashlib
import threading
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

from cephvr.acquisition.v1 import camera_pb2 as camera_pb
from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.operations import ControlOperations
from cephvr.controller.device.camera import (
    CameraCommands,
    CameraDispatch,
    CameraSelection,
)
from cephvr.controller.device.display import DisplayInitialization
from cephvr.controller.device.display_calibration import DisplayCalibrationController
from cephvr.controller.device.ports import DeviceHooks
from cephvr.controller.device.status_retention import CameraStatusRetention
from cephvr.controller.ports import BackendPort
from cephvr.controller.state import (
    CameraOperation,
    ConfigurationState,
    ControlState,
    DeviceState,
    LifecycleState,
    LimitsState,
    Watch,
)
from cephvr.shared.commands import CommandLedger
from cephvr.visual_stimulus.v1 import runtime_pb2 as visual_stimulus_pb
from tests.controller.support_components import _id, _runtime, default_limits
from tests.visual_stimulus.support import valid_display_json


def _limits() -> LimitsState:
    return LimitsState(default_limits())


class _Env:
    def __init__(self, max_records: int = 8) -> None:
        self.lifecycle = LifecycleState()
        self.configuration = ConfigurationState(
            pb.ExperimentConfiguration(), pb.ControlPolicies()
        )
        self.control = ControlState()
        self.device = DeviceState()
        self.now = 1_000
        self.spawned: list[Any] = []
        self.published = 0
        self.ops = ControlOperations(
            lifecycle=self.lifecycle,
            configuration=self.configuration,
            control=self.control,
            generation=_id(),
            max_operation_records=max_records,
            clock=lambda: self.now,
        )
        self.hooks = DeviceHooks(
            admission=self.ops.admission,
            authorized=lambda command, **_: "",
            operation=self.ops.operation,
            complete_operation=self.ops.complete_operation,
            prune_operations=self.ops.prune_operations,
            publish=self._publish,
            spawn=self.spawned.append,
        )

    def _publish(self) -> None:
        self.published += 1


class _FailingBackend:
    context = pb.BackendContext(backend_name="acquisition", backend_generation=_id())

    async def execute_camera_command(self, command: Any, *, deadline_ns: int) -> Any:
        raise ConnectionError("link lost")


async def test_camera_admission_failure_keeps_slot_until_deadline() -> None:
    env = _Env()
    retention = CameraStatusRetention(env.device, clock=lambda: env.now)
    generation = _id()
    retention.bind_ledger(
        CommandLedger(
            generation,
            10_000,
            max_records=16,
            max_bytes=1_000_000,
            result_reservation_bytes=4096,
        )
    )
    camera = CameraCommands(
        lifecycle=env.lifecycle,
        configuration=env.configuration,
        device=env.device,
        backends={},
        projections=cast(Any, None),
        file_policy_loader=None,
        generation=generation,
        limits=_limits(),
        clock=lambda: env.now,
        hooks=env.hooks,
        status_retention=retention,
    )
    child = _id()
    deadline = env.now + 500

    def select(
        request: svc.CameraCommandRequest, *, allow_stale_stop_run: bool = False
    ) -> CameraSelection:
        _ = request, allow_stale_stop_run
        return CameraSelection(
            cast(BackendPort, _FailingBackend()),
            1,
            pb.WorkContext(),
            camera_pb.CameraSessionSettings(),
            None,
        )

    def dispatch(
        request: Any,
        selection: Any,
        policy: Any,
        *,
        deadline_ns: int | None = None,
    ) -> CameraDispatch:
        _ = deadline_ns
        operator_id = request.command.operator.command_id
        env.device.camera_operation = CameraOperation(
            operator_id,
            child,
            1,
            camera_pb.CAMERA_ROLE_BEHAVIORAL,
            request.kind,
            pb.WorkContext(),
            deadline,
            False,
        )
        retention.reserve(env.device.camera_operation)
        env.ops.operation(operator_id, "ExecuteCameraCommand")
        return CameraDispatch(
            selection.backend, svc.AcquisitionCameraCommand(), child, deadline
        )

    camera._select_locked = select  # type: ignore[method-assign]
    camera._dispatch_locked = dispatch  # type: ignore[method-assign]
    request = svc.CameraCommandRequest(
        kind=svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER
    )
    request.command.operator.command_id = _id()
    result = await camera.execute_camera_command(request)

    operator_id = request.command.operator.command_id
    assert result.result == pb.COMMAND_RESULT_REJECTED
    operation = env.device.camera_operation
    assert operation is not None and operation.timed_out
    state = env.control.operations[operator_id]
    assert state.complete and not state.succeeded
    assert "unconfirmed" in state.progress
    assert len(env.spawned) == 1  # the same deadline handler as accepted commands
    assert env.device.camera_operation is operation  # held until the deadline
    env.now = deadline
    await env.spawned[0]
    # An expired, unconfirmed command can no longer be admitted: free the slot,
    # but keep manual effects admitted in case it was delivered.
    assert operation.admission_unconfirmed
    assert env.device.camera_operation is None
    assert camera.status_retention.find(operation.child_id) is operation
    assert env.device.camera_operation_changed.is_set()


def _display(env: _Env, loader: Any) -> DisplayInitialization:
    setting = pb.BackendSettings(backend_name="visual_stimulus", enabled=True)
    setting.visual_stimulus.display.profile_json = "{}"
    env.configuration.current.backends.append(setting)
    projections = type("P", (), {"expected_display": None})()
    projections.expect_display = lambda command_id, revision: setattr(  # type: ignore[attr-defined]
        projections, "expected_display", (command_id, revision)
    )
    env.projections = projections  # type: ignore[attr-defined]
    return DisplayInitialization(
        lifecycle=env.lifecycle,
        configuration=env.configuration,
        control=env.control,
        device=env.device,
        backends={
            "visual_stimulus": cast(
                BackendPort, type("B", (), {"context": pb.BackendContext()})()
            )
        },
        projections=cast(Any, projections),
        file_policy_loader=loader,
        display_validator=lambda profile: frozenset({"out"}),
        generation=_id(),
        limits=_limits(),
        max_operation_records=env.ops.max_operation_records,
        clock=lambda: env.now,
        hooks=env.hooks,
    )


def _policies() -> dict[str, Any]:
    policy = visual_stimulus_pb.VisualStimulusFilePolicies()
    policy.limits.max_document_bytes = 1
    return {"visual_stimulus": policy}


def _fill(env: _Env, count: int) -> None:
    for _ in range(count):
        env.ops.operation(_id(), "Filler", complete=False)


async def test_display_capacity_race_leaves_no_display_state_and_warns() -> None:
    env = _Env(max_records=5)

    def loader(names: frozenset[str]) -> dict[str, Any]:
        _fill(env, 3)  # capacity is consumed while validation runs
        return _policies()

    display = _display(env, loader)
    result = await display.initialize_display()
    assert result.result == pb.COMMAND_RESULT_REJECTED
    assert env.device.display_pending is None
    assert cast(Any, env.projections).expected_display is None
    assert any(w.component == "visual_stimulus_display" for w in env.control.warnings)


async def test_display_capacity_early_uses_ordinary_rule_and_warns() -> None:
    env = _Env(max_records=5)
    _fill(env, 3)
    display = _display(env, lambda names: _policies())
    result = await display.initialize_display()
    assert result.result == pb.COMMAND_RESULT_REJECTED
    assert env.device.display_pending is None
    assert any("capacity" in w.message for w in env.control.warnings)


async def test_display_initialization_still_dispatches_with_capacity() -> None:
    env = _Env(max_records=8)
    sent: list[Any] = []

    class Backend:
        context = pb.BackendContext()

        async def initialize_display(self, request: Any, *, deadline_ns: int) -> Any:
            sent.append(request)
            return pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED)

    display = _display(env, lambda names: _policies())
    display.backends = {"visual_stimulus": cast(BackendPort, Backend())}
    result = await display.initialize_display()
    assert result.result == pb.COMMAND_RESULT_ACCEPTED
    assert env.device.display_pending is not None
    assert len(sent) == 1
    for task in env.spawned:
        task.close()
    assert asyncio.get_running_loop() is not None


async def test_display_calibration_open_adopts_a_profile_before_display_initialization(
    tmp_path: Any,
) -> None:
    env = _Env()
    asset_root = tmp_path / "assets"
    asset_root.mkdir()
    profile_json = valid_display_json()
    profile = asset_root / "calibration" / "diagnostic_display_profile.json"
    profile.parent.mkdir()
    profile.write_text(profile_json)
    arena = asset_root / "calibration" / "arena.glb"
    arena.write_bytes(b"protected arena")
    accepted = pb.ExperimentConfiguration(asset_root=str(asset_root))
    setting = pb.BackendSettings(backend_name="visual_stimulus", enabled=True)
    setting.visual_stimulus.display.profile_json = '{"saved": "different"}'
    accepted.backends.append(setting)
    env.configuration.current.CopyFrom(accepted)
    policy = visual_stimulus_pb.VisualStimulusFilePolicies(contract_version=1)
    policy.limits.max_document_bytes = 1_000_000
    policy.limits.max_asset_cpu_bytes = 1_000_000
    policy.limits.max_asset_gpu_bytes = 1_000_000
    output_ids = frozenset({"projector/main"})
    sent: list[Any] = []
    projections = type("Projection", (), {"display": None})()
    projections.expect_display = lambda command_id, revision: None  # type: ignore[attr-defined]

    class Backend:
        context = pb.BackendContext(
            backend_name="visual_stimulus", backend_generation=_id()
        )

        async def open_display_calibration(self, request: Any, *, deadline_ns: int):
            sent.append(request)
            return pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED)

    controller = DisplayCalibrationController(
        lifecycle=env.lifecycle,
        configuration=env.configuration,
        control=env.control,
        device=env.device,
        backends={"visual_stimulus": cast(BackendPort, Backend())},
        projections=cast(Any, projections),
        file_policy_loader=lambda names: {"visual_stimulus": policy},
        display_validator=lambda document: output_ids,
        display_pacing_resolver=None,
        generation=_id(),
        limits=_limits(),
        hooks=env.hooks,
        maximum_asset_bytes=1_000_000,
        clock=lambda: env.now,
    )
    request = svc.OpenDisplayCalibrationRequest(
        expected_configuration_revision=env.configuration.revision,
        diagnostic_id=str(uuid4()),
        profile_asset_reference="calibration/diagnostic_display_profile.json",
        arena_asset_reference="calibration/arena.glb",
        expected_profile_sha256=hashlib.sha256(profile_json.encode()).hexdigest(),
        expected_arena_sha256=hashlib.sha256(arena.read_bytes()).hexdigest(),
    )
    request.command.operator.command_id = _id()
    result = await controller.open(request)

    assert result.result == pb.COMMAND_RESULT_ACCEPTED
    assert sent[0].profile_json != setting.visual_stimulus.display.profile_json
    assert sent[0].policies.limits.max_asset_cpu_bytes == 1_000_000
    assert sent[0].arena_size_bytes == len(b"protected arena")
    assert env.device.calibration_blocked
    for task in env.spawned:
        task.close()


async def test_display_calibration_validation_reserves_and_rechecks_authority(
    tmp_path: Any,
) -> None:
    env = _Env()
    asset_root = tmp_path / "assets"
    (asset_root / "calibration").mkdir(parents=True)
    profile_json = valid_display_json()
    profile_path = asset_root / "calibration/profile.json"
    profile_path.write_text(profile_json)
    arena_path = asset_root / "calibration/arena.glb"
    arena_path.write_bytes(b"arena")
    setting = pb.BackendSettings(backend_name="visual_stimulus", enabled=True)
    setting.visual_stimulus.display.profile_json = profile_json
    env.configuration.current.asset_root = str(asset_root)
    env.configuration.current.backends.append(setting)
    policy = visual_stimulus_pb.VisualStimulusFilePolicies(contract_version=1)
    policy.limits.max_document_bytes = 1_000_000
    policy.limits.max_asset_cpu_bytes = 1_000_000
    policy.limits.max_asset_gpu_bytes = 1_000_000
    entered = threading.Event()
    release = threading.Event()
    sent: list[Any] = []

    def loader(names: frozenset[str]) -> dict[str, Any]:
        entered.set()
        release.wait(timeout=2)
        return {"visual_stimulus": policy}

    class Backend:
        context = pb.BackendContext(
            backend_name="visual_stimulus", backend_generation=_id()
        )

        async def open_display_calibration(self, request: Any, *, deadline_ns: int):
            sent.append(request)
            return pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED)

    backend = Backend()
    projections = type("Projection", (), {"display": None})()
    projections.expect_display = lambda command_id, revision: None  # type: ignore[attr-defined]
    controller = DisplayCalibrationController(
        lifecycle=env.lifecycle,
        configuration=env.configuration,
        control=env.control,
        device=env.device,
        backends={"visual_stimulus": cast(BackendPort, backend)},
        projections=cast(Any, projections),
        file_policy_loader=loader,
        display_validator=lambda _: frozenset({"projector/main"}),
        display_pacing_resolver=None,
        generation=_id(),
        limits=_limits(),
        hooks=env.hooks,
        maximum_asset_bytes=1_000_000,
        clock=lambda: env.now,
    )

    def request() -> svc.OpenDisplayCalibrationRequest:
        value = svc.OpenDisplayCalibrationRequest(
            expected_configuration_revision=env.configuration.revision,
            diagnostic_id=str(uuid4()),
            profile_asset_reference="calibration/profile.json",
            arena_asset_reference="calibration/arena.glb",
            expected_profile_sha256=hashlib.sha256(profile_json.encode()).hexdigest(),
            expected_arena_sha256=hashlib.sha256(arena_path.read_bytes()).hexdigest(),
        )
        value.command.operator.command_id = _id()
        return value

    first = request()
    task = asyncio.create_task(controller.open(first))
    assert await asyncio.to_thread(entered.wait, 1)
    second = request()
    rejected = await controller.open(second)
    assert rejected.result == pb.COMMAND_RESULT_REJECTED
    env.lifecycle.authority_lost = True
    release.set()
    result = await task

    assert result.result == pb.COMMAND_RESULT_REJECTED
    assert "authority" in result.failure.message
    assert not sent
    assert env.device.calibration_pending is None
    assert not env.device.calibration_blocked

    env.lifecycle.authority_lost = False
    entered.clear()
    release.clear()
    cancelled_open = request()
    cancelled_task = asyncio.create_task(controller.open(cancelled_open))
    assert await asyncio.to_thread(entered.wait, 1)
    cancelled_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_task
    release.set()
    await asyncio.sleep(0)
    assert not sent
    assert env.device.calibration_pending is None
    assert not env.device.calibration_blocked
    await controller.owner_lost()
    assert not sent


@pytest.mark.parametrize("loss_path", ["release", "watch"])
@pytest.mark.parametrize("uncertain_open", [False, True])
async def test_assembled_owner_loss_closes_exact_display_calibration(
    tmp_path: Path, loss_path: str, uncertain_open: bool
) -> None:
    renderer_generation = _id()
    backend_context = pb.BackendContext(
        backend_name="visual_stimulus", backend_generation=_id()
    )
    runtime = _runtime(tmp_path, backend_context)
    diagnostic_id = _id()
    revision = runtime.configuration_state.revision
    output_ids = frozenset({"projector/main"})
    closes: list[Any] = []
    report_errors: list[str] = []
    report_receipts: list[pb.ReportReceipt] = []

    class Backend:
        context = backend_context

        async def close_display_calibration(self, request: Any, *, deadline_ns: int):
            closes.append((request, deadline_ns))
            report = pb.VisualStimulusDisplayView(
                source=pb.ProcessIdentity(
                    role="visual_stimulus",
                    generation=backend_context.backend_generation,
                ),
                backend=backend_context,
                controller=pb.ProcessIdentity(
                    role="controller", generation=runtime.generation
                ),
                command_id=request.command_id,
                requested_revision=request.configuration_revision,
                applied_revision=request.configuration_revision,
                observed_monotonic_ns=runtime.clock(),
                complete=True,
            )
            report.outputs.add(output_id="projector/main")
            report.calibration.CopyFrom(
                visual_stimulus_pb.DisplayCalibrationEvidence(
                    diagnostic_id=diagnostic_id,
                    controller_generation=runtime.generation,
                    renderer_generation=renderer_generation,
                    configuration_revision=revision,
                    state=visual_stimulus_pb.DISPLAY_CALIBRATION_STATE_IDLE,
                    observed_monotonic_ns=runtime.clock(),
                    presented=False,
                    idle=True,
                    resources_closed=True,
                )
            )
            try:
                report_receipts.append(
                    await runtime.report_projection("display", report)
                )
            except Exception as exc:
                report_errors.append(str(exc))
                raise
            return pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED)

    backend = Backend()
    runtime.display_calibration.backends["visual_stimulus"] = cast(BackendPort, backend)
    calibration = runtime.display_calibration
    calibration._active_backend = cast(BackendPort, backend)
    calibration._active_backend_context = pb.BackendContext.FromString(
        backend_context.SerializeToString()
    )
    runtime.device_state.calibration_blocked = True
    if uncertain_open:
        runtime.device_state.calibration_pending = (
            _id(),
            revision,
            runtime.clock() + runtime.limits.recovery_ns,
            diagnostic_id,
            visual_stimulus_pb.DISPLAY_CALIBRATION_STATE_ACTIVE,
            output_ids,
        )
    else:
        display = pb.VisualStimulusDisplayView(
            source=pb.ProcessIdentity(
                role="visual_stimulus", generation=backend_context.backend_generation
            ),
            backend=backend_context,
            controller=pb.ProcessIdentity(
                role="controller", generation=runtime.generation
            ),
        )
        display.outputs.add(output_id="projector/main")
        display.calibration.CopyFrom(
            visual_stimulus_pb.DisplayCalibrationEvidence(
                diagnostic_id=diagnostic_id,
                controller_generation=runtime.generation,
                renderer_generation=renderer_generation,
                configuration_revision=revision,
                state=visual_stimulus_pb.DISPLAY_CALIBRATION_STATE_ACTIVE,
                observed_monotonic_ns=runtime.clock(),
                presented=True,
                idle=False,
                resources_closed=False,
            )
        )
        runtime.projections.display = display

    client_id, watch_id, control_generation = _id(), _id(), _id()
    watch = Watch(
        client_id, watch_id, asyncio.Queue(maxsize=1), runtime.control.revision
    )
    runtime.control.watches[(client_id, watch_id)] = watch
    runtime.control.owner = (client_id, watch_id, control_generation)
    if loss_path == "release":
        command = svc.OperatorCommand(
            controller_generation=runtime.generation,
        )
        command.operator.client_id = client_id
        command.operator.control_generation = control_generation
        command.operator.command_id = _id()
        await runtime.release_control(command)
    else:
        await runtime.close_watch(watch)

    assert len(closes) == 1
    close_request, close_deadline = closes[0]
    assert close_request.diagnostic_id == diagnostic_id
    assert close_request.configuration_revision == revision
    assert close_deadline > runtime.clock()
    assert not report_errors, report_errors
    assert report_receipts[0].result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime.device_state.calibration_pending is None
    assert not runtime.device_state.calibration_blocked
    assert runtime.projections.display.calibration.resources_closed


async def test_owner_loss_dispatches_exact_close_while_open_receipt_is_pending(
    tmp_path: Path,
) -> None:
    env = _Env()
    asset_root = tmp_path / "assets"
    (asset_root / "calibration").mkdir(parents=True)
    profile_json = valid_display_json()
    profile_path = asset_root / "calibration/profile.json"
    profile_path.write_text(profile_json)
    arena_path = asset_root / "calibration/arena.glb"
    arena_path.write_bytes(b"arena")
    env.configuration.current.asset_root = str(asset_root)
    setting = pb.BackendSettings(backend_name="visual_stimulus", enabled=True)
    setting.visual_stimulus.display.profile_json = profile_json
    env.configuration.current.backends.append(setting)
    policy = visual_stimulus_pb.VisualStimulusFilePolicies(contract_version=1)
    policy.limits.max_document_bytes = 1_000_000
    policy.limits.max_asset_cpu_bytes = 1_000_000
    policy.limits.max_asset_gpu_bytes = 1_000_000
    entered_open = asyncio.Event()
    release_open = asyncio.Event()
    open_requests: list[Any] = []
    close_requests: list[Any] = []

    class Projections:
        display = None

        def expect_display(self, command_id: str, revision: int) -> None:
            pass

    projections = Projections()

    class Backend:
        context = pb.BackendContext(
            backend_name="visual_stimulus", backend_generation=_id()
        )

        async def open_display_calibration(self, request: Any, *, deadline_ns: int):
            open_requests.append((request, deadline_ns))
            entered_open.set()
            await release_open.wait()
            return pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED)

        async def close_display_calibration(self, request: Any, *, deadline_ns: int):
            close_requests.append((request, deadline_ns))
            report = pb.VisualStimulusDisplayView(
                source=pb.ProcessIdentity(
                    role="visual_stimulus", generation=self.context.backend_generation
                ),
                backend=self.context,
                controller=pb.ProcessIdentity(
                    role="controller", generation=controller.generation
                ),
                command_id=request.command_id,
                requested_revision=request.configuration_revision,
                applied_revision=request.configuration_revision,
                observed_monotonic_ns=env.now,
                complete=True,
            )
            report.outputs.add(output_id="projector/main")
            report.calibration.CopyFrom(
                visual_stimulus_pb.DisplayCalibrationEvidence(
                    diagnostic_id=request.diagnostic_id,
                    controller_generation=controller.generation,
                    renderer_generation="renderer-generation",
                    configuration_revision=request.configuration_revision,
                    state=visual_stimulus_pb.DISPLAY_CALIBRATION_STATE_IDLE,
                    observed_monotonic_ns=env.now,
                    presented=False,
                    idle=True,
                    resources_closed=True,
                )
            )
            projections.display = report
            controller.device.calibration_pending = None
            controller.device.calibration_blocked = False
            return pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED)

    backend = Backend()
    controller = DisplayCalibrationController(
        lifecycle=env.lifecycle,
        configuration=env.configuration,
        control=env.control,
        device=env.device,
        backends={"visual_stimulus": cast(BackendPort, backend)},
        projections=cast(Any, projections),
        file_policy_loader=lambda _names: {"visual_stimulus": policy},
        display_validator=lambda _document: frozenset({"projector/main"}),
        display_pacing_resolver=None,
        generation=_id(),
        limits=_limits(),
        hooks=env.hooks,
        maximum_asset_bytes=1_000_000,
        clock=lambda: env.now,
    )
    diagnostic_id = str(uuid4())
    request = svc.OpenDisplayCalibrationRequest(
        expected_configuration_revision=env.configuration.revision,
        diagnostic_id=diagnostic_id,
        profile_asset_reference="calibration/profile.json",
        arena_asset_reference="calibration/arena.glb",
        expected_profile_sha256=hashlib.sha256(profile_json.encode()).hexdigest(),
        expected_arena_sha256=hashlib.sha256(arena_path.read_bytes()).hexdigest(),
    )
    request.command.operator.command_id = _id()
    opening = asyncio.create_task(controller.open(request))
    try:
        assert await asyncio.wait_for(entered_open.wait(), 1)
        await controller.owner_lost()
        assert len(close_requests) == 1
        assert close_requests[0][0].diagnostic_id == diagnostic_id
        assert not release_open.is_set()
        assert controller.device.calibration_pending is None
        assert not controller.device.calibration_blocked
    finally:
        release_open.set()
    assert (await opening).result == pb.COMMAND_RESULT_ACCEPTED
    for task in env.spawned:
        task.close()


@pytest.mark.parametrize("blocked", ["", "camera", "diagnostic", "phase", "digest"])
async def test_controller_authorizes_firmware_only_in_idle_configuration(blocked):
    from cephvr.controller.device.microcontroller import MicrocontrollerCommands

    env = _Env()
    env.lifecycle.session.phase = (
        pb.SESSION_PHASE_SETTING_UP
        if blocked == "phase"
        else pb.SESSION_PHASE_CONFIGURATION
    )
    settings = env.configuration.current.backends.add(
        backend_name="acquisition"
    ).acquisition
    settings.pulses.port = "COM8"
    views = pb.AcquisitionDeviceViews()
    views.behavioral.device_open = blocked == "camera"
    views.diagnostic.active = blocked == "diagnostic"
    commands = []

    from types import SimpleNamespace

    class LocalOwner:
        acquisition_claimed = False
        view = pb.MicrocontrollerDeviceView()
        firmware = SimpleNamespace(busy=False)

        def ensure_idle(self):
            pass

        async def execute(self, request, pulses, deadline_ns):
            commands.append((request, pulses))
            assert deadline_ns == env.device.camera_operation.deadline_ns

    local = LocalOwner()
    local.view.diagnostic.active = blocked == "diagnostic"
    owner = MicrocontrollerCommands(
        lifecycle=env.lifecycle,
        configuration=env.configuration,
        device=env.device,
        owner=local,
        limits=_limits(),
        clock=lambda: env.now,
        hooks=env.hooks,
        device_views=lambda: views,
    )
    request = svc.MicrocontrollerCommandRequest(
        expected_configuration_revision=env.configuration.revision,
        kind=svc.MICROCONTROLLER_COMMAND_KIND_UPLOAD_FIRMWARE,
        firmware_path=r"C:\firmware\uno.hex",
        firmware_sha256="" if blocked == "digest" else "a" * 64,
    )
    request.command.operator.command_id = _id()
    try:
        result = await owner.execute(request)
        assert (result.result == pb.COMMAND_RESULT_ACCEPTED) == (not blocked)
        if not blocked:
            for coroutine in env.spawned:
                await coroutine
            env.spawned.clear()
            assert commands[0][0].firmware_path == request.firmware_path
            assert commands[0][0].firmware_sha256 == request.firmware_sha256
            assert (
                commands[0][0].command.operator.command_id
                == request.command.operator.command_id
            )
            assert commands[0][1].port == "COM8"
            assert env.device.camera_operation is None
            assert env.control.operations[request.command.operator.command_id].succeeded
        else:
            assert not commands and env.device.camera_operation is None
    finally:
        for coroutine in env.spawned:
            coroutine.close()
