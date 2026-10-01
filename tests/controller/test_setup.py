"""Setup admission, mutable limits, cancellation and session scope."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
from pathlib import Path
from typing import cast

import pytest

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.configuration import ControllerConfiguration, SupervisorStartup
from cephvr.controller.ports import BackendPort
from cephvr.controller.runtime import ControllerRuntime
from cephvr.controller.state import (
    Attempt,
    ControllerLimits,
)
from tests.controller.support_components import (
    TaskCapture,
    _attempt,
    _id,
    _RetainedPeer,
    _runtime,
    drain_runtime_tasks,
    operator_command,
)


def _settings(limits: ControllerLimits) -> ControllerConfiguration:
    return ControllerConfiguration(
        configuration=pb.ExperimentConfiguration(),
        policies=pb.ControlPolicies(),
        limits_kwargs=asdict(limits),
        supervisor_startup=SupervisorStartup(
            50052, 1_000, 2_000, 3_000, 4_000, 5_000, 6_000
        ),
        controller_port=50051,
        max_message_bytes=16_777_216,
        max_pending_events=32,
        max_pending_payload_bytes=1_000_000,
        max_retained_incidents=limits.max_retained_incidents,
        default_intertrial_gap_ns=1_000,
        history_warning=None,
    )


async def test_setup_reloads_mutable_limits_and_freezes_them_in_prepared_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    visual_stimulus = pb.BackendContext(
        backend_name="visual_stimulus", backend_generation=_id()
    )
    runtime = _runtime(tmp_path, visual_stimulus)
    runtime.setup_admission.backends = {
        "visual_stimulus": cast(
            BackendPort, _RetainedPeer(visual_stimulus, svc.RetainedResult())
        )
    }
    runtime.supervisor_state.processes["visual_stimulus"] = svc.ProcessHealthStatus(
        process=pb.ProcessIdentity(
            role="visual_stimulus", generation=visual_stimulus.backend_generation
        ),
        process_running=True,
        connected=True,
    )
    runtime.configuration_state.current.mode = pb.SESSION_MODE_OPEN_LOOP
    runtime.configuration_state.current.recording_root = str(tmp_path)
    runtime.configuration_state.current.experiment = "experiment"
    runtime.configuration_state.current.subject = "subject"
    runtime.configuration_state.current.backends.add(
        backend_name="visual_stimulus", enabled=True
    )
    runtime.configuration_state.current.trials.add(trial_number=1)
    runtime.setup_admission.validators = {
        "structural": lambda _: pb.ValidationResult(completed=True, valid=True)
    }
    runtime.setup_admission.file_policy_loader = lambda active: (
        {}
        if active == frozenset({"visual_stimulus"})
        else (_ for _ in ()).throw(AssertionError("wrong active policy set"))
    )
    baseline = _settings(runtime.limits)
    adopted = replace(
        baseline, limits_kwargs={**baseline.limits_kwargs, "setup_ns": 20_000}
    )
    runtime.setup_admission.startup_settings = baseline
    runtime.setup_admission.settings_loader = lambda: adopted
    monkeypatch.setattr(runtime.control_operations, "authorized", lambda _command: "")

    async def no_backend_dispatch(
        _attempt: Attempt, _command_id: str, _deadline_ns: int
    ) -> None:
        return None

    monkeypatch.setattr(runtime.setup_execution, "run_setup", no_backend_dispatch)
    tasks = TaskCapture(runtime.setup_admission.spawn)
    runtime.setup_admission.spawn = tasks.spawn
    command = svc.OperatorCommand()
    command.operator.command_id = _id()
    admission = await runtime.setup(command)
    assert admission.result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime.lifecycle.attempt is not None
    assert runtime.limits.setup_ns == 20_000
    assert runtime.lifecycle.attempt.prepared.policies == adopted.policies
    assert (
        runtime.lifecycle.attempt.setup_deadline_ns
        - runtime.lifecycle.attempt.prepared.anchor_monotonic_ns
        == 20_000
    )
    await tasks.drain()


async def test_setup_rejects_changed_startup_transport_settings_before_reservation(
    tmp_path: Path,
) -> None:
    runtime = _runtime(
        tmp_path,
        pb.BackendContext(backend_name="acquisition", backend_generation=_id()),
    )
    runtime.setup_admission.validators = {
        "structural": lambda _: pb.ValidationResult(completed=True, valid=True)
    }
    baseline = _settings(runtime.limits)
    runtime.setup_admission.startup_settings = baseline
    runtime.setup_admission.settings_loader = lambda: replace(
        baseline, controller_port=50053
    )
    command = svc.OperatorCommand()
    command.operator.command_id = _id()

    admission = await runtime.setup(command)
    assert admission.result == pb.COMMAND_RESULT_REJECTED
    assert "restart required" in admission.failure.message
    assert runtime.lifecycle.attempt is None


async def test_setup_admission_is_blocked_while_manual_loss_cleanup_is_unresolved(
    tmp_path: Path,
) -> None:
    runtime = _runtime(
        tmp_path,
        pb.BackendContext(backend_name="acquisition", backend_generation=_id()),
    )
    runtime.setup_admission.validators = {
        "structural": lambda _: pb.ValidationResult(completed=True, valid=True)
    }
    runtime.lifecycle.manual_control_cleanup_pending = True
    command = svc.OperatorCommand()
    command.operator.command_id = _id()

    admission = await runtime.setup(command)

    assert admission.result == pb.COMMAND_RESULT_REJECTED
    assert "manual camera cleanup" in admission.failure.message
    assert runtime.lifecycle.attempt is None


async def test_startup_recovery_cancel_preserves_blocker_then_continue_clears_after_handler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(
        tmp_path,
        pb.BackendContext(backend_name="acquisition", backend_generation=_id()),
    )
    runtime.limit_state.current = replace(
        runtime.limits, setup_cancel_ns=200_000_000, recovery_ns=200_000_000
    )
    prompt = pb.Prompt(
        prompt_id=_id(),
        setup=pb.SessionContext(controller_generation=_id(), session_id=_id()),
        operation=pb.OperationContext(command_id=_id()),
        explanation="Prior reservation requires repair",
        permitted_choices=["continue", "cancel"],
    )
    gate = asyncio.Event()

    async def handler() -> None:
        await gate.wait()

    await runtime.install_startup_recovery(
        prompt,
        handler,
        "prior reservation is unresolved",
        completion_warning="remote stop remains unconfirmed",
    )
    monkeypatch.setattr(runtime.control_operations, "authorized", lambda _command: "")
    tasks = TaskCapture(runtime.prompts.spawn)
    runtime.prompts.spawn = tasks.spawn
    cancel = svc.PromptResponse(
        prompt_id=prompt.prompt_id,
        setup=prompt.setup,
        setup_operation=prompt.operation,
        choice="cancel",
    )
    cancel.command.operator.command_id = _id()
    accepted_cancel = await runtime.respond_to_prompt(cancel)
    assert accepted_cancel.result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime.lifecycle.startup_blocker
    assert runtime.lifecycle.startup_prompt == prompt
    assert runtime.control.operations[cancel.command.operator.command_id].complete

    proceed = svc.PromptResponse(
        prompt_id=prompt.prompt_id,
        setup=prompt.setup,
        setup_operation=prompt.operation,
        choice="continue",
    )
    proceed.command.operator.command_id = _id()
    accepted_continue = await runtime.respond_to_prompt(proceed)
    assert accepted_continue.result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime.lifecycle.startup_blocker
    gate.set()
    await tasks.drain()
    assert not runtime.lifecycle.startup_blocker
    assert runtime.lifecycle.startup_prompt is None
    assert runtime.control.operations[proceed.command.operator.command_id].complete
    assert runtime.control.operations[proceed.command.operator.command_id].succeeded
    assert any(
        "remote stop remains unconfirmed" in warning.message
        for warning in runtime.control.warnings
    )


@pytest.mark.parametrize("trial_number", [2, 1])
async def test_reloaded_limits_are_applied_only_on_accepted_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, trial_number: int
) -> None:
    visual_stimulus = pb.BackendContext(
        backend_name="visual_stimulus", backend_generation=_id()
    )
    runtime = _runtime(tmp_path, visual_stimulus)
    runtime.setup_admission.backends = {
        "visual_stimulus": cast(
            BackendPort, _RetainedPeer(visual_stimulus, svc.RetainedResult())
        )
    }
    runtime.supervisor_state.processes["visual_stimulus"] = svc.ProcessHealthStatus(
        process=pb.ProcessIdentity(
            role="visual_stimulus", generation=visual_stimulus.backend_generation
        ),
        process_running=True,
        connected=True,
    )
    current = runtime.configuration_state.current
    current.mode = pb.SESSION_MODE_OPEN_LOOP
    current.recording_root = str(tmp_path)
    current.experiment = "experiment"
    current.subject = "subject"
    current.backends.add(backend_name="visual_stimulus", enabled=True)
    current.trials.add(trial_number=trial_number)  # 2 is rejected after the reload
    runtime.setup_admission.validators = {
        "structural": lambda _: pb.ValidationResult(completed=True, valid=True)
    }
    runtime.setup_admission.file_policy_loader = lambda active: {}
    baseline = _settings(runtime.limits)
    adopted = replace(
        baseline, limits_kwargs={**baseline.limits_kwargs, "setup_ns": 20_000}
    )
    runtime.setup_admission.startup_settings = baseline
    runtime.setup_admission.settings_loader = lambda: adopted
    monkeypatch.setattr(runtime.control_operations, "authorized", lambda _command: "")

    async def no_dispatch(*_args: object) -> None:
        return None

    monkeypatch.setattr(runtime.setup_execution, "run_setup", no_dispatch)
    before = runtime.limits.setup_ns
    command = svc.OperatorCommand()
    command.operator.command_id = _id()
    admission = await runtime.setup(command)

    if trial_number == 1:
        assert admission.result == pb.COMMAND_RESULT_ACCEPTED
        assert runtime.limits.setup_ns == 20_000
    else:
        assert admission.result == pb.COMMAND_RESULT_REJECTED
        assert "one-based" in admission.failure.message
        assert runtime.limits.setup_ns == before
        assert runtime.lifecycle.attempt is None


def _cancelling_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ControllerRuntime, Attempt, str]:
    runtime = _runtime(
        tmp_path,
        pb.BackendContext(backend_name="visual_stimulus", backend_generation=_id()),
    )
    attempt = _attempt(runtime, tmp_path, {})
    runtime.lifecycle.attempt = attempt
    runtime.lifecycle.session = pb.SessionState(
        phase=pb.SESSION_PHASE_SETTING_UP, context=attempt.context
    )
    setup_id = _id()
    attempt.setup_command_id = setup_id
    runtime.control.operations[setup_id] = pb.OperationState(
        context=pb.OperationContext(command_id=setup_id), command="SetupSession"
    )
    for owner in (runtime.cleanup, runtime.session_commands):
        monkeypatch.setattr(owner.control_operations, "authorized", lambda *a, **k: "")

    async def fenced(*_args: object) -> bool:
        return True

    monkeypatch.setattr(runtime.cleanup, "register_cleanup_fences", fenced)
    return runtime, attempt, setup_id


def _assert_cancelled(runtime: ControllerRuntime, setup_id: str) -> None:
    operation = runtime.control.operations[setup_id]
    assert operation.complete and not operation.succeeded
    assert operation.failure.message.startswith("setup cancelled:")
    assert operation.progress == "interruption and cleanup confirmed"


async def _prompt(runtime: ControllerRuntime) -> tuple[asyncio.Future[str], str]:
    for _ in range(200):
        if runtime.incident_state.prompts:
            prompt, future, _owner = next(iter(runtime.incident_state.prompts.values()))
            return future, prompt.prompt_id
        await asyncio.sleep(0.005)
    raise AssertionError("no Setup prompt")


async def test_prompt_cancel_choice_completes_setup_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt, setup_id = _cancelling_setup(tmp_path, monkeypatch)
    runtime.limit_state.current = replace(runtime.limits, low_space_bytes=2**62)
    task = asyncio.create_task(
        runtime.setup_execution.run_setup(attempt, setup_id, 10**12)
    )
    future, _ = await _prompt(runtime)
    future.set_result("cancel")
    await task
    _assert_cancelled(runtime, setup_id)


async def test_cancel_setup_during_pending_prompt_completes_setup_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt, setup_id = _cancelling_setup(tmp_path, monkeypatch)
    runtime.limit_state.current = replace(runtime.limits, low_space_bytes=2**62)
    task = asyncio.create_task(
        runtime.setup_execution.run_setup(attempt, setup_id, 10**12)
    )
    await _prompt(runtime)
    admission = await runtime.cleanup.cancel_setup(operator_command(runtime))
    assert admission.result == pb.COMMAND_RESULT_ACCEPTED
    await asyncio.gather(task, return_exceptions=True)
    await drain_runtime_tasks(runtime)
    _assert_cancelled(runtime, setup_id)


async def test_cancel_setup_during_evidence_wait_completes_setup_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt, setup_id = _cancelling_setup(tmp_path, monkeypatch)

    async def reserved(*_args: object) -> int:
        return 10**12

    async def waiting(att: Attempt, *_args: object) -> tuple[int, object]:
        await runtime.setup_execution.evidence_waiter.wait_evidence(
            lambda: False, 300_001_000, att
        )
        raise AssertionError("unreachable")

    monkeypatch.setattr(runtime.setup_execution, "_reserve_output", reserved)
    monkeypatch.setattr(runtime.setup_execution, "_prepare_participants", waiting)
    task = asyncio.create_task(
        runtime.setup_execution.run_setup(attempt, setup_id, 10**12)
    )
    await asyncio.sleep(0.05)
    await runtime.cleanup.cancel_setup(operator_command(runtime))
    await asyncio.gather(task, return_exceptions=True)
    await drain_runtime_tasks(runtime)
    operation = runtime.control.operations[setup_id]
    assert operation.complete and not operation.succeeded
    assert operation.failure.message
    assert runtime.lifecycle.attempt is None


async def test_unclean_cancel_keeps_session_context_for_safety_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt, _setup_id = _cancelling_setup(tmp_path, monkeypatch)
    monkeypatch.undo()  # keep the real authorization check

    async def fenced(*_args: object) -> bool:
        return True

    monkeypatch.setattr(runtime.cleanup, "register_cleanup_fences", fenced)
    attempt.reservation_registration_started = True  # unconfirmed registration
    attempt.reservation_registered = False
    await runtime.cleanup.cancel_attempt(attempt)

    assert runtime.lifecycle.attempt is attempt  # retained after unclean cleanup
    session = runtime.lifecycle.session
    assert session.phase == pb.SESSION_PHASE_CONFIGURATION
    assert session.context == attempt.context
    # The headless client builds expected_work from the published session context.
    client, watch, lease = _id(), _id(), _id()
    runtime.control.owner = (client, watch, lease)
    runtime.control.watches[(client, watch)] = object()  # type: ignore[assignment]
    command = operator_command(runtime)
    command.operator.client_id = client
    command.operator.control_generation = lease
    assert (
        runtime.control_operations.authorized(command, safety="abort")
        == "expected work is required"
    )
    command.expected_work.session.CopyFrom(session.context)
    for safety in ("abort", "shutdown"):
        assert runtime.control_operations.authorized(command, safety=safety) == ""  # type: ignore[arg-type]


def _scoped_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ControllerRuntime, Attempt]:
    runtime = _runtime(
        tmp_path,
        pb.BackendContext(backend_name="visual_stimulus", backend_generation=_id()),
    )
    attempt = _attempt(runtime, tmp_path, {})
    assert attempt.reservation.acquire() == []
    runtime.lifecycle.attempt = attempt
    runtime.lifecycle.session = pb.SessionState(
        phase=pb.SESSION_PHASE_SETTING_UP, context=attempt.context
    )
    runtime.projections.set_scope(
        pb.WorkContext(session=attempt.context), runtime.configuration_state.revision
    )
    for owner in (runtime.cleanup, runtime.configuration_commands):
        monkeypatch.setattr(owner.control_operations, "authorized", lambda *a, **k: "")

    async def fenced(*_args: object) -> bool:
        return True

    monkeypatch.setattr(runtime.cleanup, "register_cleanup_fences", fenced)
    return runtime, attempt


async def test_cancelled_setup_leaves_sessionless_current_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt = _scoped_setup(tmp_path, monkeypatch)
    runtime.configuration_state.revision = 7
    await runtime.cleanup.cancel_attempt(attempt)
    assert runtime.projections.work.WhichOneof("work") is None
    assert runtime.projections.configuration_revision == 7


async def test_failed_setup_leaves_sessionless_current_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, attempt = _scoped_setup(tmp_path, monkeypatch)
    command_id = _id()
    runtime.control.operations[command_id] = pb.OperationState(
        context=pb.OperationContext(command_id=command_id), command="Setup"
    )
    await runtime.setup_execution.fail_setup(attempt, command_id, "boom")
    assert runtime.projections.work.WhichOneof("work") is None
    assert (
        runtime.projections.configuration_revision
        == runtime.configuration_state.revision
    )


async def test_update_configuration_refreshes_projection_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, _attempt_ = _scoped_setup(tmp_path, monkeypatch)
    runtime.lifecycle.attempt = None
    runtime.lifecycle.session = pb.SessionState(phase=pb.SESSION_PHASE_CONFIGURATION)
    runtime.configuration_commands.validators = {
        "v": lambda _c: pb.ValidationResult(completed=True, valid=True)
    }
    proposed = pb.ExperimentConfiguration()
    proposed.CopyFrom(runtime.configuration_state.current)
    proposed.experiment = "changed"
    request = svc.UpdateConfigurationRequest(
        expected_revision=runtime.configuration_state.revision, proposed=proposed
    )
    request.command.operator.command_id = _id()
    receipt = await runtime.update_configuration(request)
    assert receipt.result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime.projections.configuration_revision == (
        runtime.configuration_state.revision
    )
