"""Sessionless connected-camera edits and PFS operations (A10/E07)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from cephvr.acquisition.coordinator.commands import (
    retain_worker_command,
    wait_child_operation,
)
from cephvr.acquisition.coordinator.configuration_resolution import (
    ConfigurationResolution,
)
from cephvr.acquisition.coordinator.manual_device_commands import ManualDeviceCommands
from cephvr.acquisition.coordinator.manual_device_status import (
    ManualDeviceStatusReporter,
)
from cephvr.acquisition.coordinator.manual_operation_results import (
    ManualOperationResults,
)
from cephvr.acquisition.coordinator.manual_session_access import (
    manual_command_valid,
    retire_completed_manual_session,
)
from cephvr.acquisition.coordinator.session_payloads import camera_policy
from cephvr.acquisition.coordinator.workers import WorkerRegistry
from cephvr.acquisition.ports import ControllerPort, WorkerPort
from cephvr.acquisition.state import (
    ChildOperation,
    ConfigurationRecord,
    CoordinatorIdentity,
    SessionSlot,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns


class ManualDevices:
    """Apply validated edits only to already-owned sessionless camera workers.

    The controller owns validation and command admission. This component owns the
    worker SDK operation, exact readback report, and wait for controller adoption.
    Offline roles are deliberately not opened by an ordinary settings edit.
    """

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        configuration: ConfigurationRecord,
        session_slot: SessionSlot,
        workers: WorkerRegistry,
        controller: ControllerPort,
        resolution: ConfigurationResolution,
        device_status: ManualDeviceStatusReporter,
        lock: asyncio.Lock,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.configuration = configuration
        self.session_slot = session_slot
        self.workers = workers
        self.results = ManualOperationResults(
            identity=identity, controller=controller, device_status=device_status
        )
        self.resolution = resolution
        self.device_status = device_status
        self.lock = lock
        self.clock = clock
        self.commands = ManualDeviceCommands(
            identity=identity,
            configuration=configuration,
            session_slot=session_slot,
            workers=workers,
            resolution=resolution,
            device_status=device_status,
            results=self.results,
            lock=lock,
            clock=clock,
        )

    async def apply(
        self,
        request: wire.AcquisitionCameraSettingsCommand,
        *,
        deadline_ns: int,
    ) -> control.CommandAdmission:
        command = request.command
        if not request.HasField("configuration_revision"):
            return _rejected(
                command.command_id,
                "CAMERA_EDIT_REVISION",
                "camera edit lacks an explicit configuration revision",
            )
        if not manual_command_valid(
            command,
            revision=request.configuration_revision,
            expected_revision=self.configuration.revision,
            identity=self.identity,
            session_slot=self.session_slot,
            now_ns=self.clock(),
            deadline_ns=deadline_ns,
        ):
            return _rejected(
                command.command_id, "STALE_CAMERA_EDIT", "camera edit is stale"
            )
        if not request.cameras or request.pulses.ByteSize():
            return _rejected(
                command.command_id,
                "CAMERA_EDIT_SHAPE",
                "camera edit requires a nonempty camera-only batch",
            )
        roles = [item.camera for item in request.cameras]
        if len(set(roles)) != len(roles) or any(
            role not in (camera.CAMERA_ROLE_BEHAVIORAL, camera.CAMERA_ROLE_TRACKING)
            for role in roles
        ):
            return _rejected(
                command.command_id,
                "CAMERA_EDIT_ROLES",
                "camera roles are invalid or duplicated",
            )
        revision = request.configuration_revision
        assert revision is not None
        if request.file_policies != self.configuration.file_policies:
            return _rejected(
                command.command_id,
                "CAMERA_EDIT_POLICY",
                "camera edit policy differs from the loaded controller policy",
            )
        try:
            self.device_status.reserve(command)
        except (RuntimeError, ValueError) as exc:
            return _rejected(command.command_id, "DEVICE_STATUS_CAPACITY", str(exc))
        try:
            await retire_completed_manual_session(
                self.session_slot, self.workers, deadline_ns=deadline_ns
            )
        except (RuntimeError, TimeoutError, ValueError) as exc:
            return _rejected(command.command_id, "SESSION_RETIREMENT", str(exc))
        try:
            await self.resolution.begin(
                command,
                expected_cameras=set(roles),
                request_revision=revision,
                deadline_ns=deadline_ns,
            )
            payloads = self._build_apply_payloads(request, deadline_ns)
            receipts = await asyncio.gather(
                *(
                    port.edit_camera(payload, deadline_ns=deadline_ns)
                    for _role, _child, port, payload in payloads
                )
            )
            if any(item.result != control.COMMAND_RESULT_ACCEPTED for item in receipts):
                raise RuntimeError("one or more camera edit commands were rejected")
            states = await asyncio.gather(
                *(
                    wait_child_operation(child, deadline_ns, self.lock, self.clock)
                    for _role, child, _port, _payload in payloads
                )
            )
            if any(not item.succeeded for item in states):
                raise RuntimeError("one or more camera edits failed")
            for role, child, _port, _payload in payloads:
                if child.resolved_camera is None:
                    raise RuntimeError("camera edit has no retained resolved state")
                self.device_status.resolve_camera(
                    role,
                    child.resolved_camera,
                    device_open=True,
                    cleanup_pending=True,
                )
            await self.resolution.wait_confirmed(
                control.OperationContext(command_id=command.command_id),
                deadline_ns=deadline_ns,
            )
            await self.resolution.retire(
                control.OperationContext(command_id=command.command_id)
            )
            for role, child, _port, _payload in payloads:
                assert child.resolved_camera is not None
                self.device_status.resolve_camera(
                    role,
                    child.resolved_camera,
                    device_open=True,
                    configuration_revision=self.configuration.revision,
                )
            return await self.results.complete(
                command,
                command_name="apply_camera_settings",
                deadline_ns=deadline_ns,
                status_code="DEVICE_STATUS",
                status_failure="controller rejected camera status",
                parent_code="PARENT_REPORT",
                parent_failure="controller rejected camera completion",
            )
        except (RuntimeError, TimeoutError, ValueError) as exc:
            operation = control.OperationContext(command_id=command.command_id)
            try:
                await self.resolution.cancel(operation)
                await self.resolution.retire(operation)
            except (RuntimeError, ValueError):
                pass
            await self.results.report_failure(
                command,
                command_name="apply_camera_settings",
                deadline_ns=deadline_ns,
                failure=str(exc),
            )
            return _rejected(command.command_id, "CAMERA_EDIT_FAILED", str(exc))

    async def execute(
        self,
        request: wire.AcquisitionCameraCommand,
        *,
        deadline_ns: int,
    ) -> control.CommandAdmission:
        return await self.commands.execute(request, deadline_ns=deadline_ns)

    def _build_apply_payloads(
        self,
        request: wire.AcquisitionCameraSettingsCommand,
        deadline_ns: int,
    ) -> list[tuple[int, ChildOperation, WorkerPort, acq.WorkerEditCamera]]:
        payloads = []
        for item in request.cameras:
            if not item.HasField("requested") or not item.requested.device_id:
                raise ValueError("camera edit lacks a complete assigned device")
            worker = self.workers.workers.get(item.camera)
            if worker is None or worker.context.work.WhichOneof("work") is not None:
                raise ValueError("camera edit cannot implicitly open an offline device")
            if worker.preview is not None and worker.preview.started:
                raise ValueError("preview must pause before applying camera settings")
            policy = camera_policy(request.file_policies, item.camera)
            if item.transport != policy.transport:
                raise ValueError("edit transport differs from resolved file policy")
            child, operation, port = retain_worker_command(
                worker,
                work=None,
                parent_operation=control.OperationContext(
                    command_id=request.command.command_id
                ),
                kind="apply_camera",
                deadline_ns=deadline_ns,
                configuration_revision=request.configuration_revision,
                requested_device_id=item.requested.device_id,
            )
            payload = acq.WorkerEditCamera(
                command=child,
                configuration_revision=request.configuration_revision,
                kind=acq.CAMERA_EDIT_KIND_APPLY_SETTINGS,
                requested=item.requested,
                transport=item.transport,
            )
            payloads.append((int(item.camera), operation, port, payload))
        return payloads


def _rejected(command_id: str, code: str, message: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        result=control.COMMAND_RESULT_REJECTED,
        command_id=command_id,
        failure=control.Failure(code=code, message=message[:2048]),
    )
