"""Authenticated device projection evidence and snapshot updates."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.device.ports import DeviceHooks
from cephvr.controller.device.status_retention import CameraStatusRetention
from cephvr.controller.projections import ProjectionError, ProjectionStore
from cephvr.controller.state import (
    CameraOperation,
    ConfigurationState,
    DeviceState,
    LifecycleState,
)
from cephvr.vr.v1 import runtime_pb2 as vr_pb


class DeviceViews:
    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        configuration: ConfigurationState,
        device: DeviceState,
        projections: ProjectionStore,
        clock: Callable[[], int],
        hooks: DeviceHooks,
        finish_camera_operation: Callable[[CameraOperation], None],
        status_retention: CameraStatusRetention,
    ) -> None:
        self.lifecycle = lifecycle
        self.configuration = configuration
        self.device = device
        self.projections = projections
        self.clock = clock
        self.hooks = hooks
        self.finish_camera_operation = finish_camera_operation
        self.status_retention = status_retention

    async def report_projection(
        self, kind: str, report: Message, ingress_ns: int | None = None
    ) -> pb.ReportReceipt:
        observed_ingress = self.clock() if ingress_ns is None else ingress_ns
        async with self.lifecycle.lock:
            try:
                if kind == "devices":
                    status = cast(svc.AcquisitionDeviceStatusReport, report)
                    operation = self.device.camera_operation
                    if (
                        operation is None
                        or status.operation.command_id != operation.child_id
                    ):
                        completed = self.status_retention.find(
                            status.operation.command_id
                        )
                        if completed is None:
                            raise ProjectionError(
                                "device status has no retained camera command"
                            )
                        self.projections.validate_devices(status)
                        if (
                            status.work != completed.work
                            or status.result.context.command_id != completed.child_id
                            or status.result.work != completed.work
                            or not status.result.complete
                        ):
                            raise ProjectionError(
                                "camera operation retry differs from its retained terminal evidence"
                            )
                        if completed.final_status is None:
                            # The slot was freed without terminal evidence: the
                            # first exact report is retained and adopted if newer.
                            if not status.result.HasField("succeeded"):
                                raise ProjectionError(
                                    "camera operation result work or deadline mismatch"
                                )
                            changed = self.projections.accept_newer_devices(status)
                            self.status_retention.retain_terminal(completed, status)
                            if changed:
                                self.hooks.publish()
                            return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
                        if completed.final_status.SerializeToString(
                            deterministic=True
                        ) != status.SerializeToString(deterministic=True):
                            raise ProjectionError(
                                "camera operation retry differs from its retained terminal evidence"
                            )
                        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
                    if (
                        status.work != operation.work
                        or status.result.context.command_id != operation.child_id
                        or status.result.work != operation.work
                        or (
                            status.result.complete
                            and not status.result.HasField("succeeded")
                        )
                    ):
                        raise ProjectionError(
                            "camera operation result work or deadline mismatch"
                        )
                    if operation.final_status is not None:
                        self.status_retention.retain_terminal(operation, status)
                        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
                    if observed_ingress > operation.deadline_ns:
                        self.projections.validate_devices(status)
                        if not status.result.complete:
                            raise ProjectionError(
                                "late camera operation evidence is not terminal"
                            )
                        # Late evidence updates the view only if newer; the
                        # operation stays timed out and is never relabeled timely.
                        self.projections.accept_newer_devices(status)
                        self.status_retention.retain_terminal(operation, status)
                        operation.timed_out = True
                        self.hooks.complete_operation(
                            operation.operator_id,
                            success=False,
                            progress="camera command evidence arrived late",
                            error="exact completion missed its original deadline",
                        )
                        self.finish_camera_operation(operation)
                        self.hooks.publish()
                        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
                    changed = self.projections.accept_devices(status)
                    if status.result.complete:
                        self.status_retention.retain_terminal(operation, status)
                        self.finish_camera_operation(operation)
                elif kind == "warnings":
                    changed = self.projections.accept_warnings(
                        cast(svc.AcquisitionWarningReport, report)
                    )
                elif kind == "display":
                    display_view = cast(pb.VRDisplayView, report)
                    pending = self.device.display_pending
                    if (
                        pending is None
                        or display_view.command_id != pending[0]
                        or observed_ingress > pending[2]
                        or self.configuration.revision != pending[1]
                    ):
                        raise ProjectionError(
                            "display result is stale or its original deadline elapsed"
                        )
                    changed = self.projections.accept_display(display_view)
                    if display_view.complete:
                        actual = {item.output_id for item in display_view.outputs}
                        successful = (
                            display_view.HasField("applied_revision")
                            and display_view.applied_revision == pending[1]
                            and actual == pending[3]
                            and len(display_view.outputs) == len(pending[3])
                            and not display_view.issues
                            and all(
                                item.HasField("resources_ready")
                                and item.resources_ready
                                and item.idle_submission
                                == vr_pb.SUBMISSION_OUTCOME_RETURNED
                                and item.HasField("idle_swap_return_ns")
                                for item in display_view.outputs
                            )
                        )
                        self.hooks.complete_operation(
                            pending[0],
                            success=successful,
                            progress="Idle output confirmed"
                            if successful
                            else "display initialization failed",
                            error="required Idle output evidence incomplete"
                            if not successful
                            else "",
                        )
                        self.device.display_pending = None
                elif kind == "preview":
                    changed = self.projections.accept_preview(
                        cast(svc.PreviewAttachmentReport, report)
                    )
                else:
                    raise ProjectionError("unknown projection report")
            except (ProjectionError, ValueError) as exc:
                return pb.ReportReceipt(
                    result=pb.COMMAND_RESULT_REJECTED,
                    failure=pb.Failure(code="EVIDENCE", message=str(exc)),
                )
            if changed and kind != "preview":
                self.hooks.publish()
            return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
