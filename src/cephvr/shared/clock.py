"""E08's unshifted host clock and process-registration compatibility check."""

from __future__ import annotations

import math
import platform
import sys
import time
from dataclasses import dataclass
from typing import Final, Protocol

HOST_CLOCK_ID: Final = "cephvr.host.perf_counter_ns.v1"
INT64_MAX: Final = (1 << 63) - 1


@dataclass(frozen=True)
class HostClockDescriptor:
    clock_id: str
    implementation: str
    monotonic: bool
    adjustable: bool
    resolution_s: float


class HostClockCompatibilityError(RuntimeError):
    """The process cannot share E08's host timestamp domain."""


class HostClockWire(Protocol):
    clock_id: str
    implementation: str
    monotonic: bool
    adjustable: bool
    resolution_s: float

    def HasField(self, field_name: str) -> bool: ...


def host_time_ns() -> int:
    """Read the unmodified system-wide host counter."""
    return time.perf_counter_ns()


def require_int64_ns(value: int) -> int:
    """Validate a host timestamp at a signed-int64 wire/file boundary."""
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= INT64_MAX
    ):
        raise ValueError("host nanoseconds must be a nonnegative signed int64")
    return value


def _validate_descriptor(value: HostClockDescriptor) -> None:
    if value.clock_id != HOST_CLOCK_ID:
        raise HostClockCompatibilityError("host clock domain mismatch")
    if not value.implementation:
        raise HostClockCompatibilityError("host clock implementation is missing")
    if value.monotonic is not True or value.adjustable is not False:
        raise HostClockCompatibilityError(
            "host clock must be monotonic and unadjustable"
        )
    if not math.isfinite(value.resolution_s) or value.resolution_s <= 0:
        raise HostClockCompatibilityError(
            "host clock resolution must be finite and positive"
        )


def describe_host_clock() -> HostClockDescriptor:
    """Validate this CPython binding before the process becomes operational."""
    if platform.python_implementation() != "CPython":
        raise HostClockCompatibilityError("system-wide perf_counter requires CPython")
    if sys.platform == "win32" and sys.version_info < (3, 10):
        raise HostClockCompatibilityError("Windows requires Python 3.10 or later")
    info = time.get_clock_info("perf_counter")
    value = HostClockDescriptor(
        HOST_CLOCK_ID,
        info.implementation,
        info.monotonic,
        info.adjustable,
        info.resolution,
    )
    _validate_descriptor(value)
    if (
        sys.platform == "win32"
        and "QueryPerformanceCounter" not in value.implementation
    ):
        raise HostClockCompatibilityError("Windows perf_counter is not QPC-backed")
    return value


def validate_host_clock(
    candidate: HostClockDescriptor, expected: HostClockDescriptor
) -> None:
    """Compare a registered child with this host's validated clock descriptor."""
    _validate_descriptor(expected)
    _validate_descriptor(candidate)
    if candidate.implementation != expected.implementation:
        raise HostClockCompatibilityError("host clock implementation mismatch")


def descriptor_from_wire(wire: HostClockWire) -> HostClockDescriptor:
    """Reject absent proto3 optional fields before comparing launch evidence."""
    for field_name in ("monotonic", "adjustable", "resolution_s"):
        if not wire.HasField(field_name):
            raise HostClockCompatibilityError(f"missing host clock {field_name}")
    value = HostClockDescriptor(
        wire.clock_id,
        wire.implementation,
        wire.monotonic,
        wire.adjustable,
        wire.resolution_s,
    )
    _validate_descriptor(value)
    return value
