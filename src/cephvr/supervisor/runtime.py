"""Supervisor control service and independent safety state (E04/E06/E08)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.platform.windows.jobs import WindowsLaunchError
from cephvr.shared.clock import describe_host_clock, host_time_ns
from cephvr.shared.commands import CommandLedger
from cephvr.shared.identity import require_uuid4
from cephvr.supervisor.health import HealthMonitor
from cephvr.supervisor.ports import SupervisorOutbound
from cephvr.supervisor.recovery import RecoveryCoordinator
from cephvr.supervisor.registration import RegistrationCoordinator
from cephvr.supervisor.registry import LaunchRegistry, NativeLaunches
from cephvr.supervisor.service import SupervisorService
from cephvr.supervisor.shutdown import ShutdownCoordinator
from cephvr.supervisor.state import (
    HealthState,
    RecoveryState,
    RegistrationState,
    ShutdownState,
    StatusState,
    SupervisorTasks,
)
from cephvr.supervisor.status import StatusPublisher


class SupervisorRuntime:
    def __init__(
        self,
        *,
        identity: types.ProcessIdentity,
        controller: types.ProcessIdentity,
        credentials: dict[tuple[str, str], str],
        native: NativeLaunches,
        outbound: SupervisorOutbound,
        software_root: Path,
        silence_timeout_ns: int = 15_000_000_000,
        emergency_timeout_ns: int = 5_000_000_000,
        application_backstop_ns: int = 90_000_000_000,
        max_message_bytes: int = 16 * 1024 * 1024,
        max_retained_entries: int = 256,
        command_retention_ns: int = 300_000_000_000,
        graceful_exit_ns: int = 5_000_000_000,
        terminate_exit_ns: int = 2_000_000_000,
        heartbeat_interval_ns: int = 5_000_000_000,
        gate_controller_ack: bool = False,
    ) -> None:
        if identity.role != "supervisor" or controller.role != "controller":
            raise ValueError("supervisor/controller process roles are required")
        require_uuid4(identity.generation)
        require_uuid4(controller.generation)
        if (controller.role, controller.generation) not in credentials:
            raise ValueError("controller credential is not registered")
        self.identity = identity
        self.controller = controller
        self.credentials = dict(credentials)
        self.registry = LaunchRegistry(native, silence_timeout_ns)
        self.commands = CommandLedger(
            identity.generation,
            command_retention_ns,
            max_records=1024,
            max_bytes=16 * 1024 * 1024,
            result_reservation_bytes=64 * 1024,
        )
        self.native = native
        self.outbound = outbound
        self.software_root = Path(software_root)
        self.silence_timeout_ns = silence_timeout_ns
        self.emergency_timeout_ns = emergency_timeout_ns
        self.application_backstop_ns = application_backstop_ns
        self.graceful_exit_ns = graceful_exit_ns
        self.terminate_exit_ns = terminate_exit_ns
        self.heartbeat_interval_ns = heartbeat_interval_ns
        self.max_message_bytes = max_message_bytes
        self.clock = describe_host_clock()
        if max_retained_entries <= 0:
            raise ValueError("retention bound must be positive")
        self.max_retained_entries = max_retained_entries
        self._assemble_components(gate_controller_ack)

    def _assemble_components(self, gate_controller_ack: bool) -> None:
        """Wire focused state owners and their narrow cross-component operations."""
        self.registration_state = RegistrationState()
        self.health_state = HealthState()
        self.recovery_state = RecoveryState()
        self.shutdown_state = ShutdownState()
        self.status_state = StatusState()
        self._lock = asyncio.Lock()
        self.tasks = SupervisorTasks(
            lambda name, reason: status.unavailable_component(
                "supervisor", reason, key=f"task:{name}"
            )
        )
        shutdown: ShutdownCoordinator
        health: HealthMonitor
        recovery: RecoveryCoordinator
        status: StatusPublisher
        registration = RegistrationCoordinator(
            state=self.registration_state,
            registry=self.registry,
            controller=self.controller,
            identity=self.identity,
            recovery=self.recovery_state,
            health=self.health_state,
            commands=self.commands,
            lock=self._lock,
            max_retained_entries=self.max_retained_entries,
            max_message_bytes=self.max_message_bytes,
            cleanup_blockers=lambda: recovery.cleanup_blockers(),
            verified_continuation=lambda error: health.verified_continuation(error),
            changed=lambda: status.changed(),
        )
        status = StatusPublisher(
            state=self.status_state,
            registration=self.registration_state,
            health=self.health_state,
            recovery=self.recovery_state,
            identity=self.identity,
            controller=self.controller,
            registry=self.registry,
            native=self.native,
            outbound=self.outbound,
            max_message_bytes=self.max_message_bytes,
            max_retained_entries=self.max_retained_entries,
            begin_safety=lambda reason: shutdown.begin_safety(reason),
        )
        health = HealthMonitor(
            state=self.health_state,
            registration=registration,
            shutdown=self.shutdown_state,
            registry=self.registry,
            controller=self.controller,
            identity=self.identity,
            outbound=self.outbound,
            lock=self._lock,
            silence_timeout_ns=self.silence_timeout_ns,
            heartbeat_interval_ns=self.heartbeat_interval_ns,
            max_retained_entries=self.max_retained_entries,
            begin_safety=lambda reason, triggering_error_id=None: shutdown.begin_safety(
                reason, triggering_error_id
            ),
            shutdown_owned=lambda: shutdown.shutdown_owned(),
            changed=status.changed,
            resend_status=status.resend_unacknowledged,
            reconcile_helpers=lambda deadline_ns: (
                shutdown.worker_shutdown.reconcile_native_helper_exits(deadline_ns)
            ),
            tasks=self.tasks,
            warn=lambda message: status.unavailable_component("supervisor", message),
        )
        recovery = RecoveryCoordinator(
            state=self.recovery_state,
            registration=registration,
            health=self.health_state,
            status=self.status_state,
            identity=self.identity,
            controller=self.controller,
            commands=self.commands,
            outbound=self.outbound,
            lock=self._lock,
            emergency_timeout_ns=self.emergency_timeout_ns,
            max_retained_entries=self.max_retained_entries,
            tasks=self.tasks,
            begin_safety=lambda reason: shutdown.begin_safety(reason),
            changed=status.changed,
        )
        shutdown = ShutdownCoordinator(
            state=self.shutdown_state,
            registration=registration,
            recovery=recovery,
            health=self.health_state,
            identity=self.identity,
            controller=self.controller,
            registry=self.registry,
            native=self.native,
            outbound=self.outbound,
            software_root=self.software_root,
            lock=self._lock,
            max_retained_entries=self.max_retained_entries,
            emergency_timeout_ns=self.emergency_timeout_ns,
            application_backstop_ns=self.application_backstop_ns,
            graceful_exit_ns=self.graceful_exit_ns,
            terminate_exit_ns=self.terminate_exit_ns,
            silence_timeout_ns=self.silence_timeout_ns,
            tasks=self.tasks,
            changed=status.changed,
        )
        self.registry.on_release(self._retire_released_worker)
        self.registration = registration
        self.status = status
        self.health = health
        self.recovery = recovery
        self.shutdown = shutdown
        self.service = SupervisorService(
            identity=self.identity,
            controller=self.controller,
            credentials=self.credentials,
            registry=self.registry,
            registration=self.registration,
            health=self.health,
            recovery=self.recovery,
            shutdown=self.shutdown,
            status=self.status,
            lock=self._lock,
            clock=self.clock,
            max_message_bytes=self.max_message_bytes,
        )
        self._background_tasks: tuple[asyncio.Task[None], asyncio.Task[None]] | None = (
            None
        )
        if not gate_controller_ack:
            self.shutdown_state.controller_ack.set()

    def _retire_released_worker(self, released: wire.LaunchState) -> None:
        """Close the cached worker channel once its exact launch is released."""
        # Concrete outbound only (fakes and the port protocol omit it).
        retire = getattr(self.outbound, "retire_worker_generation", None)
        if retire is not None:
            child = released.plan.child
            self.tasks.spawn(
                "worker channel retirement", retire(child.role, child.generation)
            )

    async def close_outbound(self) -> None:
        """Close every outbound channel; safe to call more than once."""
        close = getattr(self.outbound, "close", None)
        if close is not None:
            await close()

    async def monitor(self, period_s: float = 0.25) -> None:
        await self.health.monitor(period_s)

    async def heartbeat_loop(self) -> None:
        await self.health.heartbeat_loop()

    def acknowledge_controller_registration(self) -> None:
        """Permit controller endpoint admission after launcher retains its exact handle."""
        self.shutdown_state.controller_ack.set()

    def start_background(self) -> None:
        """Own the supervisor's health and outbound heartbeat loops."""
        if self._background_tasks is not None:
            raise RuntimeError("supervisor background tasks already started")
        self._background_tasks = (
            asyncio.create_task(self.health.monitor()),
            asyncio.create_task(self.health.heartbeat_loop()),
        )

    async def wait_until_shutdown(self) -> None:
        """Escalate failed authority tasks while launcher containment remains active."""
        if self._background_tasks is None:
            raise RuntimeError("supervisor background tasks are not running")
        monitor, heartbeat = self._background_tasks
        while not self.shutdown_state.shutdown_complete.is_set():
            for task in (
                monitor,
                heartbeat,
                self.shutdown_state.safety_task,
                self.shutdown_state.shutdown_task,
            ):
                if task is not None and task.done():
                    failure = task.exception()
                    if failure is not None:
                        raise WindowsLaunchError(
                            "supervisor safety/monitor task failed; launcher backstop owns containment"
                        ) from failure
                    if task in (monitor, heartbeat):
                        raise WindowsLaunchError(
                            "supervisor authority loop stopped unexpectedly"
                        )
            deadline = self.shutdown_state.shutdown_deadline_ns
            if deadline is not None and host_time_ns() >= deadline:
                raise WindowsLaunchError(
                    "application backstop reached without verified process absence"
                )
            await asyncio.sleep(0.05)

    def stop_background(self) -> None:
        self.tasks.cancel_all()
        tasks = self._background_tasks
        self._background_tasks = None
        if tasks is not None:
            for task in tasks:
                task.cancel()
