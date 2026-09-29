"""Controller state must not turn late device evidence into successful admission."""

from __future__ import annotations

import asyncio
import time
import uuid
from concurrent.futures import Future
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.configuration import ControllerConfiguration, SupervisorStartup
from cephvr.controller.runtime import (
    Attempt,
    BackendPort,
    CameraOperation,
    ControllerLimits,
    ControllerRuntime,
    _active_configuration_document,
)
from cephvr.controller.storage import (
    MetadataCompletion,
    MetadataWriter,
    OutputReservation,
)


def _id() -> str:
    return str(uuid.uuid4())


def _runtime(path: Path, backend: pb.BackendContext) -> ControllerRuntime:
    limits = ControllerLimits(
        setup_ns=1_000,
        setup_cancel_ns=1_000,
        ready_ns=1_000,
        finished_ns=1_000,
        registration_ns=1_000,
        recovery_ns=1_000,
        metadata_ns=1_000,
        validation_ns=1_000,
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
    peer = cast(BackendPort, type("Peer", (), {"context": backend})())
    return ControllerRuntime(
        generation=_id(),
        configuration=pb.ExperimentConfiguration(),
        recording_root=path,
        limits=limits,
        validators={},
        backends={"acquisition": peer},
        clock=lambda: 1_000,
    )


def _attempt(
    runtime: ControllerRuntime, path: Path, required: dict[str, BackendPort]
) -> Attempt:
    context = pb.SessionContext(
        controller_generation=runtime.generation, session_id=_id()
    )
    prepared = pb.PreparedSession(
        context=context, configuration_revision=runtime.configuration_revision
    )
    reservation = OutputReservation(
        path,
        "experiment",
        "subject",
        context.session_id,
        runtime.generation,
        datetime.now(UTC),
    )
    return Attempt(context, prepared, reservation, required, {})


class _RetainedPeer:
    def __init__(
        self, context: pb.BackendContext, retained: svc.RetainedResult
    ) -> None:
        self.context = context
        self.retained = retained
        self.queries: list[svc.RetainedResultQuery] = []

    async def get_retained_result(
        self, request: svc.RetainedResultQuery
    ) -> svc.RetainedResult:
        self.queries.append(request)
        return self.retained


class _RetiringWriter:
    def __init__(self) -> None:
        self.retired: list[str] = []

    def retire(self, command_id: str) -> None:
        self.retired.append(command_id)


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

    document = _active_configuration_document(config)
    text = str(document)
    assert "camera-1" in text
    assert "SDK SECRET SNAPSHOT" not in text
    assert "dormant-camera" not in text
    assert "dormant-pipeline" not in text
    assert (
        config.backends[0].acquisition.behavioral.device.pfs_baseline.text
        == "SDK SECRET SNAPSHOT"
    )


@pytest.mark.asyncio
async def test_late_camera_completion_reconciles_blocker_without_reviving_success(
    tmp_path: Path,
) -> None:
    backend = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _runtime(tmp_path, backend)
    parent, child = _id(), _id()
    runtime._operation(parent, "ExecuteCameraCommand")
    runtime._camera_operation = CameraOperation(
        parent,
        child,
        1,
        1,
        svc.CAMERA_COMMAND_KIND_START_PREVIEW,
        pb.WorkContext(),
        999,
        False,
    )

    await runtime._camera_timeout(child, 999)
    assert runtime._camera_operation is not None
    assert runtime._operations[parent].complete
    assert not runtime._operations[parent].succeeded

    status = svc.AcquisitionDeviceStatusReport()
    status.views.source.CopyFrom(backend)
    status.views.state_revision = 1
    status.views.observed_monotonic_ns = 1_000
    status.views.behavioral.preview_running = True
    status.views.behavioral.preview_run_id = _id()
    status.views.behavioral.device_open = True
    status.operation.command_id = child
    status.result.context.command_id = child
    status.result.complete = True
    status.result.succeeded = True
    receipt = await runtime.report_projection("devices", status, ingress_ns=1_000)

    assert receipt.result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime._camera_operation is None
    assert runtime._operations[parent].complete
    assert not runtime._operations[parent].succeeded
    assert runtime.projections.devices is not None
    assert runtime.projections.devices.behavioral.preview_running


@pytest.mark.asyncio
async def test_ready_recovery_queries_frozen_missing_peer_once_without_accepting_ungated_push(
    tmp_path: Path,
) -> None:
    context = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    runtime = _runtime(tmp_path, context)
    runtime.clock = time.monotonic_ns
    runtime.limits = replace(runtime.limits, recovery_ns=200_000_000)
    attempt = _attempt(runtime, tmp_path, {})
    command_id = _id()
    attempt.setup_operations["acquisition"] = command_id
    attempt.setup_deadline_ns = runtime.clock() - 1_000_000
    ready = pb.ReadyReport(configuration_revision=1, required_checks_passed=True)
    ready.context.backend.CopyFrom(context)
    ready.context.work.session.CopyFrom(attempt.context)
    ready.context.operation.command_id = command_id
    retained = svc.RetainedResult(
        found=True,
        backend=context,
        work=pb.WorkContext(session=attempt.context),
        ready=ready,
    )
    peer = _RetainedPeer(context, retained)
    attempt.required["acquisition"] = cast(BackendPort, peer)
    runtime.attempt = attempt
    runtime.session = pb.SessionState(
        phase=pb.SESSION_PHASE_SETTING_UP, context=attempt.context
    )

    late_push = await runtime.report_lifecycle(
        pb.LifecycleReport(ready=ready), runtime.clock()
    )
    assert late_push.result == pb.COMMAND_RESULT_REJECTED
    assert not attempt.ready

    recovered = await runtime._wait_lifecycle_with_recovery(
        attempt, "setup_ready", frozenset({"acquisition"}), attempt.setup_deadline_ns
    )
    assert recovered
    assert len(peer.queries) == 1
    assert peer.queries[0].command_id == command_id
    assert attempt.ready["acquisition"] == ready
    post_recovery_push = await runtime.report_lifecycle(
        pb.LifecycleReport(ready=ready), runtime.clock()
    )
    assert post_recovery_push.result == pb.COMMAND_RESULT_REJECTED


@pytest.mark.asyncio
async def test_finished_recovery_keeps_exact_trial_identity_and_original_cutoff(
    tmp_path: Path,
) -> None:
    context = pb.BackendContext(backend_name="tracking", backend_generation=_id())
    runtime = _runtime(tmp_path, context)
    runtime.clock = time.monotonic_ns
    runtime.limits = replace(runtime.limits, recovery_ns=200_000_000)
    attempt = _attempt(runtime, tmp_path, {})
    trial = pb.TrialContext(session=attempt.context, trial_id=_id(), trial_number=1)
    attempt.prepared.trials.add(context=trial)
    attempt.trial_index = 0
    attempt.trial_operation = _id()
    attempt.target_ns = runtime.clock() - 10_000_000
    attempt.end_ns = runtime.clock() - 2_000_000
    attempt.finished_deadline_ns = runtime.clock() - 1_000_000
    finished = pb.FinishedReport(trial_activity_stopped=True)
    finished.context.backend.CopyFrom(context)
    finished.context.work.trial.CopyFrom(trial)
    finished.context.operation.command_id = attempt.trial_operation
    retained = svc.RetainedResult(
        found=True, backend=context, work=pb.WorkContext(trial=trial), finished=finished
    )
    peer = _RetainedPeer(context, retained)
    attempt.required["tracking"] = cast(BackendPort, peer)
    attempt.trial_participants["tracking"] = cast(BackendPort, peer)
    runtime.attempt = attempt
    runtime.session = pb.SessionState(
        phase=pb.SESSION_PHASE_RUNNING, context=attempt.context
    )
    runtime.trial = pb.TrialState(phase=pb.TRIAL_PHASE_FINALIZING, context=trial)

    late_push = await runtime.report_lifecycle(
        pb.LifecycleReport(finished=finished), runtime.clock()
    )
    assert late_push.result == pb.COMMAND_RESULT_REJECTED
    recovered = await runtime._wait_lifecycle_with_recovery(
        attempt, "finished", frozenset({"tracking"}), attempt.finished_deadline_ns
    )
    assert recovered
    assert len(peer.queries) == 1
    assert peer.queries[0].query.work.trial == trial
    assert attempt.finished["tracking"] == finished
    post_recovery_push = await runtime.report_lifecycle(
        pb.LifecycleReport(finished=finished), runtime.clock()
    )
    assert post_recovery_push.result == pb.COMMAND_RESULT_REJECTED


@pytest.mark.asyncio
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
    attempt.trial_log_started = True
    attempt.started["acquisition"] = pb.StartedReport()
    attempt.interrupted = True
    attempt.interruption_issued_ns = 1_000
    attempt.finished_deadline_ns = 2_000
    attempt.finalization_deadline_ns = 1_000_000_000_000
    runtime.attempt = attempt
    runtime.trial = pb.TrialState(context=trial, phase=pb.TRIAL_PHASE_FINALIZING)
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

    monkeypatch.setattr(runtime, "_persist", persist)
    monkeypatch.setattr(runtime, "_log_event", log_event)
    monkeypatch.setattr(runtime, "_wait_evidence", missing)
    monkeypatch.setattr(runtime, "_wait_lifecycle_with_recovery", missing_finished)
    monkeypatch.setattr(
        runtime, "_activity_backends", lambda _attempt: frozenset({"acquisition"})
    )
    attempt.trial_participants["acquisition"] = cast(
        BackendPort, _RetainedPeer(backend, svc.RetainedResult())
    )

    assert await runtime._finish_interrupted_trial(attempt)
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
    assert runtime.trial.outcome == pb.TRIAL_OUTCOME_INTERRUPTED
    assert not runtime.trial.HasField("actual_end_monotonic_ns")
    assert attempt.trial_log_finished
    assert plan.context == trial


@pytest.mark.asyncio
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
        runtime._metadata[command_id] = pb.MetadataResult(
            operation=pb.OperationContext(command_id=command_id),
            state=pb.METADATA_PERSISTENCE_PENDING,
            path=str(path),
        )
    writer = _RetiringWriter()
    await runtime._record_metadata(
        MetadataCompletion(first, path, "synced", 1_000),
        cast(MetadataWriter, writer),
        terminal=True,
    )
    await runtime._record_metadata(
        MetadataCompletion(failed, path, "failed", 1_000, "disk fault"),
        cast(MetadataWriter, writer),
        terminal=True,
    )
    runtime._metadata[latest].state = pb.METADATA_PERSISTENCE_UNCONFIRMED
    runtime._metadata[latest].failure.CopyFrom(
        pb.Failure(code="METADATA_WRITE", message="original deadline expired")
    )
    future: Future[MetadataCompletion] = Future()
    future.set_result(MetadataCompletion(latest, path, "synced", 1_001, "", False))
    runtime._enqueue_late_metadata(future, cast(MetadataWriter, writer), latest, path)
    assert runtime._metadata_drain_task is not None
    await runtime._metadata_drain_task

    assert first not in runtime._metadata
    assert runtime._metadata[failed].state == pb.METADATA_PERSISTENCE_FAILED
    assert runtime._metadata[latest].state == pb.METADATA_PERSISTENCE_SYNCED
    assert not runtime._metadata[latest].HasField("failure")
    assert any(
        "original deadline expired" in warning.message for warning in runtime._warnings
    )
    assert set(writer.retired) == {first, failed, latest}


def test_confirmed_full_nonessential_loss_skips_only_its_backend(
    tmp_path: Path,
) -> None:
    acq = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    vr = pb.BackendContext(backend_name="vr", backend_generation=_id())
    runtime = _runtime(tmp_path, acq)
    peers = {
        "acquisition": cast(BackendPort, _RetainedPeer(acq, svc.RetainedResult())),
        "vr": cast(BackendPort, _RetainedPeer(vr, svc.RetainedResult())),
    }
    attempt = _attempt(runtime, tmp_path, peers)
    trial = pb.TrialContext(session=attempt.context, trial_id=_id(), trial_number=1)
    plan = attempt.prepared.trials.add(context=trial)
    attempt.ready["acquisition"] = pb.ReadyReport(
        prepared_functions=[pb.PreparedFunctionScope(resource_id="acq-output")]
    )
    attempt.ready["vr"] = pb.ReadyReport(
        prepared_functions=[pb.PreparedFunctionScope(resource_id="vr-renderer")]
    )
    attempt.prepared.outputs.add(output_key="acq-output", trial=trial, backend=acq)
    attempt.confirmed_incidents[_id()] = pb.RuntimeIncident(
        affected_resources=["acq-output"]
    )

    selected = runtime._select_trial_participants(attempt, plan)
    assert set(selected) == {"vr"}


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
        history_save_timeout_ns=limits.history_ns,
        space_query_timeout_ns=limits.space_query_ns,
        low_space_warning_bytes=limits.low_space_bytes,
        default_intertrial_gap_ns=1_000,
        history_warning=None,
    )


@pytest.mark.asyncio
async def test_setup_reloads_mutable_limits_and_freezes_them_in_prepared_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vr = pb.BackendContext(backend_name="vr", backend_generation=_id())
    runtime = _runtime(tmp_path, vr)
    runtime.backends = {
        "vr": cast(BackendPort, _RetainedPeer(vr, svc.RetainedResult()))
    }
    runtime._supervisor_processes["vr"] = svc.ProcessHealthStatus(
        process=pb.ProcessIdentity(role="vr", generation=vr.backend_generation),
        process_running=True,
        connected=True,
    )
    runtime.configuration.mode = pb.SESSION_MODE_OPEN_LOOP
    runtime.configuration.recording_root = str(tmp_path)
    runtime.configuration.experiment = "experiment"
    runtime.configuration.subject = "subject"
    runtime.configuration.backends.add(backend_name="vr", enabled=True)
    runtime.configuration.trials.add(trial_number=1)
    runtime.validators = {
        "structural": lambda _: pb.ValidationResult(completed=True, valid=True)
    }
    runtime.file_policy_loader = lambda active: (
        {}
        if active == frozenset({"vr"})
        else (_ for _ in ()).throw(AssertionError("wrong active policy set"))
    )
    baseline = _settings(runtime.limits)
    adopted = replace(
        baseline, limits_kwargs={**baseline.limits_kwargs, "setup_ns": 20_000}
    )
    runtime.startup_settings = baseline
    runtime.settings_loader = lambda: adopted
    monkeypatch.setattr(runtime, "_authorized", lambda _command: None)

    async def no_backend_dispatch(
        _attempt: Attempt, _command_id: str, _deadline_ns: int
    ) -> None:
        return None

    monkeypatch.setattr(runtime, "_run_setup", no_backend_dispatch)
    command = svc.OperatorCommand()
    command.operator.command_id = _id()
    admission = await runtime.setup(command)
    assert admission.result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime.attempt is not None
    assert runtime.limits.setup_ns == 20_000
    assert runtime.attempt.prepared.policies == adopted.policies
    assert (
        runtime.attempt.setup_deadline_ns - runtime.attempt.prepared.anchor_monotonic_ns
        == 20_000
    )
    await asyncio.gather(*runtime._tasks)


@pytest.mark.asyncio
async def test_setup_rejects_changed_startup_transport_settings_before_reservation(
    tmp_path: Path,
) -> None:
    runtime = _runtime(
        tmp_path,
        pb.BackendContext(backend_name="acquisition", backend_generation=_id()),
    )
    runtime.validators = {
        "structural": lambda _: pb.ValidationResult(completed=True, valid=True)
    }
    baseline = _settings(runtime.limits)
    runtime.startup_settings = baseline
    runtime.settings_loader = lambda: replace(baseline, controller_port=50053)
    command = svc.OperatorCommand()
    command.operator.command_id = _id()

    admission = await runtime.setup(command)
    assert admission.result == pb.COMMAND_RESULT_REJECTED
    assert "restart required" in admission.failure.message
    assert runtime.attempt is None


@pytest.mark.asyncio
async def test_pending_incident_preserves_next_valid_trial_until_original_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vr = pb.BackendContext(backend_name="vr", backend_generation=_id())
    runtime = _runtime(tmp_path, vr)
    peer = cast(BackendPort, _RetainedPeer(vr, svc.RetainedResult()))
    attempt = _attempt(runtime, tmp_path, {"vr": peer})
    trial = pb.TrialContext(session=attempt.context, trial_id=_id(), trial_number=1)
    attempt.prepared.trials.add(context=trial)
    attempt.ready["vr"] = pb.ReadyReport(
        prepared_functions=[pb.PreparedFunctionScope(resource_id="renderer")]
    )
    error_id, incident_id = _id(), _id()
    attempt.incident_id_by_error[error_id] = incident_id
    attempt.incident_deadlines[error_id] = 2_000
    runtime.attempt = attempt
    runtime.session = pb.SessionState(
        phase=pb.SESSION_PHASE_RUNNING, context=attempt.context
    )
    entered: list[str] = []

    async def run_trial(_attempt: Attempt, _plan: pb.TrialPlan) -> None:
        entered.append("trial")

    async def finalize(_attempt: Attempt) -> None:
        entered.append("finalize")

    monkeypatch.setattr(runtime, "_prepare_and_run_trial", run_trial)
    monkeypatch.setattr(runtime, "_finalize", finalize)
    await runtime._run_trials(attempt)

    assert entered == ["trial", "finalize"]
    assert set(attempt.trial_participants) == {"vr"}


@pytest.mark.asyncio
async def test_startup_recovery_cancel_preserves_blocker_then_continue_clears_after_handler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(
        tmp_path,
        pb.BackendContext(backend_name="acquisition", backend_generation=_id()),
    )
    runtime.limits = replace(
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
    monkeypatch.setattr(runtime, "_authorized", lambda _command: None)
    cancel = svc.PromptResponse(
        prompt_id=prompt.prompt_id,
        setup=prompt.setup,
        setup_operation=prompt.operation,
        choice="cancel",
    )
    cancel.command.operator.command_id = _id()
    accepted_cancel = await runtime.respond_to_prompt(cancel)
    assert accepted_cancel.result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime._startup_blocker
    assert runtime._startup_prompt == prompt
    assert runtime._operations[cancel.command.operator.command_id].complete

    proceed = svc.PromptResponse(
        prompt_id=prompt.prompt_id,
        setup=prompt.setup,
        setup_operation=prompt.operation,
        choice="continue",
    )
    proceed.command.operator.command_id = _id()
    accepted_continue = await runtime.respond_to_prompt(proceed)
    assert accepted_continue.result == pb.COMMAND_RESULT_ACCEPTED
    assert runtime._startup_blocker
    gate.set()
    await asyncio.gather(*runtime._tasks)
    assert not runtime._startup_blocker
    assert runtime._startup_prompt is None
    assert runtime._operations[proceed.command.operator.command_id].complete
    assert runtime._operations[proceed.command.operator.command_id].succeeded
    assert any(
        "remote stop remains unconfirmed" in warning.message
        for warning in runtime._warnings
    )
