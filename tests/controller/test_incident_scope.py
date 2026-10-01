"""Incident reconfirmation, isolation scope and subsequent trial selection."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.incident.scope import ScopeConfirmation
from cephvr.controller.lifecycle.activity import select_trial_participants
from cephvr.controller.ports import BackendPort
from cephvr.controller.state import Attempt, IncidentState, LifecycleState
from tests.controller.support_components import _attempt, _id, _RetainedPeer, _runtime


def test_confirmed_full_nonessential_loss_skips_only_its_backend(
    tmp_path: Path,
) -> None:
    acq = pb.BackendContext(backend_name="acquisition", backend_generation=_id())
    visual_stimulus = pb.BackendContext(
        backend_name="visual_stimulus", backend_generation=_id()
    )
    runtime = _runtime(tmp_path, acq)
    peers = {
        "acquisition": cast(BackendPort, _RetainedPeer(acq, svc.RetainedResult())),
        "visual_stimulus": cast(
            BackendPort, _RetainedPeer(visual_stimulus, svc.RetainedResult())
        ),
    }
    attempt = _attempt(runtime, tmp_path, peers)
    trial = pb.TrialContext(session=attempt.context, trial_id=_id(), trial_number=1)
    plan = attempt.prepared.trials.add(context=trial)
    attempt.ready["acquisition"] = pb.ReadyReport(
        prepared_functions=[pb.PreparedFunctionScope(resource_id="acq-output")]
    )
    attempt.ready["visual_stimulus"] = pb.ReadyReport(
        prepared_functions=[
            pb.PreparedFunctionScope(resource_id="visual-stimulus-renderer")
        ]
    )
    attempt.prepared.outputs.add(output_key="acq-output", trial=trial, backend=acq)
    attempt.confirmed_incidents[_id()] = pb.RuntimeIncident(
        affected_resources=["acq-output"]
    )

    selected = select_trial_participants(attempt, plan)
    assert set(selected) == {"visual_stimulus"}


async def test_pending_incident_preserves_next_valid_trial_until_original_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    visual_stimulus = pb.BackendContext(
        backend_name="visual_stimulus", backend_generation=_id()
    )
    runtime = _runtime(tmp_path, visual_stimulus)
    peer = cast(BackendPort, _RetainedPeer(visual_stimulus, svc.RetainedResult()))
    attempt = _attempt(runtime, tmp_path, {"visual_stimulus": peer})
    trial = pb.TrialContext(session=attempt.context, trial_id=_id(), trial_number=1)
    attempt.prepared.trials.add(context=trial)
    attempt.ready["visual_stimulus"] = pb.ReadyReport(
        prepared_functions=[pb.PreparedFunctionScope(resource_id="renderer")]
    )
    error_id, incident_id = _id(), _id()
    attempt.incident_id_by_error[error_id] = incident_id
    attempt.incident_deadlines[error_id] = 2_000
    runtime.lifecycle.attempt = attempt
    runtime.lifecycle.session = pb.SessionState(
        phase=pb.SESSION_PHASE_RUNNING, context=attempt.context
    )
    entered: list[str] = []

    async def run_trial(_attempt: Attempt, _plan: pb.TrialPlan) -> None:
        entered.append("trial")

    async def finalize(_attempt: Attempt) -> None:
        entered.append("finalize")

    monkeypatch.setattr(runtime.trials, "prepare_and_run_trial", run_trial)
    monkeypatch.setattr(runtime.interruption, "finalize", finalize)
    await runtime.trials.run_trials(attempt)

    assert entered == ["trial", "finalize"]
    assert set(attempt.trial_participants) == {"visual_stimulus"}


class _Supervisor:
    async def register_context(
        self, request: svc.RegisterContextRequest
    ) -> svc.RegistrationReceipt:
        return svc.RegistrationReceipt(
            admission=pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED),
            registered=request.context,
        )


class _Registry:
    def observe(self, error: object, classification: object, **_kw: object) -> Any:
        return pb.RuntimeIncident(incident_id="inc", revision=2)


async def test_reconfirmation_replaces_incident_in_scope_and_plans(
    tmp_path: Path,
) -> None:
    runtime = _runtime(
        tmp_path,
        pb.BackendContext(backend_name="visual_stimulus", backend_generation=_id()),
    )
    attempt = _attempt(runtime, tmp_path, {})
    prior = pb.RuntimeIncident(incident_id="inc", revision=1)
    attempt.confirmed_incidents["inc"] = prior
    attempt.registered_context = svc.RegisteredContext()
    attempt.registered_context.continuation_incidents.add().CopyFrom(prior)
    attempt.incident_topology = cast(Any, object())
    attempt.incidents = cast(Any, _Registry())
    plan = attempt.prepared.trials.add()
    plan.continuation_incidents.add().CopyFrom(prior)
    lifecycle = LifecycleState(attempt=attempt)
    scope = ScopeConfirmation(
        lifecycle=lifecycle,
        incidents=IncidentState(),
        limits=runtime.limit_state,
        clock=lambda: 0,
        publisher=cast(Any, SimpleNamespace(publish=lambda: None)),
        evidence_waiter=cast(Any, None),
        preparation_context=cast(Any, None),
        lifecycle_reports=cast(Any, None),
        supervisor=cast(Any, _Supervisor()),
        interrupt=cast(Any, None),
        spawn=lambda c: asyncio.create_task(c),
        log_incident=cast(Any, None),
    )

    async def dispatched(*_args: object) -> dict[str, str]:
        return {}

    scope._dispatch_and_verify = dispatched  # type: ignore[method-assign]
    await scope._confirm_incident_scope_serial(
        attempt,
        pb.ErrorReport(),
        pb.RuntimeIncident(incident_id="inc", revision=1),
        SimpleNamespace(reason="r"),
        10**12,
    )
    for entries in (
        attempt.registered_context.continuation_incidents,
        plan.continuation_incidents,
    ):
        assert [(i.incident_id, i.revision) for i in entries] == [("inc", 2)]


@pytest.mark.parametrize("already_confirmed", [True, False])
async def test_confirmed_incident_is_not_reconfirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, already_confirmed: bool
) -> None:
    from dataclasses import dataclass

    from cephvr.controller.incident import coordination as module
    from cephvr.controller.state import LimitsState, SupervisorState

    @dataclass
    class _Class:
        status: str
        reason: str
        affected_resources: tuple[str, ...]
        deadline_ns: int

    monkeypatch.setattr(
        module,
        "classify_incident",
        lambda *a, **k: _Class("continuable", "ok", ("r",), 10**12),
    )
    runtime = _runtime(
        tmp_path,
        pb.BackendContext(backend_name="visual_stimulus", backend_generation=_id()),
    )
    attempt = _attempt(runtime, tmp_path, {})
    attempt.incident_topology = cast(Any, object())
    attempt.incidents = cast(Any, _Registry())
    if already_confirmed:
        attempt.confirmed_incidents["inc"] = pb.RuntimeIncident(incident_id="inc")
    lifecycle = LifecycleState(
        attempt=attempt, session=pb.SessionState(phase=pb.SESSION_PHASE_RUNNING)
    )
    spawned: list[str] = []

    def spawn(coroutine: Any) -> asyncio.Task[Any]:
        spawned.append(coroutine.cr_code.co_name)
        coroutine.close()
        return cast(Any, None)

    coordinator = module.IncidentCoordinator(
        lifecycle=lifecycle,
        incidents=IncidentState(),
        supervisor_state=SupervisorState(last_seen_ns=0),
        limits=LimitsState(runtime.limit_state.current),
        health_silence_ns=10**12,
        clock=lambda: 0,
        publisher=cast(Any, SimpleNamespace(publish=lambda: None)),
        metadata=cast(Any, None),
        evidence_waiter=cast(Any, None),
        preparation_context=cast(Any, None),
        lifecycle_reports=cast(Any, None),
        supervisor=None,
        interrupt=cast(Any, None),
        spawn=spawn,
    )
    await coordinator.observe_runtime_error(pb.ErrorReport(error_id=_id()))
    assert ("confirm_incident_scope" in spawned) is (not already_confirmed)
