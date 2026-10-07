"""Process-local, generation-scoped E08 command/result retention."""

from __future__ import annotations

from dataclasses import dataclass, replace
from threading import RLock

from cephvr.shared.clock import require_int64_ns
from cephvr.shared.identity import require_uuid4


class CommandConflict(ValueError):
    """A command ID was reused with a different canonical request."""


class CommandCapacityError(RuntimeError):
    """Admission would exceed the process's retained-record budget."""


@dataclass(frozen=True)
class CommandRecord:
    command_id: str
    work_key: str
    canonical_request: bytes
    accepted_ns: int
    result: bytes | None = None
    completed_ns: int | None = None
    finalized_ns: int | None = None
    result_reservation_bytes: int = 0
    deadline_ns: int | None = None
    priority: bool = False
    executor_result: bytes | None = None


@dataclass(frozen=True)
class Admission:
    record: CommandRecord
    replayed: bool


class CommandLedger:
    """The owning process keeps this volatile cache; no cross-process sharing."""

    def __init__(
        self,
        generation: str,
        retention_ns: int,
        *,
        max_records: int,
        max_bytes: int,
        result_reservation_bytes: int,
        safety_reserve_records: int = 0,
        safety_reserve_bytes: int = 0,
    ) -> None:
        self.generation = require_uuid4(generation)
        self.retention_ns = require_int64_ns(retention_ns)
        if max_records <= 0 or max_bytes <= 0 or result_reservation_bytes <= 0:
            raise ValueError("record budgets must be positive")
        if (
            safety_reserve_records < 0
            or safety_reserve_bytes < 0
            or safety_reserve_records >= max_records
            or safety_reserve_bytes >= max_bytes
        ):
            raise ValueError("safety reservations must be nonnegative and below limits")
        self.max_records = max_records
        self.max_bytes = max_bytes
        self.result_reservation_bytes = result_reservation_bytes
        self.safety_reserve_records = safety_reserve_records
        self.safety_reserve_bytes = safety_reserve_bytes
        self._records: dict[str, CommandRecord] = {}
        self._finalized_work: dict[str, int] = {}
        self._payloads: dict[str, tuple[str, int, bool]] = {}
        self._bytes = 0
        self._lock = RLock()

    def admit(
        self,
        command_id: str,
        canonical_request: bytes,
        now_ns: int,
        *,
        work_key: str,
        deadline_ns: int | None = None,
        result_reservation_bytes: int | None = None,
        priority: bool = False,
    ) -> Admission:
        """Return a retained retry or own a new command in the active work scope."""
        require_uuid4(command_id)
        require_uuid4(work_key)
        require_int64_ns(now_ns)
        if deadline_ns is not None:
            require_int64_ns(deadline_ns)
            if deadline_ns <= 0:
                raise ValueError(
                    "command deadline must be a positive absolute timestamp"
                )
        if not isinstance(canonical_request, bytes) or not canonical_request:
            raise ValueError("canonical request must be nonempty immutable bytes")
        with self._lock:
            self._prune_locked(now_ns)
            existing = self._records.get(command_id)
            if existing is not None:
                if (
                    existing.work_key != work_key
                    or existing.canonical_request != canonical_request
                ):
                    raise CommandConflict("command ID identifies a changed request")
                return Admission(existing, True)
            if deadline_ns is not None and deadline_ns <= now_ns:
                raise ValueError("new command deadline has already expired")
            if work_key in self._finalized_work:
                raise CommandConflict("new command targets finalized work")
            record_limit = (
                self.max_records
                if priority
                else (self.max_records - self.safety_reserve_records)
            )
            if len(self._records) + len(self._payloads) >= record_limit:
                raise CommandCapacityError("command record count budget exhausted")
            result_reservation = (
                self.result_reservation_bytes
                if result_reservation_bytes is None
                else result_reservation_bytes
            )
            if result_reservation <= 0:
                raise ValueError("command result reservation must be positive")
            reserved = len(canonical_request) + result_reservation
            byte_limit = (
                self.max_bytes
                if priority
                else (self.max_bytes - self.safety_reserve_bytes)
            )
            if self._bytes + reserved > byte_limit:
                raise CommandCapacityError("command record byte budget exhausted")
            record = CommandRecord(
                command_id,
                work_key,
                canonical_request,
                now_ns,
                result_reservation_bytes=result_reservation,
                deadline_ns=deadline_ns,
                priority=priority,
            )
            self._records[command_id] = record
            self._bytes += reserved
            return Admission(record, False)

    def complete(self, command_id: str, result: bytes, now_ns: int) -> CommandRecord:
        """Retain the exact completion; a late conflicting result is an error."""
        require_uuid4(command_id)
        require_int64_ns(now_ns)
        if not isinstance(result, bytes):
            raise ValueError("result must be immutable bytes")
        with self._lock:
            old = self._records[command_id]
            if old.result is not None:
                if old.result != result:
                    raise CommandConflict("completed command result changed")
                return old
            if now_ns < old.accepted_ns:
                raise ValueError("completion predates admission")
            if len(result) > old.result_reservation_bytes:
                raise CommandCapacityError("result exceeds its admission reservation")
            updated = replace(
                old,
                result=result,
                completed_ns=now_ns,
                # A result arriving after its scope was retired starts its own window.
                finalized_ns=(
                    now_ns if old.work_key in self._finalized_work else old.finalized_ns
                ),
            )
            self._records[command_id] = updated
            return updated

    def get(self, command_id: str) -> CommandRecord | None:
        require_uuid4(command_id)
        with self._lock:
            return self._records.get(command_id)

    def has_retained_work(self, work_key: str) -> bool:
        """Whether any command or payload still retains one exact work scope."""
        require_uuid4(work_key)
        with self._lock:
            return any(
                record.work_key == work_key for record in self._records.values()
            ) or any(
                payload_work == work_key
                for payload_work, _size, _priority in self._payloads.values()
            )

    def complete_executor(
        self, command_id: str, result: bytes, now_ns: int
    ) -> CommandRecord:
        """Retain terminal executor outcome without changing admission receipt."""
        require_uuid4(command_id)
        require_int64_ns(now_ns)
        if not isinstance(result, bytes) or not result:
            raise ValueError("executor result must be nonempty immutable bytes")
        with self._lock:
            old = self._records[command_id]
            if old.executor_result is not None:
                if old.executor_result != result:
                    raise CommandConflict("executor result changed after completion")
                return old
            retained_result_size = len(old.result or b"")
            if retained_result_size + len(result) > old.result_reservation_bytes:
                raise CommandCapacityError(
                    "executor result exceeds its admission reservation"
                )
            updated = replace(old, executor_result=result)
            self._records[command_id] = updated
            return updated

    @property
    def retained_bytes(self) -> int:
        """Bytes reserved by commands and their retained payload evidence."""
        with self._lock:
            return self._bytes

    @property
    def remaining_bytes(self) -> int:
        with self._lock:
            return self.max_bytes - self._bytes

    def reserve_payload(
        self, key: str, size: int, *, work_key: str, priority: bool = False
    ) -> None:
        """Reserve evidence in the same count and byte budget as commands."""
        require_uuid4(work_key)
        if not key or "\x00" in key or size <= 0:
            raise ValueError("payload key and positive byte size are required")
        with self._lock:
            prior = self._payloads.get(key)
            if prior is not None and (prior[0] != work_key or prior[2] != priority):
                raise CommandConflict("retained payload key changed scope or priority")
            prior_size = prior[1] if prior is not None else 0
            record_limit = (
                self.max_records
                if priority
                else self.max_records - self.safety_reserve_records
            )
            if (
                prior is None
                and len(self._records) + len(self._payloads) >= record_limit
            ):
                raise CommandCapacityError("retained payload count budget exhausted")
            byte_limit = (
                self.max_bytes
                if priority
                else self.max_bytes - self.safety_reserve_bytes
            )
            if self._bytes - prior_size + size > byte_limit:
                raise CommandCapacityError("retained payload byte budget exhausted")
            self._payloads[key] = (work_key, size, priority)
            self._bytes += size - prior_size

    def has_payload(self, key: str) -> bool:
        """Whether an exact retained evidence reservation remains live."""
        with self._lock:
            return key in self._payloads

    def release_payload(self, key: str) -> int:
        """Release one exact evidence reservation after its retention window."""
        with self._lock:
            prior = self._payloads.pop(key, None)
            if prior is None:
                return 0
            self._bytes -= prior[1]
            return prior[1]

    def transfer_payload(
        self,
        old_key: str,
        new_key: str,
        size: int,
        *,
        work_key: str,
        priority: bool,
    ) -> None:
        """Atomically move reserved evidence to its terminal command scope."""
        require_uuid4(work_key)
        if not old_key or not new_key or size <= 0:
            raise ValueError("payload keys and positive byte size are required")
        with self._lock:
            old = self._payloads.get(old_key)
            if old is None:
                raise KeyError(old_key)
            if new_key != old_key and new_key in self._payloads:
                raise CommandConflict("payload transfer destination is already used")
            if new_key == old_key and (old[0] != work_key or old[2] != priority):
                raise CommandConflict("payload transfer changes its owning scope")
            byte_limit = (
                self.max_bytes
                if priority
                else self.max_bytes - self.safety_reserve_bytes
            )
            if self._bytes - old[1] + size > byte_limit:
                raise CommandCapacityError("retained payload byte budget exhausted")
            self._payloads.pop(old_key)
            self._payloads[new_key] = (work_key, size, priority)
            self._bytes += size - old[1]

    def finalize_work(self, work_key: str, now_ns: int) -> None:
        """Retire one confirmed work scope, preserving other/unfinished records."""
        require_uuid4(work_key)
        require_int64_ns(now_ns)
        with self._lock:
            matching = [
                key for key, old in self._records.items() if old.work_key == work_key
            ]
            if not matching:
                raise ValueError("work scope has no retained commands")
            prior = self._finalized_work.setdefault(work_key, now_ns)
            if prior != now_ns:
                now_ns = prior
            for key in matching:
                old = self._records[key]
                if old.finalized_ns is None and old.completed_ns is not None:
                    self._records[key] = CommandRecord(
                        old.command_id,
                        old.work_key,
                        old.canonical_request,
                        old.accepted_ns,
                        old.result,
                        old.completed_ns,
                        now_ns,
                        old.result_reservation_bytes,
                        old.deadline_ns,
                        old.priority,
                        old.executor_result,
                    )

    def finalize_command(self, command_id: str, now_ns: int) -> None:
        """Start retention for one completed record without retiring its work scope."""
        require_uuid4(command_id)
        require_int64_ns(now_ns)
        with self._lock:
            old = self._records[command_id]
            if old.finalized_ns is None and old.completed_ns is not None:
                self._records[command_id] = replace(old, finalized_ns=now_ns)

    def prune(self, now_ns: int) -> int:
        require_int64_ns(now_ns)
        with self._lock:
            return self._prune_locked(now_ns)

    def _prune_locked(self, now_ns: int) -> int:
        expired = [
            key
            for key, record in self._records.items()
            if record.finalized_ns is not None
            and record.completed_ns is not None
            and now_ns > record.finalized_ns + self.retention_ns
        ]
        for key in expired:
            record = self._records.pop(key)
            self._bytes -= (
                len(record.canonical_request) + record.result_reservation_bytes
            )
        expired_payloads = [
            key
            for key, (work_key, _, _) in self._payloads.items()
            if work_key in self._finalized_work
            and now_ns > self._finalized_work[work_key] + self.retention_ns
        ]
        for key in expired_payloads:
            _, size, _ = self._payloads.pop(key)
            self._bytes -= size
        for work_key in tuple(self._finalized_work):
            if not any(
                retained.work_key == work_key for retained in self._records.values()
            ) and not any(
                payload_work == work_key
                for payload_work, _, _ in self._payloads.values()
            ):
                self._finalized_work.pop(work_key, None)
        return len(expired) + len(expired_payloads)
