"""Fence local work and report exact authority/health failures (A02/E08)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from uuid import uuid4

from cephvr.acquisition.coordinator.shutdown import CoordinatorShutdown
from cephvr.acquisition.ports import SupervisorPort
from cephvr.acquisition.state import CoordinatorIdentity, SessionSlot, WorkerRecord
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns


class CoordinatorAuthorityFailure:
    """Own authority-loss fencing, direct supervisor reports and cleanup handoff."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        session_slot: SessionSlot,
        workers: dict[int, WorkerRecord],
        supervisor: SupervisorPort,
        shutdown: CoordinatorShutdown,
        retain_error: Callable[[control.ErrorReport], None],
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.session_slot = session_slot
        self.workers = workers
        self.supervisor = supervisor
        self.shutdown = shutdown
        self.retain_error = retain_error
        self.clock = clock

    async def authority_lost(
        self, role: str, *, deadline_ns: int, observation_failed: bool = False
    ) -> None:
        """Fence the current session and hand its retained work to cleanup."""
        if role not in {"controller", "supervisor"}:
            raise ValueError("authority loss role is not a supported authority")
        session = self.session_slot.current
        work = control.WorkContext()
        if session is not None:
            if session.trial is not None:
                work.CopyFrom(session.trial.work)
            else:
                work.CopyFrom(session.work)
            session.interrupted = True
            self.session_slot.interrupted = True
            if session.trial is not None:
                session.trial.interrupted = True
        failure = control.Failure(
            code=(
                "AUTHORITY_STATUS_UNVERIFIED"
                if observation_failed
                else f"{role.upper()}_PROCESS_LOST"
            ),
            message=(
                f"registered {role} process identity could not be verified; acquisition is stopping"
                if observation_failed
                else f"registered {role} process exited; acquisition is stopping"
            ),
        )
        error = control.ErrorReport(
            error_id=str(uuid4()),
            source=self.identity.process,
            work=work,
            operation=(
                session.operation
                if session is not None
                else control.OperationContext(command_id=str(uuid4()))
            ),
            occurred_monotonic_ns=self.clock(),
            failure=failure,
        )
        self.retain_error(error)
        sys.stderr.write(
            f"CephVR acquisition shutdown: {failure.code}: {failure.message}\n"
        )
        if role == "controller":
            await self._report_supervisor(error, deadline_ns)
        await self.shutdown.cleanup_after_failure(deadline_ns=deadline_ns)

    async def health_failure(
        self,
        source: control.ProcessIdentity,
        work: control.WorkContext,
        failure: control.Failure,
        deadline_ns: int,
    ) -> None:
        """Retain exact worker/source loss and join the serialized cleanup path."""
        session = self.session_slot.current
        if session is not None:
            session.interrupted = True
            self.session_slot.interrupted = True
            if session.trial is not None:
                session.trial.interrupted = True
        operation = (
            session.operation
            if session is not None
            else control.OperationContext(command_id=str(uuid4()))
        )
        for worker in self.workers.values():
            if worker.launch.worker == source:
                matching = [
                    child
                    for child in worker.child_operations.values()
                    if child.work == work
                ]
                if matching:
                    operation = control.OperationContext(
                        command_id=matching[-1].command_id
                    )
                break
        error = control.ErrorReport(
            error_id=str(uuid4()),
            source=source,
            work=work,
            operation=operation,
            occurred_monotonic_ns=self.clock(),
            failure=failure,
        )
        self.retain_error(error)
        sys.stderr.write(
            f"CephVR acquisition shutdown: {failure.code}: {failure.message}\n"
        )
        await self._report_supervisor(error, deadline_ns)
        await self.shutdown.cleanup_after_failure(deadline_ns=deadline_ns)

    async def _report_supervisor(
        self, error: control.ErrorReport, deadline_ns: int
    ) -> None:
        try:
            await self.supervisor.report_error(error, deadline_ns=deadline_ns)
        except Exception:
            # Local cleanup must continue when the direct supervisor path is gone.
            return
