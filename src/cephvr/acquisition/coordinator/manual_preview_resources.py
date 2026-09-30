"""Capacity-one run-scoped preview slot construction (A03/A10)."""

from __future__ import annotations

from uuid import UUID, uuid4

from cephvr.acquisition.buffers.layout import allocation_size
from cephvr.acquisition.camera.native_formats import pylon_pixel_format
from cephvr.acquisition.coordinator.session_resources import retain_ring
from cephvr.acquisition.ports import ResourcePort
from cephvr.acquisition.state import ResourceRecord, WorkerRecord
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.events import event_name
from cephvr.platform.windows.resource_ledger import NativeResourceLedger
from cephvr.shared.pixels.types import PixelLayout


async def allocate_manual_preview_slot(
    *,
    worker: WorkerRecord,
    resolved: camera.CameraResolvedState,
    controller: control.ProcessIdentity,
    run_id: str,
    configuration_revision: int,
    resources: dict[str, ResourceRecord],
    ledger: NativeResourceLedger,
    resource_port: ResourcePort,
) -> tuple[acq.FrameBufferAttachment, ResourceRecord]:
    """Create a fresh single-slot PREVIEW resource bound to this exact run."""
    if (
        worker.context.work.WhichOneof("work") is not None
        or not resolved.HasField("layout")
        or configuration_revision < 0
        or not run_id
    ):
        raise ValueError("manual preview slot identity or layout is incomplete")
    layout_message = resolved.layout
    if (
        layout_message.width <= 0
        or layout_message.height <= 0
        or layout_message.row_stride_bytes <= 0
        or layout_message.image_payload_bytes <= 0
        or not layout_message.pixel_format
    ):
        raise ValueError("resolved preview image layout is incomplete")
    pixel_format = pylon_pixel_format(layout_message.pixel_format)
    layout = PixelLayout(
        int(layout_message.width),
        int(layout_message.height),
        pixel_format,
        int(layout_message.row_stride_bytes),
        int(layout_message.image_payload_bytes),
    )
    allocation_id_value = str(uuid4())
    descriptor = acq.FrameBufferDescriptor(
        allocation_id=allocation_id_value,
        owner=worker.launch.owner,
        producer=worker.launch.worker,
        camera=worker.context.camera,
        kind=acq.FRAME_BUFFER_KIND_PREVIEW,
        layout_version=2,
        capacity_frames=1,
        shared_memory_name=f"Local\\cephvr-{allocation_id_value}-frames",
        configuration_revision=configuration_revision,
        allocation_bytes=allocation_size(1, layout.image_payload_bytes),
    )
    descriptor.preview.controller.CopyFrom(controller)
    descriptor.preview.acquisition_run_id = run_id
    descriptor.image.width = layout.width
    descriptor.image.height = layout.height
    descriptor.image.pixel_format = pixel_format.sdk_name
    descriptor.image.row_stride_bytes = layout.row_stride_bytes
    descriptor.image.image_payload_bytes = layout.image_payload_bytes
    attachment = acq.FrameBufferAttachment(buffer=descriptor)
    attachment.sync.transfer_id = str(uuid4())
    attachment.sync.target.CopyFrom(worker.launch.worker)
    attachment.sync.event_name = event_name(UUID(allocation_id_value))
    await retain_ring(
        attachment,
        layout,
        owner=worker.launch.owner,
        resources=resources,
        ledger=ledger,
        port=resource_port,
        declare_resource=_no_catalogue_resource,
    )
    resource = resources[allocation_id_value]
    return attachment, resource


async def _no_catalogue_resource(
    _owner: control.ProcessIdentity, _allocation_id: str
) -> None:
    """Manual resources have no active session catalogue to declare into."""
