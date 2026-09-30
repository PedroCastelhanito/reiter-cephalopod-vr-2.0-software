"""Retained supervisor cleanup-catalogue publication for Setup (E06/E08)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from cephvr.acquisition.ports import SupervisorPort
from cephvr.acquisition.state import CoordinatorIdentity, SessionRecord, SessionSlot
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger


class SessionCatalogue:
    """Retain exact heartbeat payload/revision before sending or retrying it."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        session_slot: SessionSlot,
        supervisor: SupervisorPort,
        commands: CommandLedger,
        lock: asyncio.Lock | None = None,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.session_slot = session_slot
        self.supervisor = supervisor
        self.commands = commands
        self.catalogue_lock = lock or asyncio.Lock()
        self.clock = clock

    async def publish_catalogue(
        self, session: SessionRecord, *, deadline_ns: int
    ) -> None:
        if not session.cleanup_catalogue_initialized:
            if session.pending_cleanup_heartbeat is None:
                session.pending_cleanup_heartbeat = control.HeartbeatReport(
                    source=self.identity.process,
                    work=session.work,
                    sent_monotonic_ns=self.clock(),
                    session_phase=control.SESSION_PHASE_SETTING_UP,
                    cleanup_resources_revision=session.cleanup_resources_revision,
                )
                session.pending_cleanup_heartbeat.cleanup_resources.extend(
                    session.cleanup_resources
                )
        await self._send_pending_catalogue(session, deadline_ns=deadline_ns)

    async def declare_resource(
        self,
        session: SessionRecord,
        owner: control.ProcessIdentity,
        resource: str,
        *,
        deadline_ns: int,
    ) -> None:
        if not resource or self.clock() >= deadline_ns:
            raise TimeoutError("cleanup resource declaration missed Setup deadline")
        async with self.catalogue_lock:
            if self.session_slot.current is not session or session.setup_cancelled:
                raise RuntimeError("Setup was cancelled before resource declaration")
            if not session.cleanup_catalogue_initialized:
                raise RuntimeError("accepted empty cleanup catalogue is required first")
            if session.pending_cleanup_heartbeat is not None:
                await self._send_pending_catalogue(session, deadline_ns=deadline_ns)
            key = (owner.role, owner.generation, resource)
            if any(
                (item.owner.role, item.owner.generation, item.resource) == key
                for item in session.cleanup_resources
            ):
                return
            next_revision = session.cleanup_resources_revision + 1
            candidate = [
                control.ResourceObligation.FromString(
                    item.SerializeToString(deterministic=True)
                )
                for item in session.cleanup_resources
            ]
            candidate.append(control.ResourceObligation(owner=owner, resource=resource))
            request = control.HeartbeatReport(
                source=self.identity.process,
                work=session.work,
                sent_monotonic_ns=self.clock(),
                session_phase=control.SESSION_PHASE_SETTING_UP,
                cleanup_resources_revision=next_revision,
            )
            request.cleanup_resources.extend(candidate)
            session.cleanup_resources = candidate
            session.cleanup_resources_revision = next_revision
            session.pending_cleanup_heartbeat = request
            session.reserve_cleanup_evidence(self.commands)
            await self._send_pending_catalogue(session, deadline_ns=deadline_ns)

    async def _send_pending_catalogue(
        self, session: SessionRecord, *, deadline_ns: int
    ) -> None:
        request = session.pending_cleanup_heartbeat
        if request is None:
            return
        receipt = await self.supervisor.report_heartbeat(
            request, deadline_ns=deadline_ns
        )
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError("supervisor rejected cleanup resource declaration")
        session.cleanup_catalogue_initialized = True
        session.pending_cleanup_heartbeat = None
