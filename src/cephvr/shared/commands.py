"""Process-local, generation-scoped E08 command/result retention."""

from __future__ import annotations

from dataclasses import dataclass
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
    ) -> None:
        self.generation = require_uuid4(generation)
        self.retention_ns = require_int64_ns(retention_ns)
        if max_records <= 0 or max_bytes <= 0 or result_reservation_bytes <= 0:
            raise ValueError("record budgets must be positive")
        self.max_records = max_records
        self.max_bytes = max_bytes
        self.result_reservation_bytes = result_reservation_bytes
        self._records: dict[str, CommandRecord] = {}
        self._finalized_work: dict[str, int] = {}
        self._bytes = 0
        self._lock = RLock()

    def admit(
        self, command_id: str, canonical_request: bytes, now_ns: int, *, work_key: str
    ) -> Admission:
        """Return a retained retry or own a new command in the active work scope."""
        require_uuid4(command_id)
        require_uuid4(work_key)
        require_int64_ns(now_ns)
        if not isinstance(canonical_request, bytes) or not canonical_request:
            raise ValueError("canonical request must be nonempty immutable bytes")
        with self._lock:
            existing = self._records.get(command_id)
            if existing is not None:
                if (
                    existing.work_key != work_key
                    or existing.canonical_request != canonical_request
                ):
                    raise CommandConflict("command ID identifies a changed request")
                return Admission(existing, True)
            self._prune_locked(now_ns)
            if work_key in self._finalized_work:
                raise CommandConflict("new command targets finalized work")
            if len(self._records) >= self.max_records:
                raise CommandCapacityError("command record count budget exhausted")
            reserved = len(canonical_request) + self.result_reservation_bytes
            if self._bytes + reserved > self.max_bytes:
                raise CommandCapacityError("command record byte budget exhausted")
            record = CommandRecord(
                command_id,
                work_key,
                canonical_request,
                now_ns,
                result_reservation_bytes=self.result_reservation_bytes,
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
            updated = CommandRecord(
                old.command_id,
                old.work_key,
                old.canonical_request,
                old.accepted_ns,
                result,
                now_ns,
                max(now_ns, finalized_at)
                if (finalized_at := self._finalized_work.get(old.work_key)) is not None
                else old.finalized_ns,
                old.result_reservation_bytes,
            )
            self._records[command_id] = updated
            return updated

    def get(self, command_id: str) -> CommandRecord | None:
        require_uuid4(command_id)
        with self._lock:
            return self._records.get(command_id)

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
                    )

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
            if not any(
                retained.work_key == record.work_key
                for retained in self._records.values()
            ):
                self._finalized_work.pop(record.work_key, None)
        return len(expired)
