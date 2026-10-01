"""Central metadata persistence, uncertain writes and operator projections."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.metadata.coordination import MetadataCoordinator
from cephvr.controller.metadata.documents import active_configuration_document
from cephvr.controller.metadata.reservation import OutputReservation
from cephvr.controller.metadata.types import (
    MetadataCompletion,
    MetadataWrite,
    StorageError,
)
from cephvr.controller.metadata.writer import MetadataWriter
from cephvr.controller.ports import BackendPort
from cephvr.controller.state import Attempt
from tests.controller.support_components import (
    _attempt,
    _id,
    _reservation,
    _RetainedPeer,
    _runtime,
)


class _RetiringWriter:
    def __init__(self) -> None:
        self.retired: list[str] = []

    def retire(self, command_id: str) -> None:
        self.retired.append(command_id)


@pytest.mark.parametrize(
    "failure", [None, "recovery", "unconfirmed", "session_log", "seal"]
)
async def test_session_closure_drains_logs_then_seals_with_remaining_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _runtime(tmp_path, backend)
    attempt = _attempt(runtime, tmp_path, {})
    events: list[str] = []
    now = 1_000
    monkeypatch.setattr(runtime.metadata, "clock", lambda: now)

    class Writer:
        def seal(self, timeout: float) -> bool:
            assert timeout == 0.5
            events.append("seal")
            return failure != "seal"

    attempt.writer = cast(MetadataWriter, Writer())

    async def recovery() -> None:
        nonlocal now
        assert attempt.recovery_log_closed
        events.append("recovery")
        now += 250_000_000
        if failure == "recovery":
            raise StorageError("recovery log failed")

    async def log_event(_attempt: Attempt, event: str, *, outcome: str) -> None:
        nonlocal now
        assert outcome == "interrupted"
        events.append(event)
        now += 250_000_000
        if failure == "session_log":
            raise StorageError("session log failed")

    attempt.recovery_log_tasks.add(asyncio.create_task(recovery()))
    monkeypatch.setattr(runtime.metadata, "log_event", log_event)
    if failure == "unconfirmed":
        runtime.metadata_state.results[_id()] = pb.MetadataResult(
            state=pb.METADATA_PERSISTENCE_UNCONFIRMED
        )
    clean = await runtime.metadata.finish_session(
        attempt, outcome="interrupted", deadline_ns=1_000_001_000
    )
    assert clean == (failure is None)
    assert events == ["recovery", "session_ended", "seal"]
    assert attempt.writer_closed == (failure != "seal")


async def test_expired_session_closure_cancels_recovery_without_claiming_seal(
    tmp_path: Path,
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _runtime(tmp_path, backend)
    attempt = _attempt(runtime, tmp_path, {})

    def seal(_timeout: float) -> bool:
        pytest.fail("expired closure must not start sealing")

    attempt.writer = cast(MetadataWriter, SimpleNamespace(seal=seal))
    recovery = asyncio.create_task(asyncio.Event().wait())
    attempt.recovery_log_tasks.add(recovery)
    assert not await runtime.metadata.finish_session(
        attempt, outcome="interrupted", deadline_ns=999
    )
    assert recovery.cancelled()
    assert attempt.recovery_log_closed and not attempt.writer_closed


def test_session_config_excludes_dormant_settings_and_pfs_payload() -> None:
    config = pb.ExperimentConfiguration()
    active = config.backends.add(backend_name="acquisition", enabled=True)
    active.acquisition.behavioral.enabled = True
    active.acquisition.behavioral.device.device_id = "camera-1"
    active.acquisition.behavioral.device.pfs_baseline.text = "SDK SECRET SNAPSHOT"
    active.acquisition.tracking.enabled = False
    active.acquisition.tracking.device.device_id = "dormant-camera"
    config.backends.add(
        backend_name="tracking", enabled=False
    ).tracking.pipeline_id = "dormant-pipeline"

    document = active_configuration_document(config)
    text = str(document)
    assert "camera-1" in text
    assert "SDK SECRET SNAPSHOT" not in text
    assert "dormant-camera" not in text
    assert "dormant-pipeline" not in text
    assert (
        config.backends[0].acquisition.behavioral.device.pfs_baseline.text
        == "SDK SECRET SNAPSHOT"
    )


async def test_interrupted_trial_logs_unknown_output_without_inventing_actual_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _runtime(tmp_path, backend)
    attempt = _attempt(runtime, tmp_path, {})
    trial = pb.TrialContext(session=attempt.context, trial_id=_id(), trial_number=1)
    plan = attempt.prepared.trials.add(context=trial)
    attempt.prepared.outputs.add(
        output_key="camera-output",
        trial=trial,
        backend=backend,
        path=str(tmp_path / "camera.mp4"),
    )
    attempt.trial_index = 0
    attempt.trial_log_name = "subject_120000_LOG.json"
    attempt.trial_log_start_task = asyncio.create_task(asyncio.sleep(0))
    attempt.started["acquisition"] = pb.StartedReport()
    attempt.interrupted = True
    attempt.interruption_issued_ns = 1_000
    attempt.finished_deadline_ns = 2_000
    attempt.finalization_deadline_ns = 1_000_000_000_000
    runtime.lifecycle.attempt = attempt
    runtime.lifecycle.trial = pb.TrialState(
        context=trial, phase=pb.TRIAL_PHASE_FINALIZING
    )
    documents: list[dict[str, object]] = []
    events: list[tuple[str, str | None, dict[str, object]]] = []
    recovery_calls: list[tuple[str, bool]] = []

    async def persist(
        _attempt: Attempt, _name: str, _action: str, document: dict[str, object]
    ) -> None:
        documents.append(document)

    async def log_event(_attempt: Attempt, name: str, **kwargs: object) -> None:
        events.append(
            (
                name,
                cast(str | None, kwargs.get("outcome")),
                cast(dict[str, object], kwargs.get("details", {})),
            )
        )

    async def missing(*_args: object, **_kwargs: object) -> None:
        raise TimeoutError("original evidence cutoff elapsed")

    async def missing_finished(
        _attempt: Attempt,
        kind: str,
        _expected: frozenset[str],
        _deadline: int,
        *,
        closure_only: bool = False,
    ) -> bool:
        recovery_calls.append((kind, closure_only))
        raise TimeoutError("one recovery query exhausted")

    monkeypatch.setattr(runtime.metadata, "persist", persist)
    monkeypatch.setattr(runtime.metadata, "log_event", log_event)
    monkeypatch.setattr(runtime.evidence_waiter, "wait_evidence", missing)
    monkeypatch.setattr(
        runtime.evidence_waiter, "wait_lifecycle_with_recovery", missing_finished
    )
    monkeypatch.setattr(
        "cephvr.controller.metadata.trial_logs.activity_backends",
        lambda _attempt: frozenset({"acquisition"}),
    )
    attempt.trial_participants["acquisition"] = cast(
        BackendPort, _RetainedPeer(backend, svc.RetainedResult())
    )

    assert await runtime.trial_logs.finish_interrupted_trial(attempt)
    assert recovery_calls == [("finished", True)]
    assert documents[0]["outcome"] == "interrupted"
    assert documents[0]["complete"] is True
    assert (
        cast(list[dict[str, object]], documents[0]["outputs"])[0]["closure"]
        == "OUTPUT_CLOSURE_UNCONFIRMED"
    )
    assert len(events) == 1
    assert events[0][0:2] == ("trial_finished", "interrupted")
    assert events[0][2]["actual_end_monotonic_ns"] is None
    assert events[0][2]["interruption_issued_monotonic_ns"] == 1_000
    assert runtime.lifecycle.trial.outcome == pb.TRIAL_OUTCOME_INTERRUPTED
    assert not runtime.lifecycle.trial.HasField("actual_end_monotonic_ns")
    assert attempt.trial_log_finished
    assert plan.context == trial


async def test_metadata_projection_coalesces_synced_file_but_retains_failed_write(
    tmp_path: Path,
) -> None:
    runtime = _runtime(
        tmp_path,
        pb.BackendContext(backend_name="acquisition", backend_generation=_id()),
    )
    path = tmp_path / "SESSION_LOG.jsonl"
    first, failed, latest = _id(), _id(), _id()
    for command_id in (first, failed, latest):
        runtime.metadata_state.results[command_id] = pb.MetadataResult(
            operation=pb.OperationContext(command_id=command_id),
            state=pb.METADATA_PERSISTENCE_PENDING,
            path=str(path),
        )
    writer = _RetiringWriter()
    await runtime.metadata.record_metadata(
        MetadataCompletion(first, path, "synced", 1_000),
        cast(MetadataWriter, writer),
        terminal=True,
    )
    await runtime.metadata.record_metadata(
        MetadataCompletion(failed, path, "failed", 1_000, "disk fault"),
        cast(MetadataWriter, writer),
        terminal=True,
    )
    runtime.metadata_state.results[latest].state = pb.METADATA_PERSISTENCE_UNCONFIRMED
    runtime.metadata_state.results[latest].failure.CopyFrom(
        pb.Failure(code="METADATA_WRITE", message="original deadline expired")
    )
    future: Future[MetadataCompletion] = Future()
    future.set_result(MetadataCompletion(latest, path, "synced", 1_001, "", False))
    runtime.metadata.enqueue_late_metadata(
        future, cast(MetadataWriter, writer), latest, path
    )
    assert runtime.metadata_state.drain_task is not None
    await runtime.metadata_state.drain_task

    assert first not in runtime.metadata_state.results
    assert (
        runtime.metadata_state.results[failed].state == pb.METADATA_PERSISTENCE_FAILED
    )
    assert (
        runtime.metadata_state.results[latest].state == pb.METADATA_PERSISTENCE_SYNCED
    )
    assert not runtime.metadata_state.results[latest].HasField("failure")
    assert any(
        "original deadline expired" in warning.message
        for warning in runtime.control.warnings
    )
    assert set(writer.retired) == {first, failed, latest}


SESSION = "81d85f03-ac85-4d5e-885c-4754ee594540"


GENERATION = "470b220b-6272-4fa3-8677-3957c29eea5f"


def _append(name: str, path: Path, payload: bytes) -> MetadataWrite:
    return MetadataWrite(
        command_id=name,
        work=pb.WorkContext(
            session=pb.SessionContext(
                controller_generation=GENERATION, session_id=SESSION
            )
        ),
        operation=pb.OperationContext(command_id=name),
        path=path,
        action="append_jsonl_record",
        payload_utf8=payload,
        submitted_ns=1,
        deadline_ns=2,
    )


def _writer(root: Path) -> MetadataWriter:
    return MetadataWriter(
        root, max_operations=4, max_bytes=4096, clock=lambda: 1, session_id=SESSION
    )


@pytest.mark.parametrize("failing", ["write", "fsync"])
def test_failed_append_poisons_log_and_old_bytes_never_reappear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing: str
) -> None:
    writer = _writer(tmp_path)
    log = tmp_path / "SESSION_LOG.jsonl"
    assert writer.submit(_append("a", log, b'{"n":1}')).result(3).state == "synced"
    real_write, real_fsync = os.write, os.fsync
    calls = {"n": 0}

    def bad_write(fd: int, data: Any) -> int:
        calls["n"] += 1
        if failing == "write":
            real_write(fd, bytes(data)[:3])  # partial bytes landed, then failure
            raise OSError("disk error")
        return real_write(fd, data)

    def bad_fsync(fd: int) -> None:
        if failing == "fsync":
            raise OSError("fsync error")
        real_fsync(fd)

    monkeypatch.setattr(os, "write", bad_write)
    monkeypatch.setattr(os, "fsync", bad_fsync)
    failed = writer.submit(_append("b", log, b'{"n":2}')).result(3)
    assert failed.state == "failed"
    monkeypatch.setattr(os, "write", real_write)
    monkeypatch.setattr(os, "fsync", real_fsync)
    before = log.read_bytes()
    again = writer.submit(_append("c", log, b'{"n":3}')).result(3)
    assert again.state == "failed" and "unconfirmed" in again.error
    assert log.read_bytes() == before
    assert b'{"n":3}' not in before
    assert writer.seal(3)


def test_first_append_failure_is_poisoned_not_already_owned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = _writer(tmp_path)
    log = tmp_path / "SESSION_LOG.jsonl"

    def bad_fsync(fd: int) -> None:
        raise OSError("fsync error")

    monkeypatch.setattr(os, "fsync", bad_fsync)
    assert writer.submit(_append("a", log, b'{"n":1}')).result(3).state == "failed"
    monkeypatch.undo()
    second = writer.submit(_append("b", log, b'{"n":2}')).result(3)
    assert second.state == "failed"
    assert "already owned" not in second.error and "unconfirmed" in second.error
    assert writer.seal(3)


def test_partial_os_write_is_looped_until_record_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = _writer(tmp_path)
    log = tmp_path / "SESSION_LOG.jsonl"
    real_write = os.write

    def short_write(fd: int, data: Any) -> int:
        return real_write(fd, bytes(data)[:2])

    monkeypatch.setattr(os, "write", short_write)
    assert writer.submit(_append("a", log, b'{"n":1}')).result(3).state == "synced"
    monkeypatch.undo()
    assert log.read_bytes() == b'{"n":1}\n'
    assert writer.seal(3)


def test_close_unactivated_keeps_files_and_marks_marker_complete(
    tmp_path: Path,
) -> None:
    reservation = _reservation(tmp_path)
    reservation.acquire()
    kept = reservation.protocol_directory / "SESSION_CONFIG.json"
    kept.write_text("{}")
    reservation.close_unactivated()
    assert not reservation.held
    assert kept.read_text() == "{}"
    data = json.loads(reservation.marker.read_text())
    assert data["complete"] is True and data["outcome"] == "not_activated"
    with pytest.raises(StorageError, match="not held"):
        reservation.close_unactivated()
    reopened = OutputReservation.open_existing(
        reservation.session_directory, SESSION, GENERATION
    )
    assert reopened.marker_issue == "reservation marker already complete"
    reopened.release()


def test_marker_outcome_other_than_not_activated_is_rejected(tmp_path: Path) -> None:
    reservation = _reservation(tmp_path)
    reservation.acquire()
    reservation.marker.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "session_id": SESSION,
                "controller_generation": GENERATION,
                "complete": True,
                "outcome": "bogus",
            }
        )
    )
    with pytest.raises(StorageError, match="schema"):
        reservation.inspect_marker()
    reservation.release()


class _NeverDoneWriter:
    root = Path("/tmp")

    def __init__(self) -> None:
        self.future: Future[MetadataCompletion] = Future()
        self.retired: list[str] = []

    def submit(self, request: MetadataWrite) -> Future[MetadataCompletion]:
        return self.future

    def retire(self, command_id: str) -> None:
        self.retired.append(command_id)


async def test_cancelled_persist_records_unconfirmed_and_reconciles_late_sync() -> None:
    writer = _NeverDoneWriter()
    results: dict[str, pb.MetadataResult] = {}
    metadata_state = SimpleNamespace(
        results=results,
        latest_synced={},
        completion_queue=asyncio.Queue(8),
        drain_task=None,
    )
    coordinator = MetadataCoordinator(
        lifecycle=SimpleNamespace(lock=asyncio.Lock()),  # type: ignore[arg-type]
        control=SimpleNamespace(warnings=[]),  # type: ignore[arg-type]
        metadata_state=metadata_state,  # type: ignore[arg-type]
        limits=SimpleNamespace(  # type: ignore[arg-type]
            current=SimpleNamespace(
                metadata_ns=60_000_000_000, max_metadata_operations=8
            )
        ),
        clock=lambda: 1,
        publish=lambda: None,
        spawn=lambda coro: asyncio.ensure_future(coro),
    )
    attempt = SimpleNamespace(
        writer=writer,
        context=pb.SessionContext(controller_generation=GENERATION, session_id=SESSION),
        trial_index=-1,
    )
    task = asyncio.ensure_future(
        coordinator.persist(attempt, "SESSION_CONFIG.json", "create_json", {"a": 1})  # type: ignore[arg-type]
    )
    await asyncio.sleep(0.05)
    assert [r.state for r in results.values()] == [pb.METADATA_PERSISTENCE_PENDING]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    (result,) = results.values()
    assert result.state == pb.METADATA_PERSISTENCE_UNCONFIRMED
    command_id = next(iter(results))
    writer.future.set_result(
        MetadataCompletion(command_id, Path("/tmp/x"), "synced", 2, "", True)
    )
    await asyncio.sleep(0.1)
    assert writer.retired == [command_id]
    assert results[command_id].state == pb.METADATA_PERSISTENCE_SYNCED
    assert uuid.UUID(command_id)
