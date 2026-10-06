"""Drive acquisition heartbeat and serial watchdog keepalive obligations (E08/A11)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from cephvr.acquisition.microcontroller.channel import ChannelDeadline
from cephvr.acquisition.ports import SerialOwnerPort, SupervisorPort
from cephvr.acquisition.state import (
    CoordinatorIdentity,
    PulseRecord,
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
    """Send registered-process health and keep the configured MCU watchdog alive."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        workers: dict[int, WorkerRecord],
        commands: CommandLedger,
        session_slot: SessionSlot,
        pulse: PulseRecord,
        supervisor: SupervisorPort,
        serial: SerialOwnerPort,
        heartbeat_interval_ns: int,
        health_silence_ns: int,
        recovery_ns: int,
        serial_keepalive_interval_ns: int,
        serial_communication_timeout_ns: int,
        serial_ack_timeout_ns: int,
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
        if (
            serial_keepalive_interval_ns <= 0
            or serial_communication_timeout_ns <= serial_keepalive_interval_ns
            or serial_ack_timeout_ns <= 0
        ):
            raise ValueError("serial watchdog timing policies are inconsistent")
        self.identity = identity
        self.workers = workers
        self.commands = commands
        self.session_slot = session_slot
        self.pulse = pulse
        self.supervisor = supervisor
        self.serial = serial
        self.heartbeat_interval_ns = heartbeat_interval_ns
        self.health_silence_ns = health_silence_ns
        self.recovery_ns = recovery_ns
        self.serial_keepalive_interval_ns = serial_keepalive_interval_ns
        self.serial_communication_timeout_ns = serial_communication_timeout_ns
        self.serial_ack_timeout_ns = serial_ack_timeout_ns
        self.catalogue_lock = catalogue_lock
        self.failure_handler = failure_handler
        self.clock = clock
        self._reported_worker_errors: dict[str, bytes] = {}
        self._silent_generations: set[str] = set()

    async def run(self, shutdown: asyncio.Event) -> None:
        """Run three bounded duties independently so serial work cannot stall health."""
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(self._heartbeat_loop(shutdown))
            tasks.create_task(self._keepalive_loop(shutdown))
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

    async def _keepalive_loop(self, shutdown: asyncio.Event) -> None:
        due_ns: int | None = None
        connection_id: str | None = None
        last_valid_ns: int | None = None
        last_observation_ns: int | None = None
        while not shutdown.is_set():
            observation = self.pulse.observation
            if (
                observation is None
                or not observation.connection_id
                or (
                    observation.state.HasField("configuration_valid")
                    and not observation.state.configuration_valid
                    and observation.state.HasField("watchdog_ms")
                    and observation.state.watchdog_ms == 0
                    and all(
                        observation.state.HasField(role)
                        and getattr(observation.state, role).HasField("running")
                        and not getattr(observation.state, role).running
                        for role in ("behavioral", "tracking")
                    )
                )
            ):
                # A connection-only probe leaves the firmware watchdog unarmed.
                due_ns = None
                connection_id = None
                last_valid_ns = None
                last_observation_ns = None
                await _wait(
                    shutdown, min(self.serial_keepalive_interval_ns, 100_000_000)
                )
                continue
            now = self.clock()
            if connection_id != observation.connection_id:
                connection_id = observation.connection_id
                observed_ns = (
                    observation.observed_monotonic_ns
                    if observation.HasField("observed_monotonic_ns")
                    else now
                )
                last_observation_ns = observed_ns
                last_valid_ns = observed_ns
                due_ns = observed_ns + self.serial_keepalive_interval_ns
            elif (
                observation.HasField("observed_monotonic_ns")
                and observation.observed_monotonic_ns > (last_observation_ns or 0)
                and observation.state.HasField("configuration_valid")
                and observation.state.configuration_valid
                and observation.state.HasField("watchdog_stopped")
                and not observation.state.watchdog_stopped
                and observation.state.HasField("watchdog_ms")
                and observation.state.watchdog_ms > 0
            ):
                last_observation_ns = observation.observed_monotonic_ns
                last_valid_ns = observation.observed_monotonic_ns
                due_ns = (
                    observation.observed_monotonic_ns
                    + self.serial_keepalive_interval_ns
                )
            if due_ns is None:
                last_valid_ns = now
                due_ns = now + self.serial_keepalive_interval_ns
            if now < due_ns:
                await _wait(shutdown, due_ns - now)
                continue
            watchdog_ms = (
                observation.state.watchdog_ms
                if observation.state.HasField("watchdog_ms")
                else 0
            )
            watchdog_deadline = (
                (last_valid_ns or now)
                + watchdog_ms * 1_000_000
                - self.serial_ack_timeout_ns
            )
            if watchdog_ms <= 0 or now >= watchdog_deadline:
                await self._fail(
                    self.identity.process,
                    _current_work(self.session_slot),
                    control.Failure(
                        code="MICROCONTROLLER_KEEPALIVE_WINDOW_EXHAUSTED",
                        message="no bounded keepalive window remains before the configured watchdog expires",
                    ),
                )
                return
            boundary = _next_pulse_boundary(self.session_slot, now)
            if boundary is not None and now + self.serial_ack_timeout_ns >= boundary:
                due_ns = boundary + self.serial_ack_timeout_ns
                continue
            deadline = min(
                now + self.serial_communication_timeout_ns,
                watchdog_deadline,
            )
            try:
                state = await self.serial.keepalive(deadline_ns=deadline)
            except ChannelDeadline:
                # The owner deferred routine traffic to protect a reserved ON/OFF.
                retry_at = (
                    boundary + self.serial_ack_timeout_ns
                    if boundary is not None
                    else now + self.serial_ack_timeout_ns
                )
                due_ns = min(retry_at, watchdog_deadline)
                continue
            except Exception as exc:
                await self._fail(
                    self.identity.process,
                    _current_work(self.session_slot),
                    control.Failure(
                        code="MICROCONTROLLER_KEEPALIVE_FAILED",
                        message=f"serial watchdog keepalive failed: {exc}"[:2048],
                    ),
                )
                return
            if not state.HasField("watchdog_stopped") or state.watchdog_stopped:
                await self._fail(
                    self.identity.process,
                    _current_work(self.session_slot),
                    control.Failure(
                        code="MICROCONTROLLER_WATCHDOG_STOPPED",
                        message="MCU keepalive did not prove a running watchdog state",
                    ),
                )
                return
            observation.state.CopyFrom(state)
            last_valid_ns = self.clock()
            due_ns = last_valid_ns + self.serial_keepalive_interval_ns

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


def _next_pulse_boundary(slot: SessionSlot, now_ns: int) -> int | None:
    session = slot.current
    trial = session.trial if session is not None else None
    if trial is None:
        return None
    values = [
        value
        for value in (trial.start_monotonic_ns, trial.end_monotonic_ns)
        if value is not None and value > now_ns
    ]
    return min(values) if values else None


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
