"""Bounded supervisor status snapshots and delivery retry (E08)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from uuid import uuid4

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.clock import host_time_ns
from cephvr.supervisor.ports import SupervisorOutbound
from cephvr.supervisor.registry import LaunchError, LaunchRegistry, NativeLaunches
from cephvr.supervisor.state import (
    HealthState,
    RecoveryState,
    RegistrationState,
    StatusState,
)


class StatusPublisher:
    def __init__(
        self,
        *,
        state: StatusState,
        registration: RegistrationState,
        health: HealthState,
        recovery: RecoveryState,
        identity: types.ProcessIdentity,
        controller: types.ProcessIdentity,
        registry: LaunchRegistry,
        native: NativeLaunches,
        outbound: SupervisorOutbound,
        max_message_bytes: int,
        max_retained_entries: int,
        begin_safety: Callable[[types.Failure], None],
    ) -> None:
        self.state = state
        self.registration = registration
        self.health = health
        self.recovery = recovery
        self.identity = identity
        self.controller = controller
        self.registry = registry
        self.native = native
        self.outbound = outbound
        self.max_message_bytes = max_message_bytes
        self.max_retained_entries = max_retained_entries
        self.begin_safety = begin_safety
        self.keyed_warnings: dict[str, str] = {}

    def changed(self) -> None:
        self.state.revision += 1
        self.state.pending_status = None
        if self.state.status_task is None or self.state.status_task.done():
            self.state.status_task = asyncio.create_task(self.send_status())

    def resend_unacknowledged(self) -> None:
        """Heartbeat-tick retry: resend the current view if the controller lacks it."""
        if self.state.revision > self.state.acknowledged_revision and (
            self.state.status_task is None or self.state.status_task.done()
        ):
            self.state.status_task = asyncio.create_task(self.send_status())

    def unavailable_component(
        self, role: str, reason: str, *, key: str | None = None
    ) -> None:
        """Add a warning; a keyed repeat replaces its earlier one instead of growing."""
        if key is not None and key in self.keyed_warnings:
            warning_id = self.keyed_warnings[key]
            if warning_id in self.state.warnings:
                self.state.warnings[warning_id].message = reason
                self.changed()
                return
        if len(self.state.warnings) >= self.max_retained_entries:
            self.begin_safety(
                types.Failure(
                    code="WARNING_CAPACITY",
                    message="required warning accounting exhausted",
                )
            )
            return
        warning_id = str(uuid4())
        if key is not None:
            self.keyed_warnings[key] = warning_id
        self.state.warnings[warning_id] = types.Warning(
            warning_id=warning_id,
            component=role,
            message=reason,
        )
        self.changed()

    def keyed_warning(self, key: str, reason: str | None) -> None:
        """Set a per-subject supervisor warning, or clear it when ``reason`` is None."""
        if reason is not None:
            self.unavailable_component("supervisor", reason, key=key)
            return
        warning_id = self.keyed_warnings.pop(key, None)
        if warning_id is not None and warning_id in self.state.warnings:
            del self.state.warnings[warning_id]
            self.changed()

    async def send_status(self) -> None:
        while True:
            revision = self.state.revision
            report = self.state.pending_status
            if report is None or report.status_revision != revision:
                report = wire.SupervisorStatusReport(
                    supervisor=self.identity,
                    controller_generation=self.controller.generation,
                    status_revision=revision,
                    observed_monotonic_ns=host_time_ns(),
                    errors=list(self.health.errors.values()),
                    warnings=list(self.state.warnings.values()),
                    recoveries=list(self.recovery.recoveries.values()),
                    operations=list(self.recovery.operations.values()),
                )
                if self.registration.context:
                    report.work.CopyFrom(self.registration.context.work)
                try:
                    states = self.registry.states()
                    for state in states:
                        status = report.processes.add(
                            process=state.plan.child,
                            launch_owner=state.plan.owner,
                            # A released launch's handle is closed; never probe
                            # its possibly reused raw PID.
                            process_running=state.HasField("pid")
                            and state.phase != wire.LAUNCH_PHASE_RELEASED
                            and self.native.process_running(
                                state.pid, state.creation_time_100ns
                            ),
                            connected=state.phase == wire.LAUNCH_PHASE_OPERATIONAL,
                            health=wire.LaunchPhase.Name(state.phase),
                        )
                        key = (state.plan.child.role, state.plan.child.generation)
                        if key in self.health.last_heartbeat:
                            status.last_evidence_monotonic_ns = (
                                self.health.last_heartbeat[key]
                            )
                        if key in self.health.heartbeat_reports:
                            status.last_heartbeat.CopyFrom(
                                self.health.heartbeat_reports[key]
                            )
                except (LaunchError, RuntimeError) as exc:
                    self.begin_safety(
                        types.Failure(
                            code="PROCESS_INSPECTION_FAILED", message=str(exc)
                        )
                    )
                    return
                if report.ByteSize() > self.max_message_bytes - 4096:
                    self.begin_safety(
                        types.Failure(
                            code="STATUS_OVERFLOW",
                            message="supervisor status exceeds RPC limit",
                        )
                    )
                    return
                self.state.pending_status = report
            try:
                await self.outbound.report_status(report)
            except Exception:
                # Retain the newest complete view; a newer revision made during
                # this send is sent now, otherwise the heartbeat tick retries.
                if revision == self.state.revision:
                    return
                continue
            self.state.acknowledged_revision = max(
                self.state.acknowledged_revision, revision
            )
            if self.state.pending_status is report:
                self.state.pending_status = None
            if revision == self.state.revision:
                return
