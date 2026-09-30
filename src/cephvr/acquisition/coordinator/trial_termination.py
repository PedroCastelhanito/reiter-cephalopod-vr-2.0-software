"""Trial Stop/Interrupt fanout and pulse-boundary failure response (A05/E05)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from typing import Any, Protocol
from uuid import uuid4

from cephvr.acquisition.coordinator.commands import retain_worker_command
from cephvr.acquisition.coordinator.manual_pulse_observation import (
    retain_applied_pulse_state,
)
from cephvr.acquisition.coordinator.trial_helpers import (
    _external_roles,
    _rejected,
)
from cephvr.acquisition.coordinator.trial_pulses import (
    TrialPulseBoundaries,
    _failure_evidence,
)
from cephvr.acquisition.ports import SerialOwnerPort
from cephvr.acquisition.state import (
    CoordinatorIdentity,
    PulseRecord,
    SessionRecord,
    SessionSlot,
    TrialRecord,
    WorkerRecord,
)
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns


class PulseBoundaryRunner(Protocol):
    def __call__(
        self,
        session: SessionRecord,
        trial: TrialRecord,
        selected_roles: tuple[int, ...],
        *,
        command: mcu.PulseBoundaryCommand,
        boundary_ns: int,
    ) -> Coroutine[Any, Any, None]: ...


class TrialTermination:
    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        session_slot: SessionSlot,
        workers: dict[int, WorkerRecord],
        serial: SerialOwnerPort,
        pulse: PulseRecord,
        pulse_boundaries: TrialPulseBoundaries,
        stop_evidence_allowance_ns: int,
        start_evidence_allowance_ns: int,
        lifecycle_delivery_ns: int,
        valid_command: Callable[[wire.BackendCommand, SessionRecord | None, int], bool],
        lock: asyncio.Lock,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.session_slot = session_slot
        self.workers = workers
        self.serial = serial
        self.pulse = pulse
        self.pulse_boundaries = pulse_boundaries
        self.stop_evidence_allowance_ns = stop_evidence_allowance_ns
        self.start_evidence_allowance_ns = start_evidence_allowance_ns
        self.lifecycle_delivery_ns = lifecycle_delivery_ns
        self._valid_command = valid_command
        self.lock = lock
        self.clock = clock

    async def stop(
        self,
        request: wire.StopTrialRequest,
        *,
        deadline_ns: int,
        aborted: bool = False,
        internal: bool = False,
    ) -> control.CommandAdmission:
        """Stop every exact trial worker and force external outputs off."""
        session = self.session_slot.current
        trial = session.trial if session is not None else None
        valid_command = self._valid_command(request.command, session, deadline_ns)
        if internal and session is not None and trial is not None:
            valid_command = bool(
                self.clock() < deadline_ns
                and not session.setup_cancelled
                and request.command.command_id
                and request.command.target == self.identity.backend
                and request.command.work == trial.work
            )
        if (
            not valid_command
            or trial is None
            or trial.schedule is None
            or trial.stop is not None
            or request.command.work != trial.work
            or request.issued_monotonic_ns <= 0
        ):
            return _rejected(
                request.command.command_id,
                "TRIAL_STOP",
                "no exact live scheduled trial",
            )
        assert session is not None
        async with self.lock:
            if self.session_slot.current is not session or session.trial is not trial:
                return _rejected(
                    request.command.command_id,
                    "TRIAL_STALE",
                    "trial changed before stop",
                )
            trial.stop = control.OperationContext(command_id=request.command.command_id)
            trial.stop_issued_ns = request.issued_monotonic_ns
            allowance = self.stop_evidence_allowance_ns
            trial.stop_deadline_ns = (
                request.issued_monotonic_ns + allowance
                if aborted or trial.end_monotonic_ns is None
                else trial.end_monotonic_ns + allowance
            )
            if aborted:
                trial.interrupted = True
        selected = _external_roles(session)
        serial_task = asyncio.create_task(
            self._force_outputs_off(
                trial,
                selected,
                request.issued_monotonic_ns,
                deadline_ns,
            )
        )
        failures: list[str] = []
        calls = []
        for role in sorted(session.required_cameras):
            worker = self.workers.get(role)
            if worker is None or worker.port is None:
                failures.append(f"camera role {role} is unavailable for Stop")
                continue
            try:
                child, operation, port = retain_worker_command(
                    worker,
                    work=trial.work,
                    parent_operation=trial.stop,
                    kind="stop_trial",
                    deadline_ns=deadline_ns,
                    configuration_revision=trial.configuration_revision,
                )
                if worker.trial is not None:
                    worker.trial.stop = control.OperationContext(
                        command_id=operation.command_id
                    )
                calls.append(
                    port.stop_trial(
                        acq.WorkerStop(
                            command=child,
                            issued_monotonic_ns=request.issued_monotonic_ns,
                            reason=request.reason,
                        ),
                        deadline_ns=deadline_ns,
                    )
                )
            except Exception as exc:
                failures.append(f"camera role {role} Stop: {exc}")
        worker_results, serial_result = await asyncio.gather(
            asyncio.create_task(_settle(calls)), serial_task
        )
        for result in worker_results:
            if isinstance(result, BaseException):
                failures.append(f"camera Stop failed: {result}")
            elif result.result != control.COMMAND_RESULT_ACCEPTED:
                failures.append("camera worker rejected Stop")
        failures.extend(serial_result)
        if failures:
            trial.interrupted = True
            return _rejected(
                request.command.command_id,
                "WORKER_STOP_UNCONFIRMED",
                "; ".join(failures),
            )
        return control.CommandAdmission(
            result=control.COMMAND_RESULT_ACCEPTED,
            command_id=request.command.command_id,
        )

    async def _force_outputs_off(
        self,
        trial: TrialRecord | None,
        selected: tuple[int, ...],
        issued_ns: int,
        deadline_ns: int,
    ) -> list[str]:
        failures: list[str] = []
        try:
            await self.serial.cancel_on_reservations(deadline_ns=deadline_ns)
        except Exception as exc:
            failures.append(f"ON-boundary cancellation failed: {exc}")
        if not selected:
            return failures
        try:
            evidence = await self.serial.off(
                selected,
                scheduled_boundary_ns=None,
                stop_issued_ns=issued_ns,
                deadline_ns=deadline_ns,
            )
        except TimeoutError:
            evidence = _failure_evidence(
                selected,
                mcu.PULSE_BOUNDARY_COMMAND_OFF,
                issued_ns,
                mcu.PULSE_COMMAND_OUTCOME_TIMED_OUT,
            )
            failures.append("MCU OFF missed its original deadline")
        except Exception as exc:
            evidence = _failure_evidence(
                selected,
                mcu.PULSE_BOUNDARY_COMMAND_OFF,
                issued_ns,
                mcu.PULSE_COMMAND_OUTCOME_TRANSPORT_FAILED,
            )
            failures.append(f"MCU OFF failed: {exc}")
        if trial is not None:
            trial.pulse_off = evidence
        if evidence.outcome == mcu.PULSE_COMMAND_OUTCOME_APPLIED:
            try:
                retain_applied_pulse_state(
                    self.pulse, evidence, deadline_ns=deadline_ns
                )
            except (RuntimeError, ValueError) as exc:
                failures.append(f"MCU OFF evidence is invalid: {exc}")
                if trial is not None:
                    trial.interrupted = True
        else:
            failures.append(
                "MCU OFF outcome was " + mcu.PulseCommandOutcome.Name(evidence.outcome)
            )
        if trial is not None:
            try:
                await self.pulse_boundaries.send_evidence(trial, evidence, deadline_ns)
            except Exception as exc:
                failures.append(f"MCU OFF evidence delivery failed: {exc}")
        return failures

    async def interrupt_session(
        self, request: wire.InterruptSessionRequest, *, deadline_ns: int
    ) -> control.CommandAdmission:
        """Fence a session, stop its workers, and independently force pulse OFF."""
        session = self.session_slot.current
        if (
            session is None
            or self.clock() >= deadline_ns
            or request.command.issuer != self.identity.controller
            or request.command.target != self.identity.backend
            or request.command.work != session.work
            or request.issued_monotonic_ns <= 0
        ):
            return _rejected(
                request.command.command_id, "SESSION_IDENTITY", "no exact live session"
            )
        async with self.lock:
            if self.session_slot.current is not session:
                return _rejected(
                    request.command.command_id, "SESSION_STALE", "session changed"
                )
            session.interrupted = True
            self.session_slot.interrupted = True
            if session.trial is not None:
                session.trial.interrupted = True
        selected = _external_roles(session)
        serial_task = asyncio.create_task(
            self._force_outputs_off(
                session.trial,
                selected,
                request.issued_monotonic_ns,
                deadline_ns,
            )
        )
        failures: list[str] = []
        calls = []
        for role in sorted(session.required_cameras):
            worker = self.workers.get(role)
            if worker is None or worker.port is None:
                failures.append(f"camera role {role} is unavailable for Interrupt")
                continue
            try:
                child, _operation, port = retain_worker_command(
                    worker,
                    work=session.work,
                    parent_operation=control.OperationContext(
                        command_id=request.command.command_id
                    ),
                    kind="interrupt_session",
                    deadline_ns=deadline_ns,
                    configuration_revision=session.configuration_revision,
                )
                calls.append(
                    port.interrupt_session(
                        acq.WorkerInterrupt(
                            command=child,
                            issued_monotonic_ns=request.issued_monotonic_ns,
                            reason=request.reason,
                        ),
                        deadline_ns=deadline_ns,
                    )
                )
            except Exception as exc:
                failures.append(f"camera role {role} Interrupt: {exc}")
        worker_results, serial_result = await asyncio.gather(
            asyncio.create_task(_settle(calls)), serial_task
        )
        for result in worker_results:
            if isinstance(result, BaseException):
                failures.append(f"camera Interrupt failed: {result}")
            elif result.result != control.COMMAND_RESULT_ACCEPTED:
                failures.append("camera worker rejected Interrupt")
        failures.extend(serial_result)
        if failures:
            return _rejected(
                request.command.command_id,
                "SESSION_INTERRUPT_UNCONFIRMED",
                "; ".join(failures),
            )
        return control.CommandAdmission(
            result=control.COMMAND_RESULT_ACCEPTED,
            command_id=request.command.command_id,
        )

    async def run_pulse_boundary(
        self,
        session: SessionRecord,
        trial: TrialRecord,
        selected_roles: tuple[int, ...],
        *,
        command: mcu.PulseBoundaryCommand,
        boundary_ns: int,
    ) -> None:
        await self.pulse_boundaries.execute(
            session,
            trial,
            selected_roles,
            command=command,
            boundary_ns=boundary_ns,
        )
        if trial.interrupted and trial.stop is None and not session.setup_cancelled:
            stop_deadline = boundary_ns + self.control_pulse_failure_allowance(command)
            command_id = str(uuid4())
            await self.stop(
                wire.StopTrialRequest(
                    command=wire.BackendCommand(
                        command_id=command_id,
                        issuer=self.identity.process,
                        target=self.identity.backend,
                        work=trial.work,
                    ),
                    issued_monotonic_ns=max(1, self.clock()),
                    reason=control.Failure(
                        code="PULSE_BOUNDARY_UNCONFIRMED",
                        message="pulse evidence or delivery is unconfirmed",
                    ),
                ),
                deadline_ns=stop_deadline,
                aborted=True,
                internal=True,
            )

    def control_pulse_failure_allowance(self, command: mcu.PulseBoundaryCommand) -> int:
        return (
            self.start_evidence_allowance_ns
            if command == mcu.PULSE_BOUNDARY_COMMAND_ON
            else self.lifecycle_delivery_ns
        )


async def _settle(
    calls: Sequence[Awaitable[control.CommandAdmission]],
) -> list[control.CommandAdmission | BaseException]:
    return list(await asyncio.gather(*calls, return_exceptions=True))
