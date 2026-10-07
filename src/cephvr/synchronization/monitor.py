"""Frozen-session SpikeGLX sample observations and gate baseline (E12)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from cephvr.shared.clock import host_time_ns
from cephvr.synchronization.diagnostic import _load_sdk, _required, _sdk_package
from cephvr.synchronization.native import (
    _FAMILY,
    _STREAMS,
    Readback,
    read_sdk,
)
from cephvr.synchronization.sdk_io import SpikeGLXIOOwner
from cephvr.synchronization.settings import HostSettings
from cephvr.synchronization.v1 import spikeglx_pb2 as wire


class SpikeGLXProgressIO:
    """Read stream counts against one captured endpoint, budget and run identity."""

    def __init__(
        self,
        *,
        software_root: Path,
        settings: HostSettings,
        expected: wire.SpikeGLXPreparation | None,
        io_owner: SpikeGLXIOOwner,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.software_root = software_root
        self.settings = settings
        self.expected = expected
        self.io_owner = io_owner
        self.clock = clock
        self._baseline: tuple[wire.StreamProgress, ...] = ()

    async def sample_counts(
        self, deadline_ns: int
    ) -> tuple[Readback, tuple[tuple[int, int, int], ...]]:
        def read() -> tuple[Readback, tuple[tuple[int, int, int], ...]]:
            readback = read_sdk(self.software_root, self.settings)
            if not readback.running or not readback.saving:
                return readback, ()
            sdk = _load_sdk(_sdk_package(self.software_root))
            handle = sdk.c_sglx_createHandle()
            if not handle:
                raise RuntimeError("SpikeGLX SDK could not create a connection handle")
            try:
                _required(
                    sdk.c_sglx_connect(
                        handle,
                        self.settings.address.encode(),
                        self.settings.port,
                    ),
                    sdk,
                    handle,
                    "connect",
                )
                samples = []
                for stream in readback.streams:
                    if not stream.saved_channel_indices:
                        continue
                    family = next(
                        key for key, enum in _FAMILY.items() if enum == stream.family
                    )
                    code = _STREAMS[family]
                    samples.append(
                        (
                            code,
                            stream.index,
                            int(
                                sdk.c_sglx_getStreamSampleCount(
                                    handle, code, stream.index
                                )
                            ),
                        )
                    )
                return readback, tuple(samples)
            finally:
                try:
                    sdk.c_sglx_close(handle)
                finally:
                    sdk.c_sglx_destroyHandle(handle)

        remaining = deadline_ns - self.clock()
        if remaining <= 0:
            raise TimeoutError("SpikeGLX operation missed its original deadline")
        result = await self.io_owner.run(
            read, min(self.settings.native_call_timeout_s, remaining / 1e9)
        )
        if self.clock() >= deadline_ns:
            raise TimeoutError("SpikeGLX sample observation missed its deadline")
        return result

    def record_writing_baseline(
        self, samples: tuple[tuple[int, int, int], ...], observed_ns: int
    ) -> None:
        if self.expected is None:
            raise RuntimeError("SpikeGLX prepared run identity is unavailable")
        counts = {(family, index): count for family, index, count in samples}
        baseline = []
        for stream in self.expected.streams:
            if not stream.saved_channel_indices:
                continue
            key = (int(stream.family) - 1, stream.index)
            if key not in counts:
                raise ValueError("writing baseline omitted a saved stream")
            baseline.append(
                wire.StreamProgress(
                    family=stream.family,
                    index=stream.index,
                    sample_count=counts[key],
                    last_progress_monotonic_ns=observed_ns,
                )
            )
        self._baseline = tuple(baseline)

    def baseline(self) -> tuple[wire.StreamProgress, ...]:
        if not self._baseline:
            raise RuntimeError("SpikeGLX writing baseline was not confirmed")
        return tuple(
            wire.StreamProgress.FromString(item.SerializeToString())
            for item in self._baseline
        )

    async def observe(self, deadline_ns: int) -> wire.SpikeGLXRecordingView:
        expected = self.expected
        if expected is None:
            raise RuntimeError("SpikeGLX prepared run identity is unavailable")
        try:
            readback, samples = await self.sample_counts(deadline_ns)
        except Exception as exc:
            return wire.SpikeGLXRecordingView(
                phase=wire.SPIKEGLX_RECORDING_PHASE_UNKNOWN,
                failure_code=type(exc).__name__,
            )
        if self.clock() >= deadline_ns:
            return wire.SpikeGLXRecordingView(
                phase=wire.SPIKEGLX_RECORDING_PHASE_UNKNOWN,
                failure_code="DEADLINE",
            )
        observed = {(family, index): count for family, index, count in samples}
        matches = (
            readback.run_name == expected.run_name
            and readback.data_directory == expected.data_directory
        )
        if not readback.running or not readback.saving or not matches:
            return wire.SpikeGLXRecordingView(
                phase=wire.SPIKEGLX_RECORDING_PHASE_UNKNOWN,
                running=readback.running,
                saving=readback.saving,
                run_name_matches=matches,
                observed_monotonic_ns=self.clock(),
            )
        saved = {
            (int(stream.family) - 1, stream.index)
            for stream in expected.streams
            if stream.saved_channel_indices
        }
        if not saved or not saved <= observed.keys():
            return wire.SpikeGLXRecordingView(
                phase=wire.SPIKEGLX_RECORDING_PHASE_UNKNOWN,
                failure_code="SAMPLE_COUNT_MISSING",
            )
        phase = (
            wire.SPIKEGLX_RECORDING_PHASE_WRITING
            if readback.running and readback.saving and matches
            else wire.SPIKEGLX_RECORDING_PHASE_UNKNOWN
        )
        view = wire.SpikeGLXRecordingView(
            phase=phase,
            running=readback.running,
            saving=readback.saving,
            run_name_matches=matches,
            observed_monotonic_ns=self.clock(),
        )
        for stream in expected.streams:
            if stream.saved_channel_indices:
                view.progress.add(
                    family=stream.family,
                    index=stream.index,
                    sample_count=observed[(int(stream.family) - 1, stream.index)],
                )
        return view

    def budgets(self) -> tuple[float, float, float]:
        return (
            self.settings.observation_interval_s,
            self.settings.native_call_timeout_s,
            self.settings.no_progress_timeout_s,
        )
