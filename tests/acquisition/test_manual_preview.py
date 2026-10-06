"""Preview restart ordering and exact viewer-transfer release."""

from __future__ import annotations

import asyncio
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
from cephvr.acquisition.coordinator.manual_preview_setup import build_preview_payload
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
    WorkerPreview,
    WorkerRecord,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import runtime_pb2 as runtime
from cephvr.acquisition.worker.function_scopes import validate_camera_function_scopes
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
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
