"""Bounded E02 controller snapshots, watches and revision publication."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.projections import ProjectionStore
from cephvr.controller.state import (
    RETAINED_LIMIT,
    ConfigurationState,
    ControlState,
    IncidentState,
    LifecycleState,
    LimitsState,
    MetadataState,
    SupervisorState,
    Watch,
)


class SnapshotPublisher:
    """Construct views from the one live state set and publish revisions."""

    def __init__(
        self,
        *,
        generation: str,
        clock: Callable[[], int],
        configuration: ConfigurationState,
        lifecycle: LifecycleState,
        control: ControlState,
        metadata: MetadataState,
        supervisor: SupervisorState,
        incidents: IncidentState,
        projections: ProjectionStore,
        limits: LimitsState,
        owner_lost: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.generation = generation
        self.clock = clock
        self.configuration_state = configuration
        self.lifecycle = lifecycle
        self.control = control
        self.metadata_state = metadata
        self.supervisor_state = supervisor
        self.incident_state = incidents
        self.projections = projections
        self.limits = limits
        self.owner_lost = owner_lost
        self.owner_loss_observers: list[Callable[[], Awaitable[None]]] = []

    def bind_owner_loss(self, handler: Callable[[], Awaitable[None]]) -> None:
        self.owner_lost = handler

    def observe_owner_loss(self, handler: Callable[[], Awaitable[None]]) -> None:
        self.owner_loss_observers.append(handler)

    def build_snapshot(self, *, include_configuration: bool = True) -> pb.Snapshot:
        view = pb.Snapshot(
            controller_generation=self.generation,
            captured_monotonic_ns=self.clock(),
            state_revision=self.control.revision,
        )
        view.configuration.revision = self.configuration_state.revision
        view.configuration.edit_validation.extend(self.configuration_state.validation)
        for validation in self.configuration_state.validation:
            if validation.completed and validation.valid and validation.issues:
                view.warnings.add(
                    warning_id=f"configuration:{self.configuration_state.revision}:{validation.component}:nonfatal",
                    component=validation.component,
                    message="Configuration has nonfatal preparation warnings",
                    issues=validation.issues,
                )
        view.configuration.locked = self.lifecycle.session.phase in (
            pb.SESSION_PHASE_STARTING,
            pb.SESSION_PHASE_RUNNING,
            pb.SESSION_PHASE_FINALIZING,
            pb.SESSION_PHASE_ENDED,
        )
        if include_configuration:
            view.configuration_values.current.CopyFrom(self.configuration_state.current)
            view.configuration_values.revision = self.configuration_state.revision
        view.session.CopyFrom(self.lifecycle.session)
        view.trial.CopyFrom(self.lifecycle.trial)
        view.tracking_diagnostic.CopyFrom(self.control.tracking_diagnostic)
        if self.control.owner is not None:
            view.control.holder_client_id = self.control.owner[0]
            view.control.control_generation = self.control.owner[2]
        view.operations.extend(self.control.operations.values())
        view.errors.extend(
            (self.control.errors + self.supervisor_state.errors)[-RETAINED_LIMIT:]
        )
        view.warnings.extend(
            (self.control.warnings + self.supervisor_state.warnings)[-RETAINED_LIMIT:]
        )
        if self.lifecycle.startup_blocker:
            view.warnings.add(
                warning_id=self.lifecycle.startup_warning_id,
                component="startup_recovery",
                message=self.lifecycle.startup_blocker,
            )
        view.recoveries.extend(
            (
                self.supervisor_state.recoveries
                + self.supervisor_state.controller_recoveries
            )[-RETAINED_LIMIT:]
        )
        view.metadata.extend(self.metadata_state.results.values())
        view.prompts.extend(item[0] for item in self.incident_state.prompts.values())
        view.prompts.extend(
            item[0] for item in self.incident_state.incident_prompts.values()
        )
        if self.lifecycle.startup_prompt is not None:
            view.prompts.add().CopyFrom(self.lifecycle.startup_prompt)
        if (
            self.lifecycle.attempt is not None
            and self.lifecycle.attempt.incidents is not None
        ):
            view.runtime_incidents.extend(self.lifecycle.attempt.incidents.snapshot())
        self.projections.install_public(view)
        if self.lifecycle.attempt is not None:
            if self.lifecycle.attempt.paired:
                view.spikeglx_recording.CopyFrom(
                    self.lifecycle.attempt.spikeglx_recording
                )
            view.reservation.session.CopyFrom(self.lifecycle.attempt.context)
            view.reservation.session_directory = str(
                self.lifecycle.attempt.reservation.session_directory
            )
            view.reservation.lock_held = self.lifecycle.attempt.reservation.held
            view.reservation.ready_for_outputs = self.lifecycle.session.phase in (
                pb.SESSION_PHASE_READY,
                pb.SESSION_PHASE_STARTING,
                pb.SESSION_PHASE_RUNNING,
                pb.SESSION_PHASE_FINALIZING,
            )
            for name, backend in self.lifecycle.attempt.required.items():
                participant = view.participants.add()
                participant.process.role = name
                participant.process.generation = backend.context.backend_generation
                participant.enabled = True
                participant.required = True
                health = self.supervisor_state.processes.get(name)
                if health is not None:
                    participant.process_running = health.process_running
                    participant.connected = health.connected
                    participant.health = health.health
                    participant.software_version = health.software_version
                    participant.capabilities.extend(health.capabilities)
                    participant.protocol_package = health.protocol_package
                if name in self.lifecycle.attempt.ready:
                    report = self.lifecycle.attempt.ready[name]
                    participant.ready.context.CopyFrom(report.context)
                    participant.ready.configuration_revision = (
                        report.configuration_revision
                    )
                    participant.ready.required_checks_passed = (
                        report.required_checks_passed
                    )
        return view

    async def snapshot(self) -> pb.Snapshot:
        async with self.lifecycle.lock:
            return self.build_snapshot()

    async def open_watch(self, client_id: str, watch_id: str) -> Watch:
        async with self.lifecycle.lock:
            key = (client_id, watch_id)
            if (
                not client_id
                or not watch_id
                or key in self.control.watches
                or len(self.control.watches) >= self.limits.current.max_watchers
            ):
                raise ValueError("watch identity unavailable")
            queue: asyncio.Queue[pb.Snapshot] = asyncio.Queue(maxsize=1)
            watch = Watch(client_id, watch_id, queue, 0)
            self.control.watches[key] = watch
            queue.put_nowait(self.build_snapshot())
            return watch

    async def delivered_watch_view(self, watch: Watch, revision: int) -> None:
        async with self.lifecycle.lock:
            if self.control.watches.get((watch.client_id, watch.watch_id)) is watch:
                watch.installed_revision = revision

    async def close_watch(self, watch: Watch) -> None:
        released = False
        async with self.lifecycle.lock:
            self.control.watches.pop((watch.client_id, watch.watch_id), None)
            if self.control.owner is not None and self.control.owner[:2] == (
                watch.client_id,
                watch.watch_id,
            ):
                self.control.owner = None
                released = True
                if self.lifecycle.session.phase == pb.SESSION_PHASE_CONFIGURATION:
                    self.lifecycle.manual_control_cleanup_pending = True
                self.publish()
        if released:
            for observer in tuple(self.owner_loss_observers):
                await observer()
            if self.owner_lost is not None:
                await self.owner_lost()

    def publish(self) -> None:
        self.control.revision += 1
        for watch in self.control.watches.values():
            if watch.queue.full():
                watch.queue.get_nowait()
            watch.queue.put_nowait(self.build_snapshot())
