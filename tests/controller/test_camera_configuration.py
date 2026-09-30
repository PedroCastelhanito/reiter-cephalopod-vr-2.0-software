"""Camera edit admission and exact readback adoption, including late reports."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

import cephvr.controller.device.readback as readback_module
from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.device.ports import DeviceHooks
from cephvr.controller.device.status_retention import CameraStatusRetention
from cephvr.controller.device.views import DeviceViews
from cephvr.controller.lifecycle import acquisition_resolution as resolution_module
from cephvr.controller.projections import ProjectionStore
from cephvr.controller.runtime import ControllerRuntime
from cephvr.controller.state import (
    CameraOperation,
    ConfigurationState,
    DeviceState,
    LifecycleState,
)
from cephvr.shared.commands import CommandLedger
from tests.controller.support_components import _attempt, _id, _runtime


class _Projection:
    def __init__(self) -> None:
        self.device_accepts = 0
        self.newer_accepts = 0

    def accept_devices(self, report: svc.AcquisitionDeviceStatusReport) -> bool:
        _ = report
        self.device_accepts += 1
        return True

    def accept_newer_devices(self, report: svc.AcquisitionDeviceStatusReport) -> bool:
        _ = report
        self.newer_accepts += 1
        return True

    def validate_devices(self, report: svc.AcquisitionDeviceStatusReport) -> None:
        _ = report


class _Hooks:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.publishes = 0

    def complete_operation(
        self, command_id: str, *, success: bool, progress: str, error: str = ""
    ) -> None:
        _ = command_id, progress
        assert not success
        self.failures.append(error)

    def publish(self) -> None:
        self.publishes += 1


def test_exact_camera_status_after_deadline_is_retained_and_adopted_if_newer() -> None:
    child_id = str(uuid4())
    operation = CameraOperation(
        operator_id=str(uuid4()),
        child_id=child_id,
        revision=3,
        camera=1,
        kind=svc.CAMERA_COMMAND_KIND_START_PREVIEW,
        work=pb.WorkContext(),
        deadline_ns=100,
        readback_required=False,
    )
    device = DeviceState(camera_operation=operation)
    generation = str(uuid4())
    ledger = CommandLedger(
        generation,
        10_000,
        max_records=16,
        max_bytes=1_000_000,
        result_reservation_bytes=4096,
    )
    ledger.admit(
        operation.operator_id,
        b"camera-command-1",
        1,
        work_key=operation.operator_id,
    )
    retention = CameraStatusRetention(device, clock=lambda: 101)
    retention.bind_ledger(ledger)
    retention.reserve(operation)
    projection = _Projection()
    hooks = _Hooks()
    lifecycle = LifecycleState()

    def finish(camera_operation: CameraOperation) -> None:
        if camera_operation is operation:
            assert camera_operation.timed_out
        device.completed_camera_operation = camera_operation
        retention.complete_internal(camera_operation)
        if device.camera_operation is camera_operation:
            device.camera_operation = None
        device.camera_operation_changed.set()

    views = DeviceViews(
        lifecycle=lifecycle,
        configuration=ConfigurationState(
            pb.ExperimentConfiguration(), pb.ControlPolicies()
        ),
        device=device,
        projections=cast(ProjectionStore, projection),
        clock=lambda: 101,
        hooks=cast(DeviceHooks, hooks),
        finish_camera_operation=finish,
        status_retention=retention,
    )
    report = svc.AcquisitionDeviceStatusReport()
    report.operation.command_id = child_id
    report.work.CopyFrom(operation.work)
    report.result.context.command_id = child_id
    report.result.work.CopyFrom(operation.work)
    report.result.complete = True
    report.result.succeeded = True
    report.views.source.backend_name = "acquisition"
    report.views.source.backend_generation = str(uuid4())
    report.views.state_revision = 1
    report.views.observed_monotonic_ns = 99

    async def submit() -> pb.ReportReceipt:
        return await views.report_projection("devices", report, ingress_ns=101)

    receipt = asyncio.run(submit())

    assert receipt.result == pb.COMMAND_RESULT_ACCEPTED
    assert operation.final_status == report
    assert operation.timed_out
    assert projection.newer_accepts == 1
    assert projection.device_accepts == 0
    assert hooks.failures == ["exact completion missed its original deadline"]
    assert device.camera_operation is None
    assert device.camera_operation_changed.is_set()
    assert hooks.publishes == 1

    current = CameraOperation(
        operator_id=str(uuid4()),
        child_id=str(uuid4()),
        revision=4,
        camera=1,
        kind=svc.CAMERA_COMMAND_KIND_START_PREVIEW,
        work=pb.WorkContext(),
        deadline_ns=200,
        readback_required=False,
    )
    device.camera_operation = current
    device.camera_operation_changed.clear()
    ledger.admit(
        current.operator_id,
        b"camera-command-2",
        102,
        work_key=current.operator_id,
    )
    retention.reserve(current)

    current_report = svc.AcquisitionDeviceStatusReport()
    current_report.operation.command_id = current.child_id
    current_report.work.CopyFrom(current.work)
    current_report.result.context.command_id = current.child_id
    current_report.result.work.CopyFrom(current.work)
    current_report.result.complete = True
    current_report.result.succeeded = True
    current_report.views.source.CopyFrom(report.views.source)
    current_report.views.state_revision = 2
    current_report.views.observed_monotonic_ns = 150

    async def retry() -> pb.ReportReceipt:
        return await views.report_projection("devices", report, ingress_ns=102)

    retry_receipt = asyncio.run(retry())
    assert retry_receipt.result == pb.COMMAND_RESULT_ACCEPTED
    assert device.camera_operation is current
    assert projection.device_accepts == 0

    async def finish_second_operation() -> pb.ReportReceipt:
        return await views.report_projection("devices", current_report, ingress_ns=150)

    second_receipt = asyncio.run(finish_second_operation())
    assert second_receipt.result == pb.COMMAND_RESULT_ACCEPTED
    assert current.final_status == current_report
    assert device.camera_operation is None
    assert device.completed_camera_operation is current
    assert projection.device_accepts == 1

    async def retry_old_after_second_completion() -> pb.ReportReceipt:
        return await views.report_projection("devices", report, ingress_ns=160)

    old_retry = asyncio.run(retry_old_after_second_completion())
    assert old_retry.result == pb.COMMAND_RESULT_ACCEPTED
    assert projection.device_accepts == 1

    changed = svc.AcquisitionDeviceStatusReport.FromString(
        report.SerializeToString(deterministic=True)
    )
    changed.views.state_revision += 1

    async def changed_retry() -> pb.ReportReceipt:
        return await views.report_projection("devices", changed, ingress_ns=103)

    changed_receipt = asyncio.run(changed_retry())
    assert changed_receipt.result == pb.COMMAND_RESULT_REJECTED
    assert device.camera_operation is None
    assert projection.device_accepts == 1


async def test_exact_duplicate_resolution_after_adoption_is_accepted(
    tmp_path: Path,
) -> None:
    runtime = _runtime_with_validators(tmp_path)
    backend = _Acquisition(pb.COMMAND_RESULT_ACCEPTED)
    attempt = _attempt(runtime, tmp_path, {"acquisition": cast(Any, backend)})
    attempt.setup_deadline_ns = 10**12
    attempt.setup_operations["acquisition"] = _id()
    runtime.lifecycle.attempt = attempt
    runtime.lifecycle.session = pb.SessionState(phase=pb.SESSION_PHASE_SETTING_UP)
    resolver = runtime.acquisition_resolution
    spawned: list[Any] = []
    resolver.spawn = lambda coroutine: spawned.append(coroutine) or coroutine  # type: ignore[assignment,return-value]

    report = svc.AcquisitionResolutionReport(requested_configuration_revision=1)
    report.source.CopyFrom(backend.context)
    report.work.session.CopyFrom(attempt.context)
    report.operation.command_id = attempt.setup_operations["acquisition"]

    first = await resolver.report_acquisition_resolution(report, 1_000)
    assert first.result == pb.COMMAND_RESULT_ACCEPTED
    spawned[0].close()
    attempt.prepared.configuration_revision = 2  # adoption bumped the revision

    duplicate = await resolver.report_acquisition_resolution(report, 1_000)
    assert duplicate.result == pb.COMMAND_RESULT_ACCEPTED
    changed = svc.AcquisitionResolutionReport()
    changed.CopyFrom(report)
    changed.requested_configuration_revision = 2
    rejected = await resolver.report_acquisition_resolution(changed, 1_000)
    assert rejected.result == pb.COMMAND_RESULT_REJECTED
    assert len(spawned) == 1


async def _manual_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, result: int
) -> tuple[Any, _Acquisition, pb.ExperimentConfiguration]:
    runtime = _runtime_with_validators(tmp_path)
    backend = _Acquisition(result)
    runtime.camera_readback.backends = {"acquisition": cast(Any, backend)}
    runtime.camera_readback.validators = runtime.configuration_commands.validators
    setting = runtime.configuration_state.current.backends.add(
        backend_name="acquisition", enabled=True
    )
    setting.acquisition.behavioral.enabled = True
    candidate = pb.ExperimentConfiguration()
    candidate.CopyFrom(runtime.configuration_state.current)
    candidate.experiment = "resolved"
    monkeypatch.setattr(
        readback_module, "resolved_configuration", lambda *a, **k: candidate
    )
    operation = CameraOperation(
        _id(),
        _id(),
        1,
        1,
        svc.CAMERA_COMMAND_KIND_IMPORT_PFS,
        pb.WorkContext(),
        10**12,
        True,
    )
    runtime.device_state.camera_operation = operation
    report = svc.AcquisitionResolutionReport()
    await runtime.camera_readback.adopt_camera_resolution(operation, report)
    return runtime, backend, candidate


async def test_manual_readback_rejection_leaves_configuration_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, backend, _candidate = await _manual_readback(
        tmp_path, monkeypatch, pb.COMMAND_RESULT_REJECTED
    )
    assert backend.confirmations[0].confirmed_configuration_revision == 2
    assert runtime.configuration_state.revision == 1
    assert runtime.configuration_state.current.experiment != "resolved"
    assert runtime.device_state.camera_operation is None


async def test_manual_readback_acceptance_commits_and_bumps_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, _backend, candidate = await _manual_readback(
        tmp_path, monkeypatch, pb.COMMAND_RESULT_ACCEPTED
    )
    assert runtime.configuration_state.revision == 2
    assert runtime.configuration_state.current == candidate
    assert runtime.projections.configuration_revision == 2


def _runtime_with_validators(tmp_path: Path) -> ControllerRuntime:
    runtime = _runtime(
        tmp_path, pb.BackendContext(backend_name="vr", backend_generation=_id())
    )
    runtime.configuration_commands.validators = {
        "v": lambda _c: pb.ValidationResult(completed=True, valid=True)
    }
    runtime.setup_admission.validators = runtime.configuration_commands.validators
    runtime.configuration_commands.control_operations.authorized = (  # type: ignore[method-assign]
        lambda *a, **k: ""
    )
    return runtime


def _open_preview(runtime: ControllerRuntime) -> None:
    views = pb.AcquisitionDeviceViews()
    views.tracking.preview_running = True
    runtime.projections.devices = views


def _command(runtime: ControllerRuntime) -> svc.OperatorCommand:
    return svc.OperatorCommand(
        controller_generation=runtime.generation,
        operator=pb.OperatorContext(command_id=_id()),
    )


@pytest.mark.parametrize("via", ["preview", "operation"])
async def test_setup_rejected_while_camera_preview_or_operation_open(
    tmp_path: Path, via: str
) -> None:
    runtime = _runtime_with_validators(tmp_path)
    if via == "preview":
        _open_preview(runtime)
    else:
        runtime.device_state.camera_operation = cast(Any, object())
    admission = await runtime.setup(_command(runtime))
    assert admission.result == pb.COMMAND_RESULT_REJECTED
    assert admission.failure.message == "stop camera preview/editing first"


async def test_setup_not_blocked_by_camera_guard_when_closed(tmp_path: Path) -> None:
    runtime = _runtime_with_validators(tmp_path)
    admission = await runtime.setup(_command(runtime))
    assert admission.failure.message != "stop camera preview/editing first"


def _update(
    runtime: ControllerRuntime, **changes: str
) -> svc.UpdateConfigurationRequest:
    proposed = pb.ExperimentConfiguration()
    proposed.CopyFrom(runtime.configuration_state.current)
    for key, value in changes.items():
        setattr(proposed, key, value)
    request = svc.UpdateConfigurationRequest(
        expected_revision=runtime.configuration_state.revision, proposed=proposed
    )
    request.command.operator.command_id = _id()
    return request


async def test_camera_setting_edit_rejected_while_preview_open(tmp_path: Path) -> None:
    runtime = _runtime_with_validators(tmp_path)
    _open_preview(runtime)
    request = _update(runtime)
    setting = request.proposed.backends.add(backend_name="acquisition", enabled=True)
    setting.acquisition.behavioral.enabled = True
    rejected = await runtime.update_configuration(request)
    assert rejected.result == pb.COMMAND_RESULT_REJECTED
    assert rejected.failure.message == (
        "stop camera preview/editing to edit camera or pulse settings"
    )
    other = await runtime.update_configuration(_update(runtime, experiment="e2"))
    assert other.result == pb.COMMAND_RESULT_ACCEPTED


class _Acquisition:
    def __init__(self, result: int) -> None:
        self.context = pb.BackendContext(
            backend_name="acquisition", backend_generation=_id()
        )
        self.result = result
        self.confirmations: list[svc.AcquisitionConfigurationConfirmation] = []

    async def confirm_configuration(
        self,
        confirmation: svc.AcquisitionConfigurationConfirmation,
        *,
        deadline_ns: int,
    ) -> pb.CommandAdmission:
        self.confirmations.append(confirmation)
        return pb.CommandAdmission(
            result=self.result, failure=pb.Failure(message="nope")
        )


async def _adopt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, result: int
) -> tuple[ControllerRuntime, _Acquisition, list[str], pb.ExperimentConfiguration]:
    runtime = _runtime_with_validators(tmp_path)
    backend = _Acquisition(result)
    attempt = _attempt(runtime, tmp_path, {"acquisition": cast(Any, backend)})
    attempt.setup_deadline_ns = 10**12
    attempt.setup_operations["acquisition"] = _id()
    setting = attempt.prepared.configuration.backends.add(
        backend_name="acquisition", enabled=True
    )
    setting.acquisition.behavioral.enabled = True
    candidate = pb.ExperimentConfiguration()
    candidate.CopyFrom(attempt.prepared.configuration)
    candidate.experiment = "resolved"
    monkeypatch.setattr(
        resolution_module, "resolved_configuration", lambda *a, **k: candidate
    )
    runtime.lifecycle.attempt = attempt
    runtime.lifecycle.session = pb.SessionState(phase=pb.SESSION_PHASE_SETTING_UP)
    resolver = runtime.acquisition_resolution
    resolver.preparation_context = cast(
        Any, SimpleNamespace(handoff_command=lambda *a: svc.BackendCommand())
    )
    resolver.validators = runtime.configuration_commands.validators
    failures: list[str] = []

    async def fail(_attempt: object, _command: str, error: str) -> None:
        failures.append(error)

    monkeypatch.setattr(resolver.setup_execution, "fail_setup", fail)
    report = svc.AcquisitionResolutionReport()
    await resolver.adopt_acquisition_resolution(attempt, report)
    return runtime, backend, failures, candidate


async def test_rejected_readback_confirmation_keeps_prior_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, backend, failures, _candidate = await _adopt(
        tmp_path, monkeypatch, pb.COMMAND_RESULT_REJECTED
    )
    assert runtime.configuration_state.revision == 1
    assert runtime.configuration_state.current.experiment != "resolved"
    assert backend.confirmations[0].confirmed_configuration_revision == 2
    assert failures and "nope" in failures[0]


async def test_accepted_readback_confirmation_commits_and_bumps_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, _backend, failures, candidate = await _adopt(
        tmp_path, monkeypatch, pb.COMMAND_RESULT_ACCEPTED
    )
    assert not failures
    assert runtime.configuration_state.revision == 2
    assert runtime.configuration_state.current == candidate
    assert runtime.projections.configuration_revision == 2
    attempt = runtime.lifecycle.attempt
    assert attempt is not None and attempt.resolution_confirmed
    assert attempt.prepared.configuration_revision == 2
