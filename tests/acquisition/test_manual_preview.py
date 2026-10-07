"""Preview restart ordering and exact viewer-transfer release."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from cephvr.acquisition.coordinator import manual_preview_pulse as pulse_module
from cephvr.acquisition.coordinator import manual_preview_start as start_module
from cephvr.acquisition.coordinator.manual_device_status import (
    ManualDeviceStatusReporter,
)
from cephvr.acquisition.coordinator.manual_preview_pulse import (
    ManualPreviewPulseLifecycle,
)
from cephvr.acquisition.coordinator.manual_preview_setup import (
    build_preview_payload,
    new_worker_preview,
)
from cephvr.acquisition.coordinator.manual_preview_start import ManualPreviewStart
from cephvr.acquisition.coordinator.manual_preview_transfer import (
    ManualPreviewTransferOwner,
)
from cephvr.acquisition.ports import (
    ControllerPort,
    ResourcePort,
    SerialOwnerPort,
    WorkerPort,
)
from cephvr.acquisition.state import (
    ChildOperation,
    ConfigurationRecord,
    CoordinatorIdentity,
    LaunchRecord,
    PausedPreview,
    PulseRecord,
    ResourceRecord,
    WorkerPreview,
    WorkerRecord,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import runtime_pb2 as runtime
from cephvr.acquisition.worker.function_scopes import validate_camera_function_scopes
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.controller.device.tracking_diagnostic import TrackingDiagnosticController
from cephvr.platform.windows.resource_ledger import NativeResourceLedger
from cephvr.shared.commands import CommandLedger


@pytest.mark.parametrize(
    "role", [camera.CAMERA_ROLE_BEHAVIORAL, camera.CAMERA_ROLE_TRACKING]
)
def test_manual_preview_declares_exact_non_saving_capture_scope(role: int) -> None:
    owner = control.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    worker = control.ProcessIdentity(role="camera_worker", generation=str(uuid4()))
    attachment = acq.FrameBufferAttachment(
        buffer=acq.FrameBufferDescriptor(owner=owner, producer=worker, camera=role)
    )
    payload = build_preview_payload(
        camera.CameraSessionSettings(sdk_buffer_count=10),
        runtime.CameraFilePolicy(frame_silence_timeout_ns=1_000_000_000),
        camera.CameraResolvedState(),
        attachment,
    )
    scopes = validate_camera_function_scopes(
        payload, acq.WorkerContext(owner=owner, worker=worker, camera=role)
    )
    assert len(scopes) == 1
    assert not payload.HasField("recording")
    assert tuple(scopes[0].affected_closure_resource_ids) == (scopes[0].resource_id,)


class _TransferOwner:
    def __init__(self) -> None:
        self.retired = asyncio.Event()

    def retire(self, preview: WorkerPreview) -> None:
        _ = preview
        self.retired.set()

    def close_retired_resource(self, preview: WorkerPreview) -> None:
        _ = preview


@pytest.mark.asyncio
@pytest.mark.parametrize("succeeded", [False, True])
async def test_preview_resolution_preserves_sdk_failure_and_requires_evidence(
    monkeypatch: pytest.MonkeyPatch, succeeded: bool
) -> None:
    class Status:
        pending = False

        def begin_device_access(self, role: int, serial: str) -> None:
            self.pending = True

    status = Status()

    class Resolution:
        async def begin(self, *args: object, **kwargs: object) -> None:
            pass

    class Port:
        async def resolve_camera_configuration(
            self, *args: object, **kwargs: object
        ) -> control.CommandAdmission:
            assert status.pending
            return control.CommandAdmission(result=control.COMMAND_RESULT_ACCEPTED)

    child = ChildOperation(
        command_id=str(uuid4()),
        camera=camera.CAMERA_ROLE_BEHAVIORAL,
        work=control.WorkContext(),
        parent_operation=control.OperationContext(),
        kind="resolve_camera",
    )
    monkeypatch.setattr(
        start_module,
        "retain_worker_command",
        lambda *a, **k: (acq.WorkerCommand(), child, Port()),
    )

    async def completed(*args: object, **kwargs: object) -> control.OperationState:
        result = control.OperationState(complete=True, succeeded=succeeded)
        if not succeeded:
            result.failure.message = "SDK ROI Width violates current limits"
        return result

    monkeypatch.setattr(start_module, "wait_child_operation", completed)
    flow = object.__new__(ManualPreviewStart)
    flow.resolution = cast(start_module.ConfigurationResolution, Resolution())
    flow.device_status = cast(ManualDeviceStatusReporter, status)
    flow.lock = asyncio.Lock()
    flow.clock = lambda: 1
    expected = "successful SDK evidence" if succeeded else "SDK ROI Width"
    with pytest.raises(RuntimeError, match=expected):
        await flow._resolve_camera_and_pulses(
            wire.AcquisitionCameraCommand(configuration_revision=1),
            cast(WorkerRecord, object()),
            camera.CameraSessionSettings(),
            runtime.CameraFilePolicy(),
            (),
            100,
        )
    assert status.pending


class _Status:
    def resolve_camera(self, *args: object, **kwargs: object) -> None:
        _ = args, kwargs


class _Port:
    def __init__(self, preview: WorkerPreview) -> None:
        self.preview = preview

    async def stop_preview(
        self, request: acq.WorkerStopPreview, *, deadline_ns: int
    ) -> control.CommandAdmission:
        _ = request, deadline_ns
        self.preview.stopped_event.set()
        self.preview.cleanup_event.set()
        return control.CommandAdmission(result=control.COMMAND_RESULT_ACCEPTED)


class _PulseLifecycle:
    def __init__(self, events: list[object]) -> None:
        self.events = events

    async def pause_for_pulse_change(
        self, roles: tuple[int, ...], *, deadline_ns: int
    ) -> tuple[PausedPreview, ...]:
        _ = deadline_ns
        self.events.append(("pause_existing", roles))
        return (PausedPreview(roles[0], camera.CameraResolvedState(), 8),)

    async def resume_after_pulse_change(
        self, token: tuple[PausedPreview, ...], *, deadline_ns: int
    ) -> None:
        _ = token, deadline_ns
        self.events.append("resume_existing")


class _StartFlow(ManualPreviewStart):
    def __init__(self, events: list[object], lifecycle: _PulseLifecycle) -> None:
        self.events = events
        self.pulse_lifecycle = lifecycle
        self.device_status = cast(ManualDeviceStatusReporter, _Status())

    async def _resolve_camera_and_pulses(
        self,
        request: wire.AcquisitionCameraCommand,
        worker: WorkerRecord,
        setting: camera.CameraSessionSettings,
        policy: runtime.CameraFilePolicy,
        external_roles: tuple[int, ...],
        deadline_ns: int,
    ) -> tuple[camera.CameraResolvedState, int]:
        _ = request, worker, setting, policy, external_roles, deadline_ns
        self.events.append("configure_and_confirm")
        return camera.CameraResolvedState(), 4

    async def _prepare_preview_run(
        self,
        request: wire.AcquisitionCameraCommand,
        worker: WorkerRecord,
        setting: camera.CameraSessionSettings,
        policy: runtime.CameraFilePolicy,
        resolved: camera.CameraResolvedState,
        run_id: str,
        configuration_revision: int,
        deadline_ns: int,
    ) -> WorkerPreview:
        _ = (
            request,
            worker,
            setting,
            policy,
            resolved,
            run_id,
            configuration_revision,
            deadline_ns,
        )
        self.events.append("prepare_new_role")
        return WorkerPreview(run_id="run-2", configuration_revision=4)

    async def _start_prepared_preview(
        self,
        request: wire.AcquisitionCameraCommand,
        worker: WorkerRecord,
        preview: WorkerPreview,
        external_roles: tuple[int, ...],
        deadline_ns: int,
    ) -> None:
        _ = request, worker, preview, deadline_ns
        self.events.append(("start_new_role", external_roles))


@pytest.mark.asyncio
async def test_second_external_preview_pauses_existing_role_before_configuration() -> (
    None
):
    events: list[object] = []
    flow = _StartFlow(events, _PulseLifecycle(events))
    request = wire.AcquisitionCameraCommand(camera=camera.CAMERA_ROLE_TRACKING)

    await flow.start(
        request,
        cast(WorkerRecord, object()),
        camera.CameraSessionSettings(),
        runtime.CameraFilePolicy(),
        (camera.CAMERA_ROLE_BEHAVIORAL, camera.CAMERA_ROLE_TRACKING),
        str(uuid4()),
        100,
    )

    assert events == [
        ("pause_existing", (camera.CAMERA_ROLE_BEHAVIORAL,)),
        "configure_and_confirm",
        "resume_existing",
        "prepare_new_role",
        ("start_new_role", (camera.CAMERA_ROLE_TRACKING,)),
    ]


@pytest.mark.asyncio
async def test_pause_with_attached_viewer_waits_for_exact_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview = WorkerPreview(
        run_id=str(uuid4()),
        configuration_revision=2,
        allocation_id=str(uuid4()),
        resolved_camera=camera.CameraResolvedState(),
        viewer=control.ProcessIdentity(role="preview_viewer", generation=str(uuid4())),
        viewer_transfer_id=str(uuid4()),
        started=True,
    )
    context = acq.WorkerContext(
        worker=control.ProcessIdentity(
            role="acquisition_behavioral_worker", generation=str(uuid4())
        ),
        owner=control.ProcessIdentity(role="acquisition", generation=str(uuid4())),
        camera=camera.CAMERA_ROLE_BEHAVIORAL,
    )
    port = _Port(preview)
    worker = WorkerRecord(
        context=context,
        port=cast(WorkerPort, port),
        launch=LaunchRecord(
            command_id=str(uuid4()),
            worker=context.worker,
            owner=context.owner,
            work=control.WorkContext(),
            camera=camera.CAMERA_ROLE_BEHAVIORAL,
            parent_operation=control.OperationContext(command_id=str(uuid4())),
            planned_ns=1,
        ),
        preview=preview,
    )

    def retained_command(
        *args: object, **kwargs: object
    ) -> tuple[acq.WorkerCommand, ChildOperation, WorkerPort]:
        _ = args, kwargs
        return (
            acq.WorkerCommand(),
            ChildOperation(
                command_id=str(uuid4()),
                camera=context.camera,
                work=control.WorkContext(),
                parent_operation=control.OperationContext(),
                kind="stop_preview",
            ),
            cast(WorkerPort, port),
        )

    async def child_complete(*args: object, **kwargs: object) -> control.OperationState:
        _ = args, kwargs
        return control.OperationState(complete=True, succeeded=True)

    monkeypatch.setattr(pulse_module, "retain_worker_command", retained_command)
    monkeypatch.setattr(pulse_module, "wait_child_operation", child_complete)
    settings = control.AcquisitionSettings()
    settings.behavioral.enabled = True
    settings.behavioral.device.frame_timing = camera.FRAME_TIMING_EXTERNAL_TRIGGER
    transfers = _TransferOwner()
    lifecycle = ManualPreviewPulseLifecycle(
        identity=cast(CoordinatorIdentity, object()),
        configuration=ConfigurationRecord(
            settings, runtime.AcquisitionFilePolicies(), 2
        ),
        workers={camera.CAMERA_ROLE_BEHAVIORAL: worker},
        pulse=PulseRecord(),
        serial=cast(SerialOwnerPort, object()),
        resources={},
        resource_ledger=cast(NativeResourceLedger, object()),
        resource_port=cast(ResourcePort, object()),
        transfers=cast(ManualPreviewTransferOwner, transfers),
        device_status=cast(ManualDeviceStatusReporter, _Status()),
        lock=asyncio.Lock(),
        clock=lambda: 10,
    )

    task = asyncio.create_task(
        lifecycle.pause_for_pulse_change(
            (camera.CAMERA_ROLE_BEHAVIORAL,), deadline_ns=1_000_000_010
        )
    )
    await asyncio.wait_for(transfers.retired.wait(), 1)
    assert not task.done()
    preview.viewer = None
    preview.viewer_transfer_id = None
    preview.viewer_released_event.set()
    paused = await task
    assert len(paused) == 1
    assert worker.preview is None


def test_release_receipt_lifetime_starts_at_release_not_attach_completion() -> None:
    owner_identity = control.ProcessIdentity(
        role="acquisition", generation=str(uuid4())
    )
    controller_identity = control.ProcessIdentity(
        role="controller", generation=str(uuid4())
    )
    identity = CoordinatorIdentity(
        backend=control.BackendContext(
            backend_name="acquisition", backend_generation=owner_identity.generation
        ),
        process=owner_identity,
        controller=controller_identity,
        supervisor=control.ProcessIdentity(role="supervisor", generation=str(uuid4())),
        tracking=control.ProcessIdentity(role="tracking", generation=str(uuid4())),
    )
    commands = CommandLedger(
        owner_identity.generation,
        retention_ns=100,
        max_records=32,
        max_bytes=1_000_000,
        result_reservation_bytes=4096,
    )
    attach_command = str(uuid4())
    attach_work = str(uuid4())
    commands.admit(attach_command, b"attach", 0, work_key=attach_work)
    commands.complete(attach_command, b"accepted", 1)
    commands.finalize_work(attach_work, 1)
    now = [1]
    owner = ManualPreviewTransferOwner(
        identity=identity,
        resources={},
        resource_ledger=cast(NativeResourceLedger, object()),
        resource_port=cast(ResourcePort, object()),
        controller=cast(ControllerPort, object()),
        commands=commands,
        find_preview=lambda _run_id: None,
        clock=lambda: now[0],
    )
    key = (str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4()))

    owner._reserve_release_receipt(key)
    reservation = owner._receipt_reservations[key]
    now[0] = 102
    commands.prune(now[0])
    assert commands.get(attach_command) is None
    assert commands.has_payload(reservation)

    release = wire.PreviewConsumerReport(
        preview_run_id=key[0],
        allocation_id=key[1],
        transfer_id=key[2],
        consumer=control.ProcessIdentity(role="viewer", generation=key[3]),
        controller_generation=controller_identity.generation,
        client_id=key[3],
        result=wire.PREVIEW_CONSUMER_RESULT_RELEASED,
    )
    serialized = release.SerializeToString(deterministic=True)
    owner._retain_release_receipt(key, serialized)
    now[0] = 150
    retry = owner.report_consumer(release)

    assert retry.result == control.COMMAND_RESULT_ACCEPTED
    assert commands.has_payload(reservation)


def test_retired_tracking_preview_waits_for_both_rings_in_either_release_order() -> (
    None
):
    released: list[str] = []
    owner_identity = control.ProcessIdentity(
        role="acquisition", generation=str(uuid4())
    )
    identity = CoordinatorIdentity(
        backend=control.BackendContext(
            backend_name="acquisition", backend_generation=owner_identity.generation
        ),
        process=owner_identity,
        controller=control.ProcessIdentity(role="controller", generation=str(uuid4())),
        supervisor=control.ProcessIdentity(role="supervisor", generation=str(uuid4())),
        tracking=control.ProcessIdentity(role="tracking", generation=str(uuid4())),
    )

    class Ledger:
        allowed: set[str]

        def may_close_owner(self, key: str) -> bool:
            return key in self.allowed

        def confirm_owner_release(self, _key: str) -> None:
            pass

        def remove_completed_resource(self, _key: str) -> None:
            pass

    class Port:
        def release_ring(self, allocation_id: str) -> None:
            released.append(allocation_id)

    def setup(allowed: set[str]):
        preview_id, tracking_id, run_id = str(uuid4()), str(uuid4()), str(uuid4())
        ledger = Ledger()
        ledger.allowed = allowed
        resources = {
            preview_id: cast(
                ResourceRecord,
                type("R", (), {"ledger_key": preview_id, "ring": None})(),
            ),
            tracking_id: cast(
                ResourceRecord,
                type("R", (), {"ledger_key": tracking_id, "ring": None})(),
            ),
        }
        owner = ManualPreviewTransferOwner(
            identity=identity,
            resources=resources,
            resource_ledger=cast(NativeResourceLedger, ledger),
            resource_port=cast(ResourcePort, Port()),
            controller=cast(ControllerPort, object()),
            commands=cast(CommandLedger, object()),
            find_preview=lambda _run: None,
        )
        preview = WorkerPreview(
            run_id=run_id,
            configuration_revision=4,
            allocation_id=preview_id,
            tracking_allocation_id=tracking_id,
        )
        owner._retired[run_id] = preview
        return owner, preview, resources, ledger, preview_id, tracking_id

    owner, preview, resources, ledger, preview_id, tracking_id = setup(set())
    # Main GUI ring releases first; retired ownership remains for Tracking.
    ledger.allowed = {preview_id, tracking_id}
    owner.close_retired_resource(preview)
    assert preview_id in resources and preview.run_id in owner._retired
    owner._close_tracking_resource(preview)
    owner.close_retired_resource(preview)
    assert released == [tracking_id, preview_id]
    assert preview.run_id not in owner._retired

    released.clear()
    owner, preview, resources, ledger, preview_id, tracking_id = setup(set())
    # Tracking releases first; the GUI ring remains retained until its owner releases.
    ledger.allowed = {tracking_id}
    owner._close_tracking_resource(preview)
    owner.close_retired_resource(preview)
    assert released == [tracking_id]
    assert preview.run_id in owner._retired and preview_id in resources
    ledger.allowed.add(preview_id)
    owner.close_retired_resource(preview)
    assert released == [tracking_id, preview_id]
    assert preview.run_id not in owner._retired


def test_tracking_worker_attachment_preserves_resource_ledger_transfer_id() -> None:
    worker = control.ProcessIdentity(role="camera_worker", generation=str(uuid4()))
    tracking = control.ProcessIdentity(role="tracking", generation=str(uuid4()))
    producer = acq.FrameBufferAttachment(
        buffer=acq.FrameBufferDescriptor(
            allocation_id=str(uuid4()),
            producer=worker,
            consumer=tracking,
            kind=acq.FRAME_BUFFER_KIND_TRACKING,
        ),
        sync=acq.RingSyncNames(transfer_id=str(uuid4()), target=worker),
    )
    consumer = acq.FrameBufferAttachment.FromString(
        producer.SerializeToString(deterministic=True)
    )
    consumer.sync.transfer_id = str(uuid4())
    consumer.sync.target.CopyFrom(tracking)
    preview = new_worker_preview(
        str(uuid4()),
        4,
        acq.FrameBufferAttachment(buffer=acq.FrameBufferDescriptor()),
        camera.CameraResolvedState(),
        8,
        tracking_attachment=consumer,
        tracking_worker_attachment=producer,
    )
    assert preview.tracking_worker_attachment is not None
    assert (
        preview.tracking_worker_attachment.sync.transfer_id == producer.sync.transfer_id
    )
    assert preview.tracking_worker_attachment.sync.target == worker


@pytest.mark.asyncio
async def test_tracking_attach_reserves_release_receipt_before_reporting_transfer() -> (
    None
):
    acquisition = control.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    controller = control.ProcessIdentity(role="controller", generation=str(uuid4()))
    tracking = control.ProcessIdentity(role="tracking", generation=str(uuid4()))
    identity = CoordinatorIdentity(
        backend=control.BackendContext(
            backend_name="acquisition", backend_generation=acquisition.generation
        ),
        process=acquisition,
        controller=controller,
        supervisor=control.ProcessIdentity(role="supervisor", generation=str(uuid4())),
        tracking=tracking,
    )
    run_id, allocation_id, command_id = str(uuid4()), str(uuid4()), str(uuid4())
    commands = CommandLedger(
        acquisition.generation,
        retention_ns=10_000,
        max_records=32,
        max_bytes=1_000_000,
        result_reservation_bytes=4096,
    )
    commands.admit(command_id, b"attach tracking", 1, work_key=run_id)
    commands.complete(command_id, b"accepted", 2)
    commands.finalize_work(run_id, 2)

    class Ledger:
        released: list[tuple[object, object, object]] = []

        def expect_attachment(self, *_args, **_kwargs):
            pass

        def confirm_release(self, key, *, peer_instance_id, transfer_id):
            self.released.append((key, peer_instance_id, transfer_id))

        def may_close_owner(self, _key):
            return True

        def confirm_owner_release(self, *_args, **_kwargs):
            pass

        def remove_completed_resource(self, *_args, **_kwargs):
            pass

    ring = acq.FrameBufferAttachment(
        buffer=acq.FrameBufferDescriptor(
            allocation_id=allocation_id,
            producer=control.ProcessIdentity(
                role="camera_worker", generation=str(uuid4())
            ),
            kind=acq.FRAME_BUFFER_KIND_TRACKING,
        ),
        sync=acq.RingSyncNames(transfer_id=str(uuid4())),
    )
    resource = type("Resource", (), {"ledger_key": allocation_id, "attachment": ring})()
    preview = WorkerPreview(
        run_id=run_id,
        configuration_revision=3,
        allocation_id=str(uuid4()),
        tracking_allocation_id=allocation_id,
        tracking_attachment=ring,
    )

    class Controller:
        async def report_preview_attachment(self, _report, *, deadline_ns):
            return control.CommandAdmission(result=control.COMMAND_RESULT_ACCEPTED)

    class ResourcePort:
        def release_ring(self, _allocation_id):
            pass

    owner = ManualPreviewTransferOwner(
        identity=identity,
        resources={allocation_id: cast(ResourceRecord, resource)},
        resource_ledger=cast(NativeResourceLedger, Ledger()),
        resource_port=cast(ResourcePort, ResourcePort()),
        controller=cast(ControllerPort, Controller()),
        commands=commands,
        find_preview=lambda run: preview if run == run_id else None,
    )
    request = wire.AcquisitionTrackingDiagnosticAttachmentCommand(
        command=wire.BackendCommand(command_id=command_id),
        tracking_consumer=tracking,
    )

    attachment = await owner.attach_tracking(request, preview, deadline_ns=10_000)
    assert preview.tracking_viewer == tracking
    assert not preview.tracking_viewer_released_event.is_set()
    key = (run_id, allocation_id, attachment.sync.transfer_id, tracking.generation)
    assert key in owner._receipt_reservations

    class AcquisitionPeer:
        async def report_preview_consumer_state(self, report):
            return owner.report_consumer(report)

    class SupervisorPeer:
        async def report_preview_consumer_state(self, report):
            assert report.result == wire.PREVIEW_CONSUMER_RESULT_RELEASED
            return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)

    controller_owner = TrackingDiagnosticController.__new__(
        TrackingDiagnosticController
    )
    controller_owner.generation = controller.generation
    controller_owner.clock = lambda: 1
    controller_owner.lifecycle = SimpleNamespace(lock=asyncio.Lock())
    controller_owner.projections = SimpleNamespace(preview_result=lambda _report: None)
    controller_owner.backends = {"acquisition": AcquisitionPeer()}
    controller_owner.supervisor_peer = SupervisorPeer()
    await controller_owner._report_release(
        tracking, run_id, attachment, deadline=10_000
    )
    assert preview.tracking_viewer is None
    assert preview.tracking_viewer_transfer_id is None
    assert preview.tracking_viewer_released_event.is_set()
    assert owner.resources.get(allocation_id) is None
    assert owner.resource_ledger.released == [
        (allocation_id, tracking.generation, attachment.sync.transfer_id)
    ]
