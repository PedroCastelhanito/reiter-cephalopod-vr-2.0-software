"""E04 startup repair, original evidence and exact prior-exit proof."""

from __future__ import annotations

import json
import os
import sys
import uuid
from concurrent.futures import Future
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.metadata.reservation import OutputReservation
from cephvr.controller.metadata.types import MetadataCompletion, StorageError
from cephvr.controller.metadata.writer import MetadataWriter
from cephvr.controller.recovery import StartupRecovery
from cephvr.controller.recovery_inspection import inspect_recovery, read_recovery_file
from cephvr.controller.startup.recovery import prepare_recovery
from cephvr.shared.recovery import RecoveryStore, UnfinishedSessionPointer
from tests.controller.support_components import _runtime


def _recovery() -> StartupRecovery:
    return StartupRecovery(
        None,  # type: ignore[arg-type]
        current_generation=_id(),
        timeout_ns=2_000_000_000,
        max_operations=8,
        max_bytes=65_536,
    )


def _inspect(tmp_path: Path, log: bytes):  # type: ignore[no-untyped-def]
    store, pointer, _ = _fixture(tmp_path, log)
    reservation = OutputReservation.open_existing(
        Path(pointer.session_directory),
        pointer.session_id,
        pointer.controller_generation,
    )
    try:
        return inspect_recovery(reservation, 65_536)
    finally:
        reservation.release()


def test_torn_final_line_keeps_endpoint_and_run(tmp_path: Path) -> None:
    result = _inspect(tmp_path, _event("session_started") + b'{"event_type":"tri')
    assert result.log_identity is None
    assert result.spikeglx_stop_unconfirmed
    assert result.spikeglx_endpoint == ("192.0.2.10", 4142)
    assert result.spikeglx_run == "known-run"


def test_null_details_do_not_break_inspection(tmp_path: Path) -> None:
    log = _event("session_started") + _event("spikeglx_stopped", details=None)
    result = _inspect(tmp_path, log)
    assert result.log_identity is not None
    assert result.spikeglx_stop_unconfirmed


def test_stop_for_another_run_does_not_confirm_stop(tmp_path: Path) -> None:
    other = _event("session_started") + _event(
        "spikeglx_stopped", details={"run_name": "other-run"}
    )
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    assert _inspect(tmp_path / "a", other).spikeglx_stop_unconfirmed
    exact = _event("session_started") + _event(
        "spikeglx_stopped", details={"run_name": "known-run"}
    )
    assert not _inspect(tmp_path / "b", exact).spikeglx_stop_unconfirmed


async def _prepare(
    tmp_path: Path, pointer: UnfinishedSessionPointer, store: RecoveryStore
) -> StartupRecovery:
    recovery = StartupRecovery(
        store,
        current_generation=_id(),
        timeout_ns=2_000_000_000,
        max_operations=8,
        max_bytes=65_536,
    )

    async def query(_: str) -> svc.RecoverySnapshot:
        return _snapshot(pointer)

    assert await recovery.prepare(query) is None
    return recovery


def _pointer(
    tmp_path: Path,
) -> tuple[RecoveryStore, OutputReservation, UnfinishedSessionPointer]:
    reservation = OutputReservation(
        tmp_path,
        "experiment",
        "subject",
        _id(),
        _id(),
        datetime(2026, 9, 29, 0, 0, tzinfo=UTC),
    )
    reservation.acquire()
    pointer = UnfinishedSessionPointer(
        str(reservation.session_directory),
        reservation.session_id,
        reservation.generation,
        _id(),
    )
    store = RecoveryStore(tmp_path / "runtime")
    store.write_pointer(pointer)
    return store, reservation, pointer


async def test_pointer_to_missing_namespace_is_cleared_with_notice(
    tmp_path: Path,
) -> None:
    store, reservation, pointer = _pointer(tmp_path)
    reservation.cancel()
    assert store.read_pointer() == pointer
    recovery = await _prepare(tmp_path, pointer, store)
    assert store.read_pointer() is None
    assert recovery.notice == "cancelled Setup cleanup completed at recovery"


async def test_leftover_quarantine_without_marker_is_removed(tmp_path: Path) -> None:
    store, reservation, pointer = _pointer(tmp_path)
    session = reservation.session_directory
    reservation.protocol_directory.rmdir()
    reservation.spikeglx_directory.rmdir()
    reservation.marker.unlink()
    reservation.release()
    quarantine = session.with_name(f".{session.name}.{uuid.uuid4()}.cleanup")
    session.rename(quarantine)
    recovery = await _prepare(tmp_path, pointer, store)
    assert store.read_pointer() is None
    assert not quarantine.exists()
    assert recovery.notice


async def test_quarantine_with_marker_keeps_strict_blocking(tmp_path: Path) -> None:
    store, reservation, pointer = _pointer(tmp_path)
    session = reservation.session_directory
    reservation.protocol_directory.rmdir()
    reservation.spikeglx_directory.rmdir()
    reservation.release()
    quarantine = session.with_name(f".{session.name}.{uuid.uuid4()}.cleanup")
    session.rename(quarantine)
    recovery = StartupRecovery(
        store,
        current_generation=_id(),
        timeout_ns=2_000_000_000,
        max_operations=8,
        max_bytes=65_536,
    )

    async def query(_: str) -> svc.RecoverySnapshot:
        return _snapshot(pointer)

    with pytest.raises((StorageError, OSError)):
        await recovery.prepare(query)
    assert store.read_pointer() == pointer
    assert quarantine.exists()


async def test_pointer_with_not_activated_marker_is_cleared_without_report(
    tmp_path: Path,
) -> None:
    store, reservation, pointer = _pointer(tmp_path)
    (reservation.protocol_directory / "SESSION_CONFIG.json").write_text("{}")
    reservation.close_unactivated()
    recovery = await _prepare(tmp_path, pointer, store)
    assert store.read_pointer() is None
    assert recovery.notice is None
    assert not list(reservation.protocol_directory.glob("RECOVERY-*"))
    assert json.loads(reservation.marker.read_text())["outcome"] == "not_activated"


class _SettledRecovery:
    """A recovery that settled a cancelled namespace without needing a prompt."""

    inspection = None
    notice = "cancelled Setup cleanup completed at recovery"

    async def prepare(self, query: object) -> None:
        return None

    async def recover(self) -> None:
        raise AssertionError("no recovery handler is installed without a prompt")


async def test_settled_recovery_notice_reaches_operator_warnings(
    tmp_path: Path,
) -> None:
    runtime = _runtime(
        tmp_path,
        pb.BackendContext(backend_name="acquisition", backend_generation=_id()),
    )
    await prepare_recovery(
        _SettledRecovery(),  # type: ignore[arg-type]
        stub=None,  # type: ignore[arg-type]
        principal=None,  # type: ignore[arg-type]
        supervisor_generation=_id(),
        install=runtime.install_startup_recovery,
    )
    assert not runtime.lifecycle.startup_blocker
    assert [
        w.message for w in runtime.control.warnings if w.component == "recovery"
    ] == ["cancelled Setup cleanup completed at recovery"]


def _id() -> str:
    return str(uuid.uuid4())


def _event(kind: str, **extra: object) -> bytes:
    event: dict[str, object] = {
        "monotonic_ns": 100,
        "wall_time": "2026-09-29T00:00:00+00:00",
        "event_type": kind,
        "source": "controller",
        **extra,
    }
    return json.dumps(event, separators=(",", ":")).encode() + b"\n"


def _fixture(
    tmp_path: Path, log: bytes
) -> tuple[RecoveryStore, UnfinishedSessionPointer, Path]:
    session = _id()
    controller = _id()
    supervisor = _id()
    reservation = OutputReservation(
        tmp_path,
        "experiment",
        "subject",
        session,
        controller,
        datetime(2026, 9, 29, 0, 0, tzinfo=UTC),
    )
    reservation.acquire()
    config = {
        "schema_version": 1,
        "session_id": session,
        "controller_generation": controller,
        "local_timezone": "UTC",
        "trials": [{"context": {"trial_number": 1}}],
        "configuration": {
            "backends": [{"backend_name": "synchronization", "enabled": True}]
        },
        "spikeglx": {
            "run_name": "known-run",
            "address": "192.0.2.10",
            "port": 4142,
        },
    }
    (reservation.protocol_directory / "SESSION_CONFIG.json").write_text(
        json.dumps(config)
    )
    (reservation.protocol_directory / "SESSION_LOG.jsonl").write_bytes(log)
    reservation.release()
    pointer = UnfinishedSessionPointer(
        str(reservation.session_directory), session, controller, supervisor
    )
    store = RecoveryStore(tmp_path / "runtime")
    store.write_pointer(pointer)
    return store, pointer, reservation.protocol_directory / "SESSION_LOG.jsonl"


def _snapshot(
    pointer: UnfinishedSessionPointer, *, valid: bool = True
) -> svc.RecoverySnapshot:
    return svc.RecoverySnapshot(
        prior_application_exit=svc.PriorApplicationExitReceipt(
            controller_generation=pointer.controller_generation,
            supervisor_generation=(pointer.supervisor_generation if valid else _id()),
            observed_monotonic_ns=100,
            all_owned_processes_absent=True,
            format_version=1,
        )
    )


async def test_wrong_prior_generation_proof_blocks_before_opening_files(
    tmp_path: Path,
) -> None:
    log = _event("session_started")
    store, pointer, path = _fixture(tmp_path, log)
    recovery = StartupRecovery(
        store,
        current_generation=_id(),
        timeout_ns=1_000_000_000,
        max_operations=8,
        max_bytes=65_536,
    )

    async def query(generation: str) -> svc.RecoverySnapshot:
        assert generation == pointer.controller_generation
        return _snapshot(pointer, valid=False)

    with pytest.raises(StorageError, match="process absence is unconfirmed"):
        await recovery.prepare(query)
    assert path.read_bytes() == log
    assert store.read_pointer() == pointer
    assert recovery.reservation is None


async def test_intact_log_appends_only_observation_labeled_terminal_events(
    tmp_path: Path,
) -> None:
    log = _event("session_started") + _event("trial_started", trial_number=1)
    store, pointer, path = _fixture(tmp_path, log)
    recovery = StartupRecovery(
        store,
        current_generation=_id(),
        timeout_ns=2_000_000_000,
        max_operations=8,
        max_bytes=65_536,
    )

    async def query(_: str) -> svc.RecoverySnapshot:
        return _snapshot(pointer)

    prompt = await recovery.prepare(query)
    assert prompt is not None
    assert "192.0.2.10:4142" in prompt.explanation
    assert "known-run" in prompt.explanation
    assert recovery.inspection is not None
    assert recovery.inspection.spikeglx_stop_unconfirmed
    assert recovery.inspection.spikeglx_endpoint == ("192.0.2.10", 4142)
    await recovery.recover()
    events = [json.loads(line) for line in path.read_bytes().splitlines()]
    assert [item["event_type"] for item in events[-3:]] == [
        "trial_finished",
        "session_ended",
        "recovery",
    ]
    assert events[-3]["details"]["actual_end_monotonic_ns"] is None
    assert events[-3]["details"]["event_clock"] == "current_recovery_application"
    assert events[-2]["details"]["end_observed_during_recovery"] is True
    assert store.read_pointer() is None
    recovery.close()


async def test_incomplete_jsonl_is_preserved_and_reported_separately(
    tmp_path: Path,
) -> None:
    log = _event("session_started") + b'{"event_type":"trial_started"'
    store, pointer, path = _fixture(tmp_path, log)
    recovery = StartupRecovery(
        store,
        current_generation=_id(),
        timeout_ns=2_000_000_000,
        max_operations=8,
        max_bytes=65_536,
    )

    async def query(_: str) -> svc.RecoverySnapshot:
        return _snapshot(pointer)

    assert await recovery.prepare(query) is not None
    assert recovery.inspection is not None
    assert recovery.inspection.log_identity is None
    await recovery.recover()
    assert path.read_bytes() == log
    reports = list(path.parent.glob("RECOVERY-*.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text())
    assert report["spikeglx_stop_unconfirmed"] is True
    assert report["expected_spikeglx_endpoint"] == {
        "address": "192.0.2.10",
        "port": 4142,
    }
    assert report["administrative_log_issue"]
    recovery.close()


async def test_uncertain_append_is_never_resubmitted_in_same_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = _event("session_started") + _event("trial_started", trial_number=1)
    store, pointer, path = _fixture(tmp_path, log)
    recovery = StartupRecovery(
        store,
        current_generation=_id(),
        timeout_ns=2_000_000_000,
        max_operations=8,
        max_bytes=65_536,
    )

    async def query(_: str) -> svc.RecoverySnapshot:
        return _snapshot(pointer)

    assert await recovery.prepare(query) is not None
    submissions = [0]

    def never_complete(
        _writer: MetadataWriter, _request: object
    ) -> Future[MetadataCompletion]:
        submissions[0] += 1
        return Future()

    monkeypatch.setattr(MetadataWriter, "submit", never_complete)
    recovery.timeout_ns = 200_000_000
    with pytest.raises(TimeoutError):
        await recovery.recover()
    with pytest.raises(StorageError, match="may already have occurred"):
        await recovery.recover()
    assert submissions == [1]
    assert path.read_bytes() == log
    assert store.read_pointer() == pointer
    assert recovery.writer is not None
    assert recovery.writer.seal(1)
    recovery.close()


def test_recovery_reader_rejects_zero_budget_and_nonregular_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "input"
    path.write_bytes(b"{}")
    with pytest.raises(StorageError, match="positive inspection"):
        read_recovery_file(path, 0)
    if sys.platform != "win32":
        fifo = tmp_path / "fifo"
        os.mkfifo(fifo)
        with pytest.raises(StorageError, match="regular"):
            read_recovery_file(fifo, 4096)


def test_prior_completed_recovery_event_is_not_duplicated(tmp_path: Path) -> None:
    log = (
        _event("session_started")
        + _event("session_ended", outcome="interrupted")
        + _event("recovery", outcome="completed")
    )
    _store, pointer, path = _fixture(tmp_path, log)
    held = OutputReservation.open_existing(
        path.parent.parent, pointer.session_id, pointer.controller_generation
    )
    try:
        inspection = inspect_recovery(held, 65_536)
        assert inspection.recovery_recorded
        assert inspection.unfinished_trials == ()
    finally:
        held.release()
