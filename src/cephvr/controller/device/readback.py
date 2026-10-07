"""Acquisition camera readback validation and completion evidence."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Mapping

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.device.ports import DeviceHooks
from cephvr.controller.device.release_evidence import (
    camera_view,
    finish_editing_confirmed,
    stop_preview_confirmed,
)
from cephvr.controller.device.status_retention import CameraStatusRetention
from cephvr.controller.microcontroller.protocol import PROTOCOL_VERSION
from cephvr.controller.ports import BackendPort
from cephvr.controller.projections import ProjectionStore
from cephvr.controller.resolution import resolved_configuration
from cephvr.controller.state import (
    CameraOperation,
    ConfigurationState,
    DeviceState,
    LifecycleState,
)


class CameraReadback:
    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        configuration: ConfigurationState,
        device: DeviceState,
        backends: Mapping[str, BackendPort],
        projections: ProjectionStore,
        validators: Mapping[
            str, Callable[[pb.ExperimentConfiguration], pb.ValidationResult]
        ],
        generation: str,
        clock: Callable[[], int],
        hooks: DeviceHooks,
        status_retention: CameraStatusRetention,
    ) -> None:
        self.lifecycle = lifecycle
        self.configuration = configuration
        self.device = device
        self.backends = backends
        self.projections = projections
        self.validators = validators
        self.generation = generation
        self.clock = clock
        self.hooks = hooks
        self.status_retention = status_retention

    async def adopt_camera_resolution(
        self, operation: CameraOperation, report: svc.AcquisitionResolutionReport
    ) -> None:
        try:
            setting = next(
                item.acquisition
                for item in self.configuration.current.backends
                if item.backend_name == "acquisition" and item.enabled
            )
            expected_pulses = (
                operation.kind == svc.CAMERA_COMMAND_KIND_START_PREVIEW
                and bool(setting.pulses.port)
            )
            backend = self.backends["acquisition"]
            candidate = resolved_configuration(
                self.configuration.current,
                report,
                source=backend.context,
                work=operation.work,
                operation_id=operation.child_id,
                revision=operation.revision,
                expected_cameras=frozenset({operation.camera}),
                expect_pulses=expected_pulses,
            )
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        asyncio.to_thread(validator, candidate)
                        for validator in self.validators.values()
                    )
                ),
                max(0, (operation.deadline_ns - self.clock()) / 1e9),
            )
            if not results or any(
                not result.completed or not result.valid for result in results
            ):
                raise RuntimeError(
                    "camera readback failed pure configuration validation"
                )
            async with self.lifecycle.lock:
                if (
                    self.device.camera_operation is not operation
                    or self.configuration.revision != operation.revision
                    or self.clock() > operation.deadline_ns
                    or self.lifecycle.authority_lost
                ):
                    raise RuntimeError("camera readback retired before adoption")
                # C12: the candidate stays aside until acquisition accepts it.
                new_revision = self.configuration.revision + (
                    candidate != self.configuration.current
                )
                confirmed = next(
                    item.acquisition
                    for item in candidate.backends
                    if item.backend_name == "acquisition" and item.enabled
                )
                confirmation = svc.AcquisitionConfigurationConfirmation(
                    resolution_operation=report.operation,
                    requested_configuration_revision=operation.revision,
                    confirmed_configuration_revision=new_revision,
                    confirmed=confirmed,
                )
                confirmation.command.command_id = str(uuid.uuid4())
                confirmation.command.issuer.CopyFrom(
                    pb.ProcessIdentity(role="controller", generation=self.generation)
                )
                confirmation.command.target.CopyFrom(backend.context)
                confirmation.command.work.CopyFrom(operation.work)
                confirmation.command.parent_operation.command_id = operation.child_id
                if report.HasField("pulses"):
                    confirmation.confirmed_pulses.CopyFrom(report.pulses)
            reply = await asyncio.wait_for(
                backend.confirm_configuration(
                    confirmation, deadline_ns=operation.deadline_ns
                ),
                max(0, (operation.deadline_ns - self.clock()) / 1e9),
            )
            if reply.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(
                    reply.failure.message
                    or "acquisition rejected readback confirmation"
                )
            async with self.lifecycle.lock:
                if (
                    self.device.camera_operation is operation
                    and self.clock() <= operation.deadline_ns
                ):
                    if self.configuration.revision != operation.revision:
                        raise RuntimeError("camera readback revision changed")
                    if new_revision != self.configuration.revision:
                        self.configuration.current.CopyFrom(candidate)
                        self.configuration.revision = new_revision
                        self.projections.set_scope(self.projections.work, new_revision)
                    operation.confirmed = True
                    self.finish_camera_operation(operation)
                    self.hooks.publish()
        except Exception as exc:
            async with self.lifecycle.lock:
                if self.device.camera_operation is operation:
                    self.hooks.complete_operation(
                        operation.operator_id,
                        success=False,
                        progress="camera readback or confirmation failed",
                        error=str(exc),
                    )
                    self.status_retention.retire_operation(operation)
                    self.hooks.publish()

    def finish_camera_operation(self, operation: CameraOperation) -> None:
        status = operation.final_status
        if status is None or self.device.camera_operation is not operation:
            return
        if operation.timed_out:
            self.status_retention.retire_operation(operation)
            return
        if not status.result.HasField("succeeded"):
            return
        if (
            status.result.succeeded
            and operation.readback_required
            and not operation.confirmed
        ):
            return
        if operation.is_microcontroller:
            diagnostic = status.views.diagnostic
            success = bool(status.result.succeeded)
            if operation.kind == svc.MICROCONTROLLER_COMMAND_KIND_CONNECT:
                success = (
                    success
                    and status.views.pulses.capabilities.protocol_version
                    == PROTOCOL_VERSION
                    and not status.views.pulses.state.behavioral.running
                    and not status.views.pulses.state.tracking.running
                )
            else:
                success = success and diagnostic.HasField("active")
                if operation.kind == svc.MICROCONTROLLER_COMMAND_KIND_START:
                    success = success and diagnostic.active
                if operation.kind == svc.MICROCONTROLLER_COMMAND_KIND_STOP:
                    success = success and not diagnostic.active
            self.hooks.complete_operation(
                operation.operator_id,
                success=success,
                progress="MCU command confirmed" if success else "MCU command failed",
                error=(
                    status.result.failure.message
                    or "required MCU result evidence incomplete"
                )
                if not success
                else "",
            )
            self.status_retention.retire_operation(operation)
            return
        view = camera_view(operation.camera, status.views)
        success = bool(status.result.succeeded)
        if operation.kind == svc.CAMERA_COMMAND_KIND_START_PREVIEW:
            success = (
                success
                and view.HasField("preview_running")
                and view.preview_running
                and view.HasField("preview_run_id")
                and bool(view.preview_run_id)
                and not view.cleanup_pending
            )
        elif operation.kind == svc.CAMERA_COMMAND_KIND_STOP_PREVIEW:
            success = success and stop_preview_confirmed(view, operation.preview_run_id)
        elif operation.kind in {
            svc.CAMERA_COMMAND_KIND_SHOW_PREVIEW,
            svc.CAMERA_COMMAND_KIND_HIDE_PREVIEW,
        }:
            success = (
                success
                and view.preview_run_id == operation.preview_run_id
                and view.HasField("preview_visible")
                and view.preview_visible
                == (operation.kind == svc.CAMERA_COMMAND_KIND_SHOW_PREVIEW)
            )
        elif (
            operation.kind == svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER and success
        ):
            transfer = self.projections.transfers.get(operation.child_id)
            if transfer is None or transfer.result is None:
                return
            success = (
                success
                and transfer.result.result == svc.PREVIEW_CONSUMER_RESULT_ATTACHED
            )
        elif operation.kind == svc.CAMERA_COMMAND_KIND_EXPORT_PFS:
            success = (
                success
                and status.HasField("exported_pfs_path")
                and status.exported_pfs_path == operation.path
            )
        elif operation.kind == svc.CAMERA_COMMAND_KIND_TEST_CONNECTION:
            success = (
                success and view.HasField("device_open") and not view.cleanup_pending
            )
        elif operation.kind == svc.CAMERA_COMMAND_KIND_FINISH_EDITING:
            success = success and finish_editing_confirmed(view, require_closed=False)
        self.hooks.complete_operation(
            operation.operator_id,
            success=success,
            progress="camera command confirmed" if success else "camera command failed",
            error=(
                status.result.failure.message
                if not status.result.succeeded and status.result.failure.message
                else "required camera result evidence incomplete"
            )
            if not success
            else "",
        )
        self.status_retention.retire_operation(operation)
