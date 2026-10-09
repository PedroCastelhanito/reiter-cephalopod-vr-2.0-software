"""Bounded event-loop wake verification for blocking camera waits (A02)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from threading import Event, Lock
from typing import Protocol

from cephvr.shared.clock import host_time_ns


class BlockingWaitCamera(Protocol):
    def verify_blocking_wait_wakeup(
        self,
        schedule_wake: Callable[[Callable[[], None]], Event],
        timeout_ns: int,
    ) -> None: ...


def verify_blocking_wait(
    loop: asyncio.AbstractEventLoop,
    camera: BlockingWaitCamera,
    deadline_ns: int,
    *,
    clock_ns: Callable[[], int] = host_time_ns,
) -> None:
    remaining = deadline_ns - clock_ns()
    if remaining <= 0:
        raise TimeoutError("camera wait compatibility deadline expired")
    timeout_ns = min(250_000_000, remaining)
    delay_s = min(0.01, timeout_ns / 2_000_000_000)
    cancelled = Event()
    callback_lock = Lock()
    acknowledgement = Event()
    handles: list[asyncio.TimerHandle] = []

    def fire(wake_private_event: Callable[[], None]) -> None:
        with callback_lock:
            if cancelled.is_set():
                return
            wake_private_event()
            acknowledgement.set()

    def register(wake_private_event: Callable[[], None]) -> None:
        with callback_lock:
            if cancelled.is_set():
                return
            handles.append(loop.call_later(delay_s, fire, wake_private_event))

    def schedule_wake(wake_private_event: Callable[[], None]) -> Event:
        loop.call_soon_threadsafe(register, wake_private_event)
        return acknowledgement

    try:
        camera.verify_blocking_wait_wakeup(schedule_wake, timeout_ns)
    finally:
        with callback_lock:
            cancelled.set()

        def cancel_handles() -> None:
            for handle in handles:
                handle.cancel()

        loop.call_soon_threadsafe(cancel_handles)
