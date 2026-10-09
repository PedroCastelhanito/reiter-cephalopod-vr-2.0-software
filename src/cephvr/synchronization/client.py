"""Controller-owned SpikeGLX lifecycle client over the serialized SDK owner."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.clock import host_time_ns
from cephvr.shared.deadlines import remaining_seconds
from cephvr.synchronization.v1 import spikeglx_pb2 as wire

from .diagnostic import _required
from .inventory_validation import (
    required_inventory_roles as _required_inventory_roles,
)
from .inventory_validation import (
    validate_inventory as _validate_inventory,
)
from .monitor import SpikeGLXProgressIO
from .native import (
    Readback,
    read_sdk,
    with_sdk,
)
from .sdk_io import SpikeGLXIOBusy, SpikeGLXIOOwner
from .settings import HostSettings, load_host_settings


class SpikeGLXControllerClient:
    """Concrete E12 port; timeouts retain the one shared SDK I/O owner."""

    def __init__(
        self,
        software_root: Path,
        *,
        controller_generation: str,
        io_owner: SpikeGLXIOOwner | None = None,
        clock: Callable[[], int] = host_time_ns,
        sleep: Callable[[float], Any] | None = None,
    ) -> None:
        import asyncio

        self.software_root = software_root
        self.controller_generation = controller_generation
        self.io_owner = io_owner or SpikeGLXIOOwner()
        self.clock = clock
        self._sleep = sleep or asyncio.sleep
        self._prepared: wire.SpikeGLXPreparation | None = None
        self._prepared_settings: HostSettings | None = None
        self._params_digest = ""
        self._start_uncertain = False
        self._mutation_uncertain = False
        self._stopped = False
        self._monitor_baseline: tuple[wire.StreamProgress, ...] = ()
        self._progress_io: SpikeGLXProgressIO | None = None

    async def _run(self, operation: Callable[[], Any], timeout_s: float) -> Any:
        return await self.io_owner.run(operation, timeout_s)

    async def prepare(
        self,
        configuration: pb.ExperimentConfiguration,
        session: pb.SessionContext,
        run_name: str,
    ) -> wire.SpikeGLXPreparation:
        del session
        settings = load_host_settings(self.software_root)
        self._monitor_baseline = ()
        if self._start_uncertain or self._mutation_uncertain:
            raise SpikeGLXIOBusy(
                "SpikeGLX mutation outcome must be reconciled before Setup"
            )
        readback = await self._run(
            lambda: read_sdk(self.software_root, settings),
            settings.native_call_timeout_s,
        )
        if readback.running:
            raise RuntimeError(
                "SpikeGLX already has a running acquisition; refusing adoption"
            )
        if readback.gate_mode != "immediate" or readback.trigger_mode != "immediate":
            raise RuntimeError(
                f"SpikeGLX gate/trigger must both be immediate, got {readback.gate_mode}/{readback.trigger_mode}"
            )
        resolved_inventory = _validate_inventory(
            settings.inventory,
            readback.streams,
            settings.mapping,
            required_roles=_required_inventory_roles(configuration),
        )
        expected_digest = readback.params_digest
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", run_name):
            raise ValueError("managed SpikeGLX run name has invalid characters")

        def set_name(sdk: Any, handle: int) -> None:
            _required(
                sdk.c_sglx_setRunName(handle, run_name.encode("utf-8")),
                sdk,
                handle,
                "setRunName",
            )

        try:
            await self._run(
                lambda: with_sdk(self.software_root, settings, set_name),
                settings.native_call_timeout_s,
            )
        except (TimeoutError, SpikeGLXIOBusy):
            self._mutation_uncertain = True
            raise
        renamed = await self._run(
            lambda: read_sdk(self.software_root, settings),
            settings.native_call_timeout_s,
        )
        if (
            renamed.run_name != run_name
            or renamed.data_directory != readback.data_directory
        ):
            raise RuntimeError("SpikeGLX run name or data directory readback differs")
        result = wire.SpikeGLXPreparation(
            spikeglx_version=renamed.version,
            # getVersion reports the remote SpikeGLX server. The installed SDK
            # wrapper/DLL exposes no build identity, so don't copy the mapping's
            # expected API version into a field that claims an observed SDK build.
            sdk_version="unknown",
            mapping_id=str(settings.mapping["mapping_id"]),
            run_name=run_name,
            data_directory=renamed.data_directory,
            gate_mode=renamed.gate_mode,
            trigger_mode=renamed.trigger_mode,
            address=settings.address,
            port=settings.port,
            pulse_channels=resolved_inventory,
        )
        result.streams.extend(renamed.streams)
        self._prepared = wire.SpikeGLXPreparation.FromString(result.SerializeToString())
        self._prepared_settings = settings
        self._params_digest = expected_digest
        self._stopped = False
        self._progress_io = SpikeGLXProgressIO(
            software_root=self.software_root,
            settings=settings,
            expected=self._prepared,
            io_owner=self.io_owner,
            clock=self.clock,
        )
        return result

    async def verify_before_start(self, deadline_ns: int | None = None) -> bool:
        settings = self._require_settings()
        expected = self._require_prepared()
        if self._start_uncertain:
            return False
        if load_host_settings(self.software_root) != settings:
            return False
        return await self._verify_before_start(
            settings,
            expected,
            deadline_ns or self.clock() + int(settings.native_call_timeout_s * 1e9),
        )

    async def _verify_before_start(
        self,
        settings: HostSettings,
        expected: wire.SpikeGLXPreparation,
        deadline_ns: int,
    ) -> bool:
        timeout_s = self._remaining_timeout(settings, deadline_ns)
        readback = await self._run(
            lambda: read_sdk(self.software_root, settings),
            timeout_s,
        )
        if self.clock() >= deadline_ns:
            return False
        return (
            not readback.running
            and readback.run_name == expected.run_name
            and readback.data_directory == expected.data_directory
            and readback.params_digest == self._params_digest
            and readback.gate_mode == "immediate"
            and readback.trigger_mode == "immediate"
            and readback.streams == tuple(expected.streams)
        )

    async def start_and_verify_writing(self, deadline_ns: int | None = None) -> bool:
        settings = self._require_settings()
        expected = self._require_prepared()
        if load_host_settings(self.software_root) != settings:
            return False
        deadline = min(
            deadline_ns or self.clock() + int(settings.writing_start_timeout_s * 1e9),
            self.clock() + int(settings.writing_start_timeout_s * 1e9),
        )
        if self._start_uncertain or not await self._verify_before_start(
            settings, expected, deadline
        ):
            return False
        self._start_uncertain = True

        def start(sdk: Any, handle: int) -> None:
            _required(
                sdk.c_sglx_startRun(handle, expected.run_name.encode("utf-8")),
                sdk,
                handle,
                "startRun",
            )

        try:
            await self._run(
                lambda: with_sdk(self.software_root, settings, start),
                self._remaining_timeout(settings, deadline),
            )
            if self.clock() >= deadline:
                return False
            previous: dict[tuple[int, int], int] | None = None
            while self.clock() < deadline:
                progress_io = self._require_progress_io()
                readback, samples = await progress_io.sample_counts(deadline)
                if self.clock() >= deadline:
                    return False
                saved = {
                    (int(stream.family) - 1, stream.index)
                    for stream in expected.streams
                    if stream.saved_channel_indices
                }
                observed = {(family, index): count for family, index, count in samples}
                if (
                    readback.running
                    and readback.saving
                    and readback.run_name == expected.run_name
                    and readback.data_directory == expected.data_directory
                    and saved
                    and saved <= observed.keys()
                    and previous is not None
                    and all(observed[key] > previous.get(key, -1) for key in saved)
                ):
                    self._start_uncertain = False
                    baseline_ns = self.clock()
                    self._monitor_baseline = tuple(
                        wire.StreamProgress(
                            family=stream.family,
                            index=stream.index,
                            sample_count=observed[
                                (int(stream.family) - 1, stream.index)
                            ],
                            last_progress_monotonic_ns=baseline_ns,
                        )
                        for stream in expected.streams
                        if stream.saved_channel_indices
                    )
                    progress_io.record_writing_baseline(samples, baseline_ns)
                    return True
                previous = observed
                await self._sleep(
                    min(
                        settings.observation_interval_s,
                        remaining_seconds(deadline, clock=self.clock),
                    )
                )
            return False
        except (TimeoutError, SpikeGLXIOBusy):
            return False

    async def observe_progress(self, deadline_ns: int) -> wire.SpikeGLXRecordingView:
        """Return one bounded host-clock observation for the active prepared run."""
        return await self._require_progress_io().observe(deadline_ns)

    def monitor_baseline(self) -> tuple[wire.StreamProgress, ...]:
        """Return the immutable per-stream gate-confirmation sample baseline."""
        if not self._monitor_baseline:
            raise RuntimeError("SpikeGLX writing baseline was not confirmed")
        return tuple(
            wire.StreamProgress.FromString(item.SerializeToString())
            for item in self._monitor_baseline
        )

    def monitor_budgets(self) -> tuple[float, float, float]:
        """Return the frozen Setup interval, call bound and loss threshold."""
        return self._require_progress_io().budgets()

    def stop_margin_s(self) -> float:
        """Return the file-owned post-Stopped capture allowance frozen at Setup."""
        return self._require_settings().stop_margin_s

    async def stop_expected_run(self, deadline_ns: int | None = None) -> bool:
        settings = self._require_settings()
        expected = self._require_prepared()
        deadline = deadline_ns or (
            self.clock()
            + int(max(settings.native_call_timeout_s, settings.stop_margin_s) * 1e9)
        )
        try:
            readback = await self._run(
                lambda: read_sdk(self.software_root, settings),
                self._remaining_timeout(settings, deadline),
            )
            if self.clock() >= deadline:
                return False
        except Exception:
            return False
        if not readback.running:
            self._start_uncertain = False
            self._stopped = True
            return not self._start_uncertain
        if (
            readback.run_name != expected.run_name
            or readback.data_directory != expected.data_directory
        ):
            return False
        if self._stopped:
            return False
        self._stopped = True

        def stop(sdk: Any, handle: int) -> None:
            _required(sdk.c_sglx_stopRun(handle), sdk, handle, "stopRun")

        try:
            await self._run(
                lambda: with_sdk(self.software_root, settings, stop),
                self._remaining_timeout(settings, deadline),
            )
            if self.clock() >= deadline:
                return False
            while self.clock() < deadline:
                after = await self._run(
                    lambda: read_sdk(self.software_root, settings),
                    self._remaining_timeout(settings, deadline),
                )
                if self.clock() >= deadline:
                    return False
                if not after.running:
                    self._start_uncertain = False
                    return True
                if (
                    after.run_name != expected.run_name
                    or after.data_directory != expected.data_directory
                ):
                    return False
                await self._sleep(0.05)
        except Exception:
            return False
        return False

    async def _sample_counts(
        self, settings: HostSettings, deadline_ns: int
    ) -> tuple[Readback, tuple[tuple[int, int, int], ...]]:
        """Compatibility entry point for tests and the writing gate."""
        progress_io = self._progress_io
        if progress_io is None or progress_io.settings != settings:
            progress_io = SpikeGLXProgressIO(
                software_root=self.software_root,
                settings=settings,
                expected=self._prepared,
                io_owner=self.io_owner,
                clock=self.clock,
            )
        return await progress_io.sample_counts(deadline_ns)

    def _remaining_timeout(self, settings: HostSettings, deadline_ns: int) -> float:
        remaining_ns = deadline_ns - self.clock()
        if remaining_ns <= 0:
            raise TimeoutError("SpikeGLX operation missed its original deadline")
        return min(settings.native_call_timeout_s, remaining_ns / 1e9)

    def _require_prepared(self) -> wire.SpikeGLXPreparation:
        if self._prepared is None:
            raise RuntimeError("SpikeGLX run identity has not been prepared")
        return self._prepared

    def _require_settings(self) -> HostSettings:
        if self._prepared_settings is None:
            raise RuntimeError("SpikeGLX host settings have not been prepared")
        return self._prepared_settings

    def _require_progress_io(self) -> SpikeGLXProgressIO:
        if self._progress_io is None:
            raise RuntimeError("SpikeGLX run identity has not been prepared")
        return self._progress_io


def create_controller_client(
    *, software_root: Path, controller_generation: str
) -> SpikeGLXControllerClient:
    return SpikeGLXControllerClient(
        software_root, controller_generation=controller_generation
    )
