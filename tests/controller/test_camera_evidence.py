"""Retained camera completion, stale evidence and owner cleanup."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import camera_pb2 as camera_pb
from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.device.owner_cleanup import (
    ManualControlCleanup,
    _release_was_confirmed,
)
from cephvr.controller.device.release_evidence import (
    camera_policy,
    finish_editing_confirmed,
    stop_preview_confirmed,
)
from cephvr.controller.device.status_retention import CameraStatusRetention
from cephvr.controller.state import CameraOperation, DeviceState
from cephvr.shared.commands import CommandCapacityError, CommandLedger
from tests.controller.support_components import _attempt, _id, _runtime, bind_ledger


def _status(
    backend: pb.BackendContext, child: str, *, succeeded: bool
) -> svc.AcquisitionDeviceStatusReport:
    status = svc.AcquisitionDeviceStatusReport()
    status.views.source.CopyFrom(backend)
    status.views.state_revision = 1
    status.views.observed_monotonic_ns = 1_000
    status.views.behavioral.preview_running = True
    status.views.behavioral.preview_run_id = _id()
    status.views.behavioral.device_open = True
    status.operation.command_id = child
    status.result.context.command_id = child
    status.result.complete = True
    status.result.succeeded = succeeded
    return status


def _start(runtime: Any, parent: str, child: str, kind: int, readback: bool) -> None:
    runtime.control_operations.operation(parent, "ExecuteCameraCommand")
    operation = CameraOperation(
        parent, child, 1, 1, kind, pb.WorkContext(), 999, readback
    )
    runtime.camera.status_retention.reserve(operation)
    runtime.device_state.camera_operation = operation


@pytest.mark.parametrize(
    "mutation", ["none", "source", "work", "command", "success", "complete", "late"]
)
async def test_manual_completion_ack_matches_retained_device_result(
    tmp_path: Path, mutation: str
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _bound_runtime(tmp_path, backend)
    parent, child = _id(), _id()
    _start(runtime, parent, child, svc.CAMERA_COMMAND_KIND_START_PREVIEW, False)
    status = _status(backend, child, succeeded=True)
    status.result.command = "execute_camera_command"
    assert (
        await runtime.report_projection("devices", status, ingress_ns=900)
    ).result == pb.COMMAND_RESULT_ACCEPTED
    report = pb.LifecycleReport(
        operation=pb.BackendOperationReport(source=backend, operation=status.result)
    )
    ingress = 901
    if mutation == "source":
        report.operation.source.backend_generation = _id()
    elif mutation == "work":
        report.operation.operation.work.session.session_id = _id()
    elif mutation == "command":
        report.operation.operation.command = "other"
    elif mutation == "success":
        report.operation.operation.succeeded = False
    elif mutation == "complete":
        report.operation.operation.complete = False
    elif mutation == "late":
        ingress = 1000
    receipt = await runtime.report_lifecycle(report, ingress)
    assert receipt.result == (
        pb.COMMAND_RESULT_ACCEPTED if mutation == "none" else pb.COMMAND_RESULT_REJECTED
    )
    assert runtime.control.operations[parent].succeeded
    assert runtime.device_state.camera_operation is None


async def test_native_preview_visibility_is_exact_observation_without_capture_change(
    tmp_path: Path,
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _bound_runtime(tmp_path, backend)
    initial = _status(backend, _id(), succeeded=True)
    initial.views.behavioral.preview_visible = True
    initial.views.behavioral.preview_visibility_revision = 1
    assert runtime.projections.accept_devices(initial)
    run_id = initial.views.behavioral.preview_run_id
    report = svc.AcquisitionDeviceStatusReport(
        views=pb.AcquisitionDeviceViews(source=backend),
        preview_visibility=svc.CameraPreviewVisibility(
            camera=1,
            preview_run_id=run_id,
            revision=2,
            visible=False,
            observed_monotonic_ns=1_001,
        ),
    )
    receipt = await runtime.report_projection("devices", report)
    assert receipt.result == pb.COMMAND_RESULT_ACCEPTED
    view = runtime.projections.devices.behavioral
    assert not view.preview_visible
    assert view.preview_running and view.device_open and view.preview_run_id == run_id
    assert runtime.device_state.camera_operation is None
    assert runtime.projections.accept_preview_visibility(report) is False
    report.preview_visibility.visible = True
    assert (
        await runtime.report_projection("devices", report)
    ).result == pb.COMMAND_RESULT_REJECTED
    report.preview_visibility.revision = 3
    report.preview_visibility.preview_run_id = _id()
    assert (
        await runtime.report_projection("devices", report)
    ).result == pb.COMMAND_RESULT_REJECTED
    report.preview_visibility.preview_run_id = run_id
    report.views.source.backend_generation = _id()
    assert (
        await runtime.report_projection("devices", report)
    ).result == pb.COMMAND_RESULT_REJECTED
    # A later command snapshot cannot resurrect visibility from before X closure.
    initial.views.state_revision = 2
    assert runtime.projections.accept_devices(initial)
    assert not runtime.projections.devices.behavioral.preview_visible
    assert runtime.projections.devices.behavioral.preview_visibility_revision == 2
    report.views.source.CopyFrom(backend)
    report.preview_visibility.revision = 1
    assert not runtime.projections.accept_preview_visibility(report)


@pytest.mark.parametrize("show", [False, True])
@pytest.mark.parametrize("confirmed", [False, True])
async def test_preview_window_completion_requires_backend_visibility(
    tmp_path: Path, show: bool, confirmed: bool
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _bound_runtime(tmp_path, backend)
    parent, child = _id(), _id()
    kind = (
        svc.CAMERA_COMMAND_KIND_SHOW_PREVIEW
        if show
        else svc.CAMERA_COMMAND_KIND_HIDE_PREVIEW
    )
    _start(runtime, parent, child, kind, False)
    status = _status(backend, child, succeeded=True)
    operation = runtime.device_state.camera_operation
    operation.deadline_ns = 10_000
    operation.preview_run_id = status.views.behavioral.preview_run_id
    status.views.behavioral.preview_visible = show if confirmed else not show
    receipt = await runtime.report_projection("devices", status, 1_001)
    assert receipt.result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime.control.operations[parent].succeeded == confirmed
    assert runtime.device_state.camera_operation is None


def test_initial_camera_warning_scope_matches_loaded_configuration(
    tmp_path: Path,
) -> None:
    from cephvr.acquisition.v1 import messages_pb2 as acq
    from cephvr.acquisition.worker.warnings import (
        WarningOccurrence,
        WorkerWarningLedger,
    )
    from cephvr.controller.projections import ProjectionError

    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _bound_runtime(tmp_path, backend)
    report = svc.AcquisitionWarningReport(source=backend)
    producer = acq.WorkerContext(
        worker=pb.ProcessIdentity(
            role="acquisition_behavioral_worker", generation=_id()
        ),
        camera=camera.CAMERA_ROLE_BEHAVIORAL,
    )
    warnings = WorkerWarningLedger(producer)
    warnings.begin_scope(
        pb.WorkContext(), configuration_revision=runtime.configuration_state.revision
    )
    report.view.CopyFrom(warnings.observe(WarningOccurrence("INVALID_IMAGE", 1)))
    assert runtime.projections.accept_warnings(report)
    report.view.configuration_revision += 1
    with pytest.raises(ProjectionError, match="scope/revision"):
        runtime.projections.accept_warnings(report)


@pytest.mark.parametrize("version", [2, 3])
async def test_microcontroller_status_completes_exact_operator_operation(
    tmp_path: Path,
    version: int,
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _bound_runtime(tmp_path, backend)
    parent, child = _id(), _id()
    ledger = runtime.camera_status_retention.ledger
    assert ledger is not None
    ledger.admit(parent, b"mcu-command", 1, work_key=parent)
    runtime.control_operations.operation(parent, "ExecuteMicrocontrollerCommand")
    operation = CameraOperation(
        parent,
        child,
        1,
        0,
        svc.MICROCONTROLLER_COMMAND_KIND_CONNECT,
        pb.WorkContext(),
        999,
        False,
        is_microcontroller=True,
    )
    runtime.camera_status_retention.reserve(operation)
    runtime.device_state.camera_operation = operation
    status = svc.AcquisitionDeviceStatusReport()
    status.views.source.CopyFrom(backend)
    status.views.state_revision = 1
    status.views.observed_monotonic_ns = 100
    status.views.pulses.capabilities.protocol_version = version
    status.views.pulses.state.behavioral.running = False
    status.views.pulses.state.tracking.running = False
    status.operation.command_id = child
    status.result.context.command_id = child
    status.result.complete = True
    status.result.succeeded = True

    receipt = await runtime.report_projection("devices", status, ingress_ns=900)

    assert receipt.result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime.control.operations[parent].succeeded == (version == 3)
    assert runtime.device_state.camera_operation is None
    assert runtime.projections.devices.pulses.capabilities.protocol_version == version


async def test_microcontroller_failure_preserves_firmware_rejection(
    tmp_path: Path,
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _bound_runtime(tmp_path, backend)
    parent, child = _id(), _id()
    ledger = runtime.camera_status_retention.ledger
    ledger.admit(parent, b"mcu-command", 1, work_key=parent)
    runtime.control_operations.operation(parent, "ExecuteMicrocontrollerCommand")
    operation = CameraOperation(
        parent,
        child,
        1,
        0,
        svc.MICROCONTROLLER_COMMAND_KIND_START,
        pb.WorkContext(),
        999,
        False,
        is_microcontroller=True,
    )
    runtime.camera_status_retention.reserve(operation)
    runtime.device_state.camera_operation = operation
    status = _status(backend, child, succeeded=False)
    status.result.failure.code = "ACQUISITION_OPERATION_FAILED"
    status.result.failure.message = "MCU rejected CONFIGURE: UNSUPPORTED_FREQUENCY"
    receipt = await runtime.report_projection("devices", status, ingress_ns=900)
    assert receipt.result == pb.COMMAND_RESULT_ACCEPTED
    assert not runtime.control.operations[parent].succeeded
    assert (
        runtime.control.operations[parent].failure.message
        == status.result.failure.message
    )


@pytest.mark.parametrize("internal", [False, True])
@pytest.mark.parametrize("succeeded", [False, True])
async def test_terminal_camera_report_retires_slot_but_retains_exact_evidence(
    tmp_path: Path, internal: bool, succeeded: bool
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _bound_runtime(tmp_path, backend)
    parent, child = _id(), _id()
    ledger = runtime.camera_status_retention.ledger
    assert ledger is not None
    if not internal:
        ledger.admit(parent, b"cmd", 1, work_key=parent)
    _start(runtime, parent, child, svc.CAMERA_COMMAND_KIND_START_PREVIEW, False)
    operation = runtime.device_state.camera_operation
    assert operation is not None
    runtime.device_state.manual_effects_admitted = True
    status = _status(backend, child, succeeded=succeeded)

    receipt = await runtime.report_projection("devices", status, ingress_ns=900)

    assert receipt.result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime.control.operations[parent].succeeded == succeeded
    assert runtime.device_state.camera_operation is None
    assert runtime.device_state.camera_operation_changed.is_set()
    assert runtime.device_state.manual_effects_admitted
    assert runtime.camera_status_retention.find(child) is operation
    assert operation.final_status == status
    record = ledger.get(child if internal else parent)
    assert record is not None
    # Public completion belongs to RPC admission; synthetic cleanup has no RPC owner.
    assert (record.completed_ns is not None) == internal
    assert (record.finalized_ns is not None) == internal


async def test_deadline_with_retained_terminal_but_no_confirmation_frees_slot(
    tmp_path: Path,
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _runtime(tmp_path, backend)
    bind_ledger(runtime)
    parent, child = _id(), _id()
    _start(runtime, parent, child, svc.CAMERA_COMMAND_KIND_START_PREVIEW, True)
    status = _status(backend, child, succeeded=True)
    receipt = await runtime.report_projection("devices", status, ingress_ns=900)
    assert receipt.result == pb.COMMAND_RESULT_ACCEPTED
    # Terminal report arrived but readback confirmation never did.
    assert runtime.device_state.camera_operation is not None

    await runtime.camera._camera_timeout(child, 999)

    assert runtime.device_state.camera_operation is None
    state = runtime.control.operations[parent]
    assert state.complete and not state.succeeded
    dup = await runtime.report_projection("devices", status, ingress_ns=1_100)
    assert dup.result == pb.COMMAND_RESULT_ACCEPTED
    assert not runtime.control.operations[parent].succeeded


async def test_deadline_without_terminal_adopts_retained_result(
    tmp_path: Path,
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _runtime(tmp_path, backend)
    bind_ledger(runtime)
    parent, child = _id(), _id()
    _start(runtime, parent, child, svc.CAMERA_COMMAND_KIND_START_PREVIEW, False)
    status = _status(backend, child, succeeded=True)
    queries: list[svc.RetainedResultQuery] = []

    async def retained(request: Any, *, deadline_ns: int) -> svc.RetainedResult:
        queries.append(request)
        return svc.RetainedResult(
            found=True,
            backend=backend,
            work=pb.WorkContext(),
            acquisition_device_result=status,
        )

    runtime.camera.backends["acquisition"].get_retained_result = retained  # type: ignore[attr-defined]

    await runtime.camera._camera_timeout(child, 999)

    assert len(queries) == 1 and queries[0].command_id == child
    assert runtime.device_state.camera_operation is None
    assert not runtime.control.operations[parent].succeeded
    assert runtime.projections.devices is not None
    assert not any("unconfirmed" in w.message for w in runtime.control.warnings)
    operation = runtime.camera_status_retention.find(child)
    assert operation is not None and operation.final_status == status


async def test_deadline_without_result_frees_unconfirmed_with_warning(
    tmp_path: Path,
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _runtime(tmp_path, backend)
    bind_ledger(runtime)
    parent, child = _id(), _id()
    _start(runtime, parent, child, svc.CAMERA_COMMAND_KIND_START_PREVIEW, False)
    runtime.device_state.manual_effects_admitted = True

    async def retained(request: Any, *, deadline_ns: int) -> svc.RetainedResult:
        return svc.RetainedResult(found=False)

    runtime.camera.backends["acquisition"].get_retained_result = retained  # type: ignore[attr-defined]

    await runtime.camera._camera_timeout(child, 999)

    assert runtime.device_state.camera_operation is None
    assert runtime.device_state.manual_effects_admitted
    assert not runtime.control.operations[parent].succeeded
    assert any("unconfirmed" in w.message for w in runtime.control.warnings)
    # A later exact terminal report is retained without reviving success.
    late = await runtime.report_projection(
        "devices", _status(backend, child, succeeded=True), ingress_ns=2_000
    )
    assert late.result == pb.COMMAND_RESULT_ACCEPTED
    assert not runtime.control.operations[parent].succeeded


BEHAVIORAL = camera_pb.CAMERA_ROLE_BEHAVIORAL


def _camera_status(
    backend: pb.BackendContext,
    child: str,
    revision: int,
    *,
    running: bool = True,
    open_: bool = True,
) -> svc.AcquisitionDeviceStatusReport:
    status = svc.AcquisitionDeviceStatusReport()
    status.views.source.CopyFrom(backend)
    status.views.state_revision = revision
    status.views.observed_monotonic_ns = 1_000 + revision
    status.views.behavioral.preview_running = running
    status.views.behavioral.device_open = open_
    if running:
        status.views.behavioral.preview_run_id = _id()
    status.operation.command_id = child
    status.result.context.command_id = child
    status.result.complete = True
    status.result.succeeded = True
    return status


def _bound_runtime(tmp_path: Path, backend: pb.BackendContext) -> Any:
    runtime = _runtime(tmp_path, backend)
    runtime.bind_camera_status_retention(
        CommandLedger(
            runtime.generation,
            10_000_000_000,
            max_records=16,
            max_bytes=1_000_000,
            result_reservation_bytes=4096,
        )
    )
    return runtime


def _retained_without_status(runtime: Any, deadline_ns: int = 999) -> CameraOperation:
    parent, child = _id(), _id()
    runtime.camera_status_retention.ledger.admit(parent, b"cmd", 1, work_key=parent)
    operation = CameraOperation(
        parent,
        child,
        1,
        BEHAVIORAL,
        svc.CAMERA_COMMAND_KIND_START_PREVIEW,
        pb.WorkContext(),
        deadline_ns,
        False,
    )
    runtime.camera_status_retention.reserve(operation)
    return operation  # the slot is free: device.camera_operation stays None


async def test_first_exact_report_for_slot_freed_operation_is_retained(
    tmp_path: Path,
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _bound_runtime(tmp_path, backend)
    operation = _retained_without_status(runtime)
    status = _camera_status(backend, operation.child_id, 1)

    receipt = await runtime.report_projection("devices", status, ingress_ns=5_000)

    assert receipt.result == pb.COMMAND_RESULT_ACCEPTED
    assert operation.final_status == status
    assert runtime.projections.devices is not None
    assert runtime.projections.devices.state_revision == 1
    retry = await runtime.report_projection("devices", status, ingress_ns=5_001)
    assert retry.result == pb.COMMAND_RESULT_ACCEPTED
    changed = svc.AcquisitionDeviceStatusReport.FromString(status.SerializeToString())
    changed.views.observed_monotonic_ns += 1
    rejected = await runtime.report_projection("devices", changed, ingress_ns=5_002)
    assert rejected.result == pb.COMMAND_RESULT_REJECTED


async def test_late_terminal_report_never_replaces_a_newer_current_view(
    tmp_path: Path,
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _bound_runtime(tmp_path, backend)
    newer = _camera_status(backend, _id(), 5, running=False, open_=False)
    assert runtime.projections.accept_devices(newer)
    operation = _retained_without_status(runtime)
    late = _camera_status(backend, operation.child_id, 2)

    receipt = await runtime.report_projection("devices", late, ingress_ns=5_000)

    assert receipt.result == pb.COMMAND_RESULT_ACCEPTED
    assert operation.final_status == late  # retained as evidence
    assert runtime.projections.devices is not None
    assert runtime.projections.devices.state_revision == 5
    assert not runtime.projections.devices.behavioral.preview_running


def test_late_exact_stop_success_confirms_owner_release() -> None:
    run_id = _id()
    operation = CameraOperation(
        _id(),
        _id(),
        1,
        BEHAVIORAL,
        svc.CAMERA_COMMAND_KIND_STOP_PREVIEW,
        pb.WorkContext(),
        100,
        False,
        preview_run_id=run_id,
    )
    operation.timed_out = True
    status = svc.AcquisitionDeviceStatusReport()
    status.result.succeeded = True
    view = status.views.behavioral
    view.device_open = False
    view.preview_running = False
    view.cleanup_pending = False
    view.preview_run_id = ""
    operation.final_status = status
    assert _release_was_confirmed(operation)
    status.result.succeeded = False
    assert not _release_was_confirmed(operation)


def test_shared_release_predicates_require_a_closed_device() -> None:
    view = pb.CameraDeviceView(
        device_open=True, preview_running=False, cleanup_pending=False
    )
    view.preview_run_id = ""
    assert not stop_preview_confirmed(view, "run")
    view.device_open = False
    assert stop_preview_confirmed(view, "run")
    assert not stop_preview_confirmed(view, "")
    open_editing = pb.CameraDeviceView(
        device_open=True, preview_running=True, cleanup_pending=False
    )
    assert finish_editing_confirmed(open_editing, require_closed=False)
    assert not finish_editing_confirmed(open_editing, require_closed=True)
    open_editing.cleanup_pending = True
    assert not finish_editing_confirmed(open_editing, require_closed=False)


async def test_owner_cleanup_accepts_all_explicitly_closed_camera_roles(
    tmp_path: Path,
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _bound_runtime(tmp_path, backend)
    views = pb.AcquisitionDeviceViews(source=backend)
    for role in ("behavioral", "tracking", "eye_tracking"):
        getattr(views, role).CopyFrom(
            pb.CameraDeviceView(
                device_open=False,
                preview_running=False,
                preview_prepared=False,
                cleanup_pending=False,
            )
        )
    runtime.projections.devices = views
    runtime.device_state.manual_effects_admitted = True
    runtime.lifecycle.manual_control_cleanup_pending = True
    cleanup = cast(ManualControlCleanup, runtime.leases.owner_lost.__self__)
    await cleanup.run()
    assert not runtime.lifecycle.manual_control_cleanup_pending
    assert not runtime.device_state.manual_effects_admitted
    assert all(state.succeeded for state in runtime.control.operations.values())


def test_camera_policy_must_be_unique() -> None:
    from cephvr.acquisition.v1 import runtime_pb2 as acquisition_pb

    policies = acquisition_pb.AcquisitionFilePolicies()
    with pytest.raises(ValueError):
        camera_policy(policies, BEHAVIORAL)
    policies.cameras.add(camera=BEHAVIORAL)
    assert camera_policy(policies, BEHAVIORAL).camera == BEHAVIORAL
    policies.cameras.add(camera=BEHAVIORAL)
    with pytest.raises(ValueError):
        camera_policy(policies, BEHAVIORAL)


def test_owner_loss_retention_uses_the_safety_reserve() -> None:
    ledger = CommandLedger(
        _id(),
        10_000,
        max_records=4,
        max_bytes=1_000_000,
        result_reservation_bytes=1024,
        safety_reserve_records=2,
    )
    for _ in range(2):
        parent = _id()
        ledger.admit(parent, b"ordinary", 1, work_key=parent)
    device = DeviceState()
    retention = CameraStatusRetention(device, clock=lambda: 1)
    retention.bind_ledger(ledger)
    parent = _id()
    with pytest.raises(CommandCapacityError):
        ledger.admit(parent, b"ordinary", 1, work_key=parent)
    internal = CameraOperation(
        _id(), _id(), 1, BEHAVIORAL, 1, pb.WorkContext(), 100, False
    )
    retention.reserve(internal)  # no public record: safety/priority reserve
    assert internal.internal_retention


async def test_owner_cleanup_failure_retries_with_warning_and_no_interruption(
    tmp_path: Path,
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _runtime(tmp_path, backend)
    attempt = _attempt(runtime, tmp_path, {})
    runtime.lifecycle.attempt = attempt
    interrupts: list[str] = []

    async def record(_attempt: Any, reason: str) -> None:
        interrupts.append(reason)

    runtime.interruption.interrupt = record  # type: ignore[method-assign]
    cleanup = cast(ManualControlCleanup, runtime.leases.owner_lost.__self__)  # type: ignore[union-attr]
    cleanup.retry_delay_s = 0.01
    calls = 0
    warned = False

    async def flaky() -> None:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("camera release unconfirmed")
        runtime.lifecycle.manual_control_cleanup_pending = False
        runtime.lifecycle.manual_control_cleanup_task = None

    cleanup.run = flaky  # type: ignore[method-assign]
    await cleanup.request()
    assert runtime.lifecycle.manual_control_cleanup_pending
    deadline = asyncio.get_running_loop().time() + 2
    while runtime.lifecycle.manual_control_cleanup_pending:
        warned = warned or any(
            item.component == "manual_camera_cleanup"
            for item in runtime.control.warnings
        )
        assert asyncio.get_running_loop().time() < deadline
        await asyncio.sleep(0.005)
    await asyncio.sleep(0.05)

    assert calls == 3
    assert warned
    assert not interrupts
    assert not any(
        item.component == "manual_camera_cleanup" for item in runtime.control.warnings
    )


def test_stopped_preview_is_not_released_while_camera_remains_open() -> None:
    run_id = str(uuid4())
    operation = CameraOperation(
        operator_id=str(uuid4()),
        child_id=str(uuid4()),
        revision=1,
        camera=camera.CAMERA_ROLE_BEHAVIORAL,
        kind=svc.CAMERA_COMMAND_KIND_STOP_PREVIEW,
        work=pb.WorkContext(),
        deadline_ns=100,
        readback_required=False,
        preview_run_id=run_id,
    )
    status = svc.AcquisitionDeviceStatusReport()
    status.result.succeeded = True
    view = status.views.behavioral
    view.device_open = True
    view.preview_running = False
    view.cleanup_pending = False
    operation.final_status = status
    assert not _release_was_confirmed(operation)

    view.device_open = False
    assert not _release_was_confirmed(operation)  # stopped run not yet reported

    view.preview_run_id = ""
    assert _release_was_confirmed(operation)


@pytest.mark.parametrize("cleanup_pending", [False, True])
async def test_connection_check_requires_confirmed_cleanup(
    tmp_path: Path,
    cleanup_pending: bool,
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _bound_runtime(tmp_path, backend)
    parent, child = _id(), _id()
    ledger = runtime.camera_status_retention.ledger
    assert ledger is not None
    ledger.admit(parent, b"connection-check", 1, work_key=parent)
    _start(runtime, parent, child, svc.CAMERA_COMMAND_KIND_TEST_CONNECTION, False)
    status = _status(backend, child, succeeded=True)
    status.views.behavioral.Clear()
    status.views.behavioral.device_open = False
    status.views.behavioral.cleanup_pending = cleanup_pending
    receipt = await runtime.report_projection("devices", status, ingress_ns=900)
    assert receipt.result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime.control.operations[parent].succeeded is not cleanup_pending
    if cleanup_pending:
        assert (
            "prior cleanup remains unresolved"
            in runtime.control.operations[parent].failure.message
        )


@pytest.mark.parametrize("stop", [False, True])
async def test_acquisition_reporter_completes_preview_with_idle_other_camera(
    tmp_path: Path, stop: bool
) -> None:
    from cephvr.acquisition.coordinator.manual_device_status import (
        ManualDeviceStatusReporter,
    )
    from cephvr.acquisition.ports import ControllerPort
    from cephvr.acquisition.state import CoordinatorIdentity, PulseRecord

    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _bound_runtime(tmp_path, backend)
    parent, child, run = _id(), _id(), _id()
    ledger = runtime.camera_status_retention.ledger
    assert ledger is not None
    ledger.admit(parent, b"preview", 1, work_key=parent)
    _start(
        runtime,
        parent,
        child,
        svc.CAMERA_COMMAND_KIND_STOP_PREVIEW
        if stop
        else svc.CAMERA_COMMAND_KIND_START_PREVIEW,
        False,
    )
    operation = runtime.device_state.camera_operation
    operation.preview_run_id = run

    class Controller:
        async def report_acquisition_device_status(
            self, report: svc.AcquisitionDeviceStatusReport, *, deadline_ns: int
        ) -> pb.ReportReceipt:
            return await runtime.report_projection("devices", report, ingress_ns=900)

    commands = CommandLedger(
        _id(),
        10_000,
        max_records=16,
        max_bytes=1_000_000,
        result_reservation_bytes=4096,
    )
    commands.admit(child, b"preview", 1, work_key=child)
    reporter = ManualDeviceStatusReporter(
        identity=CoordinatorIdentity(
            backend,
            pb.ProcessIdentity(),
            pb.ProcessIdentity(),
            pb.ProcessIdentity(),
            pb.ProcessIdentity(),
        ),
        controller=cast(ControllerPort, Controller()),
        commands=commands,
        pulse=PulseRecord(),
        clock=lambda: 100,
    )
    reporter.update_camera_state(
        camera.CAMERA_ROLE_BEHAVIORAL,
        device_open=not stop,
        preview_prepared=not stop,
        preview_running=not stop,
        preview_run_id="" if stop else run,
    )
    receipt = await reporter.report(
        svc.BackendCommand(command_id=child),
        command_name="stop_preview" if stop else "start_preview",
        succeeded=True,
        deadline_ns=999,
    )
    assert receipt.result == pb.COMMAND_RESULT_ACCEPTED, receipt.failure.message
    assert runtime.control.operations[parent].succeeded
    assert runtime.device_state.camera_operation is None
    assert runtime.projections.devices.tracking.HasField("preview_run_id")
    assert runtime.projections.devices.tracking.preview_run_id == ""


@pytest.mark.parametrize("run_id", ["", "invalid"])
@pytest.mark.parametrize("prepared", [False, True])
def test_active_preview_requires_valid_run_identity(
    tmp_path: Path, run_id: str, prepared: bool
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _bound_runtime(tmp_path, backend)
    status = _status(backend, _id(), succeeded=True)
    status.views.behavioral.preview_running = not prepared
    status.views.behavioral.preview_prepared = prepared
    status.views.behavioral.preview_run_id = run_id
    with pytest.raises(ValueError):
        runtime.projections.validate_devices(status)


@pytest.mark.parametrize("retained_failure", [False, True])
async def test_async_viewer_rejection_completes_operator_without_consumer_confirmation(
    tmp_path: Path,
    retained_failure: bool,
) -> None:
    from types import SimpleNamespace

    from cephvr.acquisition.coordinator.manual_device_status import (
        ManualDeviceStatusReporter,
    )
    from cephvr.acquisition.coordinator.manual_operation_results import (
        ManualOperationResults,
    )
    from cephvr.acquisition.ports import ControllerPort
    from cephvr.acquisition.runtime import AcquisitionCoordinatorRuntime
    from cephvr.acquisition.state import CoordinatorIdentity, PulseRecord

    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    controller = _bound_runtime(tmp_path, backend)
    parent, child = _id(), _id()
    ledger = controller.camera_status_retention.ledger
    assert ledger is not None
    ledger.admit(parent, b"viewer", 1, work_key=parent)
    _start(
        controller, parent, child, svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER, False
    )

    class Controller:
        async def report_acquisition_device_status(self, report, *, deadline_ns):
            return await controller.report_projection("devices", report, ingress_ns=900)

        async def report_lifecycle(self, report, *, deadline_ns):
            return pb.ReportReceipt(result=pb.COMMAND_RESULT_REJECTED)

    identity = CoordinatorIdentity(
        backend,
        pb.ProcessIdentity(),
        pb.ProcessIdentity(),
        pb.ProcessIdentity(),
        pb.ProcessIdentity(),
    )
    commands = CommandLedger(
        _id(),
        10_000,
        max_records=16,
        max_bytes=1_000_000,
        result_reservation_bytes=4096,
    )
    commands.admit(child, b"viewer", 1, work_key=child)
    peer = cast(ControllerPort, Controller())
    reporter = ManualDeviceStatusReporter(
        identity=identity,
        controller=peer,
        commands=commands,
        pulse=PulseRecord(),
        clock=lambda: 100,
    )
    # Failure of a viewer leaves the independently running capture intact.
    run_id = _id()
    reporter.update_camera_state(
        1,
        device_open=True,
        preview_running=True,
        preview_prepared=True,
        preview_run_id=run_id,
    )
    results = ManualOperationResults(
        identity=identity, controller=peer, device_status=reporter
    )
    command = svc.BackendCommand(command_id=child)
    original = None
    if retained_failure:
        await results.report_failure(
            command,
            command_name="attach_preview_viewer",
            deadline_ns=999,
            failure="viewer transfer rejected",
        )
        original = reporter.get_report(child).SerializeToString(deterministic=True)
    coordinator = AcquisitionCoordinatorRuntime.__new__(AcquisitionCoordinatorRuntime)
    coordinator.clock = lambda: 100
    coordinator.controller = peer
    coordinator.coordinator_identity = identity
    coordinator.manual_devices = SimpleNamespace(results=results)
    outcome = pb.OperationState(
        context=pb.OperationContext(command_id=child),
        complete=True,
        succeeded=False,
        failure=pb.Failure(code="PREVIEW_VIEWER", message="viewer transfer rejected"),
    )

    await coordinator.report_dispatch_failure(
        "ExecuteCameraCommand", command, outcome, 999
    )

    result = controller.control.operations[parent]
    assert result.complete and not result.succeeded
    assert "viewer transfer rejected" in result.failure.message
    assert controller.device_state.camera_operation is None
    assert controller.projections.devices.behavioral.preview_running
    assert controller.projections.devices.behavioral.preview_run_id == run_id
    if original is not None:
        assert (
            reporter.get_report(child).SerializeToString(deterministic=True) == original
        )
