"""Named mapping/event allocation and exact protobuf transfer attachment (A03)."""

from __future__ import annotations

from typing import TypeVar

from cephvr.acquisition.buffers.layout import (
    allocation_id,
    initial_run_id,
    kind_value,
    validate_attachment,
    write_header,
)
from cephvr.acquisition.buffers.ring import (
    FLAG_INPUT_SEALED,
    PartialRingOwnership,
    RingAllocationError,
    RingError,
    SharedRing,
)
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.events import AutoResetEvent
from cephvr.platform.windows.mappings import SharedMapping
from cephvr.shared.pixels.types import PixelLayout

RingT = TypeVar("RingT", bound=type[SharedRing])


def create_ring(
    ring_type: RingT,
    attachment: acq.FrameBufferAttachment,
    layout: PixelLayout,
    owner_identity: control.ProcessIdentity,
) -> SharedRing:
    validate_attachment(attachment, layout)
    descriptor = attachment.buffer
    if descriptor.owner != owner_identity:
        raise RingError(
            "allocation owner differs from exact registered process identity"
        )
    mapping = SharedMapping.create(
        descriptor.shared_memory_name, descriptor.allocation_bytes
    )
    event: AutoResetEvent | None = None
    try:
        event = AutoResetEvent.create(allocation_id(descriptor))
    except BaseException as original:
        partial = PartialRingOwnership(mapping, None)
        try:
            partial.close()
        except BaseException:
            raise RingAllocationError(
                "event creation failed and mapping cleanup remains owned", partial
            ) from original
        raise
    try:
        ring = ring_type(
            attachment,
            layout,
            mapping,
            event,
            owner=True,
            producer=False,
            consumer=False,
        )
    except BaseException as original:
        partial = PartialRingOwnership(mapping, event)
        try:
            partial.close()
        except BaseException:
            raise RingAllocationError(
                "ring construction failed and native cleanup remains owned", partial
            ) from original
        raise
    if ring._buffer is None:
        try:
            ring.close()
        except BaseException as cleanup_error:
            raise RingAllocationError(
                "new mapping validation failed and native cleanup remains owned", ring
            ) from cleanup_error
        raise RingError("new mapping has no writable buffer view")
    try:
        write_header(
            ring._buffer,
            kind_value(descriptor.kind),
            descriptor.capacity_frames,
            initial_run_id(descriptor),
            allocation_id(descriptor),
            flags=FLAG_INPUT_SEALED,
            epoch=0,
            published_count=0,
        )
    except BaseException as original:
        try:
            ring.close()
        except BaseException:
            raise RingAllocationError(
                "ring initialization failed and native cleanup remains owned", ring
            ) from original
        raise
    return ring


def attach_ring(
    ring_type: RingT,
    attachment: acq.FrameBufferAttachment,
    layout: PixelLayout,
    caller_identity: control.ProcessIdentity,
) -> SharedRing:
    validate_attachment(attachment, layout)
    descriptor, sync = attachment.buffer, attachment.sync
    if sync.target != caller_identity:
        raise RingError("transfer target differs from exact caller process identity")
    producer = caller_identity == descriptor.producer
    consumer = (
        descriptor.kind == acq.FRAME_BUFFER_KIND_TRACKING
        and descriptor.HasField("consumer")
        and caller_identity == descriptor.consumer
    ) or (
        descriptor.kind == acq.FRAME_BUFFER_KIND_PREVIEW
        and caller_identity != descriptor.producer
    )
    if not producer and not consumer:
        raise RingError("caller is not an authorized producer or consumer")
    mapping = SharedMapping.attach(
        descriptor.shared_memory_name, descriptor.allocation_bytes
    )
    event: AutoResetEvent | None = None
    try:
        event = AutoResetEvent.open(sync.event_name, allocation_id(descriptor))
    except BaseException as original:
        partial = PartialRingOwnership(mapping, None)
        try:
            partial.close()
        except BaseException:
            raise RingAllocationError(
                "event attach failed and mapping cleanup remains owned", partial
            ) from original
        raise
    try:
        ring = ring_type(
            attachment,
            layout,
            mapping,
            event,
            owner=False,
            producer=producer,
            consumer=consumer,
        )
    except BaseException as original:
        partial = PartialRingOwnership(mapping, event)
        try:
            partial.close()
        except BaseException:
            raise RingAllocationError(
                "ring attachment failed and native cleanup remains owned", partial
            ) from original
        raise
    try:
        ring._validate_header()
    except BaseException as original:
        try:
            ring.close()
        except BaseException:
            raise RingAllocationError(
                "attached ring validation failed and native cleanup remains owned",
                ring,
            ) from original
        raise
    return ring
