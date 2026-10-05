"""Async, single-owner-thread bridge for the synchronous serial controller."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar, cast

from cephvr.acquisition.v1 import camera_pb2, microcontroller_pb2
from cephvr.shared.clock import host_time_ns

from .owner import SerialOwner, SerialOwnerError

_T = TypeVar("_T")


class SerialOwnerBridge:
    """Serialize every port call and retain ownership while blocked I/O drains."""

    def __init__(
        self,
        owner: SerialOwner | Callable[[], SerialOwner],
        *,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self._owner: SerialOwner | None = (
            owner if isinstance(owner, SerialOwner) else None
        )
        self._owner_factory: Callable[[], SerialOwner] | None = (
            None if self._owner is not None else cast(Callable[[], SerialOwner], owner)
        )
        self._clock = clock
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="cephvr-serial-owner"
        )
        self._gate = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._active: asyncio.Future[object] | None = None
        self._closing = False
        self._closed = False

    async def connect(
        self, *, deadline_ns: int
    ) -> microcontroller_pb2.MicrocontrollerObservation:
        return await self._call(
            lambda: self._get_owner().connect(deadline_ns), deadline_ns
        )

    async def configure(
        self,
        requested: camera_pb2.CameraPulseConfiguration,
        *,
        active_roles: tuple[int | str, ...],
        deadline_ns: int,
    ) -> microcontroller_pb2.MicrocontrollerObservation:
        return await self._call(
            lambda: self._get_owner().configure(
                requested, deadline_ns, active_roles=active_roles
            ),
            deadline_ns,
        )

    async def status(
        self, *, deadline_ns: int
    ) -> microcontroller_pb2.MicrocontrollerObservation:
        return await self._call(
            lambda: self._get_owner().status(deadline_ns), deadline_ns
        )

    async def keepalive(
        self, *, deadline_ns: int
    ) -> microcontroller_pb2.MicrocontrollerState:
        return await self._call(
            lambda: self._get_owner().keepalive(deadline_ns), deadline_ns
        )

    async def diagnostic_start(
        self, kind: str, pin: str, *, frequency_hz: float | None, deadline_ns: int
    ) -> tuple[bool, str, str, int]:
        return await self._call(
            lambda: self._get_owner().diagnostic_start(
                kind, pin, deadline_ns, frequency_hz=frequency_hz
            ),
            deadline_ns,
        )

    async def diagnostic_status(
        self, *, deadline_ns: int
    ) -> tuple[bool, str, str, int]:
        return await self._call(
            lambda: self._get_owner().diagnostic_status(deadline_ns), deadline_ns
        )

    async def diagnostic_stop(self, *, deadline_ns: int) -> tuple[bool, str, str, int]:
        return await self._call(
            lambda: self._get_owner().diagnostic_stop(deadline_ns), deadline_ns
        )

    async def on(
        self,
        selected_roles: tuple[int | str, ...],
        *,
        scheduled_boundary_ns: int | None,
        deadline_ns: int,
    ) -> microcontroller_pb2.PulseCommandEvidence:
        return await self._call(
            lambda: self._get_owner().on(
                selected_roles,
                deadline_ns,
                scheduled_boundary_ns=scheduled_boundary_ns,
            ),
            deadline_ns,
        )

    async def off(
        self,
        selected_roles: tuple[int | str, ...],
        *,
        scheduled_boundary_ns: int | None,
        stop_issued_ns: int | None,
        deadline_ns: int,
    ) -> microcontroller_pb2.PulseCommandEvidence:
        return await self._call(
            lambda: self._get_owner().off(
                selected_roles,
                deadline_ns,
                scheduled_boundary_ns=scheduled_boundary_ns,
                stop_issued_ns=stop_issued_ns,
            ),
            deadline_ns,
        )

    async def reserve_boundary(
        self,
        boundary_ns: int,
        command: microcontroller_pb2.PulseBoundaryCommand,
        *,
        selected_roles: tuple[int | str, ...],
        deadline_ns: int,
    ) -> None:
        await self._call(
            lambda: self._get_owner().reserve_boundary(
                boundary_ns, command, selected_roles=selected_roles
            ),
            deadline_ns,
        )

    async def cancel_on_reservations(self, *, deadline_ns: int) -> None:
        await self._call(
            lambda: self._get_owner().cancel_on_reservations(), deadline_ns
        )

    async def cancel_active_request(self) -> bool:
        owner = self._owner
        return False if owner is None else owner.cancel_active_request()

    async def close(self, *, deadline_ns: int) -> None:
        if self._closed:
            return
        self._closing = True
        owner = self._owner
        if self._active is not None and not self._active.done() and owner is not None:
            owner.cancel_active_request()
        await self._call(
            lambda: self._close_owner(deadline_ns),
            deadline_ns,
            allow_closing=True,
        )
        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=False)

    async def _call(
        self,
        operation: Callable[[], _T],
        deadline_ns: int,
        *,
        allow_closing: bool = False,
    ) -> _T:
        if self._closed or self._closing and not allow_closing:
            raise SerialOwnerError("serial owner bridge is closed")
        if self._clock() >= deadline_ns:
            raise TimeoutError("serial command deadline expired before admission")
        if not await self._acquire_until(deadline_ns):
            raise TimeoutError("serial owner remained busy through command deadline")
        if self._closed or self._closing and not allow_closing:
            self._gate.release()
            raise SerialOwnerError("serial owner bridge is closed")
        future: asyncio.Future[_T] | None = None
        callback_registered = False
        cancel_before_dispatch = threading.Event()

        def invoke_before_deadline() -> _T:
            if cancel_before_dispatch.is_set():
                raise TimeoutError("serial command was cancelled before dispatch")
            if self._clock() >= deadline_ns:
                raise TimeoutError(
                    "serial command expired before owner-thread dispatch"
                )
            return operation()

        try:
            loop = self._event_loop()
            future = loop.run_in_executor(self._executor, invoke_before_deadline)
            self._active = cast(asyncio.Future[object], future)
            cast(asyncio.Future[object], future).add_done_callback(
                self._release_after_return
            )
            callback_registered = True
        except BaseException:
            if future is None:
                self._gate.release()
            elif not callback_registered:
                # The native call may already be running. Retain the gate until its
                # completion rather than allowing another request to overwrite it.
                cast(asyncio.Future[object], future).add_done_callback(
                    self._release_after_return
                )
            raise
        remaining = max(0, deadline_ns - self._clock()) / 1_000_000_000
        try:
            done, _ = await asyncio.wait((future,), timeout=remaining)
        except asyncio.CancelledError:
            cancel_before_dispatch.set()
            owner = self._owner
            if owner is not None:
                owner.cancel_active_request()
            raise
        if not done:
            cancel_before_dispatch.set()
            owner = self._owner
            if owner is not None:
                owner.cancel_active_request()
            raise TimeoutError("serial command exceeded its original deadline")
        if self._clock() >= deadline_ns:
            raise TimeoutError(
                "serial owner call completed after its original deadline"
            )
        return future.result()

    async def _acquire_until(self, deadline_ns: int) -> bool:
        remaining = max(0, deadline_ns - self._clock()) / 1_000_000_000
        if remaining <= 0:
            return False
        waiter = asyncio.create_task(self._gate.acquire())
        try:
            done, _ = await asyncio.wait((waiter,), timeout=remaining)
        except asyncio.CancelledError:
            waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)
            if not waiter.cancelled() and waiter.result():
                self._gate.release()
            raise
        if waiter not in done:
            waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)
            if not waiter.cancelled() and waiter.result():
                self._gate.release()
            return False
        return waiter.result()

    def _event_loop(self) -> asyncio.AbstractEventLoop:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise RuntimeError("serial owner bridge cannot move between event loops")
        return loop

    def _release_after_return(self, future: asyncio.Future[object]) -> None:
        if not future.cancelled():
            future.exception()
        self._active = None
        if self._gate.locked():
            self._gate.release()

    def _get_owner(self) -> SerialOwner:
        owner = self._owner
        if owner is not None:
            return owner
        factory = self._owner_factory
        if factory is None:
            raise SerialOwnerError("serial owner factory is unavailable")
        owner = factory()
        self._owner = owner
        self._owner_factory = None
        return owner

    def _close_owner(self, deadline_ns: int) -> None:
        owner = self._owner
        if owner is not None:
            owner.close(deadline_ns)
