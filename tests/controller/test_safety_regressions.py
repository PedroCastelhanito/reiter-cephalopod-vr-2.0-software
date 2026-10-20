"""E05/E06/E07 evidence and lifecycle regression tests against real state logic."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.metadata.reservation import OutputReservation
from cephvr.controller.ports import BackendPort
from cephvr.controller.runtime import ControllerRuntime
from cephvr.controller.state import Attempt, ControllerLimits
from tests.controller.support_components import _id


@pytest.mark.parametrize("authority_loss", [False, True])
async def test_interrupt_delivery_is_independent_and_keeps_original_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, authority_loss: bool
) -> None:
    runtime = _runtime(tmp_path)
    attempt, _ = _attempt(runtime, tmp_path)
    runtime.limit_state.current = replace(
        runtime.limit_state.current, stop_evidence_ns=20_000_000
    )
    attempt.interruption_issued_ns = 500
    calls: dict[str, int] = {}
    requests: list[svc.InterruptSessionRequest] = []
    cancelled = asyncio.Event()

    class Peer:
        def __init__(self, name: str) -> None:
            self.context = pb.BackendContext(
                backend_name=name, backend_generation=_id()
            )

        async def interrupt_session(self, request: Any, *, deadline_ns: int) -> None:
            name = self.context.backend_name
            calls[name] = deadline_ns
            requests.append(request)
            if name == "acquisition":
                raise OSError("peer unavailable")
            if name == "tracking":
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

    attempt.required = {
        name: cast(BackendPort, Peer(name))
        for name in ("acquisition", "visual_stimulus", "tracking")
    }

    if authority_loss:
        await runtime.interruption.authority_emergency_interrupt(attempt, "lost owner")
    else:
        await runtime.interruption._stop_backends(attempt, "abort")
    assert calls == dict.fromkeys(attempt.required, 20_000_500)
    assert cancelled.is_set()
    assert all(request.command.work.session == attempt.context for request in requests)
    assert all(request.issued_monotonic_ns == 500 for request in requests)


def _runtime(tmp_path: Path, *, now: int = 1_000) -> ControllerRuntime:
    limits = ControllerLimits(
        setup_ns=1_000,
        setup_cancel_ns=1_000,
        ready_ns=1_000,
        finished_ns=1_000,
        registration_ns=1_000_000_000,
        recovery_ns=1_000,
        metadata_ns=1_000,
        validation_ns=1_000_000_000,
        lead_ns=500,
        controller_release_ns=100,
        backend_release_ns=50,
        start_evidence_ns=250,
        stop_evidence_ns=250,
        max_metadata_operations=8,
        max_metadata_bytes=4096,
        history_ns=1_000,
        space_query_ns=1_000,
        low_space_bytes=1,
    )
    return ControllerRuntime(
        generation=_id(),
        configuration=pb.ExperimentConfiguration(recording_root=str(tmp_path)),
        limits=limits,
        validators={},
        backends={},
        clock=lambda: now,
    )


def _attempt(
    runtime: ControllerRuntime, tmp_path: Path
) -> tuple[Attempt, pb.BackendContext]:
    session = pb.SessionContext(
        controller_generation=runtime.generation, session_id=_id()
    )
    trial = pb.TrialContext(session=session, trial_id=_id(), trial_number=1)
    prepared = pb.PreparedSession(context=session, configuration_revision=1)
    prepared.trials.add(context=trial, resolved_duration_ns=60_000_000_000)
    reservation = OutputReservation(
        tmp_path,
        "experiment",
        "subject",
        session.session_id,
        runtime.generation,
        datetime(2026, 9, 29, tzinfo=UTC),
    )
    backend = pb.BackendContext(
        backend_name="visual_stimulus", backend_generation=_id()
    )
    # Report validation only needs the registered peer's exact context.
    peer = cast(BackendPort, type("Peer", (), {"context": backend})())
    attempt = Attempt(
        session,
        prepared,
        reservation,
        {"visual_stimulus": peer},
        {"visual_stimulus": _id()},
    )
    runtime.lifecycle.attempt = attempt
    return attempt, backend


def _context(
    attempt: Attempt, backend: pb.BackendContext, *, trial: bool
) -> pb.ReportContext:
    work = (
        pb.WorkContext(trial=attempt.prepared.trials[0].context)
        if trial
        else pb.WorkContext(session=attempt.context)
    )
    command_id = (
        attempt.trial_operation
        if trial
        else attempt.setup_operations["visual_stimulus"]
    )
    return pb.ReportContext(
        backend=backend,
        work=work,
        operation=pb.OperationContext(command_id=command_id),
    )


async def test_ready_arriving_after_original_setup_deadline_cannot_revive_attempt(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    attempt, backend = _attempt(runtime, tmp_path)
    runtime.lifecycle.session.phase = pb.SESSION_PHASE_SETTING_UP
    attempt.setup_deadline_ns = 999
    report = pb.LifecycleReport(
        ready=pb.ReadyReport(
            context=_context(attempt, backend, trial=False),
            configuration_revision=runtime.configuration_state.revision,
            required_checks_passed=True,
        )
    )
    receipt = await runtime.report_lifecycle(report, ingress_ns=1_000)
    assert receipt.result == pb.COMMAND_RESULT_REJECTED
    assert not attempt.ready


async def test_finished_before_end_or_with_failed_output_cannot_complete_trial(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    attempt, backend = _attempt(runtime, tmp_path)
    runtime.lifecycle.trial.phase = pb.TRIAL_PHASE_RUNNING
    attempt.trial_index = 0
    attempt.trial_operation = _id()
    attempt.end_ns = 1_000
    attempt.finished_deadline_ns = 2_000
    output = attempt.prepared.outputs.add(
        backend=backend,
        output_key="reserved",
        path=str(tmp_path / "stimulus_LOG.json"),
        trial=attempt.prepared.trials[0].context,
        output_tag="stimulus_LOG",
        extension="json",
    )
    result = pb.OutputResult(
        output_key=output.output_key,
        path=output.path,
        closure=pb.OUTPUT_CLOSURE_CLOSED,
        artifact_present=True,
    )
    report = pb.LifecycleReport(
        finished=pb.FinishedReport(
            context=_context(attempt, backend, trial=True),
            trial_activity_stopped=True,
            outputs=[result],
        )
    )
    early = await runtime.report_lifecycle(report, ingress_ns=999)
    assert early.result == pb.COMMAND_RESULT_REJECTED
    assert not attempt.finished
    report.finished.outputs[0].failure.CopyFrom(
        pb.Failure(code="WRITER_FAILED", message="flush failed")
    )
    failed = await runtime.report_lifecycle(report, ingress_ns=1_000)
    assert failed.result == pb.COMMAND_RESULT_REJECTED
    assert not attempt.finished


async def test_ready_edit_cancels_preparation_without_committing_unvalidated_resources(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    attempt, _ = _attempt(runtime, tmp_path)
    runtime.lifecycle.session.phase = pb.SESSION_PHASE_READY
    runtime.configuration_commands.validators = {
        "experiment": lambda _: pb.ValidationResult(
            completed=True,
            valid=True,
            component="experiment",
            configuration_module_version="test-v1",
        )
    }
    client_id = _id()
    watch_id = _id()
    watch = await runtime.open_watch(client_id, watch_id)
    await runtime.delivered_watch_view(watch, runtime.control.revision)
    claim = await runtime.claim(
        svc.ControlClaim(
            client_id=client_id,
            watch_id=watch_id,
            command_id=_id(),
            controller_generation=runtime.generation,
            synchronized_state_revision=runtime.control.revision,
        )
    )
    assert claim.result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime.control.owner is not None
    proposed = pb.ExperimentConfiguration(subject="new-subject")
    request = svc.UpdateConfigurationRequest(
        command=svc.OperatorCommand(
            controller_generation=runtime.generation,
            operator=pb.OperatorContext(
                client_id=client_id,
                command_id=_id(),
                control_generation=runtime.control.owner[2],
            ),
        ),
        expected_revision=runtime.configuration_state.revision,
        proposed=proposed,
    )
    result = await runtime.update_configuration(request)
    assert result.result == pb.COMMAND_RESULT_ACCEPTED
    assert attempt.cancel_requested
    assert runtime.configuration_state.current.subject == "new-subject"
    await runtime.close_watch(watch)


@pytest.mark.parametrize("brightness_observed", [False, True])
@pytest.mark.parametrize("interrupt_on_start", [False, True])
async def test_start_terminal_operation_time_and_interruption_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interrupt_on_start: bool,
    brightness_observed: bool,
) -> None:
    runtime = _runtime(tmp_path)
    attempt, _ = _attempt(runtime, tmp_path)
    attempt.required.clear()
    assert attempt.reservation.acquire() == []
    runtime.lifecycle.session.phase = pb.SESSION_PHASE_STARTING
    runtime.start.schema_factory = lambda _: {"schema_version": 1}

    class Supervisor:
        async def register_context(
            self, request: svc.RegisterContextRequest
        ) -> svc.RegistrationReceipt:
            return svc.RegistrationReceipt(
                admission=pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED),
                registered=request.context,
            )

    runtime.start.supervisor = cast(Any, Supervisor())

    evidence = {
        "schema_version": 1,
        "outcome": "failed",
        "requested_ma": 1500,
        "sdk_result": {"interfaces": [{"id": "usb0", "readback_ma": {"red": 1023}}]},
    }
    if brightness_observed:
        runtime.device_state.projector_brightness = evidence
    documents = {}

    async def persisted(_attempt, name, action, document):
        documents[name] = document
        return object()

    started_log_seen = False
    logged_events: list[tuple[str, object]] = []
    override = {"check": "recording_space", "free_bytes": 5, "reason": "low space"}
    attempt.overrides.append(override)

    async def logged(_attempt: Attempt, event_type: str, **kwargs: object) -> None:
        nonlocal started_log_seen
        logged_events.append((event_type, kwargs.get("details")))
        if event_type == "session_started" and not started_log_seen:
            started_log_seen = True
            if interrupt_on_start:
                await runtime.interruption.interrupt(
                    attempt, "concurrent authority loss"
                )

    monkeypatch.setattr(runtime.metadata, "persist", persisted)
    monkeypatch.setattr(runtime.metadata, "log_event", logged)

    async def no_trials(_attempt: Attempt) -> None:
        return None

    monkeypatch.setattr(runtime.trials, "run_trials", no_trials)
    command_id = _id()
    runtime.control.operations[command_id] = pb.OperationState(
        context=pb.OperationContext(command_id=command_id), command="StartSession"
    )
    try:
        await runtime.start.run_start(attempt, command_id)
        captured = documents["SESSION_CONFIG.json"]["projector_brightness"]
        if brightness_observed:
            assert captured == evidence
            evidence["sdk_result"]["interfaces"][0]["readback_ma"]["red"] = 999
            assert captured["sdk_result"]["interfaces"][0]["readback_ma"]["red"] == 1023
        else:
            assert captured["outcome"] == "unknown"
            assert "requested_ma" not in captured
        assert started_log_seen
        operation = runtime.control.operations[command_id]
        if interrupt_on_start:
            assert attempt.interrupted
            assert runtime.lifecycle.session.phase != pb.SESSION_PHASE_RUNNING
            if operation.complete:
                assert not operation.succeeded
                assert runtime.control.operation_finished_ns[command_id] == 1_000
            else:
                assert command_id not in runtime.control.operation_finished_ns
        else:
            assert runtime.lifecycle.session.phase == pb.SESSION_PHASE_RUNNING
            assert logged_events == [
                ("session_started", None),
                ("setup_override", override),
            ]
            assert operation.complete and operation.succeeded
            assert operation.progress == "session activated"
            assert runtime.control.operation_finished_ns[command_id] == 1_000
    finally:
        await runtime.cancel_background_tasks()
        if attempt.reservation.held:
            attempt.reservation.release()


@pytest.mark.parametrize(
    "dispatch_delta,receipt_delta", [(-1, -1), (0, 0), (1, 0), (0, 1)]
)
async def test_release_preserves_controller_100ms_and_backend_50ms_cutoffs(
    tmp_path, dispatch_delta, receipt_delta
):
    from cephvr.controller.lifecycle.trials import TrialSchedule
    from tests.controller.support_components import _attempt as component_attempt
    from tests.controller.support_components import _runtime as component_runtime

    context = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = component_runtime(tmp_path, context)
    attempt = component_attempt(runtime, tmp_path, {})
    target = 1_000_000_000
    dispatch_cutoff, receipt_cutoff = target - 100_000_000, target - 50_000_000
    now = [dispatch_cutoff + dispatch_delta]
    runtime.trials.clock = lambda: now[0]
    seen = []

    class Peer:
        async def release_trial(self, request, *, deadline_ns):
            seen.append((request, deadline_ns))
            now[0] = receipt_cutoff + receipt_delta
            return pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED)

    peer = Peer()
    peer.context = context
    attempt.trial_participants["acquisition"] = peer
    attempt.schedule_operations["acquisition"] = _id()
    plan = pb.TrialPlan(
        context=pb.TrialContext(session=attempt.context, trial_id=_id(), trial_number=1)
    )
    schedule = TrialSchedule(
        target, target + 1_000_000_000, dispatch_cutoff, receipt_cutoff, "prefix"
    )
    if dispatch_delta > 0 or receipt_delta > 0:
        with pytest.raises(TimeoutError):
            await runtime.trials._release_participants(attempt, plan, schedule)
    else:
        await runtime.trials._release_participants(attempt, plan, schedule)
    assert bool(seen) is (dispatch_delta <= 0)
    if seen:
        assert seen[0][1] == receipt_cutoff
        assert (
            seen[0][0].schedule_operation.command_id
            == attempt.schedule_operations["acquisition"]
        )
