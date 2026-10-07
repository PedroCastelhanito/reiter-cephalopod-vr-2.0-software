"""Aggregate exact session cleanup evidence for controller and supervisor (E06/E08)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from cephvr.acquisition.coordinator.cleanup_report import CleanupReportBuilder
from cephvr.acquisition.coordinator.commands import (
    retain_worker_command,
    wait_child_operation,
)
from cephvr.acquisition.coordinator.sessionless_cleanup import SessionlessCleanup
from cephvr.acquisition.ports import (
    ControllerPort,
    ResourcePort,
    SerialOwnerPort,
    SupervisorPort,
)
from cephvr.acquisition.state import (
    CoordinatorIdentity,
    PulseRecord,
    ResourceRecord,
    SessionRecord,
    SessionSlot,
    WorkerRecord,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.resource_ledger import NativeResourceLedger
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger


class CoordinatorCleanup:
    """Own the cleanup proof join and immutable report delivery for one session."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        session_slot: SessionSlot,
        workers: dict[int, WorkerRecord],
        resources: dict[str, ResourceRecord],
        pulse: PulseRecord,
        resource_ledger: NativeResourceLedger,
        commands: CommandLedger,
        resource_port: ResourcePort,
        serial: SerialOwnerPort,
        controller: ControllerPort,
        supervisor: SupervisorPort,
        worker_cleanup_complete: Callable[
            [WorkerRecord, acq.WorkerCleanupEvidence], bool
        ],
        lock: asyncio.Lock,
        close_preview_windows: Callable[..., Awaitable[None]] | None = None,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.session_slot = session_slot
        self.workers = workers
        self.resources = resources
        self.pulse = pulse
        self.resource_ledger = resource_ledger
        self.commands = commands
        self.resource_port = resource_port
        self.serial = serial
        self.controller = controller
        self.supervisor = supervisor
        self.worker_cleanup_complete = worker_cleanup_complete
        self.lock = lock
        self.clock = clock
        self.report_builder = CleanupReportBuilder(
            identity=identity,
            workers=workers,
            resources=resources,
            resource_ledger=resource_ledger,
            resource_port=resource_port,
            clock=clock,
        )
        self._active = False
        self.close_preview_windows = close_preview_windows
        self.sessionless = SessionlessCleanup(
            workers=workers,
            resources=resources,
            pulse=pulse,
            resource_ledger=resource_ledger,
            commands=commands,
            resource_port=resource_port,
            serial=serial,
            cleanup_complete=worker_cleanup_complete,
            lock=lock,
            clock=clock,
        )

    async def execute(
        self, request: wire.BackendCommand, *, deadline_ns: int
    ) -> control.CommandAdmission:
        if self._active:
            return _rejected(
                request.command_id,
                "CLEANUP_IN_PROGRESS",
                "another exact cleanup attempt is still active",
            )
        self._active = True
        try:
            window_failure = ""
            if self.close_preview_windows is not None:
                try:
                    await self.close_preview_windows(deadline_ns=deadline_ns)
                except Exception as exc:
                    window_failure = str(exc)
            # Stop SDK/pulse activity even if native viewer release remains unknown.
            result = await self._execute(request, deadline_ns=deadline_ns)
            if window_failure:
                return _rejected(
                    request.command_id, "PREVIEW_RELEASE_UNCONFIRMED", window_failure
                )
            return result
        finally:
            self._active = False

    async def _execute(
        self, request: wire.BackendCommand, *, deadline_ns: int
    ) -> control.CommandAdmission:
        session = self.session_slot.current
        if session is None:
            if request.work.WhichOneof("work") is not None:
                return _rejected(
                    request.command_id,
                    "CLEANUP_WORK",
                    "cleanup targets a session that is not retained",
                )
            return await self._cleanup_sessionless(request, deadline_ns)
        if request.work.WhichOneof("work") is None:
            if not session.cleanup_complete:
                return _rejected(
                    request.command_id,
                    "CLEANUP_WORK",
                    "active session cleanup requires its exact session context",
                )
            return await self._cleanup_sessionless(request, deadline_ns)
        if self.clock() >= deadline_ns:
            return _rejected(
                request.command_id,
                "CLEANUP_DEADLINE",
                "cleanup deadline expired before admission",
            )
        if request.work != session.work:
            return _rejected(
                request.command_id,
                "CLEANUP_WORK",
                "cleanup work is not the retained session",
            )
        if session.cleanup_complete:
            if session.pending_cleanup_report is None:
                return _rejected(
                    request.command_id,
                    "CLEANUP_PROOF_UNAVAILABLE",
                    "the current session has no retained local cleanup proof",
                )
            if session.cleanup_command_id == request.command_id:
                if session.cleanup_attempt_deadline_ns != deadline_ns:
                    return _rejected(
                        request.command_id,
                        "CLEANUP_DEADLINE",
                        "cleanup retry changed its original deadline",
                    )
                return await self._deliver(session, deadline_ns)
            try:
                prior_report = session.pending_cleanup_report
                if prior_report is None:
                    raise ValueError("no closed cleanup proof is retained")
                prior_report = control.CleanupReport.FromString(
                    prior_report.SerializeToString(deterministic=True)
                )
                session.prepare_cleanup_command(request.command_id, self.commands)
                session.archive_cleanup_report(self.commands)
                retained = prior_report
                retained.operation.command_id = request.command_id
                session.cleanup_command_id = request.command_id
                session.cleanup_attempt_deadline_ns = deadline_ns
                session.cleanup_report_recipients.clear()
                session.retain_cleanup_report(retained, self.commands)
            except (RuntimeError, ValueError, KeyError) as exc:
                return _rejected(request.command_id, "CLEANUP_HISTORY", str(exc))
            return await self._deliver(session, deadline_ns)
        if (
            session.pending_cleanup_report is not None
            and session.cleanup_command_id == request.command_id
        ):
            if session.cleanup_attempt_deadline_ns != deadline_ns:
                return _rejected(
                    request.command_id,
                    "CLEANUP_REPLAY",
                    "retained cleanup report belongs to another command",
                )
            return await self._deliver(session, deadline_ns)
        if session.cleanup_command_id != request.command_id:
            if session.pending_cleanup_report is not None:
                try:
                    session.archive_cleanup_report(self.commands)
                except (RuntimeError, ValueError) as exc:
                    return _rejected(request.command_id, "CLEANUP_HISTORY", str(exc))
            session.cleanup_report_recipients.clear()
            session.cleanup_command_id = request.command_id
            session.cleanup_attempt_deadline_ns = deadline_ns
            try:
                session.reserve_cleanup_evidence(self.commands)
                session.prepare_cleanup_command(request.command_id, self.commands)
            except (RuntimeError, ValueError) as exc:
                return _rejected(request.command_id, "CLEANUP_CAPACITY", str(exc))
        elif session.cleanup_attempt_deadline_ns != deadline_ns:
            return _rejected(
                request.command_id,
                "CLEANUP_DEADLINE",
                "cleanup changed its original command or deadline",
            )
        else:
            try:
                session.prepare_cleanup_command(request.command_id, self.commands)
            except (RuntimeError, ValueError) as exc:
                return _rejected(request.command_id, "CLEANUP_CAPACITY", str(exc))

        failures: list[str] = []
        worker_cleanup: dict[int, acq.WorkerCleanupEvidence] = {}
        selected_workers = [
            (role, record)
            for role, record in tuple(self.workers.items())
            if record.context.work == session.work
        ]
        worker_tasks = [
            self._cleanup_worker(record, request.command_id, session, deadline_ns)
            for _role, record in selected_workers
        ]
        serial_failures: list[str] = []
        serial_task = asyncio.create_task(
            self._stop_and_close_serial(session, deadline_ns, serial_failures)
        )
        outcomes = await asyncio.gather(*worker_tasks, return_exceptions=True)
        for (role, record), outcome in zip(selected_workers, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                failures.append(f"{record.launch.worker.role} cleanup: {outcome}")
            elif outcome is None or not self.worker_cleanup_complete(record, outcome):
                failures.append(
                    f"{record.launch.worker.role} cleanup evidence is incomplete"
                )
            else:
                worker_cleanup[role] = outcome
        try:
            serial_released = await serial_task
        except BaseException as exc:
            failures.append(f"microcontroller cleanup: {exc}")
            serial_released = False
        failures.extend(serial_failures)
        if failures:
            return _rejected(
                request.command_id, "CLEANUP_UNCONFIRMED", "; ".join(failures)
            )

        try:
            report = self.report_builder.build(
                session, request.command_id, worker_cleanup, serial_released
            )
        except (RuntimeError, ValueError) as exc:
            return _rejected(request.command_id, "CLEANUP_EVIDENCE", str(exc))
        async with self.lock:
            if session.pending_cleanup_report is None:
                session.retain_cleanup_report(report, self.commands)
            elif session.pending_cleanup_report.SerializeToString(
                deterministic=True
            ) != report.SerializeToString(deterministic=True):
                return _rejected(
                    request.command_id,
                    "CLEANUP_CONFLICT",
                    "cleanup evidence changed after report retention",
                )
            if not session.cleanup_complete:
                session.cleanup_complete = True
                self._finalize_local_proof(session)
        return await self._deliver(session, deadline_ns)

    def _finalize_local_proof(self, session: SessionRecord) -> None:
        """Retire closed local mappings independently from report receipts."""
        finalized_ns = self.clock()
        session_id = session.work.session.session_id
        self.commands.finalize_work(session_id, finalized_ns)
        for worker in self.workers.values():
            if worker.context.work == session.work:
                worker.finalize_lifecycle_work(session_id, finalized_ns)
        for obligation in session.cleanup_resources:
            resource = self.resources.get(obligation.resource)
            if resource is None or obligation.owner != self.identity.process:
                continue
            self.resource_ledger.remove_completed_resource(resource.ledger_key)
            self.resources.pop(obligation.resource, None)

    async def _cleanup_worker(
        self,
        record: WorkerRecord,
        parent_id: str,
        session: SessionRecord,
        deadline_ns: int,
    ) -> acq.WorkerCleanupEvidence | None:
        if record.port is None:
            raise RuntimeError("registered worker endpoint is unavailable")
        child = next(
            (
                item
                for item in record.child_operations.values()
                if item.kind == "cleanup"
                and item.work == session.work
                and item.parent_operation.command_id == parent_id
            ),
            None,
        )
        if child is None:
            command, child, port = retain_worker_command(
                record,
                work=session.work,
                parent_operation=control.OperationContext(command_id=parent_id),
                kind="cleanup",
                deadline_ns=deadline_ns,
                configuration_revision=session.confirmed_revision
                or session.configuration_revision,
            )
        else:
            command = acq.WorkerCommand(
                command_id=child.command_id,
                issuer=record.launch.owner,
                target=record.context,
                parent_operation=child.parent_operation,
            )
            if child.work.WhichOneof("work") is not None:
                command.target.work.CopyFrom(child.work)
            port = record.port
        receipt = await port.cleanup(command, deadline_ns=deadline_ns)
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError("worker rejected exact cleanup command")
        operation = await wait_child_operation(
            child, deadline_ns, self.lock, self.clock
        )
        if not operation.succeeded:
            raise RuntimeError("worker cleanup operation did not succeed")
        while self.clock() <= deadline_ns:
            async with self.lock:
                matching = next(
                    (
                        item
                        for item in record.lifecycle_evidence.values()
                        if item.WhichOneof("evidence") == "cleanup"
                        and item.operation.command_id == child.command_id
                        and item.source.work == session.work
                    ),
                    None,
                )
                if matching is not None:
                    saved = acq.WorkerCleanupEvidence.FromString(
                        matching.cleanup.SerializeToString(deterministic=True)
                    )
                    return saved
                child.updated.clear()
            remaining = max(0, deadline_ns - self.clock()) / 1_000_000_000
            if remaining <= 0:
                break
            try:
                await asyncio.wait_for(child.updated.wait(), remaining)
            except TimeoutError:
                break
        return None

    async def _stop_and_close_serial(
        self, session: SessionRecord, deadline_ns: int, failures: list[str]
    ) -> bool:
        port_resources = [
            item
            for item in session.cleanup_resources
            if item.resource.startswith("microcontroller-claim:")
        ]
        if not port_resources:
            return True
        if session.serial_owner_released:
            return True
        if self.clock() >= deadline_ns:
            failures.append("serial cleanup deadline expired")
            return False
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
            session.serial_owner_released = True
            return True
        except Exception as exc:
            failures.append(f"microcontroller OFF/close remains unconfirmed: {exc}")
            return False

    async def _deliver(
        self, session: SessionRecord, deadline_ns: int
    ) -> control.CommandAdmission:
        pending = session.pending_cleanup_report
        if pending is None:
            return _rejected("", "CLEANUP_REPORT_MISSING", "no retained cleanup report")
        if (
            session.cleanup_attempt_deadline_ns != deadline_ns
            or self.clock() > deadline_ns
        ):
            return _rejected(
                pending.operation.command_id,
                "CLEANUP_DEADLINE",
                "cleanup report missed its original deadline",
            )
        failures: list[str] = []
        recipients = [
            ("controller", self.controller.report_lifecycle),
            ("supervisor", self.supervisor.report_lifecycle),
        ]
        pending_recipients = [
            (recipient, send)
            for recipient, send in recipients
            if recipient not in session.cleanup_report_recipients
        ]
        results = await asyncio.gather(
            *(
                send(
                    control.LifecycleReport(cleanup=pending),
                    deadline_ns=deadline_ns,
                )
                for _recipient, send in pending_recipients
            ),
            return_exceptions=True,
        )
        for (recipient, _send), receipt in zip(
            pending_recipients, results, strict=True
        ):
            if isinstance(receipt, BaseException):
                failures.append(f"{recipient}: {receipt}")
                continue
            if receipt.result != control.COMMAND_RESULT_ACCEPTED:
                failures.append(
                    f"{recipient}: {receipt.failure.code} {receipt.failure.message}"
                )
                continue
            session.cleanup_report_recipients.add(recipient)
        if failures:
            return _rejected(
                pending.operation.command_id,
                "CLEANUP_REPORT_UNCONFIRMED",
                "; ".join(failures),
            )
        session.cleanup_delivery_complete = True
        return _accepted(pending.operation.command_id)

    async def _cleanup_sessionless(
        self, request: wire.BackendCommand, deadline_ns: int
    ) -> control.CommandAdmission:
        return await self.sessionless.execute(request, deadline_ns=deadline_ns)


def _outputs_off(state: mcu.MicrocontrollerState) -> bool:
    return all(
        state.HasField(role)
        and getattr(state, role).HasField("running")
        and not getattr(state, role).running
        for role in ("behavioral", "tracking")
    )


def _accepted(command_id: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        result=control.COMMAND_RESULT_ACCEPTED, command_id=command_id
    )


def _rejected(command_id: str, code: str, message: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        result=control.COMMAND_RESULT_REJECTED,
        command_id=command_id,
        failure=control.Failure(code=code, message=message[:2048]),
    )
