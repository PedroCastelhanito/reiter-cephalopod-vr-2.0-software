"""Session interruption, finalization, Stop and Shutdown ownership."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any, cast

import pytest

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.configuration import manual_camera_owned
from cephvr.controller.device.owner_cleanup import ManualControlCleanup
from cephvr.controller.metadata import trial_logs
from cephvr.controller.runtime import ControllerRuntime
from cephvr.controller.state import Attempt
from tests.controller.support_components import (
    _attempt,
    _id,
    _runtime,
    drain_runtime_tasks,
    operator_command,
)


def _setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ControllerRuntime, Attempt]:
    backend = pb.BackendContext(
        backend_name="visual_stimulus", backend_generation=_id()
    )
    runtime = _runtime(tmp_path, backend)
    attempt = _attempt(runtime, tmp_path, {})
    assert attempt.reservation.acquire() == []
    runtime.lifecycle.attempt = attempt
    runtime.lifecycle.session = pb.SessionState(
        phase=pb.SESSION_PHASE_RUNNING, context=attempt.context, activated=True
    )
    attempt.activated = True
    monkeypatch.setattr(
        runtime.session_commands.control_operations, "authorized", lambda *a, **k: ""
    )

    async def fenced(*_args: object) -> bool:
        return True

    monkeypatch.setattr(runtime.cleanup, "register_cleanup_fences", fenced)
    return runtime, attempt


def _operation(runtime: ControllerRuntime, attempt: Attempt, name: str) -> str:
    command_id = _id()
    runtime.control.operations[command_id] = pb.OperationState(
        context=pb.OperationContext(command_id=command_id), command=name
    )
    return command_id


async def test_interrupt_during_finalize_joins_the_one_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt = _setup(tmp_path, monkeypatch)
    gate, entered = asyncio.Event(), asyncio.Event()
    calls: list[int] = []

    async def slow_fences(*_args: object) -> bool:
        calls.append(1)
        entered.set()
        await gate.wait()
        return True

    monkeypatch.setattr(runtime.cleanup, "register_cleanup_fences", slow_fences)
    runtime.lifecycle.trial.phase = pb.TRIAL_PHASE_ENDED
    first = asyncio.create_task(runtime.interruption.finalize(attempt))
    await entered.wait()
    abort_id = _operation(runtime, attempt, "AbortNow")
    async with runtime.lifecycle.lock:
        attempt.abort_command_ids.append(abort_id)
    second = asyncio.create_task(runtime.interruption.interrupt(attempt, "late abort"))
    # The trial task being cancelled by interrupt cannot cancel finalization.
    first.cancel()
    await asyncio.sleep(0.01)
    assert not second.done()
    gate.set()
    await second
    await drain_runtime_tasks(runtime)
    assert calls == [1]
    session = runtime.lifecycle.session
    assert session.phase == pb.SESSION_PHASE_ENDED
    assert session.outcome != pb.SESSION_OUTCOME_INTERRUPTED
    assert session.cleanup_confirmed
    assert runtime.control.operations[abort_id].succeeded


async def test_trial_schedule_prefix_matches_absolute_output_reservations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt = _setup(tmp_path, monkeypatch)
    attempt.prepared.configuration.subject = "dummy"
    attempt.prepared.anchor_wall_time = "2026-10-08T14:00:00+09:00"
    attempt.prepared.anchor_monotonic_ns = 1_000
    plan = attempt.prepared.trials.add(
        context=pb.TrialContext(
            session=attempt.context, trial_id=_id(), trial_number=1
        ),
        resolved_duration_ns=60_000_000_000,
    )
    output = attempt.prepared.outputs.add(
        trial=plan.context,
        backend=pb.BackendContext(backend_name="visual_stimulus"),
        output_tag="behavioral_cam",
        extension="mp4",
    )
    attempt.trial_participants = {"visual_stimulus": cast(Any, object())}
    schedule = await runtime.trials._plan_trial(attempt, plan)
    assert Path(schedule.file_prefix).is_absolute()
    assert Path(schedule.file_prefix).parent == attempt.reservation.protocol_directory
    assert output.path == schedule.file_prefix + "_behavioral_cam.mp4"
    assert attempt.trial_log_name == Path(schedule.file_prefix).name + "_LOG.json"


@pytest.mark.parametrize(
    "outcome", [pb.SESSION_OUTCOME_COMPLETED, pb.SESSION_OUTCOME_INTERRUPTED]
)
async def test_shutdown_after_ended_completes_without_relabel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: int
) -> None:
    runtime, attempt = _setup(tmp_path, monkeypatch)
    runtime.lifecycle.session.phase = pb.SESSION_PHASE_ENDED
    runtime.lifecycle.session.outcome = cast(Any, outcome)
    runtime.lifecycle.session.cleanup_confirmed = True

    class Supervisor:
        async def request_shutdown(self, _r: object) -> pb.ReportReceipt:
            return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    runtime.session_commands.supervisor = cast(Any, Supervisor())
    history_path = tmp_path / "history.json"
    runtime.configuration_commands.configuration_history_path = history_path
    runtime.configuration_state.current.subject = "shutdown-retained"
    command = operator_command(runtime)
    admission = await runtime.shutdown_application(command)
    assert admission.result == pb.COMMAND_RESULT_ACCEPTED
    await drain_runtime_tasks(runtime)
    operation = runtime.control.operations[command.operator.command_id]
    assert operation.complete and operation.succeeded
    assert runtime.lifecycle.session.phase == pb.SESSION_PHASE_ENDED
    assert json.loads(history_path.read_text())["configuration"]["subject"] == (
        "shutdown-retained"
    )
    assert runtime.lifecycle.session.outcome == outcome
    assert not attempt.interrupted or not runtime.lifecycle.session.HasField(
        "interruption_reason"
    )


async def test_pre_activation_shutdown_cancels_attempt_prompts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt = _setup(tmp_path, monkeypatch)
    attempt.activated = False
    runtime.lifecycle.session = pb.SessionState(phase=pb.SESSION_PHASE_SETTING_UP)
    prompt_id = _id()
    prompt = pb.Prompt(prompt_id=prompt_id, explanation="operator choice")
    future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    runtime.incident_state.prompts[prompt_id] = (prompt, future, attempt)
    cancel_calls: list[Attempt] = []

    async def cancel_attempt(owner: Attempt) -> None:
        cancel_calls.append(owner)

    monkeypatch.setattr(runtime.cleanup, "cancel_attempt", cancel_attempt)

    class Supervisor:
        async def request_shutdown(self, _request: object) -> pb.ReportReceipt:
            return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    runtime.session_commands.supervisor = cast(Any, Supervisor())
    command = operator_command(runtime)
    result = await runtime.shutdown_application(command)

    assert result.result == pb.COMMAND_RESULT_ACCEPTED
    assert future.cancelled()
    await drain_runtime_tasks(runtime)
    assert cancel_calls == [attempt]


class _Writer:
    sealed = 0

    def seal(self, _timeout: float) -> bool:
        self.sealed += 1
        return True


async def test_failed_trial_metadata_still_seals_before_backend_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt = _setup(tmp_path, monkeypatch)
    writer = _Writer()
    attempt.writer = cast(Any, writer)
    attempt.finalization_deadline_ns = 1_000_001_000
    events: list[str] = []

    async def log_event(_attempt: Attempt, event: str, **_kwargs: object) -> None:
        events.append(event)

    async def fenced(_attempt: Attempt, _requests: object, deadline_ns: int) -> bool:
        assert writer.sealed == 1 and attempt.writer_closed
        assert deadline_ns == 1_000_001_000
        events.append("cleanup")
        return True

    monkeypatch.setattr(runtime.metadata, "log_event", log_event)
    monkeypatch.setattr(runtime.cleanup, "register_cleanup_fences", fenced)
    await runtime.interruption.finalize(attempt, metadata_clean=False)
    assert events == ["session_ended", "cleanup"]
    assert attempt.closure.done and not attempt.closure.clean
    assert not runtime.lifecycle.session.cleanup_confirmed
    assert attempt.reservation.held  # failed evidence cannot complete the marker
    attempt.reservation.release()


async def test_abort_during_starting_with_metadata_keeps_files_and_unblocks_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt = _setup(tmp_path, monkeypatch)
    attempt.activated = False
    runtime.lifecycle.session = pb.SessionState(phase=pb.SESSION_PHASE_STARTING)
    (attempt.reservation.protocol_directory / "SESSION_CONFIG.json").write_text("{}")
    attempt.closure.metadata_written = True
    writer = _Writer()
    attempt.writer = cast(Any, writer)
    start_id = _operation(runtime, attempt, "StartSession")
    attempt.closure.start_command_id = start_id
    closed: list[str] = []
    monkeypatch.setattr(
        attempt.reservation, "close_unactivated", lambda: closed.append("closed")
    )

    def refuse() -> None:
        raise AssertionError("cancel() must not be used once files exist")

    monkeypatch.setattr(attempt.reservation, "cancel", refuse)
    await runtime.interruption.interrupt(attempt, "operator Abort now")
    assert writer.sealed == 1 and closed == ["closed"]
    assert (attempt.reservation.protocol_directory / "SESSION_CONFIG.json").exists()
    assert runtime.lifecycle.attempt is None
    assert runtime.lifecycle.session.phase == pb.SESSION_PHASE_CONFIGURATION
    assert runtime.lifecycle.session.cleanup_confirmed
    start = runtime.control.operations[start_id]
    assert start.complete and not start.succeeded
    assert start.failure.message == "start cancelled: operator Abort now"


async def test_unactivated_attempt_without_files_keeps_plain_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt = _setup(tmp_path, monkeypatch)
    attempt.activated = False
    runtime.lifecycle.session = pb.SessionState(phase=pb.SESSION_PHASE_READY)
    cancelled: list[str] = []
    monkeypatch.setattr(attempt.reservation, "cancel", lambda: cancelled.append("x"))
    await runtime.cleanup.cancel_attempt(attempt)
    assert cancelled == ["x"]


async def test_cancel_finishing_earlier_still_completes_a_later_shutdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt = _setup(tmp_path, monkeypatch)
    attempt.cancelling = True
    attempt.closure.done = True
    attempt.closure.clean = False
    shutdown_id = _operation(runtime, attempt, "ShutdownApplication")
    async with runtime.lifecycle.lock:
        attempt.shutdown_command_ids.append(shutdown_id)
    await runtime.cleanup.cancel_attempt(attempt)
    operation = runtime.control.operations[shutdown_id]
    assert operation.complete and not operation.succeeded


async def test_start_rejected_on_revision_mismatch_or_pending_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        runtime.start.control_operations, "authorized", lambda *a, **k: ""
    )
    runtime.start.schema_factory = lambda _: {"schema_version": 1}
    runtime.start.output_planner = lambda *_: []
    runtime.lifecycle.session = pb.SessionState(phase=pb.SESSION_PHASE_READY)
    runtime.configuration_state.revision = attempt.prepared.configuration_revision + 1
    stale = await runtime.start_session(operator_command(runtime))
    assert stale.result == pb.COMMAND_RESULT_REJECTED
    assert runtime.lifecycle.session.phase == pb.SESSION_PHASE_READY
    runtime.configuration_state.revision = attempt.prepared.configuration_revision
    attempt.cancel_requested = True
    cancelled = await runtime.start_session(operator_command(runtime))
    assert cancelled.result == pb.COMMAND_RESULT_REJECTED


def _trial_attempt(runtime: ControllerRuntime, attempt: Attempt) -> pb.TrialPlan:
    trial = pb.TrialContext(session=attempt.context, trial_id=_id(), trial_number=1)
    plan = attempt.prepared.trials.add(context=trial)
    attempt.trial_index = 0
    attempt.trial_log_name = "s_000000_LOG.json"
    attempt.trial_participants = {"visual_stimulus": cast(Any, object())}
    runtime.lifecycle.trial = pb.TrialState(
        context=trial, phase=pb.TRIAL_PHASE_STARTING
    )
    return plan


def _patch_logs(
    runtime: ControllerRuntime, monkeypatch: pytest.MonkeyPatch
) -> tuple[list[dict[str, Any]], list[tuple[str, dict[str, Any]]]]:
    persisted: list[dict[str, Any]] = []
    events: list[tuple[str, dict[str, Any]]] = []

    async def persist(_a: Attempt, _name: str, _kind: str, document: Any) -> None:
        persisted.append(document)

    async def log_event(_a: Attempt, kind: str, **kwargs: Any) -> None:
        events.append((kind, kwargs))

    async def noop(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(trial_logs, "activity_backends", lambda _a: frozenset())
    monkeypatch.setattr(runtime.metadata, "persist", persist)
    monkeypatch.setattr(runtime.metadata, "log_event", log_event)
    monkeypatch.setattr(runtime.trial_logs, "start_trial_log", noop)
    monkeypatch.setattr(runtime.trial_logs.evidence_waiter, "wait_evidence", noop)
    monkeypatch.setattr(
        runtime.trial_logs.evidence_waiter, "wait_lifecycle_with_recovery", noop
    )
    return persisted, events


async def test_interrupted_trial_without_accepted_started_is_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt = _setup(tmp_path, monkeypatch)
    _trial_attempt(runtime, attempt)
    attempt.trial_closure.released = frozenset({"visual_stimulus"})
    persisted, events = _patch_logs(runtime, monkeypatch)
    await runtime.interruption.interrupt(attempt, "abort")
    assert persisted[-1]["outcome"] == "interrupted"
    assert persisted[-1]["start_unconfirmed"] == ["visual_stimulus"]
    assert persisted[-1]["participants_started"] == []
    assert [kind for kind, _ in events].count("trial_finished") == 1
    assert runtime.lifecycle.trial.outcome == pb.TRIAL_OUTCOME_INTERRUPTED
    assert runtime.lifecycle.trial.phase == pb.TRIAL_PHASE_ENDED
    assert runtime.lifecycle.session.phase == pb.SESSION_PHASE_ENDED


async def test_interruption_before_release_creates_no_trial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt = _setup(tmp_path, monkeypatch)
    _trial_attempt(runtime, attempt)
    persisted, events = _patch_logs(runtime, monkeypatch)
    await runtime.interruption.interrupt(attempt, "abort")
    assert not persisted
    assert "trial_finished" not in [kind for kind, _ in events]


async def test_uncertain_trial_finished_is_not_appended_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt = _setup(tmp_path, monkeypatch)
    _trial_attempt(runtime, attempt)
    attempt.trial_closure.released = frozenset({"visual_stimulus"})
    attempt.trial_closure.finish_append_issued = True
    persisted, events = _patch_logs(runtime, monkeypatch)

    async def start() -> None:
        return None

    async def failed() -> None:
        raise TimeoutError("append timed out")

    attempt.trial_log_start_task = asyncio.create_task(start())
    attempt.trial_log_finish_task = asyncio.create_task(failed())
    await asyncio.gather(
        attempt.trial_log_start_task,
        attempt.trial_log_finish_task,
        return_exceptions=True,
    )
    attempt.interruption_issued_ns = 1_000
    attempt.finalization_deadline_ns = 2_000_000_000
    clean = await runtime.trial_logs.finish_interrupted_trial(attempt)
    assert clean is False
    assert not persisted and not events
    assert any("unconfirmed" in warning.message for warning in runtime.control.warnings)


async def test_stop_in_starting_cancels_before_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt = _setup(tmp_path, monkeypatch)
    attempt.activated = False
    runtime.lifecycle.session = pb.SessionState(phase=pb.SESSION_PHASE_STARTING)
    reasons: list[str] = []

    async def interrupt(_attempt: Attempt, reason: str, **_k: object) -> None:
        reasons.append(reason)

    monkeypatch.setattr(runtime.interruption, "interrupt", interrupt)
    command = operator_command(runtime)
    admission = await runtime.stop_after_trial(command)
    await drain_runtime_tasks(runtime)
    assert admission.result == pb.COMMAND_RESULT_ACCEPTED
    assert len(reasons) == 1
    assert not runtime.lifecycle.session.stop_after_trial
    assert command.operator.command_id in attempt.abort_command_ids


async def test_stop_in_starting_after_activation_ends_before_first_trial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt = _setup(tmp_path, monkeypatch)
    runtime.lifecycle.session.phase = pb.SESSION_PHASE_STARTING
    command = operator_command(runtime)
    admission = await runtime.stop_after_trial(command)
    assert admission.result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime.lifecycle.session.stop_after_trial
    assert not attempt.interrupted
    _trial_attempt(runtime, attempt)
    attempt.trial_index = -1
    attempt.prepared.trials[0].resolved_duration_ns = 1
    runtime.lifecycle.trial = pb.TrialState(phase=pb.TRIAL_PHASE_PENDING)
    runtime.lifecycle.session.phase = pb.SESSION_PHASE_RUNNING

    async def never(*_a: object) -> None:
        raise AssertionError("no trial may start")

    monkeypatch.setattr(runtime.trials, "prepare_and_run_trial", never)
    await runtime.trials.run_trials(attempt)
    await drain_runtime_tasks(runtime)
    assert runtime.lifecycle.trial.phase == pb.TRIAL_PHASE_PENDING
    assert runtime.lifecycle.session.phase == pb.SESSION_PHASE_ENDED
    assert runtime.lifecycle.session.outcome == pb.SESSION_OUTCOME_STOPPED


async def test_shutdown_interrupts_at_once_and_completes_after_handoff_and_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt = _setup(tmp_path, monkeypatch)
    handoff_gate = asyncio.Event()
    order: list[str] = []
    result = pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    class Supervisor:
        async def request_shutdown(self, _r: object) -> pb.ReportReceipt:
            order.append("handoff")
            await handoff_gate.wait()
            return result

    runtime.session_commands.supervisor = cast(Any, Supervisor())
    history_path = tmp_path / "history.json"
    runtime.configuration_commands.configuration_history_path = history_path
    runtime.configuration_state.current.subject = "shutdown-retained"
    history_gate = threading.Event()
    original_writer = runtime.configuration_commands._write_history

    def delayed_writer(seq: int, path: Path, payload: bytes) -> None:
        assert history_gate.wait(2)
        original_writer(seq, path, payload)

    monkeypatch.setattr(
        runtime.configuration_commands, "_write_history", delayed_writer
    )
    command = operator_command(runtime)
    await runtime.shutdown_application(command)
    command_id = command.operator.command_id

    async def wait_for_interruption() -> None:
        async with asyncio.timeout(2):
            while runtime.lifecycle.session.phase != pb.SESSION_PHASE_ENDED:
                await asyncio.sleep(0.005)

    await wait_for_interruption()
    # Interruption is not held back by the handoff, while the operation stays pending.
    assert runtime.lifecycle.session.phase == pb.SESSION_PHASE_ENDED
    assert not runtime.control.operations[command_id].complete
    handoff_gate.set()
    await asyncio.sleep(0.02)
    assert not runtime.control.operations[command_id].complete
    history_gate.set()
    await drain_runtime_tasks(runtime)
    operation = runtime.control.operations[command_id]
    assert operation.complete and operation.succeeded
    assert json.loads(history_path.read_text())["configuration"]["subject"] == (
        "shutdown-retained"
    )


async def test_shutdown_with_rejected_handoff_completes_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt = _setup(tmp_path, monkeypatch)

    class Supervisor:
        async def request_shutdown(self, _r: object) -> pb.ReportReceipt:
            return pb.ReportReceipt(
                result=pb.COMMAND_RESULT_REJECTED,
                failure=pb.Failure(code="X", message="supervisor busy"),
            )

    runtime.session_commands.supervisor = cast(Any, Supervisor())
    command = operator_command(runtime)
    await runtime.shutdown_application(command)
    await drain_runtime_tasks(runtime)
    operation = runtime.control.operations[command.operator.command_id]
    assert operation.complete and not operation.succeeded
    assert "supervisor busy" in operation.failure.message
    assert runtime.lifecycle.session.phase == pb.SESSION_PHASE_ENDED


def _cleanup(runtime: Any) -> ManualControlCleanup:
    return ManualControlCleanup(
        lifecycle=runtime.lifecycle,
        configuration=runtime.configuration_state,
        device=runtime.device_state,
        backends=runtime.camera.backends,
        projections=runtime.projections,
        file_policy_loader=None,
        generation=runtime.generation,
        limits=runtime.limit_state,
        clock=runtime.clock,
        hooks=runtime.camera.hooks,
        status_retention=runtime.camera_status_retention,
        retry_delay_s=0.01,
    )


async def test_cancel_background_tasks_stops_cleanup_retry_chain(
    tmp_path: Path,
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _runtime(tmp_path, backend)
    cleanup = _cleanup(runtime)
    calls: list[int] = []

    async def failing_run() -> None:
        calls.append(1)
        await asyncio.sleep(0.05)
        raise RuntimeError("cleanup evidence unavailable")

    cleanup.run = failing_run  # type: ignore[method-assign]
    runtime.lifecycle.manual_control_cleanup_pending = True
    runtime.lifecycle.manual_control_cleanup_task = runtime._spawn(cleanup._task())
    await asyncio.sleep(0.01)

    await runtime.cancel_background_tasks()
    await asyncio.sleep(0.1)

    assert calls == [1]  # the chain did not respawn after shutdown began
    assert not any(not task.done() for task in runtime._tasks)
    current: Any = runtime.lifecycle.manual_control_cleanup_task
    assert current is None or current.done()


async def test_interrupt_finalizes_even_when_trial_log_closure_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = pb.BackendContext(
        backend_name="visual_stimulus", backend_generation=_id()
    )
    runtime = _runtime(tmp_path, backend)
    attempt = _attempt(runtime, tmp_path, {})
    attempt.activated = True
    runtime.lifecycle.attempt = attempt
    runtime.lifecycle.session = pb.SessionState(
        phase=pb.SESSION_PHASE_RUNNING, context=attempt.context, activated=True
    )

    async def broken(_attempt: object) -> bool:
        raise ValueError("unexpected trial log failure")

    finalized: list[bool] = []

    async def finalize(_attempt: object, **kwargs: Any) -> None:
        finalized.append(kwargs["metadata_clean"])

    monkeypatch.setattr(runtime.trial_logs, "finish_interrupted_trial", broken)
    monkeypatch.setattr(runtime.interruption, "finalize", finalize)

    await runtime.interruption.interrupt(attempt, "operator Abort now")

    assert finalized == [False]
    assert any(
        w.component == "interruption" and "unexpected trial log failure" in w.message
        for w in runtime.control.warnings
    )


async def test_owner_cleanup_releases_prepared_preview_like_setup_guard(
    tmp_path: Path,
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _runtime(tmp_path, backend)
    views = pb.AcquisitionDeviceViews()
    view = views.behavioral
    view.device_open = False
    view.preview_running = False
    view.cleanup_pending = False
    view.preview_prepared = True
    views.tracking.device_open = False
    views.tracking.preview_running = False
    views.tracking.cleanup_pending = False
    runtime.projections.devices = views
    # Setup is blocked by the prepared preview...
    assert manual_camera_owned(runtime.projections, runtime.device_state)
    runtime.lifecycle.manual_control_cleanup_pending = True

    # ...so owner cleanup must not declare success without stopping it.
    with pytest.raises(RuntimeError, match="no cleanup backend settings"):
        await _cleanup(runtime).run()
    assert runtime.lifecycle.manual_control_cleanup_pending
