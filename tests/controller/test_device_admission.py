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
from cephvr.controller.projections import ProjectionStore
from cephvr.controller.state import (
    CameraOperation,
    ConfigurationState,
    ControlState,
    DeviceState,
    LifecycleState,
    LimitsState,
    PendingCalibration,
    Watch,
)
from cephvr.shared.commands import CommandLedger
from cephvr.visual_stimulus.configuration import load_file_policies
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


@pytest.mark.parametrize("staged_matches", [True, False])
async def test_display_calibration_open_adopts_a_profile_before_display_initialization(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    staged_matches: bool,
) -> None:
    env = _Env()
    asset_root = tmp_path / "assets"
    runtime_root = tmp_path / "runtime"
    (runtime_root / "calibration").mkdir(parents=True)
    monkeypatch.setattr(
        "cephvr.controller.device.display_calibration.calibration_runtime_root",
        lambda _view: runtime_root,
    )
    monkeypatch.setattr(
        "cephvr.controller.device.display_calibration.calibration_asset_root",
        lambda: asset_root,
    )
    asset_root.mkdir()
    profile_json = valid_display_json()
    (asset_root / "calibration").mkdir()
    profile = runtime_root / "calibration" / "diagnostic_display_profile.json"
    profile.write_text(profile_json)
    arena = asset_root / "calibration" / "frame_grid.glb"
    arena.write_bytes(b"protected arena")
    (runtime_root / "calibration/frame_grid.glb").write_bytes(
        b"protected arena" if staged_matches else b"stale copy"
    )
    accepted = pb.ExperimentConfiguration(asset_root=str(tmp_path / "external-media"))
    setting = pb.BackendSettings(backend_name="visual_stimulus", enabled=True)
    setting.visual_stimulus.display.profile_json = '{"saved": "different"}'
    accepted.backends.append(setting)
    env.configuration.current.CopyFrom(accepted)
    policy = visual_stimulus_pb.VisualStimulusFilePolicies(contract_version=1)
    policy.projection.CopyFrom(
        load_file_policies(Path(__file__).resolve().parents[2]).projection
    )
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
        arena_asset_reference="calibration/frame_grid.glb",
        expected_profile_sha256=hashlib.sha256(profile_json.encode()).hexdigest(),
        expected_arena_sha256=hashlib.sha256(arena.read_bytes()).hexdigest(),
    )
    request.command.operator.command_id = _id()
    result = await controller.open(request)

    if not staged_matches:
        assert result.result == pb.COMMAND_RESULT_REJECTED
        assert "digest differs" in result.failure.message
        assert not sent and env.device.calibration_pending is None
        return

    assert result.result == pb.COMMAND_RESULT_ACCEPTED
    assert sent[0].profile_json != setting.visual_stimulus.display.profile_json
    assert sent[0].policies.limits.max_asset_cpu_bytes == 1_000_000
    assert sent[0].arena_size_bytes == len(b"protected arena")
    assert sent[0].asset_root == str(runtime_root)
    assert env.device.calibration_blocked
    for task in env.spawned:
        task.close()


async def test_display_calibration_validation_reserves_and_rechecks_authority(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = _Env()
    asset_root = tmp_path / "assets"
    monkeypatch.setattr(
        "cephvr.controller.device.display_calibration.calibration_runtime_root",
        lambda _view: asset_root,
    )
    monkeypatch.setattr(
        "cephvr.controller.device.display_calibration.calibration_asset_root",
        lambda: asset_root,
    )
    (asset_root / "calibration").mkdir(parents=True)
    profile_json = valid_display_json()
    profile_path = asset_root / "calibration/profile.json"
    profile_path.write_text(profile_json)
    arena_path = asset_root / "calibration/frame_grid.glb"
    arena_path.write_bytes(b"arena")
    setting = pb.BackendSettings(backend_name="visual_stimulus", enabled=True)
    setting.visual_stimulus.display.profile_json = profile_json
    env.configuration.current.ClearField("asset_root")
    env.configuration.current.backends.append(setting)
    policy = visual_stimulus_pb.VisualStimulusFilePolicies(contract_version=1)
    policy.projection.CopyFrom(
        load_file_policies(Path(__file__).resolve().parents[2]).projection
    )
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
            arena_asset_reference="calibration/frame_grid.glb",
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
        runtime.device_state.calibration_pending = PendingCalibration(
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = _Env()
    asset_root = tmp_path / "assets"
    monkeypatch.setattr(
        "cephvr.controller.device.display_calibration.calibration_runtime_root",
        lambda _view: asset_root,
    )
    monkeypatch.setattr(
        "cephvr.controller.device.display_calibration.calibration_asset_root",
        lambda: asset_root,
    )
    (asset_root / "calibration").mkdir(parents=True)
    profile_json = valid_display_json()
    profile_path = asset_root / "calibration/profile.json"
    profile_path.write_text(profile_json)
    arena_path = asset_root / "calibration/frame_grid.glb"
    arena_path.write_bytes(b"arena")
    env.configuration.current.ClearField("asset_root")
    setting = pb.BackendSettings(backend_name="visual_stimulus", enabled=True)
    setting.visual_stimulus.display.profile_json = profile_json
    env.configuration.current.backends.append(setting)
    policy = visual_stimulus_pb.VisualStimulusFilePolicies(contract_version=1)
    policy.projection.CopyFrom(
        load_file_policies(Path(__file__).resolve().parents[2]).projection
    )
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
        arena_asset_reference="calibration/frame_grid.glb",
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


async def test_failed_calibration_close_expires_so_the_exact_close_can_be_retried(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    from tests.controller.support_components import _runtime

    ctx = pb.BackendContext(backend_name="visual_stimulus", backend_generation=_id())
    runtime = _runtime(tmp_path, ctx)
    calls: list[Any] = []

    class Renderer:
        context = ctx

        async def close_display_calibration(self, request: Any, *, deadline_ns: int):
            calls.append(request)
            if len(calls) == 1:
                raise ConnectionError("renderer hung")
            return pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED)

    calibration = runtime.display_calibration
    calibration.hooks = replace(calibration.hooks, authorized=lambda *a, **k: "")
    renderer = Renderer()
    calibration.backends["visual_stimulus"] = cast(BackendPort, renderer)
    calibration._active_backend = cast(BackendPort, renderer)
    calibration._active_backend_context = pb.BackendContext.FromString(
        ctx.SerializeToString()
    )
    diagnostic_id = _id()
    display = pb.VisualStimulusDisplayView(backend=ctx)
    display.outputs.add(output_id="projector/main")
    display.calibration.CopyFrom(
        visual_stimulus_pb.DisplayCalibrationEvidence(
            diagnostic_id=diagnostic_id,
            controller_generation=runtime.generation,
            configuration_revision=runtime.configuration_state.revision,
            state=visual_stimulus_pb.DISPLAY_CALIBRATION_STATE_ACTIVE,
            presented=True,
            idle=False,
            resources_closed=False,
        )
    )
    runtime.projections.display = display
    runtime.device_state.calibration_blocked = True

    def close_request() -> svc.CloseDisplayCalibrationRequest:
        request = svc.CloseDisplayCalibrationRequest(
            expected_configuration_revision=runtime.configuration_state.revision,
            diagnostic_id=diagnostic_id,
        )
        request.command.operator.command_id = _id()
        return request

    first = await calibration.close(close_request())
    assert first.result == pb.COMMAND_RESULT_REJECTED
    assert runtime.device_state.calibration_pending is not None
    for _ in range(300):  # the recovery bound retires the unconfirmed Close
        if runtime.device_state.calibration_pending is None:
            break
        await asyncio.sleep(0.01)
    assert runtime.device_state.calibration_pending is None
    assert runtime.device_state.calibration_blocked  # evidence still unconfirmed
    retry = await calibration.close(close_request())
    assert retry.result == pb.COMMAND_RESULT_ACCEPTED
    assert len(calls) == 2


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

        async def execute(self, request, pulses, deadline_ns, *, progress):
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


@pytest.mark.parametrize(
    "calibration_view", ["frame_grid", "photodiode_placement", "blackout_placement"]
)
@pytest.mark.asyncio
@pytest.mark.parametrize("first_reply", ["accepted", "rejected", "unknown"])
async def test_live_calibration_update_requires_exact_leased_active_grid(
    calibration_view,
    first_reply,
):
    from cephvr.visual_stimulus.v1 import messages_pb2 as messages

    env = _Env()
    sent = []

    class Backend:
        context = pb.BackendContext(
            backend_name="visual_stimulus", backend_generation=_id()
        )

        async def update_display_calibration(self, request, *, deadline_ns):
            sent.append(request)
            assert request.deadline_monotonic_ns == deadline_ns
            if len(sent) == 1 and first_reply == "unknown":
                raise ConnectionError("renderer reply lost")
            if len(sent) == 1 and first_reply == "rejected":
                return pb.CommandAdmission(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(message="invalid live adjustment"),
                )
            return pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED)

    backend = Backend()
    display = pb.VisualStimulusDisplayView(backend=backend.context)
    display.outputs.add(output_id="projector/main")
    generation = _id()
    evidence = display.calibration
    evidence.diagnostic_id = _id()
    evidence.configuration_revision = env.configuration.revision
    evidence.controller_generation = generation
    evidence.calibration_view = calibration_view
    evidence.state = visual_stimulus_pb.DISPLAY_CALIBRATION_STATE_ACTIVE
    projections = ProjectionStore(
        generation,
        {"visual_stimulus": backend.context},
        max_entries=8,
        max_payload_bytes=1_000_000,
    )
    projections.display = display
    controller = DisplayCalibrationController(
        lifecycle=env.lifecycle,
        configuration=env.configuration,
        control=env.control,
        device=env.device,
        backends={"visual_stimulus": cast(BackendPort, backend)},
        projections=cast(Any, projections),
        file_policy_loader=lambda _: {},
        display_validator=lambda _: frozenset(),
        display_pacing_resolver=None,
        generation=generation,
        limits=_limits(),
        hooks=env.hooks,
        maximum_asset_bytes=1_000_000,
        clock=lambda: env.now,
    )
    controller._active_backend = cast(BackendPort, backend)
    request = svc.UpdateDisplayCalibrationRequest(
        expected_configuration_revision=env.configuration.revision,
        diagnostic_id=evidence.diagnostic_id,
        adjustment_sequence=1,
    )
    request.command.operator.command_id = _id()
    request.adjustments.append(
        messages.DisplayCalibrationAdjustment(
            mapping_id="diagnostic_front",
            destination_xy=[0.1, 0.1, 0.9, 0.1, 0.1, 0.9, 0.9, 0.9],
        )
    )
    import json

    placement_json = json.dumps(
        dict(
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
    )
    if calibration_view != "frame_grid":
        request.ClearField("adjustments")
        request.placement_json = placement_json
    request.diagnostic_id = _id()
    assert (await controller.update(request)).result == pb.COMMAND_RESULT_REJECTED
    request.diagnostic_id = evidence.diagnostic_id
    if calibration_view == "frame_grid":
        request.adjustments[0].destination_xy[0] = float("nan")
    else:
        request.placement_json = "{}"
    assert (await controller.update(request)).result == pb.COMMAND_RESULT_REJECTED
    assert not sent and env.device.calibration_pending is None
    if calibration_view == "frame_grid":
        request.adjustments[0].destination_xy[0] = 0.1
    else:
        request.placement_json = placement_json
    if first_reply != "accepted":
        assert (await controller.update(request)).result == pb.COMMAND_RESULT_REJECTED
        assert env.device.calibration_blocked
        assert evidence.state == visual_stimulus_pb.DISPLAY_CALIBRATION_STATE_ACTIVE
        assert evidence.adjustment_sequence == 0
        assert (env.device.calibration_pending is None) == (first_reply == "rejected")
        request.command.operator.command_id = _id()
        retry = await controller.update(request)
        assert (retry.result == pb.COMMAND_RESULT_ACCEPTED) == (
            first_reply == "rejected"
        )
        assert len(sent) == (2 if first_reply == "rejected" else 1)
        for task in env.spawned:
            task.close()
        return
    assert (await controller.update(request)).result == pb.COMMAND_RESULT_ACCEPTED
    assert sent[0].diagnostic_id == evidence.diagnostic_id
    assert sent[0].adjustment_sequence == 1
    assert sent[0].placement_json == request.placement_json
    assert (
        env.device.calibration_pending.expected_state
        == visual_stimulus_pb.DISPLAY_CALIBRATION_STATE_ACTIVE
    )
    assert evidence.adjustment_sequence == 0  # Admission is not presentation.
    assert (await controller.update(request)).result == pb.COMMAND_RESULT_REJECTED
    env.device.calibration_pending = None
    evidence.adjustment_sequence = 1
    assert (await controller.update(request)).result == pb.COMMAND_RESULT_REJECTED
    request.adjustment_sequence = 2
    evidence.calibration_view = "reference_bars"
    assert (await controller.update(request)).result == pb.COMMAND_RESULT_REJECTED
    evidence.calibration_view = calibration_view
    env.lifecycle.session.shutdown_requested = True
    request.command.operator.command_id = _id()
    assert (await controller.update(request)).result == pb.COMMAND_RESULT_REJECTED
    assert len(sent) == 1 and env.device.calibration_pending is None
    env.lifecycle.session.shutdown_requested = False
    from dataclasses import replace

    controller.hooks = replace(
        env.hooks, authorized=lambda *_args, **_kwargs: "lease lost"
    )
    assert (await controller.update(request)).result == pb.COMMAND_RESULT_REJECTED
    for task in env.spawned:
        task.close()


def test_startup_display_resolves_only_file_projection_values():
    import json

    from cephvr.controller.startup.providers import _installed_display_pacing_resolver
    from cephvr.shared.config import ConfigurationError

    policy = load_file_policies(Path(__file__).resolve().parents[2])
    resolver = _installed_display_pacing_resolver()
    assert resolver is not None
    source = json.loads(valid_display_json())
    source["geometry"].update(near_mm=5000, far_mm=1, orthogonality_tolerance=2)
    resolved = json.loads(resolver(json.dumps(source), policy))
    assert resolved["geometry"]["near_mm"] == 1
    assert resolved["geometry"]["far_mm"] == 250
    assert resolved["geometry"]["surfaces"] == source["geometry"]["surfaces"]
    policy.ClearField("projection")
    with pytest.raises(ConfigurationError, match="projection.near_mm"):
        resolver(json.dumps(source), policy)


@pytest.mark.parametrize("pending", ["display_pending", "calibration_pending"])
async def test_display_initialize_rechecks_pending_ownership_after_policy_load(pending):
    env = _Env()
    entered, release = threading.Event(), threading.Event()

    def loader(names):
        entered.set()
        assert release.wait(2)
        return _policies()

    display = _display(env, loader)
    task = asyncio.create_task(display.initialize_display())
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        setattr(env.device, pending, ("another",))
        release.set()
        result = await task
        assert result.result == pb.COMMAND_RESULT_REJECTED
        assert not env.control.operations
        assert getattr(env.device, pending) == ("another",)
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        for spawned in env.spawned:
            spawned.close()


@pytest.mark.parametrize("blocker", ["phase", "manual_cleanup", "startup"])
async def test_camera_policy_load_rechecks_lifecycle_before_dispatch(
    tmp_path, monkeypatch, blocker
):
    from cephvr.acquisition.config.file_policies import (
        load_file_policies as acquisition_policies,
    )

    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _runtime(tmp_path, backend)
    from dataclasses import replace

    runtime.camera.hooks = replace(runtime.camera.hooks, authorized=lambda *a, **k: "")
    settings = runtime.configuration_state.current.backends.add(
        backend_name="acquisition", enabled=True
    )
    settings.acquisition.behavioral.device.device_id = "assigned"
    entered, release = threading.Event(), threading.Event()

    def loader(names):
        entered.set()
        assert release.wait(2)
        return {
            "acquisition": acquisition_policies(Path(__file__).resolve().parents[2])
        }

    runtime.camera.file_policy_loader = loader
    request = svc.CameraCommandRequest(
        camera=camera_pb.CAMERA_ROLE_BEHAVIORAL,
        kind=svc.CAMERA_COMMAND_KIND_TEST_CONNECTION,
        expected_configuration_revision=1,
    )
    request.command.operator.command_id = _id()
    task = asyncio.create_task(runtime.camera.execute_camera_command(request))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        if blocker == "phase":
            runtime.lifecycle.session.phase = pb.SESSION_PHASE_SETTING_UP
        elif blocker == "manual_cleanup":
            runtime.lifecycle.manual_control_cleanup_pending = True
        else:
            runtime.lifecycle.startup_blocker = "recovery required"
        release.set()
        result = await task
        assert result.result == pb.COMMAND_RESULT_REJECTED
        assert runtime.device_state.camera_operation is None
        assert not runtime.control.operations
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("wrong_completion", [False, True])
async def test_stimulus_preview_scope_completion_and_out_of_order_status(
    wrong_completion,
):
    from cephvr.controller.device.stimulus_preview import StimulusPreviewController

    env = _Env()
    env.lifecycle.session.phase = pb.SESSION_PHASE_RUNNING
    env.lifecycle.session.context.session_id = _id()

    class Backend:
        context = pb.BackendContext(
            backend_name="visual_stimulus", backend_generation=_id()
        )

        async def set_stimulus_preview(self, request, *, deadline_ns):
            self.request = request
            return pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED)

        async def get_retained_result(self, query, *, deadline_ns):
            from types import SimpleNamespace

            return SimpleNamespace(
                found=True,
                backend=self.context,
                operation=pb.OperationState(
                    context=pb.OperationContext(
                        command_id=_id() if wrong_completion else query.command_id
                    ),
                    command="SetStimulusPreview",
                    work=query.query.work,
                    complete=True,
                    succeeded=True,
                ),
            )

    backend = Backend()
    preview = StimulusPreviewController(
        env.lifecycle,
        env.configuration,
        {"visual_stimulus": backend},
        _id(),
        _limits(),
        lambda: env.now,
        env.hooks,
    )
    report = pb.StimulusPreviewState(
        source=pb.ProcessIdentity(role="visual_stimulus_renderer", generation=_id()),
        backend=backend.context,
        session=env.lifecycle.session.context,
        configuration_revision=env.configuration.revision,
        revision=2,
        available=True,
        visible=True,
    )
    assert (await preview.report(report)).result == pb.COMMAND_RESULT_ACCEPTED
    older = pb.StimulusPreviewState.FromString(report.SerializeToString())
    older.revision = 1
    older.visible = False
    assert (await preview.report(older)).result == pb.COMMAND_RESULT_ACCEPTED
    assert preview.view.visible
    older.session.session_id = _id()
    assert (await preview.report(older)).result == pb.COMMAND_RESULT_REJECTED
    request = svc.SetStimulusPreviewRequest(
        expected_configuration_revision=env.configuration.revision, visible=False
    )
    request.command.operator.command_id = _id()
    assert (await preview.execute(request)).result == pb.COMMAND_RESULT_ACCEPTED
    assert preview.pending
    await env.spawned.pop()
    operation = env.control.operations[request.command.operator.command_id]
    assert operation.complete and operation.succeeded == (not wrong_completion)
    assert (
        not preview.pending and env.lifecycle.session.phase == pb.SESSION_PHASE_RUNNING
    )
    request.command.operator.command_id = _id()
    request.expected_configuration_revision += 1
    assert (await preview.execute(request)).result == pb.COMMAND_RESULT_REJECTED
