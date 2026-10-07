"""Manual Configuration preview runs and exact viewer transfers (A03/A10)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from uuid import uuid4

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
from cephvr.acquisition.coordinator.manual_preview_start import ManualPreviewStart
from cephvr.acquisition.coordinator.manual_preview_transfer import (
    ManualPreviewTransferOwner,
)
from cephvr.acquisition.coordinator.manual_preview_window import (
    attach_preview_viewer,
    execute_preview_window,
)
from cephvr.acquisition.coordinator.manual_pulse_observation import (
    release_idle_claim,
    retain_applied_pulse_state,
)
from cephvr.acquisition.coordinator.manual_session_access import (
    manual_configuration_available,
    retire_completed_manual_session,
)
from cephvr.acquisition.coordinator.preview_windows import PreviewWindows
from cephvr.acquisition.coordinator.session_payloads import camera_policy, role_name
from cephvr.acquisition.coordinator.workers import WorkerRegistry
from cephvr.acquisition.ports import ControllerPort, ResourcePort, SerialOwnerPort
from cephvr.acquisition.state import (
    ConfigurationRecord,
    CoordinatorIdentity,
    PulseRecord,
    ResourceRecord,
    SessionSlot,
    WorkerPreview,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.resource_ledger import NativeResourceLedger
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger
from cephvr.shared.preview_placement import valid_preview_placement


class ManualPreview:
    """Own each manual preview run, its capacity-one ring and viewer transfer."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        configuration: ConfigurationRecord,
        session_slot: SessionSlot,
        pulse: PulseRecord,
        workers: WorkerRegistry,
        serial: SerialOwnerPort,
        resources: dict[str, ResourceRecord],
        resource_ledger: NativeResourceLedger,
        resource_port: ResourcePort,
        controller: ControllerPort,
        commands: CommandLedger,
        resolution: ConfigurationResolution,
        device_status: ManualDeviceStatusReporter,
        lock: asyncio.Lock,
        visibility_report_timeout_ns: int,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.configuration = configuration
        self.session_slot = session_slot
        self.pulse = pulse
        self.workers = workers
        self.serial = serial
        self.resources = resources
        self.resource_ledger = resource_ledger
        self.resource_port = resource_port
        self.controller = controller
        self.resolution = resolution
        self.device_status = device_status
        self.results = ManualOperationResults(
            identity=identity, controller=controller, device_status=device_status
        )
        self.lock = lock
        self.clock = clock
        self.windows = PreviewWindows(
            identity=identity,
            resources=resources,
            ledger=resource_ledger,
            status=device_status,
            clock=clock,
            report_timeout_ns=visibility_report_timeout_ns,
        )
        self.start_flow = ManualPreviewStart(
            identity=identity,
            configuration=configuration,
            pulse=pulse,
            serial=serial,
            resources=resources,
            resource_ledger=resource_ledger,
            resource_port=resource_port,
            resolution=resolution,
            device_status=device_status,
            lock=lock,
            clock=clock,
        )
        self.transfers = ManualPreviewTransferOwner(
            identity=identity,
            resources=resources,
            resource_ledger=resource_ledger,
            resource_port=resource_port,
            controller=controller,
            commands=commands,
            find_preview=self._find_preview,
            clock=clock,
        )

    async def execute(
        self,
        request: wire.AcquisitionCameraCommand,
        *,
        deadline_ns: int,
    ) -> control.CommandAdmission:
        command = request.command
        if not self._valid(request, deadline_ns):
            return _rejected(
                command.command_id, "STALE_PREVIEW_COMMAND", "preview command is stale"
            )
        if not valid_preview_placement(request):
            return _rejected(
                command.command_id,
                "PREVIEW_PLACEMENT",
                "Invalid display placement hint",
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
        if request.kind in {
            wire.CAMERA_COMMAND_KIND_SHOW_PREVIEW,
            wire.CAMERA_COMMAND_KIND_HIDE_PREVIEW,
        }:
            worker = self.workers.workers.get(request.camera)
            return await execute_preview_window(
                request,
                worker.preview if worker else None,
                self.windows,
                self.results,
                deadline_ns=deadline_ns,
            )
        if request.kind == wire.CAMERA_COMMAND_KIND_START_PREVIEW:
            if (
                request.HasField("path")
                or request.HasField("preview_run_id")
                or request.HasField("preview_consumer")
            ):
                return _rejected(
                    command.command_id,
                    "PREVIEW_START_SHAPE",
                    "Start Preview does not accept path or run identity",
                )
            return await self._start(request, deadline_ns)
        if request.kind == wire.CAMERA_COMMAND_KIND_STOP_PREVIEW:
            if (
                not request.HasField("preview_run_id")
                or request.HasField("path")
                or request.HasField("preview_consumer")
            ):
                return _rejected(
                    command.command_id,
                    "PREVIEW_STOP_SHAPE",
                    "Stop Preview requires only its exact run identity",
                )
            return await self._stop(request, deadline_ns)
        if request.kind == wire.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER:
            if (
                not request.HasField("preview_run_id")
                or not request.HasField("preview_consumer")
                or request.HasField("path")
            ):
                return _rejected(
                    command.command_id,
                    "PREVIEW_ATTACH_SHAPE",
                    "viewer attach requires exact run and consumer",
                )
            worker = self.workers.workers.get(request.camera)
            return await attach_preview_viewer(
                request,
                worker.preview if worker else None,
                self.windows,
                self.transfers,
                self.results,
                deadline_ns=deadline_ns,
            )
        return _rejected(
            command.command_id,
            "PREVIEW_COMMAND_KIND",
            "camera command is not owned by preview capture",
        )

    async def report_consumer(
        self,
        request: wire.PreviewConsumerReport,
        *,
        deadline_ns: int,
    ) -> control.ReportReceipt:
        _ = deadline_ns
        return self.transfers.report_consumer(request)

    async def attach_tracking_diagnostic_input(
        self,
        request: wire.AcquisitionTrackingDiagnosticAttachmentCommand,
        *,
        deadline_ns: int,
    ) -> control.CommandAdmission:
        command = request.command
        preview = self._find_preview(request.preview_run_id)
        if (
            self.clock() >= deadline_ns
            or command.issuer != self.identity.controller
            or command.target != self.identity.backend
            or command.work.WhichOneof("work") is not None
            or request.configuration_revision != self.configuration.revision
            or request.tracking_consumer != self.identity.tracking
            or preview is None
            or not preview.started
            or preview.configuration_revision != request.configuration_revision
            or preview.tracking_allocation_id is None
        ):
            return _rejected(
                command.command_id,
                "TRACKING_DIAGNOSTIC_SOURCE",
                "diagnostic attachment does not match the exact active tracking preview",
            )
        try:
            await self.transfers.attach_tracking(
                request, preview, deadline_ns=deadline_ns
            )
        except (RuntimeError, TimeoutError, ValueError) as exc:
            return _rejected(
                command.command_id, "TRACKING_DIAGNOSTIC_TRANSFER", str(exc)
            )
        return control.CommandAdmission(
            result=control.COMMAND_RESULT_ACCEPTED,
            command_id=command.command_id,
        )

    async def _start(
        self, request: wire.AcquisitionCameraCommand, deadline_ns: int
    ) -> control.CommandAdmission:
        command = request.command
        role = request.camera
        setting = getattr(self.configuration.settings, role_name(role))
        if not setting.HasField("device") or not setting.device.device_id:
            return _rejected(
                command.command_id,
                "CAMERA_ASSIGNMENT",
                "preview camera has no assigned device",
            )
        if not request.HasField(
            "preview_output_bit_depth"
        ) or request.preview_output_bit_depth not in (8, 10):
            return _rejected(
                command.command_id,
                "PREVIEW_DEPTH",
                "preview output depth must be explicitly resolved to 8 or 10",
            )
        if request.file_policies != self.configuration.file_policies:
            return _rejected(
                command.command_id,
                "PREVIEW_POLICY",
                "preview file policy differs from loaded policy",
            )
        try:
            existing = self.workers.workers.get(role)
            if existing is not None and (
                existing.context.work.WhichOneof("work") is not None
                or existing.preview is not None
            ):
                return _rejected(
                    command.command_id,
                    "PREVIEW_ALREADY_OWNED",
                    "camera already has session or preview work",
                )
            worker = existing
            if worker is None:
                worker = await self.workers.launch(
                    role,
                    None,
                    control.OperationContext(command_id=command.command_id),
                    deadline_ns=deadline_ns,
                    file_policy=camera_policy(self.configuration.file_policies, role),
                )
            run_id = str(uuid4())
            external_roles = self._external_roles(role)
            policy = camera_policy(self.configuration.file_policies, role)
            await self.start_flow.start(
                request,
                worker,
                setting,
                policy,
                tuple(external_roles),
                run_id,
                deadline_ns,
            )
            return await self.results.complete(
                command,
                command_name="start_preview",
                deadline_ns=deadline_ns,
                status_code="DEVICE_STATUS",
                status_failure="controller rejected camera status",
                parent_code="PREVIEW_REPORT",
                parent_failure="controller rejected preview completion",
            )
        except (RuntimeError, TimeoutError, ValueError) as exc:
            try:
                operation = control.OperationContext(command_id=command.command_id)
                await self.resolution.cancel(operation)
                await self.resolution.retire(operation)
            except (RuntimeError, ValueError):
                pass
            await self.results.report_failure(
                command,
                command_name="start_preview",
                deadline_ns=deadline_ns,
                failure=str(exc),
            )
            return _rejected(command.command_id, "PREVIEW_START_FAILED", str(exc))

    async def _stop(
        self, request: wire.AcquisitionCameraCommand, deadline_ns: int
    ) -> control.CommandAdmission:
        worker = self.workers.workers.get(request.camera)
        preview = worker.preview if worker is not None else None
        if (
            worker is None
            or preview is None
            or preview.run_id != request.preview_run_id
            or not preview.started
            or preview.stopping
        ):
            return _rejected(
                request.command.command_id,
                "PREVIEW_RUN",
                "Stop Preview does not match the live run",
            )
        preview.stopping = True
        active_roles = self._external_roles(None)
        resume_roles = tuple(role for role in active_roles if role != request.camera)
        try:
            if active_roles:
                evidence = await self.serial.off(
                    tuple(active_roles),
                    scheduled_boundary_ns=None,
                    stop_issued_ns=self.clock(),
                    deadline_ns=deadline_ns,
                )
                retain_applied_pulse_state(
                    self.pulse, evidence, deadline_ns=deadline_ns
                )
            parent = control.OperationContext(command_id=request.command.command_id)
            child, operation, port = retain_worker_command(
                worker,
                work=None,
                parent_operation=parent,
                kind="stop_preview",
                deadline_ns=deadline_ns,
                configuration_revision=preview.configuration_revision,
            )
            preview.stop_operation = control.OperationContext(
                command_id=operation.command_id
            )
            stop = acq.WorkerStopPreview(
                command=child,
                preview_run_id=preview.run_id,
                release_device=True,
            )
            receipt = await port.stop_preview(stop, deadline_ns=deadline_ns)
            if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError("manual preview stop was rejected")
            state = await wait_child_operation(
                operation, deadline_ns, self.lock, self.clock
            )
            if not state.succeeded:
                raise RuntimeError("manual preview worker cleanup failed")
            await _wait_preview_event(preview.stopped_event, deadline_ns, self.clock)
            await _wait_preview_event(preview.cleanup_event, deadline_ns, self.clock)
            if preview.started:
                raise RuntimeError("manual preview did not confirm stopped activity")
            if preview.resolved_camera is None:
                raise RuntimeError("manual preview stop lacks retained resolved camera")
            await self.windows.close(
                request.camera, preview.run_id, deadline_ns=deadline_ns
            )
            self.device_status.resolve_camera(
                int(request.camera),
                preview.resolved_camera,
                device_open=False,
                configuration_revision=preview.configuration_revision,
            )
            self.transfers.retire(preview)
            viewer_was_attached = preview.viewer is not None
            tracking_consumer_attached = preview.tracking_viewer is not None
            preview.stopping = False
            worker.preview = None
            if viewer_was_attached:
                await _wait_preview_event(
                    preview.viewer_released_event, deadline_ns, self.clock
                )
            if tracking_consumer_attached:
                await _wait_preview_event(
                    preview.tracking_viewer_released_event, deadline_ns, self.clock
                )
            self.transfers.close_retired_resource(preview)
            if preview.allocation_id in self.resources or (
                preview.tracking_allocation_id is not None
                and preview.tracking_allocation_id in self.resources
            ):
                raise RuntimeError(
                    "manual preview or Tracking diagnostic ring ownership is not fully released"
                )
            if resume_roles:
                on = await self.serial.on(
                    resume_roles,
                    scheduled_boundary_ns=None,
                    deadline_ns=deadline_ns,
                )
                retain_applied_pulse_state(self.pulse, on, deadline_ns=deadline_ns)
            elif self.pulse.observation is not None:
                await release_idle_claim(
                    self.pulse, self.serial, deadline_ns=deadline_ns
                )
            return await self.results.complete(
                request.command,
                command_name="stop_preview",
                deadline_ns=deadline_ns,
                status_code="DEVICE_STATUS",
                status_failure="controller rejected camera status",
                parent_code="PREVIEW_REPORT",
                parent_failure="controller rejected preview completion",
            )
        except (RuntimeError, TimeoutError, ValueError) as exc:
            if preview is not None:
                try:
                    self.device_status.update_camera_state(
                        int(request.camera),
                        device_open=True,
                        preview_prepared=True,
                        preview_running=preview.started,
                        preview_run_id=preview.run_id,
                        cleanup_pending=True,
                    )
                except ValueError:
                    pass
            await self.results.report_failure(
                request.command,
                command_name="stop_preview",
                deadline_ns=deadline_ns,
                failure=str(exc),
            )
            return _rejected(
                request.command.command_id, "PREVIEW_STOP_FAILED", str(exc)
            )

    def _external_roles(self, adding_role: int | None) -> list[int]:
        roles: set[int] = set()
        for role, setting in (
            (camera.CAMERA_ROLE_BEHAVIORAL, self.configuration.settings.behavioral),
            (camera.CAMERA_ROLE_TRACKING, self.configuration.settings.tracking),
        ):
            worker = self.workers.workers.get(role)
            is_starting = role == adding_role
            if (
                (
                    is_starting
                    or worker is not None
                    and worker.preview is not None
                    and worker.preview.started
                )
                and setting.HasField("device")
                and setting.device.HasField("frame_timing")
                and setting.device.frame_timing == camera.FRAME_TIMING_EXTERNAL_TRIGGER
            ):
                roles.add(role)
        return sorted(roles)

    def _valid(self, request: wire.AcquisitionCameraCommand, deadline_ns: int) -> bool:
        command = request.command
        return bool(
            self.clock() < deadline_ns
            and command.command_id
            and command.issuer == self.identity.controller
            and command.target == self.identity.backend
            and command.work.WhichOneof("work") is None
            and command.HasField("parent_operation")
            and command.parent_operation.command_id
            and request.HasField("configuration_revision")
            and request.configuration_revision == self.configuration.revision
            and (
                request.file_policies == self.configuration.file_policies
                or request.kind == wire.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER
                and not request.HasField("file_policies")
            )
            and manual_configuration_available(self.session_slot)
            and request.camera
            in (
                camera.CAMERA_ROLE_BEHAVIORAL,
                camera.CAMERA_ROLE_TRACKING,
            )
        )

    def _find_preview(self, run_id: str) -> WorkerPreview | None:
        for worker in self.workers.workers.values():
            if worker.preview is not None and worker.preview.run_id == run_id:
                return worker.preview
        return None


def _rejected(command_id: str, code: str, message: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        result=control.COMMAND_RESULT_REJECTED,
        command_id=command_id,
        failure=control.Failure(code=code, message=message[:2048]),
    )


async def _wait_preview_event(
    event: asyncio.Event, deadline_ns: int, clock: Callable[[], int]
) -> None:
    remaining = max(0, deadline_ns - clock()) / 1_000_000_000
    if remaining <= 0:
        raise TimeoutError("preview lifecycle evidence missed its retained deadline")
    await asyncio.wait_for(event.wait(), remaining)
