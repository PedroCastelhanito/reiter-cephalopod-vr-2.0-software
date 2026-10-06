"""Connection checks and PFS/editing workflows for manual cameras (A10/E07)."""

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
from cephvr.acquisition.coordinator.session_payloads import camera_policy, role_name
from cephvr.acquisition.coordinator.workers import WorkerRegistry
from cephvr.acquisition.state import (
    ConfigurationRecord,
    CoordinatorIdentity,
    SessionSlot,
    WorkerRecord,
)
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns


class ManualDeviceCommands:
    """Own PFS and Finish Editing operations on exact sessionless worker records."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        configuration: ConfigurationRecord,
        session_slot: SessionSlot,
        workers: WorkerRegistry,
        resolution: ConfigurationResolution,
        device_status: ManualDeviceStatusReporter,
        results: ManualOperationResults,
        lock: asyncio.Lock,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.configuration = configuration
        self.session_slot = session_slot
        self.workers = workers
        self.results = results
        self.resolution = resolution
        self.device_status = device_status
        self.lock = lock
        self.clock = clock

    async def execute(
        self,
        request: wire.AcquisitionCameraCommand,
        *,
        deadline_ns: int,
    ) -> control.CommandAdmission:
        """Run one explicit connection check or Import/Export/Finish operation.

        Start/Stop and viewer attachment belong to ManualPreview. Import first loads
        the chosen PFS, then resolves actual values through the same adoption barrier.
        Export is refused until a current controller-confirmed readback exists.
        """
        command = request.command
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
                command.command_id, "STALE_CAMERA_COMMAND", "camera command is stale"
            )
        if not request.HasField("configuration_revision"):
            return _rejected(
                command.command_id,
                "CAMERA_COMMAND_REVISION",
                "camera command lacks an explicit configuration revision",
            )
        if request.file_policies != self.configuration.file_policies:
            return _rejected(
                command.command_id,
                "CAMERA_COMMAND_POLICY",
                "camera command policy differs from the loaded controller policy",
            )
        if request.kind not in (
            wire.CAMERA_COMMAND_KIND_IMPORT_PFS,
            wire.CAMERA_COMMAND_KIND_EXPORT_PFS,
            wire.CAMERA_COMMAND_KIND_FINISH_EDITING,
            wire.CAMERA_COMMAND_KIND_TEST_CONNECTION,
        ):
            return _rejected(
                command.command_id,
                "CAMERA_COMMAND_KIND",
                "camera command belongs to the preview owner",
            )
        try:
            self.device_status.reserve(command)
        except (RuntimeError, ValueError) as exc:
            return _rejected(command.command_id, "DEVICE_STATUS_CAPACITY", str(exc))
        if request.kind in (
            wire.CAMERA_COMMAND_KIND_IMPORT_PFS,
            wire.CAMERA_COMMAND_KIND_EXPORT_PFS,
        ):
            if not request.HasField("path") or not request.path:
                return _rejected(
                    command.command_id,
                    "PFS_PATH",
                    "PFS command requires a rig-host path",
                )
        elif request.HasField("path"):
            return _rejected(
                command.command_id,
                "CAMERA_COMMAND_PATH",
                "Finish Editing does not accept a path",
            )
        try:
            await retire_completed_manual_session(
                self.session_slot, self.workers, deadline_ns=deadline_ns
            )
        except (RuntimeError, TimeoutError, ValueError) as exc:
            return _rejected(command.command_id, "SESSION_RETIREMENT", str(exc))
        worker = self.workers.workers.get(request.camera)
        if (
            request.kind
            in (
                wire.CAMERA_COMMAND_KIND_IMPORT_PFS,
                wire.CAMERA_COMMAND_KIND_EXPORT_PFS,
                wire.CAMERA_COMMAND_KIND_TEST_CONNECTION,
            )
            and worker is None
        ):
            try:
                policy = camera_policy(self.configuration.file_policies, request.camera)
                worker = await self.workers.launch(
                    request.camera,
                    None,
                    control.OperationContext(command_id=command.command_id),
                    deadline_ns=deadline_ns,
                    file_policy=policy,
                )
            except (RuntimeError, TimeoutError, ValueError) as exc:
                return _rejected(command.command_id, "CAMERA_LAUNCH", str(exc))
        if worker is None or worker.context.work.WhichOneof("work") is not None:
            return _rejected(
                command.command_id,
                "CAMERA_NOT_OWNED",
                "camera is not connected for Configuration editing",
            )
        if worker.preview is not None and worker.preview.started:
            return _rejected(
                command.command_id,
                "PREVIEW_ACTIVE",
                "pause and reconcile preview before editing",
            )
        prior_connection = (
            self.device_status.begin_device_access(
                int(request.camera), self._device_id(request.camera)
            )
            if request.kind
            in {
                wire.CAMERA_COMMAND_KIND_TEST_CONNECTION,
                wire.CAMERA_COMMAND_KIND_IMPORT_PFS,
            }
            else None
        )
        revision = request.configuration_revision
        assert revision is not None
        if request.kind == wire.CAMERA_COMMAND_KIND_EXPORT_PFS:
            try:
                # Every export is preceded by a fresh apply/readback handshake
                # under this command's exact revision, then gets its own child.
                await self._apply_for_export(worker, request, deadline_ns)
            except (RuntimeError, TimeoutError, ValueError) as exc:
                pending = control.OperationContext(command_id=command.command_id)
                try:
                    await self.resolution.cancel(pending)
                    await self.resolution.retire(pending)
                except (RuntimeError, ValueError):
                    pass
                return _rejected(command.command_id, "PFS_EXPORT_READBACK", str(exc))
        try:
            if request.kind == wire.CAMERA_COMMAND_KIND_IMPORT_PFS:
                await self.resolution.begin(
                    command,
                    expected_cameras={request.camera},
                    request_revision=revision,
                    deadline_ns=deadline_ns,
                )
            child, operation, port = retain_worker_command(
                worker,
                work=None,
                parent_operation=control.OperationContext(
                    command_id=command.command_id
                ),
                kind=(
                    "import_pfs"
                    if request.kind == wire.CAMERA_COMMAND_KIND_IMPORT_PFS
                    else "export_pfs"
                    if request.kind == wire.CAMERA_COMMAND_KIND_EXPORT_PFS
                    else "test_connection"
                    if request.kind == wire.CAMERA_COMMAND_KIND_TEST_CONNECTION
                    else "finish_editing"
                ),
                deadline_ns=deadline_ns,
                configuration_revision=revision,
                requested_device_id=self._device_id(request.camera),
            )
            edit = acq.WorkerEditCamera(command=child)
            edit.configuration_revision = revision
            if request.kind == wire.CAMERA_COMMAND_KIND_IMPORT_PFS:
                edit.kind = acq.CAMERA_EDIT_KIND_IMPORT_PFS
                edit.path = request.path
                edit.requested.CopyFrom(request.requested)
            elif request.kind == wire.CAMERA_COMMAND_KIND_FINISH_EDITING:
                edit.kind = acq.CAMERA_EDIT_KIND_FINISH_EDITING
            elif request.kind == wire.CAMERA_COMMAND_KIND_TEST_CONNECTION:
                edit.kind = acq.CAMERA_EDIT_KIND_TEST_CONNECTION
                edit.requested.device_id = self._device_id(request.camera)
            else:
                if not request.HasField("path"):
                    raise ValueError("export path is absent")
                edit.kind = acq.CAMERA_EDIT_KIND_EXPORT_PFS
                edit.path = request.path
            receipt = await port.edit_camera(edit, deadline_ns=deadline_ns)
            if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(
                    f"{receipt.failure.code}: {receipt.failure.message}"
                    if receipt.HasField("failure")
                    else "camera edit command was rejected"
                )
            completed = await wait_child_operation(
                operation, deadline_ns, self.lock, self.clock
            )
            if not completed.succeeded:
                raise RuntimeError(
                    completed.failure.message
                    if completed.HasField("failure")
                    else "camera edit failed"
                )
            if (
                prior_connection is not None
                and request.kind == wire.CAMERA_COMMAND_KIND_TEST_CONNECTION
            ):
                self.device_status.complete_connection_test(
                    int(request.camera), prior_connection
                )
            if (
                request.kind == wire.CAMERA_COMMAND_KIND_EXPORT_PFS
                and operation.exported_pfs_path != request.path
            ):
                raise RuntimeError(
                    "PFS export did not close the exact requested destination"
                )
            if request.kind == wire.CAMERA_COMMAND_KIND_IMPORT_PFS:
                if operation.resolved_camera is None:
                    raise RuntimeError(
                        "PFS import completed without an actual readback"
                    )
                self.device_status.resolve_camera(
                    int(request.camera),
                    operation.resolved_camera,
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
                self.device_status.resolve_camera(
                    int(request.camera),
                    operation.resolved_camera,
                    device_open=True,
                    configuration_revision=self.configuration.revision,
                )
            elif request.kind == wire.CAMERA_COMMAND_KIND_FINISH_EDITING:
                self.device_status.update_camera_state(
                    int(request.camera), device_open=False
                )
            return await self.results.complete(
                command,
                command_name="execute_camera_command",
                deadline_ns=deadline_ns,
                status_code="DEVICE_STATUS",
                status_failure="controller rejected camera device status",
                parent_code="PARENT_REPORT",
                parent_failure="controller rejected camera completion",
                exported_pfs_path=(
                    operation.exported_pfs_path
                    if request.kind == wire.CAMERA_COMMAND_KIND_EXPORT_PFS
                    else None
                ),
            )
        except (RuntimeError, TimeoutError, ValueError) as exc:
            if request.kind == wire.CAMERA_COMMAND_KIND_IMPORT_PFS:
                pending = control.OperationContext(command_id=command.command_id)
                try:
                    await self.resolution.cancel(pending)
                    await self.resolution.retire(pending)
                except (RuntimeError, ValueError):
                    pass
            await self.results.report_failure(
                command,
                command_name="execute_camera_command",
                deadline_ns=deadline_ns,
                failure=str(exc),
            )
            return _rejected(command.command_id, "CAMERA_COMMAND_FAILED", str(exc))

    async def _apply_for_export(
        self,
        worker: WorkerRecord,
        request: wire.AcquisitionCameraCommand,
        deadline_ns: int,
    ) -> None:
        role = request.camera
        setting = getattr(self.configuration.settings, role_name(role))
        if not setting.HasField("device"):
            raise ValueError("camera has no controller-confirmed device assignment")
        revision = request.configuration_revision
        assert revision is not None
        await self.resolution.begin(
            request.command,
            expected_cameras={role},
            request_revision=revision,
            deadline_ns=deadline_ns,
        )
        child, operation, port = retain_worker_command(
            worker,
            work=None,
            parent_operation=control.OperationContext(
                command_id=request.command.command_id
            ),
            kind="apply_camera",
            deadline_ns=deadline_ns,
            configuration_revision=revision,
            requested_device_id=setting.device.device_id,
        )
        policy = camera_policy(self.configuration.file_policies, role)
        edit = acq.WorkerEditCamera(
            command=child,
            configuration_revision=revision,
            kind=acq.CAMERA_EDIT_KIND_APPLY_SETTINGS,
            requested=setting.device,
            transport=policy.transport,
        )
        receipt = await port.edit_camera(edit, deadline_ns=deadline_ns)
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError("pending camera settings were not admitted")
        state = await wait_child_operation(
            operation, deadline_ns, self.lock, self.clock
        )
        if not state.succeeded or operation.resolved_camera is None:
            raise RuntimeError("pending camera settings lack successful SDK readback")
        self.device_status.resolve_camera(
            role,
            operation.resolved_camera,
            device_open=True,
            cleanup_pending=True,
        )
        await self.resolution.wait_confirmed(
            control.OperationContext(command_id=request.command.command_id),
            deadline_ns=deadline_ns,
        )
        await self.resolution.retire(
            control.OperationContext(command_id=request.command.command_id)
        )
        self.device_status.resolve_camera(
            role,
            operation.resolved_camera,
            device_open=True,
            configuration_revision=self.configuration.revision,
        )

    def _device_id(self, role: int) -> str:
        setting = getattr(self.configuration.settings, role_name(role))
        return setting.device.device_id if setting.HasField("device") else ""


def _rejected(command_id: str, code: str, message: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        result=control.COMMAND_RESULT_REJECTED,
        command_id=command_id,
        failure=control.Failure(code=code, message=message[:2048]),
    )
