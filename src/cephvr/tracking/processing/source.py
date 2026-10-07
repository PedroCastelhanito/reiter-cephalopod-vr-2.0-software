"""A03 native seqlock snapshot, shared conversion and finite private leases."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from cephvr.acquisition.buffers.ring import SharedRing
from cephvr.acquisition.camera.native_formats import pylon_pixel_format
from cephvr.acquisition.v1.messages_pb2 import FrameBufferAttachment
from cephvr.control.v1.types_pb2 import ProcessIdentity, WorkContext
from cephvr.shared.pixels.preparer import PixelPreparer
from cephvr.shared.pixels.types import PixelLayout
from cephvr.tracking.config.models.records import SourceFrame
from cephvr.tracking.processing.frames import FramePool
from cephvr.tracking.processing.preprocessing import ImageTransform, resolve_transform
from cephvr.tracking.types import ImageLayout, PrivateFrame
from cephvr.tracking.v1.pose_pb2 import TrackingPreprocessingSettings


class RingSource:
    def __init__(
        self,
        frames: FrameBufferAttachment,
        identity: ProcessIdentity,
        maximum_bytes: int,
        preprocessing: TrackingPreprocessingSettings | None = None,
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
        self.source_layout = ImageLayout(
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
        enabled, crop, scale = _preprocessing(preprocessing)
        self.transform: ImageTransform = resolve_transform(
            image.width,
            image.height,
            crop_enabled=enabled,
            crop=crop,
            scale_percent=scale,
        )
        transform_digest = hashlib.sha256(
            (
                transform + json.dumps((enabled, crop, scale), separators=(",", ":"))
            ).encode()
        ).hexdigest()
        self.layout = ImageLayout(
            self.transform.output_width,
            self.transform.output_height,
            self.transform.output_width * channels * (bits // 8),
            "gray" if channels == 1 else "rgb",
            "uint8" if bits == 8 else "uint16",
            native.effective_bits,
            "lsb" if bits == 8 else "msb",
            0,
            (1 << native.effective_bits) - 1,
            transform_digest,
        )
        # One movement frame, one retained baseline, one pose active, one pose waiting.
        native_copy_bytes = (
            self.source_layout.row_stride_bytes * self.source_layout.height
        )
        processed_copy_bytes = self.layout.row_stride_bytes * self.layout.height
        needed = (
            4 * processed_copy_bytes + native_copy_bytes + image.image_payload_bytes
        )
        if needed > maximum_bytes:
            raise ValueError("source copies exceed preparation budget")
        self.pool = FramePool(
            self.layout,
            4,
            maximum_bytes - image.image_payload_bytes - native_copy_bytes,
            self.transform,
        )
        self.scratch = bytearray(image.image_payload_bytes)
        self.native_scratch = bytearray(native_copy_bytes)
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
        if work.WhichOneof("work") != "trial":
            raise ValueError("trial source reads require their exact trial context")
        frame, gap, _ = self.read_run(
            UUID(work.trial.trial_id), work, generation, copy_acquired=False
        )
        return frame, gap

    def read_run(
        self,
        run_id: UUID,
        work: WorkContext,
        generation: str,
        *,
        copy_acquired: bool,
        maximum_acquired_bytes: int | None = None,
    ) -> tuple[PrivateFrame | None, bool, bytes | None]:
        if self.ring is None or self.converter is None:
            raise RuntimeError("source is detached")
        slot = self.pool.acquire()
        if slot is None:
            return None, True, None
        index, destination = slot
        try:
            result = self.ring.read_into(
                self.sequence, self.scratch, expected_run_id=run_id
            )
            if result.status in ("lapped", "torn"):
                self.sequence = max(self.sequence + 1, result.sequence)
                return None, True, None
            if result.status == "retired":
                raise RuntimeError("acquisition retired active tracking source")
            if result.record is None:
                return None, False, None
            self.sequence += 1
            changed = result.discontinuity_epoch != self.epoch
            self.epoch = result.discontinuity_epoch
            self.converter.prepare_source_depth_into(self.scratch, self.native_scratch)
            import numpy as np

            native_pixels = np.frombuffer(
                self.native_scratch, dtype=self.source_layout.storage
            )
            native_pixels = native_pixels.reshape(
                self.source_layout.height,
                self.source_layout.width,
                *((1,) if self.source_layout.channels == "gray" else (3,)),
            )
            if self.source_layout.channels == "gray":
                native_pixels = native_pixels[:, :, 0]
            acquired_copy = (
                bytes(self.scratch)
                if copy_acquired
                and (
                    maximum_acquired_bytes is None
                    or self.native_layout.image_payload_bytes <= maximum_acquired_bytes
                )
                else None
            )
            processed_pixels = np.frombuffer(destination, dtype=self.layout.storage)
            processed_shape: tuple[int, ...] = (self.layout.height, self.layout.width)
            if self.layout.channels == "rgb":
                processed_shape += (3,)
            processed_pixels = processed_pixels.reshape(processed_shape)
            self.transform.apply(native_pixels, processed_pixels)
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
            return frame, changed, acquired_copy
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


def _preprocessing(
    value: TrackingPreprocessingSettings | None,
) -> tuple[bool, tuple[int, int, int, int] | None, int]:
    if value is None:
        return False, None, 100
    enabled = bool(value.crop_enabled)
    scale = int(value.scale_percent) if value.HasField("scale_percent") else 100
    crop = None
    if value.HasField("crop_region"):
        region = value.crop_region
        crop = (region.x_px, region.y_px, region.width_px, region.height_px)
    return enabled, crop, scale
