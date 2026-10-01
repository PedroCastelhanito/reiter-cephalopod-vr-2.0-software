"""A03/T08 finite private image pool; independent holders share one immutable copy."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from uuid import uuid4

from cephvr.control.v1.types_pb2 import WorkContext
from cephvr.tracking.config.models.records import SourceFrame
from cephvr.tracking.types import ImageLayout, PrivateFrame


@dataclass
class _Slot:
    pixels: bytearray
    lease: PrivateFrame | None = None
    references: int = 0
    writing: bool = False


class FramePool:
    def __init__(self, layout: ImageLayout, capacity: int, maximum_bytes: int) -> None:
        size = layout.row_stride_bytes * layout.height
        if capacity < 1 or size * capacity > maximum_bytes:
            raise ValueError("private frame pool exceeds prepared memory budget")
        self.layout = layout
        self.lock = threading.Lock()
        self.slots = [_Slot(bytearray(size)) for _ in range(capacity)]

    def acquire(self) -> tuple[int, memoryview] | None:
        with self.lock:
            for index, slot in enumerate(self.slots):
                if slot.references == 0 and not slot.writing:
                    slot.writing = True
                    return index, memoryview(slot.pixels)
        return None

    def publish(
        self, index: int, source: SourceFrame, work: WorkContext, generation: str
    ) -> PrivateFrame:
        with self.lock:
            slot = self.slots[index]
            if not slot.writing or slot.references:
                raise ValueError("slot is not exclusively owned for preparation")
            frame = PrivateFrame(
                source,
                WorkContext.FromString(work.SerializeToString()),
                generation,
                self.layout,
                memoryview(slot.pixels).toreadonly(),
                str(uuid4()),
            )
            slot.lease, slot.references, slot.writing = frame, 1, False
            return frame

    def cancel(self, index: int) -> None:
        with self.lock:
            slot = self.slots[index]
            if not slot.writing:
                raise ValueError("slot has no pending preparation")
            slot.writing = False

    def retain(self, frame: PrivateFrame) -> None:
        with self.lock:
            self._slot(frame).references += 1

    def release(self, frame: PrivateFrame) -> None:
        with self.lock:
            slot = self._slot(frame)
            slot.references -= 1
            if not slot.references:
                slot.lease = None

    def _slot(self, frame: PrivateFrame) -> _Slot:
        slot = next((slot for slot in self.slots if slot.lease is frame), None)
        if slot is None or slot.references <= 0:
            raise ValueError("unknown or retired private frame")
        return slot

    def idle(self) -> bool:
        with self.lock:
            return all(not slot.references and not slot.writing for slot in self.slots)
