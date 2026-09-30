"""A03 version-2 seqlock ring for acquisition tracking and preview pixels."""

from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass
from typing import Literal

from cephvr.acquisition.buffers.layout import (
    ALIGNMENT,
    HEADER_BYTES,
    SLOT_BYTES,
    allocation_id,
    kind_value,
    pixel_base,
    validate_header,
    write_header,
)
from cephvr.acquisition.buffers.layout import (
    align_up as _align_up,
)
from cephvr.acquisition.buffers.records import FrameRecord
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.atomics import atomic_load_u64, atomic_store_u64
from cephvr.platform.windows.events import AutoResetEvent
from cephvr.platform.windows.mappings import SharedMapping
from cephvr.shared.pixels.types import PixelLayout

FLAG_INPUT_SEALED = 1
FLAG_RETIRED = 2
SLOT_COUNTER_VALID = 1
SLOT_TIMESTAMP_VALID = 2
_SLOT_METADATA = struct.Struct("<I 4s Q q Q q Q Q")
_HEADER_RUN_ID = struct.Struct("<16s")


class RingError(RuntimeError):
    """The shared frame ring violates its declared ABI or ownership protocol."""


class RingAllocationError(RingError):
    """Allocation failed while native ownership remains retryably available."""

    def __init__(
        self, message: str, partial: PartialRingOwnership | SharedRing
    ) -> None:
        super().__init__(message)
        self.partial = partial


class PartialRingOwnership:
    """Retain partially allocated OS objects when rollback itself fails."""

    def __init__(self, mapping: SharedMapping, event: AutoResetEvent | None) -> None:
        self.mapping: SharedMapping | None = mapping
        self.event: AutoResetEvent | None = event

    def close(self) -> None:
        event = self.event
        if event is not None:
            event.close()
            self.event = None
        mapping = self.mapping
        if mapping is not None:
            mapping.close()
            self.mapping = None


@dataclass(frozen=True, slots=True)
class RingRead:
    status: Literal["frame", "not_available", "lapped", "torn", "sealed", "retired"]
    sequence: int
    record: FrameRecord | None
    discontinuity_epoch: int


class SharedRing:
    """Single-writer ring that never waits for a consumer during publication.

    The public protobuf attachment is the descriptor authority. The pixel layout is
    the confirmed SDK mapping associated with that descriptor, not a second wire model.
    """

    def __init__(
        self,
        attachment: acq.FrameBufferAttachment,
        layout: PixelLayout,
        mapping: SharedMapping,
        event: AutoResetEvent,
        *,
        owner: bool,
        producer: bool,
        consumer: bool,
    ) -> None:
        self._attachment = acq.FrameBufferAttachment.FromString(
            attachment.SerializeToString(deterministic=True)
        )
        self.layout = layout
        self._mapping: SharedMapping | None = mapping
        self._event: AutoResetEvent | None = event
        self._owner = owner
        self._producer = producer
        self._consumer = consumer
        self._buffer: memoryview | None = mapping.buffer
        self._closed = False
        self._view_released = False
        self._pixel_base = pixel_base(self._attachment.buffer.capacity_frames)
        self._pixel_stride = _align_up(layout.image_payload_bytes, ALIGNMENT)

    @classmethod
    def create(
        cls,
        attachment: acq.FrameBufferAttachment,
        layout: PixelLayout,
        owner_identity: control.ProcessIdentity,
    ) -> SharedRing:
        from cephvr.acquisition.buffers.ring_attachment import create_ring

        return create_ring(cls, attachment, layout, owner_identity)

    @classmethod
    def attach(
        cls,
        attachment: acq.FrameBufferAttachment,
        layout: PixelLayout,
        caller_identity: control.ProcessIdentity,
    ) -> SharedRing:
        from cephvr.acquisition.buffers.ring_attachment import attach_ring

        return attach_ring(cls, attachment, layout, caller_identity)

    @property
    def descriptor(self) -> acq.FrameBufferDescriptor:
        """Return an isolated copy of the registered protobuf descriptor."""
        return acq.FrameBufferDescriptor.FromString(
            self._attachment.buffer.SerializeToString(deterministic=True)
        )

    @property
    def published_count(self) -> int:
        return atomic_load_u64(self._buf(), 64)

    @property
    def input_sealed(self) -> bool:
        return bool(self._header_flags() & FLAG_INPUT_SEALED)

    @property
    def retired(self) -> bool:
        return bool(self._header_flags() & FLAG_RETIRED)

    @property
    def discontinuity_epoch(self) -> int:
        return atomic_load_u64(self._buf(), 56)

    @property
    def run_id(self) -> uuid.UUID:
        """Return the exact trial or manual-preview run bound to this ring."""
        return _header_run_id(self._buf())

    def reset_quiescent(
        self, run_id: uuid.UUID, *, prior_completion_confirmed: bool
    ) -> None:
        """Reset only after the owner has matched all prior-run completion evidence."""
        self._require_owner()
        if not prior_completion_confirmed:
            raise RingError("prior producer and consumer completion is not confirmed")
        if not self.input_sealed or self.retired:
            raise RingError("ring reset requires sealed, non-retired input")
        if run_id.int == 0 or run_id.version != 4:
            raise RingError("bound trial or preview run must use a nonzero UUID")
        buffer = self._buf()
        write_header(
            buffer,
            kind_value(self._attachment.buffer.kind),
            self._attachment.buffer.capacity_frames,
            run_id,
            allocation_id(self._attachment.buffer),
            flags=FLAG_INPUT_SEALED,
            epoch=0,
            published_count=0,
        )
        self._signal()

    def open_admission(self, run_id: uuid.UUID) -> None:
        self._require_producer()
        if _header_run_id(self._buf()) != run_id or self.retired:
            raise RingError("run identity is stale or ring has been retired")
        self._store_flags(self._header_flags() & ~FLAG_INPUT_SEALED)
        self._signal()

    def publish(
        self,
        record: FrameRecord,
        pixels: memoryview,
        *,
        discontinuity_epoch: int | None = None,
    ) -> int:
        """Publish one valid native image with one native slot write and no reader wait."""
        self._require_producer()
        if not record.valid_image:
            raise RingError(
                "invalid images advance discontinuity but never enter pixel slots"
            )
        if self.input_sealed or self.retired:
            raise RingError("shared ring admission is sealed or retired")
        payload = memoryview(pixels).cast("B")
        if payload.nbytes != self.layout.image_payload_bytes:
            raise RingError("published payload differs from confirmed native layout")
        sequence = self.published_count
        if sequence >= 0x7FFFFFFFFFFFFFFF:
            raise RingError("64-bit frame sequence exhausted")
        epoch = (
            self.discontinuity_epoch
            if discontinuity_epoch is None
            else discontinuity_epoch
        )
        if epoch < self.discontinuity_epoch or epoch > 0x7FFFFFFFFFFFFFFF:
            raise RingError("discontinuity epoch is invalid or regressed")
        if (
            record.frame_id > 0xFFFFFFFFFFFFFFFF
            or record.acquisition_time_ns > 0x7FFFFFFFFFFFFFFF
        ):
            raise RingError("frame identity/time exceeds slot field width")
        counter = record.camera_frame_counter
        timestamp = record.camera_timestamp_ns
        if counter is not None and counter > 0xFFFFFFFFFFFFFFFF:
            raise RingError("camera counter exceeds slot field width")
        if timestamp is not None and timestamp > 0x7FFFFFFFFFFFFFFF:
            raise RingError("camera timestamp exceeds slot field width")
        slot = sequence % self._attachment.buffer.capacity_frames
        slot_offset = HEADER_BYTES + slot * SLOT_BYTES
        generation = atomic_load_u64(self._buf(), slot_offset)
        if generation & 1 or generation >= 0x7FFFFFFFFFFFFFFD:
            raise RingError("slot generation is odd or exhausted")
        _store_expected(self._buf(), slot_offset, generation, generation + 1)
        slot_flags = (SLOT_COUNTER_VALID if counter is not None else 0) | (
            SLOT_TIMESTAMP_VALID if timestamp is not None else 0
        )
        _SLOT_METADATA.pack_into(
            self._buf(),
            slot_offset + 8,
            slot_flags,
            bytes(4),
            record.frame_id,
            record.acquisition_time_ns,
            counter if counter is not None else 0,
            timestamp if timestamp is not None else 0,
            epoch,
            sequence,
        )
        pixel_offset = self._pixel_base + slot * self._pixel_stride
        self._buf()[pixel_offset : pixel_offset + payload.nbytes] = payload
        _store_expected(self._buf(), slot_offset, generation + 1, generation + 2)
        _store_expected(self._buf(), 64, sequence, sequence + 1)
        self._signal()
        return sequence

    def advance_discontinuity(self) -> int:
        self._require_producer()
        if self.retired:
            raise RingError("retired ring cannot advance discontinuity")
        epoch = self.discontinuity_epoch
        if epoch >= 0x7FFFFFFFFFFFFFFE:
            raise RingError("64-bit discontinuity epoch exhausted")
        _store_expected(self._buf(), 56, epoch, epoch + 1)
        self._signal()
        return epoch + 1

    def seal(self) -> None:
        self._require_producer()
        self._store_flags(self._header_flags() | FLAG_INPUT_SEALED)
        self._signal()

    def read_into(
        self,
        sequence: int,
        destination: bytearray | memoryview,
        *,
        expected_run_id: uuid.UUID,
    ) -> RingRead:
        """Copy one sequence to caller storage, then check generation and sequence once."""
        self._require_consumer()
        if expected_run_id.int == 0 or self.run_id != expected_run_id:
            raise RingError("consumer read is bound to a stale or different run")
        if sequence < 0:
            raise ValueError("ring sequence must be nonnegative")
        target = memoryview(destination).cast("B")
        if target.readonly or target.nbytes != self.layout.image_payload_bytes:
            raise RingError("reader destination does not match native image payload")
        if self.retired:
            return RingRead("retired", sequence, None, self.discontinuity_epoch)
        published = self.published_count
        if sequence >= published:
            status: Literal["sealed", "not_available"] = (
                "sealed" if self.input_sealed else "not_available"
            )
            return RingRead(status, sequence, None, self.discontinuity_epoch)
        if published - sequence > self._attachment.buffer.capacity_frames:
            return RingRead("lapped", published - 1, None, self.discontinuity_epoch)
        slot = sequence % self._attachment.buffer.capacity_frames
        slot_offset = HEADER_BYTES + slot * SLOT_BYTES
        generation = atomic_load_u64(self._buf(), slot_offset)
        if generation & 1:
            return RingRead("torn", sequence, None, self.discontinuity_epoch)
        (
            flags,
            reserved,
            frame_id,
            receipt_ns,
            counter,
            timestamp,
            epoch,
            stored_sequence,
        ) = _SLOT_METADATA.unpack_from(self._buf(), slot_offset + 8)
        pixel_offset = self._pixel_base + slot * self._pixel_stride
        target[:] = self._buf()[pixel_offset : pixel_offset + target.nbytes]
        second_sequence = _SLOT_METADATA.unpack_from(self._buf(), slot_offset + 8)[-1]
        second_generation = atomic_load_u64(self._buf(), slot_offset)
        if (
            generation != second_generation
            or generation & 1
            or stored_sequence != sequence
            or second_sequence != sequence
        ):
            return RingRead("torn", sequence, None, self.discontinuity_epoch)
        if self.run_id != expected_run_id:
            return RingRead("torn", sequence, None, self.discontinuity_epoch)
        if self.retired:
            return RingRead("retired", sequence, None, self.discontinuity_epoch)
        if reserved != bytes(4) or flags & ~(SLOT_COUNTER_VALID | SLOT_TIMESTAMP_VALID):
            raise RingError("slot reserved bytes or flag bits are invalid")
        record = FrameRecord(
            frame_id,
            receipt_ns,
            counter if flags & SLOT_COUNTER_VALID else None,
            timestamp if flags & SLOT_TIMESTAMP_VALID else None,
            True,
            None,
        )
        return RingRead("frame", sequence, record, epoch)

    def wait(self, timeout_ns: int) -> bool:
        self._require_consumer()
        if timeout_ns < 0:
            raise ValueError("ring event timeout must be nonnegative")
        event = self._event
        if event is None:
            raise RingError("ring event handle is closed")
        return event.wait(timeout_ns)

    def signal(self) -> None:
        self._signal()

    def retire(self, reason: str) -> None:
        """Mark failure after external lifecycle state records its concrete reason."""
        self._require_owner()
        if not reason:
            raise ValueError("ring retirement requires an externally recorded reason")
        self._store_flags(self._header_flags() | FLAG_RETIRED | FLAG_INPUT_SEALED)
        self._signal()

    def close(self) -> None:
        if self._closed:
            return
        event = self._event
        if event is not None:
            event.close()
            self._event = None
        buffer = self._buffer
        if buffer is not None and not self._view_released:
            buffer.release()
            self._view_released = True
        mapping = self._mapping
        if mapping is not None:
            mapping.close()
            self._mapping = None
        self._closed = True

    def _validate_header(self) -> None:
        validate_header(self._buf(), self._attachment.buffer)

    def _header_flags(self) -> int:
        return atomic_load_u64(self._buf(), 16) >> 32

    def _store_flags(self, flags: int) -> None:
        if flags & ~(FLAG_INPUT_SEALED | FLAG_RETIRED):
            raise RingError("unknown shared ring header flags")
        buffer = self._buf()
        current_word = atomic_load_u64(buffer, 16)
        capacity = current_word & 0xFFFFFFFF
        current_flags = current_word >> 32
        if current_flags & ~(FLAG_INPUT_SEALED | FLAG_RETIRED):
            raise RingError("unknown shared ring header flags")
        if current_flags & FLAG_RETIRED:
            if not flags & (FLAG_RETIRED | FLAG_INPUT_SEALED):
                raise RingError("retired ring flags are irreversible")
            flags |= FLAG_RETIRED | FLAG_INPUT_SEALED
        replacement = capacity | (flags << 32)
        _store_expected(buffer, 16, current_word, replacement)

    def _signal(self) -> None:
        event = self._event
        if event is None:
            raise RingError("ring event handle is closed")
        event.set()

    def _buf(self) -> memoryview:
        self._require_open()
        if self._buffer is None:
            raise RingError("ring mapping view is closed")
        return self._buffer

    def _require_open(self) -> None:
        if self._closed:
            raise RingError("shared ring is closed")

    def _require_owner(self) -> None:
        self._require_open()
        if not self._owner:
            raise RingError("operation requires coordinator mapping ownership")

    def _require_producer(self) -> None:
        self._require_open()
        if not self._producer:
            raise RingError("operation requires exact registered producer attachment")

    def _require_consumer(self) -> None:
        self._require_open()
        if not self._consumer:
            raise RingError("operation requires exact registered consumer attachment")


def _header_run_id(buffer: memoryview) -> uuid.UUID:
    return uuid.UUID(bytes=_HEADER_RUN_ID.unpack_from(buffer, 24)[0])


def _store_expected(
    buffer: memoryview, offset: int, expected: int, replacement: int
) -> None:
    try:
        atomic_store_u64(buffer, offset, expected, replacement)
    except Exception as exc:
        raise RingError("single-writer atomic value changed unexpectedly") from exc
