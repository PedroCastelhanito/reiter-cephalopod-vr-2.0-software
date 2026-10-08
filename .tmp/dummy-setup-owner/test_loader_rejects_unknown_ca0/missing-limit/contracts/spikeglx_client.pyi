"""E12 controller-owned SpikeGLX client boundary (spikeglx-control.md).

Declaration only. Implemented over the official SpikeGLX SDK Python wrapper; every
call runs on its owner's serialized SpikeGLX I/O thread with an absolute deadline.
The controller is the only client; there is no supervisor fallback.
"""
from dataclasses import dataclass
from typing import Literal

StreamFamily = Literal["ni", "onebox", "imec"]  # Native js codes 0, 1, 2.
PulseRole = Literal["behavioral_camera", "tracking_camera", "photodiode"]


@dataclass(frozen=True)
class StreamInfo:
    family: StreamFamily
    index: int
    sample_rate_hz: float
    acquired_channel_counts: tuple[int, ...]
    saved_channel_indices: tuple[int, ...]
    hardware_serial: str | None


@dataclass(frozen=True)
class PulseChannel:
    role: PulseRole
    family: StreamFamily
    stream_index: int
    channel_index: int
    bit: int | None


@dataclass(frozen=True)
class Readback:
    spikeglx_version: str
    sdk_version: str
    mapping_id: str
    run_name: str
    data_directory: str
    running: bool
    streams: tuple[StreamInfo, ...]
    gate_mode: str
    trigger_mode: str
    params_digest: str  # Canonical digest of getParams groups for change detection.


@dataclass(frozen=True)
class Progress:
    running: bool | None  # None: query failed or timed out (unknown).
    saving: bool | None
    run_name: str | None
    sample_counts: tuple[tuple[StreamFamily, int, int], ...]  # (family, index, count)
    observed_ns: int  # host_time_ns() at completion.


class Unknown(Exception):
    """A mutating call's outcome is unknown; query before any further mutation."""


class SpikeGLXClient:
    def __init__(self, address: str, port: int) -> None: ...
    def connect(self, deadline_ns: int) -> None: ...
    def close(self) -> None: ...
    def read_back(self, deadline_ns: int) -> Readback: ...
    def check_pulse_inventory(
        self, readback: Readback, required: tuple[PulseRole, ...],
        inventory: tuple[PulseChannel, ...],
    ) -> tuple[PulseChannel, ...]: ...  # Raises on unmapped/wrong-stream/unsaved roles.
    def set_run_name(self, name: str, deadline_ns: int) -> None: ...  # May raise Unknown.
    def start_run(self, deadline_ns: int) -> None: ...  # May raise Unknown.
    def progress(self, deadline_ns: int) -> Progress: ...
    def stop_run(self, deadline_ns: int) -> None: ...  # May raise Unknown.
