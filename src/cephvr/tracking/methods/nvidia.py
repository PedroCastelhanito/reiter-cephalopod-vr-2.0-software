"""T07 ordered GPU baseline/pair leases; timeout never makes storage reusable."""

from __future__ import annotations

import time
from uuid import uuid4

from cephvr.platform.windows.nvidia_device import verify_tracking_device
from cephvr.shared.clock import host_time_ns
from cephvr.tracking.config.models.methods import FileLimits, FlowSettings
from cephvr.tracking.methods.flow_buffers import grid_mapping
from cephvr.tracking.methods.images import GrayPreparation
from cephvr.tracking.native.nvof import NativeFlow
from cephvr.tracking.types import (
    FlowGridMapping,
    FlowLease,
    HostFlowView,
    ImageLayout,
    PrivateFrame,
)


class NvidiaFlow:
    def __init__(self) -> None:
        self.native: NativeFlow | None = None
        self.baseline: PrivateFrame | None = None
        self.pending_frame: PrivateFrame | None = None
        self.lease: FlowLease | None = None
        self.completed = False
        self.generation: str | None = None
        self.prepared = False

    def prepare(
        self, settings: FlowSettings, layout: ImageLayout, limits: FileLimits
    ) -> None:
        self.device = verify_tracking_device(settings.device_ordinal)
        self.settings = settings
        self.mapping = grid_mapping(
            layout.width, layout.height, settings.output_grid_px
        )
        host_bytes = layout.width * layout.height * 9 + (
            self.mapping.grid_width * self.mapping.grid_height * 48
        )
        if host_bytes >= limits.max_native_bytes:
            raise ValueError("gray preparation and grid mapping exceed native budget")
        self.gray = GrayPreparation(layout)
        self.native = NativeFlow()
        # Keep the partial owner reachable if creation fails; cleanup still owns it.
        self.native.prepare(settings, layout, limits.max_native_bytes - host_bytes)
        self.prepared = True

    def grid_mapping(self) -> FlowGridMapping:
        return self.mapping

    def establish_baseline(self, frame: PrivateFrame, deadline_host_ns: int) -> bool:
        if self.lease is not None:
            raise ValueError("host lease must be released before baseline")
        if self.baseline is not None:
            if _identity(frame) != _identity(self.baseline):
                raise ValueError("baseline replacement requires processing reset")
            return True
        if self.pending_frame is not None:
            if _identity(frame) != _identity(self.pending_frame):
                raise ValueError("another baseline upload is pending")
        else:
            self._generation(frame)
            self.pending_frame = frame
            self._native().upload(self.gray.feature(frame), baseline=True)
        if not self._wait(deadline_host_ns):
            return False
        self.baseline, self.pending_frame = frame, None
        return True

    def compute_pair(self, earlier: PrivateFrame, later: PrivateFrame) -> FlowLease:
        if self.lease is not None or self.pending_frame is not None:
            raise ValueError("one outstanding native/host lease is allowed")
        if self.baseline is None or _identity(self.baseline) != _identity(earlier):
            raise ValueError("earlier frame is not retained on GPU")
        self._generation(later)
        if (
            earlier.work != later.work
            or earlier.layout != later.layout
            or later.source.frame_id != earlier.source.frame_id + 1
            or later.source.host_receipt_ns <= earlier.source.host_receipt_ns
        ):
            raise ValueError("pair crosses source interval/binding")
        mapping = self.mapping
        key = str(uuid4())
        quality = key + "-cost" if self.settings.output_cost else None
        self.lease = FlowLease(
            key,
            later.reset_generation,
            later.work,
            mapping.mapping_id,
            earlier.source,
            later.source,
            mapping.grid_width,
            mapping.grid_height,
            self.settings.output_grid_px,
            mapping.grid_width * 4,
            key,
            "int16x2",
            "little",
            "host",
            1 / 32,
            "input_pixel_displacement",
            key + "-flow",
            quality,
            mapping.grid_width if quality else None,
            "tracking.nvof-cost-u8.v1" if quality else None,
            None,
            None,
        )
        self.pending_frame = later
        self.completed = False
        self._native().upload(self.gray.feature(later), baseline=False)
        return self.lease

    def wait_complete(self, lease: FlowLease, deadline_host_ns: int) -> bool:
        self._check(lease)
        if self.completed:
            return True
        if not self._wait(deadline_host_ns):
            return False
        self.baseline, self.pending_frame = self.pending_frame, None
        self.completed = True
        return True

    def host_view(self, lease: FlowLease) -> HostFlowView:
        self._check(lease)
        if not self.completed:
            raise ValueError("readback has not completed")
        data, cost = self._native().views(lease.grid_width * lease.grid_height)
        return HostFlowView(lease.lease_id, data, cost, None)

    def release(self, lease: FlowLease) -> None:
        self._check(lease)
        if not self.completed:
            raise ValueError("cannot release pending native storage")
        self.lease = None
        self.completed = False

    def reset(self, generation: str) -> None:
        if self.lease is not None or self.pending_frame is not None:
            raise ValueError("reset requires native reconciliation and host release")
        self._native().reset()
        self.baseline = None
        self.generation = generation

    def close(self, deadline_host_ns: int) -> bool:
        if self.lease is not None:
            return False
        if self.native is not None:
            if self.prepared and not self._wait(deadline_host_ns):
                return False
            self.native.close()
            self.native = None
            self.prepared = False
        self.baseline, self.pending_frame = None, None
        return True

    def _native(self) -> NativeFlow:
        if self.native is None:
            raise RuntimeError("flow native owner is not prepared")
        return self.native

    def _check(self, lease: FlowLease) -> None:
        if self.lease is not lease:
            raise ValueError("unknown or retired flow lease")

    def _generation(self, frame: PrivateFrame) -> None:
        if self.generation is None:
            self.generation = frame.reset_generation
        if self.generation != frame.reset_generation:
            raise ValueError("frame processing generation differs from native owner")

    def _wait(self, deadline: int) -> bool:
        while host_time_ns() < deadline:
            if self._native().complete():
                return True
            time.sleep(min(0.001, max(0, (deadline - host_time_ns()) / 1e9)))
        return False


def _identity(frame: PrivateFrame) -> tuple[bytes, str, str, int, int, str]:
    return (
        frame.work.SerializeToString(deterministic=True),
        frame.reset_generation,
        frame.layout.transform_id,
        frame.source.frame_id,
        frame.source.host_receipt_ns,
        frame.lease_id,
    )
