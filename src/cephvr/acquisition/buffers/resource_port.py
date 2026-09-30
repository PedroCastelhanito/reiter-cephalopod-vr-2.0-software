"""Coordinator-owned frame-ring allocation and release port (A03/E08)."""

from __future__ import annotations

from cephvr.acquisition.buffers.ring import (
    PartialRingOwnership,
    RingAllocationError,
    SharedRing,
)
from cephvr.acquisition.buffers.ring_attachment import create_ring
from cephvr.acquisition.ports import ResourcePort
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.pixels.types import PixelLayout


class WindowsResourcePort(ResourcePort):
    """Retain ring handles across partial creation and retryable release."""

    def __init__(self) -> None:
        self._rings: dict[str, SharedRing | PartialRingOwnership] = {}

    def create_ring(
        self,
        attachment: acq.FrameBufferAttachment,
        layout: PixelLayout,
        owner: control.ProcessIdentity,
    ) -> SharedRing:
        key = attachment.buffer.allocation_id
        if key in self._rings:
            raise RuntimeError("ring allocation ID was reused")
        try:
            ring = create_ring(SharedRing, attachment, layout, owner)
        except RingAllocationError as exc:
            self._rings[key] = exc.partial
            raise
        self._rings[key] = ring
        return ring

    def release_ring(self, allocation_id_value: str) -> None:
        ring = self._rings.get(allocation_id_value)
        if ring is None:
            raise RuntimeError("owned ring mapping is not present for release")
        ring.close()
        self._rings.pop(allocation_id_value, None)
