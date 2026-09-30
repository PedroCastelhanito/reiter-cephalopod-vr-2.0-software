"""Validated protobuf-to-v2-ring ABI layout (A03)."""

from __future__ import annotations

import struct
import uuid

from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.platform.windows.events import event_name
from cephvr.shared.identity import require_uuid4
from cephvr.shared.pixels.types import PixelLayout

MAGIC = b"CEPHFRM2"
LAYOUT_VERSION = 2
HEADER_BYTES = 128
SLOT_BYTES = 64
ALIGNMENT = 64
_HEADER = struct.Struct("<8sIIII16s16sQQ56s")


class RingLayoutError(ValueError):
    """A protobuf descriptor cannot describe the declared shared ring ABI."""


def validate_attachment(
    attachment: acq.FrameBufferAttachment, layout: PixelLayout
) -> None:
    if not attachment.HasField("buffer") or not attachment.HasField("sync"):
        raise RingLayoutError("protobuf attachment requires descriptor and sync names")
    descriptor, sync = attachment.buffer, attachment.sync
    try:
        allocation_id(descriptor)
        require_uuid4(sync.transfer_id)
        require_uuid4(descriptor.owner.generation)
        require_uuid4(descriptor.producer.generation)
    except (ValueError, AttributeError) as exc:
        raise RingLayoutError("protobuf attachment identity is invalid") from exc
    if (
        descriptor.kind
        not in (acq.FRAME_BUFFER_KIND_TRACKING, acq.FRAME_BUFFER_KIND_PREVIEW)
        or not descriptor.HasField("layout_version")
        or descriptor.layout_version != LAYOUT_VERSION
        or not descriptor.HasField("capacity_frames")
        or descriptor.capacity_frames <= 0
        or not descriptor.HasField("allocation_bytes")
        or not descriptor.HasField("configuration_revision")
        or not descriptor.HasField("image")
        or not descriptor.HasField("owner")
        or not descriptor.HasField("producer")
    ):
        raise RingLayoutError("protobuf descriptor omits required A03 layout fields")
    if (
        descriptor.kind == acq.FRAME_BUFFER_KIND_PREVIEW
        and descriptor.capacity_frames != 1
    ):
        raise RingLayoutError("preview ring must have exactly one latest-frame slot")
    if descriptor.kind == acq.FRAME_BUFFER_KIND_TRACKING:
        if not descriptor.HasField("consumer"):
            raise RingLayoutError("tracking ring requires its fixed consumer identity")
        try:
            require_uuid4(descriptor.consumer.generation)
        except ValueError as exc:
            raise RingLayoutError("tracking consumer identity is invalid") from exc
    if descriptor.camera == camera.CAMERA_ROLE_UNSPECIFIED:
        raise RingLayoutError("camera role is required by shared ring descriptor")
    if not sync.event_name or sync.event_name != event_name(allocation_id(descriptor)):
        raise RingLayoutError("event name does not match allocation UUID")
    if (
        descriptor.shared_memory_name
        != f"Local\\cephvr-{allocation_id(descriptor)}-frames"
    ):
        raise RingLayoutError("shared memory name does not match allocation UUID")
    if not descriptor.image.HasField("width") or not descriptor.image.HasField(
        "height"
    ):
        raise RingLayoutError("confirmed dimensions are required in the descriptor")
    if (
        descriptor.image.width != layout.width
        or descriptor.image.height != layout.height
        or descriptor.image.pixel_format != layout.pixel_format.sdk_name
        or not descriptor.image.HasField("row_stride_bytes")
        or descriptor.image.row_stride_bytes != layout.row_stride_bytes
        or not descriptor.image.HasField("image_payload_bytes")
        or descriptor.image.image_payload_bytes != layout.image_payload_bytes
    ):
        raise RingLayoutError(
            "SDK pixel layout differs from protobuf buffer descriptor"
        )
    if descriptor.allocation_bytes != allocation_size(
        descriptor.capacity_frames, layout.image_payload_bytes
    ):
        raise RingLayoutError("allocation byte count differs from derived v2 layout")
    if descriptor.WhichOneof("scope") not in ("session", "preview"):
        raise RingLayoutError(
            "ring descriptor requires an explicit session or preview scope"
        )
    if (
        descriptor.kind == acq.FRAME_BUFFER_KIND_PREVIEW
        and descriptor.WhichOneof("scope") == "preview"
    ):
        try:
            require_uuid4(descriptor.preview.acquisition_run_id)
        except ValueError as exc:
            raise RingLayoutError(
                "manual preview scope requires an exact acquisition run"
            ) from exc


def allocation_id(descriptor: acq.FrameBufferDescriptor) -> uuid.UUID:
    try:
        require_uuid4(descriptor.allocation_id)
        return uuid.UUID(descriptor.allocation_id)
    except (ValueError, AttributeError) as exc:
        raise RingLayoutError("allocation ID must be a registered UUIDv4") from exc


def initial_run_id(descriptor: acq.FrameBufferDescriptor) -> uuid.UUID:
    if descriptor.WhichOneof("scope") == "preview":
        return uuid.UUID(descriptor.preview.acquisition_run_id)
    return uuid.UUID(int=0)


def kind_value(kind: int) -> int:
    if kind in (acq.FRAME_BUFFER_KIND_TRACKING, acq.FRAME_BUFFER_KIND_PREVIEW):
        return int(kind)
    raise RingLayoutError("unsupported shared ring kind")


def pixel_base(capacity: int) -> int:
    return align_up(HEADER_BYTES + capacity * SLOT_BYTES, ALIGNMENT)


def allocation_size(capacity: int, image_payload_bytes: int) -> int:
    if capacity <= 0 or image_payload_bytes <= 0:
        raise RingLayoutError("ring capacity and payload size must be positive")
    stride = align_up(image_payload_bytes, ALIGNMENT)
    size = pixel_base(capacity) + capacity * stride
    if size > 0x7FFFFFFFFFFFFFFF:
        raise RingLayoutError("ring allocation size overflows supported bounds")
    return size


def align_up(value: int, alignment: int) -> int:
    if value < 0 or alignment <= 0:
        raise RingLayoutError("layout size/alignment is invalid")
    return ((value + alignment - 1) // alignment) * alignment


def write_header(
    buffer: memoryview,
    kind: int,
    capacity: int,
    run_id: uuid.UUID,
    allocation: uuid.UUID,
    flags: int,
    epoch: int,
    published_count: int,
) -> None:
    _HEADER.pack_into(
        buffer,
        0,
        MAGIC,
        LAYOUT_VERSION,
        kind_value(kind),
        capacity,
        flags,
        run_id.bytes,
        allocation.bytes,
        epoch,
        published_count,
        bytes(56),
    )


def validate_header(buffer: memoryview, descriptor: acq.FrameBufferDescriptor) -> None:
    (
        magic,
        version,
        kind,
        capacity,
        flags,
        run_id,
        allocation,
        _,
        published,
        reserved,
    ) = _HEADER.unpack_from(buffer)
    if descriptor.WhichOneof("scope") == "session":
        try:
            scoped_run_id = uuid.UUID(bytes=run_id)
        except ValueError as exc:
            raise RingLayoutError("session ring run identity is malformed") from exc
        run_matches = (scoped_run_id.int == 0 and published == 0) or (
            scoped_run_id.version == 4
        )
    else:
        run_matches = run_id == initial_run_id(descriptor).bytes
    if (
        magic != MAGIC
        or version != LAYOUT_VERSION
        or kind != kind_value(descriptor.kind)
        or capacity != descriptor.capacity_frames
        or flags & ~3
        or not run_matches
        or allocation != allocation_id(descriptor).bytes
        or reserved != bytes(56)
    ):
        raise RingLayoutError(
            "shared ring header differs from exact protobuf descriptor"
        )
