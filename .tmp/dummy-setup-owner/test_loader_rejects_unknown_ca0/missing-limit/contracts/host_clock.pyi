"""E08 host-clock implementation interface. Declarations only; see host-clock.md."""
from dataclasses import dataclass
from typing import Final

HOST_CLOCK_ID: Final[str] = "cephvr.host.perf_counter_ns.v1"

@dataclass(frozen=True)
class HostClockDescriptor:
    clock_id: str
    implementation: str
    monotonic: bool
    adjustable: bool
    resolution_s: float

class HostClockCompatibilityError(RuntimeError): ...

# Implementation returns time.perf_counter_ns() unchanged, without state or I/O.
def host_time_ns() -> int: ...

# Describes and validates the current runtime; raises on unsupported local binding.
def describe_host_clock() -> HostClockDescriptor: ...

# Pure compatibility check; no timing probe, offset estimation or configuration edit.
# expected is the supervisor's already validated local descriptor.
def validate_host_clock(candidate: HostClockDescriptor, expected: HostClockDescriptor) -> None: ...
