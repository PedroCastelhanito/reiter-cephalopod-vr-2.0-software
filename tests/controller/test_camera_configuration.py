"""Camera edit admission and exact readback adoption, including late reports."""

from __future__ import annotations

import asyncio
import dataclasses
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

import cephvr.controller.device.readback as readback_module
from cephvr.acquisition.configuration import validate_configuration
from cephvr.acquisition.coordinator.configuration_resolution import (
    ConfigurationResolution,
)
from cephvr.acquisition.coordinator.manual_device_status import (
    ManualDeviceStatusReporter,
)
from cephvr.acquisition.coordinator.manual_devices import ManualDevices
from cephvr.acquisition.coordinator.queries import CoordinatorQueries
from cephvr.acquisition.coordinator.state import (
    ConfigurationRecord,
    CoordinatorIdentity,
    PulseRecord,
    SessionSlot,
)
from cephvr.acquisition.v1 import camera_pb2 as acquisition_camera_pb
from cephvr.acquisition.v1 import runtime_pb2 as acquisition_pb
from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.configuration import manual_camera_owned
from cephvr.controller.device.ports import DeviceHooks
from cephvr.controller.device.status_retention import CameraStatusRetention
from cephvr.controller.device.views import DeviceViews
from cephvr.controller.lifecycle import acquisition_resolution as resolution_module
from cephvr.controller.projections import ProjectionStore
from cephvr.controller.runtime import ControllerRuntime
from cephvr.controller.state import (
    CameraOperation,
    ConfigurationEditTerminal,
    ConfigurationState,
    DeviceState,
    LifecycleState,
    Watch,
)
from cephvr.shared.admission import CommandAdmissionTransport
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger
from tests.controller.support_components import (
    _attempt,
    _id,
    _runtime,
    bind_ledger,
    operator_command,
)


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


def test_camera_failure_retains_original_device_reason(tmp_path) -> None:
    runtime = _runtime_with_validators(tmp_path)
    hooks = _Hooks()
    runtime.camera_readback.hooks = cast(Any, hooks)
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
    operation.final_status = svc.AcquisitionDeviceStatusReport()
    operation.final_status.result.succeeded = False
    operation.final_status.result.failure.message = "Gain capability is unavailable"
    runtime.device_state.camera_operation = operation
    runtime.camera_readback.finish_camera_operation(operation)
    assert hooks.failures == ["Gain capability is unavailable"]
    assert runtime.device_state.camera_operation is None


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
    assert retention.find(current.child_id) is current
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
        tmp_path,
        pb.BackendContext(backend_name="visual_stimulus", backend_generation=_id()),
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


@pytest.mark.parametrize("via", ["preview", "operation"])
async def test_setup_rejected_while_camera_preview_or_operation_open(
    tmp_path: Path, via: str
) -> None:
    runtime = _runtime_with_validators(tmp_path)
    if via == "preview":
        _open_preview(runtime)
    else:
        runtime.device_state.camera_operation = cast(Any, object())
    admission = await runtime.setup(operator_command(runtime))
    assert admission.result == pb.COMMAND_RESULT_REJECTED
    assert admission.failure.message == "stop camera preview/editing first"


async def test_setup_not_blocked_by_camera_guard_when_closed(tmp_path: Path) -> None:
    runtime = _runtime_with_validators(tmp_path)
    admission = await runtime.setup(operator_command(runtime))
    assert admission.failure.message != "stop camera preview/editing first"


@pytest.mark.parametrize("extra_edit", ["", "settings", "experiment"])
async def test_camera_participation_can_precede_settings_validation(
    tmp_path: Path, extra_edit: str
) -> None:
    runtime = _runtime_with_validators(tmp_path)
    runtime.configuration_commands.validators = {
        "experiment": lambda _c: pb.ValidationResult(completed=True, valid=True),
        "acquisition": validate_configuration,
    }
    runtime.setup_admission.validators = runtime.configuration_commands.validators
    entry = runtime.configuration_state.current.backends.add(
        backend_name="acquisition", enabled=False
    )
    entry.acquisition.behavioral.device.device_id = "40065509"
    entry.acquisition.behavioral.enabled = False
    request = _update(runtime)
    proposed = request.proposed.backends[0]
    proposed.enabled = True
    proposed.acquisition.behavioral.enabled = True
    if extra_edit == "settings":
        proposed.acquisition.behavioral.device.settings.trigger_source = "Line4"
    elif extra_edit == "experiment":
        request.proposed.experiment = "new-experiment"

    admission = await runtime.update_configuration(request)

    if extra_edit:
        assert admission.result == pb.COMMAND_RESULT_REJECTED
        assert not runtime.configuration_state.current.backends[0].enabled
        assert runtime.configuration_state.revision == 1
    else:
        assert admission.result == pb.COMMAND_RESULT_ACCEPTED
        assert runtime.configuration_state.current.backends[
            0
        ].acquisition.behavioral.enabled
        assert runtime.configuration_state.revision == 2
        assert not validate_configuration(runtime.configuration_state.current).valid
        setup = await runtime.setup(operator_command(runtime))
        assert setup.result == pb.COMMAND_RESULT_REJECTED


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


class _LiveEditAcquisition:
    def __init__(
        self,
        runtime: ControllerRuntime,
        *,
        reject: bool = False,
        mismatched_rejection: bool = False,
        unspecified_admission: bool = False,
        fail_after_confirmation: bool = False,
        unknown_admission: bool = False,
        confirmation_gate: asyncio.Event | None = None,
    ) -> None:
        self.runtime = runtime
        self.context = pb.BackendContext(
            backend_name="acquisition", backend_generation=_id()
        )
        self.reject = reject
        self.mismatched_rejection = mismatched_rejection
        self.unspecified_admission = unspecified_admission
        self.fail_after_confirmation = fail_after_confirmation
        self.unknown_admission = unknown_admission
        self.confirmation_gate = confirmation_gate
        self.confirmed = asyncio.Event()
        self.confirmation_started = asyncio.Event()
        self.request: svc.AcquisitionCameraSettingsCommand | None = None
        self.confirmation: svc.AcquisitionConfigurationConfirmation | None = None

    async def apply_camera_settings(
        self, request: svc.AcquisitionCameraSettingsCommand, *, deadline_ns: int
    ) -> pb.CommandAdmission:
        _ = deadline_ns
        self.request = request
        if self.unknown_admission:
            raise TimeoutError("ApplyCameraSettings reply was lost")
        if self.reject:
            return pb.CommandAdmission(
                result=pb.COMMAND_RESULT_REJECTED,
                command_id=(
                    _id() if self.mismatched_rejection else request.command.command_id
                ),
                failure=pb.Failure(message="SDK batch rejected"),
            )
        if self.unspecified_admission:
            return pb.CommandAdmission(
                result=pb.COMMAND_RESULT_UNSPECIFIED,
                command_id=request.command.command_id,
            )
        report = svc.AcquisitionResolutionReport(
            source=self.context,
            operation=pb.OperationContext(command_id=request.command.command_id),
            requested_configuration_revision=request.configuration_revision,
        )
        for item in request.cameras:
            resolved = report.cameras.add(camera=item.camera).result
            resolved.configuration_revision = request.configuration_revision
            resolved.device.configured_id = item.requested.device_id
            resolved.device.physical_id = f"physical-{item.camera}"
            resolved.applied.CopyFrom(item.requested)
            resolved.capabilities.SetInParent()
            resolved.layout.width = 640
            resolved.layout.height = 480
            resolved.transport.CopyFrom(item.transport)
        receipt = await self.runtime.report_acquisition_resolution(
            report, self.runtime.clock()
        )
        assert receipt.result == pb.COMMAND_RESULT_ACCEPTED
        await asyncio.wait_for(self.confirmed.wait(), 1)
        if self.fail_after_confirmation:
            return pb.CommandAdmission(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(message="preview restart failed after confirmation"),
            )
        return pb.CommandAdmission(
            result=pb.COMMAND_RESULT_ACCEPTED,
            command_id=request.command.command_id,
        )

    async def confirm_configuration(
        self,
        request: svc.AcquisitionConfigurationConfirmation,
        *,
        deadline_ns: int,
    ) -> pb.CommandAdmission:
        _ = deadline_ns
        self.confirmation = request
        self.confirmation_started.set()
        if self.confirmation_gate is not None:
            await self.confirmation_gate.wait()
        self.confirmed.set()
        return pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED)


async def test_configuration_edit_uses_retained_resolution_while_preview_open(
    tmp_path: Path,
) -> None:
    runtime = _runtime_with_validators(tmp_path)
    _open_preview(runtime)
    acquisition = runtime.configuration_state.current.backends.add(
        backend_name="acquisition", enabled=True
    )
    acquisition.acquisition.behavioral.enabled = True
    assert manual_camera_owned(runtime.projections, runtime.device_state)
    backend = _LiveEditAcquisition(runtime)
    runtime.configuration_commands.owned_edits.backend = cast(Any, backend)
    runtime.acquisition_resolution.backends = {"acquisition": cast(Any, backend)}
    runtime.acquisition_resolution.validators = (
        runtime.configuration_commands.validators
    )
    runtime.acquisition_resolution.authorized = lambda _command: ""
    runtime.configuration_commands.owned_edits.file_policy_loader = lambda _names: {
        "acquisition": acquisition_pb.AcquisitionFilePolicies()
    }
    request = _update(runtime, experiment="e2")

    admission = await runtime.update_configuration(request)

    assert admission.result == pb.COMMAND_RESULT_ACCEPTED, admission.failure.message
    assert runtime.configuration_state.current.experiment == "e2"
    assert runtime.configuration_state.revision == 2
    assert backend.request is not None and not backend.request.cameras
    assert backend.confirmation is not None
    assert backend.confirmation.confirmed_configuration_revision == 2


@pytest.mark.parametrize("never_confirm", [False, True])
async def test_empty_edit_uses_real_acquisition_status_and_completion_path(
    tmp_path: Path, never_confirm: bool
) -> None:
    runtime = _runtime_with_validators(tmp_path)
    runtime.clock = host_time_ns
    runtime.acquisition_resolution.clock = host_time_ns
    runtime.device_views.clock = host_time_ns
    runtime.configuration_commands.clock = host_time_ns
    runtime.configuration_commands.owned_edits.clock = host_time_ns
    if never_confirm:
        runtime.configuration_commands.owned_edits.limits.current = dataclasses.replace(
            runtime.configuration_commands.owned_edits.limits.current,
            setup_ns=100_000_000,
            recovery_ns=1_000_000,
        )
    _open_preview(runtime)
    entry = runtime.configuration_state.current.backends.add(
        backend_name="acquisition", enabled=True
    )
    entry.acquisition.behavioral.enabled = True
    backend_context = pb.BackendContext(
        backend_name="acquisition", backend_generation=_id()
    )
    runtime.projections.peers["acquisition"] = backend_context
    controller_identity = pb.ProcessIdentity(
        role="controller",
        generation=runtime.configuration_commands.owned_edits.generation,
    )
    acquisition_settings = pb.AcquisitionSettings()
    acquisition_settings.CopyFrom(entry.acquisition)
    file_policies = acquisition_pb.AcquisitionFilePolicies()
    configuration = ConfigurationRecord(
        settings=acquisition_settings,
        file_policies=file_policies,
        revision=runtime.configuration_state.revision,
    )
    commands = CommandLedger(
        backend_context.backend_generation,
        10_000,
        max_records=16,
        max_bytes=1_000_000,
        result_reservation_bytes=4096,
    )

    class _Bridge:
        resolution_receipt: pb.ReportReceipt | None = None
        status_receipt: pb.ReportReceipt | None = None
        lifecycle_receipt: pb.ReportReceipt | None = None
        lifecycle_report: pb.LifecycleReport | None = None

        def __init__(self) -> None:
            self.status_started = asyncio.Event()
            self.status_gate = asyncio.Event()

        async def report_acquisition_resolution(self, report, *, deadline_ns):
            _ = deadline_ns
            self.resolution_receipt = await runtime.report_acquisition_resolution(
                report, runtime.clock()
            )
            return self.resolution_receipt

        async def report_acquisition_device_status(self, report, *, deadline_ns):
            _ = deadline_ns
            self.status_started.set()
            await self.status_gate.wait()
            self.status_receipt = await runtime.report_projection(
                "devices", report, runtime.clock()
            )
            return self.status_receipt

        async def report_lifecycle(self, report, *, deadline_ns):
            _ = deadline_ns
            self.lifecycle_report = pb.LifecycleReport.FromString(
                report.SerializeToString(deterministic=True)
            )
            self.lifecycle_receipt = await runtime.report_lifecycle(
                report, runtime.clock()
            )
            return self.lifecycle_receipt

    bridge = _Bridge()
    identity = CoordinatorIdentity(
        backend=backend_context,
        process=pb.ProcessIdentity(
            role="acquisition", generation=backend_context.backend_generation
        ),
        controller=controller_identity,
        supervisor=pb.ProcessIdentity(role="supervisor", generation=_id()),
        tracking=pb.ProcessIdentity(role="tracking", generation=_id()),
    )
    resolution = ConfigurationResolution(
        identity=identity,
        configuration=configuration,
        controller=bridge,  # type: ignore[arg-type]
        lock=asyncio.Lock(),
        clock=runtime.clock,
    )
    device_status = ManualDeviceStatusReporter(
        identity=identity,
        controller=bridge,  # type: ignore[arg-type]
        commands=commands,
        pulse=PulseRecord(),
        clock=runtime.clock,
    )

    class _Workers:
        workers: dict[int, Any] = {}

        async def retire_completed_session(self, *_args, **_kwargs):
            return None

    class _Serial:
        pass

    class _Preview:
        pass

    manual = ManualDevices(
        identity=identity,
        configuration=configuration,
        session_slot=SessionSlot(),
        workers=_Workers(),  # type: ignore[arg-type]
        controller=bridge,  # type: ignore[arg-type]
        resolution=resolution,
        device_status=device_status,
        pulse=device_status.pulse,
        serial=_Serial(),  # type: ignore[arg-type]
        preview=_Preview(),  # type: ignore[arg-type]
        lock=resolution.lock,
        clock=runtime.clock,
    )

    class _Backend:
        context = backend_context

        def __init__(self) -> None:
            self.request: svc.AcquisitionCameraSettingsCommand | None = None
            self.manual_admission: pb.CommandAdmission | None = None
            self.confirmation_admission: pb.CommandAdmission | None = None
            self.confirmation_started = asyncio.Event()
            self.confirmation_gate = asyncio.Event()
            self.confirmation_calls = 0
            self.transport = CommandAdmissionTransport(commands)

        async def apply_camera_settings(self, request, *, deadline_ns):
            self.request = request

            async def execute(*, deadline_ns):
                self.manual_admission = await manual.apply(
                    request, deadline_ns=deadline_ns
                )
                return self.manual_admission

            return await self.transport.dispatch(
                "ApplyCameraSettings",
                request,
                request.command,
                deadline_ns,
                execute,
            )

        async def confirm_configuration(self, request, *, deadline_ns):
            self.confirmation_calls += 1
            self.confirmation_started.set()
            await self.confirmation_gate.wait()
            self.confirmation_admission = await resolution.confirm(
                request, deadline_ns=deadline_ns
            )
            # The handler ran, but the reply was lost. The controller retries
            # the same confirmation command; only the retained device status
            # and completion make the live edit terminal.
            raise TimeoutError("confirmation reply was lost after handler execution")

    backend = _Backend()
    runtime.configuration_commands.owned_edits.backend = backend  # type: ignore[assignment]
    runtime.configuration_commands.owned_edits.file_policy_loader = lambda _names: {
        "acquisition": file_policies
    }
    runtime.acquisition_resolution.backends = {"acquisition": backend}  # type: ignore[assignment]
    runtime.acquisition_resolution.validators = (
        runtime.configuration_commands.validators
    )
    runtime.acquisition_resolution.authorized = lambda _command: ""

    update = asyncio.create_task(
        runtime.update_configuration(_update(runtime, experiment="e3"))
    )
    await asyncio.wait_for(backend.confirmation_started.wait(), 1)
    if never_confirm:
        admission = await asyncio.wait_for(update, 2)
        await asyncio.wait_for(
            asyncio.gather(*tuple(backend.transport._inflight.values())), 2
        )
        assert admission.result == pb.COMMAND_RESULT_ACCEPTED
        assert runtime.configuration_state.revision == 2
        assert runtime.configuration_state.current.experiment == "e3"
        assert configuration.revision == 1
        assert bridge.status_receipt is None
        assert bridge.lifecycle_receipt is None
        assert backend.request is not None
        local_status = device_status.get_report(backend.request.command.command_id)
        assert local_status is not None and not local_status.result.succeeded
        queries = CoordinatorQueries(
            identity=identity,
            session_slot=manual.session_slot,
            workers={},
            commands=commands,
            device_status=device_status,
            current_error=lambda: None,
            clock=host_time_ns,
        )
        recovered = await queries.get_retained_result(
            svc.RetainedResultQuery(
                query=svc.BackendQuery(target=backend_context),
                command_id=backend.request.command.command_id,
            ),
            deadline_ns=host_time_ns() + 1_000_000_000,
        )
        assert recovered.found
        assert recovered.acquisition_device_result == local_status
        assert recovered.operation.succeeded is False
        assert resolution._pending is None
        retained = runtime.device_state.configuration_edit_terminals[
            backend.request.command.command_id
        ]
        assert retained.device_status is None
        assert retained.operation_result is None

        backend.confirmation_gate.set()
        bridge.status_gate.set()
        runtime.configuration_commands.owned_edits.limits.current = dataclasses.replace(
            runtime.configuration_commands.owned_edits.limits.current,
            setup_ns=2_000_000_000,
            recovery_ns=1_000_000_000,
        )
        retry = await asyncio.wait_for(
            runtime.update_configuration(_update(runtime, experiment="e4")), 2
        )
        await backend.transport.close(host_time_ns() + 2_000_000_000)
        assert retry.result == pb.COMMAND_RESULT_ACCEPTED, retry.failure.message
        assert configuration.revision == runtime.configuration_state.revision == 3
        assert resolution._pending is None
    else:
        assert runtime.configuration_state.revision == 2
        assert runtime.configuration_state.current.experiment == "e3"
        assert configuration.revision == 1
        backend.confirmation_gate.set()
        await asyncio.wait_for(bridge.status_started.wait(), 1)
        admission = await asyncio.wait_for(update, 1)
        assert runtime.device_state.configuration_edit is None
        bridge.status_gate.set()
        await backend.transport.close(host_time_ns() + 5_000_000_000)

    assert backend.manual_admission is not None
    assert bridge.resolution_receipt is not None
    if not never_confirm:
        assert backend.confirmation_admission is not None
        assert backend.confirmation_calls == 2
        assert backend.manual_admission.result == pb.COMMAND_RESULT_ACCEPTED, (
            backend.manual_admission.failure.message
        )
        assert admission.result == pb.COMMAND_RESULT_ACCEPTED, admission.failure.message
        assert runtime.configuration_state.revision == 2
        assert runtime.configuration_state.current.experiment == "e3"
        assert configuration.revision == 2
        assert backend.request is not None
        retained = runtime.device_state.configuration_edit_terminals[
            backend.request.command.command_id
        ]
        final_status = retained.device_status
        assert final_status is not None and final_status.result.succeeded
        assert runtime.device_state.configuration_edit is None
        assert bridge.lifecycle_report is not None
        assert retained.device_status == final_status
        assert retained.operation_result == bridge.lifecycle_report.operation.operation
        assert (
            await runtime.report_projection("devices", final_status, runtime.clock())
        ).result == pb.COMMAND_RESULT_ACCEPTED
        assert (
            await runtime.report_lifecycle(bridge.lifecycle_report, runtime.clock())
        ).result == pb.COMMAND_RESULT_ACCEPTED
        conflicting = svc.AcquisitionDeviceStatusReport.FromString(
            final_status.SerializeToString(deterministic=True)
        )
        conflicting.result.succeeded = False
        assert (
            await runtime.report_projection("devices", conflicting, runtime.clock())
        ).result == pb.COMMAND_RESULT_REJECTED


async def test_queued_apply_handler_failure_routes_exact_terminal_operation(
    tmp_path: Path,
) -> None:
    runtime = _runtime_with_validators(tmp_path)
    now = host_time_ns()
    deadline_ns = now + 2_000_000_000
    source = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime.projections.peers["acquisition"] = source
    command_id = _id()
    runtime.device_state.configuration_edit_terminals[command_id] = (
        ConfigurationEditTerminal(
            operation_id=command_id, source=source, deadline_ns=deadline_ns
        )
    )
    command = svc.BackendCommand(command_id=command_id)
    request = svc.AcquisitionCameraSettingsCommand(command=command)
    failed_status = svc.AcquisitionDeviceStatusReport(
        views=pb.AcquisitionDeviceViews(
            source=source, state_revision=1, observed_monotonic_ns=now
        ),
        operation=pb.OperationContext(command_id=command_id),
        result=pb.OperationState(
            context=pb.OperationContext(command_id=command_id),
            command="ApplyCameraSettings",
            complete=True,
            succeeded=False,
            failure=pb.Failure(code="CAMERA_EDIT_FAILED", message="SDK failed"),
        ),
    )
    assert (
        await runtime.report_projection("devices", failed_status, now)
    ).result == pb.COMMAND_RESULT_ACCEPTED
    ledger = CommandLedger(
        source.backend_generation,
        10_000,
        max_records=8,
        max_bytes=100_000,
        result_reservation_bytes=4096,
    )

    async def terminal_failure(method, _command, outcome, terminal_deadline):
        receipt = await runtime.report_lifecycle(
            pb.LifecycleReport(
                operation=pb.BackendOperationReport(
                    source=source,
                    operation=pb.OperationState.FromString(
                        outcome.SerializeToString(deterministic=True)
                    ),
                )
            ),
            runtime.clock(),
        )
        assert method == "ApplyCameraSettings"
        assert terminal_deadline == deadline_ns
        assert receipt.result == pb.COMMAND_RESULT_ACCEPTED

    transport = CommandAdmissionTransport(ledger, terminal_failure=terminal_failure)

    async def fail(*, deadline_ns):
        _ = deadline_ns
        return pb.CommandAdmission(
            result=pb.COMMAND_RESULT_REJECTED,
            command_id=command_id,
            failure=pb.Failure(code="CAMERA_EDIT_FAILED", message="SDK failed"),
        )

    admission = await transport.dispatch(
        "ApplyCameraSettings", request, command, deadline_ns, fail
    )
    assert admission.result == pb.COMMAND_RESULT_ACCEPTED
    await transport.close(host_time_ns() + 2_000_000_000)

    retained = runtime.device_state.configuration_edit_terminals[command_id]
    assert retained.device_status == failed_status
    assert retained.operation_result is not None
    assert retained.operation_result.command == "ApplyCameraSettings"
    assert retained.operation_result.succeeded is False


async def test_owned_camera_batch_commits_only_after_confirmation(
    tmp_path: Path,
) -> None:
    runtime = _runtime_with_validators(tmp_path)
    _open_preview(runtime)
    acquisition = runtime.configuration_state.current.backends.add(
        backend_name="acquisition", enabled=True
    )
    acquisition.acquisition.tracking.enabled = True
    acquisition.acquisition.tracking.device.device_id = "CAM-TRACK"
    acquisition.acquisition.tracking.device.settings.trigger_source = "Line1"
    backend = _LiveEditAcquisition(runtime, confirmation_gate=asyncio.Event())
    runtime.configuration_commands.owned_edits.backend = cast(Any, backend)
    runtime.acquisition_resolution.backends = {"acquisition": cast(Any, backend)}
    runtime.acquisition_resolution.validators = (
        runtime.configuration_commands.validators
    )
    runtime.acquisition_resolution.authorized = lambda _command: ""
    policies = acquisition_pb.AcquisitionFilePolicies()
    policy = policies.cameras.add(camera=acquisition_camera_pb.CAMERA_ROLE_TRACKING)
    policy.transport.SetInParent()
    runtime.configuration_commands.owned_edits.file_policy_loader = lambda _names: {
        "acquisition": policies
    }
    request = _update(runtime)
    request.proposed.backends[
        0
    ].acquisition.tracking.device.settings.trigger_source = "Line2"

    update = asyncio.create_task(runtime.update_configuration(request))
    await asyncio.wait_for(backend.confirmation_started.wait(), 1)
    camera_command = svc.CameraCommandRequest(
        kind=svc.CAMERA_COMMAND_KIND_STOP_PREVIEW,
        camera=acquisition_camera_pb.CAMERA_ROLE_TRACKING,
        expected_configuration_revision=runtime.configuration_state.revision,
        preview_run_id="held-edit-run",
    )
    camera_command.command.operator.command_id = _id()
    camera_admission = await runtime.execute_camera_command(camera_command)
    assert camera_admission.result == pb.COMMAND_RESULT_REJECTED
    mcu_command = svc.MicrocontrollerCommandRequest(
        kind=svc.MICROCONTROLLER_COMMAND_KIND_STATUS,
        expected_configuration_revision=runtime.configuration_state.revision,
    )
    mcu_command.command.operator.command_id = _id()
    mcu_admission = await runtime.execute_microcontroller_command(mcu_command)
    assert mcu_admission.result == pb.COMMAND_RESULT_REJECTED
    # Matched readback commits before the confirmation is admitted; the held
    # transport reply does not gate adoption.
    assert runtime.configuration_state.revision == 2
    assert (
        runtime.configuration_state.current.backends[
            0
        ].acquisition.tracking.device.settings.trigger_source
        == "Line2"
    )
    assert backend.request is not None
    assert [item.camera for item in backend.request.cameras] == [
        acquisition_camera_pb.CAMERA_ROLE_TRACKING
    ]
    backend.confirmation_gate.set()
    admission = await asyncio.wait_for(update, 1)

    assert admission.result == pb.COMMAND_RESULT_ACCEPTED, admission.failure.message
    assert runtime.configuration_state.revision == 2
    assert (
        runtime.configuration_state.current.backends[
            0
        ].acquisition.tracking.device.settings.trigger_source
        == "Line2"
    )


async def test_owned_edit_backend_rejection_preserves_controller_configuration(
    tmp_path: Path,
) -> None:
    runtime = _runtime_with_validators(tmp_path)
    _open_preview(runtime)
    acquisition = runtime.configuration_state.current.backends.add(
        backend_name="acquisition", enabled=True
    )
    acquisition.acquisition.behavioral.enabled = True
    backend = _LiveEditAcquisition(runtime, reject=True)
    runtime.configuration_commands.owned_edits.backend = cast(Any, backend)
    runtime.acquisition_resolution.backends = {"acquisition": cast(Any, backend)}
    runtime.acquisition_resolution.authorized = lambda _command: ""
    runtime.configuration_commands.owned_edits.file_policy_loader = lambda _names: {
        "acquisition": acquisition_pb.AcquisitionFilePolicies()
    }
    old_operation_id = _id()
    runtime.device_state.configuration_edit_terminals[old_operation_id] = (
        ConfigurationEditTerminal(
            operation_id=old_operation_id,
            source=backend.context,
            deadline_ns=runtime.clock() - 1,
        )
    )
    request = _update(runtime, experiment="e2")

    admission = await runtime.update_configuration(request)

    assert admission.result == pb.COMMAND_RESULT_REJECTED
    assert runtime.configuration_state.current.experiment != "e2"
    assert runtime.configuration_state.revision == 1
    assert list(runtime.device_state.configuration_edit_terminals) == [old_operation_id]


async def test_owned_edit_local_policy_rejection_drops_only_never_dispatched_terminal(
    tmp_path: Path,
) -> None:
    runtime = _runtime_with_validators(tmp_path)
    _open_preview(runtime)
    acquisition = runtime.configuration_state.current.backends.add(
        backend_name="acquisition", enabled=True
    )
    acquisition.acquisition.tracking.enabled = True
    acquisition.acquisition.tracking.device.device_id = "CAM-TRACK"
    backend = _LiveEditAcquisition(runtime)
    runtime.configuration_commands.owned_edits.backend = cast(Any, backend)
    runtime.configuration_commands.owned_edits.file_policy_loader = lambda _names: {
        "acquisition": acquisition_pb.AcquisitionFilePolicies()
    }

    request = _update(runtime, experiment="e2")
    request.proposed.backends[0].acquisition.tracking.device.device_id = "CAM-NEXT"
    admission = await runtime.update_configuration(request)

    assert admission.result == pb.COMMAND_RESULT_REJECTED
    assert backend.request is None
    assert runtime.configuration_state.revision == 1
    assert runtime.device_state.configuration_edit is None
    assert runtime.device_state.configuration_edit_terminals == {}


@pytest.mark.parametrize(
    "admission_kind", ["timeout", "unspecified", "mismatched_rejection"]
)
async def test_owned_edit_unknown_admission_retains_cleanup_candidate(
    tmp_path: Path, admission_kind: str
) -> None:
    runtime = _runtime_with_validators(tmp_path)
    _open_preview(runtime)
    acquisition = runtime.configuration_state.current.backends.add(
        backend_name="acquisition", enabled=True
    )
    acquisition.acquisition.tracking.enabled = True
    acquisition.acquisition.tracking.device.device_id = "CAM-TRACK"
    backend = _LiveEditAcquisition(
        runtime,
        unknown_admission=admission_kind == "timeout",
        unspecified_admission=admission_kind == "unspecified",
        reject=admission_kind == "mismatched_rejection",
        mismatched_rejection=admission_kind == "mismatched_rejection",
    )
    runtime.configuration_commands.owned_edits.backend = cast(Any, backend)
    runtime.acquisition_resolution.backends = {"acquisition": cast(Any, backend)}
    runtime.acquisition_resolution.authorized = lambda _command: ""
    policies = acquisition_pb.AcquisitionFilePolicies()
    policies.cameras.add(
        camera=acquisition_camera_pb.CAMERA_ROLE_TRACKING
    ).transport.SetInParent()
    runtime.configuration_commands.owned_edits.file_policy_loader = lambda _names: {
        "acquisition": policies
    }

    admission = await runtime.update_configuration(_update(runtime, experiment="e2"))

    assert admission.result == pb.COMMAND_RESULT_REJECTED
    assert backend.request is not None
    operation_id = backend.request.command.command_id
    assert runtime.configuration_state.revision == 1
    assert runtime.device_state.configuration_edit is None
    assert operation_id in runtime.device_state.configuration_edit_terminals
    async with runtime.lifecycle.lock:
        candidate = runtime.camera._owned_edit_recovery_locked(
            svc.CameraCommandRequest(kind=svc.CAMERA_COMMAND_KIND_STOP_PREVIEW),
            cast(Any, backend),
        )
    assert candidate is not None and candidate[0] == operation_id


async def test_postconfirmation_device_failure_keeps_committed_configuration(
    tmp_path: Path,
) -> None:
    runtime = _runtime_with_validators(tmp_path)
    _open_preview(runtime)
    acquisition = runtime.configuration_state.current.backends.add(
        backend_name="acquisition", enabled=True
    )
    acquisition.acquisition.behavioral.enabled = True
    backend = _LiveEditAcquisition(runtime, fail_after_confirmation=True)
    runtime.configuration_commands.owned_edits.backend = cast(Any, backend)
    runtime.acquisition_resolution.backends = {"acquisition": cast(Any, backend)}
    runtime.acquisition_resolution.validators = (
        runtime.configuration_commands.validators
    )
    runtime.acquisition_resolution.authorized = lambda _command: ""
    runtime.configuration_commands.owned_edits.file_policy_loader = lambda _names: {
        "acquisition": acquisition_pb.AcquisitionFilePolicies()
    }

    admission = await runtime.update_configuration(_update(runtime, experiment="e2"))

    assert admission.result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime.configuration_state.current.experiment == "e2"
    assert runtime.configuration_state.revision == 2


@pytest.mark.parametrize(
    ("query_fault", "request_matches_reported_run"),
    [
        (None, False),
        (None, True),
        ("newer_known_status", True),
        ("wrong_source", False),
        ("wrong_operation", False),
        ("wrong_status_operation", False),
        ("stale_generation", False),
    ],
)
async def test_controller_recovers_expired_owned_edit_status_before_camera_stop(
    tmp_path: Path, query_fault: str | None, request_matches_reported_run: bool
) -> None:
    from cephvr.acquisition.coordinator.manual_preview import ManualPreview
    from cephvr.acquisition.coordinator.state import (
        LaunchRecord,
        WorkerPreview,
        WorkerRecord,
    )
    from cephvr.acquisition.v1 import messages_pb2 as acq
    from cephvr.control.v1 import types_pb2 as control
    from cephvr.shared.commands import CommandLedger

    runtime = _runtime_with_validators(tmp_path)
    run_id = _id()
    stale_run_id = _id()
    _open_preview(runtime)
    runtime.projections.devices.tracking.preview_run_id = (
        run_id if request_matches_reported_run else stale_run_id
    )
    runtime.configuration_state.revision = 2
    entry = runtime.configuration_state.current.backends.add(
        backend_name="acquisition", enabled=True
    )
    entry.acquisition.tracking.enabled = True
    entry.acquisition.tracking.device.device_id = "CAM-TRACK"
    backend_context = pb.BackendContext(
        backend_name="acquisition", backend_generation=_id()
    )
    runtime.projections.peers["acquisition"] = backend_context
    backend_identity = pb.ProcessIdentity(
        role="acquisition", generation=backend_context.backend_generation
    )
    controller_identity = pb.ProcessIdentity(
        role="controller", generation=runtime.generation
    )
    settings = pb.AcquisitionSettings()
    settings.CopyFrom(entry.acquisition)
    policies = acquisition_pb.AcquisitionFilePolicies()
    policies.cameras.add(
        camera=acquisition_camera_pb.CAMERA_ROLE_TRACKING
    ).transport.SetInParent()
    configuration = ConfigurationRecord(settings, policies, revision=1)
    worker_identity = pb.ProcessIdentity(
        role="acquisition_tracking_worker", generation=_id()
    )
    worker_owner = backend_identity
    work = pb.WorkContext()
    worker_context = acq.WorkerContext(
        worker=worker_identity,
        owner=worker_owner,
        camera=acquisition_camera_pb.CAMERA_ROLE_TRACKING,
    )
    preview = WorkerPreview(
        run_id=run_id,
        configuration_revision=1,
        resolved_camera=acquisition_camera_pb.CameraResolvedState(),
        started=True,
    )
    ledger = CommandLedger(
        backend_context.backend_generation,
        10_000,
        max_records=16,
        max_bytes=1_000_000,
        result_reservation_bytes=4096,
    )

    class _WorkerPort:
        record: WorkerRecord

        async def stop_preview(self, request, *, deadline_ns):
            child = self.record.child_operations[request.command.command_id]
            child.report = control.OperationState(
                context=control.OperationContext(command_id=child.command_id),
                complete=True,
                succeeded=True,
            )
            child.report_ingress_ns = runtime.clock()
            child.report_revision = 1
            child.updated.set()
            preview.started = False
            preview.stopped_event.set()
            preview.cleanup_event.set()
            assert request.preview_run_id == run_id
            assert deadline_ns == child.deadline_ns
            return control.CommandAdmission(
                result=control.COMMAND_RESULT_ACCEPTED,
                command_id=request.command.command_id,
            )

    port = _WorkerPort()
    worker = WorkerRecord(
        context=worker_context,
        port=port,  # type: ignore[arg-type]
        launch=LaunchRecord(
            command_id=_id(),
            worker=worker_identity,
            owner=worker_owner,
            work=work,
            camera=acquisition_camera_pb.CAMERA_ROLE_TRACKING,
            parent_operation=control.OperationContext(command_id=_id()),
            planned_ns=host_time_ns(),
        ),
        commands=ledger,
        preview=preview,
    )
    port.record = worker
    identity = CoordinatorIdentity(
        backend=backend_context,
        process=backend_identity,
        controller=controller_identity,
        supervisor=pb.ProcessIdentity(role="supervisor", generation=_id()),
        tracking=pb.ProcessIdentity(role="tracking", generation=_id()),
    )
    resolution = ConfigurationResolution(
        identity=identity,
        configuration=configuration,
        controller=cast(Any, object()),
        lock=asyncio.Lock(),
        clock=host_time_ns,
    )
    edit_id = _id()
    original_deadline_ns = runtime.clock() - 1
    edit = svc.BackendCommand(
        command_id=edit_id,
        issuer=controller_identity,
        target=backend_context,
        parent_operation=control.OperationContext(command_id=edit_id),
    )
    resolution_operation = await resolution.begin(
        edit,
        expected_cameras={acquisition_camera_pb.CAMERA_ROLE_TRACKING},
        request_revision=1,
        deadline_ns=host_time_ns() + 5_000_000_000,
        device_work_quiescent=lambda: worker.preview is None,
    )
    await resolution.cancel(resolution_operation)
    runtime.device_state.configuration_edit_terminals[edit_id] = (
        ConfigurationEditTerminal(
            operation_id=edit_id,
            source=pb.BackendContext.FromString(
                backend_context.SerializeToString(deterministic=True)
            ),
            deadline_ns=original_deadline_ns,
        )
    )

    apply_ledger = CommandLedger(
        backend_context.backend_generation,
        10_000_000_000,
        max_records=16,
        max_bytes=1_000_000,
        result_reservation_bytes=16_384,
    )
    apply_command = svc.BackendCommand(
        command_id=edit_id,
        target=backend_context,
    )
    apply_ledger.admit(
        edit_id,
        b"ApplyCameraSettings\0" + apply_command.SerializeToString(deterministic=True),
        original_deadline_ns - 1,
        work_key=edit_id,
        deadline_ns=original_deadline_ns,
    )
    apply_ledger.complete(
        edit_id,
        control.CommandAdmission(
            result=control.COMMAND_RESULT_ACCEPTED,
            command_id=edit_id,
        ).SerializeToString(deterministic=True),
        original_deadline_ns,
    )
    retained_operation = control.OperationState(
        context=control.OperationContext(command_id=edit_id),
        command="ApplyCameraSettings",
        complete=True,
        succeeded=False,
    )
    apply_ledger.complete_executor(
        edit_id,
        retained_operation.SerializeToString(deterministic=True),
        original_deadline_ns,
    )

    class _ExpiredController:
        async def report_acquisition_device_status(self, *_args, **_kwargs):
            return pb.ReportReceipt(result=pb.COMMAND_RESULT_REJECTED)

    reporter = ManualDeviceStatusReporter(
        identity=identity,
        controller=cast(Any, _ExpiredController()),
        commands=apply_ledger,
        pulse=PulseRecord(),
        clock=runtime.clock,
    )
    resolved = acquisition_camera_pb.CameraResolvedState()
    resolved.device.configured_id = "CAM-TRACK"
    resolved.device.physical_id = "physical-track"
    resolved.applied.settings.SetInParent()
    resolved.capabilities.SetInParent()
    reporter.resolve_camera(
        acquisition_camera_pb.CAMERA_ROLE_TRACKING,
        resolved,
        device_open=True,
        preview_prepared=True,
        preview_running=True,
        preview_run_id=run_id,
        cleanup_pending=True,
    )
    expired_receipt = await reporter.report(
        apply_command,
        command_name="ApplyCameraSettings",
        succeeded=False,
        deadline_ns=original_deadline_ns,
        failure="preview restart status delivery expired",
    )
    assert expired_receipt.result == pb.COMMAND_RESULT_REJECTED
    retained_status = reporter.get_report(edit_id)
    assert retained_status is not None
    assert retained_status.views.observed_monotonic_ns > original_deadline_ns
    queries = CoordinatorQueries(
        identity=identity,
        session_slot=SessionSlot(),
        workers={},
        commands=apply_ledger,
        device_status=reporter,
        current_error=lambda: None,
        clock=runtime.clock,
    )

    class _DeviceStatus:
        def reserve(self, _command):
            return None

        def resolve_camera(self, *_args, **_kwargs):
            return None

    class _ControllerBackend:
        context = backend_context

        def __init__(self) -> None:
            self.retained_queries: list[tuple[svc.RetainedResultQuery, int]] = []
            self.camera_deadlines: list[int] = []

        async def get_retained_result(self, request, *, deadline_ns):
            self.retained_queries.append((request, deadline_ns))
            result = await queries.get_retained_result(request, deadline_ns=deadline_ns)
            if query_fault == "wrong_source":
                result.backend.backend_generation = _id()
            elif query_fault == "wrong_operation":
                result.operation.context.command_id = _id()
            elif query_fault == "wrong_status_operation":
                result.acquisition_device_result.operation.command_id = _id()
            elif query_fault == "stale_generation":
                result.acquisition_device_result.views.source.backend_generation = _id()
            return result

        async def execute_camera_command(self, request, *, deadline_ns):
            self.camera_deadlines.append(deadline_ns)
            return await manual.execute(request, deadline_ns=deadline_ns)

    async def complete(*_args, **_kwargs):
        return control.CommandAdmission(result=control.COMMAND_RESULT_ACCEPTED)

    manual = ManualPreview.__new__(ManualPreview)
    manual.identity = identity
    manual.configuration = configuration
    manual.session_slot = SessionSlot()
    manual.pulse = PulseRecord()
    manual.workers = cast(
        Any,
        SimpleNamespace(workers={acquisition_camera_pb.CAMERA_ROLE_TRACKING: worker}),
    )
    manual.resolution = resolution
    manual.device_status = _DeviceStatus()
    manual.lock = asyncio.Lock()
    manual.clock = runtime.clock
    manual.windows = SimpleNamespace(close=complete)

    async def retire_and_release(_preview, *, deadline_ns):
        _ = deadline_ns

    manual.transfers = SimpleNamespace(
        retire=lambda _preview: None,
        retire_and_release=retire_and_release,
        close_retired_resource=lambda _preview: None,
    )
    manual.resources = {}
    manual.results = SimpleNamespace(complete=complete)
    controller_backend = _ControllerBackend()
    runtime.camera.backends["acquisition"] = cast(Any, controller_backend)
    runtime.camera.file_policy_loader = lambda _names: {"acquisition": policies}
    bind_ledger(runtime)
    client_id, watch_id, control_generation = _id(), _id(), _id()
    runtime.control.watches[(client_id, watch_id)] = Watch(
        client_id, watch_id, asyncio.Queue(maxsize=1), runtime.control.revision
    )
    runtime.control.owner = (client_id, watch_id, control_generation)
    tracking_view = runtime.projections.devices.tracking
    tracking_view.preview_running = False
    tracking_view.cleanup_pending = True

    request = svc.CameraCommandRequest(
        kind=svc.CAMERA_COMMAND_KIND_STOP_PREVIEW,
        camera=acquisition_camera_pb.CAMERA_ROLE_TRACKING,
        expected_configuration_revision=2,
        preview_run_id=(run_id if request_matches_reported_run else stale_run_id),
    )
    request.command.operator.command_id = _id()
    request.command.controller_generation = runtime.generation
    request.command.operator.client_id = client_id
    request.command.operator.control_generation = control_generation
    request.kind = svc.CAMERA_COMMAND_KIND_SHOW_PREVIEW
    request.preview_run_id = tracking_view.preview_run_id
    request.command.operator.command_id = _id()
    show_admission = await runtime.execute_camera_command(request)
    assert show_admission.result == pb.COMMAND_RESULT_REJECTED
    assert show_admission.failure.message == "current preview run does not match"

    request.kind = svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER
    request.command.operator.command_id = _id()
    request.preview_consumer.role = "gui"
    request.preview_consumer.generation = client_id
    runtime.lifecycle.session.phase = pb.SESSION_PHASE_RUNNING
    attach_admission = await runtime.execute_camera_command(request)
    assert attach_admission.result == pb.COMMAND_RESULT_REJECTED
    assert attach_admission.failure.message == "current preview run does not match"

    runtime.lifecycle.session.phase = pb.SESSION_PHASE_CONFIGURATION
    request.kind = svc.CAMERA_COMMAND_KIND_STOP_PREVIEW
    request.ClearField("preview_consumer")
    request.command.operator.command_id = _id()
    async with runtime.lifecycle.lock:
        exact_cleanup_selection = runtime.camera._select_locked(request)
    assert not isinstance(exact_cleanup_selection, pb.CommandAdmission)
    if query_fault == "newer_known_status":
        newer_operation_id = _id()
        newer_status = svc.AcquisitionDeviceStatusReport.FromString(
            retained_status.SerializeToString(deterministic=True)
        )
        newer_status.operation.command_id = newer_operation_id
        newer_status.result.context.command_id = newer_operation_id
        newer_status.result.succeeded = True
        newer_status.result.ClearField("failure")
        newer_status.views.state_revision = 3
        newer_status.views.observed_monotonic_ns = runtime.clock()
        runtime.device_state.configuration_edit_terminals[newer_operation_id] = (
            ConfigurationEditTerminal(
                operation_id=newer_operation_id,
                source=backend_context,
                deadline_ns=original_deadline_ns,
            )
        )
        assert (
            await runtime.report_projection("devices", newer_status, runtime.clock())
        ).result == pb.COMMAND_RESULT_ACCEPTED
        tracking_view = runtime.projections.devices.tracking
    tracking_view.preview_running = True
    tracking_view.cleanup_pending = False
    admission = await runtime.execute_camera_command(request)

    if query_fault == "newer_known_status":
        assert controller_backend.retained_queries == []
        assert admission.result == pb.COMMAND_RESULT_ACCEPTED, admission.failure.message
        assert len(controller_backend.camera_deadlines) == 1
    elif query_fault is not None:
        assert len(controller_backend.retained_queries) == 1
        query, query_deadline_ns = controller_backend.retained_queries[0]
        assert query.command_id == edit_id
        assert query.query.target == backend_context
        assert query.query.work == pb.WorkContext()
        assert query_deadline_ns > runtime.clock()
        assert admission.result == pb.COMMAND_RESULT_REJECTED
        assert admission.failure.message == (
            "owned camera cleanup status could not be reconciled"
        )
        assert (
            runtime.device_state.configuration_edit_terminals[edit_id].device_status
            is None
        )
        assert (
            runtime.projections.devices.tracking.preview_run_id
            == tracking_view.preview_run_id
        )
        assert worker.preview is not None
    else:
        assert len(controller_backend.retained_queries) == 1
        query, query_deadline_ns = controller_backend.retained_queries[0]
        assert query.command_id == edit_id
        assert query.query.target == backend_context
        assert query.query.work == pb.WorkContext()
        assert query_deadline_ns > runtime.clock()
    if query_fault is None and request_matches_reported_run:
        assert admission.result == pb.COMMAND_RESULT_ACCEPTED, admission.failure.message
        assert len(controller_backend.camera_deadlines) == 1
        assert controller_backend.camera_deadlines[0] == query_deadline_ns
    elif query_fault is None:
        assert admission.result == pb.COMMAND_RESULT_REJECTED
        assert admission.failure.message == "current preview run does not match"
        assert runtime.projections.devices.tracking.preview_run_id == run_id
        terminal = runtime.device_state.configuration_edit_terminals[edit_id]
        assert terminal.device_status == retained_status
        assert terminal.device_status_late

        request.preview_run_id = _id()
        request.command.operator.command_id = _id()
        wrong_run_admission = await runtime.execute_camera_command(request)
        assert wrong_run_admission.result == pb.COMMAND_RESULT_REJECTED
        request.preview_run_id = run_id
        request.command.operator.command_id = _id()
        admission = await runtime.execute_camera_command(request)
        assert admission.result == pb.COMMAND_RESULT_ACCEPTED, admission.failure.message
        assert len(controller_backend.retained_queries) == 1

    if admission.result == pb.COMMAND_RESULT_ACCEPTED:
        assert worker.preview is None
        assert resolution._pending is None
    for task in tuple(runtime._tasks):
        task.cancel()
    if runtime._tasks:
        await asyncio.gather(*tuple(runtime._tasks), return_exceptions=True)


@pytest.mark.parametrize("conflict", ["camera", "microcontroller", "tracking"])
async def test_owned_edit_rechecks_device_gate_after_policy_load(
    tmp_path: Path, conflict: str
) -> None:
    runtime = _runtime_with_validators(tmp_path)
    _open_preview(runtime)
    acquisition = runtime.configuration_state.current.backends.add(
        backend_name="acquisition", enabled=True
    )
    acquisition.acquisition.behavioral.enabled = True
    assert manual_camera_owned(runtime.projections, runtime.device_state)
    started = threading.Event()
    release = threading.Event()

    def slow_policies(_names):
        started.set()
        release.wait(timeout=2)
        return {"acquisition": acquisition_pb.AcquisitionFilePolicies()}

    runtime.configuration_commands.owned_edits.file_policy_loader = slow_policies
    runtime.configuration_commands.owned_edits.backend = cast(
        Any, _LiveEditAcquisition(runtime)
    )
    active = [False]
    runtime.configuration_commands.owned_edits.microcontroller_active = lambda: active[
        0
    ]
    update = asyncio.create_task(
        runtime.update_configuration(_update(runtime, experiment="race"))
    )
    await asyncio.sleep(0.1)
    if not started.is_set():
        pytest.fail((await update).failure.message)
    if conflict == "camera":
        runtime.device_state.camera_operation = cast(Any, object())
    elif conflict == "tracking":
        runtime.control.tracking_diagnostic.closed = False
    else:
        active[0] = True
    release.set()

    admission = await asyncio.wait_for(update, 1)

    assert admission.result == pb.COMMAND_RESULT_REJECTED
    assert runtime.configuration_state.current.experiment != "race"
    assert runtime.configuration_state.revision == 1


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
