"""Preview attachment queries and consumer release coordination."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.device.ports import DeviceHooks
from cephvr.controller.ports import BackendPort, SupervisorPort
from cephvr.controller.projections import ProjectionError, ProjectionStore
from cephvr.controller.receipts import rejected_receipt
from cephvr.controller.state import (
    CameraOperation,
    DeviceState,
    LifecycleState,
    LimitsState,
)


class PreviewHandling:
    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        device: DeviceState,
        backends: Mapping[str, BackendPort],
        supervisor: SupervisorPort | None,
        projections: ProjectionStore,
        limits: LimitsState,
        hooks: DeviceHooks,
        finish_camera_operation: Callable[[CameraOperation], None],
    ) -> None:
        self.lifecycle = lifecycle
        self.device = device
        self.backends = backends
        self.supervisor = supervisor
        self.projections = projections
        self.limits = limits
        self.hooks = hooks
        self.finish_camera_operation = finish_camera_operation

    async def get_preview_attachment(
        self, query: svc.PreviewAttachmentQuery
    ) -> svc.PreviewAttachmentResult:
        async with self.lifecycle.lock:
            try:
                return self.projections.preview(query)
            except (ProjectionError, ValueError) as exc:
                return svc.PreviewAttachmentResult(
                    available=False,
                    failure=pb.Failure(code="EVIDENCE", message=str(exc)),
                )

    async def report_preview_consumer_state(
        self, report: svc.PreviewConsumerReport
    ) -> pb.ReportReceipt:
        async with self.lifecycle.lock:
            try:
                self.projections.preview_result(report)
            except (ProjectionError, ValueError) as exc:
                return rejected_receipt("EVIDENCE", str(exc))
        acquisition = self.backends.get("acquisition")
        if acquisition is None or self.supervisor is None:
            return rejected_receipt(
                "UNAVAILABLE", "preview release recipients unavailable"
            )
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    acquisition.report_preview_consumer_state(report),
                    self.supervisor.report_preview_consumer_state(report),
                ),
                self.limits.current.registration_ns / 1e9,
            )
        except Exception as exc:
            return rejected_receipt("HANDOFF", str(exc))
        if any(item.result != pb.COMMAND_RESULT_ACCEPTED for item in results):
            return rejected_receipt(
                "HANDOFF", "preview consumer result was not retained by every owner"
            )
        async with self.lifecycle.lock:
            operation = self.device.camera_operation
            if (
                operation is not None
                and operation.kind == svc.CAMERA_COMMAND_KIND_ATTACH_PREVIEW_VIEWER
                and operation.preview_run_id == report.preview_run_id
            ):
                self.finish_camera_operation(operation)
                self.hooks.publish()
        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
