"""Exact manual-preview ring and GUI transfer ownership (A03/A10)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from uuid import uuid4

from cephvr.acquisition.ports import ControllerPort, ResourcePort
from cephvr.acquisition.state import (
    CoordinatorIdentity,
    ResourceRecord,
    WorkerPreview,
)
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.resource_ledger import NativeResourceLedger
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger
from cephvr.shared.deadlines import remaining_seconds

_RELEASE_RECEIPT_RESERVATION_BYTES = 4096


class ManualPreviewTransferOwner:
    """Admit, confirm, retire and close only exact preview ring transfers."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        resources: dict[str, ResourceRecord],
        resource_ledger: NativeResourceLedger,
        resource_port: ResourcePort,
        controller: ControllerPort,
        commands: CommandLedger,
        find_preview: Callable[[str], WorkerPreview | None],
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.resources = resources
        self.resource_ledger = resource_ledger
        self.resource_port = resource_port
        self.controller = controller
        self.commands = commands
        self.find_preview = find_preview
        self.clock = clock
        self._retired: dict[str, WorkerPreview] = {}
        self._release_receipts: dict[tuple[str, str, str, str], bytes] = {}
        self._receipt_reservations: dict[tuple[str, str, str, str], str] = {}
        self._receipt_commands: dict[tuple[str, str, str, str], str] = {}
        self._receipt_scopes: dict[tuple[str, str, str, str], str] = {}

    async def attach(
        self,
        request: wire.AcquisitionCameraCommand,
        preview: WorkerPreview,
        *,
        deadline_ns: int,
    ) -> acq.FrameBufferAttachment:
        if preview.allocation_id is None:
            raise ValueError("preview allocation identity is absent")
        resource = self.resources.get(preview.allocation_id)
        if resource is None:
            raise ValueError("preview ring is not retained")
        self._prune_release_receipts()
        command_record = self.commands.get(request.command.command_id)
        if command_record is None:
            raise ValueError("viewer attachment command is not retained")
        attachment = acq.FrameBufferAttachment.FromString(
            resource.attachment.SerializeToString(deterministic=True)
        )
        transfer_id = str(uuid4())
        attachment.sync.transfer_id = transfer_id
        attachment.sync.target.CopyFrom(request.preview_consumer)
        receipt_key = (
            preview.run_id,
            preview.allocation_id,
            transfer_id,
            request.preview_consumer.generation,
        )
        self._reserve_release_receipt(receipt_key)
        self.resource_ledger.expect_attachment(
            resource.ledger_key,
            peer_instance_id=request.preview_consumer.generation,
            transfer_id=transfer_id,
        )
        self.retain_attachment(preview, attachment, request.preview_consumer)
        receipt = await self.controller.report_preview_attachment(
            wire.PreviewAttachmentReport(
                source=self.identity.backend,
                operation=control.OperationContext(
                    command_id=request.command.command_id
                ),
                attachment=attachment,
            ),
            deadline_ns=deadline_ns,
        )
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError("controller rejected viewer transfer")
        return attachment

    async def attach_tracking(
        self,
        request: wire.AcquisitionTrackingDiagnosticAttachmentCommand,
        preview: WorkerPreview,
        *,
        deadline_ns: int,
    ) -> acq.FrameBufferAttachment:
        allocation_id = preview.tracking_allocation_id
        if allocation_id is None or preview.tracking_attachment is None:
            raise ValueError("ordered Tracking diagnostic source is unavailable")
        if preview.tracking_viewer is not None:
            if preview.tracking_viewer != request.tracking_consumer:
                raise ValueError("another diagnostic consumer owns this preview run")
            raise ValueError("diagnostic source transfer is already active")
        resource = self.resources.get(allocation_id)
        command_record = self.commands.get(request.command.command_id)
        if resource is None or command_record is None:
            raise ValueError("diagnostic source or command is not retained")
        attachment = acq.FrameBufferAttachment.FromString(
            resource.attachment.SerializeToString(deterministic=True)
        )
        attachment.sync.transfer_id = str(uuid4())
        attachment.sync.target.CopyFrom(request.tracking_consumer)
        receipt_key = (
            preview.run_id,
            allocation_id,
            attachment.sync.transfer_id,
            request.tracking_consumer.generation,
        )
        self._reserve_release_receipt(receipt_key)
        self.resource_ledger.expect_attachment(
            resource.ledger_key,
            peer_instance_id=request.tracking_consumer.generation,
            transfer_id=attachment.sync.transfer_id,
        )
        preview.tracking_viewer = control.ProcessIdentity.FromString(
            request.tracking_consumer.SerializeToString(deterministic=True)
        )
        preview.tracking_viewer_transfer_id = attachment.sync.transfer_id
        preview.tracking_viewer_released_event.clear()
        receipt = await self.controller.report_preview_attachment(
            wire.PreviewAttachmentReport(
                source=self.identity.backend,
                operation=control.OperationContext(
                    command_id=request.command.command_id
                ),
                attachment=attachment,
            ),
            deadline_ns=deadline_ns,
        )
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            preview.tracking_viewer = None
            preview.tracking_viewer_transfer_id = None
            raise RuntimeError("controller rejected ordered Tracking transfer")
        return attachment

    def retain_attachment(
        self,
        preview: WorkerPreview,
        attachment: acq.FrameBufferAttachment,
        consumer: control.ProcessIdentity,
    ) -> None:
        preview.viewer = control.ProcessIdentity.FromString(
            consumer.SerializeToString(deterministic=True)
        )
        preview.viewer_transfer_id = attachment.sync.transfer_id
        preview.viewer_released_event.clear()
        preview.attachment = acq.FrameBufferAttachment.FromString(
            attachment.SerializeToString(deterministic=True)
        )

    def report_consumer(
        self, request: wire.PreviewConsumerReport
    ) -> control.ReportReceipt:
        self._prune_release_receipts()
        receipt_key = (
            request.preview_run_id,
            request.allocation_id,
            request.transfer_id,
            request.consumer.generation,
        )
        serialized = request.SerializeToString(deterministic=True)
        accepted = self._release_receipts.get(receipt_key)
        if accepted is not None:
            if accepted == serialized:
                return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)
            return _rejected(
                "PREVIEW_TRANSFER", "consumer retry changed its exact release report"
            )
        preview = self.find_preview(request.preview_run_id) or self._retired.get(
            request.preview_run_id
        )
        tracking_transfer = (
            preview is not None
            and preview.tracking_viewer == request.consumer
            and preview.tracking_viewer_transfer_id == request.transfer_id
            and preview.tracking_allocation_id == request.allocation_id
        )
        viewer_transfer = (
            preview is not None
            and preview.viewer == request.consumer
            and preview.viewer_transfer_id == request.transfer_id
            and preview.allocation_id == request.allocation_id
        )
        if (
            preview is None
            or request.controller_generation != self.identity.controller.generation
            or request.client_id != request.consumer.generation
            or not (tracking_transfer or viewer_transfer)
            or request.result
            not in {
                wire.PREVIEW_CONSUMER_RESULT_ATTACHED,
                wire.PREVIEW_CONSUMER_RESULT_RELEASED,
                wire.PREVIEW_CONSUMER_RESULT_FAILED,
            }
        ):
            return _rejected(
                "PREVIEW_TRANSFER",
                "consumer report differs from the exact retained transfer",
            )
        resource = self.resources.get(request.allocation_id)
        if resource is None:
            return _rejected(
                "PREVIEW_RESOURCE", "preview owner resource is no longer retained"
            )
        peer = request.consumer.generation
        try:
            if request.result == wire.PREVIEW_CONSUMER_RESULT_ATTACHED:
                self.resource_ledger.confirm_attachment(
                    resource.ledger_key,
                    peer_instance_id=peer,
                    transfer_id=request.transfer_id,
                )
            elif request.result == wire.PREVIEW_CONSUMER_RESULT_RELEASED:
                if len(serialized) > _RELEASE_RECEIPT_RESERVATION_BYTES:
                    return _rejected(
                        "PREVIEW_RELEASE",
                        "release receipt exceeds its retained reservation",
                    )
                self.resource_ledger.confirm_release(
                    resource.ledger_key,
                    peer_instance_id=peer,
                    transfer_id=request.transfer_id,
                )
                if tracking_transfer:
                    preview.tracking_viewer = None
                    preview.tracking_viewer_transfer_id = None
                    preview.tracking_viewer_released_event.set()
                    self._close_tracking_resource(preview)
                    self.close_retired_resource(preview)
                else:
                    preview.viewer = None
                    preview.viewer_transfer_id = None
                    preview.viewer_released_event.set()
                    self.close_retired_resource(preview)
                self._retain_release_receipt(receipt_key, serialized)
            else:
                self.resource_ledger.retire(
                    resource.ledger_key, reason="preview consumer reported failure"
                )
        except (RuntimeError, ValueError) as exc:
            return _rejected("PREVIEW_RELEASE", str(exc))
        return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)

    def retire(self, preview: WorkerPreview) -> None:
        allocation_id = preview.allocation_id
        if allocation_id is None:
            return
        for run_id, retired in tuple(self._retired.items()):
            if retired.allocation_id not in self.resources:
                self._retired.pop(run_id, None)
        if preview.run_id not in self._retired and len(self._retired) >= 64:
            raise RuntimeError("retired preview ownership capacity is exhausted")
        self._retired[preview.run_id] = preview
        resource = self.resources.get(allocation_id)
        if resource is None:
            return
        if resource.ring is not None:
            resource.ring.retire("manual preview stopped")
        self.resource_ledger.retire(
            resource.ledger_key, reason="manual preview stopped"
        )
        tracking_id = preview.tracking_allocation_id
        tracking = None if tracking_id is None else self.resources.get(tracking_id)
        if tracking is not None:
            if tracking.ring is not None:
                tracking.ring.retire("manual tracking diagnostic source stopped")
            self.resource_ledger.retire(
                tracking.ledger_key,
                reason="manual tracking diagnostic source stopped",
            )
        self._close_tracking_resource(preview)

    async def retire_and_release(
        self, preview: WorkerPreview, *, deadline_ns: int
    ) -> None:
        """Retire one preview and prove both consumer and ring releases."""
        self.retire(preview)
        self.close_retired_resource(preview)
        if preview.viewer is not None:
            await _wait_release_event(
                preview.viewer_released_event, deadline_ns, self.clock
            )
            if preview.viewer is not None:
                raise RuntimeError(
                    "preview viewer release did not retire exact transfer"
                )
        if preview.tracking_viewer is not None:
            await _wait_release_event(
                preview.tracking_viewer_released_event, deadline_ns, self.clock
            )
            if preview.tracking_viewer is not None:
                raise RuntimeError(
                    "Tracking viewer release did not retire exact transfer"
                )
        self.close_retired_resource(preview)
        retained = {
            allocation_id
            for allocation_id in (
                preview.allocation_id,
                preview.tracking_allocation_id,
            )
            if allocation_id is not None and allocation_id in self.resources
        }
        if retained:
            raise RuntimeError("preview ring ownership remains unresolved")

    def close_retired_resource(self, preview: WorkerPreview) -> None:
        tracking_id = preview.tracking_allocation_id
        if tracking_id is not None and tracking_id in self.resources:
            return
        allocation_id = preview.allocation_id
        if allocation_id is None:
            return
        resource = self.resources.get(allocation_id)
        if resource is None:
            self._retired.pop(preview.run_id, None)
            return
        if not self.resource_ledger.may_close_owner(resource.ledger_key):
            return
        self.resource_port.release_ring(allocation_id)
        self.resource_ledger.confirm_owner_release(resource.ledger_key)
        self.resource_ledger.remove_completed_resource(resource.ledger_key)
        self.resources.pop(allocation_id, None)
        self._retired.pop(preview.run_id, None)

    def _close_tracking_resource(self, preview: WorkerPreview) -> None:
        allocation_id = preview.tracking_allocation_id
        if allocation_id is None:
            return
        resource = self.resources.get(allocation_id)
        if resource is None or not self.resource_ledger.may_close_owner(
            resource.ledger_key
        ):
            return
        self.resource_port.release_ring(allocation_id)
        self.resource_ledger.confirm_owner_release(resource.ledger_key)
        self.resource_ledger.remove_completed_resource(resource.ledger_key)
        self.resources.pop(allocation_id, None)

    def _retain_release_receipt(
        self, key: tuple[str, str, str, str], serialized: bytes
    ) -> None:
        reservation = self._receipt_reservations.get(key)
        command_id = self._receipt_commands.get(key)
        if reservation is None or command_id is None:
            raise RuntimeError("viewer release has no pre-reserved receipt ownership")
        if len(serialized) > _RELEASE_RECEIPT_RESERVATION_BYTES:
            raise ValueError("viewer release receipt exceeds its reservation")
        scope = self._receipt_scopes.get(key)
        if scope is None:
            raise RuntimeError("viewer release lacks its retained transfer scope")
        now_ns = self.clock()
        self.commands.complete(command_id, serialized, now_ns)
        self.commands.finalize_work(scope, now_ns)
        self._release_receipts[key] = serialized

    def _reserve_release_receipt(self, key: tuple[str, str, str, str]) -> None:
        scope = str(uuid4())
        command_id = str(uuid4())
        reservation = _receipt_reservation_key(key)
        canonical = b"manual-preview-release\0" + "\0".join(key).encode("utf-8")
        self.commands.admit(
            command_id,
            canonical,
            self.clock(),
            work_key=scope,
            result_reservation_bytes=_RELEASE_RECEIPT_RESERVATION_BYTES,
            priority=True,
        )
        try:
            self.commands.reserve_payload(
                reservation,
                _RELEASE_RECEIPT_RESERVATION_BYTES,
                work_key=scope,
                priority=True,
            )
        except Exception:
            now_ns = self.clock()
            self.commands.complete(command_id, b"reservation failed", now_ns)
            self.commands.finalize_work(scope, now_ns)
            raise
        self._receipt_reservations[key] = reservation
        self._receipt_commands[key] = command_id
        self._receipt_scopes[key] = scope

    def _prune_release_receipts(self) -> None:
        self.commands.prune(self.clock())
        for key, reservation in tuple(self._receipt_reservations.items()):
            if not self.commands.has_payload(reservation):
                self._receipt_reservations.pop(key, None)
                self._receipt_commands.pop(key, None)
                self._receipt_scopes.pop(key, None)
                self._release_receipts.pop(key, None)


def _receipt_reservation_key(key: tuple[str, str, str, str]) -> str:
    return "manual-preview-release:" + ":".join(key)


def _rejected(code: str, message: str) -> control.ReportReceipt:
    return control.ReportReceipt(
        result=control.COMMAND_RESULT_REJECTED,
        failure=control.Failure(code=code, message=message[:2048]),
    )


async def _wait_release_event(
    event: asyncio.Event, deadline_ns: int, clock: Callable[[], int]
) -> None:
    remaining = remaining_seconds(deadline_ns, clock=clock)
    if remaining <= 0:
        raise TimeoutError("preview transfer release missed its retained deadline")
    await asyncio.wait_for(event.wait(), remaining)
