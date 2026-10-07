"""Join OpenCV reader lifetime to exact native ownership and device evidence."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from cephvr.acquisition.coordinator.manual_device_status import (
    ManualDeviceStatusReporter,
)
from cephvr.acquisition.preview.highgui import HighGuiPreview
from cephvr.acquisition.state import CoordinatorIdentity, ResourceRecord, WorkerPreview
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.platform.windows.resource_ledger import NativeResourceLedger


@dataclass
class _Window:
    role: int
    run_id: str
    reader: HighGuiPreview
    resource: ResourceRecord
    transfer_id: str
    released: bool = False


class PreviewWindows:
    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        resources: dict[str, ResourceRecord],
        ledger: NativeResourceLedger,
        status: ManualDeviceStatusReporter,
        clock: Callable[[], int],
        report_timeout_ns: int,
    ) -> None:
        self.identity = identity
        self.resources = resources
        self.ledger = ledger
        self.status = status
        self.clock = clock
        self.report_timeout_ns = report_timeout_ns
        self._windows: dict[int, _Window] = {}
        self._notifications: set[asyncio.Task[None]] = set()

    async def show(
        self,
        role: int,
        preview: WorkerPreview,
        *,
        deadline_ns: int,
        placement: rpc.PreviewWindowPlacement | None = None,
    ) -> None:
        current = self._windows.get(role)
        if current is not None:
            if current.run_id != preview.run_id:
                raise RuntimeError("another exact preview run still owns a window")
            if not current.reader.done.done():
                return
            await self.close(role, preview.run_id, deadline_ns=deadline_ns)
        if preview.viewer is not None:
            raise RuntimeError(
                "an external consumer already owns this latest-frame slot"
            )
        if preview.allocation_id is None:
            raise ValueError("preview allocation is missing")
        resource = self.resources[preview.allocation_id]
        attachment = acq.FrameBufferAttachment.FromString(
            resource.attachment.SerializeToString()
        )
        attachment.sync.target.CopyFrom(self.identity.process)
        attachment.sync.transfer_id = str(uuid4())
        self.ledger.expect_attachment(
            resource.ledger_key,
            peer_instance_id=self.identity.process.generation,
            transfer_id=attachment.sync.transfer_id,
        )
        loop = asyncio.get_running_loop()

        def on_closed(value: HighGuiPreview) -> None:
            loop.call_soon_threadsafe(self._closed, role, value)

        reader = HighGuiPreview(
            attachment,
            preview.preview_output_bit_depth,
            "Behavior camera" if role == 1 else "Tracking camera",
            on_closed,
            placement=placement,
        )
        window = _Window(
            role, preview.run_id, reader, resource, attachment.sync.transfer_id
        )
        self._windows[role] = window
        reader.start()
        try:
            await asyncio.wait_for(
                asyncio.shield(asyncio.wrap_future(reader.ready)),
                max(0, deadline_ns - self.clock()) / 1e9,
            )
            self.ledger.confirm_attachment(
                resource.ledger_key,
                peer_instance_id=self.identity.process.generation,
                transfer_id=window.transfer_id,
            )
            self.status.set_preview_visibility(role, window.run_id, True)
        except Exception:
            await self.close(role, preview.run_id, deadline_ns=deadline_ns)
            raise

    async def close(self, role: int, run_id: str, *, deadline_ns: int) -> None:
        window = self._windows.get(role)
        if window is None:
            self.status.set_preview_visibility(role, run_id, False)
            return
        if window.run_id != run_id:
            raise RuntimeError("window close targets a different preview run")
        window.reader.stop()
        released = await asyncio.wait_for(
            asyncio.shield(asyncio.wrap_future(window.reader.done)),
            max(0, deadline_ns - self.clock()) / 1e9,
        )
        self.status.set_preview_visibility(
            role, run_id, window.reader.visible, window.reader.failure
        )
        if not released:
            raise RuntimeError(
                window.reader.failure or "Preview reader release unconfirmed"
            )
        self._release(window)
        self._windows.pop(role, None)

    async def close_all(self, *, deadline_ns: int) -> None:
        for role, window in tuple(self._windows.items()):
            await self.close(role, window.run_id, deadline_ns=deadline_ns)
        if self._notifications:
            await asyncio.wait_for(
                asyncio.gather(*tuple(self._notifications), return_exceptions=True),
                max(0, deadline_ns - self.clock()) / 1e9,
            )

    def owns(self, role: int) -> bool:
        return role in self._windows

    def _release(self, window: _Window) -> None:
        if window.released:
            return
        self.ledger.confirm_release(
            window.resource.ledger_key,
            peer_instance_id=self.identity.process.generation,
            transfer_id=window.transfer_id,
        )
        self.ledger.prune_released_transfer(
            window.resource.ledger_key, transfer_id=window.transfer_id
        )
        window.released = True

    def _closed(self, role: int, reader: HighGuiPreview) -> None:
        window = self._windows.get(role)
        if window is None or window.reader is not reader:
            return
        if reader.done.result():
            self._release(window)
            self._windows.pop(role, None)
        observation = self.status.set_preview_visibility(
            role, window.run_id, reader.visible, reader.failure
        )
        if observation is None:
            return
        task = asyncio.create_task(
            self.status.publish_preview_visibility(
                observation,
                deadline_ns=self.clock() + self.report_timeout_ns,
            )
        )
        self._notifications.add(task)
        task.add_done_callback(self._notification_done)

    def _notification_done(self, task: asyncio.Task[None]) -> None:
        self._notifications.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logging.getLogger(__name__).warning(
                "Preview visibility delivery failed: %s", task.exception()
            )
