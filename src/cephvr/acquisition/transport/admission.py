"""Bounded, method-bound command replay at the acquisition transport edge."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol

from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandCapacityError, CommandConflict, CommandLedger
from cephvr.shared.transport_deadlines import remaining_seconds


class AdmissionHandler(Protocol):
    def __call__(self, *, deadline_ns: int) -> Awaitable[control.CommandAdmission]: ...


class CommandAdmissionTransport:
    """Pin original deadlines and serialize concurrent retries per command ID."""

    def __init__(
        self,
        ledger: CommandLedger,
        *,
        terminal_failure: Callable[
            [str, wire.BackendCommand, control.OperationState, int], Awaitable[None]
        ]
        | None = None,
    ) -> None:
        self._ledger = ledger
        self._terminal_failure = terminal_failure
        self._inflight: dict[str, asyncio.Task[bytes]] = {}
        self._accepting = True

    @property
    def outstanding_commands(self) -> tuple[str, ...]:
        return tuple(self._inflight)

    async def close(self, deadline_ns: int) -> None:
        """Stop new admission and drain owned tasks through the retained deadline."""
        self._accepting = False
        tasks = tuple(self._inflight.values())
        if not tasks:
            return
        timeout = remaining_seconds(deadline_ns)
        if timeout <= 0:
            raise TimeoutError("admission tasks remain beyond shutdown deadline")
        done, pending = await asyncio.wait(tasks, timeout=timeout)
        for task in done:
            try:
                task.result()
            except Exception:
                # The ledger retains the explicit uncertainty result if needed.
                pass
        if pending:
            raise TimeoutError(
                f"{len(pending)} admitted commands remain owned after shutdown deadline"
            )

    async def dispatch(
        self,
        method: str,
        request: Message,
        command: wire.BackendCommand,
        deadline_ns: int,
        handler: AdmissionHandler,
        *,
        priority: bool = False,
        result_reservation_bytes: int | None = None,
    ) -> control.CommandAdmission:
        if not self._accepting:
            return _rejected(
                command.command_id,
                "SERVICE_CLOSING",
                "acquisition transport no longer accepts new commands",
            )
        command_id = command.command_id
        try:
            canonical = (
                method.encode("ascii", "strict")
                + b"\0"
                + request.SerializeToString(deterministic=True)
            )
            work_key = _work_key(command)
            admitted = self._ledger.admit(
                command_id,
                canonical,
                host_time_ns(),
                work_key=(
                    command_id if method in {"Cleanup", "Shutdown"} else work_key
                ),
                deadline_ns=deadline_ns,
                priority=priority,
                result_reservation_bytes=result_reservation_bytes,
            )
        except (CommandCapacityError, CommandConflict, ValueError) as exc:
            return _rejected(command_id, "COMMAND_ADMISSION", str(exc))
        record = admitted.record
        if record.result is not None:
            return control.CommandAdmission.FromString(record.result)
        task = self._inflight.get(command_id)
        if task is None:
            if admitted.replayed:
                return _rejected(
                    command_id,
                    "COMMAND_UNCONFIRMED",
                    "retained command has no completed admission receipt",
                )
            accepted = control.CommandAdmission(
                result=control.COMMAND_RESULT_ACCEPTED,
                command_id=command_id,
            )
            record = self._ledger.complete(
                command_id,
                accepted.SerializeToString(deterministic=True),
                host_time_ns(),
            )
            task = asyncio.create_task(
                self._execute_first(
                    method,
                    command,
                    record.deadline_ns or deadline_ns,
                    handler,
                )
            )
            self._inflight[command_id] = task
        # The RPC is an admission boundary. The retained task owns hardware work
        # independently of this caller and reports its terminal lifecycle later.
        if record.result is None:
            raise RuntimeError("accepted admission receipt was not retained")
        return control.CommandAdmission.FromString(record.result)

    async def _execute_first(
        self,
        method: str,
        command: wire.BackendCommand,
        deadline_ns: int,
        handler: AdmissionHandler,
    ) -> bytes:
        handler_returned = False
        try:
            result = await handler(deadline_ns=deadline_ns)
            handler_returned = True
        except asyncio.CancelledError:
            # Cancellation cannot prove that no side effect ran; retain an
            # unconfirmed terminal record and retire the executor task.
            result = _rejected(
                command.command_id,
                "COMMAND_UNCONFIRMED",
                f"{method} executor was cancelled after admission; cleanup remains required",
            )
        except Exception as exc:
            # Once admitted, an OS/transport exception cannot prove that no effect
            # occurred. Retain an explicit non-replayable uncertainty result and
            # leave its work scope unfinalized as a cleanup blocker.
            result = _rejected(
                command.command_id,
                "COMMAND_UNCONFIRMED",
                f"{method} outcome is unconfirmed; do not retry with a new command ID: {exc}",
            )
        try:
            if result.result == control.COMMAND_RESULT_REJECTED:
                outcome = control.OperationState(
                    context=control.OperationContext(command_id=command.command_id),
                    command=method,
                    work=command.work,
                    complete=True,
                    succeeded=False,
                    failure=result.failure,
                )
                self._ledger.complete_executor(
                    command.command_id,
                    outcome.SerializeToString(deterministic=True),
                    host_time_ns(),
                )
                if self._terminal_failure is not None:
                    try:
                        retained = self._ledger.get(command.command_id)
                        await self._terminal_failure(
                            method,
                            command,
                            outcome,
                            retained.deadline_ns
                            if retained is not None and retained.deadline_ns is not None
                            else 0,
                        )
                    except Exception:
                        pass
            return result.SerializeToString(deterministic=True)
        finally:
            if handler_returned and (
                method in {"Cleanup", "Shutdown"}
                or command.work.WhichOneof("work") is None
            ):
                try:
                    self._ledger.finalize_work(command.command_id, host_time_ns())
                except ValueError:
                    # A missing record leaves the payload reserved as a blocker.
                    pass
            # A completed or failed task is no longer a live executor. Incomplete
            # ledger records remain authoritative and can never trigger re-execution.
            self._inflight.pop(command.command_id, None)


def _work_key(command: wire.BackendCommand) -> str:
    work = command.work
    selected = work.WhichOneof("work")
    if selected == "session":
        return work.session.session_id
    if selected == "trial":
        return work.trial.trial_id
    return command.command_id


def _rejected(command_id: str, code: str, message: str) -> control.CommandAdmission:
    return control.CommandAdmission(
        result=control.COMMAND_RESULT_REJECTED,
        command_id=command_id,
        failure=control.Failure(code=code, message=message[:2048]),
    )
