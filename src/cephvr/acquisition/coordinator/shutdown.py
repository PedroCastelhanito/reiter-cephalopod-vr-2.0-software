"""Acquisition session stop/cancel and terminal cleanup orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Protocol
from uuid import uuid4

from cephvr.acquisition.state import CoordinatorIdentity, SessionRecord, SessionSlot
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns


class SessionCancelPort(Protocol):
    async def cancel(self, session: SessionRecord, *, deadline_ns: int) -> None: ...


class TrialStopPort(Protocol):
    async def stop(
        self,
        request: wire.StopTrialRequest,
        *,
        deadline_ns: int,
        aborted: bool = False,
        internal: bool = False,
    ) -> control.CommandAdmission: ...


class CleanupPort(Protocol):
    async def execute(
        self, request: wire.BackendCommand, *, deadline_ns: int
    ) -> control.CommandAdmission: ...


class CoordinatorShutdown:
    """Own cleanup sequencing without a reference to the coordinator runtime."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        session_slot: SessionSlot,
        session_cancel: SessionCancelPort,
        trial_stop: TrialStopPort,
        cleanup: CleanupPort,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.session_slot = session_slot
        self.session_cancel = session_cancel
        self.trial_stop = trial_stop
        self.cleanup_owner = cleanup
        self.clock = clock
        self.shutdown_requested = asyncio.Event()
        self.closing = False

    async def cleanup_session(
        self, request: wire.BackendCommand, *, deadline_ns: int
    ) -> control.CommandAdmission:
        session = self.session_slot.current
        if session is not None and request.work == session.work:
            if session.trial is not None and session.trial.stop is None:
                stop = wire.StopTrialRequest(
                    command=wire.BackendCommand(
                        command_id=str(uuid4()),
                        issuer=self.identity.process,
                        target=self.identity.backend,
                        work=session.trial.work,
                    ),
                    issued_monotonic_ns=self.clock(),
                    reason=control.Failure(code="CLEANUP", message="owner cleanup"),
                )
                await self.trial_stop.stop(
                    stop, deadline_ns=deadline_ns, aborted=True, internal=True
                )
            elif not session.ready_report:
                await self.session_cancel.cancel(session, deadline_ns=deadline_ns)
        return await self.cleanup_owner.execute(request, deadline_ns=deadline_ns)

    async def request_shutdown(
        self, request: wire.BackendCommand, *, deadline_ns: int
    ) -> control.CommandAdmission:
        self.closing = True
        session = self.session_slot.current
        if (
            session is not None
            and request.work == session.work
            and session.cleanup_complete
            and session.cleanup_delivery_complete
        ):
            # Both recipients already hold the exact session closure. Shutdown
            # retires this process; it cannot rebind that proof to a new fence.
            self.shutdown_requested.set()
            return control.CommandAdmission(
                result=control.COMMAND_RESULT_ACCEPTED,
                command_id=request.command_id,
            )
        receipt = await self.cleanup_session(request, deadline_ns=deadline_ns)
        if receipt.result == control.COMMAND_RESULT_ACCEPTED:
            self.shutdown_requested.set()
        return receipt

    async def cleanup_after_failure(
        self, *, deadline_ns: int
    ) -> control.CommandAdmission:
        """Use the retained session work for authority-loss cleanup."""
        cleanup_work = control.WorkContext()
        session = self.session_slot.current
        if session is not None:
            cleanup_work.CopyFrom(session.work)
        request = wire.BackendCommand(
            command_id=str(uuid4()),
            issuer=self.identity.process,
            target=self.identity.backend,
            work=cleanup_work,
        )
        try:
            return await self.cleanup_session(request, deadline_ns=deadline_ns)
        finally:
            self.shutdown_requested.set()
