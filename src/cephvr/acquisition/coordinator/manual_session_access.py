"""Access gates for manual commands after a retained session completes."""

from __future__ import annotations

from cephvr.acquisition.coordinator.workers import WorkerRegistry
from cephvr.acquisition.state import CoordinatorIdentity, SessionSlot
from cephvr.control.v1 import services_pb2 as wire


def manual_configuration_available(session_slot: SessionSlot) -> bool:
    """Allow Configuration with no session or a fully cleaned retained session."""
    session = session_slot.current
    return session is None or session.cleanup_complete


async def retire_completed_manual_session(
    session_slot: SessionSlot,
    workers: WorkerRegistry,
    *,
    deadline_ns: int,
) -> None:
    """Retire exact old session workers without discarding session history."""
    session = session_slot.current
    if session is None:
        return
    if not manual_configuration_available(session_slot):
        raise RuntimeError(
            "manual Configuration is blocked by unfinished session cleanup"
        )
    await workers.retire_completed_session(session.work, deadline_ns=deadline_ns)


def manual_command_valid(
    command: wire.BackendCommand,
    *,
    revision: int | None,
    expected_revision: int,
    identity: CoordinatorIdentity,
    session_slot: SessionSlot,
    now_ns: int,
    deadline_ns: int,
) -> bool:
    """Bind sessionless edits/PFS operations to the current controller and revision."""
    return bool(
        now_ns < deadline_ns
        and command.command_id
        and command.issuer == identity.controller
        and command.target == identity.backend
        and command.HasField("parent_operation")
        and command.parent_operation.command_id
        and command.work.WhichOneof("work") is None
        and revision is not None
        and revision == expected_revision
        and manual_configuration_available(session_slot)
    )
