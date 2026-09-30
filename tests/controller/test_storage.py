from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.metadata.reservation import OutputReservation
from cephvr.controller.metadata.types import MetadataWrite as _MetadataWrite
from cephvr.controller.metadata.types import StorageError
from cephvr.controller.metadata.writer import MetadataWriter


def _write(
    command_id: str,
    path: Path,
    action: Literal["create_json", "replace_json", "append_jsonl_record"],
    payload_utf8: bytes,
    submitted_ns: int,
    deadline_ns: int,
) -> _MetadataWrite:
    document = json.loads(payload_utf8)
    session_id = document.get("session_id", "s")
    return _MetadataWrite(
        command_id=command_id,
        work=pb.WorkContext(
            session=pb.SessionContext(
                controller_generation="81d85f03-ac85-4d5e-885c-4754ee594540",
                session_id=session_id,
            )
        ),
        operation=pb.OperationContext(command_id=command_id),
        path=path,
        action=action,
        payload_utf8=payload_utf8,
        submitted_ns=submitted_ns,
        deadline_ns=deadline_ns,
    )


def _reservation(root: Path) -> OutputReservation:
    return OutputReservation(
        root,
        "experiment",
        "subject",
        "81d85f03-ac85-4d5e-885c-4754ee594540",
        "470b220b-6272-4fa3-8677-3957c29eea5f",
        datetime(2026, 9, 29, 13, 14, 15, tzinfo=UTC),
    )


def test_reservation_exclusive_and_cancel_removes_only_attempt_paths(
    tmp_path: Path,
) -> None:
    first = _reservation(tmp_path)
    assert first.acquire() == []
    second = _reservation(tmp_path)
    with pytest.raises(StorageError, match="locked"):
        second.acquire()
    first.cancel()
    assert not first.session_directory.exists()
    assert not first.experiment_directory.exists()


def test_unexpected_file_blocks_cancel_without_deletion(tmp_path: Path) -> None:
    reservation = _reservation(tmp_path)
    reservation.acquire()
    unexpected = reservation.protocol_directory / "owner-data.bin"
    unexpected.write_bytes(b"preserve")
    with pytest.raises(StorageError, match="unexpected files"):
        reservation.cancel()
    assert unexpected.read_bytes() == b"preserve"
    assert reservation.held
    reservation.release()


def test_preexisting_session_cancellation_never_unlinks_new_owners_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reservation = _reservation(tmp_path)
    reservation.protocol_directory.mkdir(parents=True)
    reservation.spikeglx_directory.mkdir()
    assert reservation.acquire() == []
    assert reservation._lock_created
    original_release = reservation.release

    def competing_owner() -> None:
        # The old lock has been renamed while still held. A new owner can create
        # the canonical name; the cancelled attempt must never unlink that file.
        assert not reservation.lock_path.exists()
        reservation.lock_path.write_bytes(b"new owner")
        original_release()

    monkeypatch.setattr(reservation, "release", competing_owner)
    reservation.cancel()
    assert reservation.lock_path.read_bytes() == b"new owner"


def test_existing_marker_inspection_requires_held_lock_and_keeps_recovery_evidence(
    tmp_path: Path,
) -> None:
    reservation = _reservation(tmp_path)
    with pytest.raises(StorageError, match="held"):
        reservation.inspect_marker()
    reservation.acquire()
    marker = reservation.inspect_marker()
    assert marker.session_id == reservation.session_id and not marker.complete
    reservation.release()
    again = _reservation(tmp_path)
    with pytest.raises(StorageError, match="requires recovery"):
        again.acquire()
    assert again.inspect_marker() == marker
    again.release()


def test_existing_lock_symlink_is_never_followed(tmp_path: Path) -> None:
    reservation = _reservation(tmp_path)
    reservation.session_directory.mkdir(parents=True)
    reservation.protocol_directory.mkdir()
    reservation.spikeglx_directory.mkdir()
    outside = tmp_path / "outside-lock"
    outside.write_bytes(b"preserve")
    try:
        reservation.lock_path.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable on this host")
    with pytest.raises(StorageError, match="regular"):
        reservation.acquire()
    assert outside.read_bytes() == b"preserve"


def test_failed_session_quarantine_preserves_unfinished_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    reservation = _reservation(tmp_path)
    reservation.acquire()
    original = os.replace

    def fail_session_rename(source: Path, destination: Path) -> None:
        if source == reservation.session_directory:
            raise OSError("busy directory")
        original(source, destination)

    monkeypatch.setattr(os, "replace", fail_session_rename)
    with pytest.raises(StorageError, match="unfinished marker retained"):
        reservation.cancel()
    assert reservation.inspect_marker().complete is False
    assert reservation.held
    reservation.release()


def test_corrupt_existing_marker_is_preserved_for_startup_recovery(
    tmp_path: Path,
) -> None:
    reservation = _reservation(tmp_path)
    reservation.acquire()
    reservation.marker.write_bytes(b"{corrupt")
    with pytest.raises(StorageError, match="corrupt"):
        reservation.inspect_marker()
    with pytest.raises(StorageError, match="corrupt"):
        reservation.cancel()
    assert reservation.marker.read_bytes() == b"{corrupt"
    reservation.release()


def test_writer_syncs_exact_json_and_rejects_changed_retry(tmp_path: Path) -> None:
    now = 1_000_000
    session_id = "81d85f03-ac85-4d5e-885c-4754ee594540"
    writer = MetadataWriter(
        tmp_path,
        max_operations=2,
        max_bytes=1024,
        clock=lambda: now,
        session_id=session_id,
    )
    path = tmp_path / "SESSION_CONFIG.json"
    payload = json.dumps({"schema_version": 1, "session_id": session_id}).encode()
    request = _write("op1", path, "create_json", payload, now, now + 1_000_000)
    first = writer.submit(request)
    assert writer.submit(request) is first
    assert first.result(3).state == "synced"
    assert json.loads(path.read_text())["session_id"] == session_id
    with pytest.raises(StorageError, match="reused"):
        writer.submit(
            _write(
                "op1",
                path,
                "create_json",
                json.dumps(
                    {"schema_version": 1, "session_id": session_id, "changed": True}
                ).encode(),
                now,
                now + 1_000_000,
            )
        )
    collision = writer.submit(
        _write("op2", path, "create_json", payload, now, now + 1_000_000)
    ).result(3)
    assert collision.state == "failed"
    assert json.loads(path.read_text())["session_id"] == session_id
    assert writer.seal(3)


def test_writer_rejects_unreserved_path_and_invalid_document(tmp_path: Path) -> None:
    writer = MetadataWriter(
        tmp_path, max_operations=1, max_bytes=32, clock=lambda: 1, session_id="s"
    )
    with pytest.raises(StorageError, match="destination"):
        writer.submit(
            _write("a", tmp_path / "arbitrary.json", "create_json", b"{}", 1, 100)
        )
    with pytest.raises(StorageError, match="schema"):
        writer.submit(
            _write("b", tmp_path / "SCHEMA.json", "create_json", b"{}", 1, 100)
        )
    assert writer.seal(3)


def test_writer_preserves_late_sync_evidence_and_seal_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cephvr.controller.metadata.writer as storage

    now = [1]
    entered = threading.Event()
    release = threading.Event()
    from cephvr.controller.metadata.files import atomic_json

    original = atomic_json

    def delayed(path: Path, payload: bytes, *, replace: bool) -> None:
        entered.set()
        assert release.wait(3)
        original(path, payload, replace=replace)

    monkeypatch.setattr(storage, "atomic_json", delayed)
    writer = MetadataWriter(
        tmp_path, max_operations=1, max_bytes=1024, clock=lambda: now[0], session_id="s"
    )
    work = writer.submit(
        _write(
            "one",
            tmp_path / "SESSION_CONFIG.json",
            "create_json",
            b'{"schema_version":1,"session_id":"s"}',
            1,
            2,
        )
    )
    assert entered.wait(3)
    now[0] = 3
    release.set()
    result = work.result(3)
    assert result.state == "synced" and not result.deadline_met
    assert writer.seal(3)


def test_cancelled_waiter_cannot_erase_required_writer_completion(
    tmp_path: Path,
) -> None:
    writer = MetadataWriter(
        tmp_path, max_operations=1, max_bytes=1024, clock=lambda: 1, session_id="s"
    )
    work = _write(
        "one",
        tmp_path / "SESSION_CONFIG.json",
        "create_json",
        b'{"schema_version":1,"session_id":"s"}',
        1,
        2,
    )
    retained = writer.submit(work)
    assert not retained.cancel()
    assert retained.result(3).state == "synced"
    assert writer.submit(work) is retained
    writer.retire("one")
    with pytest.raises(StorageError, match="not retained"):
        writer.retire("one")
    assert writer.seal(3)


def test_completed_id_is_not_evicted_by_next_admission_before_retirement(
    tmp_path: Path,
) -> None:
    writer = MetadataWriter(
        tmp_path, max_operations=1, max_bytes=1024, clock=lambda: 1, session_id="s"
    )
    first = _write(
        "first",
        tmp_path / "SESSION_CONFIG.json",
        "create_json",
        b'{"schema_version":1,"session_id":"s"}',
        1,
        2,
    )
    retained = writer.submit(first)
    assert retained.result(3).state == "synced"
    second = _write(
        "second",
        tmp_path / "SCHEMA.json",
        "create_json",
        b'{"schema_version":1,"session_id":"s"}',
        1,
        2,
    )
    assert writer.submit(second).result(3).state == "synced"
    assert writer.submit(first) is retained
    writer.retire("first")
    writer.retire("second")
    assert writer.seal(3)


def test_writer_never_appends_to_unowned_existing_log(tmp_path: Path) -> None:
    path = tmp_path / "SESSION_LOG.jsonl"
    path.write_bytes(b"preexisting\n")
    writer = MetadataWriter(
        tmp_path, max_operations=1, max_bytes=1024, clock=lambda: 1, session_id="s"
    )
    result = writer.submit(
        _write("one", path, "append_jsonl_record", b'{"event_type":"start"}', 1, 2)
    ).result(3)
    assert result.state == "failed"
    assert path.read_bytes() == b"preexisting\n"
    assert writer.seal(3)


def test_writer_binds_work_and_operation_to_exact_session(tmp_path: Path) -> None:
    writer = MetadataWriter(
        tmp_path, max_operations=1, max_bytes=1024, clock=lambda: 1, session_id="s"
    )
    request = _write(
        "one",
        tmp_path / "SESSION_CONFIG.json",
        "create_json",
        b'{"schema_version":1,"session_id":"s"}',
        1,
        2,
    )
    request.operation.command_id = "other"
    with pytest.raises(StorageError, match="operation/command"):
        writer.submit(request)
    request.operation.command_id = "one"
    request.work.session.session_id = "other"
    with pytest.raises(StorageError, match="work/session"):
        writer.submit(request)
    assert writer.seal(3)


def test_existing_reservation_recovery_requires_unchanged_marker(
    tmp_path: Path,
) -> None:
    original = _reservation(tmp_path)
    original.acquire()
    original.release()
    recovered = OutputReservation.open_existing(
        original.session_directory, original.session_id, original.generation
    )
    assert recovered.marker_issue is None
    fingerprint = recovered.marker_fingerprint()
    with pytest.raises(StorageError, match="changed"):
        recovered.finish_recovery("0" * 64)
    recovered.finish_recovery(fingerprint)
    assert recovered._lock_fd is None
    assert recovered.marker.exists()
    assert recovered.marker.read_text().find('"complete":true') > 0


def test_recovery_log_adoption_requires_exact_held_file_identity(
    tmp_path: Path,
) -> None:
    reservation = _reservation(tmp_path)
    reservation.acquire()
    log = reservation.protocol_directory / "SESSION_LOG.jsonl"
    log.write_bytes(b'{"event_type":"prior"}\n')
    info = log.stat()
    writer = MetadataWriter(
        reservation.protocol_directory,
        max_operations=1,
        max_bytes=1024,
        clock=lambda: 1,
        session_id=reservation.session_id,
    )
    with pytest.raises(StorageError, match="changed"):
        writer.adopt_recovery_log(
            reservation,
            expected_dev=info.st_dev,
            expected_ino=info.st_ino,
            expected_size=info.st_size + 1,
        )
    writer.adopt_recovery_log(
        reservation,
        expected_dev=info.st_dev,
        expected_ino=info.st_ino,
        expected_size=info.st_size,
    )
    writer.reserve_recovery_report(f"RECOVERY-{uuid.uuid4()}.json")
    request = _MetadataWrite(
        command_id="recovery-append",
        work=pb.WorkContext(
            session=pb.SessionContext(
                controller_generation=reservation.generation,
                session_id=reservation.session_id,
            )
        ),
        operation=pb.OperationContext(command_id="recovery-append"),
        path=log,
        action="append_jsonl_record",
        payload_utf8=b'{"event_type":"recovery"}',
        submitted_ns=1,
        deadline_ns=2,
    )
    assert writer.submit(request).result(3).state == "synced"
    assert log.read_bytes().endswith(b'{"event_type":"recovery"}\n')
    assert writer.seal(3)
    reservation.release()


def test_owned_log_path_replacement_cannot_redirect_append(tmp_path: Path) -> None:
    path = tmp_path / "SESSION_LOG.jsonl"
    outside = tmp_path / "outside.jsonl"
    outside.write_bytes(b"preserve\n")
    writer = MetadataWriter(
        tmp_path, max_operations=2, max_bytes=1024, clock=lambda: 1, session_id="s"
    )
    first = _write("one", path, "append_jsonl_record", b'{"event_type":"first"}', 1, 2)
    assert writer.submit(first).result(3).state == "synced"
    path.rename(tmp_path / "moved.jsonl")
    try:
        path.symlink_to(outside)
    except OSError as exc:
        assert writer.seal(3)
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows account lacks symlink creation privilege")
        raise
    completion = writer.submit(
        _write("two", path, "append_jsonl_record", b'{"event_type":"second"}', 1, 2)
    ).result(3)
    assert completion.state == "failed"
    assert outside.read_bytes() == b"preserve\n"
    assert writer.seal(3)
