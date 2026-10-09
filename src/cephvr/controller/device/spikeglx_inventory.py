"""Lease-protected file inventory access for controller-owned SpikeGLX (E12)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.operations import ControlOperations
from cephvr.controller.state import (
    ConfigurationState,
    LifecycleState,
    LimitsState,
)
from cephvr.shared.deadlines import remaining_seconds
from cephvr.synchronization.inventory import (
    _mapping,
    _validate_channels,
    update_inventory,
)
from cephvr.synchronization.inventory_validation import required_inventory_roles
from cephvr.synchronization.settings import load_host_settings


@dataclass(slots=True)
class _PendingWrite:
    command_id: str
    deadline_ns: int
    task: asyncio.Task[str]
    settlement: asyncio.Task[None] | None = None
    error: str = ""


class SpikeGLXInventory:
    """Read or atomically update only the host-file pulse inventory section."""

    def __init__(
        self,
        *,
        software_root: Path,
        lifecycle: LifecycleState,
        configuration: ConfigurationState,
        operations: ControlOperations,
        limits: LimitsState,
        publish: Callable[[], None],
        clock: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self.software_root = software_root
        self.lifecycle = lifecycle
        self.configuration = configuration
        self.operations = operations
        self.limits = limits
        self.publish = publish
        self.clock = clock
        self._pending_write: _PendingWrite | None = None

    async def read(
        self, request: svc.SpikeGLXInventoryRequest
    ) -> tuple[svc.SpikeGLXInventorySnapshot | None, str]:
        async with self.lifecycle.lock:
            error = self._precondition(
                request.command, request.expected_configuration_revision
            )
            if error:
                return None, error
            revision = self.configuration.revision
        try:
            settings = await asyncio.to_thread(load_host_settings, self.software_root)
        except (OSError, ValueError) as exc:
            return None, f"SpikeGLX inventory is unavailable: {exc}"
        async with self.lifecycle.lock:
            error = self._precondition(
                request.command, request.expected_configuration_revision
            )
            if error:
                return None, error
            return (
                svc.SpikeGLXInventorySnapshot(
                    configuration_revision=revision,
                    file_sha256=settings.file_sha256,
                    pulse_channels=settings.inventory,
                    backend_enabled=next(
                        (
                            item.enabled
                            for item in self.configuration.current.backends
                            if item.backend_name == "synchronization"
                        ),
                        False,
                    ),
                    address=settings.address,
                    command_port=settings.port,
                ),
                "",
            )

    async def update(
        self, request: svc.SpikeGLXInventoryUpdateRequest
    ) -> pb.CommandAdmission:
        command_id = request.command.operator.command_id
        deadline_ns = self.clock() + self.limits.current.validation_ns
        async with self.lifecycle.lock:
            error = self._precondition(
                request.command,
                request.expected_configuration_revision,
                edit=True,
            )
            if error:
                return self.operations.admission(command_id, error=error)
            if not request.expected_file_sha256:
                return self.operations.admission(
                    command_id, error="inventory file digest is required"
                )
            try:
                if self.lifecycle.inventory_update_pending:
                    return self.operations.admission(
                        command_id, error="another inventory update is unresolved"
                    )
                config_revision = self.configuration.revision
                captured_configuration = type(self.configuration.current).FromString(
                    self.configuration.current.SerializeToString()
                )
                pulse_channels = tuple(
                    type(channel).FromString(channel.SerializeToString())
                    for channel in request.pulse_channels
                )
            except Exception as exc:
                return self.operations.admission(command_id, error=str(exc))

        # Mapping and inventory validation can touch host files; never perform
        # that work under the lifecycle lock.
        try:
            required_roles = required_inventory_roles(captured_configuration)
            remaining = remaining_seconds(deadline_ns, clock=self.clock)
            if remaining <= 0:
                raise TimeoutError("inventory edit exceeded its validation deadline")

            def validate() -> None:
                _validate_channels(
                    pulse_channels,
                    _mapping(self.software_root),
                    required_roles=required_roles,
                )

            await asyncio.wait_for(asyncio.to_thread(validate), remaining)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return self.operations.admission(
                command_id, error=f"inventory validation unavailable: {exc}"
            )

        async with self.lifecycle.lock:
            error = self._precondition(
                request.command,
                request.expected_configuration_revision,
                edit=True,
            )
            if error:
                return self.operations.admission(command_id, error=error)
            if config_revision != self.configuration.revision:
                return self.operations.admission(
                    command_id,
                    error="configuration revision changed during inventory validation",
                )
            if self.lifecycle.inventory_update_pending:
                return self.operations.admission(
                    command_id, error="another inventory update is unresolved"
                )
            if self.clock() >= deadline_ns:
                return self.operations.admission(
                    command_id, error="inventory edit exceeded its validation deadline"
                )

            self.operations.operation(
                command_id,
                "UpdateSpikeGLXInventory",
                progress="atomic inventory replacement is in progress",
            )
            self.lifecycle.inventory_update_pending = True
            writer = asyncio.create_task(
                asyncio.to_thread(
                    update_inventory,
                    self.software_root,
                    expected_file_sha256=request.expected_file_sha256,
                    pulse_channels=pulse_channels,
                    required_roles=required_roles,
                ),
                name=f"spikeglx-inventory-write-{command_id}",
            )
            pending = _PendingWrite(command_id, deadline_ns, writer)
            pending.settlement = asyncio.create_task(
                self._settle(pending), name=f"settle-{writer.get_name()}"
            )
            self._pending_write = pending
            self.publish()

        try:
            remaining = remaining_seconds(deadline_ns, clock=self.clock)
            done, _ = await asyncio.wait((writer,), timeout=remaining)
        except asyncio.CancelledError:
            await self._mark_unconfirmed(
                pending, "request cancelled; persistence outcome unconfirmed"
            )
            raise
        if not done:
            await self._mark_unconfirmed(
                pending, "deadline exceeded; persistence outcome unconfirmed"
            )
            # Dispatch is the commit point: an accepted operation may complete
            # after this RPC bound, so retain its outcome under its command ID.
            return self.operations.admission(command_id)

        assert pending.settlement is not None
        await asyncio.shield(pending.settlement)
        if pending.error:
            return self.operations.admission(command_id, error=pending.error)
        return self.operations.admission(command_id)

    async def _mark_unconfirmed(self, pending: _PendingWrite, progress: str) -> None:
        async with self.lifecycle.lock:
            operation = self.operations.control.operations.get(pending.command_id)
            if operation is not None and not operation.complete:
                operation.progress = progress
            self.publish()

    async def _settle(self, pending: _PendingWrite) -> None:
        try:
            await asyncio.shield(pending.task)
        except Exception as exc:
            pending.error = str(exc)
        async with self.lifecycle.lock:
            if self._pending_write is not pending:
                return
            self.lifecycle.inventory_update_pending = False
            self._pending_write = None
            late = self.clock() >= pending.deadline_ns
            if pending.error:
                progress = (
                    "inventory replacement failed after deadline"
                    if late
                    else "inventory replacement failed"
                )
                self.operations.complete_operation(
                    pending.command_id,
                    success=False,
                    progress=progress,
                    error=pending.error,
                )
            else:
                progress = (
                    "inventory committed after deadline"
                    if late
                    else "inventory committed"
                )
                self.operations.complete_operation(
                    pending.command_id,
                    success=True,
                    progress=progress,
                )
            self.publish()

    def _precondition(
        self,
        command: svc.OperatorCommand,
        expected_revision: int,
        *,
        edit: bool = False,
    ) -> str:
        error = self.operations.authorized(command)
        if error:
            return error
        if expected_revision != self.configuration.revision:
            return "configuration revision mismatch"
        phases = {pb.SESSION_PHASE_CONFIGURATION}
        if not edit:
            phases.add(pb.SESSION_PHASE_READY)
        if self.lifecycle.session.phase not in phases:
            return "SpikeGLX inventory is unavailable in this session phase"
        if edit and (
            self.lifecycle.startup_blocker
            or self.lifecycle.manual_control_cleanup_pending
            or self.lifecycle.authority_lost
            or self.lifecycle.session.shutdown_requested
        ):
            return "SpikeGLX inventory editing is blocked by controller state"
        if edit and self.lifecycle.inventory_update_pending:
            return "SpikeGLX inventory update is still unresolved"
        return ""
