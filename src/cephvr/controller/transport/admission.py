"""Bounded command replay and owned execution for the controller RPC front door."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol

from google.protobuf.message import Message

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.receipts import rejected_admission
from cephvr.shared.commands import CommandCapacityError, CommandConflict, CommandLedger


class CommandWorkView(Protocol):
    generation: str
    clock: Callable[[], int]

    def current_work_key(self) -> str | None: ...

    def command_work_complete(self, key: str) -> bool: ...

    def clean_work_retired(self) -> bool: ...


class CommandAdmissionGate:
    """Retain canonical requests across disconnects in three bounded lanes."""

    def __init__(
        self,
        work: CommandWorkView,
        *,
        max_pending_events: int,
        max_pending_payload_bytes: int,
        command_retention_ns: int,
    ) -> None:
        self._work = work
        self._ledger = CommandLedger(
            work.generation,
            command_retention_ns,
            max_records=max_pending_events,
            max_bytes=max_pending_payload_bytes,
            result_reservation_bytes=4096,
        )
        self._abort_ledger = self._safety_ledger(work, command_retention_ns)
        self._shutdown_ledger = self._safety_ledger(work, command_retention_ns)
        self._ledgers = (self._ledger, self._abort_ledger, self._shutdown_ledger)
        self._pending: dict[str, asyncio.Future[pb.CommandAdmission]] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._closed = False
        self._disposed = False
        self._setup_work_key: str | None = None
        self._session_work_key: str | None = None
        self._camera_work_keys: set[str] = set()
        self._housekeeping = asyncio.create_task(self._housekeep())

    @staticmethod
    def _safety_ledger(
        work: CommandWorkView, command_retention_ns: int
    ) -> CommandLedger:
        return CommandLedger(
            work.generation,
            command_retention_ns,
            max_records=8,
            max_bytes=65_536,
            result_reservation_bytes=4096,
        )

    def fresh(self, name: str, command_id: str) -> bool:
        """Check the matching safety lane before its first precondition check."""
        return self._lane(name).get(command_id) is None

    @property
    def retention_ledger(self) -> CommandLedger:
        """Shared ledger for bounded secondary evidence owned by admitted commands."""
        return self._ledger

    def stop_accepting(self) -> None:
        self._closed = True

    def _lane(self, name: str) -> CommandLedger:
        if name == "AbortNow":
            return self._abort_ledger
        if name == "ShutdownApplication":
            return self._shutdown_ledger
        return self._ledger

    async def _housekeep(self) -> None:
        while True:
            await asyncio.sleep(1)
            self._retire_clean_work()
            for key in tuple(self._camera_work_keys):
                if self._work.command_work_complete(key):
                    self._ledger.finalize_work(key, self._work.clock())
                    self._camera_work_keys.discard(key)
            for ledger in self._ledgers:
                ledger.prune(self._work.clock())

    def _retire_clean_work(self) -> None:
        if not self._work.clean_work_retired():
            return
        for key in (self._setup_work_key, self._session_work_key):
            if key is not None:
                for ledger in self._ledgers:
                    try:
                        ledger.finalize_work(key, self._work.clock())
                    except ValueError:
                        pass
        self._setup_work_key = None
        self._session_work_key = None

    async def admit(
        self,
        name: str,
        command_id: str,
        request: Message,
        action: Callable[[], Awaitable[pb.CommandAdmission]],
    ) -> pb.CommandAdmission:
        if self._closed:
            return rejected_admission(
                command_id, "SHUTDOWN", "controller service is closing"
            )
        canonical = (
            name.encode() + b"\0" + request.SerializeToString(deterministic=True)
        )
        ledger = self._lane(name)
        other_ledgers = tuple(other for other in self._ledgers if other is not ledger)
        synchronous = name in {
            "AcquireControl",
            "TakeOverControl",
            "ReleaseControl",
            "UpdateConfiguration",
            "RespondToPrompt",
            "SaveConfigurationHistory",
            "NewSession",
        }
        current_work = self._work.current_work_key()
        work_key = (
            command_id
            if synchronous
            or name in {"Setup", "ExecuteCameraCommand"}
            or current_work is None
            else current_work
        )
        try:
            if any(other.get(command_id) is not None for other in other_ledgers):
                raise CommandConflict(
                    "command ID already belongs to another admission lane"
                )
            admission = ledger.admit(
                command_id, canonical, self._work.clock(), work_key=work_key
            )
        except (ValueError, CommandConflict, CommandCapacityError) as exc:
            return rejected_admission(command_id, "ADMISSION", str(exc))
        if admission.replayed:
            if admission.record.result is not None:
                return pb.CommandAdmission.FromString(admission.record.result)
            pending = self._pending.get(command_id)
            if pending is not None:
                return await asyncio.shield(pending)
            return rejected_admission(
                command_id, "PENDING", "matching command admission is pending"
            )
        future: asyncio.Future[pb.CommandAdmission] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[command_id] = future
        task = asyncio.create_task(
            self._execute(
                ledger, name, command_id, work_key, synchronous, action, future
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return await asyncio.shield(future)

    async def _execute(
        self,
        ledger: CommandLedger,
        name: str,
        command_id: str,
        work_key: str,
        synchronous: bool,
        action: Callable[[], Awaitable[pb.CommandAdmission]],
        future: asyncio.Future[pb.CommandAdmission],
    ) -> None:
        try:
            result = await action()
            ledger.complete(
                command_id,
                result.SerializeToString(deterministic=True),
                self._work.clock(),
            )
            if synchronous:
                ledger.finalize_work(work_key, self._work.clock())
            elif result.result == pb.COMMAND_RESULT_REJECTED:
                # A rejection retires only its own record; the shared session
                # scope stays open for later commands (incl. AbortNow).
                ledger.finalize_command(command_id, self._work.clock())
            elif name == "Setup":
                self._setup_work_key = work_key
                current_work = self._work.current_work_key()
                if current_work is not None:
                    self._session_work_key = current_work
            elif name == "ExecuteCameraCommand":
                self._camera_work_keys.add(work_key)
            else:
                current_work = self._work.current_work_key()
                if current_work is not None:
                    self._session_work_key = current_work
            if name == "NewSession" and result.result == pb.COMMAND_RESULT_ACCEPTED:
                self._retire_clean_work()
            if not future.done():
                future.set_result(result)
        except asyncio.CancelledError:
            result = rejected_admission(
                command_id,
                "SHUTDOWN",
                "controller service closed before admission completed",
            )
            self._fail_admission(
                ledger, command_id, work_key, synchronous, future, result
            )
            raise
        except Exception as exc:
            result = rejected_admission(command_id, "INTERNAL", str(exc))
            self._fail_admission(
                ledger, command_id, work_key, synchronous, future, result
            )
        finally:
            self._pending.pop(command_id, None)

    def _fail_admission(
        self,
        ledger: CommandLedger,
        command_id: str,
        work_key: str,
        synchronous: bool,
        future: asyncio.Future[pb.CommandAdmission],
        result: pb.CommandAdmission,
    ) -> None:
        ledger.complete(
            command_id,
            result.SerializeToString(deterministic=True),
            self._work.clock(),
        )
        self._finalize_failed(ledger, command_id, work_key, synchronous)
        if not future.done():
            future.set_result(result)

    def _finalize_failed(
        self, ledger: CommandLedger, command_id: str, work_key: str, synchronous: bool
    ) -> None:
        if synchronous or work_key == command_id:
            ledger.finalize_work(work_key, self._work.clock())
        else:
            ledger.finalize_command(command_id, self._work.clock())

    async def aclose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        self._closed = True
        tasks = (self._housekeeping, *tuple(self._tasks))
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for pending in self._pending.values():
            if not pending.done():
                pending.set_result(
                    pb.CommandAdmission(
                        result=pb.COMMAND_RESULT_REJECTED,
                        failure=pb.Failure(
                            code="SHUTDOWN", message="controller service closed"
                        ),
                    )
                )
