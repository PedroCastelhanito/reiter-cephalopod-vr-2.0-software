"""Frozen Setup configuration, commit races and serialized history saves."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.configuration import controller_validators
from cephvr.controller.control import configuration as configuration_module
from cephvr.controller.metadata.reservation import OutputReservation
from cephvr.controller.ports import BackendPort
from cephvr.controller.runtime import ControllerRuntime
from cephvr.controller.startup.providers import (
    _installed_file_policies,
    _installed_validators,
)
from cephvr.controller.state import Attempt
from cephvr.visual_stimulus.v1 import runtime_pb2 as visual_stimulus_pb
from tests.controller.support_components import (
    TaskCapture,
    _id,
    _RetainedPeer,
    default_limits,
)
from tests.controller.support_components import _runtime as component_runtime
from tests.visual_stimulus.support import valid_display_json


def _runtime(backend: pb.BackendContext | None = None) -> ControllerRuntime:
    limits = default_limits()
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
    visual_stimulus = pb.BackendContext(
        backend_name="visual_stimulus", backend_generation=_id()
    )
    runtime = _runtime(visual_stimulus)
    runtime.supervisor_state.processes["visual_stimulus"] = svc.ProcessHealthStatus(
        process=pb.ProcessIdentity(
            role="visual_stimulus", generation=visual_stimulus.backend_generation
        ),
        process_running=True,
        connected=True,
    )
    current = runtime.configuration_state.current
    current.mode = pb.SESSION_MODE_OPEN_LOOP
    current.recording_root = root
    current.experiment = "experiment"
    current.subject = "subject"
    current.backends.add(backend_name="visual_stimulus", enabled=True)
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
    if kind == "symlink":
        try:
            link.symlink_to(real, target_is_directory=True)
        except OSError as exc:
            if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
                pytest.skip("Windows account lacks symlink creation privilege")
            raise
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


@pytest.mark.parametrize(
    "blocker", ["manual_cleanup", "failed_cleanup", "tracking", "inventory"]
)
async def test_update_configuration_preserves_unresolved_owner_revision(
    monkeypatch: pytest.MonkeyPatch, blocker: str
) -> None:
    runtime = _runtime()
    monkeypatch.setattr(runtime.control_operations, "authorized", lambda _command: "")
    runtime.configuration_commands.validators = {
        "test": lambda _configuration: pb.ValidationResult(completed=True, valid=True)
    }
    if blocker == "manual_cleanup":
        runtime.lifecycle.manual_control_cleanup_pending = True
    elif blocker == "inventory":
        runtime.lifecycle.inventory_update_pending = True
    elif blocker == "failed_cleanup":
        session = pb.SessionContext(
            controller_generation=runtime.generation, session_id=_id()
        )
        attempt = Attempt(
            session,
            pb.PreparedSession(context=session),
            None,  # type: ignore[arg-type]
            {},
            {},
        )
        attempt.closure.done = True
        attempt.closure.clean = False
        runtime.lifecycle.attempt = attempt
        runtime.lifecycle.session.cleanup_confirmed = False
    else:
        runtime.control.tracking_diagnostic.diagnostic_id = _id()
        runtime.control.tracking_diagnostic.active = True
        runtime.control.tracking_diagnostic.closed = False
        runtime.control.tracking_diagnostic.configuration_revision = (
            runtime.configuration_state.revision
        )
    revision = runtime.configuration_state.revision
    admission = await runtime.update_configuration(_update_request(runtime, "changed"))
    assert admission.result == pb.COMMAND_RESULT_REJECTED
    expected = {
        "manual_cleanup": "manual device cleanup",
        "inventory": "inventory persistence",
        "failed_cleanup": "session cleanup is unresolved",
        "tracking": "Tracking diagnostic must confirm closure",
    }[blocker]
    assert expected in admission.failure.message
    assert runtime.configuration_state.revision == revision
    assert runtime.configuration_state.current.subject == ""


async def test_update_configuration_rechecks_owner_cleanup_after_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    monkeypatch.setattr(runtime.control_operations, "authorized", lambda _command: "")
    started, release = threading.Event(), threading.Event()

    def validate(_configuration: pb.ExperimentConfiguration) -> pb.ValidationResult:
        started.set()
        assert release.wait(2)
        return pb.ValidationResult(completed=True, valid=True)

    runtime.configuration_commands.validators = {"test": validate}
    update = asyncio.create_task(
        runtime.update_configuration(_update_request(runtime, "changed"))
    )
    assert await asyncio.to_thread(started.wait, 2)
    runtime.lifecycle.manual_control_cleanup_pending = True
    release.set()
    admission = await update
    assert admission.result == pb.COMMAND_RESULT_REJECTED
    assert runtime.configuration_state.revision == 1


async def test_ready_configuration_edit_without_unresolved_owner_remains_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    runtime.lifecycle.session.phase = pb.SESSION_PHASE_READY
    monkeypatch.setattr(runtime.control_operations, "authorized", lambda _command: "")
    runtime.configuration_commands.validators = {
        "test": lambda _configuration: pb.ValidationResult(completed=True, valid=True)
    }
    session = pb.SessionContext(
        controller_generation=runtime.generation, session_id=_id()
    )
    runtime.lifecycle.attempt = Attempt(
        session,
        pb.PreparedSession(context=session),
        None,  # type: ignore[arg-type]
        {},
        {},
    )
    cleanup_calls = []

    async def cancel_attempt(_attempt: Attempt) -> None:
        cleanup_calls.append(True)

    monkeypatch.setattr(runtime.cleanup, "cancel_attempt", cancel_attempt)
    tasks = TaskCapture(runtime.configuration_commands.spawn)
    runtime.configuration_commands.spawn = tasks.spawn
    admission = await runtime.update_configuration(_update_request(runtime, "changed"))
    await tasks.drain()
    assert admission.result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime.configuration_state.current.subject == "changed"
    assert cleanup_calls == [True]


async def test_setup_waits_for_inventory_persistence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recording_root = tmp_path / "recordings"
    recording_root.mkdir()
    runtime, _tasks = _setup_ready_runtime(monkeypatch, str(recording_root))
    runtime.lifecycle.inventory_update_pending = True
    admission = await runtime.setup(_command())
    assert admission.result == pb.COMMAND_RESULT_REJECTED
    assert "inventory persistence" in admission.failure.message


@pytest.mark.parametrize("blocker", ["inventory", "tracking", "calibration"])
async def test_setup_rechecks_owner_readiness_after_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, blocker: str
) -> None:
    recording_root = tmp_path / "recordings"
    recording_root.mkdir()
    runtime, tasks = _setup_ready_runtime(monkeypatch, str(recording_root))
    started, release = threading.Event(), threading.Event()

    def validate(_configuration: pb.ExperimentConfiguration) -> pb.ValidationResult:
        started.set()
        assert release.wait(2)
        return pb.ValidationResult(completed=True, valid=True)

    runtime.setup_admission.validators = {"structural": validate}
    setup = asyncio.create_task(runtime.setup(_command()))
    assert await asyncio.to_thread(started.wait, 2)
    async with runtime.lifecycle.lock:
        if blocker == "inventory":
            runtime.lifecycle.inventory_update_pending = True
        elif blocker == "tracking":
            runtime.control.tracking_diagnostic.active = True
            runtime.control.tracking_diagnostic.closed = False
        else:
            runtime.device_state.calibration_blocked = True
    release.set()
    admission = await setup
    assert admission.result == pb.COMMAND_RESULT_REJECTED
    assert {
        "inventory": "inventory persistence",
        "tracking": "Tracking diagnostic must confirm closure",
        "calibration": "Display calibration must confirm Idle",
    }[blocker] in admission.failure.message
    assert runtime.lifecycle.attempt is None
    assert runtime.lifecycle.session.phase == pb.SESSION_PHASE_CONFIGURATION
    await tasks.drain()


async def test_rejected_edit_reports_first_validation_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    monkeypatch.setattr(runtime.control_operations, "authorized", lambda _command: "")
    result = pb.ValidationResult(completed=True, valid=False)
    result.issues.add(
        field_path="backends.acquisition.behavioral.device.settings.trigger_source",
        failure=pb.Failure(
            code="TRIGGER_SOURCE_REQUIRED",
            message="external trigger input must be explicit",
        ),
    )
    runtime.configuration_commands.validators = {"acquisition": lambda _: result}
    admission = await runtime.update_configuration(_update_request(runtime, "subject"))
    assert admission.result == pb.COMMAND_RESULT_REJECTED
    assert "trigger_source: external trigger input must be explicit" in (
        admission.failure.message
    )


async def test_update_configuration_admission_rejects_setting_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    runtime.lifecycle.session.phase = pb.SESSION_PHASE_SETTING_UP
    monkeypatch.setattr(runtime.control_operations, "authorized", lambda _command: "")
    revision = runtime.configuration_state.revision
    result = await runtime.update_configuration(_update_request(runtime, "new"))
    assert result.result == pb.COMMAND_RESULT_REJECTED
    assert runtime.configuration_state.current.subject == ""
    assert runtime.configuration_state.revision == revision


async def test_installed_visual_stimulus_policy_is_shared_by_edit_and_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = Path(__file__).resolve().parents[2]
    for relative in (
        "config/backends/visual_stimulus_config.toml",
        "contracts/policy/visual_stimulus_policy.toml",
    ):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repository / relative, destination)
    config_path = tmp_path / "config/backends/visual_stimulus_config.toml"
    config_path.write_text(
        config_path.read_text().replace(
            '# pacing_output_id = "<configured output ID>"',
            'pacing_output_id = "projector/main"',
        )
    )

    profile = json.loads(valid_display_json())
    profile["presentation_mode"] = "photodiode_only_vsync"
    profile["photodiode_enabled"] = False
    profile["photodiode_output_id"] = None
    profile.pop("pacing_output_id", None)
    proposed = pb.ExperimentConfiguration()
    backend = proposed.backends.add(backend_name="visual_stimulus", enabled=True)
    backend.visual_stimulus.display.profile_json = json.dumps(profile)

    runtime = _runtime()
    validators = controller_validators(_installed_validators(tmp_path))
    runtime.configuration_commands.validators = validators
    runtime.setup_admission.validators = validators
    policy_loads = 0

    def load_policy_after_commit(active: frozenset[str]) -> dict[str, object]:
        nonlocal policy_loads
        policy_loads += 1
        policies = _installed_file_policies(tmp_path, active)
        # Setup must validate against the exact file policy it captured even if
        # the host file changes before the validator runs.
        config_path.write_text(
            config_path.read_text().replace(
                'pacing_output_id = "projector/main"',
                'pacing_output_id = "projector/changed"',
            )
        )
        return policies

    runtime.setup_admission.file_policy_loader = load_policy_after_commit
    monkeypatch.setattr(runtime.control_operations, "authorized", lambda _command: "")
    initial_revision = runtime.configuration_state.revision
    request = svc.UpdateConfigurationRequest(
        command=svc.OperatorCommand(operator=pb.OperatorContext(command_id=_id())),
        expected_revision=runtime.configuration_state.revision,
        proposed=proposed,
    )

    admission = await runtime.update_configuration(request)

    assert admission.result == pb.COMMAND_RESULT_ACCEPTED, admission.failure.message
    assert runtime.configuration_state.revision == initial_revision + 1
    saved_profile = runtime.configuration_state.current.backends[
        0
    ].visual_stimulus.display.profile_json
    assert (
        saved_profile
        == request.proposed.backends[0].visual_stimulus.display.profile_json
    )
    assert "pacing_output_id" not in json.loads(saved_profile)
    candidate = await runtime.setup_admission._load_candidate(
        _id(), runtime.configuration_state.current
    )
    assert policy_loads == 1
    assert not isinstance(candidate, pb.CommandAdmission)
    policy = candidate.file_policies["visual_stimulus"]
    assert policy.pacing_output_id == "projector/main"
    assert candidate.validation[0].completed and candidate.validation[0].valid


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


@pytest.mark.parametrize(
    ("phase", "accepted"),
    [(pb.SESSION_PHASE_SETTING_UP, False), (pb.SESSION_PHASE_READY, True)],
)
async def test_commit_racing_setup_or_ready_checks_phase_again(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: pb.SessionPhase.ValueType,
    accepted: bool,
) -> None:
    runtime, attempt, tasks = _racing_runtime(tmp_path, monkeypatch, phase)
    result = await runtime.update_configuration(_update_request(runtime, "new"))
    assert result.result == (
        pb.COMMAND_RESULT_ACCEPTED if accepted else pb.COMMAND_RESULT_REJECTED
    )
    assert (runtime.configuration_state.current.subject == "new") is accepted
    assert attempt.cancel_requested is accepted
    await tasks.drain()
    assert tasks.cancelled == ([attempt] if accepted else [])  # type: ignore[attr-defined]


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
    visual_stimulus = pb.BackendContext(
        backend_name="visual_stimulus", backend_generation=_id()
    )
    runtime = _runtime(visual_stimulus)
    session = pb.SessionContext(
        controller_generation=runtime.generation, session_id=_id()
    )
    prepared = pb.PreparedSession(context=session)
    frozen = prepared.configuration.backends.add(
        backend_name="visual_stimulus", enabled=True
    )
    frozen.visual_stimulus.save_visual_stimulus_data = True
    live = runtime.configuration_state.current.backends.add(
        backend_name="visual_stimulus", enabled=True
    )
    live.visual_stimulus.save_visual_stimulus_data = False
    peer = cast(BackendPort, _RetainedPeer(visual_stimulus, svc.RetainedResult()))
    prepared.trials.add(
        context=pb.TrialContext(session=session, trial_id=_id(), trial_number=1)
    )
    attempt = Attempt(
        session, prepared, cast(OutputReservation, None), {"visual_stimulus": peer}, {}
    )
    attempt.file_policies["visual_stimulus"] = (
        visual_stimulus_pb.VisualStimulusFilePolicies()
    )
    request = runtime.preparation_context.setup_request(
        attempt,
        peer,
        _id(),
    )
    assert request.settings.visual_stimulus.save_visual_stimulus_data is True


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


async def test_wait_evidence_surfaces_retained_setup_failure(tmp_path: Path) -> None:
    runtime = _runtime()
    attempt = _waiting_attempt(runtime, tmp_path)
    runtime.lifecycle.session.phase = pb.SESSION_PHASE_SETTING_UP
    attempt.setup_operations["acquisition"] = "camera-setup"
    attempt.scope_results["camera-setup"] = pb.OperationState(
        complete=True,
        succeeded=False,
        failure=pb.Failure(code="CAMERA_SETTINGS", message="readback failed"),
    )
    with pytest.raises(
        RuntimeError, match="acquisition Setup failed: CAMERA_SETTINGS: readback failed"
    ):
        await runtime.evidence_waiter.wait_evidence(lambda: False, 10**18, attempt)


async def test_timed_out_save_cannot_overwrite_a_newer_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime: ControllerRuntime = component_runtime(
        tmp_path,
        pb.BackendContext(backend_name="visual_stimulus", backend_generation=_id()),
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
        tmp_path,
        pb.BackendContext(backend_name="visual_stimulus", backend_generation=_id()),
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


async def test_history_queue_wait_consumes_original_save_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = component_runtime(
        tmp_path,
        pb.BackendContext(backend_name="visual_stimulus", backend_generation=_id()),
    )
    commands = runtime.configuration_commands
    commands.configuration_history_path = tmp_path / "history.json"
    monkeypatch.setattr(commands.control_operations, "authorized", lambda *a, **k: "")
    runtime.limit_state.current = dataclasses.replace(
        runtime.limit_state.current, history_ns=20_000_000
    )
    await commands._history_lock.acquire()
    try:
        async with asyncio.timeout(0.5):
            receipt = await commands.save_configuration_history(_history_command())
        assert receipt.result == pb.COMMAND_RESULT_REJECTED
        assert not commands.configuration_history_path.exists()
        assert commands._history_seq == 0
    finally:
        commands._history_lock.release()


async def test_shutdown_history_failure_preserves_previous_file_and_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = component_runtime(
        tmp_path,
        pb.BackendContext(backend_name="visual_stimulus", backend_generation=_id()),
    )
    commands = runtime.configuration_commands
    history = tmp_path / "history.json"
    history.write_text("previous", encoding="utf-8")
    commands.configuration_history_path = history

    def fail_write(*args: object, **kwargs: object) -> None:
        raise OSError("history disk unavailable")

    monkeypatch.setattr(configuration_module, "_atomic_json", fail_write)
    await commands.save_history_on_shutdown(
        commands.clock() + runtime.limit_state.current.history_ns
    )
    assert history.read_text(encoding="utf-8") == "previous"
    assert any(
        warning.component == "configuration_history"
        and "history disk unavailable" in warning.message
        for warning in runtime.control.warnings
    )


async def test_wait_evidence_surfaces_retained_trial_failure(tmp_path: Path) -> None:
    runtime = _runtime()
    attempt = _waiting_attempt(runtime, tmp_path)
    runtime.lifecycle.session.phase = pb.SESSION_PHASE_RUNNING
    runtime.lifecycle.trial.phase = pb.TRIAL_PHASE_PREPARING
    attempt.trial_results["acquisition"] = pb.OperationState(
        complete=True,
        succeeded=False,
        failure=pb.Failure(code="WRITER", message="cannot prepare output"),
    )
    with pytest.raises(
        RuntimeError,
        match="acquisition PrepareTrial failed: WRITER: cannot prepare output",
    ):
        await runtime.evidence_waiter.wait_evidence(lambda: False, 10**18, attempt)
