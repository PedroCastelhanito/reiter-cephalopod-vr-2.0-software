"""Controller-owned Configuration firmware handoff and outputs-off verification."""

import asyncio
from collections.abc import Callable

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.microcontroller.firmware import FirmwareUploadPort
from cephvr.controller.microcontroller.firmware_source import (
    FirmwareSketch,
    read_firmware,
)
from cephvr.shared.microcontroller import SerialOwnerPort


class FirmwareUpdate:
    def __init__(
        self,
        uploader: FirmwareUploadPort | None,
        serial: SerialOwnerPort,
        view: pb.MicrocontrollerDeviceView,
        clock: Callable[[], int],
    ) -> None:
        self.uploader = uploader
        self.serial = serial
        self.view = view
        self.clock = clock
        self.task: asyncio.Task[None] | None = None
        self.serial_cleanup_pending = False
        self.cancelled = False

    @property
    def busy(self) -> bool:
        return (
            self.serial_cleanup_pending
            or (self.task is not None and not self.task.done())
            or (self.uploader is not None and not self.uploader.cleanup_complete)
        )

    def ensure_idle(self) -> None:
        if self.busy:
            raise RuntimeError(
                "Firmware update or exact native cleanup is still pending"
            )

    async def execute(
        self,
        path: str,
        digest: str,
        port: str,
        operation: pb.OperationContext,
        deadline_ns: int,
    ) -> None:
        self.ensure_idle()
        if self.uploader is None:
            raise RuntimeError("Firmware upload is unavailable in this controller")
        self.cancelled = False
        self.uploader.reset_cancel()
        self.task = asyncio.create_task(
            self._perform(path, digest, port, operation, deadline_ns)
        )
        await asyncio.shield(self.task)

    async def _perform(
        self,
        path: str,
        digest: str,
        port: str,
        operation: pb.OperationContext,
        deadline_ns: int,
    ) -> None:
        assert self.uploader is not None
        released_serial = False
        try:
            selected = await asyncio.to_thread(read_firmware, path, digest)
            self._check(deadline_ns)
            image = (
                await asyncio.to_thread(
                    self.uploader.compile, selected, operation, deadline_ns=deadline_ns
                )
                if isinstance(selected, FirmwareSketch)
                else selected
            )
            self._check(deadline_ns)
            await asyncio.to_thread(self.uploader.prepare, image)
            self._check(deadline_ns)
            self.view.ClearField("observation")
            self.serial_cleanup_pending = True
            await self.serial.close(deadline_ns=deadline_ns)
            self.serial_cleanup_pending = False
            released_serial = True
            self.view.ClearField("diagnostic")
            await asyncio.to_thread(
                self.uploader.upload, port, operation, deadline_ns=deadline_ns
            )
            self._check(deadline_ns)
            await self.serial.connect(deadline_ns=deadline_ns)
            active, _, _, _ = await self.serial.diagnostic_stop(deadline_ns=deadline_ns)
            if active:
                raise RuntimeError("Firmware diagnostic output did not stop")
            observation = await self.serial.status(deadline_ns=deadline_ns)
            if not all(
                observation.state.HasField(role)
                and getattr(observation.state, role).HasField("running")
                and not getattr(observation.state, role).running
                for role in ("behavioral", "tracking")
            ):
                raise RuntimeError(
                    "Firmware verification did not confirm stopped camera outputs"
                )
            self.view.observation.CopyFrom(observation)
        except BaseException:
            if released_serial:
                self.view.ClearField("observation")
                self.serial_cleanup_pending = True
                await self.serial.close(deadline_ns=deadline_ns)
                self.serial_cleanup_pending = False
            raise
        finally:
            await asyncio.to_thread(self.uploader.close, deadline_ns=deadline_ns)

    def _check(self, deadline_ns: int) -> None:
        if self.cancelled or self.clock() >= deadline_ns:
            raise RuntimeError(
                "Firmware update cancelled or expired before the next phase"
            )

    async def close(self, *, deadline_ns: int) -> None:
        self.cancelled = True
        if self.uploader is not None:
            self.uploader.cancel()
            if self.task is not None:
                try:
                    async with asyncio.timeout(
                        max(0, (deadline_ns - self.clock()) / 1e9)
                    ):
                        await asyncio.shield(self.task)
                except (OSError, RuntimeError, ValueError, UnicodeError):
                    if not self.task.done():
                        raise
            await asyncio.to_thread(self.uploader.close, deadline_ns=deadline_ns)
        if self.serial_cleanup_pending:
            await self.serial.close(deadline_ns=deadline_ns)
            self.serial_cleanup_pending = False
        self.ensure_idle()
