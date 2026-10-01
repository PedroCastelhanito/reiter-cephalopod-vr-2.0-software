"""Bounded preparation reservations for immutable Visual Stimulus assets."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import Protocol


class PreparationBudget(Protocol):
    def check_cancelled_or_expired(self) -> None: ...

    def reserve(self, *, owner: str, cpu_bytes: int, gpu_bytes: int) -> None: ...

    def release(self, *, owner: str) -> None: ...


@dataclass(frozen=True, slots=True)
class ResourceUsage:
    cpu_bytes: int
    gpu_bytes: int


def arena_texture_bytes(width: int, height: int, *, mipmapped: bool) -> int:
    """Two RGBA32F material variants, including every allocated mip level."""
    if min(width, height) <= 0:
        raise ValueError("positive arena texture dimensions required")
    pixels = width * height
    while mipmapped and (width > 1 or height > 1):
        width, height = max(1, width // 2), max(1, height // 2)
        pixels += width * height
    return pixels * 16 * 2


def arena_mesh_bytes(vertex_count: int, index_count: int) -> int:
    """Upload ABI: float32 position3/UV2/color4 plus uint32 indices."""
    if min(vertex_count, index_count) < 0:
        raise ValueError("nonnegative arena mesh element counts required")
    return vertex_count * 9 * 4 + index_count * 4


class BoundedBudget:
    """Thread-safe checked accounting; reservations are atomic by owner."""

    def __init__(
        self,
        *,
        cpu_limit: int,
        gpu_limit: int,
        cancelled: threading.Event | None = None,
        deadline_ns: int | None = None,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        if cpu_limit <= 0 or gpu_limit <= 0:
            raise ValueError("resource limits must be positive")
        self.cpu_limit = cpu_limit
        self.gpu_limit = gpu_limit
        self.cancelled = cancelled
        self.deadline_ns = deadline_ns
        self.clock_ns = clock_ns
        self._usage: dict[str, ResourceUsage] = {}
        self._lock = RLock()

    @property
    def usage(self) -> ResourceUsage:
        with self._lock:
            return ResourceUsage(
                sum(item.cpu_bytes for item in self._usage.values()),
                sum(item.gpu_bytes for item in self._usage.values()),
            )

    def reserve(self, *, owner: str, cpu_bytes: int, gpu_bytes: int) -> None:
        if not owner or min(cpu_bytes, gpu_bytes) < 0:
            raise ValueError("owner and nonnegative resource sizes are required")
        candidate = ResourceUsage(cpu_bytes, gpu_bytes)
        with self._lock:
            old = self._usage.get(owner, ResourceUsage(0, 0))
            cpu = (
                sum(v.cpu_bytes for v in self._usage.values())
                - old.cpu_bytes
                + cpu_bytes
            )
            gpu = (
                sum(v.gpu_bytes for v in self._usage.values())
                - old.gpu_bytes
                + gpu_bytes
            )
            if cpu > self.cpu_limit or gpu > self.gpu_limit:
                raise MemoryError(
                    f"resource budget exceeded for {owner}: "
                    f"CPU {cpu}/{self.cpu_limit}, GPU {gpu}/{self.gpu_limit}"
                )
            self._usage[owner] = candidate

    def release(self, *, owner: str) -> None:
        with self._lock:
            self._usage.pop(owner, None)

    def check_cancelled_or_expired(self) -> None:
        if self.cancelled is not None and self.cancelled.is_set():
            raise InterruptedError("Visual Stimulus preparation was cancelled")
        if self.deadline_ns is not None and self.clock_ns() >= self.deadline_ns:
            raise TimeoutError("Visual Stimulus preparation deadline expired")
