"""Bounded in-session SpikeGLX progress monitoring and E06 evidence (E12)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from uuid import uuid4

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.incident.coordination import IncidentCoordinator
from cephvr.controller.ports import SpikeGLXPort
from cephvr.controller.state import Attempt, LifecycleState
from cephvr.shared.clock import host_time_ns
from cephvr.synchronization.v1 import spikeglx_pb2 as wire


class SpikeGLXProgressMonitor:
    """Poll the frozen prepared endpoint and retain per-stream progress evidence."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        spikeglx: SpikeGLXPort,
        incidents: IncidentCoordinator,
        publisher: SnapshotPublisher,
        generation: str,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.lifecycle = lifecycle
        self.spikeglx = spikeglx
        self.incidents = incidents
        self.publisher = publisher
        self.generation = generation
        self.clock = clock

    async def run(self, attempt: Attempt) -> None:
        interval_s, call_timeout_s, no_progress_s = self.spikeglx.monitor_budgets()
        saved = tuple(
            (int(stream.family), stream.index)
            for stream in attempt.prepared.spikeglx.streams
            if stream.saved_channel_indices
        )
        if not saved:
            await self._interrupt(attempt, "paired SpikeGLX has no saved streams")
            return
        try:
            baseline = self.spikeglx.monitor_baseline()
        except Exception as exc:
            await self._interrupt(
                attempt, f"paired SpikeGLX writing baseline is unavailable: {exc}"
            )
            return
        counts = {
            (int(item.family), item.index): item.sample_count for item in baseline
        }
        last_progress = {
            (int(item.family), item.index): item.last_progress_monotonic_ns
            for item in baseline
            if item.HasField("last_progress_monotonic_ns")
        }
        if set(counts) != set(saved) or set(last_progress) != set(saved):
            await self._interrupt(
                attempt, "paired SpikeGLX writing baseline does not cover saved streams"
            )
            return
        incident_id = ""
        incident_started_ns = 0
        incident_episode_id = str(uuid4())
        previous_fault = ""
        while await self._active(attempt):
            try:
                await asyncio.wait_for(attempt.spikeglx_monitor_stop.wait(), interval_s)
                return
            except TimeoutError:
                pass
            if not await self._active(attempt):
                return
            deadline = self.clock() + int(call_timeout_s * 1e9)
            observation = await self.spikeglx.observe_progress(deadline)
            completed_ns = self.clock()
            if (
                completed_ns >= deadline
                or not observation.HasField("observed_monotonic_ns")
                or observation.observed_monotonic_ns > deadline
            ):
                observation = wire.SpikeGLXRecordingView(
                    phase=wire.SPIKEGLX_RECORDING_PHASE_UNKNOWN,
                    failure_code="DEADLINE",
                )
            if not await self._active(attempt):
                return
            view = wire.SpikeGLXRecordingView.FromString(
                observation.SerializeToString()
            )
            now = completed_ns
            fault = self._fault(view, saved, counts, last_progress, now, no_progress_s)
            if fault and fault != previous_fault:
                if not incident_id:
                    incident_started_ns = now
                error = pb.ErrorReport(
                    error_id=str(uuid4()),
                    source=pb.ProcessIdentity(
                        role="controller", generation=self.generation
                    ),
                    work=pb.WorkContext(session=attempt.context),
                    operation=pb.OperationContext(command_id=str(uuid4())),
                    occurred_monotonic_ns=now,
                    device="SpikeGLX",
                    incident_episode_id=incident_episode_id,
                    failure=pb.Failure(code=fault, message=self._message(fault)),
                )
                error.isolation.affected_resource_ids.append("spikeglx_recording")
                error.isolation.leases_released_or_quarantined = True
                error.isolation.bounded_uncertainty = True
                error.isolation.verified_monotonic_ns = now
                observed_incident = await self.incidents.observe_runtime_error(error)
                incident_id = incident_id or observed_incident or ""
                previous_fault = fault
            elif (
                incident_id
                and not fault
                and self._recovered(view, saved, last_progress, incident_started_ns)
            ):
                if await self.incidents.resolve_recovered_incident(
                    attempt, incident_id, now
                ):
                    incident_id = ""
                    incident_started_ns = 0
                    incident_episode_id = str(uuid4())
                    view.failure_code = ""
                    previous_fault = ""
            if fault:
                view.failure_code = fault
            self._retain_history(view, saved, counts, last_progress)
            async with self.lifecycle.lock:
                if self.lifecycle.attempt is not attempt or attempt.interrupted:
                    return
                attempt.spikeglx_recording.CopyFrom(view)
                self.publisher.publish()

    async def _active(self, attempt: Attempt) -> bool:
        async with self.lifecycle.lock:
            return (
                self.lifecycle.attempt is attempt
                and not attempt.interrupted
                and not attempt.spikeglx_monitor_stop.is_set()
                and self.lifecycle.session.phase
                in (pb.SESSION_PHASE_STARTING, pb.SESSION_PHASE_RUNNING)
            )

    async def _interrupt(self, attempt: Attempt, reason: str) -> None:
        await self.incidents.interrupt(attempt, reason)

    @staticmethod
    def _fault(
        view: wire.SpikeGLXRecordingView,
        saved: tuple[tuple[int, int], ...],
        counts: dict[tuple[int, int], int],
        last_progress: dict[tuple[int, int], int],
        now: int,
        no_progress_s: float,
    ) -> str:
        if view.HasField("running") and not view.running:
            return "NOT_RUNNING"
        if view.HasField("saving") and not view.saving:
            return "NOT_SAVING"
        if view.HasField("run_name_matches") and not view.run_name_matches:
            return "RUN_IDENTITY_CHANGED"
        observed = {
            (int(item.family), item.index): item.sample_count for item in view.progress
        }
        for key in saved:
            count = observed.get(key)
            if count is None:
                continue
            previous = counts.get(key)
            if previous is not None and count < previous:
                counts[key] = count
                return "SAMPLE_COUNTER_RESET"
            if previous is None:
                counts[key] = count
            elif count > previous:
                counts[key] = count
                last_progress[key] = now
        timeout_ns = int(no_progress_s * 1e9)
        if any(now - last_progress[key] >= timeout_ns for key in saved):
            return "NO_PROGRESS"
        return ""

    @staticmethod
    def _recovered(
        view: wire.SpikeGLXRecordingView,
        saved: tuple[tuple[int, int], ...],
        last_progress: dict[tuple[int, int], int],
        incident_started_ns: int,
    ) -> bool:
        return (
            view.phase == wire.SPIKEGLX_RECORDING_PHASE_WRITING
            and view.HasField("running")
            and view.running
            and view.HasField("saving")
            and view.saving
            and view.HasField("run_name_matches")
            and view.run_name_matches
            and all(last_progress[key] > incident_started_ns for key in saved)
        )

    @staticmethod
    def _retain_history(
        view: wire.SpikeGLXRecordingView,
        saved: tuple[tuple[int, int], ...],
        counts: dict[tuple[int, int], int],
        last_progress: dict[tuple[int, int], int],
    ) -> None:
        """Publish retained historical values without claiming a fresh poll."""
        observed = {(int(item.family), item.index) for item in view.progress}
        for family, index in saved:
            if (family, index) in observed:
                item = next(
                    item
                    for item in view.progress
                    if int(item.family) == family and item.index == index
                )
                if (family, index) in last_progress:
                    item.last_progress_monotonic_ns = last_progress[(family, index)]
                continue
            if (family, index) not in counts or (family, index) not in last_progress:
                continue
            view.progress.add(
                family=family,
                index=index,
                sample_count=counts[(family, index)],
                last_progress_monotonic_ns=last_progress[(family, index)],
            )

    @staticmethod
    def _message(code: str) -> str:
        return {
            "NO_PROGRESS": "A saved SpikeGLX stream stopped advancing.",
            "NOT_RUNNING": "SpikeGLX confirmed the prepared run is no longer running.",
            "NOT_SAVING": "SpikeGLX confirmed the prepared run is no longer saving.",
            "RUN_IDENTITY_CHANGED": "SpikeGLX reports a different run or data directory.",
            "SAMPLE_COUNTER_RESET": "A saved SpikeGLX sample counter decreased.",
            "REMOTE_STATE_UNKNOWN": "SpikeGLX progress could not be confirmed.",
            "REMOTE_IDENTITY": "SpikeGLX progress did not match the prepared run.",
        }.get(code, "SpikeGLX progress evidence is unavailable.")
