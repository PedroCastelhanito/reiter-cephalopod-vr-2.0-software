"""Command replay, capacity, finalization and retained-evidence windows."""

from __future__ import annotations

from uuid import uuid4

import pytest

from cephvr.shared.commands import CommandCapacityError, CommandConflict, CommandLedger


def _id() -> str:
    return str(uuid4())


def _ledger() -> CommandLedger:
    return CommandLedger(
        _id(), 10, max_records=8, max_bytes=1000, result_reservation_bytes=10
    )


def test_finalize_command_keeps_work_scope_open_and_prunes_after_retention() -> None:
    ledger, work, first, later = _ledger(), _id(), _id(), _id()
    ledger.admit(first, b"a", 0, work_key=work)
    ledger.complete(first, b"rejected", 1)
    ledger.finalize_command(first, 2)

    # The shared scope still accepts new commands.
    ledger.admit(later, b"b", 3, work_key=work)
    assert ledger.admit(first, b"a", 4, work_key=work).replayed
    assert ledger.prune(12) == 0
    assert ledger.prune(13) == 1
    assert ledger.get(first) is None
    assert ledger.get(later) is not None


def test_finalize_command_ignores_pending_and_does_not_restart_clock() -> None:
    ledger, work, pending, done = _ledger(), _id(), _id(), _id()
    ledger.admit(pending, b"a", 0, work_key=work)
    ledger.finalize_command(pending, 5)
    assert ledger.get(pending).finalized_ns is None  # type: ignore[union-attr]
    ledger.admit(done, b"b", 0, work_key=work)
    ledger.complete(done, b"r", 1)
    ledger.finalize_command(done, 2)
    ledger.finalize_command(done, 9)
    assert ledger.get(done).finalized_ns == 2  # type: ignore[union-attr]


def test_finalize_work_still_blocks_new_commands() -> None:
    ledger, work, first = _ledger(), _id(), _id()
    ledger.admit(first, b"a", 0, work_key=work)
    ledger.complete(first, b"r", 1)
    ledger.finalize_work(work, 2)
    with pytest.raises(CommandConflict, match="finalized work"):
        ledger.admit(_id(), b"b", 3, work_key=work)


def test_late_completion_after_scope_finalization_starts_its_own_window() -> None:
    ledger, work, pending = _ledger(), _id(), _id()
    done = _id()
    ledger.admit(done, b"a", 0, work_key=work)
    ledger.complete(done, b"r", 1)
    ledger.admit(pending, b"b", 0, work_key=work)
    ledger.finalize_work(work, 2)
    ledger.complete(pending, b"late", 20)
    assert ledger.get(pending).finalized_ns == 20  # type: ignore[union-attr]


def test_ledger_deduplicates_and_never_evicts_active() -> None:
    generation, command, other, work = _id(), _id(), _id(), _id()
    ledger = CommandLedger(
        generation, 300, max_records=1, max_bytes=100, result_reservation_bytes=20
    )
    assert not ledger.admit(command, b"exact request", 1, work_key=work).replayed
    assert ledger.admit(command, b"exact request", 2, work_key=work).replayed
    with pytest.raises(CommandConflict):
        ledger.admit(command, b"changed", 2, work_key=work)
    assert ledger.prune(10_000) == 0
    with pytest.raises(CommandCapacityError):
        ledger.admit(other, b"new", 10_000, work_key=work)
    ledger.complete(command, b"accepted completion", 20)
    ledger.finalize_work(work, 30)
    assert ledger.prune(330) == 0
    assert ledger.prune(331) == 1
    assert not ledger.admit(other, b"new", 332, work_key=_id()).replayed


def test_ledger_reserves_result_capacity_at_admission() -> None:
    ledger = CommandLedger(
        _id(), 1, max_records=2, max_bytes=10, result_reservation_bytes=8
    )
    ledger.admit(_id(), b"x", 0, work_key=_id())
    with pytest.raises(CommandCapacityError):
        ledger.admit(_id(), b"x", 0, work_key=_id())


def test_ledger_priority_admission_uses_only_reserved_safety_quota() -> None:
    ledger = CommandLedger(
        _id(),
        10,
        max_records=10,
        max_bytes=100,
        result_reservation_bytes=4,
        safety_reserve_records=2,
        safety_reserve_bytes=20,
    )
    for _ in range(8):
        ledger.admit(_id(), b"x", 1, work_key=_id())
    with pytest.raises(CommandCapacityError):
        ledger.admit(_id(), b"x", 1, work_key=_id())
    ledger.admit(_id(), b"x", 1, work_key=_id(), priority=True)
    ledger.admit(_id(), b"x", 1, work_key=_id(), priority=True)
    with pytest.raises(CommandCapacityError):
        ledger.admit(_id(), b"x", 1, work_key=_id(), priority=True)


def test_ledger_large_result_reservation_is_pinned_on_first_admission() -> None:
    ledger = CommandLedger(
        _id(), 10, max_records=2, max_bytes=100, result_reservation_bytes=10
    )
    command, work = _id(), _id()
    first = ledger.admit(
        command,
        b"large result command",
        1,
        work_key=work,
        result_reservation_bytes=60,
    )
    replay = ledger.admit(
        command,
        b"large result command",
        2,
        work_key=work,
        result_reservation_bytes=2,
    )
    assert replay.replayed
    assert (
        first.record.result_reservation_bytes
        == replay.record.result_reservation_bytes
        == 60
    )
    ledger.complete(command, b"x" * 60, 3)


def test_finalization_is_scoped_and_pending_result_is_preserved() -> None:
    first_work, second_work = _id(), _id()
    completed, pending, other = _id(), _id(), _id()
    ledger = CommandLedger(
        _id(), 10, max_records=3, max_bytes=60, result_reservation_bytes=10
    )
    ledger.admit(completed, b"a", 0, work_key=first_work)
    ledger.complete(completed, b"done", 1)
    ledger.admit(pending, b"b", 0, work_key=first_work)
    ledger.admit(other, b"c", 0, work_key=second_work)
    ledger.finalize_work(first_work, 2)
    assert ledger.prune(13) == 1
    assert ledger.get(pending) is not None
    assert ledger.get(other) is not None
    with pytest.raises(CommandConflict, match="finalized work"):
        ledger.admit(_id(), b"new", 14, work_key=first_work)
    ledger.complete(pending, b"late", 20)
    assert ledger.prune(30) == 0
    assert ledger.prune(31) == 1


def test_finalized_work_rejects_even_priority_commands() -> None:
    generation, work, original = _id(), _id(), _id()
    ledger = CommandLedger(
        generation,
        100,
        max_records=8,
        max_bytes=1000,
        result_reservation_bytes=50,
        safety_reserve_records=4,
        safety_reserve_bytes=200,
    )
    ledger.admit(original, b"setup", 1, work_key=work)
    ledger.complete(original, b"ready", 2)
    ledger.finalize_work(work, 10)
    with pytest.raises(CommandConflict, match="finalized work"):
        ledger.admit(_id(), b"ordinary", 20, work_key=work)

    with pytest.raises(CommandConflict, match="finalized work"):
        ledger.admit(_id(), b"cleanup", 20, work_key=work, priority=True)


def test_terminal_command_scope_uses_its_own_retention_window() -> None:
    generation, work, original, cleanup = _id(), _id(), _id(), _id()
    ledger = CommandLedger(
        generation,
        100,
        max_records=8,
        max_bytes=1000,
        result_reservation_bytes=50,
        safety_reserve_records=4,
        safety_reserve_bytes=200,
    )
    ledger.admit(original, b"setup", 1, work_key=work)
    ledger.complete(original, b"ready", 2)
    ledger.finalize_work(work, 10)

    admitted = ledger.admit(
        cleanup, b"Cleanup\0original-work", 20, work_key=cleanup, priority=True
    )
    assert admitted.record.finalized_ns is None
    ledger.complete(cleanup, b"closed", 21)
    ledger.finalize_work(cleanup, 22)

    assert ledger.prune(121) == 1
    assert ledger.get(cleanup) is not None
    assert ledger.prune(123) == 1
    assert ledger.get(cleanup) is None


def test_ledger_pins_original_deadline_through_replay_completion_and_finalization() -> (
    None
):
    command, work = _id(), _id()
    ledger = CommandLedger(
        _id(), 10, max_records=2, max_bytes=100, result_reservation_bytes=20
    )

    first = ledger.admit(command, b"same request", 5, work_key=work, deadline_ns=20)
    replay = ledger.admit(command, b"same request", 6, work_key=work, deadline_ns=90)
    assert replay.replayed
    assert replay.record.deadline_ns == first.record.deadline_ns == 20
    completed = ledger.complete(command, b"done", 10)
    assert completed.deadline_ns == 20
    ledger.finalize_work(work, 11)
    retained = ledger.get(command)
    assert retained is not None
    assert retained.deadline_ns == 20


def test_omitted_deadline_preserves_shared_command_ledger_behavior() -> None:
    ledger = CommandLedger(
        _id(), 10, max_records=2, max_bytes=100, result_reservation_bytes=20
    )
    record = ledger.admit(_id(), b"legacy caller", 5, work_key=_id()).record
    assert record.deadline_ns is None


def test_retained_evidence_uses_command_count_and_byte_budgets() -> None:
    command, work = _id(), _id()
    ledger = CommandLedger(
        _id(), 10, max_records=2, max_bytes=30, result_reservation_bytes=10
    )
    ledger.admit(command, b"x", 1, work_key=work)
    ledger.reserve_payload("ready:command-1", 5, work_key=work)
    assert ledger.retained_bytes == 16
    with pytest.raises(CommandCapacityError, match="count budget"):
        ledger.reserve_payload("started:command-1", 1, work_key=work)
    assert ledger.release_payload("ready:command-1") == 5
    assert ledger.remaining_bytes == 19


def test_retained_evidence_prunes_with_its_finalized_work() -> None:
    command, work = _id(), _id()
    ledger = CommandLedger(
        _id(), 10, max_records=3, max_bytes=100, result_reservation_bytes=10
    )
    ledger.admit(command, b"x", 1, work_key=work)
    ledger.complete(command, b"ok", 2)
    ledger.reserve_payload("ready:command-1", 20, work_key=work)
    ledger.finalize_work(work, 3)
    assert ledger.prune(13) == 0
    assert ledger.retained_bytes == 31
    assert ledger.prune(14) == 2
    assert ledger.retained_bytes == 0
