"""Bounded exact-request replay for authenticated camera-trigger operations."""

import asyncio
from collections.abc import Awaitable, Callable

from cephvr.control.v1 import services_pb2 as wire
from cephvr.shared.commands import CommandLedger


class MicrocontrollerIoAdmission:
    def __init__(
        self,
        ledger: CommandLedger,
        clock: Callable[[], int],
        execute: Callable[
            [wire.MicrocontrollerIoRequest], Awaitable[wire.MicrocontrollerIoResult]
        ],
    ) -> None:
        self.ledger = ledger
        self.clock = clock
        self.operation = execute
        self.tasks: dict[str, asyncio.Task[wire.MicrocontrollerIoResult]] = {}

    async def execute(
        self, request: wire.MicrocontrollerIoRequest
    ) -> wire.MicrocontrollerIoResult:
        try:
            admission = self.ledger.admit(
                request.command_id,
                request.SerializeToString(deterministic=True),
                self.clock(),
                work_key=request.command_id,
                deadline_ns=request.deadline_monotonic_ns,
                result_reservation_bytes=65_536,
                priority=request.kind
                in {
                    wire.MICROCONTROLLER_IO_KIND_OFF,
                    wire.MICROCONTROLLER_IO_KIND_CLOSE,
                    wire.MICROCONTROLLER_IO_KIND_CANCEL_ON,
                    wire.MICROCONTROLLER_IO_KIND_CANCEL_ACTIVE,
                },
            )
        except (RuntimeError, ValueError) as exc:
            return wire.MicrocontrollerIoResult(
                command_id=request.command_id, failure=str(exc)
            )
        if admission.record.result is not None:
            return wire.MicrocontrollerIoResult.FromString(admission.record.result)
        task = self.tasks.get(request.command_id)
        if task is None:
            if admission.replayed:
                return wire.MicrocontrollerIoResult(
                    command_id=request.command_id,
                    failure="Microcontroller command has no confirmed retained executor",
                )
            task = asyncio.create_task(self._perform(request))
            self.tasks[request.command_id] = task
        return await asyncio.shield(task)

    async def _perform(
        self, request: wire.MicrocontrollerIoRequest
    ) -> wire.MicrocontrollerIoResult:
        try:
            try:
                if self.clock() >= request.deadline_monotonic_ns:
                    raise TimeoutError(
                        "Original Microcontroller deadline expired before execution"
                    )
                result = await self.operation(request)
                if (
                    self.clock() >= request.deadline_monotonic_ns
                    and not result.HasField("evidence")
                ):
                    raise TimeoutError(
                        "Microcontroller completion missed its original deadline"
                    )
            except Exception as exc:
                result = wire.MicrocontrollerIoResult(
                    command_id=request.command_id, failure=str(exc)[:2048]
                )
            self.ledger.complete(
                request.command_id,
                result.SerializeToString(deterministic=True),
                self.clock(),
            )
            self.ledger.finalize_work(request.command_id, self.clock())
            return result
        finally:
            self.tasks.pop(request.command_id, None)

    async def close(self) -> None:
        if self.tasks:
            await asyncio.gather(*tuple(self.tasks.values()), return_exceptions=True)
