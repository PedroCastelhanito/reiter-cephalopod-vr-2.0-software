"""E02 live WatchState control lease acquisition and release."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.operations import ControlOperations
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.state import ControlState, LifecycleState


class ControlLeases:
    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        control: ControlState,
        operations: ControlOperations,
        publisher: SnapshotPublisher,
        generation: str,
        owner_lost: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.lifecycle = lifecycle
        self.control = control
        self.control_operations = operations
        self.publisher = publisher
        self.generation = generation
        self.owner_lost = owner_lost

    def bind_owner_loss(self, handler: Callable[[], Awaitable[None]]) -> None:
        self.owner_lost = handler

    async def claim(
        self, claim: svc.ControlClaim, *, takeover: bool = False
    ) -> pb.CommandAdmission:
        async with self.lifecycle.lock:
            if self.lifecycle.authority_lost:
                return self.control_operations.admission(
                    claim.command_id, error="controller authority permanently lost"
                )
            key = (claim.client_id, claim.watch_id)
            watch = self.control.watches.get(key)
            if (
                claim.controller_generation != self.generation
                or watch is None
                or claim.synchronized_state_revision != watch.installed_revision
            ):
                return self.control_operations.admission(
                    claim.command_id,
                    error="claim requires this client's synchronized live WatchState",
                )
            if self.control.owner is not None and not takeover:
                return self.control_operations.admission(
                    claim.command_id, error="control is held"
                )
            if claim.HasField("session_id") and (
                self.lifecycle.attempt is None
                or claim.session_id != self.lifecycle.attempt.context.session_id
            ):
                return self.control_operations.admission(
                    claim.command_id, error="session identity mismatch"
                )
            self.control.owner = (claim.client_id, claim.watch_id, str(uuid.uuid4()))
            self.publisher.publish()
            return self.control_operations.admission(claim.command_id)

    async def release_control(
        self, command: svc.OperatorCommand
    ) -> pb.CommandAdmission:
        released = False
        async with self.lifecycle.lock:
            error = self.control_operations.authorized(command)
            if error:
                return self.control_operations.admission(
                    command.operator.command_id, error=error
                )
            released = self.control.owner is not None
            self.control.owner = None
            if (
                released
                and self.lifecycle.session.phase == pb.SESSION_PHASE_CONFIGURATION
            ):
                self.lifecycle.manual_control_cleanup_pending = True
            self.publisher.publish()
            admission = self.control_operations.admission(command.operator.command_id)
        if released and self.owner_lost is not None:
            await self.owner_lost()
        return admission
