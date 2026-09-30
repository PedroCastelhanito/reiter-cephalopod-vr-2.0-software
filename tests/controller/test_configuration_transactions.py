"""Frozen Setup configuration, commit races and serialized history saves."""

from __future__ import annotations

import asyncio
import dataclasses
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control import configuration as configuration_module
from cephvr.controller.metadata.reservation import OutputReservation
from cephvr.controller.ports import BackendPort
from cephvr.controller.runtime import ControllerRuntime
from cephvr.controller.state import Attempt, ControllerLimits
from cephvr.vr.v1 import runtime_pb2 as vr_pb
from tests.controller.support_components import TaskCapture, _RetainedPeer
from tests.controller.support_components import _runtime as component_runtime


def _id() -> str:
    return str(uuid.uuid4())


def _runtime(backend: pb.BackendContext | None = None) -> ControllerRuntime:
    limits = ControllerLimits(
        setup_ns=1_000_000_000,
        setup_cancel_ns=1_000_000_000,
        ready_ns=1_000_000_000,
        finished_ns=1_000_000_000,
        registration_ns=1_000_000_000,
        recovery_ns=1_000_000_000,
        metadata_ns=1_000_000_000,
        validation_ns=1_000_000_000,
        lead_ns=500_000_000,
        controller_release_ns=100_000_000,
        backend_release_ns=50_000_000,
        start_evidence_ns=250_000_000,
        stop_evidence_ns=250_000_000,
        max_metadata_operations=8,
        max_metadata_bytes=4096,
        history_ns=1_000_000_000,
        space_query_ns=1_000_000_000,
        low_space_bytes=1,
    )
    backends = {}
    if backend is not None:
        backends[backend.backend_name] = cast(
            BackendPort, _RetainedPeer(backend, svc.RetainedResult())
        )
    return ControllerRuntime(
        generation=_id(),
        configuration=pb.ExperimentConfiguration(),
        limits=limits,
        validators={},
        backends=backends,
        clock=lambda: 1_000,
    )


# ---- recording_root frozen per Setup -------------------------------------


def _setup_ready_runtime(
    monkeypatch: pytest.MonkeyPatch, root: str
) -> tuple[ControllerRuntime, TaskCapture]:
    vr = pb.BackendContext(backend_name="vr", backend_generation=_id())
    runtime = _runtime(vr)
    runtime.supervisor_state.processes["vr"] = svc.ProcessHealthStatus(
        process=pb.ProcessIdentity(role="vr", generation=vr.backend_generation),
        process_running=True,
        connected=True,
    )
    current = runtime.configuration_state.current
    current.mode = pb.SESSION_MODE_OPEN_LOOP
    current.recording_root = root
    current.experiment = "experiment"
    current.subject = "subject"
    current.backends.add(backend_name="vr", enabled=True)
    current.trials.add(trial_number=1)
    runtime.setup_admission.validators = {
        "structural": lambda _: pb.ValidationResult(completed=True, valid=True)
    }
    runtime.setup_admission.file_policy_loader = lambda _active: {}
    monkeypatch.setattr(runtime.control_operations, "authorized", lambda _command: "")

    async def no_dispatch(*_args: object) -> None:
        return None

    monkeypatch.setattr(runtime.setup_execution, "run_setup", no_dispatch)
    tasks = TaskCapture(runtime.setup_admission.spawn)
    runtime.setup_admission.spawn = tasks.spawn
    return runtime, tasks


def _command() -> svc.OperatorCommand:
    command = svc.OperatorCommand()
    command.operator.command_id = _id()
    return command


async def test_setup_freezes_edited_recording_root_into_reservation_and_session_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    edited = tmp_path / "edited"
    edited.mkdir()
    runtime, tasks = _setup_ready_runtime(monkeypatch, str(edited))
    admission = await runtime.setup(_command())
    assert admission.result == pb.COMMAND_RESULT_ACCEPTED, admission.failure.message
    attempt = runtime.lifecycle.attempt
    assert attempt is not None
    assert attempt.reservation.root == edited.resolve()
    assert Path(attempt.prepared.session_directory).is_relative_to(edited.resolve())
    assert attempt.prepared.configuration.recording_root == str(edited)
    await tasks.drain()


async def test_setup_disk_check_uses_frozen_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime()
    session = pb.SessionContext(
        controller_generation=runtime.generation, session_id=_id()
    )
    reservation = OutputReservation(
        tmp_path,
        "experiment",
        "subject",
        session.session_id,
        runtime.generation,
        datetime(2026, 9, 30, tzinfo=UTC),
    )
    attempt = Attempt(session, pb.PreparedSession(context=session), reservation, {}, {})
    queried: list[Path] = []
    real = shutil.disk_usage

    def spy(path: Path) -> object:
        queried.append(Path(path))
        return real(path)

    monkeypatch.setattr(shutil, "disk_usage", spy)
    await runtime.setup_execution._reserve_output(attempt, _id(), 10**12)
    assert queried == [tmp_path.resolve()]


@pytest.mark.parametrize("kind", ["unset", "blank", "relative", "missing", "symlink"])
async def test_setup_rejects_unset_or_invalid_recording_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    root = {
        "unset": "",
        "blank": "   ",
        "relative": "relative/dir",
        "missing": str(tmp_path / "missing"),
        "symlink": str(link),
    }[kind]
    runtime, _tasks = _setup_ready_runtime(monkeypatch, root)
    admission = await runtime.setup(_command())
    assert admission.result == pb.COMMAND_RESULT_REJECTED
    assert "recording root" in admission.failure.message
    assert runtime.lifecycle.attempt is None


# ---- commit-time phase recheck -------------------------------------------


def _update_request(
    runtime: ControllerRuntime, subject: str
) -> svc.UpdateConfigurationRequest:
    return svc.UpdateConfigurationRequest(
        command=svc.OperatorCommand(operator=pb.OperatorContext(command_id=_id())),
        expected_revision=runtime.configuration_state.revision,
        proposed=pb.ExperimentConfiguration(subject=subject),
    )


def _racing_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    final_phase: pb.SessionPhase.ValueType,
) -> tuple[ControllerRuntime, Attempt, TaskCapture]:
    runtime = _runtime()
    session = pb.SessionContext(
        controller_generation=runtime.generation, session_id=_id()
    )
    reservation = OutputReservation(
        tmp_path,
        "experiment",
        "subject",
        session.session_id,
        runtime.generation,
        datetime(2026, 9, 30, tzinfo=UTC),
    )
    attempt = Attempt(session, pb.PreparedSession(context=session), reservation, {}, {})
    monkeypatch.setattr(runtime.control_operations, "authorized", lambda _command: "")

    def validator(_: pb.ExperimentConfiguration) -> pb.ValidationResult:
        # The phase moves while validation runs outside the lifecycle lock.
        runtime.lifecycle.session.phase = final_phase
        if final_phase != pb.SESSION_PHASE_CONFIGURATION:
            runtime.lifecycle.attempt = attempt
        return pb.ValidationResult(completed=True, valid=True)

    runtime.configuration_commands.validators = {"experiment": validator}
    cancelled: list[Attempt] = []

    async def cancel(target: Attempt) -> None:
        cancelled.append(target)

    monkeypatch.setattr(
        runtime.configuration_commands.cleanup, "cancel_attempt", cancel
    )
    tasks = TaskCapture(runtime.configuration_commands.spawn)
    runtime.configuration_commands.spawn = tasks.spawn
    tasks.cancelled = cancelled  # type: ignore[attr-defined]
    return runtime, attempt, tasks


@pytest.mark.parametrize("phase", [pb.SESSION_PHASE_SETTING_UP, pb.SESSION_PHASE_READY])
async def test_commit_racing_setup_or_ready_commits_and_cancels_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: pb.SessionPhase.ValueType
) -> None:
    runtime, attempt, tasks = _racing_runtime(tmp_path, monkeypatch, phase)
    result = await runtime.update_configuration(_update_request(runtime, "new"))
    assert result.result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime.configuration_state.current.subject == "new"
    assert attempt.cancel_requested
    await tasks.drain()
    assert tasks.cancelled == [attempt]  # type: ignore[attr-defined]


@pytest.mark.parametrize("phase", [pb.SESSION_PHASE_STARTING, pb.SESSION_PHASE_RUNNING])
async def test_commit_racing_start_is_rejected_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: pb.SessionPhase.ValueType
) -> None:
    runtime, attempt, tasks = _racing_runtime(tmp_path, monkeypatch, phase)
    revision = runtime.configuration_state.revision
    result = await runtime.update_configuration(_update_request(runtime, "new"))
    assert result.result == pb.COMMAND_RESULT_REJECTED
    assert "not applied" in result.failure.message
    assert runtime.configuration_state.revision == revision
    assert runtime.configuration_state.current.subject != "new"
    assert not attempt.cancel_requested
    assert tasks.cancelled == []  # type: ignore[attr-defined]


async def test_commit_in_configuration_phase_just_commits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, _attempt, tasks = _racing_runtime(
        tmp_path, monkeypatch, pb.SESSION_PHASE_CONFIGURATION
    )
    result = await runtime.update_configuration(_update_request(runtime, "new"))
    assert result.result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime.configuration_state.current.subject == "new"
    assert tasks.cancelled == []  # type: ignore[attr-defined]


# ---- setup_request uses the frozen prepared settings ----------------------


def test_setup_request_uses_prepared_backend_settings_not_live() -> None:
    vr = pb.BackendContext(backend_name="vr", backend_generation=_id())
    runtime = _runtime(vr)
    session = pb.SessionContext(
        controller_generation=runtime.generation, session_id=_id()
    )
    prepared = pb.PreparedSession(context=session)
    frozen = prepared.configuration.backends.add(backend_name="vr", enabled=True)
    frozen.vr.save_vr_data = True
    live = runtime.configuration_state.current.backends.add(
        backend_name="vr", enabled=True
    )
    live.vr.save_vr_data = False
    attempt = Attempt(session, prepared, cast(OutputReservation, None), {}, {})
    attempt.file_policies["vr"] = vr_pb.VRFilePolicies()
    request = runtime.preparation_context.setup_request(
        attempt, cast(BackendPort, _RetainedPeer(vr, svc.RetainedResult())), _id()
    )
    assert request.settings.vr.save_vr_data is True


# ---- evidence cutoff --------------------------------------------------------


def _waiting_attempt(runtime: ControllerRuntime, tmp_path: Path) -> Attempt:
    session = pb.SessionContext(
        controller_generation=runtime.generation, session_id=_id()
    )
    reservation = OutputReservation(
        tmp_path,
        "experiment",
        "subject",
        session.session_id,
        runtime.generation,
        datetime(2026, 9, 30, tzinfo=UTC),
    )
    attempt = Attempt(session, pb.PreparedSession(context=session), reservation, {}, {})
    runtime.lifecycle.attempt = attempt
    return attempt


async def test_wait_evidence_accepts_satisfied_predicate_past_wall_deadline(
    tmp_path: Path,
) -> None:
    runtime = _runtime()
    attempt = _waiting_attempt(runtime, tmp_path)
    now = [1_000]
    runtime.evidence_waiter.clock = lambda: now[0]
    deadline = 2_000
    # A slow start_trial_log fsync moved the wall clock beyond the deadline while
    # evidence ingressed on time is already recorded.
    now[0] = deadline + 10_000_000
    await runtime.evidence_waiter.wait_evidence(lambda: True, deadline, attempt)


async def test_wait_evidence_still_times_out_when_evidence_missing(
    tmp_path: Path,
) -> None:
    runtime = _runtime()
    attempt = _waiting_attempt(runtime, tmp_path)
    runtime.evidence_waiter.clock = lambda: 5_000
    with pytest.raises(TimeoutError):
        await runtime.evidence_waiter.wait_evidence(lambda: False, 2_000, attempt)


async def test_timed_out_save_cannot_overwrite_a_newer_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime: ControllerRuntime = component_runtime(
        tmp_path, pb.BackendContext(backend_name="vr", backend_generation=_id())
    )
    commands = runtime.configuration_commands
    commands.configuration_history_path = tmp_path / "history.json"
    monkeypatch.setattr(commands.control_operations, "authorized", lambda *a, **k: "")
    written: list[bytes] = []
    monkeypatch.setattr(
        configuration_module,
        "_atomic_json",
        lambda path, payload, *, replace: written.append(payload),
    )
    limits = runtime.limit_state
    normal = limits.current
    limits.current = dataclasses.replace(normal, history_ns=50_000_000)
    commands._history_writer_lock.acquire()  # the first writer thread is stuck
    first = await commands.save_configuration_history(_history_command())
    assert first.result == pb.COMMAND_RESULT_REJECTED
    limits.current = normal
    runtime.configuration_state.current.experiment = "newer"
    second_task = asyncio.create_task(
        commands.save_configuration_history(_history_command())
    )
    await asyncio.sleep(0.05)
    commands._history_writer_lock.release()
    assert (await second_task).result == pb.COMMAND_RESULT_ACCEPTED
    await asyncio.sleep(0.1)
    assert len(written) == 1 and b"newer" in written[0]


def _history_command() -> svc.OperatorCommand:
    return svc.OperatorCommand(operator=pb.OperatorContext(command_id=_id()))


async def test_concurrent_history_saves_do_not_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = component_runtime(
        tmp_path, pb.BackendContext(backend_name="vr", backend_generation=_id())
    )
    commands = runtime.configuration_commands
    commands.configuration_history_path = tmp_path / "history.json"
    monkeypatch.setattr(commands.control_operations, "authorized", lambda *a, **k: "")
    active = 0
    peak = 0

    def writer(path: Path, payload: bytes, *, replace: bool) -> None:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        import time

        time.sleep(0.02)
        active -= 1

    monkeypatch.setattr(configuration_module, "_atomic_json", writer)
    results = await asyncio.gather(
        *(
            commands.save_configuration_history(
                svc.OperatorCommand(operator=pb.OperatorContext(command_id=_id()))
            )
            for _ in range(3)
        )
    )
    assert all(r.result == pb.COMMAND_RESULT_ACCEPTED for r in results)
    assert peak == 1
