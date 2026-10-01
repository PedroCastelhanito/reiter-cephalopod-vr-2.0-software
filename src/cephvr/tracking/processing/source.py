"""A03 native seqlock snapshot, shared conversion and finite private leases."""

from __future__ import annotations

import hashlib
from uuid import UUID

from cephvr.acquisition.buffers.ring import SharedRing
from cephvr.acquisition.camera.native_formats import pylon_pixel_format
from cephvr.acquisition.v1.messages_pb2 import FrameBufferAttachment
from cephvr.control.v1.types_pb2 import ProcessIdentity, WorkContext
from cephvr.shared.pixels.preparer import PixelPreparer
from cephvr.shared.pixels.types import PixelLayout
from cephvr.tracking.config.models.records import SourceFrame
from cephvr.tracking.processing.frames import FramePool
from cephvr.tracking.types import ImageLayout, PrivateFrame


class RingSource:
    def __init__(
        self,
        frames: FrameBufferAttachment,
        identity: ProcessIdentity,
        maximum_bytes: int,
    ) -> None:
        image = frames.buffer.image
        native = pylon_pixel_format(image.pixel_format)
        self.native_layout = PixelLayout(
            image.width,
            image.height,
            native,
            image.row_stride_bytes,
            image.image_payload_bytes,
        )
        channels = 1 if native.channel_layout.startswith("mono") else 3
        bits = 8 if native.effective_bits == 8 else 16
        transform = hashlib.sha256(
            frames.buffer.SerializeToString(deterministic=True)
        ).hexdigest()
        self.layout = ImageLayout(
            image.width,
            image.height,
            image.width * channels * (bits // 8),
            "gray" if channels == 1 else "rgb",
            "uint8" if bits == 8 else "uint16",
            native.effective_bits,
            "lsb" if bits == 8 else "msb",
            0,
            (1 << native.effective_bits) - 1,
            transform,
        )
        # One movement frame, one retained baseline, one pose active, one pose waiting.
        needed = (
            4 * self.layout.row_stride_bytes * self.layout.height
            + image.image_payload_bytes
        )
        if needed > maximum_bytes:
            raise ValueError("source copies exceed preparation budget")
        self.pool = FramePool(self.layout, 4, maximum_bytes - image.image_payload_bytes)
        self.scratch = bytearray(image.image_payload_bytes)
        self.converter: PixelPreparer | None = None
        self.ring: SharedRing | None = None
        self.frames = frames
        self.sequence = 0
        self.epoch = 0

    def open(self, identity: ProcessIdentity) -> None:
        self.converter = PixelPreparer(self.native_layout)
        self.ring = SharedRing.attach(self.frames, self.native_layout, identity)

    def begin(self) -> None:
        self.sequence, self.epoch = 0, 0

    def latest(self) -> None:
        if self.ring is None:
            raise RuntimeError("source is detached")
        self.sequence = max(self.sequence, self.ring.published_count - 1)

    def read(
        self, work: WorkContext, generation: str
    ) -> tuple[PrivateFrame | None, bool]:
        if self.ring is None or self.converter is None:
            raise RuntimeError("source is detached")
        slot = self.pool.acquire()
        if slot is None:
            return None, True
        index, destination = slot
        try:
            result = self.ring.read_into(
                self.sequence, self.scratch, expected_run_id=UUID(work.trial.trial_id)
            )
            if result.status in ("lapped", "torn"):
                self.sequence = max(self.sequence + 1, result.sequence)
                return None, True
            if result.status == "retired":
                raise RuntimeError("acquisition retired active tracking source")
            if result.record is None:
                return None, False
            self.sequence += 1
            changed = result.discontinuity_epoch != self.epoch
            self.epoch = result.discontinuity_epoch
            self.converter.prepare_source_depth_into(self.scratch, destination)
            frame = self.pool.publish(
                index,
                SourceFrame(
                    frame_id=result.record.frame_id,
                    host_receipt_ns=result.record.acquisition_time_ns,
                ),
                work,
                generation,
            )
            index = -1
            return frame, changed
        finally:
            destination.release()
            if index >= 0:
                self.pool.cancel(index)

    def close(self) -> bool:
        if not self.pool.idle():
            return False
        if self.converter is not None:
            self.converter.close()
            self.converter = None
        if self.ring is not None:
            self.ring.close()
            self.ring = None
        return True
