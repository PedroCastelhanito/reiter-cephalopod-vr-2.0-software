"""Sessionless camera/preview and serial cleanup proof (A10/E06/E08)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from cephvr.acquisition.coordinator.commands import (
    retain_worker_command,
    wait_child_operation,
)
from cephvr.acquisition.ports import ResourcePort, SerialOwnerPort
from cephvr.acquisition.state import PulseRecord, ResourceRecord, WorkerRecord
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.resource_ledger import NativeResourceLedger
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger


class SessionlessCleanup:
    """Close independent configuration-time workers under one retained bound."""

    def __init__(
        self,
        *,
        workers: dict[int, WorkerRecord],
        resources: dict[str, ResourceRecord],
        pulse: PulseRecord,
        resource_ledger: NativeResourceLedger,
        commands: CommandLedger,
        resource_port: ResourcePort,
        serial: SerialOwnerPort,
        cleanup_complete: Callable[[WorkerRecord, acq.WorkerCleanupEvidence], bool],
        lock: asyncio.Lock,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.workers = workers
        self.resources = resources
        self.pulse = pulse
        self.resource_ledger = resource_ledger
        self.commands = commands
        self.resource_port = resource_port
        self.serial = serial
        self.cleanup_complete = cleanup_complete
        self.lock = lock
        self.clock = clock

    async def execute(
        self, request: wire.BackendCommand, *, deadline_ns: int
    ) -> control.CommandAdmission:
        if self.clock() >= deadline_ns:
            return _rejected(
                request.command_id,
                "CLEANUP_DEADLINE",
                "sessionless cleanup deadline expired before admission",
            )
        failures: list[str] = []
        selected = [
            record
            for record in tuple(self.workers.values())
            if record.context.work.WhichOneof("work") is None
        ]
        tasks = [
            self._cleanup_worker(record, request, deadline_ns) for record in selected
        ]
        serial_task: asyncio.Task[bool] | None = None
        serial_failures: list[str] = []
        if self.pulse.observation is not None:
            serial_task = asyncio.create_task(
                self._stop_serial(deadline_ns, serial_failures)
            )
        results = await asyncio.gather(*tasks, return_exceptions=True)
        closed: list[WorkerRecord] = []
        for record, result in zip(selected, results, strict=True):
            if isinstance(result, BaseException):
                failures.append(f"{record.launch.worker.role}: {result}")
            elif result is not None:
                closed.append(result)
        if serial_task is not None:
            try:
                await serial_task
            except BaseException as exc:
                serial_failures.append(str(exc))
            failures.extend(serial_failures)
        if not failures:
            for record in closed:
                preview = record.preview
                if preview is not None and preview.allocation_id is not None:
                    try:
                        self._close_ring(preview.allocation_id)
                    except (KeyError, RuntimeError, ValueError) as exc:
                        failures.append(
                            f"{record.launch.worker.role} preview ring remains owned: {exc}"
                        )
                    else:
                        record.preview = None
        if failures:
            return _rejected(
                request.command_id, "CLEANUP_UNCONFIRMED", "; ".join(failures)
            )
        return control.CommandAdmission(
            result=control.COMMAND_RESULT_ACCEPTED,
            command_id=request.command_id,
        )

    async def _cleanup_worker(
        self,
        record: WorkerRecord,
        request: wire.BackendCommand,
        deadline_ns: int,
    ) -> WorkerRecord:
        if record.port is None:
            raise RuntimeError("worker launch is unregistered")
        command, child, port = retain_worker_command(
            record,
            work=None,
            parent_operation=control.OperationContext(command_id=request.command_id),
            kind="cleanup",
            deadline_ns=deadline_ns,
            configuration_revision=record.preview.configuration_revision
            if record.preview
            else 0,
        )
        receipt = await port.cleanup(command, deadline_ns=deadline_ns)
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError("worker rejected cleanup")
        operation = await wait_child_operation(
            child, deadline_ns, self.lock, self.clock
        )
        if not operation.succeeded:
            raise RuntimeError("cleanup operation failed")
        evidence = await self._wait_cleanup(record, child.command_id, deadline_ns)
        if evidence is None or not self.cleanup_complete(record, evidence):
            raise RuntimeError("exact worker cleanup release evidence is incomplete")
        return record

    async def _wait_cleanup(
        self, record: WorkerRecord, command_id: str, deadline_ns: int
    ) -> acq.WorkerCleanupEvidence | None:
        child = record.child_operations.get(command_id)
        if child is None:
            return None
        while self.clock() <= deadline_ns:
            async with self.lock:
                match = next(
                    (
                        item
                        for item in record.lifecycle_evidence.values()
                        if item.WhichOneof("evidence") == "cleanup"
                        and item.operation.command_id == command_id
                        and item.source.work.WhichOneof("work") is None
                    ),
                    None,
                )
                if match is not None:
                    return acq.WorkerCleanupEvidence.FromString(
                        match.cleanup.SerializeToString(deterministic=True)
                    )
                child.updated.clear()
            remaining = max(0, deadline_ns - self.clock()) / 1_000_000_000
            if remaining <= 0:
                return None
            try:
                await asyncio.wait_for(child.updated.wait(), remaining)
            except TimeoutError:
                return None
        return None

    async def _stop_serial(self, deadline_ns: int, failures: list[str]) -> bool:
        try:
            await self.serial.cancel_on_reservations(deadline_ns=deadline_ns)
            evidence = await self.serial.off(
                (camera.CAMERA_ROLE_BEHAVIORAL, camera.CAMERA_ROLE_TRACKING),
                scheduled_boundary_ns=None,
                stop_issued_ns=self.clock(),
                deadline_ns=deadline_ns,
            )
            if (
                evidence.outcome != mcu.PULSE_COMMAND_OUTCOME_APPLIED
                or not evidence.HasField("resulting_state")
                or not _outputs_off(evidence.resulting_state)
            ):
                raise RuntimeError("both MCU outputs are not proven off")
            if self.pulse.observation is not None:
                self.pulse.observation.state.CopyFrom(evidence.resulting_state)
            await self.serial.close(deadline_ns=deadline_ns)
            self.pulse.observation = None
            return True
        except Exception as exc:
            failures.append(f"microcontroller OFF/close remains unconfirmed: {exc}")
            return False

    def _close_ring(self, allocation_id: str) -> None:
        resource = self.resources.get(allocation_id)
        if resource is None or resource.native_state == "released":
            return
        if not self.resource_ledger.may_close_owner(resource.ledger_key):
            raise ValueError(f"ring {allocation_id} still has an unreleased transfer")
        if resource.native_state != "absent":
            self.resource_port.release_ring(allocation_id)
        self.resource_ledger.confirm_owner_release(resource.ledger_key)
        self.resource_ledger.remove_completed_resource(resource.ledger_key)
        self.resources.pop(allocation_id, None)


def _outputs_off(state: mcu.MicrocontrollerState) -> bool:
    return all(
        state.HasField(role)
        and getattr(state, role).HasField("running")
        and not getattr(state, role).running
        for role in ("behavioral", "tracking")
    )


def _rejected(command_id: str, code: str, message: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        result=control.COMMAND_RESULT_REJECTED,
        command_id=command_id,
        failure=control.Failure(code=code, message=message[:2048]),
    )
