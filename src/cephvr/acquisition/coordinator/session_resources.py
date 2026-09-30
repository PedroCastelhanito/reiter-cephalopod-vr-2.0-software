"""A03 session ring descriptors and transfer reservations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from cephvr.acquisition.buffers.layout import allocation_size
from cephvr.acquisition.buffers.ring import RingAllocationError
from cephvr.acquisition.camera.native_formats import pylon_pixel_format
from cephvr.acquisition.ports import ResourcePort
from cephvr.acquisition.state import ResourceRecord, SessionRecord, WorkerRecord
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.events import event_name
from cephvr.platform.windows.resource_ledger import NativeResourceLedger, ResourceKey
from cephvr.shared.pixels.types import PixelLayout


async def allocate_camera_outputs(
    *,
    session: SessionRecord,
    worker: WorkerRecord,
    resolved: camera.CameraResolvedState,
    tracking_consumer: control.ProcessIdentity,
    tracking_required: bool,
    settings: control.AcquisitionSettings,
    resources: dict[str, ResourceRecord],
    ledger: NativeResourceLedger,
    port: ResourcePort,
    declare_resource: Callable[[control.ProcessIdentity, str], Awaitable[None]],
) -> tuple[tuple[acq.FrameBufferAttachment, ...], acq.FrameBufferAttachment | None]:
    """Create only this camera's locked-session tracking/preview rings."""
    layout = _layout(resolved)
    if not settings.HasField("session_preview_max_hz"):
        raise ValueError("session preview rate cap is unresolved")
    save_preview = settings.session_preview_max_hz > 0
    create_tracking = (
        worker.context.camera == camera.CAMERA_ROLE_TRACKING and tracking_required
    )
    attachments: list[acq.FrameBufferAttachment] = []
    tracking_input: acq.FrameBufferAttachment | None = None
    expected: set[str] = set()
    if create_tracking:
        if (
            not settings.HasField("tracking_ring_frames")
            or settings.tracking_ring_frames <= 0
        ):
            raise ValueError(
                "enabled tracking camera requires a positive ring capacity"
            )
        capacity = int(settings.tracking_ring_frames)
        producer_attachment, consumer_attachment = _new_ring(
            worker=worker,
            session=session,
            layout=layout,
            owner=worker.launch.owner,
            camera_role=worker.context.camera,
            kind=acq.FRAME_BUFFER_KIND_TRACKING,
            capacity=capacity,
            consumer=tracking_consumer,
        )
        await retain_ring(
            producer_attachment,
            layout,
            owner=worker.launch.owner,
            resources=resources,
            ledger=ledger,
            port=port,
            declare_resource=declare_resource,
        )
        attachments.append(producer_attachment)
        tracking_input = consumer_attachment
        key = ResourceKey(
            producer_attachment.buffer.allocation_id, worker.launch.owner.generation
        )
        assert consumer_attachment is not None
        ledger.expect_attachment(
            key,
            peer_instance_id=tracking_consumer.generation,
            transfer_id=consumer_attachment.sync.transfer_id,
        )
        expected.add(producer_attachment.buffer.allocation_id)
    if save_preview:
        preview_attachment, _ = _new_ring(
            worker=worker,
            session=session,
            layout=layout,
            owner=worker.launch.owner,
            camera_role=worker.context.camera,
            kind=acq.FRAME_BUFFER_KIND_PREVIEW,
            capacity=1,
            consumer=None,
        )
        await retain_ring(
            preview_attachment,
            layout,
            owner=worker.launch.owner,
            resources=resources,
            ledger=ledger,
            port=port,
            declare_resource=declare_resource,
        )
        attachments.append(preview_attachment)
        expected.add(preview_attachment.buffer.allocation_id)
    session.expected_attachments[worker.context.camera] = expected
    return tuple(attachments), tracking_input


def _new_ring(
    *,
    worker: WorkerRecord,
    session: SessionRecord,
    layout: PixelLayout,
    owner: control.ProcessIdentity,
    camera_role: camera.CameraRole,
    kind: acq.FrameBufferKind,
    capacity: int,
    consumer: control.ProcessIdentity | None,
) -> tuple[acq.FrameBufferAttachment, acq.FrameBufferAttachment | None]:
    allocation = str(uuid4())
    descriptor = acq.FrameBufferDescriptor(
        allocation_id=allocation,
        owner=owner,
        producer=worker.launch.worker,
        camera=camera_role,
        kind=kind,
        layout_version=2,
        capacity_frames=capacity,
        shared_memory_name=f"Local\\cephvr-{allocation}-frames",
        configuration_revision=session.configuration_revision,
        allocation_bytes=allocation_size(capacity, layout.image_payload_bytes),
    )
    descriptor.session.CopyFrom(session.work.session)
    if consumer is not None:
        descriptor.consumer.CopyFrom(consumer)
    descriptor.image.width = layout.width
    descriptor.image.height = layout.height
    descriptor.image.pixel_format = layout.pixel_format.sdk_name
    descriptor.image.row_stride_bytes = layout.row_stride_bytes
    descriptor.image.image_payload_bytes = layout.image_payload_bytes
    worker_attachment = acq.FrameBufferAttachment(buffer=descriptor)
    worker_attachment.sync.transfer_id = str(uuid4())
    worker_attachment.sync.target.CopyFrom(worker.launch.worker)
    worker_attachment.sync.event_name = event_name(UUID(allocation))
    if consumer is None:
        return worker_attachment, None
    consumer_attachment = acq.FrameBufferAttachment.FromString(
        worker_attachment.SerializeToString(deterministic=True)
    )
    consumer_attachment.sync.transfer_id = str(uuid4())
    consumer_attachment.sync.target.CopyFrom(consumer)
    return worker_attachment, consumer_attachment


async def retain_ring(
    attachment: acq.FrameBufferAttachment,
    layout: PixelLayout,
    *,
    owner: control.ProcessIdentity,
    resources: dict[str, ResourceRecord],
    ledger: NativeResourceLedger,
    port: ResourcePort,
    declare_resource: Callable[[control.ProcessIdentity, str], Awaitable[None]],
) -> None:
    descriptor = attachment.buffer
    allocation_id = descriptor.allocation_id
    key = ResourceKey(allocation_id, owner.generation)
    kind_name = (
        "tracking" if descriptor.kind == acq.FRAME_BUFFER_KIND_TRACKING else "preview"
    )
    ledger.register(key, kind=kind_name)
    ledger.expect_attachment(
        key,
        peer_instance_id=descriptor.producer.generation,
        transfer_id=attachment.sync.transfer_id,
    )
    retained = acq.FrameBufferAttachment.FromString(
        attachment.SerializeToString(deterministic=True)
    )
    record = ResourceRecord(
        attachment=retained,
        ring=None,
        ledger_key=key,
        native_state="planned",
    )
    resources[allocation_id] = record
    await declare_resource(owner, allocation_id)
    try:
        ring = port.create_ring(attachment, layout, owner)
    except RingAllocationError as exc:
        record.partial = exc.partial
        record.native_state = "partial"
        ledger.retire(key, reason="native ring allocation cleanup remains owned")
        raise
    except Exception:
        # The concrete ResourcePort either returns a ring or raises a typed partial
        # ownership error. An ordinary failure therefore proves its local rollback.
        record.native_state = "absent"
        raise
    record.ring = ring
    record.native_state = "allocated"


def _layout(resolved: camera.CameraResolvedState) -> PixelLayout:
    if not resolved.HasField("layout"):
        raise ValueError("resolved camera has no image layout")
    image = resolved.layout
    if (
        image.width <= 0
        or image.height <= 0
        or image.row_stride_bytes <= 0
        or image.image_payload_bytes <= 0
        or not image.pixel_format
    ):
        raise ValueError("resolved camera image layout is incomplete")
    pixel_format = pylon_pixel_format(image.pixel_format)
    return PixelLayout(
        int(image.width),
        int(image.height),
        pixel_format,
        int(image.row_stride_bytes),
        int(image.image_payload_bytes),
    )
