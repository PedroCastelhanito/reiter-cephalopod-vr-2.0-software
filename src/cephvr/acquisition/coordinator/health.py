"""Drive acquisition heartbeat and worker progress obligations (E08)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from cephvr.acquisition.ports import SupervisorPort
from cephvr.acquisition.state import (
    CoordinatorIdentity,
    SessionRecord,
    SessionSlot,
    TrialRecord,
    WorkerRecord,
)
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger

FailureHandler = Callable[
    [control.ProcessIdentity, control.WorkContext, control.Failure, int],
    Awaitable[None],
]


class AcquisitionHealth:
    """Send registered-process health and monitor camera-worker progress."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        workers: dict[int, WorkerRecord],
        commands: CommandLedger,
        session_slot: SessionSlot,
        supervisor: SupervisorPort,
        heartbeat_interval_ns: int,
        health_silence_ns: int,
        recovery_ns: int,
        catalogue_lock: asyncio.Lock,
        failure_handler: FailureHandler,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        if (
            heartbeat_interval_ns <= 0
            or health_silence_ns <= heartbeat_interval_ns
            or recovery_ns <= 0
        ):
            raise ValueError("acquisition heartbeat cadence exceeds its silence bound")
        self.identity = identity
        self.workers = workers
        self.commands = commands
        self.session_slot = session_slot
        self.supervisor = supervisor
        self.heartbeat_interval_ns = heartbeat_interval_ns
        self.health_silence_ns = health_silence_ns
        self.recovery_ns = recovery_ns
        self.catalogue_lock = catalogue_lock
        self.failure_handler = failure_handler
        self.clock = clock
        self._reported_worker_errors: dict[str, bytes] = {}
        self._silent_generations: set[str] = set()

    async def run(self, shutdown: asyncio.Event) -> None:
        """Run process heartbeat and worker-silence monitoring independently."""
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(self._heartbeat_loop(shutdown))
            tasks.create_task(self._worker_silence_loop(shutdown))

    async def _heartbeat_loop(self, shutdown: asyncio.Event) -> None:
        next_due = self.clock()
        while not shutdown.is_set():
            delay = max(0, next_due - self.clock()) / 1_000_000_000
            if delay:
                try:
                    await asyncio.wait_for(shutdown.wait(), delay)
                    return
                except TimeoutError:
                    pass
            session = self.session_slot.current
            now = self.clock()
            report = control.HeartbeatReport(
                source=self.identity.process,
                sent_monotonic_ns=now,
                health_summary="acquisition coordinator and registered worker monitor active",
            )
            work = control.WorkContext()
            if session is not None:
                if session.trial is not None:
                    work.CopyFrom(session.trial.work)
                    report.trial_phase = _trial_phase(session.trial)
                else:
                    work.CopyFrom(session.work)
                    report.session_phase = _session_phase(session)
            else:
                report.session_phase = control.SESSION_PHASE_CONFIGURATION
            if work.WhichOneof("work") is not None:
                report.work.CopyFrom(work)
            live_generations = {
                f"{worker.launch.worker.role}:{worker.launch.worker.generation}"
                for worker in self.workers.values()
            }
            for retired in set(self._reported_worker_errors) - live_generations:
                self._reported_worker_errors.pop(retired, None)
            self.commands.prune(now)
            for worker in tuple(self.workers.values()):
                worker.prune_child_operations()
                heartbeat = worker.heartbeat
                report.workers.add(
                    worker=worker.launch.worker.role,
                    progress_required=True,
                    **(
                        {"last_progress_monotonic_ns": heartbeat.sent_monotonic_ns}
                        if heartbeat is not None
                        else {}
                    ),
                )
                if (
                    heartbeat is None
                    or now - heartbeat.sent_monotonic_ns > self.health_silence_ns
                ):
                    continue
                for item in heartbeat.continuing_functions:
                    report.continuing_functions.add().CopyFrom(item)
                if heartbeat.HasField("active_error"):
                    error = heartbeat.active_error
                    payload = error.SerializeToString(deterministic=True)
                    generation = (
                        f"{worker.launch.worker.role}:{worker.launch.worker.generation}"
                    )
                    if self._reported_worker_errors.get(generation) != payload:
                        try:
                            receipt = await self.supervisor.report_error(
                                error,
                                deadline_ns=now + self.heartbeat_interval_ns,
                            )
                            if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                                raise RuntimeError(
                                    "supervisor rejected retained worker ErrorReport"
                                )
                        except Exception as exc:
                            await self._fail(
                                self.identity.supervisor,
                                work,
                                control.Failure(
                                    code="WORKER_ERROR_FORWARD_FAILED",
                                    message=(
                                        f"worker ErrorReport was not accepted: {exc}"
                                    )[:2048],
                                ),
                            )
                            return
                        self._reported_worker_errors[generation] = payload
            try:
                async with self.catalogue_lock:
                    selected = report
                    deadline = now + self.heartbeat_interval_ns
                    if (
                        session is not None
                        and session.pending_cleanup_heartbeat is not None
                    ):
                        if (
                            session.setup_deadline_ns is None
                            or now >= session.setup_deadline_ns
                        ):
                            raise TimeoutError(
                                "retained cleanup catalogue receipt expired"
                            )
                        selected = control.HeartbeatReport.FromString(
                            session.pending_cleanup_heartbeat.SerializeToString(
                                deterministic=True
                            )
                        )
                        deadline = session.setup_deadline_ns
                    elif session is not None and session.cleanup_catalogue_initialized:
                        report.cleanup_resources_revision = (
                            session.cleanup_resources_revision
                        )
                        report.cleanup_resources.extend(session.cleanup_resources)
                    receipt = await self.supervisor.report_heartbeat(
                        selected, deadline_ns=deadline
                    )
                    if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                        raise RuntimeError(
                            f"supervisor rejected acquisition heartbeat: "
                            f"{receipt.failure.code}: {receipt.failure.message}"
                        )
                    if (
                        session is not None
                        and selected is not report
                        and self.session_slot.current is session
                    ):
                        session.cleanup_catalogue_initialized = True
                        session.pending_cleanup_heartbeat = None
            except Exception as exc:
                await self._fail(
                    self.identity.supervisor,
                    work,
                    control.Failure(
                        code="SUPERVISOR_HEARTBEAT_FAILED",
                        message=f"acquisition heartbeat was not accepted: {exc}"[:2048],
                    ),
                )
                return
            next_due = now + self.heartbeat_interval_ns

    async def _worker_silence_loop(self, shutdown: asyncio.Event) -> None:
        interval = min(self.heartbeat_interval_ns, 1_000_000_000)
        while not shutdown.is_set():
            await _wait(shutdown, interval)
            now = self.clock()
            for worker in tuple(self.workers.values()):
                generation = worker.launch.worker.generation
                if generation in self._silent_generations:
                    continue
                last = (
                    worker.heartbeat.sent_monotonic_ns
                    if worker.heartbeat is not None
                    else worker.launch.planned_ns
                )
                if now - last <= self.health_silence_ns:
                    continue
                self._silent_generations.add(generation)
                await self._fail(
                    worker.launch.worker,
                    _current_work(self.session_slot),
                    control.Failure(
                        code="WORKER_HEARTBEAT_SILENCE",
                        message=f"registered {worker.launch.worker.role} stopped reporting before its silence bound",
                    ),
                )
                return

    async def _fail(
        self,
        source: control.ProcessIdentity,
        work: control.WorkContext,
        failure: control.Failure,
    ) -> None:
        deadline = self.clock() + self.recovery_ns
        await self.failure_handler(source, work, failure, deadline)


async def _wait(shutdown: asyncio.Event, delay_ns: int) -> None:
    try:
        await asyncio.wait_for(shutdown.wait(), max(0, delay_ns) / 1_000_000_000)
    except TimeoutError:
        pass


def _current_work(slot: SessionSlot) -> control.WorkContext:
    session = slot.current
    if session is None:
        return control.WorkContext()
    work = control.WorkContext()
    if session.trial is not None:
        work.CopyFrom(session.trial.work)
    else:
        work.CopyFrom(session.work)
    return work


def _session_phase(session: SessionRecord) -> control.SessionPhase:
    if session.interrupted or session.setup_cancelled:
        return control.SESSION_PHASE_FINALIZING
    if session.ready_report is not None:
        return control.SESSION_PHASE_READY
    return control.SESSION_PHASE_SETTING_UP


def _trial_phase(trial: TrialRecord) -> control.TrialPhase:
    if trial.finished_report is not None:
        return control.TRIAL_PHASE_ENDED
    if trial.stopped_report is not None:
        return control.TRIAL_PHASE_FINALIZING
    if trial.started_report is not None:
        return control.TRIAL_PHASE_RUNNING
    if trial.ready_report is not None:
        return control.TRIAL_PHASE_READY
    return control.TRIAL_PHASE_PREPARING
