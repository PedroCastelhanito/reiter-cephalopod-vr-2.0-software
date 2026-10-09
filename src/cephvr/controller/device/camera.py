"""Acquisition camera command admission and dispatch."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from google.protobuf.message import Message

from cephvr.acquisition.identity import camera_role_name
from cephvr.acquisition.v1 import camera_pb2 as camera_pb
from cephvr.acquisition.v1 import runtime_pb2 as acquisition_pb
from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.device.owned_edit_recovery import recover_owned_edit_status
from cephvr.controller.device.ports import DeviceHooks
from cephvr.controller.device.release_evidence import (
    camera_policy,
    load_file_policies,
)
from cephvr.controller.device.status_retention import CameraStatusRetention
from cephvr.controller.ports import BackendPort
from cephvr.controller.projections import ProjectionError, ProjectionStore
from cephvr.controller.state import (
    CameraOperation,
    ConfigurationState,
    DeviceState,
    LifecycleState,
    LimitsState,
)
from cephvr.shared.deadlines import remaining_seconds
from cephvr.shared.preview_placement import valid_preview_placement

NO_PATH = frozenset(
    {
        svc.CAMERA_COMMAND_KIND_START_PREVIEW,
        svc.CAMERA_COMMAND_KIND_STOP_PREVIEW,
        svc.CAMERA_COMMAND_KIND_FINISH_EDITING,
        svc.CAMERA_COMMAND_KIND_TEST_CONNECTION,
        svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER,
        svc.CAMERA_COMMAND_KIND_SHOW_PREVIEW,
        svc.CAMERA_COMMAND_KIND_HIDE_PREVIEW,
    }
)
REQUIRES_RUN = frozenset(
    {
        svc.CAMERA_COMMAND_KIND_STOP_PREVIEW,
        svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER,
        svc.CAMERA_COMMAND_KIND_SHOW_PREVIEW,
        svc.CAMERA_COMMAND_KIND_HIDE_PREVIEW,
    }
)
REQUIRES_READBACK = frozenset(
    {
        svc.CAMERA_COMMAND_KIND_START_PREVIEW,
        svc.CAMERA_COMMAND_KIND_IMPORT_PFS,
        svc.CAMERA_COMMAND_KIND_EXPORT_PFS,
    }
)


@dataclass(frozen=True)
class CameraSelection:
    backend: BackendPort
    revision: int
    work: pb.WorkContext
    selected: camera_pb.CameraSessionSettings
    bit_depth: int | None


@dataclass(frozen=True)
class CameraDispatch:
    backend: BackendPort
    command: svc.AcquisitionCameraCommand
    child_id: str
    deadline_ns: int


class CameraCommands:
    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        configuration: ConfigurationState,
        device: DeviceState,
        backends: Mapping[str, BackendPort],
        projections: ProjectionStore,
        file_policy_loader: Callable[[frozenset[str]], Mapping[str, Message]] | None,
        generation: str,
        limits: LimitsState,
        clock: Callable[[], int],
        hooks: DeviceHooks,
        status_retention: CameraStatusRetention,
    ) -> None:
        self.lifecycle = lifecycle
        self.configuration = configuration
        self.device = device
        self.backends = backends
        self.projections = projections
        self.file_policy_loader = file_policy_loader
        self.generation = generation
        self.limits = limits
        self.clock = clock
        self.hooks = hooks
        self.status_retention = status_retention
        self._report_devices: (
            Callable[[str, Message, int | None], Coroutine[Any, Any, pb.ReportReceipt]]
            | None
        ) = None
        self._warn: Callable[[str], None] = lambda message: None

    async def execute_camera_command(
        self, request: svc.CameraCommandRequest
    ) -> pb.CommandAdmission:
        operator_id = request.command.operator.command_id
        async with self.lifecycle.lock:
            selection = self._select_locked(
                request,
                allow_stale_stop_run=(
                    request.kind == svc.CAMERA_COMMAND_KIND_STOP_PREVIEW
                ),
            )
        if isinstance(selection, pb.CommandAdmission):
            return selection
        backend = selection.backend
        deadline_ns: int | None = None
        if request.kind == svc.CAMERA_COMMAND_KIND_STOP_PREVIEW:
            async with self.lifecycle.lock:
                try:
                    recovery = self._owned_edit_recovery_locked(request, backend)
                except ValueError as exc:
                    return self.hooks.admission(operator_id, error=str(exc))
            if recovery is not None:
                operation_id, source, work = recovery
                deadline_ns = (
                    self.clock()
                    + self.limits.current.setup_ns
                    + self.limits.current.recovery_ns
                )
                if not await recover_owned_edit_status(
                    backend=backend,
                    operation_id=operation_id,
                    source=source,
                    work=work,
                    report_devices=self._report_devices,
                    clock=self.clock,
                    deadline_ns=deadline_ns,
                ):
                    return self.hooks.admission(
                        operator_id,
                        error="owned camera cleanup status could not be reconciled",
                    )
            async with self.lifecycle.lock:
                refreshed = self._select_locked(request)
            if isinstance(refreshed, pb.CommandAdmission):
                return refreshed
            selection = refreshed
            backend = selection.backend
        policy: acquisition_pb.AcquisitionFilePolicies | None = None
        if request.kind != svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER:
            try:
                policy = await load_file_policies(
                    self.file_policy_loader, self.limits.current.validation_ns / 1e9
                )
                camera_policy(policy, request.camera)
            except Exception as exc:
                return self.hooks.admission(
                    operator_id, error=f"acquisition file policy unavailable: {exc}"
                )
        async with self.lifecycle.lock:
            try:
                dispatched = self._dispatch_locked(
                    request, selection, policy, deadline_ns=deadline_ns
                )
            except (RuntimeError, ValueError) as exc:
                return self.hooks.admission(operator_id, error=str(exc))
        if isinstance(dispatched, pb.CommandAdmission):
            return dispatched
        child_id = dispatched.child_id
        deadline_ns = dispatched.deadline_ns
        command = dispatched.command
        try:
            reply = await asyncio.wait_for(
                backend.execute_camera_command(command, deadline_ns=deadline_ns),
                remaining_seconds(deadline_ns, clock=self.clock),
            )
        except Exception as exc:
            async with self.lifecycle.lock:
                if (
                    self.device.camera_operation is not None
                    and self.device.camera_operation.child_id == child_id
                ):
                    self.device.camera_operation.timed_out = True
                    self.device.camera_operation.admission_unconfirmed = True
                    self.hooks.complete_operation(
                        operator_id,
                        success=False,
                        progress="camera command admission unconfirmed",
                        error=str(exc),
                    )
                    self.hooks.publish()
                    # Same deadline handling as an accepted command; a later
                    # report is still reconciled by child command ID.
                    self.hooks.spawn(self._camera_timeout(child_id, deadline_ns))
            return self.hooks.admission(operator_id, error=str(exc))
        if reply.result != pb.COMMAND_RESULT_ACCEPTED:
            async with self.lifecycle.lock:
                if (
                    self.device.camera_operation is not None
                    and self.device.camera_operation.child_id == child_id
                ):
                    self.hooks.complete_operation(
                        operator_id,
                        success=False,
                        progress="camera command rejected",
                        error=reply.failure.message,
                    )
                    operation = self.device.camera_operation
                    if operation is not None:
                        operation.admission_rejected = True
                        self.status_retention.release_unstarted(operation)
                        self.device.manual_effects_admitted = (
                            operation.manual_effects_before
                        )
                    self.device.camera_operation = None
                    self.device.camera_operation_changed.set()
                    self.hooks.publish()
            return self.hooks.admission(
                operator_id,
                error=reply.failure.message or "acquisition rejected camera command",
            )
        if request.kind == svc.CAMERA_COMMAND_KIND_STOP_PREVIEW:
            self.projections.retire_preview(request.preview_run_id)
        self.hooks.spawn(self._camera_timeout(child_id, deadline_ns))
        return self.hooks.admission(operator_id)

    def _select_locked(
        self,
        request: svc.CameraCommandRequest,
        *,
        allow_stale_stop_run: bool = False,
    ) -> CameraSelection | pb.CommandAdmission:
        operator_id = request.command.operator.command_id
        error = self.hooks.authorized(
            request.command,
            targets_work=request.kind == svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER,
        )
        backend = self.backends.get("acquisition")
        attached_session = (
            request.kind == svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER
            and self.lifecycle.session.phase == pb.SESSION_PHASE_RUNNING
        )
        if (
            error
            or self.lifecycle.startup_blocker
            or self.lifecycle.manual_control_cleanup_pending
            or backend is None
            or self.device.camera_operation is not None
            or self.device.configuration_edit is not None
            or self.lifecycle.session.cleanup_blockers
            or self.lifecycle.authority_lost
            or self.lifecycle.session.shutdown_requested
            or (
                self.lifecycle.session.phase != pb.SESSION_PHASE_CONFIGURATION
                and not attached_session
            )
        ):
            return self.hooks.admission(
                operator_id,
                error=error
                or self.lifecycle.startup_blocker
                or "camera operation unavailable or another operation pending",
            )
        if (
            not request.HasField("expected_configuration_revision")
            or request.expected_configuration_revision != self.configuration.revision
            or request.camera
            not in (
                camera_pb.CAMERA_ROLE_BEHAVIORAL,
                camera_pb.CAMERA_ROLE_TRACKING,
                camera_pb.CAMERA_ROLE_EYE_TRACKING,
            )
            or request.kind not in NO_PATH | REQUIRES_READBACK
            or not valid_preview_placement(request)
        ):
            return self.hooks.admission(
                operator_id, error="camera command shape or revision invalid"
            )
        if (
            request.kind in NO_PATH
            and request.HasField("path")
            or request.kind not in NO_PATH
            and (not request.HasField("path") or not request.path)
        ):
            return self.hooks.admission(
                operator_id, error="camera path does not match command kind"
            )
        if (
            request.kind in REQUIRES_RUN
            and not request.HasField("preview_run_id")
            or request.kind not in REQUIRES_RUN
            and request.HasField("preview_run_id")
        ):
            return self.hooks.admission(
                operator_id,
                error="preview run identity does not match command kind",
            )
        if request.kind == svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER:
            consumer = request.preview_consumer
            if (
                consumer.role not in {"gui", "cli"}
                or consumer.generation != request.command.operator.client_id
            ):
                return self.hooks.admission(
                    operator_id,
                    error="preview consumer is not the authenticated operator client",
                )
        elif request.HasField("preview_consumer"):
            return self.hooks.admission(
                operator_id, error="preview consumer is only valid for attachment"
            )
        settings = next(
            (
                item.acquisition
                for item in self.configuration.current.backends
                if item.backend_name == "acquisition" and item.enabled
            ),
            None,
        )
        if settings is None:
            return self.hooks.admission(
                operator_id, error="acquisition settings unavailable"
            )
        camera = getattr(settings, camera_role_name(request.camera))
        if not camera.device.device_id:
            return self.hooks.admission(
                operator_id, error="assigned camera device ID unresolved"
            )
        current_view = (
            getattr(self.projections.devices, camera_role_name(request.camera))
            if self.projections.devices
            else None
        )
        stale_stop_refresh = (
            allow_stale_stop_run
            and request.kind == svc.CAMERA_COMMAND_KIND_STOP_PREVIEW
        )
        cleanup_stop = (
            request.kind == svc.CAMERA_COMMAND_KIND_STOP_PREVIEW
            and current_view is not None
            and current_view.cleanup_pending
        )
        if (
            request.kind in REQUIRES_RUN
            and not stale_stop_refresh
            and (
                current_view is None
                or current_view.preview_run_id != request.preview_run_id
                or (not current_view.preview_running and not cleanup_stop)
            )
        ):
            return self.hooks.admission(
                operator_id, error="current preview run does not match"
            )
        if (
            request.kind == svc.CAMERA_COMMAND_KIND_START_PREVIEW
            and current_view is not None
            and current_view.preview_running
        ):
            return self.hooks.admission(operator_id, error="preview already running")
        revision = self.configuration.revision
        work = deepcopy(self.projections.work)
        selected = deepcopy(camera)
        bit_depth = (
            settings.preview_output_bit_depth
            if settings.HasField("preview_output_bit_depth")
            else None
        )
        return CameraSelection(backend, revision, work, selected, bit_depth)

    def _dispatch_locked(
        self,
        request: svc.CameraCommandRequest,
        selection: CameraSelection,
        policy: acquisition_pb.AcquisitionFilePolicies | None,
        *,
        deadline_ns: int | None = None,
    ) -> CameraDispatch | pb.CommandAdmission:
        operator_id = request.command.operator.command_id
        backend = selection.backend
        revision = selection.revision
        work = selection.work
        selected = selection.selected
        bit_depth = selection.bit_depth
        error = self.hooks.authorized(
            request.command,
            targets_work=request.kind == svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER,
        )
        if (
            error
            or self.configuration.revision != revision
            or deadline_ns is not None
            and self.clock() >= deadline_ns
            or self.device.camera_operation is not None
            or self.device.configuration_edit is not None
            or self.lifecycle.authority_lost
            or self.lifecycle.session.shutdown_requested
        ):
            return self.hooks.admission(
                operator_id,
                error=error or "camera operation retired before dispatch",
            )
        child_id = str(uuid.uuid4())
        if deadline_ns is None:
            deadline_ns = (
                self.clock()
                + self.limits.current.setup_ns
                + self.limits.current.recovery_ns
            )
        command = svc.AcquisitionCameraCommand(
            camera=request.camera,
            kind=request.kind,
            configuration_revision=revision,
        )
        command.settings.CopyFrom(
            next(
                item.acquisition
                for item in self.configuration.current.backends
                if item.backend_name == "acquisition"
            )
        )
        command.command.command_id = child_id
        command.command.issuer.CopyFrom(
            pb.ProcessIdentity(role="controller", generation=self.generation)
        )
        command.command.target.CopyFrom(backend.context)
        command.command.work.CopyFrom(work)
        command.command.parent_operation.command_id = operator_id
        if request.HasField("path"):
            command.path = request.path
        if request.HasField("preview_run_id"):
            command.preview_run_id = request.preview_run_id
        if request.HasField("preview_placement"):
            command.preview_placement.CopyFrom(request.preview_placement)
        if request.kind == svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER:
            command.preview_consumer.CopyFrom(request.preview_consumer)
            try:
                self.projections.expect_preview(
                    child_id,
                    request.preview_consumer,
                    request.preview_run_id,
                    request.camera,
                )
            except (ProjectionError, ValueError) as exc:
                return self.hooks.admission(operator_id, error=str(exc))
        else:
            assert policy is not None
            command.file_policies.CopyFrom(policy)
            command.requested.CopyFrom(selected.device)
            command.transport.CopyFrom(camera_policy(policy, request.camera).transport)
            if bit_depth is not None:
                command.preview_output_bit_depth = bit_depth
        operation = CameraOperation(
            operator_id,
            child_id,
            revision,
            request.camera,
            request.kind,
            work,
            deadline_ns,
            request.kind in REQUIRES_READBACK,
            request.path if request.HasField("path") else "",
            request.preview_run_id if request.HasField("preview_run_id") else "",
        )
        self.status_retention.prune()
        try:
            self.status_retention.reserve(operation)
        except (RuntimeError, ValueError):
            if request.kind == svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER:
                self.projections.cancel_preview_expectation(child_id)
            raise
        operation.manual_effects_before = self.device.manual_effects_admitted
        self.device.camera_operation = operation
        self.device.camera_operation_changed.clear()
        self.device.manual_effects_admitted = True
        self.hooks.operation(
            operator_id,
            "ExecuteCameraCommand",
            attempt=self.lifecycle.attempt,
            progress="acquisition command pending",
        )
        self.hooks.publish()
        return CameraDispatch(backend, command, child_id, deadline_ns)

    def bind_recovery(
        self,
        report_devices: Callable[
            [str, Message, int | None], Coroutine[Any, Any, pb.ReportReceipt]
        ],
        warn: Callable[[str], None],
    ) -> None:
        self._report_devices = report_devices
        self._warn = warn

    def _owned_edit_recovery_locked(
        self, request: svc.CameraCommandRequest, backend: BackendPort
    ) -> tuple[str, pb.BackendContext, pb.WorkContext] | None:
        if request.kind != svc.CAMERA_COMMAND_KIND_STOP_PREVIEW:
            return None
        if not self.device.configuration_edit_terminals:
            return None
        operation_id = next(reversed(self.device.configuration_edit_terminals))
        terminal = self.device.configuration_edit_terminals[operation_id]
        if terminal.device_status is not None:
            return None
        source = pb.BackendContext.FromString(
            terminal.source.SerializeToString(deterministic=True)
        )
        if operation_id != terminal.operation_id or source != backend.context:
            raise ValueError("owned camera cleanup terminal has stale source identity")
        return operation_id, source, pb.WorkContext()

    async def _camera_timeout(self, child_id: str, deadline_ns: int) -> None:
        await asyncio.sleep(remaining_seconds(deadline_ns, clock=self.clock))
        async with self.lifecycle.lock:
            operation = self.device.camera_operation
            if operation is None or operation.child_id != child_id:
                return
            operation.timed_out = True
            self.hooks.complete_operation(
                operation.operator_id,
                success=False,
                progress="camera command evidence timed out",
                error="exact completion missing",
            )
            if operation.admission_unconfirmed or operation.final_status is not None:
                # The expired command can no longer be admitted, or its terminal
                # report arrived but confirmation did not: free the slot.
                self.status_retention.retire_operation(operation)
            self.hooks.publish()
            if self.device.camera_operation is not operation:
                return
        await self._recover_terminal(operation)
        async with self.lifecycle.lock:
            if self.device.camera_operation is operation:
                self.status_retention.retire_operation(operation)
                self._warn(
                    "camera command result unconfirmed after its deadline and "
                    f"one recovery query: {operation.child_id}"
                )
                self.hooks.publish()

    async def _recover_terminal(self, operation: CameraOperation) -> None:
        """One bounded query of the child command's retained terminal result."""
        backend = self.backends.get("acquisition")
        report = self._report_devices
        if backend is None or report is None:
            return
        deadline_ns = self.clock() + self.limits.current.recovery_ns
        request = svc.RetainedResultQuery(
            query=svc.BackendQuery(target=backend.context, work=operation.work),
            command_id=operation.child_id,
        )
        try:
            retained = await asyncio.wait_for(
                backend.get_retained_result(request, deadline_ns=deadline_ns),
                remaining_seconds(deadline_ns, clock=self.clock),
            )
            if (
                retained.found
                and retained.backend == backend.context
                and retained.work == operation.work
                and retained.HasField("acquisition_device_result")
            ):
                await report(
                    "devices", retained.acquisition_device_result, self.clock()
                )
        except Exception:
            return
