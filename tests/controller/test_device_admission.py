"""Camera and display admission under deadline and capacity pressure."""

from __future__ import annotations

import asyncio
from typing import Any, cast
from uuid import uuid4

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
from cephvr.controller.device.ports import DeviceHooks
from cephvr.controller.ports import BackendPort
from cephvr.controller.state import (
    CameraOperation,
    ConfigurationState,
    ControllerLimits,
    ControlState,
    DeviceState,
    LifecycleState,
    LimitsState,
)
from cephvr.vr.v1 import runtime_pb2 as vr_pb


def _id() -> str:
    return str(uuid4())


def _limits() -> LimitsState:
    return LimitsState(
        ControllerLimits(
            setup_ns=1_000_000_000,
            setup_cancel_ns=1_000_000_000,
            ready_ns=1_000_000_000,
            finished_ns=1_000_000_000,
            registration_ns=1_000_000_000,
            recovery_ns=1_000_000_000,
            metadata_ns=1_000_000_000,
            validation_ns=1_000_000_000,
            lead_ns=500_000_000,
            controller_release_ns=100_000_000,
            backend_release_ns=50_000_000,
            start_evidence_ns=250_000_000,
            stop_evidence_ns=250_000_000,
            max_metadata_operations=8,
            max_metadata_bytes=4096,
            history_ns=1_000_000_000,
            space_query_ns=1_000_000_000,
            low_space_bytes=1,
        )
    )


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
    completed: list[CameraOperation] = []
    retention = type("R", (), {"complete_internal": staticmethod(completed.append)})()
    camera = CameraCommands(
        lifecycle=env.lifecycle,
        configuration=env.configuration,
        device=env.device,
        backends={},
        projections=cast(Any, None),
        file_policy_loader=None,
        generation=_id(),
        limits=_limits(),
        clock=lambda: env.now,
        hooks=env.hooks,
        status_retention=cast(Any, retention),
    )
    child = _id()
    deadline = env.now + 500

    def select(request: svc.CameraCommandRequest) -> CameraSelection:
        return CameraSelection(
            cast(BackendPort, _FailingBackend()),
            1,
            pb.WorkContext(),
            camera_pb.CameraSessionSettings(),
            None,
        )

    def dispatch(request: Any, selection: Any, policy: Any) -> CameraDispatch:
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
    assert env.device.completed_camera_operation is operation
    assert completed == [operation]


def _display(env: _Env, loader: Any) -> DisplayInitialization:
    setting = pb.BackendSettings(backend_name="vr", enabled=True)
    setting.vr.display.profile_json = "{}"
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
            "vr": cast(BackendPort, type("B", (), {"context": pb.BackendContext()})())
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
    policy = vr_pb.VRFilePolicies()
    policy.limits.max_document_bytes = 1
    return {"vr": policy}


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
    assert any(w.component == "vr_display" for w in env.control.warnings)


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
    display.backends = {"vr": cast(BackendPort, Backend())}
    result = await display.initialize_display()
    assert result.result == pb.COMMAND_RESULT_ACCEPTED
    assert env.device.display_pending is not None
    assert len(sent) == 1
    for task in env.spawned:
        task.close()
    assert asyncio.get_running_loop() is not None
